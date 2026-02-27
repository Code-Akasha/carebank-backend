# Phase 2: Agent Skeletons & LangGraph Orchestration (Hours 6-12)

> **Status: PENDING** | Branch: `feature/coordinator-agent`
> **Reference:** [Coordinator Agent Guide](file:///d:/WebstormProjects/.github-private/docs/FEATURE-GUIDES/coordinator-agent.md)

---

## Goal

Build the Coordinator Agent using LangGraph, create a common agent interface, and wire up stub agents that the Coordinator can route to. This phase is **backend-only** — no frontend work.

## Dependencies

- ✅ Phase 1: Database, models, deterministic core, API routes — **COMPLETE**
- ✅ Redis available via Docker Compose

## New Dependencies to Install

```
langgraph>=0.4.0
langchain-core>=0.3.0
langchain-openai>=0.3.0
```

---

## Tasks

### Task 1: Install LangGraph Dependencies
- Add `langgraph`, `langchain-core`, `langchain-openai` to `requirements.txt`
- `pip install -r requirements.txt`
- **Verify:** `python -c "import langgraph; print(langgraph.__version__)"`

### Task 2: Create Agent Base Interface (`app/agents/base.py`)
- Define `AgentInput` / `AgentOutput` Pydantic models (common contract)
- Create abstract `BaseAgent` class with `invoke(input: AgentInput) -> AgentOutput`
- Add error handling + fallback pattern
- **Verify:** Can instantiate a test subclass

### Task 3: Create Stub Agents
Create minimal implementations that return hardcoded responses:
- `app/agents/intelligence.py` — stub Intelligence Agent
- `app/agents/communication.py` — stub Communication Agent
- `app/agents/opportunity.py` — stub Opportunity Agent
- `app/agents/auto_savings.py` — stub Auto-Savings Agent
- `app/agents/__init__.py` — export all agents
- **Verify:** Each stub returns a valid `AgentOutput` when called

### Task 4: Implement Coordinator State Machine (`app/agents/coordinator.py`)
Based on the [Feature Guide](file:///d:/WebstormProjects/.github-private/docs/FEATURE-GUIDES/coordinator-agent.md):
- `CoordinatorState` TypedDict (user_id, message, intent, agent_response, audit_log)
- LangGraph `StateGraph` with nodes: `classify` → `route` → `validate` → `respond`
- Intent classification: keyword-based initially (health → Intelligence, what-if → Intelligence+Core, save → Auto-Savings, product → Opportunity, general → Communication)
- Agent routing: call the correct stub agent based on classified intent
- Compile graph with `graph.compile()`
- **Verify:** `build_coordinator_graph()` compiles without errors

### Task 5: Session State Management
- Create `app/models/session.py` — SQLAlchemy model for agent sessions
- Fields: `id`, `user_id`, `state_json`, `created_at`, `updated_at`
- LangGraph checkpointer using PostgreSQL (or in-memory for MVP)
- **Verify:** State persists across 2 sequential requests

### Task 6: Interaction Audit Logging
- Create `app/models/audit_log.py` — SQLAlchemy model
- Fields: `id`, `session_id`, `user_id`, `user_message`, `intent`, `agent_used`, `agent_response`, `timestamp`
- Log every Coordinator interaction automatically
- Add Alembic migration for new models
- **Verify:** After a chat request, audit log has a new entry

### Task 7: Coordinator API Route (`app/routes/chat.py`)
- `POST /api/chat` — accepts `{user_id, message}`
- Calls Coordinator graph with the message
- Returns `{response, intent, agent_used}`
- **Verify:** `curl -X POST /api/chat -d '{"user_id":"user_001","message":"What is my health score?"}'` returns a response

### Task 8: Add Conversation Memory
- LangGraph conversation memory (message history)
- Store in PostgreSQL or use LangGraph's built-in checkpointer
- Context window management (keep last N messages)
- **Verify:** Coordinator remembers context from previous message

### Task 9: Tests
- `tests/test_coordinator.py`:
  - Health query → routed to Intelligence Agent
  - What-if query → routed to Intelligence + Deterministic Core
  - Unknown query → fallback to Communication Agent
  - Agent failure → graceful error message
  - Audit log created for each interaction
- **Verify:** `pytest tests/test_coordinator.py -v` passes

---

## Done When

- [ ] Coordinator routes a test message to a stub agent and returns a response
- [ ] Interaction log persists to database
- [ ] State survives across multiple requests
- [ ] All stub agents implement `BaseAgent` interface
- [ ] `POST /api/chat` endpoint works end-to-end

## File Structure After Phase 2

```
app/
├── agents/
│   ├── __init__.py
│   ├── base.py           # BaseAgent interface
│   ├── coordinator.py    # LangGraph state machine
│   ├── intelligence.py   # Stub
│   ├── communication.py  # Stub
│   ├── opportunity.py    # Stub
│   └── auto_savings.py   # Stub
├── models/
│   ├── session.py        # Session state model
│   └── audit_log.py      # Audit log model
├── routes/
│   └── chat.py           # POST /api/chat
└── ...
```

## Notes

- Keep stubs simple — they just need to prove routing works. Real logic comes in Phase 3-4.
- Intent classification can be keyword-based for now. LLM-based classification comes in Phase 4.
- The Coordinator is the **single entry point** for all agent interactions — never call agents directly.
