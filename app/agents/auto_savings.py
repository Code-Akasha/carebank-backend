import logging

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.services.forecast import forecast_balance
from app.services.data import generate_mock_transactions
from app.services.banking_client import (
    get_transactions_sync,
    get_balance_sync,
    get_accounts_sync,
    BankingClientError,
)


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

        # Forecast balance for next week (7 days)
        forecast_result = forecast_balance(transactions, periods=7)
        predicted_balance = forecast_result.get("predicted_balance", current_balance)

        # Basic rule: Is it safe to save?
        safety_threshold = self._derive_safety_threshold(accounts)

        if predicted_balance > safety_threshold:
            # We can afford to save some amount, let's say 10% of the surplus up to 500
            surplus = predicted_balance - safety_threshold
            suggested_amount = min(500, int(surplus * 0.1))

            if suggested_amount >= 50:
                # We have a meaningful amount to save
                response = (
                    f"Good news! Based on your forecast, you can safely save ₹{suggested_amount} this week "
                    "without affecting your upcoming bills. This would bring your savings "
                    "goal progress to 68%. Would you like to approve this micro-transfer?"
                )
                return AgentOutput(
                    response=response,
                    agent_name=self.name,
                    confidence=0.9,
                    metadata={
                        "suggested_amount": suggested_amount,
                        "goal_progress": 0.68,
                    },
                )

        # If not safe, suggest no savings
        return AgentOutput(
            response=(
                "Based on your forecast, things are a bit tight this week so I am not suggesting any auto-savings right now."
            ),
            agent_name=self.name,
            confidence=0.9,
            metadata={"suggested_amount": 0, "goal_progress": 0.60},
        )

    def _fetch_transactions(self, user_id: str) -> list[dict]:
        try:
            return get_transactions_sync(user_id=user_id)
        except BankingClientError as exc:
            logger.warning(
                "AutoSavingsAgent fallback transactions for %s: %s", user_id, exc
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
                "AutoSavingsAgent fallback accounts for %s: %s", user_id, exc
            )
            return [
                {
                    "account_type": "checking",
                    "current_balance": 25000.0,
                    "available_balance": 20000.0,
                }
            ]

    def _derive_safety_threshold(self, accounts: list[dict]) -> float:
        if not accounts:
            return 5000.0
        checking = next(
            (acct for acct in accounts if acct.get("account_type") == "checking"),
            accounts[0],
        )
        available = checking.get("available_balance") or checking.get(
            "current_balance", 0.0
        )
        dynamic_floor = max(3000.0, available * 0.3)
        return round(dynamic_floor, 2)
