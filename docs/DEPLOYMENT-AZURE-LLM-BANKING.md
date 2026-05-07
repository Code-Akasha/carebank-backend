# Azure Deployment Guide

This guide covers the recommended Azure setup for hosting the CareBank backend and frontend while keeping LLM inference and optional banking mock providers externally reachable through admin-managed connectors.

## Recommended Azure Size

- **Default recommendation**: `Standard B2s` Linux VM
  - 2 vCPU
  - 4 GiB RAM
  - Best fit for Dockerized FastAPI + frontend + reverse proxy + Redis/Postgres for a student-budget environment
- **Minimum dev-only option**: `Standard B1ms`
  - Works for light testing
  - Not ideal for shared use, longer sessions, or running extra services

If you need one machine for everything, pick `B2s`. If you are very credit-constrained and only testing alone, start with `B1ms` and move up quickly.

## What To Host On Azure

Host these services in Azure:

- Backend API
- Frontend static build or frontend container
- PostgreSQL
- Redis
- Optional reverse proxy such as Nginx or Caddy

Do **not** host local Ollama on Azure for this design. Ollama stays on your local machine and is reached from the backend through the admin-configured secure tunnel.

The same applies to the mock banking provider: keep it modular. The backend now supports an admin-managed banking connector so you can point it at:

- a local mock banking container exposed through a tunnel
- a remote mock banking service
- another banking API that matches the same contract

## Deployment Model

Use one of these two options:

### Option 1: Single VM, Docker Compose

Best for quick student deployment.

Run on the VM:

- backend container
- frontend container or a build served by Nginx
- postgres container
- redis container

Use the admin panel to configure:

- Ollama tunnel URL
- Ollama default model
- banking connector base URL
- banking connector secret

### Option 2: Azure App Service + External Data Services

Use this if you want fewer VM ops tasks.

- Backend on App Service
- Frontend on Static Web Apps or App Service
- PostgreSQL in Azure Database for PostgreSQL
- Redis in Azure Cache for Redis

This is cleaner operationally, but the VM approach is usually easier for students.

## Required Environment Variables

Backend:

- `DATABASE_URL` or the individual `DB_*` variables
- `REDIS_URL`
- `BANKING_API_URL` and `BANKING_API_SECRET` as fallback values
- `JWT_SECRET`
- `OLLAMA_BASE_URL` and `OLLAMA_MODEL` as fallback values
- `GEMINI_API_KEY` only if you want cloud fallback
- `CORS_ORIGINS` including the frontend URL
- `ENVIRONMENT=production`
- `DB_SCHEMA_MODE=alembic`

Frontend:

- `VITE_API_BASE_URL` pointing at the backend API URL

## How The Admin Connectors Work

### LLM Connector

1. Admin saves the tunnel URL and token in the backend admin panel.
2. Backend stores the secret encrypted at rest.
3. Backend resolves that runtime config before falling back to env vars.
4. Admin can test model discovery and prompt updates without redeploying.

### Banking Connector

1. Admin saves the banking mock/API base URL and secret in the backend admin panel.
2. Backend stores the secret encrypted at rest.
3. `BankingClient` resolves the DB config before env vars.
4. Provider, account, beneficiary, schedule, and transaction reads all flow through the same client abstraction.

## Suggested VM Setup

On the Azure VM:

1. Install Ubuntu 22.04 LTS.
2. Install Docker and Docker Compose plugin.
3. Clone the backend and frontend repositories.
4. Create production `.env` files.
5. Bring up the stack with Docker Compose.
6. Set up a reverse proxy for the frontend and backend.
7. Open only ports 80 and 443 publicly.

Recommended internal service exposure:

- backend: internal only, reverse proxied
- frontend: internal only, reverse proxied
- postgres/redis: internal only

## Startup Order

1. Database
2. Redis
3. Backend
4. Frontend
5. Reverse proxy

If you keep the frontend static, it can be served by the proxy immediately after the frontend build is present.

## Validation Checklist

After deployment, verify:

1. Login works.
2. `/health` or home route returns successfully.
3. Admin panel opens.
4. LLM tunnel config can be saved.
5. Ollama model listing works through the tunnel.
6. Banking connector can be saved.
7. Banking provider/account/transaction reads work through the configured mock provider.
8. Restarting the VM does not lose admin config because it is stored in the database.

## Local Ollama And Mock Provider Flow

Suggested workflow:

1. Run Ollama locally on your machine.
2. Expose it through ngrok or another secure tunnel.
3. Save that URL in the admin panel.
4. Run your mock banking provider locally or remotely.
5. Save that URL in the banking proxy tab.
6. Use the admin test buttons to confirm both connectors are reachable.

## Notes

- Keep `BANKING_API_SECRET` and the Ollama tunnel token out of source control.
- Prefer Azure Key Vault for longer-term hardening, but encrypted-at-rest DB storage is already supported in the current implementation.
- The recommended instance size is `B2s` because it is the smallest practical size that leaves enough room for Docker, logs, admin usage, and future growth.