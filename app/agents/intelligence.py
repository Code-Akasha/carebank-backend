import logging
from dataclasses import dataclass

from app.agents.base import BaseAgent, AgentInput, AgentOutput, AgentStatus
from app.services.forecast import forecast_balance
from app.services.anomaly import detect_anomaly
from app.services.health_score import compute_health_score
from app.services.data import generate_mock_transactions
from app.core.finance import forecast_impact
from app.core.config_thresholds import get_risk_thresholds
from app.core.config import get_settings
from app.services.banking_client import (
    get_transactions_sync,
    get_balance_sync,
    BankingClientError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FinancialData:
    """Bundle for deduplicated fetch results."""

    transactions: list[dict]
    balance: float


class IntelligenceAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "IntelligenceAgent"

    @property
    def description(self) -> str:
        return (
            "Analyzes financial data to provide insights, forecasts, health scores, what-if scenarios, "
            "balance inquiries, and affordability checks. Returns structured data for NLG synthesis."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "financial_health_score",
            "balance_forecast",
            "what_if_simulation",
            "spending_analysis",
            "spending_advice",
            "anomaly_detection",
            "future_predictions",
            "balance_inquiry",
            "affordability_check",
        ]

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        intent = agent_input.intent
        user_id = agent_input.user_id
        ctx = agent_input.context

        if intent == "health_score":
            return self._handle_health_score(user_id)

        if intent == "forecast":
            return self._handle_forecast(user_id)

        if intent == "what_if":
            return self._handle_what_if(user_id, ctx)

        if intent == "anomaly_check":
            amount = ctx.amount or 0.0
            return self._handle_anomaly(user_id, amount)

        if intent == "balance":
            return self._handle_balance(user_id)

        if intent == "affordability":
            return self._handle_affordability(user_id, ctx)

        if intent == "advice":
            return self._handle_advice(user_id)

        # Default: return health score data
        return self._handle_health_score(user_id)

    # ------------------------------------------------------------------
    # Health Score — returns structured data only
    # ------------------------------------------------------------------
    def _handle_health_score(self, user_id: str) -> AgentOutput:
        fin = self._fetch_financial_data(user_id)
        result = compute_health_score(
            user_id,
            transactions=fin.transactions,
            current_balance=fin.balance,
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

        return AgentOutput(
            agent_name=self.name,
            confidence=0.85,
            metadata={
                "intent_handled": "health_score",
                "score": score,
                "persona": persona,
                "factors": factors,
                "top_factor": top_factor,
                "weak_factor": weak_factor,
            },
        )

    # ------------------------------------------------------------------
    # Forecast — returns structured data only
    # ------------------------------------------------------------------
    def _handle_forecast(self, user_id: str) -> AgentOutput:
        fin = self._fetch_financial_data(user_id)
        transactions = fin.transactions
        current_balance = fin.balance

        forecast_result = forecast_balance(transactions, periods=30)
        predicted_balance = forecast_result.get("predicted_balance", current_balance)
        lower_bound = forecast_result.get("lower_bound", predicted_balance * 0.9)
        upper_bound = forecast_result.get("upper_bound", predicted_balance * 1.1)

        return AgentOutput(
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

    # ------------------------------------------------------------------
    # What-If — enforces required parameters
    # ------------------------------------------------------------------
    def _handle_what_if(self, user_id: str, ctx) -> AgentOutput:
        expense_amount = ctx.expense_amount
        if expense_amount is None:
            return AgentOutput(
                agent_name=self.name,
                status=AgentStatus.needs_input,
                confidence=0.0,
                required_params=["expense_amount"],
                metadata={
                    "intent_handled": "what_if",
                    "error": "Missing expense_amount for simulation",
                },
            )

        expense_amount = float(expense_amount)
        fin = self._fetch_financial_data(user_id)

        # Current forecast
        current = forecast_balance(fin.transactions)
        predicted_balance = current.get("predicted_balance", fin.balance)

        # Simulated forecast
        simulated_balance = forecast_impact(
            current_balance=fin.balance,
            scheduled_expenses=0,
            simulated_expense=expense_amount,
        )

        impact = simulated_balance - predicted_balance
        retained_pct = (
            (simulated_balance / predicted_balance * 100)
            if predicted_balance > 0
            else 0
        )

        thresholds = get_risk_thresholds()
        if retained_pct > thresholds.what_if_low:
            risk_level = "low"
        elif retained_pct > thresholds.what_if_medium:
            risk_level = "medium"
        else:
            risk_level = "high"

        return AgentOutput(
            agent_name=self.name,
            confidence=0.82,
            metadata={
                "intent_handled": "what_if",
                "expense_amount": expense_amount,
                "current_balance": fin.balance,
                "predicted_balance": predicted_balance,
                "simulated_balance": simulated_balance,
                "impact": impact,
                "risk_level": risk_level,
                "retained_pct": round(retained_pct, 1),
            },
        )

    # ------------------------------------------------------------------
    # Anomaly — returns structured data only
    # ------------------------------------------------------------------
    def _handle_anomaly(self, user_id: str, amount: float) -> AgentOutput:
        transactions = self._fetch_transactions(user_id)
        history = [abs(t["amount"]) for t in transactions if t["amount"] < 0]

        result = detect_anomaly(abs(amount), history)

        return AgentOutput(
            agent_name=self.name,
            confidence=0.9,
            metadata={
                "intent_handled": "anomaly_check",
                "amount": abs(amount),
                **result,
            },
        )

    # ------------------------------------------------------------------
    # Balance — moved from CommunicationAgent
    # ------------------------------------------------------------------
    def _handle_balance(self, user_id: str) -> AgentOutput:
        try:
            balance = get_balance_sync(user_id)
        except BankingClientError as exc:
            if _is_production_env():
                logger.warning("Could not fetch balance for %s: %s", user_id, exc)
                return AgentOutput(
                    agent_name=self.name,
                    status=AgentStatus.error,
                    confidence=0.3,
                    metadata={
                        "intent_handled": "balance",
                        "error": f"Could not fetch live balance: {exc}",
                    },
                )
            logger.warning(
                "Falling back to default balance data for %s: %s", user_id, exc
            )
            balance = {
                "current_balance": 25000.0,
                "available_balance": 24000.0,
            }

        current_balance = float(balance.get("current_balance", 0.0))
        available_balance = float(balance.get("available_balance", current_balance))
        return AgentOutput(
            agent_name=self.name,
            confidence=0.98,
            metadata={
                "intent_handled": "balance",
                "current_balance": current_balance,
                "available_balance": available_balance,
            },
        )

    # ------------------------------------------------------------------
    # Affordability — moved from CommunicationAgent
    # ------------------------------------------------------------------
    def _handle_affordability(self, user_id: str, ctx) -> AgentOutput:
        purchase_amount = ctx.purchase_amount
        if purchase_amount is None:
            return AgentOutput(
                agent_name=self.name,
                status=AgentStatus.needs_input,
                confidence=0.0,
                required_params=["purchase_amount"],
                metadata={
                    "intent_handled": "affordability",
                    "error": "Missing purchase_amount for affordability check",
                },
            )

        purchase_amount = float(purchase_amount)
        try:
            balance = get_balance_sync(user_id)
        except BankingClientError as exc:
            if _is_production_env():
                logger.warning(
                    "Could not fetch affordability data for %s: %s", user_id, exc
                )
                return AgentOutput(
                    agent_name=self.name,
                    status=AgentStatus.error,
                    confidence=0.3,
                    metadata={
                        "intent_handled": "affordability",
                        "purchase_amount": purchase_amount,
                        "error": f"Could not fetch live balance: {exc}",
                    },
                )
            logger.warning(
                "Falling back to default affordability data for %s: %s", user_id, exc
            )
            balance = {"available_balance": 25000.0}

        available_balance = float(balance.get("available_balance", 0.0))
        post_purchase_balance = available_balance - purchase_amount

        thresholds = get_risk_thresholds()
        if post_purchase_balance >= thresholds.affordability_safe_buffer:
            verdict = "affordable"
        elif post_purchase_balance >= 0:
            verdict = "tight_buffer"
        else:
            verdict = "not_recommended"

        return AgentOutput(
            agent_name=self.name,
            confidence=0.97,
            metadata={
                "intent_handled": "affordability",
                "purchase_amount": purchase_amount,
                "available_balance": available_balance,
                "post_purchase_balance": post_purchase_balance,
                "verdict": verdict,
            },
        )

    # ------------------------------------------------------------------
    # Spending Advice — current vs previous month category analysis
    # ------------------------------------------------------------------
    def _handle_advice(self, user_id: str) -> AgentOutput:
        """Identify top spending spikes vs last month and quantify savings opportunity."""
        transactions = self._fetch_transactions(user_id)

        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        curr_month = now.strftime("%Y-%m")
        prev_month_dt = now.replace(day=1) - timedelta(days=1)
        prev_month = prev_month_dt.strftime("%Y-%m")

        monthly_spending: dict[str, dict[str, float]] = {}
        for txn in transactions:
            if txn["amount"] >= 0:
                continue
            date_val = txn.get("date")
            if isinstance(date_val, str):
                try:
                    date_val = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                except ValueError:
                    continue
            elif not hasattr(date_val, "strftime"):
                continue
            month_key = date_val.strftime("%Y-%m")
            cat = txn.get("category", "other")
            monthly_spending.setdefault(month_key, {}).setdefault(cat, 0.0)
            monthly_spending[month_key][cat] += abs(txn["amount"])

        curr_cats = monthly_spending.get(curr_month, {})
        prev_cats = monthly_spending.get(prev_month, {})

        spikes: list[dict] = []
        for cat, curr_amt in sorted(curr_cats.items(), key=lambda x: -x[1]):
            prev_amt = prev_cats.get(cat, 0.0)
            delta = curr_amt - prev_amt
            pct_change = (delta / prev_amt * 100) if prev_amt > 0 else 100.0
            spikes.append(
                {
                    "category": cat,
                    "current_month_spend": round(curr_amt, 2),
                    "previous_month_spend": round(prev_amt, 2),
                    "delta": round(delta, 2),
                    "pct_change": round(pct_change, 1),
                    "savings_if_cut_30pct": round(curr_amt * 0.30, 2),
                }
            )

        # Sort by delta descending — biggest increases first
        spikes.sort(key=lambda x: -x["delta"])
        top_spikes = spikes[:3]

        total_savings_opportunity = sum(s["savings_if_cut_30pct"] for s in top_spikes)

        return AgentOutput(
            agent_name=self.name,
            confidence=0.88,
            metadata={
                "intent_handled": "advice",
                "current_month": curr_month,
                "previous_month": prev_month,
                "top_spikes": top_spikes,
                "total_savings_opportunity": round(total_savings_opportunity, 2),
            },
        )

    # ------------------------------------------------------------------
    # Data fetching helpers
    # ------------------------------------------------------------------
    def _fetch_financial_data(self, user_id: str) -> _FinancialData:
        """Fetch transactions and balance once, avoiding duplicate API calls."""
        return _FinancialData(
            transactions=self._fetch_transactions(user_id),
            balance=self._fetch_balance(user_id),
        )

    def _fetch_transactions(self, user_id: str) -> list[dict]:
        try:
            return get_transactions_sync(user_id=user_id)
        except BankingClientError as exc:
            if _is_production_env():
                logger.error(
                    "Transaction fetch failed in production for %s: %s", user_id, exc
                )
                raise
            logger.warning(
                "Falling back to generated transactions for %s: %s", user_id, exc
            )
            return generate_mock_transactions(user_id)

    def _fetch_balance(self, user_id: str) -> float:
        try:
            balance = get_balance_sync(user_id)
            return float(balance.get("current_balance", 25000.0))
        except BankingClientError as exc:
            if _is_production_env():
                logger.error(
                    "Balance fetch failed in production for %s: %s", user_id, exc
                )
                raise
            logger.warning("Falling back to default balance for %s: %s", user_id, exc)
            return 25000.0


def _is_production_env() -> bool:
    settings = get_settings()
    return settings.environment.lower() == "production"
