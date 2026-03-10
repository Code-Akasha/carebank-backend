# PLAN: Agent Architecture Refactor

**Goal:** Transform the three core agents (Coordinator, Intelligence, Communication) from a linear router + text-formatting pattern into a true agentic architecture with structured outputs, multi-intent chaining, clean separation of concerns, and a pure NLG communication layer.

---

## User Review Required

> [!IMPORTANT]
> **Breaking Changes to `AgentOutput`**: The `response` field on `AgentOutput` will become optional/empty for non-Communication agents. All data will move to `metadata`. Existing test assertions like `assert "Health Score" in output.response` will break and need updating.

> [!IMPORTANT]
> **Chat API contract is preserved**: `ChatResponse` shape stays identical (`response`, `intent`, `agent_used`). Frontend is unaffected.

> [!WARNING]
> **LLM dependency for entity extraction**: The new Coordinator uses `.with_structured_output()` for intent classification + entity extraction. If no LLM is available, it falls back to keyword matching (existing behavior) but **without** entity extraction. This means `what_if` without an LLM will still use a hardcoded fallback amount. Is this acceptable for your demo, or should we add regex-based entity extraction in the keyword fallback path too?

---

## Proposed Changes

### Phase 1 — Upgrade Base Contracts

#### [MODIFY] [base.py](file:///d:/PycharmProjects/carebank-backend/app/agents/base.py)

- Add `status` field to `AgentOutput` (enum: `success`, `error`, `needs_input`)
- Make `response` field optional (default empty string — kept for backward compat)
- Add `required_params` field to `AgentOutput` for agents to signal missing data

```diff
 class AgentOutput(BaseModel):
-    response: str
+    response: str = ""
     agent_name: str
     confidence: float = 1.0
     metadata: dict = Field(default_factory=dict)
+    status: str = "success"  # "success" | "error" | "needs_input"
+    required_params: list[str] = Field(default_factory=list)
```

---

### Phase 2 — Refactor Coordinator Agent

#### [MODIFY] [coordinator.py](file:///d:/PycharmProjects/carebank-backend/app/agents/coordinator.py)

**2a. Structured LLM Output (replace text parsing):**

- Define `ClassificationResult` Pydantic model with `intent`, `agent_name`, `confidence`, and `parameters` dict
- Replace `_classify_intent_with_llm` to use `llm.with_structured_output(ClassificationResult)`
- Delete `_parse_llm_classification()` entirely
- Keep `_classify_intent_keywords()` as fallback (no LLM available)

```python
class ClassificationResult(BaseModel):
    """Structured output from LLM intent classification."""
    intent: str = Field(description="One of: balance, forecast, health_score, what_if, auto_savings, opportunity, general")
    agent_name: str = Field(description="Exact agent name to route to")
    confidence: float = Field(description="0.0 to 1.0 confidence score")
    parameters: dict = Field(default_factory=dict, description="Extracted entities like expense_amount, category, date")
```

**2b. Multi-Intent Support (Plan-and-Execute):**

- Add `tasks` list to `CoordinatorState` for decomposed sub-intents
- Add `agent_results` list to collect structured results from multiple agents
- Modify the graph to support cyclic flow:
  - `classify` → `plan_tasks` → `execute_task` → `check_remaining` → (loop or `synthesize`)
  - `synthesize` → `validate` → `respond`
- `check_remaining` is a conditional edge: if more tasks remain → `execute_task`, else → `synthesize`

**2c. Pass Extracted Parameters to Agents:**

- The `parameters` dict from `ClassificationResult` gets merged into `AgentInput.context`
- Example: "What if I buy a 50k TV?" → `context={"expense_amount": 50000.0}`

**2d. Handle `needs_input` from agents:**

- If an agent returns `status="needs_input"`, the coordinator generates a follow-up question instead of routing to validation
- For MVP, this short-circuits to a friendly message asking for the missing info

---

### Phase 3 — Refactor Intelligence Agent

#### [MODIFY] [intelligence.py](file:///d:/PycharmProjects/carebank-backend/app/agents/intelligence.py)

**3a. Return Data, Not Text:**

Strip all `f"..."` response strings. Return structured data in `metadata` only. Set `response` to empty.

```diff
 # _handle_health_score
-response = (
-    f"Your Financial Health Score is {score}/100. "
-    f"Strongest area: {top_factor} ..."
-)
 return AgentOutput(
-    response=response,
+    response="",
     agent_name=self.name,
     confidence=0.85,
     metadata={
         "intent_handled": "health_score",
         "score": score,
         "persona": persona,
         "factors": factors,
+        "top_factor": top_factor,
+        "weak_factor": weak_factor,
     },
 )
```

Same pattern for `_handle_forecast`, `_handle_what_if`, `_handle_anomaly`.

**3b. Enforce Required Parameters:**

For `what_if` intent: if `expense_amount` is missing from context, return `status="needs_input"`.

```python
def _handle_what_if(self, user_id, context):
    expense_amount = context.get("expense_amount")
    if expense_amount is None:
        return AgentOutput(
            agent_name=self.name,
            status="needs_input",
            required_params=["expense_amount"],
            metadata={"intent_handled": "what_if", "error": "Missing expense_amount"},
        )
```

