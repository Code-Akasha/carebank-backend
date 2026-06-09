# CareBank Backend Project Guidelines

## Scope
- This file applies to work inside the carebank-backend repository.
- Use `.agent/ARCHITECTURE.md` for the local agent-system blueprint and `docs/` for implementation plans and contracts.
- Before implementation, check relevant phase plans in `docs/` (for example: `docs/PLAN-backend-production.md`, `docs/PLAN-backend-next-phase.md`).
- If a needed plan does not exist, create a new `docs/PLAN-*.md` file first, then implement.

## Architecture
- Keep domain boundaries clear:
  - `app/routes`: HTTP layer only; keep handlers thin.
  - `app/services`: business logic, orchestration, and external integration.
  - `app/agents`: coordinator and specialist agent behavior.
  - `app/core`: deterministic calculations, config, DB/session setup.
  - `app/compliance`: safety and policy checks.
- Preserve user isolation across flows: authenticated `user_id` context must propagate to all downstream actions.
- Align with `docs/ACTION-ENGINE-CONTRACT.md` and `docs/SYSTEM-ARCHITECTURE.md` for agent roles, action lifecycle, and policy expectations.
- Do not introduce architecture that conflicts with the existing 5 core agents and deterministic-core-plus-compliance approach.

## Build And Test
- Prefer the repository virtual environment for all Python commands:
  - `.venv\Scripts\python.exe -m pip install -r requirements.txt`
  - `.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
  - `.venv\Scripts\python.exe -m pytest`
- Use pytest markers from `pyproject.toml` for selective runs:
  - `.venv\Scripts\python.exe -m pytest -m unit`
  - `.venv\Scripts\python.exe -m pytest -m integration`
- Lint with Ruff when touching Python code:
  - `.venv\Scripts\ruff.exe check .`
- For full local stack startup (backend + mockbank + frontend), use `startup.bat` from repo root.

## Conventions
- Keep financial math deterministic and out of LLM paths.
- Use Pydantic schemas in `app/schemas` for API contracts; avoid ad hoc dict payload contracts in routes.
- Keep route functions focused on validation and response shaping; move branching logic to services.
- For SQLAlchemy JSON columns, avoid in-place mutation. Reassign a new dict object so updates are persisted reliably.
- When adding new SQLAlchemy models, ensure they are imported in `app/core/database.py` `init_db` path so table creation remains consistent.
- Keep environment-driven config in `app/core/config.py`; avoid hardcoded endpoints, secrets, or credentials.

## Primary References
- `.agent/ARCHITECTURE.md`
- `docs/ACTION-ENGINE-CONTRACT.md`
- `docs/SYSTEM-ARCHITECTURE.md`
- `docs/PLAN-backend-production.md`
- `docs/PLAN-backend-next-phase.md`
- `docs/IMPLEMENTATION-PROGRESS.md`
