# Phase 5: Autonomy Execution + Reminder Workers + Migrations + MockBank Persistence

## Goal
Close the “Next Up” gaps: run planner/executor tool actions inside the coordinator pipeline (so compliance + auditability cover the final response), add reminder cadence + overdue escalation tied to recurring rules, establish Alembic migrations for production schema management, and add optional PostgreSQL persistence to MockBank for schedules/beneficiaries/dead-letters.

## Tasks
- [ ] **Coordinator tool execution in-graph**: Add an `apply_actions` node that executes planned chat actions when `db` + `current_user` are provided; ensure compliance runs on the final post-action response. → Verify: `tests/test_planning_profile.py::test_chat_creates_schedule_directly` + `tests/test_communication.py` pass.
- [ ] **Centralize chat action execution**: Move the chat “planned action” executor into a reusable service module (used by graph + routes) to avoid duplication and keep routes thin. → Verify: chat endpoint behavior unchanged.
- [ ] **Reminder cadence + overdue escalation**: Implement a worker service that (a) materializes due checklist items, (b) emits D-3/D-1/D0 reminders, (c) escalates overdue items, and (d) creates policy-governed action requests on due-day for autopay rules (pending vs auto-approved trusted recurring). → Verify: new unit tests cover reminder creation + idempotency.
- [ ] **Notifications persistence (minimal)**: Add a lightweight notification/event table and API for listing/marking read so reminder workers have a durable output sink. → Verify: create/list/read flows via FastAPI client.
- [ ] **Alembic baseline + toggle**: Fix `alembic/env.py` model imports, add an initial baseline migration, and introduce a config toggle to use Alembic in production while keeping `create_all` for tests/dev. → Verify: `python -m alembic upgrade head` works on an empty DB.
- [ ] **MockBank PostgreSQL persistence (optional, non-breaking)**: Add DB-backed storage for beneficiaries/schedules/webhook dead-letters when `MOCKBANK_DATABASE_URL` is set; fallback to in-memory storage otherwise. → Verify: `carebank-mockbank/test_endpoints.py` still passes without DB; basic persistence works with DB configured.

## Done When
- [ ] Coordinator executes planned actions in the graph and compliance validates the final message.
- [ ] Reminder worker produces reminders + due-day action requests without duplicates.
- [ ] Alembic can reproduce schema from scratch; production can run without `create_all`.
- [ ] MockBank supports durable schedules/beneficiaries/dead-letters under Postgres.
