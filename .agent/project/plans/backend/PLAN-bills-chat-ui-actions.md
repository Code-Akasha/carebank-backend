# Plan: Bills UX in Chat (Discovery + Pay Now/Later Buttons)

> Status: PENDING

## Goal
When a user says things like **"pay my rent"** (or gas/utility/bill), the assistant should:
1. **Discover** any relevant pending/scheduled bills (from existing Planning + Action Engine data)
2. **Ask for disambiguation** when multiple matches exist (via chat selection)
3. **Offer buttons**: **Pay now** (creates an `ActionRequest` only; approval handled separately) and **Later** (snoozes suggestions)

Also support **adding bills** via chat by routing schedule-creation phrases into the existing planning flow.

## Constraints / Principles
- Reuse existing concepts (`RecurringRule`, `ChecklistItem`, `ActionRequest`) — do **not** introduce a new “Bill” domain entity.
- Deterministic execution of side effects:
  - DB access occurs in the existing `chat_action_executor` hook (`apply_planned_chat_action`).
- Preserve user isolation: always scope discovery + snoozes by authenticated `user_id`.
- Minimal UX:
  - Buttons only for **Pay now** / **Later**.
  - If multiple matches, ask user to choose via chat **before** showing buttons.

## Implementation Outline
1. **Chat response contract**
   - Extend `/api/chat` response model to include `ui_actions: [{label, message}]`.
   - Populate `ui_actions` from `response_metadata` produced by the coordinator.

2. **Coordinator routing fix (avoid misrouting "pay rent" into planning)**
   - Make schedule-signal detection require explicit scheduling language; remove overly-broad hints.

3. **Bill discovery execution (DB-backed)**
   - Add planned chat action: `discover_bills`.
   - Discovery sources:
     - Pending `ChecklistItem`s (due/overdue/soon) joined to `RecurringRule` when available.
     - Active `RecurringRule`s (scheduled upcoming) as fallback.
   - Exclude items currently snoozed.

4. **Multi-turn flow**
   - If multiple matches: store pending state `actions.flow=bill_picker` with a candidate list; ask user to reply `1/2/...`.
   - If exactly one match: store pending state `actions.flow=bill_suggestion` with that candidate and emit `ui_actions`.

5. **Later = snooze**
   - Add small persistence table (e.g. `BillSnooze`) keyed by `(user_id, source_type, source_id)` with `snoozed_until`.
   - Planned chat action `snooze_bill` updates/creates the snooze record.

6. **Frontend Chat UI**
   - Render `ui_actions` as buttons under the assistant message.
   - Clicking a button sends its `message` to `/api/chat` as a normal user turn.

7. **Tests**
   - Add/extend backend tests to cover: discover → buttons → pay now creates action request; later snoozes and suppresses.

## Done When
- `pay my rent` discovers scheduled/pending rent and returns `ui_actions`.
- Multiple matches triggers a text choice step (no buttons until chosen).
- Pay now creates an approval request (no auto-execution without approval).
- Later snoozes and suppresses re-suggestion until snooze expiry.