**3c. Add Balance + Affordability Handlers (from Communication Agent):**

- Add `_handle_balance(user_id)` — returns balance data as structured JSON
- Add `_handle_affordability(user_id, amount)` — returns verdict + numbers as structured JSON
- These were previously in `CommunicationAgent` doing math in the presentation layer

---

### Phase 4 — Refactor Communication Agent

#### [MODIFY] [communication.py](file:///d:/PycharmProjects/carebank-backend/app/agents/communication.py)

**4a. Move Balance + Affordability Logic Out:**

- Delete `_handle_balance_question`, `_handle_affordability_question`, `_handle_purchase_question_without_amount`
- Delete `_is_balance_question`, `_is_purchase_question` (intent detection lives in Coordinator)
- Delete `_extract_purchase_amount` (entity extraction lives in Coordinator LLM)
- Remove imports: `re`, `get_balance_sync`, `compute_health_score`

**4b. Pure NLG Engine:**

The entire `_invoke` becomes:
1. Check nudge fatigue (stays — it's a communication concern)
2. Get user persona (from `context` or computed)
3. Format `agent_results` (structured JSON from other agents) for NLG
4. Call `generate_response()` with persona + data
5. Return NLG output

```python
def _invoke(self, agent_input: AgentInput) -> AgentOutput:
    user_id = agent_input.user_id
    context = agent_input.context

    # Nudge check
    if context.get("is_nudge"):
        allowed, reason = can_send_nudge(user_id)
        if not allowed:
            return AgentOutput(response=f"[Nudge Blocked: {reason}]", ...)

    persona = context.get("persona", "Balanced Manager")
    agent_results = context.get("agent_results", [])
    data_context = json.dumps(agent_results, default=str)
    task_description = context.get("task", "Summarize the financial data for the user in a helpful way.")

    nlg_result = generate_response(persona, data_context, task_description)
    return AgentOutput(response=nlg_result["text"], ...)
```

---

### Phase 5 — Update NLG Service

#### [MODIFY] [nlg.py](file:///d:/PycharmProjects/carebank-backend/app/services/nlg.py)

- Update `BASE_PROMPT` to handle structured JSON input
- Add persona as a prompt variable
- Update template fallback to handle JSON `data_context` gracefully

```diff
 BASE_PROMPT = """You are a helpful financial assistant for CareBank.
+
+You will receive structured data from analysis agents as JSON.
+Translate this data into a clear, empathetic, persona-adapted response.
 
 IMPORTANT RULES:
 1. NEVER make up or hallucinate specific financial numbers
-2. If you don't have specific data, say so clearly
-3. Keep responses concise (maximum 3 sentences)
+2. ONLY use numbers that appear in the provided data context
+3. Keep responses concise (2-3 sentences max)
 4. Do NOT add financial disclaimers (the system adds them automatically)
+5. Match the tone to the user's persona: {persona}
 
-Context: {data_context}
+Data (JSON): {data_context}
 Task: {task_description}
```

---

### Phase 6 — Update Tests

#### [MODIFY] [test_coordinator.py](file:///d:/PycharmProjects/carebank-backend/tests/test_coordinator.py)

- Update assertions to match new structured output flow
- Add tests for multi-intent queries
- Add test for `needs_input` handling

#### [MODIFY] [test_intelligence.py](file:///d:/PycharmProjects/carebank-backend/tests/test_intelligence.py)

- Assert on `metadata` fields instead of `response` text
- Add `test_what_if_missing_amount_returns_needs_input`
- Add `test_balance_intent` and `test_affordability_intent`

#### [MODIFY] [test_communication.py](file:///d:/PycharmProjects/carebank-backend/tests/test_communication.py)

- Remove deleted function tests (`_extract_purchase_amount`, purchase without amount)
- Add tests for structured JSON NLG input

---

## Verification Plan

### Automated Tests

**Run all tests:**
```bash
cd d:\PycharmProjects\carebank-backend
python -m pytest tests/ -v --tb=short
```

**Run specific test files:**
```bash
python -m pytest tests/test_coordinator.py -v
python -m pytest tests/test_intelligence.py -v
python -m pytest tests/test_communication.py -v
```

### Manual Verification

**1. Start the backend:**
```bash
cd d:\PycharmProjects\carebank-backend
python -m uvicorn app.main:app --reload --port 8000
```

**2. Test health score (single-intent):**
```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d "{\"user_id\": \"test_user_1\", \"message\": \"What is my health score?\"}"
```
Expected: NLG-generated response (not hardcoded f-string), `intent: "health_score"`, `agent_used: "IntelligenceAgent"`.

**3. Test entity extraction (what-if with amount):**
```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d "{\"user_id\": \"test_user_1\", \"message\": \"What if I buy a 50k TV?\"}"
```
Expected: Response mentions ₹50,000 impact (not old hardcoded 5000).

**4. Test needs_input (what-if without amount):**
```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d "{\"user_id\": \"test_user_1\", \"message\": \"What if I buy something?\"}"
```
Expected: Follow-up asking for the amount.

**5. Test balance (now via Intelligence → NLG pipeline):**
```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d "{\"user_id\": \"test_user_1\", \"message\": \"What is my balance?\"}"
```
Expected: NLG-generated balance response.
