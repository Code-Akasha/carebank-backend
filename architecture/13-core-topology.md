# 13 · Core System Architecture & Topology

> [← 12 · Security & Compliance](12-security-compliance.md) · **Core System Topology** · [README →](README.md)

---

## Overview

This document presents the overarching CareBank architecture, broken down into **presenter-friendly component topologies** designed for onboarding newcomers. 

Instead of a single overwhelming diagram, the system is split into four high-level but detailed domains: **Edge & Web**, **AI Orchestration**, **Banking Proxy & Security**, and **Real-Time & Omni-Channel**. Each diagram highlights the specific technologies used, the security boundaries, and the flow of data. Following the component diagrams, sequence diagrams detail the exact interactions over time.

---

## Part I: Component Topologies (For Presentation)

### 1.1 Web Application & Edge Topology
*Focuses on how users interact with the system securely from the browser.*

```mermaid
graph LR
    subgraph Browser["User Device"]
        FE["CareBank UI: React 18 / Vite / Tailwind"]
        LS["localStorage: Stores User JWT"]
    end

    subgraph Edge["Backend Edge Network"]
        Auth["Auth Middleware: FastAPI / HTTPBearer"]
        CORS["CORS Protection: Origin Whitelist"]
        API["REST Controllers: FastAPI Routers"]
    end

    subgraph Data["Persistence"]
        DB["PostgreSQL: User Accounts & MPIN hashes"]
    end

    FE -->|"(1) Request + Bearer JWT"| CORS
    CORS -->|"(2) Pre-flight OK"| Auth
    Auth -->|"(3) Decodes HS256 JWT"| API
    Auth -.->|"Verify Credentials"| DB
    LS -.->|"Provides Token"| FE
```

**Key Technologies & Security:**
- **Frontend**: React SPA bundled with Vite for fast HMR and optimized builds.
- **Security**: The frontend holds a stateless **User JWT (HS256)** valid for 24 hours. No secrets are exposed to the client. Passwords and MPINs are hashed with **bcrypt** in PostgreSQL.
- **API**: Built on **FastAPI**, leveraging Pydantic validation and asynchronous Python (`asyncio`) for high concurrency.

---

### 1.2 AI Orchestration Topology
*Focuses on the "Brain" of the system: how LangGraph coordinates multiple specialist AI agents.*

```mermaid
graph TB
    subgraph Orchestration["Cognitive Core (Backend)"]
        Coord["Coordinator Agent: LangGraph State Machine"]
        Mem["Conversation Store: Redis Short-term Context"]
    end

    subgraph AI_Pipeline["NLP Pipeline"]
        Classify["Intent Classifier: LLM + Regex Fallback"]
        NLG["NLG Synthesiser: Response Generation"]
        Comp["Compliance Guard: Blacklist & Hallucination Check"]
    end

    subgraph Workers["Specialist Agents"]
        Intel["Intelligence: Forecasts & What-Ifs"]
        Comm["Communication: Planning & Tasks"]
        Opp["Opportunity: Product Offers"]
        Auto["AutoSavings: Micro-Savings"]
        Pay["Payment: P2P Transfers"]
    end

    Coord <-->|"(1) Read/Write State"| Mem
    Coord -->|"(2) Detect Intent"| Classify
    Classify -->|"(3) Route Request"| Workers
    Workers -->|"(4) Structured Data"| NLG
    NLG -->|"(5) Natural Language"| Comp
    Comp -->|"(6) Safe Output"| Coord
```

**Key Technologies & Security:**
- **Orchestration**: **LangGraph** manages the state transitions. If the user misses a parameter (e.g. an amount for rent), the state is saved to **Redis**, and the LLM pauses to ask for it.
- **LLM Engine**: Powered by **Gemini 2.5 Flash** (or local Ollama fallback), configured via admin prompts in the database.
- **Compliance**: The `Compliance Guard` is a hard-coded security layer that runs *after* the LLM. It intercepts the response to strip blacklisted terms ("guaranteed returns") and flags fabricated numbers.

---

### 1.3 Secure Proxy & Core Banking Topology
*Focuses on how the Backend safely communicates with the external Banking Proxy without exposing it to the frontend.*

