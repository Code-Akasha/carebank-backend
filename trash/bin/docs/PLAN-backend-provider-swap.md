# PLAN: Banking Provider Proxy Swap (2026-05-05)

## Objective
Replace the standalone MockBank dependency with an internal agentic proxy that preserves the existing BankingClient contract and backend/frontend API stability. All banking data must flow frontend -> backend -> proxy -> backend -> frontend (no direct frontend -> proxy access).

## Scope
- Keep backend routes and frontend contracts unchanged.
- Swap BANKING_API_URL to point at the proxy service.
- Preserve async signed webhook lifecycle for action execution.
- Maintain policy fallback behavior if the proxy is unavailable.

## Phases

### 1. Contract Freeze
- Confirm the provider contract surface in app/services/banking_client.py.
- Enumerate endpoints and required response fields.
- Document compatibility assumptions for webhook payloads.

### 2. Proxy Readiness
- Implement agentic proxy with JWT auth, Synthetic World State, response cache, and webhook delivery.
- Ensure admin dead-letter and replay endpoints are supported.
- Enforce backend-only access with service JWT and no CORS.

### 3. Backend Integration
- Point BANKING_API_URL to proxy.
- Align BANKING_API_SECRET and webhook secret usage.
- Keep existing webhook signature verification and policy fallback unchanged.

### 4. Validation
- Contract parity tests for each BankingClient method.
- Action lifecycle tests (trigger -> webhook -> reconcile -> dead-letter replay).
- Frontend smoke tests with no direct proxy access.

### 5. Decommission MockBank
- Remove mockbank runtime dependency from startup scripts and compose.
- Keep rollback toggle for legacy provider.

## Risks
- Contract drift in proxy responses could break backend routes.
- Webhook signature mismatch could stall action execution updates.
- Proxy cache collisions if fingerprinting is too coarse.

## Rollback
- Restore BANKING_API_URL to legacy provider and disable proxy usage.
