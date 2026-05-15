# ADR-003: Database, ORM, and Migrations — PostgreSQL + SQLAlchemy + Alembic

**Date:** 2026-04-20
**Status:** Accepted
**Deciders:** Frederick Ferguson

---

## Context

The system requires a relational database, an ORM for Python model definitions, and a migration tool to manage schema evolution. Requirements:

- Multi-tenant schema with `tenant_id` on every scoped table
- UUID primary keys
- Complex queries: appointment scheduling (time window overlap detection), reporting aggregations, CRM history
- Schema migrations as a first-class habit from day one (Design Principle #3)
- PostgreSQL-specific features are acceptable — the system is not targeting multi-database portability
- Local development via Docker Compose; cloud deployment on managed Postgres (see ADR-001)

---

## Decision

**PostgreSQL 16** (database) + **SQLAlchemy 2.x async** (ORM) + **Alembic** (migrations).

---

## Rationale

### PostgreSQL

| Criterion | PostgreSQL | MySQL / MariaDB | SQLite |
|-----------|-----------|-----------------|--------|
| UUID native type | ✓ | requires workaround | ✓ (text) |
| Overlap / range operators | ✓ `tstzrange`, `&&` | limited | no |
| JSONB for flexible fields | ✓ | limited | no |
| Row-level security (Phase 3 tenant isolation) | ✓ | limited | no |
| Managed cloud offering | ✓ both GCP + Azure | ✓ | n/a |

PostgreSQL's `tstzrange` type and `&&` overlap operator are directly useful for appointment scheduling queries (find conflicting time windows). Row-level security is the preferred Phase 3 multi-tenancy enforcement mechanism. SQLite is ruled out for production; MySQL lacks the range type support.

### SQLAlchemy 2.x (async)

SQLAlchemy 2.x with async sessions (`AsyncSession`) integrates cleanly with FastAPI's async request handlers. The 2.x API (`select()`, `scalars()`) is cleaner than the legacy 1.x query API. Alternatives:

- **Tortoise ORM / SQLModel** — lighter but smaller ecosystem; SQLModel's maturity is still limited for complex relationships
- **Raw asyncpg** — maximum performance but no ORM layer; too low-level for rapid Phase 1 development
- **Django ORM** — ruled out with Django (ADR-002)

SQLAlchemy's explicit mapping keeps models decoupled from the database driver, which is important for testability.

### Alembic

Alembic is the standard SQLAlchemy migration companion. Key decisions:

- Migrations live in `migrations/` at the repo root
- **Every model change requires a migration** — no `Base.metadata.create_all()` in production, ever
- Migration scripts are reviewed before merging, not auto-generated blindly
- `alembic upgrade head` runs as a dedicated CI step (`.github/workflows/deploy.yml`) **before** the new Cloud Run revision is rolled out. Migrations used to run inside `docker-entrypoint.sh` but the Cloud SQL socket isn't reliably mounted at container startup on Cloud Run Gen2, which caused revisions to time out before binding to `PORT`. The container entrypoint now only starts uvicorn.

---

## Consequences

- **Positive:** PostgreSQL range types simplify appointment overlap detection significantly.
- **Positive:** Alembic autogenerate gives a starting point for migrations; manual review catches subtle issues (index additions, constraint naming).
- **Positive:** SQLAlchemy models serve as the canonical schema definition — ERM entities map 1:1 to SQLAlchemy `DeclarativeBase` subclasses.
- **Negative:** SQLAlchemy async requires careful session lifecycle management in FastAPI (dependency injection pattern for `AsyncSession`).
- **Negative:** Alembic autogenerate does not detect all changes (e.g., check constraints, some index types) — manual migration additions will be needed occasionally.
- **Neutral:** Local Docker Compose runs `postgres:16`. Cloud uses managed PostgreSQL (Cloud SQL or Azure Database for PostgreSQL — see ADR-001). Connection string in environment variable per 12-factor config.

---

## Migration Conventions

```
migrations/
├── env.py              # Alembic env — imports all models for autogenerate
├── script.py.mako      # Template for new revisions
└── versions/
    └── 0001_initial.py # First migration: Tenant + User
```

- Revision IDs: sequential prefix (`0001_`, `0002_`) for readability
- Naming: `{seq}_{short_description}.py` — e.g., `0003_add_provider_schedule_block.py`
- Downgrade functions: always implement, even if it's just `pass` with a comment explaining why reversal is unsafe
