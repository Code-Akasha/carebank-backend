# Connectivity Audit Plan

## 1. Overview
The goal of this task is to coordinate multiple agents to connect the three repositories (`carebank-backend`, `carebank-mockbank`, and `carebank-frontend`), run them simultaneously, and audit the system against the 36-hour hackathon constraints outlined in `SOLUTION.md`. This will identify any unimplemented features, broken connections, or missing integrations.

## 2. Project Type
**FULL STACK (WEB + BACKEND)**

## 3. Success Criteria
* All three services start and communicate without CORS or connection refused errors.
* We can identify which of the 5 core agents (Coordinator, Intelligence, Communication, Opportunity, Auto-Savings) are fully functional versus stubbed.
* We can identify the status of the 3 killer features (Financial Health Score, What-If Simulator, Auto-Micro-Savings).
* A clear orchestration report is generated summarizing the gaps.

## 4. Tech Stack Context
* **Backend**: FastAPI (port 8000), connected to PostgreSQL and Redis.
* **MockBank**: FastAPI (port 8001), serving mock transactions.
* **Frontend**: React + Vite (port 5173).

## 5. File Structure
* `carebank-backend/`
* `carebank-mockbank/`
* `carebank-frontend/`

## 6. Task Breakdown

### Task 1: Start Services & Verify Connections
* **Agent**: `devops-engineer`
* **Skills**: `bash-linux`, `powershell-windows`, `server-management`
* **INPUT**: Three repositories with their respective startup scripts (`startup.bat` for backend/mockbank, `npm run dev` for frontend).
* **OUTPUT**: Services running on ports 8000, 8001, and 5173.
* **VERIFY**: Use `Invoke-WebRequest` or CLI tools to verify `/health` or base endpoints return 200 OK.

### Task 2: Backend Architecture & Agent Audit
* **Agent**: `backend-specialist`
* **Skills**: `python-patterns`, `api-patterns`
* **INPUT**: `carebank-backend/app/` and `carebank-mockbank/`.
* **OUTPUT**: A checklist of implemented vs missing backend components (the 5 agents, Celery workers, LangGraph integration).
* **VERIFY**: Cross-reference existing files in `app/agents/` and `app/routes/` with `SOLUTION.md`.

### Task 3: Frontend Feature Audit
* **Agent**: `frontend-specialist`
* **Skills**: `frontend-design`, `react-best-practices`
* **INPUT**: `carebank-frontend/src/`.
* **OUTPUT**: A checklist of implemented UI features (Dashboard, Health Score meter, Simulator UI, Admin Monitor).
* **VERIFY**: Cross-reference React components and API connection hooks with `SOLUTION.md`.

### Task 4: Synthesis & Reporting
* **Agent**: `orchestrator`
* **Skills**: `parallel-agents`
* **INPUT**: Findings from Tasks 1-3.
* **OUTPUT**: Unified Orchestration Report identifying exactly what is not implemented and what the next immediate development priorities should be.
* **VERIFY**: Report is clear, actionable, and aligns with the hackathon constraints.

## 7. Phase X: Verification
* [ ] Security check on API endpoints using `security_scan.py`
* [ ] Lint validation check
* [ ] End-to-end trace of a single mockbank API call flowing through the backend to the frontend.
