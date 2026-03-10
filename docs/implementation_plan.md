# Agent Framework Hardening — Implementation Plan

The 4 agent files (`base.py`, `communication.py`, `coordinator.py`, `intelligence.py`) received a detailed code review scoring **8.3/10**. This plan addresses each finding to bring the system closer to production-readiness while respecting the hackathon constraints (no new agents, no stack changes, no new features).

> [!IMPORTANT]
> This plan is **NO CODE**. It covers **18 improvements** grouped across 4 files, ordered by priority. Each improvement has clear INPUT → OUTPUT → VERIFY criteria.

---

## Proposed Changes

### 1. Agent Framework — `base.py`

#### [MODIFY] [base.py](file:///d:/PycharmProjects/carebank-backend/app/agents/base.py)

**1.1 — Typed context model** (replaces loose `dict`)
- Create `AgentContext(BaseModel)` with typed fields: `history`, `persona`, `expense_amount`, `purchase_amount`, `is_nudge`, `agent_results`, `data`, `task`, `amount`
- Update `AgentInput.context` from `dict` to `AgentContext`
- Use `model_validator` or `__init__` to accept both dict and AgentContext for backwards compat

**1.2 — Status enum**
- Create `AgentStatus(str, Enum)` with values: `success`, `error`, `needs_input`
- Replace `status: str = "success"` in `AgentOutput`

**1.3 — Execution metrics in AgentOutput**
- Add optional fields: `latency_ms: float | None`, `tokens_used: int | None`
- Capture latency in `BaseAgent.invoke()` via `time.perf_counter()`

**1.4 — Invoke latency tracking**
- Wrap `_invoke()` call with timing in the base `invoke()` method
- Attach `latency_ms` to output metadata automatically

---

### 2. Communication Agent — `communication.py`

#### [MODIFY] [communication.py](file:///d:/PycharmProjects/carebank-backend/app/agents/communication.py)

**2.1 — Remove JSON serialization of agent_results**
- Change `json.dumps(agent_results, default=str)` to pass `agent_results` directly  
- Let the prompt template handle formatting

**2.2 — Enrich provider metadata**
- Add `model` and `tokens` to the returned metadata dict (from `nlg_result`)

> [!NOTE]
> Persona caching (Redis) and nudge service extraction are **deferred** — they are architectural changes beyond the scope of this hardening pass. Documented as future work.

---

### 3. Coordinator — `coordinator.py`

#### [MODIFY] [coordinator.py](file:///d:/PycharmProjects/carebank-backend/app/agents/coordinator.py)

**3.1 — Remove `agent_name` from LLM classification output**
- Remove `agent_name` field from `ClassificationResult`
- After LLM returns intent, use `_INTENT_TO_AGENT` mapping to resolve agent deterministically
- This decouples routing from LLM hallucination

**3.2 — Lazy agent registry**
- Change `_build_agent_registry()` to store **classes** instead of **instances**
- Instantiate on first access via a `_get_agent(name)` helper
- Optional: use `functools.lru_cache` per agent name

**3.3 — Multi-intent task planning (basic)**
- Enhance `plan_tasks()` to detect if the LLM returned secondary intents
- Update the classification prompt to optionally return `secondary_intent`
- Create 2 tasks when both primary and secondary are detected

**3.4 — Conversation store abstraction**
- Create `ConversationStore` protocol (interface) with `get`, `add`, `clear`
- Implement `InMemoryConversationStore` (current behavior)
- Wire it into coordinator via a module-level instance
- This makes Redis swap a future 1-line change without touching logic

**3.5 — Classification prompt update**
- Remove `agent_name` instruction from the prompt template
- Simplify to only ask for `intent`, `confidence`, `parameters`

---

### 4. Intelligence Agent — `intelligence.py`

#### [MODIFY] [intelligence.py](file:///d:/PycharmProjects/carebank-backend/app/agents/intelligence.py)

**4.1 — Deduplicate data fetching**
- Create a `_fetch_financial_data(user_id)` helper that returns both transactions and balance in one call
- Replace individual `_fetch_transactions` + `_fetch_balance` calls in handlers that need both

