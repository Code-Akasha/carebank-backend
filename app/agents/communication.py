from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from app.agents.base import AgentInput, AgentOutput, AgentStatus, BaseAgent
from app.services.health_score import compute_health_score
from app.services.nlg import generate_response
from app.services.nudge import can_send_nudge, record_nudge

logger = logging.getLogger(__name__)


class CommunicationAgent(BaseAgent):
    _ACTION_CONFIRMATIONS = {
        "yes",
        "y",
        "ok",
        "okay",
        "sure",
        "go ahead",
        "proceed",
        "continue",
        "confirm",
        "approve",
        "do it",
    }

    _ACTION_REJECTIONS = {
        "no",
        "n",
        "cancel",
        "stop",
        "reject",
        "don't",
        "do not",
    }

    @property
    def name(self) -> str:
        return "CommunicationAgent"

    @property
    def description(self) -> str:
        return (
            "Pure NLG engine that translates structured agent data into empathetic, "
            "persona-adapted natural language responses. Handles nudge fatigue control."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "natural_language_generation",
            "persona_adaptation",
            "nudge_management",
            "conversational_response",
            "multi_result_synthesis",
        ]

    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        user_id = agent_input.user_id
        ctx = agent_input.context

        # 1. Nudge Fatigue Check
        if ctx.is_nudge:
            allowed, reason = can_send_nudge(user_id)
            if not allowed:
                return AgentOutput(
                    response=f"[Nudge Blocked: {reason}]",
                    agent_name=self.name,
                    confidence=1.0,
                    metadata={"nudge": "blocked", "reason": reason},
                )

        # 2. Get Persona
        persona = ctx.persona
        if not persona:
            persona = self._get_persona(user_id)

        action_plan = self._plan_action_engine_action(
            requested_intent=agent_input.intent,
            user_message=agent_input.message,
            history=ctx.history,
            conversation_state=self._conversation_state_from_context(ctx),
            parsed_parameters=self._action_parameters_from_context(ctx),
        )
        if action_plan:
            if ctx.is_nudge:
                record_nudge(user_id)
            return AgentOutput(
                response=action_plan["response"],
                agent_name=self.name,
                confidence=float(action_plan.get("confidence", 0.93)),
                metadata={
                    "provider": "action_engine_planner",
                    "model": "deterministic",
                    "persona": persona,
                    "is_nudge": ctx.is_nudge,
                    "pending_state": action_plan.get("pending_state"),
                    "clear_pending": bool(action_plan.get("clear_pending", False)),
                    "action": action_plan.get("action"),
                    "ui_actions": action_plan.get("ui_actions")
                    if isinstance(action_plan.get("ui_actions"), list)
                    else [],
                },
            )

        planning_result = self._plan_schedule_action(
            requested_intent=agent_input.intent,
            user_message=agent_input.message,
            history=ctx.history,
            conversation_state=self._conversation_state_from_context(ctx),
            parsed_parameters=self._planning_parameters_from_context(ctx),
        )
        if planning_result:
            if ctx.is_nudge:
                record_nudge(user_id)
            return AgentOutput(
                response=planning_result["response"],
                agent_name=self.name,
                confidence=float(planning_result.get("confidence", 0.93)),
                metadata={
                    "provider": "planning_executor",
                    "model": "deterministic",
                    "persona": persona,
                    "is_nudge": ctx.is_nudge,
                    "pending_state": planning_result.get("pending_state"),
                    "clear_pending": bool(planning_result.get("clear_pending", False)),
                    "action": planning_result.get("action"),
                },
            )

        # 3. Format structured agent results for NLG (no json.dumps)
        agent_results = ctx.agent_results
        if agent_results:
            # Short-circuit to deterministic balance template when possible
            balance_response = self._maybe_render_balance_response(
                persona,
                agent_results,
                requested_intent=agent_input.intent,
                user_message=agent_input.message,
                task=ctx.task,
            )
            if balance_response:
                if ctx.is_nudge:
                    record_nudge(user_id)
                return AgentOutput(
                    response=balance_response,
                    agent_name=self.name,
                    confidence=0.95,
                    metadata={
                        "provider": "balance_template",
                        "model": "deterministic",
                        "persona": persona,
                        "is_nudge": ctx.is_nudge,
                    },
                )
            affordability_response = self._maybe_render_affordability_response(
                agent_results,
                requested_intent=agent_input.intent,
            )
            if affordability_response:
                if ctx.is_nudge:
                    record_nudge(user_id)
                return AgentOutput(
                    response=affordability_response,
                    agent_name=self.name,
                    confidence=0.95,
                    metadata={
                        "provider": "affordability_template",
                        "model": "deterministic",
                        "persona": persona,
                        "is_nudge": ctx.is_nudge,
                    },
                )
            advice_response = self._maybe_render_advice_response(
                agent_results,
                requested_intent=agent_input.intent,
            )
            if advice_response:
                if ctx.is_nudge:
                    record_nudge(user_id)
                return AgentOutput(
                    response=advice_response,
                    agent_name=self.name,
                    confidence=0.95,
                    metadata={
                        "provider": "advice_template",
                        "model": "deterministic",
                        "persona": persona,
                        "is_nudge": ctx.is_nudge,
                    },
                )
            health_response = self._maybe_render_health_response(
                agent_results,
                requested_intent=agent_input.intent,
            )
            if health_response:
                if ctx.is_nudge:
                    record_nudge(user_id)
                return AgentOutput(
                    response=health_response,
                    agent_name=self.name,
                    confidence=0.95,
                    metadata={
                        "provider": "health_template",
                        "model": "deterministic",
                        "persona": persona,
                        "is_nudge": ctx.is_nudge,
                    },
                )
        if agent_results and self._can_use_agent_results_for_intent(
            agent_results,
            agent_input.intent,
        ):
            data_context = agent_results
        else:
            data_context = ctx.data or f"User query: {agent_input.message}"

        task_description = (
            ctx.task or "Provide a helpful, personalized response summarizing the data."
        )

        # 4. Generate NLG Response
        nlg_result = generate_response(
            persona=persona,
            data_context=data_context,
            task_description=task_description,
        )

        # 5. Record nudge if sent successfully
        if ctx.is_nudge:
            record_nudge(user_id)

        return AgentOutput(
            response=nlg_result["text"],
            agent_name=self.name,
            confidence=0.9,
            metadata={
                "provider": nlg_result["provider"],
                "model": nlg_result.get("model"),
                "tokens": nlg_result.get("tokens"),
                "persona": nlg_result["persona"],
                "is_nudge": ctx.is_nudge,
            },
            tokens_used=nlg_result.get("tokens"),
        )

    def _get_persona(self, user_id: str) -> str:
        """Fetch user persona from health score computation."""
        try:
            health_data = compute_health_score(user_id)
            return health_data.get("persona", {}).get("persona", "Balanced Manager")
        except Exception as e:
            logger.warning("Could not fetch persona for %s: %s", user_id, e)
            return "Balanced Manager"

    def _maybe_render_balance_response(
        self,
        persona: str,
        agent_results: list[dict],
        *,
        requested_intent: str,
        user_message: str,
        task: str | None,
    ) -> str | None:
        if not self._is_balance_query(
            requested_intent=requested_intent,
            user_message=user_message,
            task=task,
        ):
            return None

        if self._has_non_balance_success(agent_results):
            return None

        for result in agent_results:
            metadata = result.get("metadata") or {}
            if metadata.get("intent_handled") != "balance":
                continue
            status = result.get("status")
            if status not in (AgentStatus.success, AgentStatus.needs_input):
                continue
            current = self._coerce_float(metadata.get("current_balance"))
            available = self._coerce_float(metadata.get("available_balance"))
            if current is None and available is None:
                continue
            if current is None:
                current = available
            if available is None:
                available = current
            symbol = self._resolve_currency_symbol(metadata.get("currency"))
            total_str = self._format_currency(available, symbol)
            current_str = self._format_currency(current, symbol)
            tone = self._persona_opening(persona)
            spend_line = f"You can comfortably spend around {total_str} without dipping into pending funds."
            return f"{tone}Total balance {total_str}. Current balance {current_str}. {spend_line}"
        return None

    def _maybe_render_affordability_response(
        self,
        agent_results: list[dict],
        *,
        requested_intent: str,
    ) -> str | None:
        if (requested_intent or "").strip().lower() != "affordability":
            return None

        for result in agent_results:
            metadata = result.get("metadata") or {}
            if (
                str(metadata.get("intent_handled") or "").strip().lower()
                != "affordability"
            ):
                continue
            status = result.get("status")
            if status not in (AgentStatus.success, AgentStatus.needs_input):
                continue

            purchase_amount = self._coerce_float(metadata.get("purchase_amount"))
            available_balance = self._coerce_float(metadata.get("available_balance"))
            post_purchase_balance = self._coerce_float(
                metadata.get("post_purchase_balance"),
            )
            verdict = str(metadata.get("verdict") or "").strip().lower()

            if purchase_amount is None or available_balance is None:
                continue

            amount_str = self._format_currency(purchase_amount, "₹")
            balance_str = self._format_currency(available_balance, "₹")
            if verdict == "affordable":
                remaining = self._format_currency(post_purchase_balance or 0.0, "₹")
                return (
                    f"Yes, you can afford a laptop for {amount_str}. "
                    f"You currently have {balance_str} available, and you'd still have about {remaining} left after the purchase."
                )
            if verdict == "tight_buffer":
                remaining = self._format_currency(post_purchase_balance or 0.0, "₹")
                return (
                    f"You can technically buy a laptop for {amount_str}, but it would leave you with a tight buffer. "
                    f"You have {balance_str} available, and you'd be down to about {remaining} afterward."
                )
            shortfall = self._format_currency(abs(post_purchase_balance or 0.0), "₹")
            return (
                f"I wouldn't recommend buying a laptop for {amount_str} right now. "
                f"You have {balance_str} available, so you'd fall short by about {shortfall} after the purchase."
            )
        return None

    def _maybe_render_advice_response(
        self,
        agent_results: list[dict],
        *,
        requested_intent: str,
    ) -> str | None:
        if (requested_intent or "").strip().lower() != "advice":
            return None

        for result in agent_results:
            metadata = result.get("metadata") or {}
            if str(metadata.get("intent_handled") or "").strip().lower() != "advice":
                continue
            status = result.get("status")
            if status not in (AgentStatus.success, AgentStatus.needs_input):
                continue

            top_spikes = metadata.get("top_spikes", [])
            total_savings = self._coerce_float(
                metadata.get("total_savings_opportunity"),
            )

            if not top_spikes:
                return "Your spending looks very stable compared to last month. Keep up the good work!"

            lines = ["Here are the areas where you spent noticeably more this month:"]
            for spike in top_spikes:
                cat = str(spike.get("category", "other")).capitalize()
                delta = self._format_currency(spike.get("delta", 0), "₹")
                pct = spike.get("pct_change", 0)
                lines.append(f"• **{cat}**: up {delta} (+{pct}%)")

            if total_savings and total_savings > 0:
                savings_str = self._format_currency(total_savings, "₹")
                lines.append(
                    f"\nIf you can reduce these spikes by just 30%, you could save an extra {savings_str} this month.",
                )

            top_cat = str(top_spikes[0].get("category", "other")).capitalize()
            lines.append(f"\nWant me to set a spending alert for {top_cat}?")

            return "\n".join(lines)
        return None

    def _maybe_render_health_response(
        self,
        agent_results: list[dict],
        *,
        requested_intent: str,
    ) -> str | None:
        if (requested_intent or "").strip().lower() != "health_score":
            return None

        for result in agent_results:
            metadata = result.get("metadata") or {}
            if (
                str(metadata.get("intent_handled") or "").strip().lower()
                != "health_score"
            ):
                continue
            score = self._coerce_float(metadata.get("score"))
            if score is None:
                continue
            return f"Health Score: {score:.1f}/100."

        return None

    def _maybe_render_schedule_guidance(
        self,
        *,
        requested_intent: str,
        user_message: str,
        history: list[dict] | None = None,
    ) -> str | None:
        if not self._is_schedule_query(requested_intent, user_message):
            return None

        day = self._extract_day_of_month(user_message)
        amount = self._extract_amount(user_message)

        # Continue multi-turn schedule capture (e.g. first turn has day, second has amount).
        if history:
            if day is None:
                day = self._extract_recent_schedule_day(history)
            if amount is None:
                amount = self._extract_recent_schedule_amount(history)

        if amount is None and day is not None:
            return (
                f"I understood you want to schedule rent on day {day} every month. "
                "Please share the rent amount as well (example: 25000), and I will guide the next step."
            )

        if day is None and amount is not None:
            return (
                f"I captured the rent amount as INR {amount:,.2f}. "
                "Please share the day of month (for example: 5th), and I will guide the next step."
            )

        if day is None and amount is None:
            return (
                "I can help with recurring rent scheduling. "
                "Please include both amount and day of month, for example: 'pay rent 25000 every month on 5th'."
            )

        return (
            f"I captured a recurring rent schedule of INR {amount:,.2f} on day {day} each month. "
            "Use Integration Lab > Planning or POST /api/planning/schedule-from-text to create it now."
        )

    @staticmethod
    def _conversation_state_from_context(ctx) -> dict[str, Any]:
        state = (
            ctx.model_extra.get("conversation_state")
            if hasattr(ctx, "model_extra")
            else None
        )
        if isinstance(state, dict):
            return state
        return {}

    @staticmethod
    def _planning_parameters_from_context(ctx) -> dict[str, Any]:
        extras = ctx.model_extra if hasattr(ctx, "model_extra") else {}
        params: dict[str, Any] = {}

        if ctx.amount is not None:
            params["amount"] = ctx.amount

        if isinstance(extras, dict):
            if "amount" in extras and params.get("amount") is None:
                params["amount"] = extras.get("amount")
            if "day_of_month" in extras:
                params["day_of_month"] = extras.get("day_of_month")
            if "source_text" in extras:
                params["source_text"] = extras.get("source_text")
        return params

    @staticmethod
    def _action_parameters_from_context(ctx) -> dict[str, Any]:
        extras = ctx.model_extra if hasattr(ctx, "model_extra") else {}
        params: dict[str, Any] = {}

        if ctx.amount is not None:
            params["amount"] = ctx.amount

        if isinstance(extras, dict):
            if "action_type" in extras:
                params["action_type"] = extras.get("action_type")
            if "action_payload" in extras:
                params["action_payload"] = extras.get("action_payload")
            if "action_command" in extras:
                params["action_command"] = extras.get("action_command")
            if "request_id" in extras:
                params["request_id"] = extras.get("request_id")
            if "execution_id" in extras:
                params["execution_id"] = extras.get("execution_id")
        return params

    def _plan_action_engine_action(
        self,
        *,
        requested_intent: str,
        user_message: str,
        history: list[dict],
        conversation_state: dict[str, Any],
        parsed_parameters: dict[str, Any],
    ) -> dict[str, Any] | None:
        pending_intent = str(conversation_state.get("pending_intent") or "").lower()
        bill_listing_query = self._is_bill_listing_query(user_message)
        if (
            requested_intent != "actions"
            and pending_intent != "actions"
            and not bill_listing_query
        ):
            return None

        if (
            pending_intent == "actions"
            and requested_intent != "actions"
            and not self._is_action_follow_up_message(user_message)
        ):
            return None

        pending = conversation_state.get("actions")
        if not isinstance(pending, dict):
            pending = {}

        flow = str(pending.get("flow") or "").strip().lower()
        direct_command = str(parsed_parameters.get("action_command") or "").strip()
        if direct_command:
            request_id = self._coerce_int(parsed_parameters.get("request_id"))
            execution_id = self._coerce_int(parsed_parameters.get("execution_id"))

            if direct_command == "approve_action_request" and request_id is not None:
                return {
                    "response": f"Understood. Approving action request ID {request_id} now.",
                    "confidence": 0.95,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": {
                        "type": "approve_action_request",
                        "request_id": request_id,
                    },
                    "ui_actions": [],
                }

            if direct_command == "reject_action_request" and request_id is not None:
                return {
                    "response": f"Okay. Cancelling action request ID {request_id}.",
                    "confidence": 0.95,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": {
                        "type": "reject_action_request",
                        "request_id": request_id,
                    },
                    "ui_actions": [],
                }

            if direct_command == "get_action_status" and (
                request_id is not None or execution_id is not None
            ):
                action: dict[str, Any] = {"type": "get_action_status"}
                if request_id is not None:
                    action["request_id"] = request_id
                if execution_id is not None:
                    action["execution_id"] = execution_id
                return {
                    "response": "Checking that action status now.",
                    "confidence": 0.94,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": action,
                    "ui_actions": [],
                }

            return {
                "response": "Please include the action request or execution ID.",
                "confidence": 0.9,
                "pending_state": None,
                "clear_pending": False,
                "action": None,
                "ui_actions": [],
            }

        if not flow and bill_listing_query:
            return {
                "response": "Let me check your pending bills.",
                "confidence": 0.93,
                "pending_state": None,
                "clear_pending": True,
                "action": {
                    "type": "discover_bills",
                    "action_type": "pay_bill",
                },
                "ui_actions": [],
            }

        if flow == "bill_picker":
            candidates = pending.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                return {
                    "response": "I lost the bill list. Please re-send what you want to pay.",
                    "confidence": 0.9,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": None,
                    "ui_actions": [],
                }

            normalized = re.sub(r"\s+", " ", user_message.lower()).strip()
            match = re.search(r"\b(\d{1,2})\b", normalized)
            if not match:
                return {
                    "response": "Please reply with the number (1, 2, ...).",
                    "confidence": 0.9,
                    "pending_state": None,
                    "clear_pending": False,
                    "action": None,
                    "ui_actions": [],
                }

            choice = int(match.group(1))
            if choice < 1 or choice > len(candidates):
                return {
                    "response": "That number doesn't match the list. Reply with 1, 2, ...",
                    "confidence": 0.9,
                    "pending_state": None,
                    "clear_pending": False,
                    "action": None,
                    "ui_actions": [],
                }

            candidate = candidates[choice - 1]
            if not isinstance(candidate, dict):
                return {
                    "response": "I couldn't read that selection. Please try again.",
                    "confidence": 0.9,
                    "pending_state": None,
                    "clear_pending": False,
                    "action": None,
                    "ui_actions": [],
                }

            title = str(candidate.get("title") or "Payment")
            due_date = str(candidate.get("due_date") or "").strip()
            amount = candidate.get("amount")
            amount_clause = ""
            try:
                if amount is not None:
                    amount_clause = f" for INR {float(amount):,.2f}"
            except (TypeError, ValueError):
                amount_clause = ""

            due_clause = f" due {due_date}" if due_date else ""
            return {
                "response": f"Got it: {title}{due_clause}{amount_clause}. What do you want to do?",
                "confidence": 0.94,
                "pending_state": {
                    "pending_intent": "actions",
                    "actions": {
                        "flow": "bill_suggestion",
                        "candidate": candidate,
                    },
                },
                "clear_pending": False,
                "action": None,
                "ui_actions": [
                    {"label": "Pay now", "message": "pay now"},
                    {"label": "Later", "message": "later"},
                ],
            }

        if flow == "bill_suggestion":
            candidate = pending.get("candidate")
            if not isinstance(candidate, dict):
                return {
                    "response": "I lost the bill context. Please re-send what you want to pay.",
                    "confidence": 0.9,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": None,
                    "ui_actions": [],
                }

            normalized = re.sub(r"\s+", " ", user_message.lower()).strip()
            _PAY_NOW_TRIGGERS = {
                "pay now",
                "pay",
                "yes",
                "y",
                "ok",
                "okay",
                "sure",
                "go ahead",
                "confirm",
                "proceed",
                "do it",
                "approve",
            }
            if normalized in _PAY_NOW_TRIGGERS:
                candidate_action_type = (
                    str(candidate.get("action_type") or "").strip().lower()
                )
                amount = candidate.get("amount")
                try:
                    amount_value = float(amount) if amount is not None else 0.0
                except (TypeError, ValueError):
                    amount_value = 0.0

                if not candidate_action_type or amount_value <= 0:
                    label = self._format_action_label(candidate_action_type)
                    return {
                        "response": f"Understood. How much should I {label}? Please share the amount.",
                        "confidence": 0.93,
                        "pending_state": {
                            "pending_intent": "actions",
                            "actions": {
                                "flow": "action_request",
                                "action_type": candidate_action_type,
                                "action_payload": {
                                    "amount": None,
                                    "description": "Payment requested via chat",
                                },
                            },
                        },
                        "clear_pending": False,
                        "action": None,
                        "ui_actions": [],
                    }

                title = str(candidate.get("title") or "Payment")
                due_date = str(candidate.get("due_date") or "").strip()
                source_type = str(candidate.get("source_type") or "").strip().lower()
                source_id = candidate.get("source_id")
                try:
                    source_id_int = int(source_id)
                except (TypeError, ValueError):
                    source_id_int = None

                idempotency_key = None
                if source_id_int is not None and source_type and due_date:
                    idempotency_key = f"bill:{source_type}:{source_id_int}:{due_date}:{candidate_action_type}"

                description = title
                if due_date:
                    description = f"{title} due {due_date}"

                action_payload: dict[str, Any] = {
                    "amount": amount_value,
                    "description": description,
                    "source_type": source_type,
                    "source_id": source_id_int,
                    "due_date": due_date or None,
                }
                category = candidate.get("category")
                if isinstance(category, str) and category.strip():
                    action_payload["category"] = category.strip()

                from app.core.config import get_settings

                settings = get_settings()

                label = self._format_action_label(candidate_action_type)

                if amount_value <= settings.auto_approve_limit:
                    return {
                        "response": f"Processing payment to {label} for ₹{amount_value:,.2f}…",
                        "confidence": 0.95,
                        "pending_state": None,
                        "clear_pending": True,
                        "action": {
                            "type": "execute_direct_payment",
                            "action_type": candidate_action_type,
                            "action_payload": action_payload,
                            "idempotency_key": idempotency_key,
                        },
                        "ui_actions": [],
                    }
                return {
                    "response": f"This payment of ₹{amount_value:,.2f} exceeds the instant-payment limit (₹{settings.auto_approve_limit:,.0f}). Creating an action request for approval...",
                    "confidence": 0.95,
                    "pending_state": {
                        "pending_intent": "actions",
                        "actions": {
                            "flow": "action_request",
                            "action_type": candidate_action_type,
                            "action_payload": action_payload,
                        },
                    },
                    "clear_pending": False,
                    "action": None,
                    "ui_actions": [],
                }

            if normalized in {"later", "not now", "snooze", "remind later"}:
                source_type = str(candidate.get("source_type") or "").strip().lower()
                source_id_raw = candidate.get("source_id")
                try:
                    source_id = int(source_id_raw)
                except (TypeError, ValueError):
                    source_id = None

                if not source_type or source_id is None:
                    return {
                        "response": "Okay. I'll remind you later.",
                        "confidence": 0.9,
                        "pending_state": None,
                        "clear_pending": True,
                        "action": None,
                        "ui_actions": [],
                    }

                return {
                    "response": "Okay. Snoozing that for later.",
                    "confidence": 0.94,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": {
                        "type": "snooze_bill",
                        "source_type": source_type,
                        "source_id": source_id,
                        "hours": 24,
                    },
                    "ui_actions": [],
                }

            return {
                "response": "Reply 'Pay now' or 'Later'.",
                "confidence": 0.9,
                "pending_state": None,
                "clear_pending": False,
                "action": None,
                "ui_actions": [
                    {"label": "Pay now", "message": "pay now"},
                    {"label": "Later", "message": "later"},
                ],
            }

        pending_request_id = pending.get("request_id")
        if pending_request_id is not None:
            decision = self._parse_action_decision(user_message)
            try:
                request_id = int(pending_request_id)
            except (TypeError, ValueError):
                request_id = None

            if request_id is None:
                return {
                    "response": (
                        "I had a pending action approval, but I lost the request reference. "
                        "Please re-send the action you want to perform."
                    ),
                    "confidence": 0.9,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": None,
                }

            if decision == "approve":
                return {
                    "response": "Understood. Approving and executing that now.",
                    "confidence": 0.94,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": {
                        "type": "approve_action_request",
                        "request_id": request_id,
                    },
                }

            if decision == "reject":
                return {
                    "response": "Okay. Cancelling that action request.",
                    "confidence": 0.94,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": {
                        "type": "reject_action_request",
                        "request_id": request_id,
                    },
                }

            return {
                "response": (
                    "You have a pending action approval. Reply 'yes' to approve or 'no' to cancel."
                ),
                "confidence": 0.9,
                "pending_state": None,
                "clear_pending": False,
                "action": None,
            }

        action_type = parsed_parameters.get("action_type") or pending.get("action_type")
        inferred = self._infer_action_type(user_message)
        if not action_type and inferred:
            action_type = inferred

        action_payload: dict[str, Any] = {}
        pending_payload = pending.get("action_payload")
        if isinstance(pending_payload, dict):
            action_payload.update(pending_payload)

        parsed_payload = parsed_parameters.get("action_payload")
        if isinstance(parsed_payload, dict):
            action_payload.update(parsed_payload)

        amount = self._coerce_amount(parsed_parameters.get("amount"))
        if amount is None:
            amount = self._coerce_amount(action_payload.get("amount"))
        if amount is None:
            amount = self._extract_amount(user_message)
        if amount is not None:
            action_payload["amount"] = amount

        if not action_type:
            return {
                "response": (
                    "What would you like me to do? For example: 'transfer 5000 to savings' "
                    "or 'pay rent 25000'."
                ),
                "confidence": 0.86,
                "pending_state": None,
                "clear_pending": False,
                "action": None,
            }

        normalized_type = str(action_type).strip().lower()
        label = self._format_action_label(normalized_type)

        if normalized_type == "record_note":
            if not action_payload.get("message"):
                action_payload["message"] = user_message.strip()
            return {
                "response": "Got it. Recording that note now.",
                "confidence": 0.95,
                "pending_state": None,
                "clear_pending": True,
                "action": {
                    "type": "create_action_request",
                    "action_type": normalized_type,
                    "action_payload": action_payload,
                    "expires_in_hours": 24,
                },
            }

        if action_payload.get("amount") is None:
            if normalized_type in {"pay_rent", "pay_bill", "pay_gas", "pay_utility"}:
                object_map = {
                    "pay_rent": "rent",
                    "pay_bill": "bill",
                    "pay_gas": "gas bill",
                    "pay_utility": "utility bill",
                }
                object_label = object_map.get(normalized_type, "bill")
                return {
                    "response": f"Okay. Let me check your pending or scheduled {object_label}.",
                    "confidence": 0.94,
                    "pending_state": None,
                    "clear_pending": True,
                    "action": {
                        "type": "discover_bills",
                        "action_type": normalized_type,
                    },
                    "ui_actions": [],
                }

            return {
                "response": (
                    f"Understood. How much should I {label}? Please share the amount."
                ),
                "confidence": 0.93,
                "pending_state": {
                    "pending_intent": "actions",
                    "actions": {
                        "flow": "action_request",
                        "action_type": normalized_type,
                        "action_payload": {
                            **action_payload,
                            "amount": None,
                        },
                    },
                },
                "clear_pending": False,
                "action": None,
                "ui_actions": [],
            }

        try:
            amount_value = float(action_payload.get("amount") or 0)
        except (TypeError, ValueError):
            amount_value = 0.0

        return {
            "response": (
                f"Got it. Creating an action request for approval to {label} for INR {amount_value:,.2f} now."
            ),
            "confidence": 0.95,
            "pending_state": None,
            "clear_pending": True,
            "action": {
                "type": "create_action_request",
                "action_type": normalized_type,
                "action_payload": action_payload,
                "expires_in_hours": 24,
                "idempotency_key": self._build_chat_idempotency_key(
                    normalized_type,
                    action_payload,
                    user_message,
                ),
            },
        }

    @classmethod
    def _parse_action_decision(cls, message: str) -> str | None:
        normalized = re.sub(r"\s+", " ", message.lower()).strip()
        if not normalized:
            return None
        if normalized in cls._ACTION_CONFIRMATIONS:
            return "approve"
        if normalized in cls._ACTION_REJECTIONS:
            return "reject"
        return None

    @classmethod
    def _is_action_follow_up_message(cls, user_message: str) -> bool:
        normalized = re.sub(r"\s+", " ", user_message.lower()).strip()
        if not normalized:
            return False

        if normalized in cls._ACTION_CONFIRMATIONS:
            return True
        if normalized in cls._ACTION_REJECTIONS:
            return True

        if re.fullmatch(
            r"(?:₹|rs\.?|inr)?\s*\d+(?:\.\d+)?\s*(?:k|thousand|lakh|lakhs|crore|crores|cr)?",
            normalized,
        ):
            return True

        if re.match(r"^(approve|reject|cancel)\b", normalized):
            return True

        return False

    @staticmethod
    def _infer_action_type(user_message: str) -> str | None:
        lowered = user_message.lower()
        if "transfer" in lowered and (
            "savings" in lowered or "to savings" in lowered or "save" in lowered
        ):
            return "transfer_savings"
        if "pay" in lowered and "rent" in lowered:
            return "pay_rent"
        if "pay" in lowered and ("gas" in lowered or "lpg" in lowered):
            return "pay_gas"
        if "pay" in lowered and (
            "utility" in lowered
            or "electric" in lowered
            or "electricity" in lowered
            or "water" in lowered
        ):
            return "pay_utility"
        if "pay" in lowered and "bill" in lowered:
            return "pay_bill"
        if "note" in lowered or "remember" in lowered or "record" in lowered:
            return "record_note"
        return None

    @staticmethod
    def _format_action_label(action_type: str) -> str:
        mapping = {
            "pay_rent": "pay rent",
            "pay_bill": "pay a bill",
            "pay_gas": "pay the gas bill",
            "pay_utility": "pay the utility bill",
            "transfer_savings": "transfer to savings",
            "record_note": "record a note",
        }
        normalized = (action_type or "").strip().lower()
        return mapping.get(normalized, normalized.replace("_", " "))

    @staticmethod
    def _is_bill_listing_query(user_message: str) -> bool:
        normalized = re.sub(r"\s+", " ", user_message.lower()).strip()
        if not normalized:
            return False

        bill_tokens = ("bill", "bills", "bil", "bils")
        if not any(token in normalized for token in bill_tokens):
            return False

        if re.search(r"\bpay\b", normalized) and re.search(r"\b\d", normalized):
            return False

        discovery_hints = (
            "pending",
            "due",
            "upcoming",
            "scheduled",
            "what are",
            "show",
            "list",
            "any",
        )
        return any(hint in normalized for hint in discovery_hints)

    def _plan_schedule_action(
        self,
        *,
        requested_intent: str,
        user_message: str,
        history: list[dict],
        conversation_state: dict[str, Any],
        parsed_parameters: dict[str, Any],
    ) -> dict[str, Any] | None:
        pending_intent = str(conversation_state.get("pending_intent") or "").lower()
        if requested_intent != "planning" and pending_intent != "planning":
            return None

        current_message_has_schedule_hints = self._is_schedule_query("", user_message)
        if (
            pending_intent == "planning"
            and requested_intent != "planning"
            and not self._is_schedule_follow_up_message(user_message)
        ):
            return None

        pending = conversation_state.get("planning")
        if not isinstance(pending, dict):
            pending = {}

        current_day = self._extract_day_of_month(user_message)
        current_amount = self._extract_amount(user_message)

        if current_day is None:
            current_day = self._coerce_day(parsed_parameters.get("day_of_month"))
        if current_amount is None:
            current_amount = self._coerce_amount(parsed_parameters.get("amount"))

        day = current_day
        if day is None:
            day = self._coerce_day(pending.get("day_of_month"))
        if day is None:
            day = self._extract_recent_schedule_day(history)

        amount = current_amount
        if amount is None:
            amount = self._coerce_amount(pending.get("amount"))
        if amount is None:
            amount = self._extract_recent_schedule_amount(history)

        source_text_candidate = parsed_parameters.get("source_text")
        if not source_text_candidate and current_message_has_schedule_hints:
            source_text_candidate = user_message

        source_text = str(
            source_text_candidate
            or pending.get("source_text")
            or self._find_recent_schedule_request_text(history)
            or user_message,
        ).strip()

        if amount is None:
            return {
                "response": (
                    "Understood. I will set this recurring payment schedule. "
                    "Please share the payment amount."
                ),
                "confidence": 0.93,
                "pending_state": {
                    "pending_intent": "planning",
                    "planning": {
                        "flow": "schedule_from_text",
                        "source_text": source_text,
                        "day_of_month": day,
                        "amount": None,
                        "autopay_enabled": True,
                        "requires_approval": True,
                    },
                },
                "clear_pending": False,
                "action": None,
            }

        if day is None:
            return {
                "response": (
                    f"Got the amount INR {amount:,.2f}. "
                    "Please share the day of month for this recurring payment."
                ),
                "confidence": 0.93,
                "pending_state": {
                    "pending_intent": "planning",
                    "planning": {
                        "flow": "schedule_from_text",
                        "source_text": source_text,
                        "day_of_month": None,
                        "amount": amount,
                        "autopay_enabled": True,
                        "requires_approval": True,
                    },
                },
                "clear_pending": False,
                "action": None,
            }

        schedule_text = source_text
        lower_schedule = schedule_text.lower()
        if (
            "every month" not in lower_schedule
            and "monthly" not in lower_schedule
            and "recurring" not in lower_schedule
        ):
            schedule_text = f"{schedule_text} every month"
        if self._extract_day_of_month(schedule_text) is None:
            schedule_text = f"{schedule_text} on {day}th"
        if self._extract_amount(schedule_text) is None:
            schedule_text = f"{schedule_text} of {amount:.2f}"
        if "remind" not in schedule_text.lower():
            schedule_text = f"{schedule_text} and remind me"

        return {
            "response": (
                f"Got it. Creating recurring payment schedule for INR {amount:,.2f} on day {day} now."
            ),
            "confidence": 0.95,
            "pending_state": None,
            "clear_pending": True,
            "action": {
                "type": "create_schedule_from_text",
                "text": schedule_text,
                "default_amount": amount,
                "autopay_enabled": True,
                "requires_approval": True,
            },
        }

    @staticmethod
    def _coerce_day(value: Any) -> int | None:
        try:
            day = int(value)
        except (TypeError, ValueError):
            return None
        if 1 <= day <= 31:
            return day
        return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return parsed

    @staticmethod
    def _build_chat_idempotency_key(
        action_type: str,
        action_payload: dict[str, Any],
        user_message: str,
    ) -> str:
        amount = action_payload.get("amount")
        description = str(action_payload.get("description") or "").strip().lower()
        source_type = str(action_payload.get("source_type") or "").strip().lower()
        source_id = str(action_payload.get("source_id") or "").strip().lower()
        raw = "|".join(
            [
                "chat",
                action_type,
                str(amount),
                description,
                source_type,
                source_id,
                re.sub(r"\s+", " ", user_message.lower()).strip(),
            ],
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"chat:{action_type}:{digest}"

    @staticmethod
    def _coerce_amount(value: Any) -> float | None:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        if amount <= 0:
            return None
        return amount

    @classmethod
    def _find_recent_schedule_request_text(cls, history: list[dict]) -> str | None:
        for msg in reversed(history[-10:]):
            if str(msg.get("role") or "").lower() != "user":
                continue
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            if cls._is_schedule_query("", content):
                return content
        return None

    @classmethod
    def _extract_recent_schedule_day(cls, history: list[dict]) -> int | None:
        for msg in reversed(history[-8:]):
            if str(msg.get("role") or "").lower() != "user":
                continue
            content = str(msg.get("content") or "")
            if not cls._is_schedule_query("", content):
                continue
            day = cls._extract_day_of_month(content)
            if day is not None:
                return day
        return None

    @classmethod
    def _extract_recent_schedule_amount(cls, history: list[dict]) -> float | None:
        for msg in reversed(history[-8:]):
            if str(msg.get("role") or "").lower() != "user":
                continue
            content = str(msg.get("content") or "")
            if not cls._is_schedule_query("", content):
                continue
            amount = cls._extract_amount(content)
            if amount is not None:
                return amount
        return None

    @staticmethod
    def _can_use_agent_results_for_intent(
        agent_results: list[dict],
        requested_intent: str,
    ) -> bool:
        normalized = (requested_intent or "").strip().lower()
        if normalized in {"", "general", "planning"}:
            return False

        result_intents = {
            str((result.get("metadata") or {}).get("intent_handled", ""))
            .strip()
            .lower()
            for result in agent_results
            if (result.get("metadata") or {}).get("intent_handled")
        }
        if not result_intents:
            return True
        return normalized in result_intents

    @staticmethod
    def _has_non_balance_success(agent_results: list[dict]) -> bool:
        for result in agent_results:
            status = result.get("status")
            if status not in (AgentStatus.success, AgentStatus.needs_input):
                continue
            metadata = result.get("metadata") or {}
            intent_handled = str(metadata.get("intent_handled") or "").strip().lower()
            if intent_handled and intent_handled != "balance":
                return True
        return False

    @staticmethod
    def _is_balance_query(
        *,
        requested_intent: str,
        user_message: str,
        task: str | None,
    ) -> bool:
        query_text = f"{user_message} {task or ''}".lower()
        balance_hints = (
            "balance",
            "current balance",
            "available balance",
            "account balance",
            "how much do i have",
            "how much money",
        )
        has_balance_hint = any(hint in query_text for hint in balance_hints)
        if has_balance_hint:
            return True

        # Avoid deterministic balance responses when intent was misclassified.
        return False

    @staticmethod
    def _is_schedule_query(requested_intent: str, user_message: str) -> bool:
        if (requested_intent or "").strip().lower() == "planning":
            return True
        lowered = user_message.lower()
        schedule_hints = (
            "schedule",
            "shedule",
            "recurring",
            "autopay",
            "pay rent",
            "every month",
            "monthly",
        )
        return any(hint in lowered for hint in schedule_hints)

    @staticmethod
    def _is_schedule_follow_up_message(user_message: str) -> bool:
        normalized = re.sub(r"\s+", " ", user_message.lower()).strip()
        if not normalized:
            return False

        if re.fullmatch(
            r"(?:₹|rs\.?|inr)?\s*\d+(?:\.\d+)?\s*(?:k|thousand|lakh|lakhs|crore|crores|cr)?",
            normalized,
        ):
            return True

        if re.fullmatch(r"(?:on\s+)?\d{1,2}(?:st|nd|rd|th)?", normalized):
            return True

        if CommunicationAgent._is_schedule_query("", normalized):
            return True

        confirmations = {
            "yes",
            "y",
            "ok",
            "okay",
            "sure",
            "go ahead",
            "proceed",
            "continue",
            "confirm",
            "do it",
        }
        return normalized in confirmations

    @staticmethod
    def _extract_day_of_month(text: str) -> int | None:
        lowered = text.lower()
        match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", lowered)
        if not match:
            match = re.search(r"\bon\s+(\d{1,2})\b", lowered)
        if not match:
            return None
        day = int(match.group(1))
        if 1 <= day <= 31:
            return day
        return None

    @staticmethod
    def _extract_amount(text: str) -> float | None:
        match = re.search(
            r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|crore|crores|cr)?\b",
            text.lower(),
        )
        if not match:
            return None
        amount = float(match.group(1))
        unit = (match.group(2) or "").lower()
        multipliers = {
            "k": 1_000,
            "thousand": 1_000,
            "lakh": 100_000,
            "lakhs": 100_000,
            "crore": 10_000_000,
            "crores": 10_000_000,
            "cr": 10_000_000,
        }
        if unit:
            amount *= multipliers.get(unit, 1)
        if amount <= 0:
            return None
        return amount

    @staticmethod
    def _coerce_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolve_currency_symbol(currency: str | None) -> str:
        if not currency:
            return "₹"
        upper = currency.upper()
        if upper == "INR":
            return "₹"
        if upper == "USD":
            return "$"
        if upper == "EUR":
            return "€"
        return currency

    @staticmethod
    def _format_currency(value: float, symbol: str) -> str:
        if value is None:
            return ""
        return f"{symbol} {value:,.2f}"

    @staticmethod
    def _persona_opening(persona: str) -> str:
        openings = {
            "Cautious Saver": "Let's keep things steady: ",
            "Social Spender": "Good news - ",
            "Impulse Buyer": "Quick heads-up: ",
        }
        return openings.get(persona, "Here's where you stand: ")
