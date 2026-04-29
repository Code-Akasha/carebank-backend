# CareBank Autonomous Banking Progress Tracker

Last updated: 2026-04-29

## Current Build Objective
Build a policy-governed action platform with hybrid autonomy (first approval, then trusted recurring auto-execution), India-first constraints, and strong auditability. Complete end-to-end wiring across Backend, MockBank, and Frontend.

---

## GAP ANALYSIS (2026-04-29 — Cross-Repo Audit)

### Critical Wiring Gaps (Backend ↔ MockBank ↔ Frontend)

| # | Gap | Impact | Repos |
|---|-----|--------|-------|
| G1 | **MockBank routes not wired**: Only `accounts.py` scaffold exists in `app/routes/`; all endpoints live in monolithic `main.py` (~2500 lines). No route modularization. | Maintenance nightmare, no separation of concerns | MockBank |
| G2 | **MockBank admin endpoints not exposed**: Backend `admin.py` has webhook replay proxy but no scenario trigger/ simulation toggle/ dead-letter list proxies wired to MockBank `/admin/*` endpoints. | Admin can't manage simulation or dead letters | Backend+MockBank |
| G3 | **MockBank `/admin/*` endpoints missing entirely**: No admin endpoints for scenario triggering, simulation toggle, dead-letter listing exist in MockBank `main.py`. | Can't trigger scenarios or manage simulation from admin UI | MockBank |
| G4 | **Coordinator graph not using tool actions**: Planner/executor integration into coordinator graph is NOT done. `chat_action_executor.py` exists but `coordinator.py` doesn't route action intents through it. | Chat can't trigger bill pay, rent pay, etc. | Backend |
| G5 | **Action webhook endpoint wiring**: Backend has `/api/actions/webhooks/mockbank` but MockBank `_dispatch_signed_webhook` calls it — need to verify signature validation end-to-end. | Webhook delivery may silently fail | Backend+MockBank |
| G6 | **Frontend bill-pay flow incomplete**: `Bills.tsx` shows discovery results but has no "Pay Now" button wired to action engine. `Planning.tsx` shows plans but no "Execute" action. | Users can't act on discovered bills or plans | Frontend+Backend |
| G7 | **Frontend no beneficiary management UI**: Backend & MockBank have full beneficiary CRUD + verify. Frontend has zero beneficiary pages/components. | Users can't manage beneficiaries | Frontend |
| G8 | **Frontend no schedule management UI**: Backend & MockBank have schedule CRUD. Frontend has zero schedule pages. | Users can't manage bank schedules | Frontend |
| G9 | **Overdue escalation not implemented**: Reminder worker covers D-3/D-1/due-day but has no escalation path after missed due date. | Missed payments go silent | Backend |
| G10 | **No Alembic migrations for new tables**: Models exist in SQLAlchemy but no Alembic migration files generated. `db_schema_mode` defaults to `alembic` but migrations are empty. | Production deploys will fail | Backend |
| G11 | **MockBank in-memory state for transactions/balances**: Despite Postgres persistence for beneficiaries/schedules/dead-letters, transactions and balances are still in-memory dicts. | Data lost on restart | MockBank |
| G12 | **Frontend admin simulation page incomplete**: `AdminSimulation.tsx` exists but MockBank has no `/admin/simulation` endpoint to toggle. | Admin can't control simulation | Frontend+MockBank |
| G13 | **Telegram outbound reminders incomplete**: Phase 6 checklist shows outbound reminders/approvals not done. | No push notifications via Telegram | Backend |
| G14 | **No E2E tests across repos**: Tests exist per-repo but no cross-repo integration/E2E tests. | Regressions across repo boundaries | All 3 |

### Feature Completeness Matrix

