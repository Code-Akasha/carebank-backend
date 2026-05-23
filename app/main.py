import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware
except Exception:  # pragma: no cover - older starlette in tests may not provide this
    # Minimal fallback ASGI middleware that honors X-Forwarded-Proto so the
    # application sees the original client scheme when behind a TLS
    # terminating proxy. This avoids importing a missing symbol in older
    # starlette versions used by test environments.
    class ProxyHeadersMiddleware:
        def __init__(self, app, trusted_hosts: str | None = None):
            self.app = app

        async def __call__(self, scope, receive, send):
            # Only operate on HTTP requests
            if scope.get("type") == "http":
                headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
                proto = headers.get("x-forwarded-proto")
                if proto:
                    # take the first value if multiple
                    scope["scheme"] = proto.split(",")[0].strip()
            await self.app(scope, receive, send)

from app.core.config import get_settings
from app.core.database import init_db
from app.routes.accounts import router as accounts_router
from app.routes.actions import router as actions_router
from app.routes.admin import router as admin_router
from app.routes.admin_banking_config import router as admin_banking_config_router
from app.routes.admin_llm_config import router as admin_llm_config_router
from app.routes.auth import router as auth_router
from app.routes.auto_savings import router as auto_savings_router
from app.routes.balances import router as balances_router
from app.routes.bank_schedules import router as bank_schedules_router
from app.routes.beneficiaries import router as beneficiaries_router
from app.routes.bills import router as bills_router
from app.routes.bot import router as bot_router
from app.routes.business_bills import router as business_bills_router
from app.routes.chat import router as chat_router
from app.routes.events import router as events_router
from app.routes.health_score import router as health_score_router
from app.routes.notifications import router as notifications_router
from app.routes.payment_settings import router as payment_settings_router
from app.routes.payments import router as payments_router
from app.routes.planning import router as planning_router
from app.routes.products import router as products_router
from app.routes.profile import router as profile_router
from app.routes.providers import router as providers_router
from app.routes.recurring_payments import router as recurring_payments_router
from app.routes.service_plans import router as service_plans_router
from app.routes.simulate import router as simulate_router
from app.routes.tools import router as tools_router
from app.routes.transactions import router as transactions_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FastAPI application...")

    # Initialize database with error handling - don't block startup if it fails
    try:
        init_db()
        logger.info("Database initialization completed successfully")
    except Exception as exc:
        logger.error(f"Database initialization failed: {exc}", exc_info=True)
        # Continue - database might be initializing, this is non-fatal for health checks
        logger.warning(
            "Continuing startup despite database error - health endpoint will be available",
        )

    # Start recurring payment scheduler (BackgroundScheduler is thread-based,
    # no conflict with FastAPI's asyncio event loop)
    try:
        from app.services.recurring_scheduler import start_scheduler

        start_scheduler()
        logger.info("Recurring payment scheduler started")
    except Exception as exc:
        logger.warning("Failed to start recurring scheduler (non-fatal): %s", exc)

    yield

    # Stop scheduler on shutdown
    try:
        from app.services.recurring_scheduler import stop_scheduler

        stop_scheduler()
        logger.info("Recurring payment scheduler stopped")
    except Exception as exc:
        logger.warning("Failed to stop scheduler (non-fatal): %s", exc)


app = FastAPI(
    title="CareBank Backend",
    description="Personalized Banking & Financial Wellness API",
    version="0.2.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trust proxy headers (X-Forwarded-For, X-Forwarded-Proto) so generated
# absolute URLs / redirect locations use the original client scheme (https)
# when running behind TLS-terminating load balancers / container ingress.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.include_router(auth_router)
app.include_router(bills_router)
app.include_router(admin_router)
app.include_router(admin_llm_config_router)
app.include_router(admin_banking_config_router)
app.include_router(profile_router)
app.include_router(planning_router)
app.include_router(actions_router)
app.include_router(notifications_router)
app.include_router(transactions_router)
app.include_router(balances_router)
app.include_router(products_router)
app.include_router(accounts_router)
app.include_router(beneficiaries_router)
app.include_router(bank_schedules_router)
app.include_router(providers_router)
app.include_router(health_score_router)
app.include_router(chat_router)
app.include_router(simulate_router)
app.include_router(events_router)
app.include_router(bot_router)
app.include_router(tools_router)
app.include_router(payment_settings_router)
app.include_router(payments_router)
app.include_router(recurring_payments_router)
app.include_router(auto_savings_router)
app.include_router(service_plans_router)
app.include_router(business_bills_router)


@app.get("/")
async def health():
    return {"status": "CareBank Backend Running", "version": "0.2.0"}
