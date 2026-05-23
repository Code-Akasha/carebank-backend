# 10 · Real-Time Events & Communication

> [← 09 · Action Engine](09-action-engine.md) · **Real-Time Events** · [11 · Admin & Observability →](11-admin-observability.md)

---

## Overview

CareBank supports three real-time communication channels: **Server-Sent Events (SSE)** for live browser updates, **Redis Pub/Sub** for inter-service event distribution, and **Telegram Bot** integration for out-of-app notifications. All three are orchestrated by the `event_dispatcher` service and the `push_event` API in the events module.

The SSE endpoint (`GET /api/events/stream`) merges two event sources: an in-memory queue (for push events from within the backend) and a Redis pub/sub channel (for cross-instance events). The frontend connects via the `useEventStream` hook which handles automatic reconnection with exponential backoff (up to 5 retries, max 30-second delay).

---

## Communication Architecture

```mermaid
graph TB
    subgraph EventSources["Event Sources"]
        TXN["Transaction Completed"]
        SCORE["Health Score Changed"]
        ACTION["Action Approved/Rejected"]
        REMIND["Reminder Due"]
    end

    subgraph Backend["Backend (FastAPI)"]
        ED["EventDispatcher"]
        PushAPI["push_event(user_id, type, data)"]
        MemQ["In-Memory Queue\n(per-user asyncio.Queue)"]
        SSE["SSE Endpoint\nGET /api/events/stream"]
    end

    subgraph Redis
        PubSub["Redis Pub/Sub\ncarebank:transactions:{user_id}"]
    end

    subgraph Telegram
        TGBot["Telegram Bot Service"]
        TGAlerts["Telegram Alerts"]
    end

    subgraph Frontend
        ESHook["useEventStream hook"]
        Browser["Browser (EventSource)"]
    end

    TXN --> ED
    SCORE --> ED
    ACTION --> PushAPI
    REMIND --> PushAPI
    
    ED --> PubSub
    ED --> PushAPI
    PushAPI --> MemQ
    
    MemQ --> SSE
    PubSub --> SSE
    
    SSE -->|"text/event-stream"| Browser
    Browser --> ESHook
    
    ED --> TGAlerts
    TGAlerts --> TGBot
```

---

## SSE Stream: Step-by-Step

### 1. Frontend connects

| Repo | What happens |
|---|---|
| **Frontend** | `useEventStream` hook creates `EventSource` to `GET /api/events/stream?token=<jwt>` |
| **Backend** | `events.py` validates JWT, creates per-user `asyncio.Queue`, subscribes to Redis channel `carebank:transactions:{user_id}` |

### 2. Event loop

| Repo | What happens |
|---|---|
| **Backend** | SSE endpoint enters infinite loop. Priority: (1) check in-memory queue (non-blocking), (2) check Redis pub/sub (1s timeout), (3) send keepalive every 5 seconds. |
| **Frontend** | `EventSource.onmessage` parses JSON, calls `onEvent` callback. Keepalive comments are silently ignored. |

### 3. Event arrives

| Repo | What happens |
|---|---|
| **Backend** | EventDispatcher calls `push_event("user_123", "transaction_completed", {...})`. Payload is enqueued to all connected SSE clients for that user. |
| **Frontend** | Hook processes event, triggers UI updates (e.g. refresh balance widget). |

### 4. Connection drops

| Repo | What happens |
|---|---|
| **Frontend** | `EventSource.onerror` fires. Hook closes connection, increments retry counter, schedules reconnect with backoff: `min(1000 × 2^retries, 30000)ms`. Max 5 retries. |
| **Backend** | `asyncio.CancelledError` caught in SSE generator. Queue removed from `_user_queues`. Redis pub/sub unsubscribed and closed. |

---

## Sequence Diagram: Transaction Event → SSE Push

```mermaid
sequenceDiagram
    participant PX as Proxy
    participant BE as Backend
    participant ED as EventDispatcher
    participant Redis as Redis
    participant SSE as SSE Generator
    participant FE as Frontend

    PX->>BE: Webhook: transaction.lifecycle
    BE->>ED: handle_transaction_event(txn)
    ED->>ED: detect_anomaly()
    ED->>ED: compute_health_score()
    
    ED->>Redis: PUBLISH carebank:transactions:user_123 {event}
    Note over SSE: SSE loop polls Redis
    SSE->>SSE: get_message() → event data
    SSE->>FE: data: {"type":"transaction_completed","amount":-15000}\n\n
    FE->>FE: Update dashboard balance
```

---

## Telegram Bot Integration

CareBank supports a Telegram bot for out-of-app notifications. The bot uses two access modes:

| Mode | `TELEGRAM_DM_POLICY` | Behaviour |
|---|---|---|
| **Pairing** | `pairing` | User must link Telegram account by sending a pairing code |
| **Allowlist** | `allowlist` | Only pre-approved Telegram IDs can interact |

### Telegram Alert Flow

```mermaid
sequenceDiagram
    participant ED as EventDispatcher
    participant TGA as TelegramAlerts
    participant TGBot as Telegram Bot API

    ED->>TGA: send_alert(user_id, "Health score dropped to 72")
    TGA->>TGA: Lookup linked Telegram chat_id
    alt Chat ID found
        TGA->>TGBot: sendMessage(chat_id, text)
        TGBot-->>TGA: OK
    else No linked account
        TGA->>TGA: Log: "No Telegram link for user"
    end
```

---

## Event Types

| Event Type | Source | Payload |
|---|---|---|
| `connected` | SSE endpoint | `{type, user_id}` |
| `transaction_completed` | EventDispatcher | `{type, transaction_id, amount, category}` |
| `health_score_updated` | EventDispatcher | `{type, score, previous_score}` |
| `action_approved` | ActionRequestService | `{type, request_id, action_type}` |
| `action_rejected` | ActionRequestService | `{type, request_id, reason}` |
| `reminder_due` | ReminderWorker | `{type, checklist_item_id, description}` |
| `nudge` | CommunicationAgent | `{type, message, anomaly}` |

---

## Reconnection Backoff Schedule

| Retry # | Delay | Cumulative |
|---|---|---|
| 1 | 1s | 1s |
| 2 | 2s | 3s |
| 3 | 4s | 7s |
| 4 | 8s | 15s |
| 5 | 16s | 31s |
| — | Max reached | Connection abandoned |

---

## Decision Table

| Trigger | System Action | Outcome |
|---|---|---|
| Frontend mounts dashboard | `useEventStream` connects SSE | Real-time updates enabled |
| Transaction webhook arrives | EventDispatcher → push_event | SSE data frame sent |
| Redis unavailable | SSE falls back to push-only mode | In-memory queue still works |
| SSE connection drops | Frontend retries with backoff | Auto-reconnect (up to 5 attempts) |
| Health score drops ≥ 5 pts | Nudge via SSE + Telegram | User notified on both channels |
| Telegram not linked | Alert logged, skipped | No Telegram message sent |
| Keepalive timer (5s) | Send SSE comment `: keepalive` | Connection kept alive |

---

| ← Previous | Current | Next → |
|---|---|---|
| [09 · Action Engine](09-action-engine.md) | **10 · Real-Time Events** | [11 · Admin & Observability](11-admin-observability.md) |