| Feature | Backend API | Backend Logic | MockBank | Frontend UI | Wired E2E |
|---------|------------|---------------|----------|-------------|-----------|
| Auth (Register/Login) | ✅ | ✅ | ✅ (JWT verify) | ✅ | ✅ |
| Dashboard (Balances/Txns) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Health Score | ✅ | ✅ | N/A | ✅ | ✅ |
| Chat/Agent | ✅ | ✅ | N/A | ✅ | ✅ |
| Transaction History | ✅ | ✅ | ✅ | ✅ | ✅ |
| Account Management | ✅ | ✅ | ✅ (scaffold) | ✅ | ⚠️ Partial |
| Profile/Settings | ✅ | ✅ | N/A | ❌ | ❌ |
| Planning (Plans/Goals) | ✅ | ✅ | N/A | ⚠️ Read-only | ❌ |
| Bills Discovery | ✅ | ✅ | N/A | ⚠️ Read-only | ❌ |
| Recurring Rules | ✅ | ✅ | N/A | ❌ | ❌ |
| Action Requests (CRUD) | ✅ | ✅ | N/A | ❌ | ❌ |
| Action Approval/Reject | ✅ | ✅ | N/A | ❌ | ❌ |
| Action Execution | ✅ | ✅ | ✅ (trigger) | ❌ | ❌ |
| Payment Execution (one-time) | ✅ | ✅ | ✅ | ❌ | ❌ |
| Recurring Payments | ✅ | ✅ | N/A | ❌ | ❌ |
| Auto-Savings | ✅ | ✅ | ✅ | ❌ | ❌ |
| Beneficiaries CRUD | ✅ (proxy) | ✅ | ✅ | ❌ | ❌ |
| Beneficiary Verify | ✅ (proxy) | ✅ | ✅ | ❌ | ❌ |
| Bank Schedules CRUD | ✅ (proxy) | ✅ | ✅ | ❌ | ❌ |
| Settlement Windows | ✅ (proxy) | ✅ | ✅ | ❌ | ❌ |
| Reminders/Notifications | ✅ | ✅ | N/A | ❌ | ❌ |
| Admin Dashboard | ✅ | ✅ | ❌ | ✅ | ⚠️ Partial |
| Admin Agent Logs | ✅ | ✅ | N/A | ✅ | ✅ |
| Admin Users List | ✅ | ✅ | N/A | ✅ | ✅ |
| Admin Simulation | ❌ | ❌ | ❌ | ⚠️ Shell | ❌ |
| Admin Webhooks DLQ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Telegram Bot | ✅ | ✅ | N/A | N/A | ⚠️ Partial |
| MPIN Verification | ✅ | ✅ | N/A | ⚠️ Component | ❌ |

---

## REVISED PHASE PLAN — End-to-End Completion

### Phase 8 — MockBank Modularization + Admin Endpoints (Week 1-2) 🔴 P0
**Goal**: Make MockBank maintainable and expose admin controls.

- [ ] **M8.1** Extract MockBank routes from `main.py` into `app/routes/`:
  - `transactions.py` — GET /transactions, POST /trigger, GET /lifecycle, POST /reverse
  - `balances.py` — GET /balances
  - `beneficiaries.py` — GET/POST /beneficiaries, PUT /verify
  - `schedules.py` — GET/POST /schedules, POST /run, DELETE
  - `products.py` — GET /products, /banking/plans
  - `policies.py` — GET /banking/policies, /policies/actions/{type}
  - `providers.py` — GET /providers
  - `accounts.py` — GET/POST/DELETE /accounts (replace scaffold)
  - `admin.py` — POST /admin/scenario, POST /admin/simulation/toggle, GET /admin/simulation/status, GET /admin/webhooks/dead-letter, POST /admin/webhooks/dead-letter/{id}/replay, GET /admin/webhooks/delivery-log
  - `profiles.py` — POST /profiles/upsert
- [ ] **M8.2** Move helper functions to `app/services/`:
  - `transaction_service.py` — _append_transaction, _process_transaction_event, _validate_transaction_policy
  - `settlement_service.py` — _compute_settlement_fields, _finalize_settlement_after_delay
  - `webhook_service.py` — _build_signed_webhook, _dispatch_signed_webhook, dead-letter management
  - `beneficiary_service.py` — beneficiary CRUD, cooldown, verify
  - `schedule_service.py` — schedule CRUD, run, advance
  - `simulation_service.py` — auto-simulation loop, scenario builders