**4.2 — Move risk thresholds to config**
- Create `app/core/config_thresholds.py` with `RiskThresholds` dataclass
- Move hardcoded values (`retained_pct > 70`, `post_purchase_balance >= 10000`) to config
- Import and use in intelligence.py

**4.3 — Mock fallback production guard**
- Add environment check before falling back to mock data
- Guard: `if settings.ENVIRONMENT == "production": raise` instead of silently using mocks

---

### 5. New Files

#### [NEW] [config_thresholds.py](file:///d:/PycharmProjects/carebank-backend/app/core/config_thresholds.py)
- `RiskThresholds` dataclass with `what_if_low`, `what_if_medium`, `affordability_safe_buffer`

#### [NEW] [conversation_store.py](file:///d:/PycharmProjects/carebank-backend/app/services/conversation_store.py)
- `ConversationStore` Protocol
- `InMemoryConversationStore` implementation

---

### 6. Test Updates

#### [MODIFY] [test_coordinator.py](file:///d:/PycharmProjects/carebank-backend/tests/test_coordinator.py)
- Update imports (remove `ClassificationResult.agent_name` references if any)
- Add test for deterministic intent→agent mapping
- Add test for lazy registry instantiation
- Add test for multi-intent detection (basic)

#### [MODIFY] [test_intelligence.py](file:///d:/PycharmProjects/carebank-backend/tests/test_intelligence.py)
- Add test for mock fallback guard in production mode
- Add test for config threshold usage

#### [MODIFY] [test_communication.py](file:///d:/PycharmProjects/carebank-backend/tests/test_communication.py)
- Verify enriched metadata includes `model` field

#### [NEW] [test_base.py](file:///d:/PycharmProjects/carebank-backend/tests/test_base.py)
- Test `AgentStatus` enum values
- Test `AgentContext` typed model validation
- Test latency tracking in `invoke()`

---

## Deferred Items (Future Work)

These improvements from the review are valid but are architectural changes beyond this hardening pass:

| Item | Reason Deferred |
|------|----------------|
| Redis conversation store | Requires infra setup; abstraction layer enables easy swap |
| Persona caching (Redis TTL) | Requires Redis infra + cache invalidation strategy |
| Nudge service extraction | Architectural refactor; current location works for MVP |
| Embedding-based classifier | Requires pgvector integration for intent embeddings |
| Langfuse/OpenTelemetry observability | Requires external service setup |
| Async parallel data fetching | Requires converting sync agents to async |
| Smarter affordability (income/expenses) | Feature expansion beyond hardening scope |

---

## Verification Plan

### Automated Tests

Run the full existing test suite plus new tests:

```bash
cd d:\PycharmProjects\carebank-backend
pytest tests/ -v --tb=short
```

**Expected:** All existing 40+ tests pass, plus ~8 new tests.

### Specific Test Coverage

| Change | Test Command | What It Verifies |
|--------|-------------|-----------------|
| `AgentStatus` enum | `pytest tests/test_base.py -v` | Enum values match, backward compat with string |
| `AgentContext` model | `pytest tests/test_base.py -v` | Typed context accepts valid data, rejects invalid |
| Latency tracking | `pytest tests/test_base.py -v` | `latency_ms` is populated after invoke |
| Deterministic routing | `pytest tests/test_coordinator.py::TestKeywordClassification -v` | Intent→agent mapping is code-driven, not LLM |
| Lazy registry | `pytest tests/test_coordinator.py -v` | Agents instantiated on demand |
| Multi-intent | `pytest tests/test_coordinator.py::TestPlanTasks -v` | Two tasks created for compound queries |
| Mock guard | `pytest tests/test_intelligence.py -v` | Mock fallback blocked in production env |
| Config thresholds | `pytest tests/test_intelligence.py -v` | Thresholds read from config, not hardcoded |

### Regression Check

```bash
pytest tests/test_coordinator.py tests/test_communication.py tests/test_intelligence.py -v
```

All existing E2E graph tests must pass unchanged (the full `TestCoordinatorGraph` suite).

### Lint Check

```bash
cd d:\PycharmProjects\carebank-backend
ruff check app/agents/ app/core/ app/services/ tests/
```
