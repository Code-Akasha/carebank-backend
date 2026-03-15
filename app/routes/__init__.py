from app.routes.transactions import router as transactions_router
from app.routes.balances import router as balances_router
from app.routes.products import router as products_router
from app.routes.accounts import router as accounts_router
from app.routes.beneficiaries import router as beneficiaries_router
from app.routes.bank_schedules import router as bank_schedules_router
from app.routes.providers import router as providers_router
from app.routes.health_score import router as health_score_router
from app.routes.chat import router as chat_router
from app.routes.profile import router as profile_router
from app.routes.planning import router as planning_router
from app.routes.actions import router as actions_router

__all__ = [
    "transactions_router",
    "balances_router",
    "products_router",
    "accounts_router",
    "beneficiaries_router",
    "bank_schedules_router",
    "providers_router",
    "health_score_router",
    "chat_router",
    "profile_router",
    "planning_router",
    "actions_router",
]
