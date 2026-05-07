# Plan: Admin-Configurable LLM, Secure Tunnel Integration, and Prompt Customization

**Phase**: Production Readiness - Admin Control Layer  
**Date Created**: May 7, 2026  
**Status**: Implementation Ready  

---

## Overview

Deploy CareBank backend on Azure (stateless) while running LLM inference locally via secure ngrok tunnel. Introduce a runtime admin configuration layer that allows:
- **LLM connectivity**: ngrok tunnel URL, model selection, timeout configuration
- **Model discovery**: list available Ollama models from admin UI
- **Prompt customization**: environment-scoped system prompts per agent with version history and rollback
- **Fail-fast policy**: LLM-dependent routes return explicit admin-actionable errors when tunnel/model unavailable
- **Deterministic banking preservation**: core financial flows remain operational when LLM is down

---

## Alignment with Architecture Contracts

### 1. SYSTEM-ARCHITECTURE Constraints

**Deterministic Core Priority** ([SYSTEM-ARCHITECTURE.md § 4 - Security & Safety](SYSTEM-ARCHITECTURE.md#4-security--safety))
- "LLMs **never** perform math. The Deterministic Core handles all real financial logic."
- **Implementation**: LLM connectivity failures do not block account queries, transfers, or balance computations.
- **Fallback**: Non-LLM routes (balance, transactions, compliance) remain fully operational when LLM provider is unreachable.

**Stateless JWT Architecture** ([SYSTEM-ARCHITECTURE.md § 1](SYSTEM-ARCHITECTURE.md#section-1))
- "stateless JWT authentication architecture… backend can scale horizontally"
- **Implementation**: New admin config models store only encryption keys/references, never session state.
- **User isolation**: Admin configuration applies globally; user-scoped data (transactions, beneficiaries) unaffected.

**Banking Provider Isolation** ([SYSTEM-ARCHITECTURE.md § 12 - MockBank Integration](SYSTEM-ARCHITECTURE.md#12-mockbank-integration))
- "Webhook signature verification via `MOCKBANK_WEBHOOK_SECRET`"
- **Implementation**: New tunnel/LLM config follows same encrypted secret pattern.

---

### 2. ACTION-ENGINE-CONTRACT Constraints

**Tool Contract Stability** ([ACTION-ENGINE-CONTRACT.md § Tool Execution Interface](ACTION-ENGINE-CONTRACT.md#tool-execution-interface))
- Tool interface: `can_handle()`, `execute()`, `get_schema()`, `get_metadata()`
- **Implementation**: LLM configuration does not change tool registry or action execution logic.
- **Prompts**: Customizable agent system prompts do not alter tool discovery or schema validation.

**Banking Provider Lifecycle** ([ACTION-ENGINE-CONTRACT.md § Banking Provider Lifecycle](ACTION-ENGINE-CONTRACT.md#banking-provider-lifecycle-mockbank))
- Banking client uses direct `httpx` to `BANKING_API_URL` (no service mesh layer).
- **Implementation**: LLM tunnel configuration is separate; banking API connectivity unchanged.

---

### 3. Existing Admin Capability Foundation

**Admin Role-Based Access** ([app/core/security.py](../app/core/security.py#L80))
- `require_admin()` dependency protects sensitive routes.
- **Implementation**: New LLM admin routes reuse this pattern; no new auth framework needed.

**Service Layer Architecture** ([.github/copilot-instructions.md § Architecture](../.github/copilot-instructions.md#architecture))
- Domain boundaries: `routes` (HTTP thin layer) → `services` (business logic) → `core` (config, DB setup) → `models` (persistence)
- **Implementation**: Strictly follow this pattern for new LLM admin functionality.

---

## Feature Scope

### In Scope

1. **Runtime LLM Configuration Management**
   - Store ngrok tunnel URL, Ollama endpoint, default model, and timeouts in database
   - Encrypt sensitive credentials (ngrok auth token) at rest
   - Admin API to create, read, update tunnel settings by environment (dev/stage/prod)

2. **Model Discovery**
   - Admin endpoint that lists available Ollama models (name, size, tags) from configured tunnel
   - Cached results (30–120 seconds) to reduce repeated tunnel calls
   - Handle tunnel unreachability with explicit error for admin remediation

3. **Environment-Scoped Prompt Customization**
   - Store system prompts per agent, per environment (dev/stage/prod) in database
   - Version history with rollback capability
   - Validation: prevent malformed templates that break agent parsing

4. **Fail-Fast Policy When LLM Unavailable**
   - LLM-dependent routes (chat, intent classification) return `503 Service Unavailable` with remediation hints
   - Deterministic routes (account, transaction, balance) remain fully operational
   - Clear audit trail for when/why LLM became unavailable

5. **Audit Logging**
   - Log all admin mutations: tunnel config updates, secret rotations, prompt publishes, rollbacks
   - Include actor (user_id), timestamp, before/after values, environment scope

---

### Out of Scope (v1)

- Multi-tunnel provider abstraction (ngrok only in first release)
- Per-user prompt customization (global + environment only)
- Prompt template dry-run validation endpoint (add in Phase 2)
- Non-admin user prompt editing
- Replacement of deterministic banking logic with LLM decisioning

---

## Data Model

### 1. LLM Tunnel Configuration

```python
# app/models/llm_tunnel_config.py (NEW)
class LLMTunnelConfig(Base):
    id: int (PK)
    environment: str  # "dev" | "stage" | "prod"
    provider_type: str  # "ngrok" for v1
    tunnel_url: str  # e.g., "https://abc123.ngrok.io"
    tunnel_auth_token_encrypted: str  # Bcrypt or AES-encrypted
    ollama_model_default: str  # "qwen3:8b"
    request_timeout_sec: int = 30
    is_active: bool = True
    created_by: str (FK user_id)
    updated_by: str (FK user_id)
    created_at: datetime
    updated_at: datetime
    last_connectivity_check: datetime | None
    last_error: str | None
```

### 2. Agent Prompt Configuration (Versioned)

```python
# app/models/agent_prompt_config.py (NEW)
class AgentPromptConfig(Base):
    id: int (PK)
    agent_name: str  # "coordinator", "payment_agent", etc.
    environment: str  # "dev" | "stage" | "prod"
    system_prompt: str (TEXT)  # Full template
    version: int = 1
    is_active: bool = True  # Only one version per agent/env can be active
    created_by: str (FK user_id)
    updated_by: str (FK user_id)
    created_at: datetime
    updated_at: datetime
    notes: str | None  # Admin notes on changes
    
    # Unique constraint: (agent_name, environment, is_active) with exactly 1 active per pair
```

### 3. Audit Log Extension

Extend existing [AuditLog](../app/models/audit_log.md) or create new `AdminActionLog`:
```python
class AdminActionLog(Base):
    id: int (PK)
    admin_user_id: str (FK user_id)
    action_type: str  # "llm_config_update" | "prompt_publish" | "prompt_rollback" | "secret_rotate"
    resource_type: str  # "tunnel" | "prompt" | "model"
    resource_id: str | None
    environment: str | None
    before_value: str | None (JSON or masked)
    after_value: str | None (JSON or masked)
    status: str  # "success" | "failed"
    error_message: str | None
    created_at: datetime
    
    # Unique index on (admin_user_id, created_at) for audit trail queries
```

---

## Backend API Contract

### Admin LLM Routes (all protected by `@Depends(require_admin)`)

**Tunnel Configuration**
```
GET    /api/admin/llm/tunnel/{environment}         → LLMTunnelConfigResponse
PUT    /api/admin/llm/tunnel/{environment}         → LLMTunnelConfigResponse
POST   /api/admin/llm/tunnel/{environment}/test    → {"status": "ok"|"error", "models_count": int, "error": str}
```

**Model Discovery**
```
GET    /api/admin/llm/models?environment={env}     → {"models": [{"name": "qwen3:8b", "size_gb": 4.7, "available": true}]}
```

**Prompt Management**
```
GET    /api/admin/llm/prompts                           → list[AgentPromptResponse] (all agents, all envs, active only)
GET    /api/admin/llm/prompts?agent={name}&env={env}   → list[AgentPromptResponse] (all versions with history)
PUT    /api/admin/llm/prompts/{id}                      → AgentPromptResponse (publish new version, auto-increment)
POST   /api/admin/llm/prompts/{id}/rollback             → AgentPromptResponse (activate prior version, create audit record)
GET    /api/admin/llm/prompts/{id}/history             → list[AgentPromptHistoryResponse]
```

**Error Responses (Fail-Fast)**
```json
{
  "status": "error",
  "code": "llm_tunnel_unavailable",
  "message": "LLM tunnel not configured or unreachable for environment 'prod'. Check Admin > LLM Configuration.",
  "remediation": "1) Verify ngrok tunnel is running locally. 2) Update tunnel URL in admin panel. 3) Run connectivity test."
}
```

---

## Frontend Admin UI Contract

### Types to Define

```typescript
// src/api/llmConfig.ts (NEW)
export interface LLMTunnelConfig {
  id: number;
  environment: 'dev' | 'stage' | 'prod';
  provider_type: string; // "ngrok"
  tunnel_url: string;
  tunnel_auth_token_masked: string; // "****...****"
  ollama_model_default: string;
  request_timeout_sec: number;
  is_active: boolean;
  last_connectivity_check: string; // ISO timestamp
  last_error?: string;
}

export interface AgentPromptConfig {
  id: number;
  agent_name: string;
  environment: 'dev' | 'stage' | 'prod';
  system_prompt: string;
  version: number;
  is_active: boolean;
  created_by: string;
  created_at: string;
  notes?: string;
}

export interface OllamaModel {
  name: string;
  size_gb: number;
  available: boolean;
}

export interface LLMConnectivityTest {
  status: 'ok' | 'error';
  models_count?: number;
  error?: string;
}
```

### Admin Page Structure

Three tabs:
1. **Connection Settings**: tunnel URL, auth token, default model, timeout
2. **Connectivity & Models**: test button, model list display, default model selector
3. **Agent Prompts**: environment selector, per-agent editor, version history, rollback

---

## Implementation Phases

### Phase 1: Architecture & Contracts (NOW)
- ✅ Create this plan document
- Define backend API contract (above)
- Define frontend types contract (above)

### Phase 2: Backend Data Models & Crypto

**Deliverables:**
- New SQLAlchemy models: `LLMTunnelConfig`, `AgentPromptConfig`, audit log extension
- Alembic migration
- Encryption/decryption service in `app/core/crypto.py`
- Masked-read utility for secrets

**Files to Create/Modify:**
- `app/models/llm_tunnel_config.py` (NEW)
- `app/models/agent_prompt_config.py` (NEW)
- `app/core/crypto.py` (NEW)
- `alembic/versions/{timestamp}_add_llm_admin_models.py` (NEW migration)
- `app/core/database.py` (register new models)

**Testing:** Unit tests for encryption, model imports, migration application

---

### Phase 3: Backend Services & Agent Integration

**Deliverables:**
- `app/services/llm_admin_service.py`: CRUD, URL validation, connectivity test
- `app/services/llm_model_discovery.py`: fetch/cache Ollama models
- `app/services/agent_prompt_service.py`: version control, rollback, validation
- Refactored `app/services/llm.py`: environment-scoped provider resolution
- Updated `app/agents/coordinator.py`: runtime prompt resolver

**Files to Create/Modify:**
- `app/services/llm_admin_service.py` (NEW)
- `app/services/llm_model_discovery.py` (NEW)
- `app/services/agent_prompt_service.py` (NEW)
- `app/services/llm.py` (MODIFY: add DB config precedence)
- `app/agents/coordinator.py` (MODIFY: fetch prompts at runtime)

**Testing:** Unit tests for service logic, integration tests for DB access

---

### Phase 4: Backend Routes & Schemas

**Deliverables:**
- `app/routes/admin_llm_config.py`: tunnel, model, prompt endpoints
- `app/schemas/admin_llm.py`: request/response Pydantic models
- OpenAPI documentation
- Rate limiting (if middleware exists)

**Files to Create/Modify:**
- `app/routes/admin_llm_config.py` (NEW)
- `app/schemas/admin_llm.py` (NEW)
- `app/main.py` (register router)

**Testing:** Integration tests for all routes with admin auth checks

---

### Phase 5: Frontend Admin Wiring

**Deliverables:**
- New admin route and navigation item
- `src/pages/admin/AdminLLMConfig.tsx`: main page with tabs
- `src/components/admin/EndpointConfigPanel.tsx`: connection settings
- `src/components/admin/ModelsPanel.tsx`: model discovery & selection
- `src/components/admin/AgentPromptsPanel.tsx`: prompt editor, versioning, rollback
- API client methods
- Component tests

**Files to Create/Modify:**
- `src/pages/admin/AdminLLMConfig.tsx` (NEW)
- `src/components/admin/EndpointConfigPanel.tsx` (NEW)
- `src/components/admin/ModelsPanel.tsx` (NEW)
- `src/components/admin/AgentPromptsPanel.tsx` (NEW)
- `src/App.tsx` (add route)
- `src/layouts/AdminLayout.tsx` (add nav link)
- `src/lib/api.ts` (add client methods)

---

### Phase 6: Testing & Validation

**Backend Tests:**
- Unit: encryption, model parsing, prompt versioning, rollback
- Integration: admin routes with role checks, persistence
- E2E: manual on local Azure emulation (if available) or mock backend

**Frontend Tests:**
- Component tests for each admin panel
- Model list rendering and error states
- Prompt version history and rollback UX

**E2E Checklist:**
1. Save tunnel config (URL, token, model)
2. Run connectivity test → see model list
3. Update environment-specific prompt
4. View version history
5. Rollback to prior version
6. Simulate tunnel down → verify LLM routes fail with clear error
7. Verify banking routes still work during LLM outage
8. Confirm audit logs recorded all admin actions

---

### Phase 7: Azure Operations Readiness

**Deliverables:**
- Deployment config notes (app settings for encryption key, environment mapping)
- Runbook: ngrok token rotation, outage handling
- Monitoring signals: tunnel health, model-list latency, prompt publish/rollback events
- Production rollback procedure: disable LLM integration while preserving banking

**Files to Create/Modify:**
- `docs/DEPLOYMENT-AZURE-LLM-TUNNEL.md` (NEW)
- `docs/RUNBOOK-LLM-TUNNEL-OPERATIONS.md` (NEW)
- Backend: add observability logging for tunnel checks, model discovery, prompt operations

---

## Key Implementation Decisions

| Decision | Rationale |
|----------|-----------|
| **Tunnel tech: ngrok** | Simplest setup for secure tunnel; can add Tailscale/Cloudflare in v2 |
| **Prompt scope: environment-scoped** | Separate prompts for dev/stage/prod with independent rollback history |
| **Prompt operations: versioned + rollback required** | Enables audit trail and production blast-radius reduction |
| **Failure mode: explicit error** | Admin can quickly see what's wrong; deterministic routes unaffected |
| **Secret handling: encrypted at rest in DB** | No need for external secret manager in v1; still secure and auditable |
| **Cache policy: 30–120 sec for model list** | Balances freshness vs. tunnel call overhead |

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| **Tunnel credential leak** | Encrypt at rest; mask on admin read API; audit all accesses |
| **Broken prompt crashes agent** | Validate prompt template structure before publish; keep prior version as rollback |
| **LLM outage blocks all routes** | Deterministic banking + non-LLM routes unaffected by design; LLM routes fail-fast |
| **Admin misconfigures environment** | Clear error messages on connectivity test; rollback support for prompts |
| **Horizontal scaling loses config** | Config in DB (shared across replicas); no server-side session state |

---

## Success Criteria

1. **Admin can configure ngrok tunnel URL and auth token via UI** and the configuration persists across backend restarts
2. **Admin can test tunnel connectivity** and see list of available Ollama models
3. **Admin can select default model** for a given environment
4. **Admin can edit and publish system prompts** per agent per environment
5. **Admin can view prompt version history** and roll back to any prior version
6. **When tunnel/model is unavailable**, LLM-dependent routes return fail-fast error with remediation hints
7. **Deterministic banking routes remain operational** when LLM is down
8. **All admin mutations are audited** (config changes, secret rotations, prompt publishes, rollbacks)
9. **Azure-deployed backend can reach local Ollama** over ngrok tunnel
10. **OpenAPI docs reflect new admin contract** and routes are discoverable

---

## References

- [SYSTEM-ARCHITECTURE.md](SYSTEM-ARCHITECTURE.md)
- [ACTION-ENGINE-CONTRACT.md](ACTION-ENGINE-CONTRACT.md)
- [PLAN-backend-production.md](PLAN-backend-production.md)
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)
