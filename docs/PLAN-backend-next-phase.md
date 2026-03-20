# PLAN: Backend Next Phase Implementation (2026-03-19)

## Objective
Integrate planner/executor tool actions into the coordinator graph, enabling policy-governed autonomous execution and audit logging.

---

## Checklist

### 1. Coordinator Integration
- [ ] Update coordinator graph to call planner/executor tool actions for relevant intents
- [ ] Ensure tool registry is accessible from coordinator
- [ ] Validate action contract compliance for all tool executions
- [ ] Add audit logging for tool actions and results

### 2. Reminder Worker Service
- [ ] Build reminder cadence workers (D-3, D-1, due-day)
- [ ] Implement overdue escalation workflow for missed actions

### 3. Alembic Migrations
- [ ] Move all schema changes to Alembic migration-only workflow
- [ ] Ensure new domain tables (schedules, beneficiaries, webhook dead-letter) are covered

### 4. MockBank Postgres Persistence
- [ ] Add Postgres persistence for MockBank schedules, beneficiaries, and webhook dead-letter records

---

## Verification
- [ ] Unit/integration tests for coordinator tool actions
- [ ] Migration checks for new tables
- [ ] Audit log validation for tool executions
- [ ] PRs reference this plan and update IMPLEMENTATION-PROGRESS.md
