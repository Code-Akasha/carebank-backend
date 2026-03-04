import logging

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.services.forecast import forecast_balance
from app.services.anomaly import detect_anomaly
from app.services.health_score import compute_health_score
from app.services.data import generate_mock_transactions
from app.core.finance import forecast_impact
from app.services.banking_client import (
    get_transactions_sync,
    get_balance_sync,
    BankingClientError,
)

logger = logging.getLogger(__name__)


class IntelligenceAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "IntelligenceAgent"

    @property
    def description(self) -> str:
        return (
            "Analyzes financial data to provide insights, forecasts, health scores, and what-if scenarios. "
            "Uses transaction history and balance data to predict future financial states and assess financial wellness."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "financial_health_score",
            "balance_forecast",
            "what_if_simulation",
            "spending_analysis",
            "anomaly_detection",
            "future_predictions",
        ]

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        intent = agent_input.intent
        user_id = agent_input.user_id
        context = agent_input.context

        if intent == "health_score":
            return self._handle_health_score(user_id)

        if intent == "forecast":
            return self._handle_forecast(user_id)

        if intent == "what_if":
            expense_amount = context.get("expense_amount", 5000.0)
            return self._handle_what_if(user_id, expense_amount)

        if intent == "anomaly_check":
            amount = context.get("amount", 0.0)
            return self._handle_anomaly(user_id, amount)

        # Default: return health score
        return self._handle_health_score(user_id)

    def _handle_health_score(self, user_id: str) -> AgentOutput:
        transactions = self._fetch_transactions(user_id)
        current_balance = self._fetch_balance(user_id)
        result = compute_health_score(
            user_id,
            transactions=transactions,
            current_balance=current_balance,
        )
        score = result["score"]
        persona = result.get("persona", {}).get("persona", "Balanced Manager")
        factors = result.get("factors", {})

        top_factor = (
            max(factors.items(), key=lambda x: x[1]["score"])[0]
            if factors
            else "savings"
        )
        weak_factor = (
            min(factors.items(), key=lambda x: x[1]["score"])[0]
            if factors
            else "liquidity"
        )

        response = (
            f"Your Financial Health Score is {score}/100. "
            f"Strongest area: {top_factor} ({factors.get(top_factor, {}).get('label', 'Good')}). "
            f"Area to improve: {weak_factor} ({factors.get(weak_factor, {}).get('label', 'Needs Work')}). "
            f'Your spending persona is "{persona}".'
        )

        return AgentOutput(
            response=response,
            agent_name=self.name,
            confidence=0.85,
            metadata={
                "intent_handled": "health_score",
                "score": score,
                "persona": persona,
                "factors": factors,
            },
        )

    def _handle_forecast(self, user_id: str) -> AgentOutput:
        """Handle balance forecast queries."""
        transactions = self._fetch_transactions(user_id)
        current_balance = self._fetch_balance(user_id)

        forecast_result = forecast_balance(transactions, periods=30)
        predicted_balance = forecast_result.get("predicted_balance", current_balance)
        lower_bound = forecast_result.get("lower_bound", predicted_balance * 0.9)
        upper_bound = forecast_result.get("upper_bound", predicted_balance * 1.1)

        response = (
            f"Based on your current spending patterns and income, your forecasted balance at the end of the month is "
            f"₹{predicted_balance:,.0f} (range: ₹{lower_bound:,.0f} - ₹{upper_bound:,.0f}). "
            f"Your current balance is ₹{current_balance:,.0f}."
        )

        return AgentOutput(
            response=response,
            agent_name=self.name,
            confidence=0.82,
            metadata={
                "intent_handled": "forecast",
                "current_balance": current_balance,
                "predicted_balance": predicted_balance,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
            },
        )

    def _handle_what_if(self, user_id: str, expense_amount: float) -> AgentOutput:
        transactions = self._fetch_transactions(user_id)
        current_balance = self._fetch_balance(user_id)

        # Current forecast
        current = forecast_balance(transactions)
        predicted_balance = current.get("predicted_balance", current_balance)

        # Simulated forecast (using Deterministic Core for impact)
        simulated_balance = forecast_impact(
            current_balance=current_balance,
            scheduled_expenses=0,
            simulated_expense=expense_amount,
        )

        impact = simulated_balance - predicted_balance
        retained_pct = (
            (simulated_balance / predicted_balance * 100)
            if predicted_balance > 0
            else 0
        )

        if retained_pct > 70:
            risk_level = "low"
        elif retained_pct > 30:
            risk_level = "medium"
        else:
            risk_level = "high"

        response = (
            f"Current forecast: ₹{predicted_balance:,.0f} end-of-month. "
            f"After this expense: ₹{simulated_balance:,.0f} (impact: ₹{impact:,.0f}). "
            f"Risk level: {risk_level}."
        )

        return AgentOutput(
            response=response,
            agent_name=self.name,
            confidence=0.82,
            metadata={
                "intent_handled": "what_if",
                "current_forecast": current_balance,
                "simulated_forecast": simulated_balance,
                "impact": impact,
                "risk_level": risk_level,
            },
        )

    def _handle_anomaly(self, user_id: str, amount: float) -> AgentOutput:
        transactions = self._fetch_transactions(user_id)
        history = [abs(t["amount"]) for t in transactions if t["amount"] < 0]

        result = detect_anomaly(abs(amount), history)

        if result["is_anomaly"]:
            response = (
                f"⚠️ This transaction of ₹{abs(amount):,.0f} is unusual. "
                f"Severity: {result['severity']}. "
                "It's significantly different from your typical spending pattern."
            )
        else:
            response = f"This transaction of ₹{abs(amount):,.0f} looks normal based on your spending history."

        return AgentOutput(
            response=response,
            agent_name=self.name,
            confidence=0.9,
            metadata={"intent_handled": "anomaly_check", **result},
        )

    def _fetch_transactions(self, user_id: str) -> list[dict]:
        try:
            return get_transactions_sync(user_id=user_id)
        except BankingClientError as exc:
            logger.warning(
                "Falling back to generated transactions for %s: %s", user_id, exc
            )
            return generate_mock_transactions(user_id)

    def _fetch_balance(self, user_id: str) -> float:
        try:
            balance = get_balance_sync(user_id)
            return float(balance.get("current_balance", 25000.0))
        except BankingClientError as exc:
            logger.warning("Falling back to default balance for %s: %s", user_id, exc)
            return 25000.0
