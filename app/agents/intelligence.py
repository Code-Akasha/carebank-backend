from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.services.forecast import forecast_balance
from app.services.anomaly import detect_anomaly
from app.services.health_score import compute_health_score
from app.services.data import generate_mock_transactions
from app.core.finance import forecast_impact


class IntelligenceAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "IntelligenceAgent"

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        intent = agent_input.intent
        user_id = agent_input.user_id
        context = agent_input.context

        if intent == "health_score":
            return self._handle_health_score(user_id)

        if intent == "what_if":
            expense_amount = context.get("expense_amount", 5000.0)
            return self._handle_what_if(user_id, expense_amount)

        if intent == "anomaly_check":
            amount = context.get("amount", 0.0)
            return self._handle_anomaly(user_id, amount)

        # Default: return health score
        return self._handle_health_score(user_id)

    def _handle_health_score(self, user_id: str) -> AgentOutput:
        result = compute_health_score(user_id)
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

    def _handle_what_if(self, user_id: str, expense_amount: float) -> AgentOutput:
        transactions = generate_mock_transactions(user_id)

        # Current forecast
        current = forecast_balance(transactions)
        current_balance = current["predicted_balance"]

        # Simulated forecast (using Deterministic Core for impact)
        simulated_balance = forecast_impact(
            current_balance=current_balance,
            scheduled_expenses=0,
            simulated_expense=expense_amount,
        )

        impact = simulated_balance - current_balance
        retained_pct = (
            (simulated_balance / current_balance * 100) if current_balance > 0 else 0
        )

        if retained_pct > 70:
            risk_level = "low"
        elif retained_pct > 30:
            risk_level = "medium"
        else:
            risk_level = "high"

        response = (
            f"Current forecast: ₹{current_balance:,.0f} end-of-month. "
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
        transactions = generate_mock_transactions(user_id)
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
