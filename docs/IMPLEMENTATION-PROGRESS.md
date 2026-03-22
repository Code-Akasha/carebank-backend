# CareBank Autonomous Banking Progress Tracker

Last updated: 2026-03-15

## Current Build Objective
Build a policy-governed action platform with hybrid autonomy (first approval, then trusted recurring auto-execution), India-first constraints, and strong auditability.

## Phase Status

### Phase 0 - Trust Boundary + Architecture Freeze (Week 1-2)
- [x] Remove payload user identity dependency in chat and enforce auth-derived identity.
- [x] Add domain models for schedules, recurring rules, plans, checklist items, user profile.
- [x] Add domain models for approvals, execution logs, and idempotency records.
- [x] Define and publish one canonical action contract document.
- [ ] Move all schema changes to Alembic migration-only workflow.
- [x] Publish autonomy policy matrix with amount caps in product docs.

### Phase 1 - Action Engine (Week 2-5)
- [x] Implement tool registry and executor.
- [x] Add approval workflow states: pending, approved, rejected, expired.
- [x] Add execution ledger states: queued, running, success, failure, rollback.
- [x] Add idempotency handling and replay-safe behavior.
- [ ] Integrate planner/executor tool path inside coordinator graph.
- [x] Add rollback state transitions for compensating actions.

### Phase 2 - Scheduler, Plans, Checklist System (Week 3-6)
- [x] Create financial plan and checklist tracking APIs.
- [x] Add recurring templates and recurring rules.
- [x] Add schedule-from-text endpoint.
- [ ] Add reminder cadence workers (D-3, D-1, due-day).
- [ ] Add overdue escalation workflow.
- [x] Add user monthly salary and persistent expense configuration.

### Phase 3 - Vector Analytics (Week 4-8)
- [ ] Enable pgvector embedding storage.
- [ ] Build transaction embedding ingestion pipeline.
- [ ] Add recurring pattern detection with deterministic + vector signals.
- [ ] Add explainable recommendation scoring API.

### Phase 4 - Distress Prediction + Mitigation (Week 6-10)
- [ ] Define distress score features and threshold policy.
- [ ] Add mitigation playbooks and explainability payloads.
- [ ] Backtest using transaction windows and adverse scenarios.
- [ ] Enforce explicit confirmation for high-impact actions.

### Phase 5 - MockBank Hardening (Week 2-9)
- [ ] Move MockBank to PostgreSQL persistence.
- [ ] Add transfers, bill pay, rent pay, utility booking, scheduled payments.
- [x] Add transaction lifecycle states and reversals.
- [x] Add idempotency and signed webhooks.
- [x] Add settlement windows and bank-side schedule contracts.
- [x] Add webhook retry/dead-letter workflows and settlement reconciliation tooling.
- [ ] Add fraud/distress simulation endpoints.
- [x] Publish India-first policy + plan catalogs in MockBank and enforce action/rail caps at transaction trigger.

### Phase 6 - Telegram Gateway (Week 8-11)
- [ ] Build Telegram adapter with policy-gated command execution.
- [ ] Add secure account linking.
- [ ] Add outbound reminders/approvals/distress templates.
- [ ] Add anti-abuse controls and complete audit logs.

### Phase 7 - Scale + Reliability (Week 10-14)
- [ ] Add workers for recurring jobs and heavy tasks.
- [ ] Add metrics, tracing, structured logs.
- [ ] Define SLOs and run load tests.
- [ ] Add failure-mode runbooks and release gates.

## Current Iteration Log

### Iteration A (Completed)
- Auth-scoped chat enforcement.
- Profile API with salary/persistent expenses.
- Planning APIs (plans, recurring rules, checklist materialization).
- Trusted recurring promotion after first completed payment.

### Iteration B (Completed)
- Action engine core (request + approve/reject + execution ledger).
- Policy checks and amount caps by action type.
- Idempotency records for request and execution scopes.
- Tool registry with note tool and bank transaction tool.

### Iteration C (Completed)
- MockBank is now the source of truth for action caps, payment rail policies, and bank plan catalogs.
- Backend action policy evaluation now resolves policy from MockBank with cached + resilient fallback behavior.
- Action execution sends action type + payment rail context to MockBank for consistent rail enforcement.
- Added insufficient-funds and policy-cap checks directly in MockBank transaction trigger path.

### Iteration D (Completed)
- MockBank transaction lifecycle now emits queued/running/success transitions and supports reversal operations.
- MockBank trigger endpoint now supports replay-safe idempotency keys.
- Signed webhook callbacks (HMAC) from MockBank are now delivered to backend action webhook endpoint.
- Backend webhook handler now updates execution status to success/failure/rollback from bank lifecycle events.

### Iteration E (Completed)
- Added client-bank beneficiary lifecycle endpoints in MockBank (create/list/verify).
- Enforced NEFT and RTGS beneficiary verification + cooldown in MockBank policy validation.
- Added backend beneficiary proxy routes and beneficiary_id pass-through in action execution payloads.
- Added MockBank schedule endpoints (create/list/run/cancel) with idempotent schedule-run execution.
- Added settlement-window contracts and settlement status metadata on transactions.
- Added backend bank-schedule proxy routes and banking client methods for schedules + settlement windows.

### Iteration F (In Progress)
- Added webhook retry logic in MockBank delivery pipeline with configurable attempts and backoff.
- Added dead-letter queue storage + admin replay endpoints in MockBank.
- Added backend execution reconciliation endpoint that maps MockBank lifecycle status back into local execution ledger state.
- Added cross-repo tests for dead-letter replay and reconciliation paths.
- Extracted action request lifecycle logic into application services so workers and chat flows no longer call FastAPI route functions directly.
- Extracted planning and checklist mutation logic into application services and slimmed the planning routes to HTTP wrappers.
- Hardened auth registration user ID generation to avoid count-based collisions in long-lived test/dev databases.

## Next Up
1. Coordinator integration with planner/executor tool actions.
2. Reminder worker service and overdue escalation.
3. Alembic migrations for all newly added tables.
4. Postgres persistence for MockBank schedules, beneficiaries, and webhook dead-letter records.
