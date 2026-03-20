# Phase 1 Add-on: Coordinator ↔ Action Engine Integration

> Status: IN PROGRESS

## Goal
Enable chat/coordinator to create policy-checked `ActionRequest`s, collect user approvals, and trigger execution via the existing action engine + tool registry.

## Constraints / Principles
- Keep routes thin; use existing action engine contract and deterministic parsing.
- Preserve user isolation: authenticated `user_id` must flow to all requests/executions.
- Do **not** execute money-moving actions without explicit approval unless policy allows (trusted recurring / requires_approval=false).
- Avoid LLM hallucinations for action payloads; use deterministic extraction (amount/type) and explicit user confirmation.

## Scope (MVP)
- Action types supported via chat:
  - `pay_rent`, `pay_bill`, `pay_gas`, `pay_utility`, `transfer_savings`, `record_note`
- Multi-turn flows:
  - Missing details (e.g., amount) → ask follow-up and store pending state
  - Pending approval → "yes" approves, "no" rejects

## Implementation Tasks
1. Coordinator routing
   - Add `actions` intent code routed to `CommunicationAgent`.
   - Add deterministic detection for tool-action requests (pay/transfer) that overrides LLM routing.
   - Add pending-intent resume guard for `actions` so stale state doesn’t hijack unrelated queries.

2. CommunicationAgent planning
   - Add deterministic planner for action-engine flows:
     - derive `action_type` + payload
     - emit `metadata.action` instructions for chat route to execute
     - emit `pending_state` for multi-turn capture and approvals

3. Chat route execution
   - Extend `/api/chat` post-processing to execute `metadata.action`:
     - create action request
     - approve/reject pending action request
   - Update conversation pending state based on request status.

4. Tests
   - Unit tests for `CommunicationAgent` action planner.
   - Integration test for `/api/chat` create→approve flow (mock tool execution).

## Done When
- A message like "transfer 5000 to savings" creates a pending `ActionRequest` and prompts approval.
- A follow-up "yes" approves and executes; "no" rejects.
- Stale pending action state does not hijack unrelated queries.
- Tests cover create/prompt/approve path and pass in CI.
