# PLAN: Backend Telegram-Only + MPIN Security Phase (2026-03-28)

## Objective
Replace WhatsApp integration with Telegram-only bot operations, enforce MPIN verification for sensitive Telegram intents (balance, score, money actions), and add Telegram spending usage alerts with dedupe controls.

## Checklist

### 1. Channel Cleanup
- [ ] Remove WhatsApp webhook/service implementation from backend runtime.
- [ ] Remove Twilio/WhatsApp settings from config contract.
- [ ] Add regression check ensuring `/bot/whatsapp/webhook` is unavailable.

### 2. MPIN Foundation
- [ ] Add MPIN persistence model with lockout metadata.
- [ ] Add MPIN service for set/verify/session lockout behavior.
- [ ] Add authenticated MPIN setup endpoint in auth routes.

### 3. Telegram Enforcement
- [ ] Add sensitive-intent detection in Telegram gateway.
- [ ] Require MPIN verification for balance/score/money intents.
- [ ] Support short verification session TTL for usability.

### 4. Telegram Alerts
- [ ] Add spending usage alert delivery to linked Telegram users.
- [ ] Persist dedupe keys for alert idempotency.

### 5. Verification
- [ ] Unit/integration tests for MPIN + Telegram gate paths.
- [ ] Update implementation progress and security docs.

## Verification Commands
- `.venv\Scripts\ruff.exe check .`
- `.venv\Scripts\python.exe -m pytest -m unit`
- `.venv\Scripts\python.exe -m pytest -m integration`
