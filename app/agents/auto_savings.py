import logging

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.core.database import SessionLocal
from app.models.user_profile import UserProfile
from app.services.banking_client import (
    BankingClientError,
    get_accounts_sync,
    get_balance_sync,
    get_transactions_sync,
)
from app.services.data import generate_mock_transactions
from app.services.forecast import forecast_balance

logger = logging.getLogger(__name__)


class AutoSavingsAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "AutoSavingsAgent"

    @property
    def description(self) -> str:
        return (
            "Recommends optimal savings amounts based on financial forecasts and safety thresholds. "
            "Analyzes upcoming expenses and income to suggest safe micro-savings transfers."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "auto_savings_recommendation",
            "micro_savings",
            "budget_analysis",
            "savings_goal_tracking",
            "safe_transfer_calculation",
        ]

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        user_id = agent_input.user_id
        transactions = self._fetch_transactions(user_id)
        current_balance = self._fetch_balance(user_id)
        accounts = self._fetch_accounts(user_id)
        profile = self._fetch_profile(user_id)

        # Forecast balance for next week (7 days)
        forecast_result = forecast_balance(transactions, periods=7)
        predicted_balance = forecast_result.get("predicted_balance", current_balance)

        # Personalize safety and transfer sizing using persisted profile settings.
        safety_threshold = self._derive_safety_threshold(accounts, profile)
        savings_ratio = self._target_savings_ratio(profile)
        transfer_cap = self._max_transfer_cap(profile)

        if predicted_balance > safety_threshold:
            # Move a profile-aware percentage of forecasted surplus.
            surplus = predicted_balance - safety_threshold
            suggested_amount = min(transfer_cap, int(surplus * savings_ratio))
            goal_progress = self._estimate_goal_progress(
                profile,
                suggested_amount=suggested_amount,
            )

            if suggested_amount >= 50:
                # We have a meaningful amount to save
                response = (
                    f"Good news! Based on your forecast, you can safely save ₹{suggested_amount} this week "
                    "without affecting your upcoming bills. This would bring your savings "
                    f"goal progress to {int(goal_progress * 100)}%. Would you like to approve this micro-transfer?"
                )
                return AgentOutput(
                    response=response,
                    agent_name=self.name,
                    confidence=0.9,
                    metadata={
                        "intent_handled": "auto_savings",
                        "suggested_amount": suggested_amount,
                        "goal_progress": goal_progress,
                        "safety_threshold": safety_threshold,
                        "savings_ratio": savings_ratio,
                        "transfer_cap": transfer_cap,
                    },
                )

        # If not safe, suggest no savings
        return AgentOutput(
            response=(
                "Based on your forecast, things are a bit tight this week so I am not suggesting any auto-savings right now."
            ),
            agent_name=self.name,
            confidence=0.9,
            metadata={
                "intent_handled": "auto_savings",
                "suggested_amount": 0,
                "goal_progress": self._estimate_goal_progress(
                    profile,
                    suggested_amount=0,
                ),
                "safety_threshold": safety_threshold,
                "savings_ratio": savings_ratio,
                "transfer_cap": transfer_cap,
            },
        )

    def _fetch_profile(self, user_id: str) -> UserProfile | None:
        with SessionLocal() as db:
            return db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    def _fetch_transactions(self, user_id: str) -> list[dict]:
        try:
            return get_transactions_sync(user_id=user_id)
        except BankingClientError as exc:
            logger.warning(
                "AutoSavingsAgent fallback transactions for %s: %s",
                user_id,
                exc,
            )
            return generate_mock_transactions(user_id, days=90)

    def _fetch_balance(self, user_id: str) -> float:
        try:
            balance = get_balance_sync(user_id)
            return float(balance.get("current_balance", 0.0))
        except BankingClientError as exc:
            logger.warning("AutoSavingsAgent fallback balance for %s: %s", user_id, exc)
            return 0.0

    def _fetch_accounts(self, user_id: str) -> list[dict]:
        try:
            return get_accounts_sync(user_id)
        except BankingClientError as exc:
            logger.warning(
                "AutoSavingsAgent fallback accounts for %s: %s",
                user_id,
                exc,
            )
            return [
                {
                    "account_type": "checking",
                    "current_balance": 25000.0,
                    "available_balance": 20000.0,
                },
            ]

    def _derive_safety_threshold(
        self,
        accounts: list[dict],
        profile: UserProfile | None,
    ) -> float:
        if not accounts:
            profile_floor = float(profile.min_safe_balance) if profile else 5000.0
            return profile_floor
        checking = next(
            (acct for acct in accounts if acct.get("account_type") == "checking"),
            accounts[0],
        )
        available = checking.get("available_balance") or checking.get(
            "current_balance",
            0.0,
        )
        dynamic_floor = max(3000.0, available * 0.3)
        profile_floor = float(profile.min_safe_balance) if profile else 0.0
        return round(max(dynamic_floor, profile_floor), 2)

    def _target_savings_ratio(self, profile: UserProfile | None) -> float:
        if not profile:
            return 0.1
        return max(0.05, min(0.4, float(profile.savings_goal_pct or 0.1)))

    def _max_transfer_cap(self, profile: UserProfile | None) -> int:
        if profile and float(profile.monthly_salary or 0.0) > 0:
            return max(500, int(float(profile.monthly_salary) * 0.05))
        return 500

    def _estimate_goal_progress(
        self,
        profile: UserProfile | None,
        suggested_amount: float,
    ) -> float:
        if not profile:
            return 0.60

        monthly_salary = float(profile.monthly_salary or 0.0)
        savings_target_ratio = float(profile.savings_goal_pct or 0.0)
        monthly_target = monthly_salary * savings_target_ratio

        if monthly_target <= 0:
            return 0.60

        progress = suggested_amount / monthly_target
        return round(max(0.0, min(0.99, progress)), 2)
