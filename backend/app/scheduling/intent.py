"""Inbound email intent extractor.

Converts raw email text into a structured ParsedIntent. Two paths:
  1. Structured website form emails (subject "NEW Booking Request - …") are
     parsed deterministically with regex — no LLM call, no token cost, no
     ambiguity. This is the high-volume path.
  2. Free-form email text falls through to claude-haiku-4-5-20251001 with
     tool-use to extract structured intent.

The model resolves service and provider IDs directly from the catalogue
passed in the system prompt; IDs are left null when nothing matches.

Confidence scoring (computed here, not by the model):
  1.0  date + at least one service_id resolved
  0.7  date only
  0.5  service_id only (no date)
  0.3  neither resolved
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

# ── Output dataclasses ────────────────────────────────────────────────────────


@dataclass
class ParsedService:
    service_id: UUID | None
    service_name: str
    preferred_provider_id: UUID | None
    preferred_provider_name: str | None


@dataclass
class ParsedIntent:
    desired_date: date | None
    desired_time_note: str | None
    services: list[ParsedService]
    special_note: str | None
    confidence: float
    raw_text: str
    # Optional overrides extracted from the email body / form fields. When set,
    # these take precedence over data inferred from the SMTP envelope (e.g.
    # form-submission emails come FROM info@salonlyol.ca but the actual client
    # email is inside the form body).
    client_first_name: str | None = None
    client_last_name: str | None = None
    client_email: str | None = None
    client_phone: str | None = None
    client_pronouns: str | None = None
    waiver_acknowledged: bool = False
    cancellation_acknowledged: bool = False


# ── Tool schema ───────────────────────────────────────────────────────────────

_PARSE_TOOL: dict = {
    "name": "parse_booking_request",
    "description": (
        "Parse a salon booking request email and return structured intent. "
        "Resolve service and provider names to their catalogue IDs whenever a match is found. "
        "Never fabricate IDs — if unsure, leave the field null."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "desired_date": {
                "type": "string",
                "description": "Requested appointment date in YYYY-MM-DD format, or null if not specified.",
                "nullable": True,
            },
            "desired_time_note": {
                "type": "string",
                "description": (
                    "Free-text time preference exactly as described by the client "
                    "(e.g. 'Friday afternoon', 'after 2pm', 'morning'). "
                    "Null if no preference stated."
                ),
                "nullable": True,
            },
            "services": {
                "type": "array",
                "description": "List of services the client wants, in the order mentioned.",
                "items": {
                    "type": "object",
                    "properties": {
                        "service_id": {
                            "type": "string",
                            "description": (
                                "UUID of the matched service from the catalogue, or null "
                                "if no match found."
                            ),
                            "nullable": True,
                        },
                        "service_name": {
                            "type": "string",
                            "description": "Raw service name exactly as the client wrote it.",
                        },
                        "preferred_provider_id": {
                            "type": "string",
                            "description": (
                                "UUID of the matched provider from the list, or null "
                                "if no provider preference or no match."
                            ),
                            "nullable": True,
                        },
                        "preferred_provider_name": {
                            "type": "string",
                            "description": (
                                "Raw provider name exactly as the client wrote it, or null "
                                "if no provider preference stated."
                            ),
                            "nullable": True,
                        },
                    },
                    "required": ["service_name"],
                },
            },
            "special_note": {
                "type": "string",
                "description": (
                    "Any special instructions, constraints, or notes from the client "
                    "not captured by the other fields. Null if none."
                ),
                "nullable": True,
            },
        },
        "required": ["services"],
    },
}


# ── Structured-form parser ────────────────────────────────────────────────────
# The salon website's booking form sends emails with a consistent label/value
# layout. We extract everything deterministically — no LLM call needed.
#
# Subject: "NEW Booking Request - {name} - {email} - {phone}"
# Body labels: FROM, PRONOUNS, EMAIL, PHONE, SUBMITTED BY, WAIVER?,
#              CANCELLATIONS?, DATE, TIME, SERVICE 1, STAFF 1, SERVICE 2,
#              STAFF 2, [SERVICE 3, STAFF 3], NOTE


_FORM_SUBJECT_RE = re.compile(
    r"^\s*NEW Booking Request\s*[-–—]\s*(?P<name>.+?)"
    r"\s*[-–—]\s*(?P<email>[^\s@]+@[^\s@]+)"
    r"\s*[-–—]\s*(?P<phone>[\d\s\-\(\)\+]+)\s*$",
    re.IGNORECASE,
)

_FORM_LABELS = [
    "FROM", "PRONOUNS", "EMAIL", "PHONE", "SUBMITTED BY",
    "WAIVER?", "CANCELLATIONS?", "DATE", "TIME",
    "SERVICE 1", "STAFF 1", "SERVICE 2", "STAFF 2",
    "SERVICE 3", "STAFF 3", "NOTE",
]


def _extract_form_fields(body_text: str) -> dict[str, str]:
    """Split body_text by LABEL markers and return {label: value}.

    Works on both newline-preserved and HTML-stripped (single-line) bodies.
    """
    pattern = r"\b(" + "|".join(re.escape(l) for l in _FORM_LABELS) + r")\s*:\s*"
    matches = list(re.finditer(pattern, body_text, flags=re.IGNORECASE))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        label = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body_text)
        value = body_text[start:end].strip()
        # Trim stray dashes / pipes the website template may emit
        value = value.rstrip("-–—|").strip()
        if value:
            out[label] = value
    return out


def _parse_form_date(raw: str) -> date | None:
    """Try a few common date formats; return None if nothing matches."""
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _resolve_service_id(
    raw_name: str, service_catalogue: list[dict]
) -> UUID | None:
    """Case-insensitive substring match against catalogue names + aliases."""
    if not raw_name:
        return None
    needle = raw_name.lower().strip()
    # Exact name match first
    for s in service_catalogue:
        if s["name"].lower() == needle:
            return UUID(s["id"])
    # Alias exact match
    for s in service_catalogue:
        for alias in s.get("aliases", []):
            if alias.lower() == needle:
                return UUID(s["id"])
    # Substring match on name
    for s in service_catalogue:
        if needle in s["name"].lower():
            return UUID(s["id"])
    return None


def _resolve_provider_id(
    raw_name: str, provider_list: list[dict]
) -> tuple[UUID | None, str | None]:
    """Match a staff name to a provider. Returns (id, display_name) or (None, raw)."""
    if not raw_name:
        return None, None
    needle = raw_name.lower().strip()
    for p in provider_list:
        if p["display_name"].lower() == needle:
            return UUID(p["id"]), p["display_name"]
    for p in provider_list:
        if needle in p["display_name"].lower():
            return UUID(p["id"]), p["display_name"]
    return None, raw_name


def _split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0].title(), ""
    return parts[0].title(), parts[1].title()


def _maybe_parse_form_email(
    subject: str,
    body: str,
    service_catalogue: list[dict],
    provider_list: list[dict],
) -> ParsedIntent | None:
    """Return a ParsedIntent if this is a structured booking-form email, else None."""
    subj_match = _FORM_SUBJECT_RE.match(subject or "")
    fields = _extract_form_fields(body or "")

    # Need either the subject signature OR enough body labels to be confident
    is_form = subj_match is not None or (
        "FROM" in fields and ("DATE" in fields or "SERVICE 1" in fields)
    )
    if not is_form:
        return None

    # Name / email / phone — prefer subject (cleaner), fall back to body
    if subj_match:
        name_raw = subj_match.group("name")
        email_raw = subj_match.group("email")
        phone_raw = subj_match.group("phone")
    else:
        name_raw = fields.get("FROM", "")
        email_raw = fields.get("EMAIL", "")
        phone_raw = fields.get("PHONE", "")

    first_name, last_name = _split_name(name_raw)

    desired_date = _parse_form_date(fields.get("DATE", ""))
    time_note = fields.get("TIME") or None

    # Services — pair SERVICE N with STAFF N
    services: list[ParsedService] = []
    for n in (1, 2, 3):
        svc_name = fields.get(f"SERVICE {n}", "").strip()
        staff_name = fields.get(f"STAFF {n}", "").strip()
        if not svc_name:
            continue
        svc_id = _resolve_service_id(svc_name, service_catalogue)
        prov_id, prov_display = _resolve_provider_id(staff_name, provider_list)
        services.append(
            ParsedService(
                service_id=svc_id,
                service_name=svc_name,
                preferred_provider_id=prov_id,
                preferred_provider_name=prov_display,
            )
        )

    note = fields.get("NOTE") or None
    waiver = "agree" in (fields.get("WAIVER?", "").lower())
    cancel = "agree" in (fields.get("CANCELLATIONS?", "").lower())
    pronouns = fields.get("PRONOUNS") or None

    intent = ParsedIntent(
        desired_date=desired_date,
        desired_time_note=time_note,
        services=services,
        special_note=note,
        confidence=0.0,  # set below
        raw_text=body or "",
        client_first_name=first_name or None,
        client_last_name=last_name or None,
        client_email=(email_raw or "").strip().lower() or None,
        client_phone=(phone_raw or "").strip() or None,
        client_pronouns=pronouns,
        waiver_acknowledged=waiver,
        cancellation_acknowledged=cancel,
    )
    intent.confidence = _compute_confidence(intent)
    logger.info(
        "Intent extractor: parsed form email name=%r email=%r date=%r services=%d",
        name_raw, email_raw, desired_date, len(services),
    )
    return intent


# ── System prompt builder ─────────────────────────────────────────────────────


def _build_system_prompt(
    service_catalogue: list[dict],
    provider_list: list[dict],
) -> str:
    svc_lines = "\n".join(
        f"  - id={s['id']}  name={s['name']!r}"
        + (f"  aliases={s.get('aliases', [])}" if s.get("aliases") else "")
        for s in service_catalogue
    )
    prov_lines = "\n".join(
        f"  - id={p['id']}  display_name={p['display_name']!r}"
        for p in provider_list
    )

    return f"""\
