# PLAN: Backend Production Upgrade

## Overview
Upgrade the CareBank backend infrastructure to support 100+ parallel users securely and efficiently. This plan implements mandatory JWT authentication for strict session isolation, an async Task Queue/Worker Pool to offload heavy LLM/Inference calculations, and an Event Logger for Admin Observability. 

## Project Type
**BACKEND**

## Success Criteria
- [ ] JWT generation and validation endpoints are functional.
- [ ] `user_id` context is securely extracted from the token and used to isolate LangGraph sessions, vector storage, and DB calls.
- [ ] LLM requests and Prophet forecasts are executed asynchronously via a Background Task Queue (Celery + Redis or FastAPI Background Tasks).
- [ ] An `AgentLogs` / immutable event ledger captures every agent decision, trigger, and compliance check.
- [ ] Admin API exposes live system health, user risks, active sessions, and paginated logs.

## Tech Stack
- **FastAPI** (Core API)
- **JWT / passlib** (Auth Layer)
- **LangGraph** (Isolated Agent Memory scoped by user_id)
- **Celery + Redis** (Asynchronous task execution to avoid HTTP blocking)
- **PostgreSQL / SQLAlchemy** (Added `AgentLogs` and `User` schema)

## File Structure Additions
```text
app/
├── auth/          # JWT issuing, validation, and token dependencies
├── worker/        # Celery background tasks or message queue consumers
├── admin/         # Admin API endpoints and system health metrics
└── models/
    └── log.py     # Immutable event ledger model
```

## Task Breakdown

### 1. Implement JWT Authentication Layer
- **Agent:** `security-auditor`
- **Skills:** `api-patterns`
- **Priority:** P0
- **INPUT:** `app/main.py`, new `app/auth/`
- **OUTPUT:** Login route (`/auth/login`), JWT signing mechanisms, and a `get_current_user` dependency.
- **VERIFY:** Requests to endpoints without a valid token return `401 Unauthorized`.

### 2. Isolate Coordinator Agent State
- **Agent:** `backend-specialist`
- **Priority:** P0
- **Dependencies:** Task 1
- **INPUT:** `app/coordinator/`
- **OUTPUT:** LangGraph thread contexts securely coupled strictly to the `user_id` provided by the authorized current user.
- **VERIFY:** Requests belonging to `user_id_A` cannot access or leak conversation memory of `user_id_B`.

### 3. Implement Task Queue / Worker Pool
- **Agent:** `backend-specialist`
- **Skills:** `performance-profiling`
- **Priority:** P1
- **INPUT:** `app/agents/intelligence`, `app/agents/communication`
- **OUTPUT:** Refactor heavy endpoints or internal calls to dispatch work to a celery queue. The Coordinator will await or poll for results.
- **VERIFY:** Simulating 50 concurrent large forecast requests does not freeze the FastAPI synchronous event loop.

### 4. Implement Event Logger & Admin DB Schema
- **Agent:** `database-architect`
- **Priority:** P1
- **INPUT:** `app/models/`
- **OUTPUT:** Database migration adding `AgentLog` storing `action_type`, `user_id`, `details`, `timestamp`, `latency`.
- **VERIFY:** Every agent nudges or compliance block inserts a row into the database.

### 5. Admin Observability Endpoints
- **Agent:** `backend-specialist`
- **Priority:** P1
- **Dependencies:** Task 4
- **INPUT:** `app/routers/`
- **OUTPUT:** `/admin/system/health`, `/admin/logs`, `/admin/users/risks` routes (protected by an Admin role/secret).
- **VERIFY:** Calling the endpoints returns the expected real-time metric aggregations.

## Phase X: Verification
- [ ] Lint: Pass `ruff check .`
- [ ] Setup: Redis Queue operates cleanly alongside Pub/Sub.
- [ ] Security: Verify JWT payload does not leak sensitive unencrypted data and requires signatures.
- [ ] Run: `pytest` over new worker, auth, and admin endpoints.