- [ ] **M8.3** Move Pydantic models to `app/models.py` (already exists, populate it)
- [ ] **M8.4** Ensure `app/state.py` is the single source of truth for runtime state
- [ ] **M8.5** Add proper `auth.py` dependency injection on ALL routes (currently some skip auth)
- [ ] **M8.6** Add admin endpoints: scenario trigger, simulation toggle, dead-letter list/replay
- [ ] **M8.7** Add tests for all new route modules

### Phase 9 — Coordinator + Action Engine Integration (Week 2-3) 🔴 P0
**Goal**: Chat can actually execute payments/bills/rent through the action engine.

- [ ] **M9.1** Wire coordinator graph to route "pay_*", "transfer_*" intents through `chat_action_executor.py`
- [ ] **M9.2** Add intent detection in coordinator for action requests (approve/reject/status)
- [ ] **M9.3** Implement `_plan_action_engine_action` in CommunicationAgent to emit proper `response_metadata.action`
- [ ] **M9.4** Add conversation state machine in chat for multi-step flows:
  - "I want to pay rent" → discover bills → show candidates → "pay this one" → create action request → "approve" → execute
- [ ] **M9.5** Wire action execution webhook handling end-to-end (MockBank → Backend webhook → execution ledger update)
- [ ] **M9.6** Add idempotency key propagation through full chain (chat → action request → execution → MockBank trigger)
- [ ] **M9.7** Tests: chat-to-execution E2E for pay_bill, pay_rent, transfer_savings

### Phase 10 — Frontend Wiring: Bills, Planning, Actions (Week 3-4) 🔴 P0
**Goal**: Users can act on discovered bills and plans from the UI.

- [ ] **M10.1** Add "Pay Now" button to Bills.tsx that creates action request
- [ ] **M10.2** Add action approval/rejection UI (modal or inline)
- [ ] **M10.3** Add action execution status tracking UI (queued → running → success/failure)
- [ ] **M10.4** Add "New Goal" form to Planning.tsx wired to POST /api/planning/plans
- [ ] **M10.5** Add recurring rule creation UI in Planning page
- [ ] **M10.6** Add checklist item status toggle in Planning (mark done/pending)
- [ ] **M10.7** Add notification bell/badge in UserLayout header wired to GET /api/notifications
- [ ] **M10.8** Add notification mark-read on click

### Phase 11 — Frontend: Beneficiaries + Schedules (Week 4-5) 🔴 P0
**Goal**: Users can manage beneficiaries and bank schedules.

- [ ] **M11.1** Create Beneficiaries page with list/add/delete
- [ ] **M11.2** Add beneficiary verification flow (trigger verify, show cooldown)
- [ ] **M11.3** Add beneficiary selection in payment/action flows
- [ ] **M11.4** Create Schedules page with list/create/cancel/run-now
- [ ] **M11.5** Add settlement window display per schedule
- [ ] **M11.6** Wire schedule creation from Bills discovery ("Make this recurring")

### Phase 12 — Frontend: Payments + Auto-Savings (Week 5-6) 🔴 P0
**Goal**: Complete payment and savings flows.

- [ ] **M12.1** Create Payment page with one-time payment form (beneficiary + amount + method + MPIN)
- [ ] **M12.2** Create Recurring Payments management page (list/pause/resume/delete)
- [ ] **M12.3** Add payment history view
- [ ] **M12.4** Wire Auto-Savings recommendation to Dashboard widget
- [ ] **M12.5** Add "Save ₹X now" button on Dashboard
- [ ] **M12.6** Add MPIN setup/change flow in Settings (wire MPINSetup component properly)

### Phase 13 — Alembic Migrations + DB Hardening (Week 6) 🟡 P1
**Goal**: Production-ready schema management.

- [ ] **M13.1** Generate initial Alembic migration from current SQLAlchemy models
- [ ] **M13.2** Add migration for any missing columns (telegram_user_id, etc.)
- [ ] **M13.3** Test upgrade → downgrade → upgrade cycle
- [ ] **M13.4** Set `DB_SCHEMA_MODE=alembic` as default for production
- [ ] **M13.5** Add migration CI check in GitHub Actions

