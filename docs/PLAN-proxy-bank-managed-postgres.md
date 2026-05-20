# Proxy Bank Managed PostgreSQL Plan

## Goal
- Move the agentic proxy bank off local sqlite so its state survives container restarts.
- Reuse the existing Azure PostgreSQL managed service used by CareBank where possible.

## Scope
1. Add PostgreSQL-backed storage support to `carebank-agentic-bank` with sqlite fallback for local development.
2. Prefer `PROXY_DATABASE_URL`, then `DATABASE_URL`, before falling back to `PROXY_DB_PATH`.
3. Keep the current storage API stable so routes and state helpers do not need behavioral changes.
4. Verify the backend Azure PostgreSQL server can host the proxy bank database, and only clean data after the target database is confirmed.

## Validation
- Run a focused import / unit check for the proxy bank storage module.
- Confirm the selected Azure PostgreSQL resource before any destructive cleanup.