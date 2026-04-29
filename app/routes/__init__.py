from __future__ import annotations

__all__ = [
    "bills_router",
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
    "auto_savings_router",
]


def __getattr__(name: str):
    router_modules = {
        "bills_router": ("app.routes.bills", "router"),
        "transactions_router": ("app.routes.transactions", "router"),
        "balances_router": ("app.routes.balances", "router"),
        "products_router": ("app.routes.products", "router"),
        "accounts_router": ("app.routes.accounts", "router"),
        "beneficiaries_router": ("app.routes.beneficiaries", "router"),
        "bank_schedules_router": ("app.routes.bank_schedules", "router"),
        "providers_router": ("app.routes.providers", "router"),
        "health_score_router": ("app.routes.health_score", "router"),
        "chat_router": ("app.routes.chat", "router"),
        "profile_router": ("app.routes.profile", "router"),
        "planning_router": ("app.routes.planning", "router"),
        "actions_router": ("app.routes.actions", "router"),
        "auto_savings_router": ("app.routes.auto_savings", "router"),
    }
    target = router_modules.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = target
    module = __import__(module_name, fromlist=[attr_name])
    return getattr(module, attr_name)
