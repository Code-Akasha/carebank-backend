# 04 · Financial Health Score

> [← 03 · Agent Pipeline](03-agent-pipeline.md) · **Health Score** · [05 · What-If Simulator →](05-what-if-simulator.md)

---

## Overview

The Financial Health Score is CareBank's flagship insight feature — a **composite 0–100 score** calculated from four equally-weighted deterministic factors. No LLM is involved in the score computation itself; the LLM only handles natural-language presentation of the results.

The pipeline works as follows: transaction data is fetched from the proxy, monthly stats are calculated (savings ratio, expense variance), liquidity days are derived from balance and daily expenses, forecast error comes from Prophet-based time-series prediction, and a persona is assigned via K-Means clustering. All four signals feed into a deterministic formula in `core/finance.py` that produces the final score.

The health score is **event-driven**: it can be recomputed asynchronously whenever a new transaction arrives via the `EventDispatcher`, cached in Redis for 5 minutes, and served instantly on subsequent requests. If the score drops by 5+ points, a nudge notification is automatically sent to the user.

---

## Score Computation Pipeline

```mermaid
graph LR
    subgraph DataFetch["1. Data Fetch"]
        TXN["Fetch Transactions\n(Proxy API)"]
        BAL["Fetch Balance\n(Proxy API)"]
    end

    subgraph Analysis["2. Analysis"]
        Stats["Monthly Stats: savings_ratio, expense_variance"]
        Liquidity["Liquidity Days = balance / daily_expense"]
        Forecast["Prophet Forecast → forecast_error"]
        Cluster["K-Means Clustering → persona"]
    end

    subgraph Core["3. Deterministic Core"]
        Score["calculate_health_score: 4 factors × 25 pts"]
    end

    subgraph Output["4. Output"]
        Result["Score 0-100 + factor breakdown + persona"]
    end

    TXN --> Stats
    TXN --> Forecast
    TXN --> Cluster
    BAL --> Liquidity
    Stats --> Score
    Liquidity --> Score
    Forecast --> Score
    Score --> Result
    Cluster --> Result
```

---

## Factor Breakdown (25 Points Each)

| Factor         | Input              | Formula                       | Max | "Good" Threshold   |
| -------------- | ------------------ | ----------------------------- | --- | ------------------ |
| **Savings**    | `savings_ratio`    | `min(ratio / 0.20, 1.0) × 25` | 25  | ≥ 15% savings rate |
| **Stability**  | `expense_variance` | `max(1 - variance, 0) × 25`   | 25  | Variance < 0.30    |
| **Liquidity**  | `liquidity_days`   | `min(days / 30, 1.0) × 25`    | 25  | ≥ 15 days coverage |
| **Confidence** | `forecast_error`   | `max(1 - error, 0) × 25`      | 25  | Error < 0.20       |

**Total Score** = sum of all four factor scores (0–100).

---

## Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant BE as Backend
    participant Intel as IntelligenceAgent
    participant PX as Proxy
    participant Finance as core/finance.py

    User->>FE: Opens Dashboard / asks "my health score"
    FE->>BE: GET /api/health-score (or via chat)
    BE->>Intel: _handle_health_score(user_id)
    Intel->>PX: GET /transactions
    PX-->>Intel: [50 transactions]
    Intel->>PX: GET /balances
    PX-->>Intel: {current_balance: 85000}

    Note over Intel: Pipeline starts
    Intel->>Intel: calculate_monthly_stats() → savings_ratio=0.18, variance=0.25
    Intel->>Intel: liquidity_days = 85000 / (expenses/30) = 22 days
    Intel->>Intel: forecast_balance() → forecast_error=0.15
    Intel->>Intel: cluster_persona() → "Balanced Manager"
    Intel->>Finance: calculate_health_score(0.18, 0.25, 22, 0.15)
    Finance-->>Intel: {score: 77.5, factors: {...}}

    Intel-->>BE: AgentOutput {score: 77.5, persona, factors}
    BE-->>FE: {score: 77.5, factors: {...}, persona: "Balanced Manager"}
    FE->>FE: Render HealthScoreMeter (animated gauge)
