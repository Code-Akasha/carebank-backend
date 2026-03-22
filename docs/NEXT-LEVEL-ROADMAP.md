# CareBank Next-Level Roadmap

Last updated: 2026-03-21

## Goal
Move CareBank from a strong feature-rich prototype into a production-ready platform with a cleaner architecture, safer deployment posture, and faster development loop.

## Phase 1 - Engineering Baseline
- Make test collection and local setup deterministic.
- Remove import-time side effects that cause unrelated modules to fail during tests.
- Add graceful fallback behavior for optional orchestration dependencies.
- Publish one implementation-focused roadmap that maps recommendations to code changes.

Status:
- Completed on 2026-03-21.

### Phase 1 Deliverables
- Lazy package exports for `app.agents` and `app.routes` so imports only load what is needed.
- Coordinator graph fallback when `langgraph` is unavailable in a dev or CI environment.
- Baseline verification via targeted test runs and a documented starting point for follow-up refactors.

## Phase 2 - Service Boundaries
- Move business logic out of route handlers into reusable application services.
- Keep API routes thin and focused on request/response concerns.
- Decouple reminder, chat action, and action approval workflows from FastAPI route functions.

Status:
- In progress on 2026-03-22.
- Action request workflows now live in `app/services/action_request_service.py`.
- Planning workflows now live in `app/services/planning_service.py`.
- Reminder worker and chat action executor no longer depend on FastAPI route functions.

## Phase 3 - Durable Runtime State
- Replace in-memory conversation state with Redis-backed conversation and pending-intent storage.
- Formalize worker-driven execution for reminders, forecasting, and reconciliation.
- Add operational visibility: structured logs, metrics, tracing, and runbooks.

## Phase 4 - Production Data Discipline
- Finish Alembic-only schema management.
- Review model relationships, foreign keys, and indexes for action and planning flows.
- Tighten startup behavior so demo seeding and other environment helpers are explicit.

## Immediate Next Steps
1. Finish Phase 2 by adding focused service-layer tests and trimming remaining route duplication.
2. Introduce Redis-backed conversation state behind the existing store interface.
3. Move reminder and reconciliation execution behind a proper worker runtime.
