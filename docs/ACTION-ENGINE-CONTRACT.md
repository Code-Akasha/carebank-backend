# Action Engine Contract (Phase 1)

Last updated: 2026-03-14

## Purpose
Define a single contract for executable actions in CareBank with policy checks, approval flow, idempotency, and auditable execution states.

## Action Request Contract

Endpoint: POST /api/actions/requests

Request payload:
- action_type: string
- action_payload: object
- idempotency_key: optional string
- expires_in_hours: optional int (default 24)

Validation:
- Action type must be supported by policy matrix.
- Amount must be positive if present.
- Amount must be below action cap for the type.

Policy output:
- allowed: bool
- requires_approval: bool
- reason: string
- max_amount: number or null
- trusted_recurring: bool

## Approval State Machine

Statuses:
- pending
- approved
- rejected
- expired

Transitions:
- pending -> approved (user approval)
- pending -> rejected (user rejection)
- pending -> expired (timeout reached)
- approved -> approved (idempotent read)

Notes:
- Trusted recurring rules may auto-approve requests based on policy.

## Execution Ledger State Machine

Statuses:
- queued
- running
- success
- failure
- rollback

Transitions:
- queued -> running
- running -> success
- running -> failure
- failure -> rollback (for future compensating flow)

## Banking Provider Lifecycle (MockBank)

MockBank emits transaction lifecycle webhooks to `/api/actions/webhooks/mockbank`.

Lifecycle statuses (webhook `status` field):
- queued
- running
- pending_settlement (deferred rails like NEFT)
- success
- failure
- reversed

Settlement fields included in webhook payload:
- settlement_status: `pending` | `cleared`
- settlement_due_at: ISO timestamp (UTC)

Notes:
- UPI settles immediately (T+0) and skips `pending_settlement`.
- NEFT may emit `pending_settlement` and later `success` once settlement clears.
- Webhook signatures are verified using `MOCKBANK_WEBHOOK_SECRET`.

## Idempotency Rules

Scope keys:
- action_request
- execution

Behavior:
- Same idempotency key + same payload => replay original result.
- Same idempotency key + different payload => conflict (HTTP 409).
- Execution scope stores execution_id and status for replay-safe returns.

## Tool Execution Interface

Tool responsibilities:
- can_handle(action_type) -> bool
- execute(user_id, action_type, payload) -> dict

Current tools:
- NoteTool: deterministic local event tool
- BankTransactionTool: transaction trigger via banking client

## Hybrid Autonomy Rule

- First recurring payment normally requires explicit approval.
- After successful completion, recurring rule is promoted to trusted_recurring.
- Trusted recurring actions can bypass approval if policy allows.

## Auditability Requirements

Persist and expose:
- action request payload and policy snapshot
- decision timestamp and reason
- execution attempts, error messages, and result payload
- idempotency status and replay linkage

## Open Work
- Integrate coordinator planner/executor graph with this contract.
- Add explicit rollback handlers for compensating transactions.
- Bind reminders and scheduler workers to action requests and execution outcomes.
- Add Alembic migrations to manage schema changes in production.
