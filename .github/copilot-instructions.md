# CareBank Backend Project Guidelines

## Scope
- This file applies to work inside the carebank-backend repository.
- Use .agent as the primary project context source.
- Before implementation, check relevant phase plans in .agent/project/plans/backend/.
- If a phase plan does not exist, create a new plan first under .agent/project/plans/backend/.

## Architecture
- Keep domain boundaries clear:
  - app/routes: HTTP layer only, keep handlers thin.
  - app/services: business logic, orchestration, external integration.
  - app/agents: coordinator and specialist agent behavior.
  - app/core: deterministic calculations, config, DB/session setup.
  - app/compliance: safety and policy checks.
- Preserve user isolation across flows: authenticated user_id context must propagate to all downstream actions.
- Align with .agent/project/SOLUTION.md and docs/ACTION-ENGINE-CONTRACT.md for agent roles, action lifecycle, and policy expectations.
- Do not introduce architecture that conflicts with the existing 5 core agents and deterministic-core-plus-compliance approach.

## Build And Test
- Prefer the repository virtual environment for all Python commands:
  - .venv\Scripts\python.exe -m pip install -r requirements.txt
  - .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  - .venv\Scripts\python.exe -m pytest
- Use pytest markers from pytest.ini for selective runs:
  - .venv\Scripts\python.exe -m pytest -m unit
  - .venv\Scripts\python.exe -m pytest -m integration
- Lint with Ruff when touching Python code:
  - .venv\Scripts\ruff.exe check .
- For full local stack startup (backend + mockbank + frontend), use startup.bat from repo root.

## Conventions
- Keep financial math deterministic and out of LLM paths.
- Use Pydantic schemas in app/schemas for API contracts; avoid ad hoc dict payload contracts in routes.
- Keep route functions focused on validation and response shaping; move branching logic to services.
- For SQLAlchemy JSON columns, avoid in-place mutation. Reassign a new dict object so updates are persisted reliably.
- When adding new SQLAlchemy models, ensure they are imported by app/core/database.py init_db path so table creation and migrations remain consistent.
- Keep environment-driven config in app/core/config.py; avoid hardcoded endpoints, secrets, or credentials.

## Primary References
- .agent/project/PROJECT-CONFIG.md
- .agent/project/SOLUTION.md
- .agent/project/plans/README.md
- docs/ACTION-ENGINE-CONTRACT.md