### Phase 14 — MockBank Data Persistence (Week 6-7) 🟡 P1
**Goal**: Survive restarts without data loss.

- [ ] **M14.1** Add Postgres table for transactions with full schema
- [ ] **M14.2** Add Postgres table for balances
- [ ] **M14.3** Add Postgres table for accounts
- [ ] **M14.4** Add Postgres table for transaction_lifecycle events
- [ ] **M14.5** Add Postgres table for idempotent trigger responses
- [ ] **M14.6** Write migration script from in-memory → Postgres on startup
- [ ] **M14.7** Add Postgres-backed seed data for 100+ users

### Phase 15 — Overdue Escalation + Reminder Hardening (Week 7) 🟡 P1
**Goal**: Complete the reminder lifecycle.

- [ ] **M15.1** Implement overdue detection in reminder worker (D+1, D+3, D+7)
- [ ] **M15.2** Add escalation levels: reminder → warning → critical
- [ ] **M15.3** Add Telegram push for overdue items
- [ ] **M15.4** Add admin alert for critical overdue patterns
- [ ] **M15.5** Add snooze-aware overdue logic (don't escalate snoozed items)

### Phase 16 — Admin Simulation + Full Admin Panel (Week 7-8) 🟡 P1
**Goal**: Admin can fully manage the system.

- [ ] **M16.1** Add MockBank admin endpoints (scenario, simulation toggle, dead-letters)
- [ ] **M16.2** Wire backend admin proxy to MockBank admin endpoints
- [ ] **M16.3** Complete AdminSimulation.tsx (toggle, scenario dropdown, status)
- [ ] **M16.4** Add dead-letter detail view + replay confirmation
- [ ] **M16.5** Add simulation config panel (interval, max amount, categories, target users)

### Phase 17 — Telegram Outbound + Notifications Complete (Week 8) 🟢 P2
**Goal**: Complete Telegram integration.

- [ ] **M17.1** Add outbound reminder templates for Telegram
- [ ] **M17.2** Add outbound approval request messages via Telegram
- [ ] **M17.3** Add distress alert templates
- [ ] **M17.4** Wire Telegram alerts into reminder worker
- [ ] **M17.5** Add user preference for notification channel (web/telegram/both)

### Phase 18 — E2E Tests + Cross-Repo Integration Tests (Week 8-9) 🟢 P2
**Goal**: Prevent regressions across repo boundaries.

- [ ] **M18.1** Create cross-repo test suite in `tests/cross-repo/`
- [ ] **M18.2** E2E test: Register → Login → Create beneficiary → Pay bill → Verify execution
- [ ] **M18.3** E2E test: Chat → Discover bills → Approve → Execute → Webhook → Status update
- [ ] **M18.4** E2E test: Create recurring rule → Scheduler runs → Payment executes
- [ ] **M18.5** E2E test: Admin scenario trigger → Frontend sees transaction
- [ ] **M18.6** E2E test: Webhook failure → Dead letter → Admin replay → Success
- [ ] **M18.7** Add Playwright tests for critical frontend flows

### Phase 19 — Polish + Production Hardening (Week 9-10) 🟢 P2
**Goal**: Production-ready quality.

- [ ] **M19.1** Add structured JSON logging across all services
- [ ] **M19.2** Add request ID tracing (X-Request-ID header propagation)
- [ ] **M19.3** Add rate limiting on auth endpoints (login, register)
- [ ] **M19.4** Add health check endpoints with dependency status
- [ ] **M19.5** Add Docker Compose production profile
- [ ] **M19.6** Add startup order dependency (MockBank before Backend, Backend before Frontend)
- [ ] **M19.7** Performance audit: DB query optimization, N+1 detection
- [ ] **M19.8** Security audit: JWT expiry, CORS tightness, input validation coverage

---

## Dependency Graph

```
Phase 8 (MockBank Modularization)
  └─→ Phase 9 (Coordinator+Action Integration)
       └─→ Phase 10 (Frontend Bills/Planning/Actions)
            └─→ Phase 11 (Frontend Beneficiaries+Schedules)
                 └─→ Phase 12 (Frontend Payments+Savings)

Phase 8 ─→ Phase 13 (Alembic Migrations)
Phase 8 ─→ Phase 14 (MockBank Persistence)
Phase 8 ─→ Phase 16 (Admin Simulation)

Phase 9 ─→ Phase 15 (Overdue Escalation)
Phase 9 ─→ Phase 17 (Telegram Outbound)

Phase 12 ─→ Phase 18 (E2E Tests)
Phase 18 ─→ Phase 19 (Production Hardening)
```

---

## Quick Wins (Do Immediately)

These are standalone fixes that unblock multiple phases:

1. **Add MockBank admin endpoints** (`/admin/scenario`, `/admin/simulation/*`, `/admin/webhooks/*`) — unblocks Phase 16
2. **Generate Alembic initial migration** — unblocks Phase 13
3. **Add "Pay Now" to Bills.tsx** — unblocks Phase 10
4. **Create Beneficiaries page** — unblocks Phase 11
5. **Wire coordinator to chat_action_executor** — unblocks Phase 9

---

## Previous Phase Status (Historical)

### Phase 0 - Trust Boundary + Architecture Freeze ✅
- [x] Remove payload user identity dependency in chat and enforce auth-derived identity.
- [x] Add domain models for schedules, recurring rules, plans, checklist items, user profile.
- [x] Add domain models for approvals, execution logs, and idempotency records.
- [x] Define and publish one canonical action contract document.
- [ ] Move all schema changes to Alembic migration-only workflow. → **Moved to Phase 13**
- [x] Publish autonomy policy matrix with amount caps in product docs.

### Phase 1 - Action Engine ✅
- [x] Implement tool registry and executor.
- [x] Add approval workflow states: pending, approved, rejected, expired.
- [x] Add execution ledger states: queued, running, success, failure, rollback.
- [x] Add idempotency handling and replay-safe behavior.
- [ ] Integrate planner/executor tool path inside coordinator graph. → **Moved to Phase 9**
- [x] Add rollback state transitions for compensating actions.

### Phase 2 - Scheduler, Plans, Checklist System ✅
- [x] Create financial plan and checklist tracking APIs.
- [x] Add recurring templates and recurring rules.
- [x] Add schedule-from-text endpoint.
- [x] Add reminder cadence workers (D-3, D-1, due-day).
- [ ] Add overdue escalation workflow. → **Moved to Phase 15**
- [x] Add user monthly salary and persistent expense configuration.

### Phase 3 - Vector Analytics (Deferred)
- [ ] Enable pgvector embedding storage. → **Post-MVP**
- [ ] Build transaction embedding ingestion pipeline. → **Post-MVP**
- [ ] Add recurring pattern detection with deterministic + vector signals. → **Post-MVP**
- [ ] Add explainable recommendation scoring API. → **Post-MVP**

### Phase 4 - Distress Prediction + Mitigation (Deferred)
- [ ] Define distress score features and threshold policy. → **Post-MVP**
- [ ] Add mitigation playbooks and explainability payloads. → **Post-MVP**
- [ ] Backtest using transaction windows and adverse scenarios. → **Post-MVP**
- [ ] Enforce explicit confirmation for high-impact actions. → **Post-MVP**

### Phase 5 - MockBank Hardening ✅
- [x] Add transaction lifecycle states and reversals.
- [x] Add idempotency and signed webhooks.
- [x] Add settlement windows and bank-side schedule contracts.
- [x] Add webhook retry/dead-letter workflows and settlement reconciliation tooling.
- [ ] Move MockBank to PostgreSQL persistence. → **Moved to Phase 14**
- [ ] Add transfers, bill pay, rent pay, utility booking, scheduled payments. → **Done via action engine**
- [ ] Add fraud/distress simulation endpoints. → **Moved to Phase 16**
- [x] Publish India-first policy + plan catalogs in MockBank and enforce action/rail caps at transaction trigger.

### Phase 6 - Telegram Gateway ✅ (Partial)
- [x] Build Telegram adapter with policy-gated command execution.
- [x] Add secure account linking.
- [ ] Add outbound reminders/approvals/distress templates. → **Moved to Phase 17**
- [x] Remove WhatsApp runtime integration and Twilio dependency path.
- [x] Add MPIN secondary verification gate for sensitive Telegram intents.
- [x] Add anti-abuse controls baseline (MPIN attempt limits + lockout).

### Phase 7 - Scale + Reliability (Deferred)
- [ ] Add workers for recurring jobs and heavy tasks. → **Post-MVP**
- [ ] Add metrics, tracing, structured logs. → **Moved to Phase 19**
- [ ] Define SLOs and run load tests. → **Post-MVP**
- [ ] Add failure-mode runbooks and release gates. → **Post-MVP**

---

## Completed Iterations

### Iteration A ✅
- Auth-scoped chat enforcement.
- Profile API with salary/persistent expenses.
- Planning APIs (plans, recurring rules, checklist materialization).
- Trusted recurring promotion after first completed payment.

### Iteration B ✅
- Action engine core (request + approve/reject + execution ledger).
- Policy checks and amount caps by action type.
- Idempotency records for request and execution scopes.
- Tool registry with note tool and bank transaction tool.

### Iteration C ✅
- MockBank is now the source of truth for action caps, payment rail policies, and bank plan catalogs.
- Backend action policy evaluation now resolves policy from MockBank with cached + resilient fallback behavior.
- Action execution sends action type + payment rail context to MockBank for consistent rail enforcement.
- Added insufficient-funds and policy-cap checks directly in MockBank transaction trigger path.

### Iteration D ✅
- MockBank transaction lifecycle now emits queued/running/success transitions and supports reversal operations.
- MockBank trigger endpoint now supports replay-safe idempotency keys.
- Signed webhook callbacks (HMAC) from MockBank are now delivered to backend action webhook endpoint.
- Backend webhook handler now updates execution status to success/failure/rollback from bank lifecycle events.

### Iteration E ✅
- Added client-bank beneficiary lifecycle endpoints in MockBank (create/list/verify).
- Enforced NEFT and RTGS beneficiary verification + cooldown in MockBank policy validation.
- Added backend beneficiary proxy routes and beneficiary_id pass-through in action execution payloads.
- Added MockBank schedule endpoints (create/list/run/cancel) with idempotent schedule-run execution.
- Added settlement-window contracts and settlement status metadata on transactions.
- Added backend bank-schedule proxy routes and banking client methods for schedules + settlement windows.

### Iteration F ✅
- Added webhook retry logic in MockBank delivery pipeline with configurable attempts and backoff.
- Added dead-letter queue storage + admin replay endpoints in MockBank.
- Added backend execution reconciliation endpoint that maps MockBank lifecycle status back into local execution ledger state.
- Added cross-repo tests for dead-letter replay and reconciliation paths.
- Extracted action request lifecycle logic into application services so workers and chat flows no longer call FastAPI route functions directly.
- Extracted planning and checklist mutation logic into application services and slimmed the planning routes to HTTP wrappers.
- Hardened auth registration user ID generation to avoid count-based collisions in long-lived test/dev databases.

### Iteration G ✅
- Added backend bills discovery endpoint with frontend wiring for bill discovery UI.
- Added admin webhooks proxy endpoints and frontend wiring for dead-letter replay.
- Implemented snooze-aware reminder worker with scheduled cadence.
- Added notification dedupe keys to avoid duplicate reminder noise.
- Added mockbank pytest coverage for admin webhooks replay and beneficiary cooldown.

---

## Next Up (Priority Order)
1. **Phase 8**: MockBank route modularization + admin endpoints (unblocks everything)
2. **Phase 9**: Coordinator + action engine integration in chat
3. **Phase 10**: Frontend Bills/Planning/Actions wiring
4. **Phase 11**: Frontend Beneficiaries + Schedules pages
5. **Phase 12**: Frontend Payments + Auto-Savings pages
6. **Phase 13**: Alembic migrations
7. **Phase 14**: MockBank Postgres persistence for transactions
8. **Phase 15**: Overdue escalation
9. **Phase 16**: Admin simulation panel
10. **Phase 17**: Telegram outbound
11. **Phase 18**: Cross-repo E2E tests
12. **Phase 19**: Production hardening
