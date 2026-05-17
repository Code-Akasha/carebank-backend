Architecture Document for
CareBank Platform

TABLE OF CONTENTS

1 INTRODUCTION
1.1 PURPOSE
1.2 SCOPE
1.3 DEFINITIONS, ACRONYMS AND ABBREVIATIONS
1.4 REFERENCES
2 ARCHITECTURAL GOALS AND CONSTRAINTS
2.1 REUSABILITY
2.2 SCALABILITY
2.3 CUSTOMIZABILITY
2.4 EXTENDIBILITY
2.5 USE OF EXISTING BUSINESS LOGIC
2.6 TIME TO MARKET
2.7 PORTABILITY
2.8 AVAILABILITY
2.9 PERFORMANCE
2.10 ANY OTHER CRITICAL GOALS APPLICABLE
3 PRODUCTIZATION ASSESSMENT
3.1 RE-USABLE COMPONENTS
3.2 ANALYZE ARCHITECTURAL FRAMEWORKS IN REPOSITORY
3.3 IDENTIFY AND ANALYZE OPEN SOURCE AND COTS PRODUCTS
4 SYSTEM ARCHITECTURE
4.1 OVERVIEW
4.2 LOGICAL/FUNCTIONAL VIEW
4.3 USE CASE VIEW
4.4 IMPLEMENTATION/SYSTEM VIEW
4.5 PROCESS/THREAD VIEW
4.6 DEPLOYMENT VIEW
5 GENERAL ARCHITECTURE FOR CORE TECHNICAL SERVICES
5.1 PERSISTENCE
5.2 INTER-PROCESS COMMUNICATION
5.3 AUTHENTICATION AND AUTHORIZATION
5.4 ERROR HANDLING
5.5 LOGGING
5.6 TRANSACTION MANAGEMENT
5.7 OTHER APPLICABLE TECHNICAL SERVICES
6 RISKS/LIMITATION
7 ALTERNATIVE SOLUTIONS CONSIDERED
APPENDIX
1. EXPECTED SOFTWARE RESPONSE
2. PERFORMANCE BOUNDS
3. IDENTIFICATION OF CRITICAL COMPONENTS
4. REVIEW COMMENTS ON ARCHITECTURAL POC
5. JUSTIFICATION OF CHANGES TO EXISTING ARCHITECTURE (OPTIONAL)

Document Revisions
Date        Version Description                          Author
2026-03-31  1.0     Initial CareBank architecture draft  Copilot

Document Approval
Virtusa Corporation and Client have reviewed this document and hereby agree that the contents herein are accurate. Any changes to this document must be communicated in writing and signed-off by both parties.

Signature  ____________________________  Date  __________  Name  ____________________________  Client  ____________________________
Signature  ____________________________  Date  __________  Name  ____________________________  Virtusa Corporation

1 Introduction

1.1 Purpose
This document provides a comprehensive architectural overview of the CareBank platform, using multiple architectural views to capture major design decisions, data flow, and operational constraints across the backend, frontend, and MockBank services.

1.2 Scope
In scope:
- CareBank backend (FastAPI) including the Coordinator Agent, specialized agents, deterministic core, compliance guard, action engine, planning and checklist services, and admin/observability endpoints.
- CareBank frontend (React + Vite) that integrates with backend APIs, JWT authentication, and optional SSE streaming.
- MockBank service (FastAPI or Mockoon) that simulates banking APIs, policies, schedules, beneficiaries, and transaction lifecycle webhooks.
- Shared data stores (Postgres with pgvector, Redis) and external LLM providers.

Out of scope:
- Production infrastructure automation beyond docker-compose and local dev wiring.
- Bank partner integrations beyond the MockBank simulation.
- Mobile clients.

1.3 Definitions, Acronyms and Abbreviations
- Action Engine: Policy-governed action request, approval, execution ledger, and idempotency system.
- Coordinator Agent: LangGraph-based orchestrator that routes intents to specialist agents.
- Deterministic Core: Non-LLM financial calculations for correctness and auditability.
- MockBank: Mock banking API used for transactions, products, policies, schedules, and webhooks.
- SSE: Server-Sent Events endpoint for streaming events to the frontend.
- JWT: JSON Web Token used for authentication and service-to-service calls.
- LLM: Large Language Model used for natural language classification and generation only.