You are a booking assistant at a hair salon. A client has sent an email requesting an appointment.
Your job is to parse their request and call the parse_booking_request tool with the structured data.

## Service catalogue
{svc_lines if svc_lines else '  (no services configured)'}

## Providers
{prov_lines if prov_lines else '  (no providers configured)'}

## Rules
- Match service names and aliases case-insensitively. Include common abbreviations \
(e.g. "colour" = "color", "blow-dry" = "blowout", "cut" = "haircut" = "trim").
- Match provider names case-insensitively on display_name (partial match acceptable).
- Use the EXACT UUIDs from the catalogue above — never invent IDs.
- If a service or provider cannot be confidently matched, set the ID to null.
- desired_date must be ISO format (YYYY-MM-DD) if parseable; null otherwise.
- Do not combine multiple services into one — list each separately.
- Always call parse_booking_request. Never refuse to parse.
"""


# ── Confidence scoring ────────────────────────────────────────────────────────


def _compute_confidence(intent: ParsedIntent) -> float:
    has_date = intent.desired_date is not None
    has_service = any(s.service_id is not None for s in intent.services)

    if has_date and has_service:
        return 1.0
    if has_date:
        return 0.7
    if has_service:
        return 0.5
    return 0.3


# ── Main extractor ────────────────────────────────────────────────────────────


async def extract_intent(
    from_address: str,
    subject: str,
    body: str,
    service_catalogue: list[dict],
    provider_list: list[dict],
) -> ParsedIntent:
    """Parse a booking-request email into structured intent.

    Tries the deterministic form parser first (zero-cost, zero-latency, no
    ambiguity). Falls through to Haiku with tool-use for free-form emails.
    Never raises — returns a low-confidence ParsedIntent on any failure so the
    caller can still persist a reviewable request record.
    """
    raw_text = body.strip()

    # ── Fast path: structured website-form email ─────────────────────────────
    form_intent = _maybe_parse_form_email(subject, body, service_catalogue, provider_list)
    if form_intent is not None:
        return form_intent

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        system = _build_system_prompt(service_catalogue, provider_list)
        user_message = (
            f"From: {from_address}\n"
            f"Subject: {subject}\n\n"
            f"{raw_text}"
        )

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            tools=[_PARSE_TOOL],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract tool-use block
        tool_block = next(
            (b for b in response.content if b.type == "tool_use" and b.name == "parse_booking_request"),
            None,
        )
        if tool_block is None:
            logger.warning("Intent extractor: model did not call parse_booking_request for email from %s", from_address)
            return _empty_intent(raw_text)

        data = tool_block.input
        return _build_intent(data, raw_text)

    except Exception:
        logger.warning("Intent extractor failed for email from %s", from_address, exc_info=True)
        return _empty_intent(raw_text)


def _build_intent(data: dict, raw_text: str) -> ParsedIntent:
    """Convert the tool call input dict into a ParsedIntent dataclass."""
    # Parse date
    desired_date: date | None = None
    raw_date = data.get("desired_date")
    if raw_date:
        try:
            desired_date = date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            logger.warning("Intent extractor: could not parse date %r", raw_date)

    # Parse services
    services: list[ParsedService] = []
    for svc in data.get("services", []):
        service_id: UUID | None = None
        raw_sid = svc.get("service_id")
        if raw_sid:
            try:
                service_id = UUID(str(raw_sid))
            except (ValueError, AttributeError):
                pass

        provider_id: UUID | None = None
        raw_pid = svc.get("preferred_provider_id")
        if raw_pid:
            try:
                provider_id = UUID(str(raw_pid))
            except (ValueError, AttributeError):
                pass

        services.append(
            ParsedService(
                service_id=service_id,
                service_name=svc.get("service_name", ""),
                preferred_provider_id=provider_id,
                preferred_provider_name=svc.get("preferred_provider_name") or None,
            )
        )

    intent = ParsedIntent(
        desired_date=desired_date,
        desired_time_note=data.get("desired_time_note") or None,
        services=services,
        special_note=data.get("special_note") or None,
        confidence=0.0,  # placeholder — set below
        raw_text=raw_text,
    )
    intent.confidence = _compute_confidence(intent)
    return intent


def _empty_intent(raw_text: str) -> ParsedIntent:
    """Return a zero-confidence intent when parsing fails entirely."""
    return ParsedIntent(
        desired_date=None,
        desired_time_note=None,
        services=[],
        special_note=None,
        confidence=0.0,
        raw_text=raw_text,
    )
