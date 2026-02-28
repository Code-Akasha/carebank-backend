# Phase 4: Communication Agent + LLM Integration + Compliance Guard (Hours 20-24)

> **Status: PENDING** | Branches: `feature/compliance-guard`
> **References:** [Communication Agent Guide](file:///d:/WebstormProjects/.github-private/docs/FEATURE-GUIDES/communication-agent.md) · [Compliance Guard Guide](file:///d:/WebstormProjects/.github-private/docs/FEATURE-GUIDES/compliance-guard.md)

---

## Goal

Replace the Communication Agent stub with LLM-powered NLG, implement nudge fatigue control, persona-based tone adaptation, and build the Compliance Guard interceptor. Use a **multi-provider LLM strategy**: Ollama (local) as primary, Gemini API as fallback, template as last resort.

## Dependencies

- ✅ Phase 1: Deterministic Core (source of truth for numbers)
- ✅ Phase 2: BaseAgent interface, Coordinator pipeline (validate node is placeholder)
- ✅ Phase 3: Intelligence Agent (provides persona, forecasts, anomaly data)
- Gemini API key configured in `.env` (for fallback)

## New Dependencies to Install

```
langchain-google-genai>=2.1.0   # Gemini API via LangChain
langchain-ollama>=0.3.0         # Ollama local LLM via LangChain
```

> [!IMPORTANT]
> **Removed `langchain-openai` dependency from the LLM flow.** We keep it installed (coordinator uses langchain-core) but the NLG service uses Gemini + Ollama only.

---

## LLM Provider Strategy

```
Priority Chain:
  1. Ollama (local) ← primary, zero-cost, low-latency, offline-capable
  2. Gemini API     ← fallback, generous free tier, no billing needed
  3. Template       ← last resort, always works, no LLM needed
```

### `.env` Configuration

```env
# LLM Provider: "ollama" | "gemini" | "auto" (default: auto = try ollama → gemini → template)
LLM_PROVIDER=auto

# Ollama settings (when LLM_PROVIDER=ollama or auto)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Gemini settings (when LLM_PROVIDER=gemini or auto fallback)
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```

### Config Updates (`app/core/config.py`)

```python
class Settings(BaseSettings):
    # ... existing fields ...
    llm_provider: str = "auto"          # "ollama" | "gemini" | "auto"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
```

---

## Tasks

### Task 1: LLM Provider Factory (`app/services/llm.py`)

**Centralized LLM initialization with automatic fallback.**

```python
def get_llm() -> BaseChatModel | None:
    """
    Returns the configured LLM based on LLM_PROVIDER setting.
    
    - "ollama" → ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
    - "gemini" → ChatGoogleGenerativeAI(model=GEMINI_MODEL, api_key=GEMINI_API_KEY)
    - "auto"   → try Ollama first, then Gemini, else None (triggers template fallback)
    """
```

**Implementation details:**
- `auto` mode: ping Ollama `/api/tags` endpoint → if reachable, use Ollama; else try Gemini
- Cache the resolved provider per-process (avoid re-probing on every request)
- Return `None` if neither is available → NLG service uses template fallback

**Verify:** With Ollama running → returns `ChatOllama`. Without Ollama + with `GEMINI_API_KEY` → returns `ChatGoogleGenerativeAI`. Neither → returns `None`.

---

### Task 2: NLG Service (`app/services/nlg.py`)

**Core LLM integration with structured prompts.**

```python
SYSTEM_PROMPT = """You are CareBank's financial wellness assistant.
Rules:
- Never mention competitor names
- ONLY use the exact numbers provided in the data — never invent numbers
- Adapt tone based on the persona provided
- Keep responses under 3 sentences unless asked for detail
- Be empathetic and actionable
"""

def generate_explanation(data: dict, persona: str, context: str = "") -> str:
    """
    Calls LLM (Ollama/Gemini) or falls back to template.
    Input:  Deterministic Core data + persona label + context
    Output: Human-readable explanation string
    """
```

**Fallback chain within the function:**
```python
def generate_explanation(data, persona, context=""):
    llm = get_llm()
    if llm:
        try:
            return _call_llm(llm, data, persona, context)
        except Exception:
            pass  # fall through to template
    return _template_fallback(data, persona)
```

> [!IMPORTANT]
> **Critical safety rule:** The LLM receives numbers FROM Deterministic Core. It NEVER calculates numbers. It only explains them in natural language.

**Verify:** With Ollama → returns LLM response. Without Ollama + with Gemini key → returns Gemini response. Neither → returns template.

---

### Task 3: Nudge Fatigue Controller (`app/services/nudge.py`)

**Prevents notification overload.**

```python
MAX_NUDGES_PER_DAY = 3
COOLDOWN_HOURS = 4

def should_send_nudge(user_id: str) -> bool:
    """
    1. Today's nudge count < MAX_NUDGES_PER_DAY
    2. Hours since last nudge >= COOLDOWN_HOURS
    """

def record_nudge(user_id: str) -> None:
    """Record that a nudge was sent (in-memory for MVP)."""
```

**Verify:** 4th nudge in a day → blocked. Nudge within 4h window → blocked.

---

### Task 4: Upgrade Communication Agent (`app/agents/communication.py`)

Replace stub with LLM-powered agent:

- Use `generate_explanation()` from NLG service (handles Ollama/Gemini/template automatically)
- Adapt tone based on persona from context
- Return structured `AgentOutput` with metadata including which LLM provider was used

**Verify:** Returns persona-adapted explanation via resolved LLM (or fallback).

---

### Task 5: Compliance Guard Implementation (`app/compliance/guard.py`)

**Safety interceptor — validates all outputs.**

Pipeline:
1. **Blacklist check** → block prohibited terms ("guaranteed returns", "risk-free", etc.)
2. **Number verification** → ensure numbers trace to Deterministic Core source data
3. **Disclaimer injection** → add context-appropriate legal text
4. **Audit logging** → record every decision

**Verify:** Blacklisted terms caught; clean responses get disclaimers.

---

### Task 6: Compliance Rules (`app/compliance/rules.py`)

- `BLACKLIST`: prohibited financial terms
- `DISCLAIMERS`: context-specific legal text (savings, products, investment, general)
- `extract_numbers()`: find all numeric values in text
- `select_disclaimer()`: match disclaimer to response content

**Verify:** Number extractor finds currency amounts and percentages.

---

### Task 7: Wire Compliance Guard into Coordinator

Update `validate_response` node in `coordinator.py` → call `ComplianceGuard.validate()` instead of pass-through.

**Verify:** Coordinator pipeline actively validates before returning.

---

### Task 8: Update Config (`app/core/config.py`)

Add LLM provider settings:
- `llm_provider`, `ollama_base_url`, `ollama_model`, `gemini_api_key`, `gemini_model`
- Remove `openai_api_key` (no longer primary)

---

### Task 9: Tests

#### `tests/test_communication.py`
- NLG: Template fallback returns useful response (no LLM configured)
- Nudge: Blocks 4th notification in a day
- Nudge: Blocks within 4h cooldown
- Nudge: Allows after cooldown expires
- Communication Agent: Returns valid AgentOutput
- LLM factory: Returns `None` when no provider configured

#### `tests/test_compliance.py`
- Blacklisted "guaranteed returns" → blocked
- Clean advice → approved with disclaimer
- Number verification: hallucinated number → blocked
- Disclaimer: savings context → savings disclaimer
- Audit log records every decision

**Verify:** `pytest tests/test_communication.py tests/test_compliance.py -v` passes.

---

## Done When

- [ ] LLM provider factory resolves Ollama → Gemini → None correctly
- [ ] Communication Agent generates LLM explanations with persona tone
- [ ] Nudge fatigue prevents > 3/day and respects 4h cooldown
- [ ] Compliance Guard blocks prohibited terms and hallucinated numbers
- [ ] Template fallback works when no LLM is available
- [ ] Coordinator validate node uses real Compliance Guard
- [ ] All tests pass

## File Structure After Phase 4

```
app/
├── agents/
│   ├── communication.py  # Upgraded → LLM-powered NLG
│   ├── coordinator.py    # validate node → real Compliance Guard
│   └── ...
├── compliance/
│   ├── __init__.py       # ComplianceResult model
│   ├── guard.py          # ComplianceGuard class
│   └── rules.py          # Blacklist, disclaimers, number extraction
├── services/
│   ├── llm.py            # LLM provider factory (Ollama/Gemini/None)
│   ├── nlg.py            # NLG with automatic fallback chain
│   ├── nudge.py          # Nudge fatigue controller
│   └── ...
└── ...
```

## Notes

- **Priority: Ollama → Gemini → Template.** This gives maximum flexibility — develop offline with Ollama, demo with Gemini, never break with template.
- The `LLM_PROVIDER=auto` mode pings Ollama once on startup and caches the result.
- Gemini's free tier (60 RPM on `gemini-2.0-flash`) is more than enough for hackathon demo.
- Communication Agent is the **single LLM touchpoint**. All other agents stay deterministic/ML.