1.4 References
- CareBank System Architecture: docs/SYSTEM-ARCHITECTURE.md
- Action Engine Contract: docs/ACTION-ENGINE-CONTRACT.md
- Backend Production Plan: docs/PLAN-backend-production.md
- Backend Next Phase Plan: docs/PLAN-backend-next-phase.md
- Implementation Progress: docs/IMPLEMENTATION-PROGRESS.md
- Solution Overview: ../.github-private/docs/SOLUTION-OVERVIEW.md
- Tech Stack: ../.github-private/docs/TECH-STACK.md
- System Container Diagram: ../.github-private/docs/ARCHITECTURE-DIAGRAMS/01-system-container.md
- Backend Layered Diagram: ../.github-private/docs/ARCHITECTURE-DIAGRAMS/02-backend-layered.md
- Action Engine Sequence: ../.github-private/docs/ARCHITECTURE-DIAGRAMS/03-action-engine-sequence.md
- Backend ER Model: ../.github-private/docs/ARCHITECTURE-DIAGRAMS/04-data-model-er.md

2 Architectural Goals and Constraints

2.1 Reusability
- Shared service contracts (actions, plans, schedules, checklists) are implemented in app/services and referenced by routes, workers, and agents.
- MockBank policy and action contracts are reused across backend action execution and reconciliation.

2.2 Scalability
- Stateless JWT auth enables horizontal API scaling without sticky sessions.
- Heavy inference or forecasting is scheduled for asynchronous execution (planned worker pool) to avoid blocking HTTP threads.

2.3 Customizability
- Agent orchestration allows swapping or extending agents with minimal changes to routing.
- Policy thresholds and action caps are externalized to MockBank policy endpoints and environment configuration.

2.4 Extendibility
- Action Engine contract allows adding new action types without changing core approval or execution logic.
- Planning and checklist systems are modeled as domain entities with recurring rules and schedule materialization.

2.5 Use of Existing Business Logic
- All financial math is consolidated in the deterministic core, reused by agents and services.
- Action execution logic is centralized in action services to avoid duplication across routes and workers.

2.6 Time to Market
- FastAPI, SQLAlchemy, and docker-compose enable rapid iteration and minimal infra setup.
- MockBank provides a stable simulated banking provider to decouple product work from partner APIs.

2.7 Portability
- Services are container-ready and can run on Windows, macOS, or Linux with Python 3.11+ and Node 18+.
- Data layer uses Postgres and Redis, both widely supported.

2.8 Availability
- Stateless auth and idempotent action execution improve resilience to retries and transient failures.
- Webhook replay and dead-letter workflows are part of MockBank hardening (in progress).

2.9 Performance
- Deterministic core ensures fast and predictable calculations.
- Redis Pub/Sub enables low-latency event streaming and SSE fanout.

2.10 Any Other Critical Goals Applicable
- Safety and correctness: LLMs never perform calculations; deterministic core owns financial math.
- Auditability: action requests, approvals, executions, and policy snapshots are persisted with idempotency guarantees.
- User isolation: authenticated user_id context is propagated across all services and agents.

3 Productization Assessment

3.1 Re-Usable Components
- Coordinator Agent orchestration and tool registry.
- Action Engine approval and execution ledger.
- Planning and checklist materialization services.
- Banking client abstraction for MockBank integration.

3.2 Analyze Architectural Frameworks in Repository
- LangGraph is used for multi-agent orchestration with explicit state isolation.
- FastAPI and SQLAlchemy provide service and data access patterns.
- Redis Pub/Sub is used for event streaming and notification dispatch.

3.3 Identify and Analyze Open Source and COTS Products
- Open source: FastAPI, SQLAlchemy, Alembic, Redis, pgvector, Prophet, scikit-learn.
- COTS/APIs: OpenAI GPT-4, Gemini, Ollama (optional local). Usage is constrained to NLG and classification.
- Risk note: LLM providers are optional dependencies; deterministic core is independent of them.

4 System Architecture

4.1 Overview
CareBank is a multi-service architecture with a React frontend, a FastAPI backend, and a MockBank API that simulates banking operations. The backend is layered into HTTP/API routes, orchestration agents, business services, compliance safety checks, and a data layer. All requests are authenticated using JWTs and are scoped to a user_id for isolation. The action engine provides policy-governed execution with approval flows and audit logging. Redis and Postgres provide the core data and event backbone, while LLM providers are used only for text tasks.

4.2 Logical/Functional View
Logical components:
- Frontend UI: user and admin interfaces with JWT auth and optional SSE subscription.
- Backend API: REST endpoints for chat, actions, planning, transactions, and admin views.
- Coordinator Agent: routes intents to Intelligence, Opportunity, AutoSavings, and Communication agents.
- Deterministic Core: financial math, health score, affordability checks.
- Compliance Guard: redaction, disclaimers, and audit policy enforcement.
- Action Engine: policy lookup, approval workflow, execution ledger, idempotency rules.
- MockBank: banking APIs, policies, schedules, beneficiaries, transaction lifecycle webhooks.
- Data stores: Postgres (relational + pgvector), Redis (cache, Pub/Sub, SSE).