```

---

## Example Scenario

**User Profile:** Priya, balance ₹85,000, moderate spender, saving 18% monthly.

**Input Data:**
```json
{
  "transactions": [
    {"amount": -3500, "category": "food", "date": "2026-05-15"},
    {"amount": -15000, "category": "rent", "date": "2026-05-01"},
    {"amount": 75000, "category": "salary", "date": "2026-05-01"},
    {"amount": -2000, "category": "utilities", "date": "2026-05-03"}
  ],
  "current_balance": 85000.0
}
```

**Computed Factors:**

| Factor | Value | Score | Label |
|---|---|---|---|
| Savings | ratio = 0.18 | 22.5 / 25 | Good |
| Stability | variance = 0.25 | 18.8 / 25 | Stable |
| Liquidity | 22 days | 18.3 / 25 | Good |
| Confidence | error = 0.15 | 21.3 / 25 | High |

**Final Score: 80.9 / 100** — Persona: "Balanced Manager"

**Response (API):**
```json
{
  "score": 80.9,
  "factors": {
    "savings": {"value": 0.18, "score": 22.5, "label": "Good"},
    "stability": {"value": 0.25, "score": 18.8, "label": "Stable"},
    "liquidity": {"value": 22, "score": 18.3, "label": "Good"},
    "confidence": {"value": 0.15, "score": 21.3, "label": "High"}
  },
  "persona": "Balanced Manager",
  "forecast": {
    "predicted_balance": 82000,
    "forecast_error": 0.15
  },
  "stats": {
    "income": 75000,
    "expenses": 20500,
    "savings_ratio": 0.18,
    "expense_variance": 0.25
  }
}
```

---

## Event-Driven Recomputation

```mermaid
sequenceDiagram
    participant PX as Proxy
    participant BE as Backend
    participant ED as EventDispatcher
    participant Redis as Redis Cache
    participant User as User (SSE)

    PX->>BE: Webhook: transaction.lifecycle
    BE->>ED: handle_transaction_event(txn)
    ED->>PX: GET /transactions (fresh)
    ED->>PX: GET /balances (fresh)
    ED->>ED: compute_health_score()
    ED->>Redis: GET carebank:health_score:{user_id}
    Note over ED: Previous score = 82
    ED->>Redis: SET carebank:health_score:{user_id} (TTL: 300s)
    Note over ED: New score = 75 (dropped 7 pts!)
    ED->>ED: Score dropped ≥ 5 → trigger nudge
    ED->>User: SSE push: "Your health score dropped from 82 to 75"
```

---

## Frontend Visualization

The `HealthScoreMeter.tsx` component renders an animated circular gauge:
- **0–40**: Red zone — "Needs Attention"
- **41–70**: Yellow zone — "Room for Improvement"
- **71–100**: Green zone — "Healthy"

Factor breakdowns are shown as horizontal bars beneath the gauge.

---

## Decision Table

| Trigger                           | System Action                            | Outcome                            |
| --------------------------------- | ---------------------------------------- | ---------------------------------- |
| User asks "my health score"       | IntelligenceAgent computes full pipeline | Score + breakdown returned         |
| New transaction arrives (webhook) | EventDispatcher recomputes score         | Redis cache updated                |
| Score drops ≥ 5 points vs cached  | Nudge sent via CommunicationAgent        | User notified via SSE/Telegram     |
| Proxy unreachable (dev mode)      | Fallback to mock transactions            | Score computed from synthetic data |
| Proxy unreachable (production)    | Error raised                             | 500 returned to user               |

---

| ← Previous | Current | Next → |
|---|---|---|
| [03 · Agent Pipeline](03-agent-pipeline.md) | **04 · Health Score** | [05 · What-If Simulator](05-what-if-simulator.md) |
