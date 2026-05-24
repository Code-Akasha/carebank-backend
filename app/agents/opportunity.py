import logging
from typing import Any

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.services.banking_client import (
    BankingClientError,
    get_accounts_sync,
    get_products_sync,
    get_providers_sync,
    get_transactions_sync,
)
from app.services.data import generate_mock_transactions

logger = logging.getLogger(__name__)

ENTERTAINMENT_MERCHANTS = {"Netflix", "Spotify", "BookMyShow", "Hotstar", "SonyLiv"}


class OpportunityAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "OpportunityAgent"

    @property
    def description(self) -> str:
        return (
            "Identifies and recommends financial products and opportunities like loans, subscriptions, and offers. "
            "Evaluates user eligibility and provides personalized product recommendations."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "product_recommendations",
            "loan_eligibility",
            "subscription_analysis",
            "offer_evaluation",
            "eligibility_checks",
        ]

    def _detect_unused_subscriptions(
        self,
        transactions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Hardcoding unused pattern matching for testing purpose
        # In a real app we'd look for recurring payments without corresponding login data etc
        subs = []
        for txn in transactions:
            merchant = (txn.get("merchant") or "").title()
            if (
                txn["category"].lower() == "entertainment"
                and merchant in ENTERTAINMENT_MERCHANTS
            ):
                # simple mock logic: if we see an entertainment txn, flag as potential unused sub
                subs.append(txn)
        return subs

    @staticmethod
    def _conversation_state_from_context(ctx) -> dict:
        state = (
            ctx.model_extra.get("conversation_state")
            if hasattr(ctx, "model_extra")
            else None
        )
        if isinstance(state, dict):
            return state
        return {}

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        user_id = agent_input.user_id

        conversation_state = self._conversation_state_from_context(agent_input.context)
        opp_context = conversation_state.get("opportunity_context", {})

        if opp_context.get("is_comparing"):
            product_name = opp_context.get("product_name", "the recommended product")
            provider = opp_context.get("provider", "your bank")
            rate = opp_context.get("rate", 0)
            amount = opp_context.get("amount", 0)

            try:
                earnings = float(amount) * (float(rate) / 100.0)
            except ValueError:
                earnings = 0

            # Use LLM to dynamically handle the user's follow-up (questions, yes, no, etc.)
            from app.services.llm import get_llm_provider
            from langchain_core.prompts import PromptTemplate

            llm, _ = get_llm_provider(temperature=0.3)
            if llm:
                prompt = PromptTemplate.from_template(
                    "You are a helpful financial assistant for CareBank. "
                    "You recently suggested moving idle cash to a better product. "
                    "Context: {context}\n"
                    "User's reply: {message}\n"
                    "If the user is agreeing, confirm the breakdown (Amount: {amount}, Rate: {rate}%, Earnings: {earnings}/yr) and ask if they want to initiate the transfer. "
                    "If the user is rejecting, acknowledge it gracefully. "
                    "If the user is asking a question (e.g. risks, details), answer it based on the context. "
                    "Keep it concise (1-3 sentences)."
                )
                context_str = f"Product: {product_name}, Provider: {provider}, Rate: {rate}%, Idle Cash: {amount}, Est. Annual Earnings: {earnings}"
                try:
                    chain = prompt | llm
                    llm_response = chain.invoke(
                        {
                            "context": context_str,
                            "message": agent_input.message,
                            "amount": amount,
                            "rate": rate,
                            "earnings": earnings,
                        }
                    )
                    response = llm_response.content.strip()
                except Exception as e:
                    logger.warning("OpportunityAgent LLM follow-up failed: %s", e)
                    response = "I can help you proceed with that transfer, or we can explore other options. What would you prefer?"
            else:
                response = "I can help you proceed with that transfer, or we can explore other options. What would you prefer?"

            return AgentOutput(
                response=response,
                agent_name=self.name,
                confidence=1.0,
                metadata={"intent_handled": "opportunity", "clear_pending": True},
            )

        transactions = self._fetch_transactions(user_id)
        products = self._fetch_products()
        accounts = self._fetch_accounts(user_id)
        providers = self._fetch_providers()

        # Get Financial Health Score to tailor recommendations
        try:
            from app.agents.intelligence import IntelligenceAgent

            intel = IntelligenceAgent()
            health_output = intel._handle_health_score(user_id)
            score = health_output.metadata.get("score", 75)
        except Exception as exc:
            logger.warning("Failed to get health score for recommendations: %s", exc)
            score = 75

        subscriptions = self._detect_unused_subscriptions(transactions)

        pending_state = None
        if subscriptions:
            sub = subscriptions[0]
            amount = abs(sub["amount"])
            product = self._select_best_product(products, accounts, providers, score)
            response = (
                f"I spotted a recurring charge from {sub['merchant']} for ₹{amount:,.0f}/month. "
                "If you don't actively use it, redirecting that amount could accelerate your goals. "
            )
            if product:
                response += (
                    f"Since you're already connected with {product['provider_name']}, their {product['name']} is offering "
                    f"{product.get('interest_rate', 0)}% APR. Want me to tee up the details?"
                )
                pending_state = {
                    "pending_intent": "opportunity",
                    "opportunity_context": {
                        "is_comparing": True,
                        "product_name": product["name"],
                        "provider": product["provider_name"],
                        "rate": product.get("interest_rate", 0),
                        "amount": amount
                        * 12,  # Annualized savings if they cancel subscription
                    },
                }
            subs_flagged = 1
        else:
            target_account = self._pick_underutilized_account(accounts)
            product = self._select_best_product(products, accounts, providers, score)
            response = "Your recurring spend looks under control. "
            if target_account and product:
                response += (
                    f"If you move ₹{target_account['available_to_move']:,.0f} from {target_account['name']} "
                    f"into {product['name']} ({product['interest_rate']}% via {product['provider_name']}), "
                    "you could earn more on idle cash. Should I prepare the comparison?"
                )
                pending_state = {
                    "pending_intent": "opportunity",
                    "opportunity_context": {
                        "is_comparing": True,
                        "product_name": product["name"],
                        "provider": product["provider_name"],
                        "rate": product.get("interest_rate", 0),
                        "amount": target_account["available_to_move"],
                    },
                }
            else:
                response += "I can still scout for higher-yield products if you like."
            subs_flagged = 0

        metadata = {
            "products_found": 1,
            "subscriptions_flagged": subs_flagged,
            "intent_handled": "opportunity",
        }
        if pending_state:
            metadata["pending_state"] = pending_state

        return AgentOutput(
            response=response,
            agent_name=self.name,
            confidence=0.8,
            metadata=metadata,
        )

    def _fetch_transactions(self, user_id: str) -> list[dict[str, Any]]:
        try:
            return get_transactions_sync(user_id=user_id)
        except BankingClientError as exc:
            logger.warning(
                "OpportunityAgent fallback transactions for %s: %s",
                user_id,
                exc,
            )
            return generate_mock_transactions(user_id, days=30)

    def _fetch_products(self) -> list[dict[str, Any]]:
        try:
            return get_products_sync()
        except BankingClientError as exc:
            logger.warning("OpportunityAgent fallback products: %s", exc)
            return [
                {
                    "id": 101,
                    "name": "Premium Savings Account",
                    "interest_rate": 7.5,
                    "provider_id": "carebank_retail",
                },
            ]

    def _fetch_accounts(self, user_id: str) -> list[dict[str, Any]]:
        try:
            return get_accounts_sync(user_id)
        except BankingClientError as exc:
            logger.warning(
                "OpportunityAgent fallback accounts for %s: %s",
                user_id,
                exc,
            )
            return [
                {
                    "account_id": f"{user_id}-chk",
                    "user_id": user_id,
                    "provider_id": "carebank_retail",
                    "account_type": "checking",
                    "name": "Everyday Checking",
                    "current_balance": 25000.0,
                    "available_balance": 20000.0,
                    "status": "active",
                },
            ]

    def _fetch_providers(self) -> list[dict[str, Any]]:
        try:
            return get_providers_sync()
        except BankingClientError as exc:
            logger.warning("OpportunityAgent fallback providers: %s", exc)
            return [
                {
                    "id": "carebank_retail",
                    "name": "CareBank Retail",
                    "status": "online",
                },
            ]

    def _select_best_product(
        self,
        products: list[dict[str, Any]],
        accounts: list[dict[str, Any]],
        providers: list[dict[str, Any]],
        health_score: int,
    ) -> dict[str, Any] | None:
        if not products:
            return None
        provider_lookup = {
            provider.get("id", provider.get("provider_id", str(i))): provider
            for i, provider in enumerate(providers)
        }
        active_providers = {
            acct["provider_id"]
            for acct in accounts
            if provider_lookup.get(acct["provider_id"], {}).get("status")
            != "maintenance"
        }
        # Filter products based on health score tier
        if health_score >= 80:
            # Score 80-100 (Saver): Growth & high yield
            target_types = {"fixed_deposit", "sip", "mutual_fund", "high_yield_savings"}
        elif health_score >= 50:
            # Score 50-79 (Balanced): Safety & insurance
            target_types = {
                "insurance",
                "emergency_fund",
                "recurring_deposit",
                "fixed_deposit",
            }
        else:
            # Score 0-49 (Spender): Relief & restructuring
            target_types = {
                "overdraft",
                "debt_consolidation",
                "credit_card_bt",
                "personal_loan",
            }

        eligible_products = [
            p
            for p in products
            if p.get("type", "").lower() in target_types
            or p.get("category", "").lower() in target_types
        ]

        # Fallback to all products if no exact match for tier
        if not eligible_products:
            eligible_products = products

        ranked = sorted(
            eligible_products,
            key=lambda item: float(item.get("interest_rate", 0.0)),
            reverse=True,
        )
        for product in ranked:
            provider_id = product.get("provider_id")
            if (
                not provider_id
                or provider_id in active_providers
                or not active_providers
            ):
                provider = provider_lookup.get(provider_id, {})
                product = {
                    **product,
                    "provider_name": provider.get("name", provider_id or "CareBank"),
                }
                return product
        first = ranked[0]
        provider = provider_lookup.get(first.get("provider_id"), {})
        return {
            **first,
            "provider_name": provider.get("name", first.get("provider_id", "CareBank")),
        }

    def _pick_underutilized_account(
        self,
        accounts: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not accounts:
            return None
        savings_like = [
            acct
            for acct in accounts
            if acct.get("account_type") in {"savings", "checking"}
        ]
        target = max(
            savings_like or accounts,
            key=lambda acct: acct.get("available_balance", 0.0),
        )
        available = max(0.0, target.get("available_balance", 0.0) - 5000.0)
        return {
            **target,
            "available_to_move": available,
        }