4.3 Use Case View
Representative use cases:
- Live Transaction Nudge: ingest a new transaction, recalc forecast, update health score, and optionally notify the user.
- What-If Simulator: simulate a hypothetical spend and return deterministic balance outcomes with explanations.
- Auto-Micro-Savings: detect surplus cashflow, request approval, and execute savings transfer via the action engine.
- Action Approval: create action request, apply policy caps, approve or reject, and update execution status via webhook.
- Planning and Checklist: create financial plans, generate recurring rules, and materialize checklist items.

4.4 Implementation/System View
Key modules and directory boundaries:
- app/routes: HTTP layer only; validation and response shaping.
- app/agents: Coordinator and specialist agents.
- app/services: business logic, action execution, planning, banking clients, LLM adapters.
- app/compliance: safety checks, redaction, disclaimer injection.
- app/core: configuration, database session, deterministic math helpers.
- app/models: SQLAlchemy models for actions, plans, notifications, sessions, idempotency.
- app/schemas: Pydantic contracts for API boundaries.

4.5 Process/Thread View
- API requests are handled by FastAPI async endpoints.
- Agent orchestration runs in-process with LangGraph state scoped per user_id.
- Long-running inference and forecast tasks are planned for background workers (Celery + Redis or FastAPI tasks).
- Webhook callbacks update execution status and persist audit records.
- Redis Pub/Sub streams events to SSE subscribers.

4.6 Deployment View
- Local development uses docker-compose for Postgres and Redis and local FastAPI servers for backend and MockBank.
- Frontend runs on a Vite dev server and calls the backend over HTTPS/HTTP with JWT auth.
- Target deployment supports separate containers for backend API, workers, Postgres, Redis, and MockBank, with environment-driven configuration.

5 General Architecture for Core Technical Services

5.1 Persistence
- Primary store: Postgres with pgvector for structured and embedding data.
- Models include users, transactions, plans, recurring rules, checklist items, action requests/executions, idempotency, and audit logs.
- MockBank optionally uses Postgres for persistence and webhook dead-letter queues (planned).

5.2 Inter-Process Communication
- Redis Pub/Sub for event dispatch and SSE streaming.
- HTTP calls between backend and MockBank secured by service JWT.

5.3 Authentication and Authorization
- JWT auth for client to backend requests; user_id injected into all downstream calls.
- Service JWT for backend to MockBank requests with short expiry.
- Admin endpoints gated by role checks or admin secret dependencies.

5.4 Error Handling
- Idempotency records prevent duplicate action execution.
- Action engine tracks failed executions and supports rollback state transitions.
- Webhook signature verification ensures only trusted lifecycle updates are accepted.

5.5 Logging
- Audit logging for action decisions, policy snapshots, and execution results.
- Planned admin observability endpoints expose health metrics and logs.

5.6 Transaction Management
- Action engine manages approval and execution states: pending, approved, rejected, queued, running, success, failure, rollback.
- MockBank provides lifecycle events for settlement and reversal states.
- Deterministic core guards all calculations to ensure consistent results.

5.7 Other Applicable Technical Services
- Compliance guard enforces redaction and adds required disclosures.
- Planning and checklist services provide scheduling and reminder cadences.
- SSE stream endpoint pushes live events to the frontend.

6 Risks/Limitation
- LLM dependency availability and latency; mitigated by deterministic core for math and business rules.
- Incomplete worker pool integration could cause heavy requests to block HTTP threads.
- MockBank persistence and webhook dead-letter flows are still in progress.
- Policy enforcement correctness depends on MockBank policy data consistency.

7 Alternative Solutions Considered
- Kubernetes: rejected for early phase due to operational overhead.
- Fine-tuned LLMs: deferred in favor of reliable hosted APIs.
- Deep learning forecasting: rejected in favor of explainable Prophet forecasting.

Appendix

1. Expected Software Response
- Action requests return policy-compliant responses with appropriate approval state.
- Forecasting and calculations return deterministic outputs consistent with deterministic core.

2. Performance Bounds
- Target latency: sub-2s for lightweight chat intents; heavy forecasting should be offloaded to background tasks.
- SSE event delivery should be near real time when Redis Pub/Sub is active.

3. Identification of Critical Components
- Action engine (approval and execution ledger)
- Deterministic core financial math
- Auth user_id isolation and policy enforcement
- MockBank webhook reconciliation

4. Review Comments on Architectural POC
- Initial POC validated that multi-agent orchestration with deterministic core avoids LLM math errors.
- Action engine contract provides a stable integration path for future tools and policy enforcement.

5. Justification of Changes to Existing Architecture (Optional)
- Introduced action engine and approval workflows to enforce safe autonomy.
- Added compliance guard and deterministic core to guarantee safety and correctness.