```mermaid
graph LR
    subgraph Backend["CareBank Backend"]
        Client["BankingClient: Internal Service"]
        Signer["JWT Signer: Generates 5m Token"]
    end

    subgraph SecurityBoundary["VPC / Network Boundary"]
        Wall{"Network Firewall"}
    end

    subgraph Proxy["Agentic Banking Proxy"]
        Verify["Auth Validator: Verifies BANKING_API_SECRET"]
        Engine["Idempotent Action Engine: Prevents double-charges"]
        State["Per-User Ledger: SQLite"]
        WH["Webhook Emitter: HMAC-SHA256 Signed"]
    end

    Client -->|"(1) Request JWT"| Signer
    Signer -->|"(2) Service JWT (5m TTL)"| Client
    Client -->|"(3) API Call via HTTPS"| Wall
    Wall --> Verify
    Verify -->|"(4) Authenticated"| Engine
    Engine <-->|"(5) Execute Transaction"| State
    Engine -->|"(6) Async Settlement"| WH
```

**Key Technologies & Security:**
- **Isolation**: The Frontend **cannot** talk to the Proxy. Only the Backend can.
- **Service JWTs**: The Backend signs a short-lived token (5 minutes) using a shared secret (`BANKING_API_SECRET`). The proxy verifies this token for every incoming request.
- **Idempotency**: The Proxy Action Engine uses unique `idempotency_keys` for every transaction. If a network blip causes a retry, the user is never charged twice.
- **Webhooks**: When a transaction settles in the proxy, it fires an async webhook back to the backend. This payload is signed with **HMAC-SHA256** to guarantee authenticity.

---

### 1.4 Omni-Channel & Real-Time Topology
*Focuses on how asynchronous events and notifications reach the user across devices.*

```mermaid
graph TB
    subgraph Triggers["Event Sources"]
        Webhook["Proxy Webhook: Transaction Settled"]
    end

    subgraph Dispatcher["Event Router (Backend)"]
        ED["EventDispatcher: Async Queue"]
        Score["Health Score Engine: Recomputes Deterministically"]
        Nudge["Nudge Engine: Fatigue & Cooldown Rules"]
    end

    subgraph Channels["Delivery Channels"]
        SSE["Server-Sent Events: Live Web Dashboard Sync"]
        TG["Telegram Alerts: Push Notifications to Phone"]
    end

    Webhook -->|"(1) HTTP POST"| ED
    ED -->|"(2) Trigger Calculation"| Score
    Score -->|"(3) Score dropped > 5pts"| Nudge
    
    ED -->|"(4) Broadcast"| SSE
    Nudge -->|"(5) Allowed by limits?"| TG
```

**Key Technologies & Security:**
- **SSE (Server-Sent Events)**: A lightweight, unidirectional websocket alternative used to push live balance/score updates to the React frontend the millisecond a proxy webhook clears.
- **Telegram Bot**: Users bind their Telegram app via a secure 6-digit hex pairing code.
- **Fatigue Protection**: The Nudge engine ensures users aren't spammed. It strictly enforces `DAILY_LIMIT = 2` and a 4-hour `COOLDOWN` window between Telegram alerts.

---

## Part II: Interaction Workflows (Sequence Diagrams)

### 2.1 Agent Pipeline & Orchestration Flow

This sequence traces a standard chat request through the AI components.

```mermaid
sequenceDiagram
    autonumber
    
    box rgba(100, 150, 255, 0.1) "Edge Layer"
        actor User
        participant HTTP as FastAPI Routes
    end
    
    box rgba(150, 255, 150, 0.1) "Orchestrator Core"
        participant Coord as Coordinator
        participant LLM as Intent Classifier
    end

    box rgba(255, 200, 100, 0.1) "Agent & Compliance"
        participant Agent as Specialist Agent
        participant NLG as NLG Synthesizer
        participant Comp as Compliance Guard
        participant DB as PostgreSQL (Audit)
    end

    User->>HTTP: "What is my balance?"
    HTTP->>Coord: invoke_graph(message)
    
    Coord->>LLM: classify_intent(message, history)
    LLM-->>Coord: intent: "balance"
    
    Coord->>Agent: route to IntelligenceAgent.invoke()
    Note over Agent: Fetches proxy data, computes stats
    Agent-->>Coord: AgentOutput (structured stats)
    
    Coord->>NLG: format_response(AgentOutput)
    NLG-->>Coord: Natural language string
    
    Coord->>Comp: validate_and_refine(response)
    Note over Comp: Blacklist & Number checks
    Comp-->>Coord: Refined response + metadata
    
    Coord->>DB: Log AuditLog entry
    Coord-->>HTTP: Final ChatResponse
    HTTP-->>User: "Your balance is ₹85,000..."
```

