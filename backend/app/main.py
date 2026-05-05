from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, appointment_requests, appointments, auth, briefings, cash_reconciliation, clients, households, inbound_email, internal, payment_methods, promotions, provider_service_prices, providers, public, reports, retail_items, sales, schedules, scheduling, service_categories, services, time_blocks, time_entries
from app.routers import settings as settings_router

app = FastAPI(
    title="Salon Lyol Management API",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(appointments.router)
app.include_router(appointment_requests.router)
app.include_router(providers.router)
app.include_router(clients.router)
app.include_router(households.router)
app.include_router(services.router)
app.include_router(service_categories.router)
app.include_router(provider_service_prices.router)
app.include_router(schedules.router)
app.include_router(time_blocks.router)
app.include_router(settings_router.router)
app.include_router(payment_methods.router)
app.include_router(sales.router)
app.include_router(cash_reconciliation.router)
app.include_router(promotions.router)
app.include_router(retail_items.router)
app.include_router(reports.router)
app.include_router(public.router)
app.include_router(internal.router)
app.include_router(briefings.router)
app.include_router(inbound_email.router)
app.include_router(time_entries.router)
app.include_router(scheduling.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "environment": settings.environment}