---

### 2.2 Conversation Context & Memory Flow

This sequence demonstrates how LangGraph handles a `needs_input` state when the user hasn't provided enough information (e.g. the amount for a scheduled payment).

```mermaid
sequenceDiagram
    autonumber
    
    box rgba(100, 150, 255, 0.1) "User Interface"
        actor User
    end
    
    box rgba(150, 255, 150, 0.1) "Context Engine"
        participant Coord as Coordinator
        participant Store as ConversationStore
        participant DB as Redis (History)
    end
    
    box rgba(255, 200, 100, 0.1) "Specialist"
        participant Agent as CommunicationAgent
    end

    User->>Coord: "Schedule a payment for rent"
    
    Coord->>Store: get_conversation_state()
    Store->>DB: Fetch state
    DB-->>Store: {}
    Store-->>Coord: state: {}
    
    Coord->>Agent: invoke(intent="planning")
    Note over Agent: Detects missing 'amount'
    Agent-->>Coord: status: needs_input, required: ["amount"]
    
    Coord->>Store: set_state({action: "schedule_payment", requires: "amount"})
    Store->>DB: Save pending state
    Coord-->>User: "Sure, what's the rent amount?"

    Note over User,DB: --- Turn 2 ---
    
    User->>Coord: "15000"
    
    Coord->>Store: get_conversation_state()
    Store->>DB: Fetch state
    DB-->>Store: {action: "schedule_payment", requires: "amount"}
    Store-->>Coord: state: {action: "schedule_payment", requires: "amount"}
    
    Note over Coord: Keyword heuristics detect<br/>"15000" matches pending state.
    Coord->>Agent: invoke(amount=15000)
    Agent-->>Coord: Action complete.
    
    Coord->>Store: clear_state()
    Store->>DB: Delete pending state
    Coord-->>User: "Scheduled ₹15,000 for rent."
```

---

### 2.3 Telegram Pairing Flow

Because Telegram users start out unauthenticated, a secure 6-digit hex pairing code is used to bind their device to their CareBank web profile.

```mermaid
sequenceDiagram
    autonumber
    
    box rgba(100, 150, 255, 0.1) "Telegram Ecosystem"
        actor UserTG as Telegram User
        participant API as Telegram API
    end
    
    box rgba(150, 255, 150, 0.1) "Telegram Gateway"
        participant Poller as Polling Loop
        participant Gate as BotGateway
        participant Pair as PairingStore
    end
    
    box rgba(255, 200, 100, 0.1) "CareBank Platform"
        participant Coord as CoordinatorAgent
        participant DB as PostgreSQL
        participant FE as Web Frontend
    end

    UserTG->>API: "/start"
    API->>Poller: fetch_updates()
    Poller->>Gate: process_update(message)
    
    Gate->>DB: lookup User by tg_id
    DB-->>Gate: Not Found (Unlinked)
    
    Gate->>Pair: create_pairing_code(tg_id)
    Note over Pair: Sets TTL to 60 mins
    Pair-->>Gate: code: "A1B2C3"
    Gate-->>API: "Pairing required. Code: A1B2C3"
    API-->>UserTG: Receives code
    
    Note over UserTG,FE: User logs into Web UI
    UserTG->>FE: Enters code "A1B2C3" in settings
    FE->>Gate: POST /bot/telegram/pair/approve {code: "A1B2C3"}
    Gate->>Pair: pop(code)
    Pair-->>Gate: tg_id
    
    Gate->>DB: update User set telegram_user_id = tg_id
    DB-->>Gate: Success
    Gate-->>FE: Pairing Successful!
    
    Note over UserTG,Coord: --- Later, sending a message ---
    UserTG->>API: "What's my balance?"
    API->>Poller: fetch_updates()
    Poller->>Gate: process_update()
    Gate->>DB: lookup User
    DB-->>Gate: Valid User
    Gate->>Coord: invoke_graph(message)
    Coord-->>Gate: "Your balance is ₹85,000"
    Gate-->>API: Send text
    API-->>UserTG: "Your balance is ₹85,000"
```

---

| ← Previous | Current | Next → |
|---|---|---|
| [12 · Security & Compliance](12-security-compliance.md) | **13 · Core System Topology** | [README](README.md) |
