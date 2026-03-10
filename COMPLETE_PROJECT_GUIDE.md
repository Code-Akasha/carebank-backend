# 🏦 CareBank: Complete Project 

**A Complete Overview of All 3 Repositories & How Everything Works Together**

---

## 📌 Table of Contents

1. [What is CareBank?](#what-is-carebank)
2. [The Three Repositories](#the-three-repositories)
3. [System Architecture Overview](#system-architecture-overview)
4. [The 5 Specialized Agents](#the-5-specialized-agents)
5. [Core Safety Layer (Deterministic Core)](#core-safety-layer)
6. [Compliance Guard (Security)](#compliance-guard)
7. [Mock Banking API](#mock-banking-api)
8. [How Everything Communicates](#how-everything-communicates)
9. [Security & Trust](#security--trust)
10. [Real-World Example: Health Score](#real-world-example)

---

## What is CareBank?

CareBank is a **financial wellness chatbot** that helps people understand and improve their finances using AI agents. Instead of one general AI trying to do everything, CareBank has **5 specialized AI agents** - each an expert in a specific financial task.

### Core Mission
✅ Help users understand their financial health  
✅ Predict future money problems  
✅ Recommend savings opportunities  
✅ Suggest relevant financial products  
✅ Do this safely, transparently, and without hallucinations  

---

## The Three Repositories

### 1. **carebank-backend** (`d:\PycharmProjects\carebank-backend`)
- **What it is**: The brain of the system (Python + FastAPI)
- **Main job**: Run the 5 AI agents, do all calculations, enforce safety rules
- **Key folders**:
  - `app/agents/` - The 5 specialized agents
  - `app/core/` - Pure financial calculations (Deterministic Core)
  - `app/compliance/` - Safety & regulatory rules (Compliance Guard)
  - `app/services/` - Data processing, forecasting, clustering
  - `app/routes/` - REST API endpoints

### 2. **carebank-frontend** (`d:\WebstormProjects\carebank-frontend`)
- **What it is**: The user interface (TypeScript + React + Vite)
- **Main job**: Show information beautifully, let users interact
- **Key features**:
  - Health Score meter (0-100 gauge)
  - What-If simulator (test spending scenarios)
  - Chat interface
  - Transaction history
  - Notification center
  - Product recommendations

### 3. **carebank-mockbank** (`d:\PycharmProjects\carebank-mockbank`)
- **What it is**: Simulated banking system (Python + FastAPI)
- **Main job**: Pretend to be a real bank, provide test data
- **Key endpoints**:
  - `/transactions` - List all transactions
  - `/balances` - Get account balances
  - `/products` - Show banking products
  - Real-time events via Redis Pub/Sub

### 4. **.github-private** (Documentation & Team Coordination)
- Team docs, architecture diagrams, feature guides
- Not part of the running system, but guides development

---

## System Architecture Overview

### 🏗️ The Complete System Diagram

```
┌────────────────────────────────────────────┐
│         Frontend (React + Vite)            │
│  • Dashboard with Health Score            │
│  • What-If Simulator                      │
│  • Chat interface                         │
│  • Notifications & Products               │
└───────────────┬────────────────────────────┘
                │ (REST API calls)
                ▼
┌────────────────────────────────────────────┐
│     Coordinator Agent (LangGraph)          │
│  ┌──────────────────────────────────────┐  │
│  │ 1. Receive user message              │  │
│  │ 2. Understand intent (balance? save? │  │
│  │ 3. Route to correct agent            │  │
│  │ 4. Collect response                  │  │
│  │ 5. Return to user                    │  │
│  └──────────────────────────────────────┘  │
└───┬──┬──────┬──────────┬──────────────────┘
    │  │      │          │
    ▼  ▼      ▼          ▼
 ┌──────────┐ ┌──────────────┐ ┌──────────┐ ┌────────────┐
 │Intelligence│ │Communication │ │Opportunity│ │Auto-Savings│
 │  Agent    │ │   Agent      │ │  Agent   │ │  Agent    │
 ├──────────┤ ├──────────────┤ ├──────────┤ ├────────────┤
 │ Analyzes │ │ Explains     │ │ Finds    │ │ Suggests  │
 │ patterns │ │ things       │ │ deals &  │ │ savings   │
 │ Predicts │ │ Sends gentle │ │ products │ │ amounts   │
 │ balance  │ │ reminders    │ │ Checks   │ │ Asks user │
 │ Spots   │ │ Checks tone  │ │ if you   │ │ approval  │
 │ anomalies│ │ in response  │ │ qualify  │ │ Calculates│
 └────┬────┘ └──────┬───────┘ └────┬─────┘ └─────┬──────┘
      │             │              │             │
      └─────────────┴──────────────┴─────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │  Deterministic Core (Safety)  │
        │  ┌─────────────────────────┐  │
        │  │ ALL financial numbers   │  │
        │  │ come from here:         │  │
        │  │ • Balance calculations  │  │
        │  │ • Budget math           │  │
        │  │ • Score computations    │  │
        │  │ • Eligibility checks    │  │
        │  │ • Impact forecasts      │  │
        │  │ NO LLM involved!        │  │
        │  └─────────────────────────┘  │
        └───────────┬───────────────────┘
                    │
                    ▼
        ┌───────────────────────────────┐
        │   Compliance Guard (Blocker)  │
        │  ┌─────────────────────────┐  │
        │  │ Check output safety:    │  │
        │  │ ✓ No banned terms       │  │
        │  │ ✓ Numbers verified      │  │
        │  │ ✓ Disclaimers added     │  │
        │  │ ✓ Audit logged          │  │
        │  └─────────────────────────┘  │
        └───────────┬───────────────────┘
                    │
                    ▼
        ┌───────────────────────────────┐
        │   Safe Response to User       │
        │  Ready for Frontend Display   │
        └───────────────────────────────┘
```

### 📊 Data Sources

```
Mock Banking API (carebank-mockbank)
  │
  ├─ /transactions → Transaction history (spending patterns)
  │
  ├─ /balances → Current account balance
  │
  └─ /products → Available financial products
       ▼
All data flows to Backend agents
```

---

## The 5 Specialized Agents

Think of agents like specialized doctors. Instead of one general doctor, you have 5 experts:

### 1. 🧠 **Intelligence Agent**
**"The Data Analyst & Predictor"**

**What it does**:
- Analyzes your spending patterns with machine learning
- Predicts your balance at the end of the month
- Detects unusual transactions (fraud/anomalies)
- Calculates your financial health score
- Groups you into a spending "persona" (saver, spender, etc.)

**How it works**:
1. Gets your transaction history
2. Uses Prophet (a forecasting tool) to predict future balance
3. Uses K-means clustering to find your spending type
4. Passes data to Deterministic Core for final score calculation

**Example**:
- User has ₹25,000 balance
- Intelligence Agent looks at last 3 months of spending
- Predicts: "You'll have ₹18,000 left next week"
- Hands to Core for official verification

---

### 2. 💬 **Communication Agent**
**"The Friendly Explainer & Reminder"**

**What it does**:
- Answers normal questions (How much do I have? Am I broke?)
- Explains financial concepts in plain English
- Sends gentle nudges/reminders (not too many!)
- Adapts tone to your preferences
- Uses an LLM (AI language model) to generate human-like responses

**How it works**:
1. Receives your question
2. Gets your current balance & data
3. Uses Language Model to write a friendly response
4. Checks "nudge fatigue" (Don't send too many reminders!)
5. Hands to Compliance Guard for safety check

**Example**:
- You ask: "Can I afford a ₹1,500 laptop?"
- Communication Agent gets your balance & upcoming bills
- Writes: "You have ₹25,000, but ₹18,000 is spoken for next month. A ₹1,500 laptop would be tight. Maybe wait 2 weeks?"
- Compliance Guard checks it's honest
- Sends to you

---

### 3. 🤝 **Opportunity Agent**
**"The Deal Finder & Product Matcher"**

**What it does**:
- Finds unused subscriptions (Netflix you don't watch?)
- Recommends products you qualify for (credit cards, loans, etc.)
- Checks if you're eligible based on your financial profile
- Uses pattern matching + RAG (Retrieval-Augmented Generation) to find matches

**How it works**:
1. Analyzes your recent transactions
2. Looks for recurring charges (subscriptions)
3. Checks product database for matches to your profile
4. Uses Deterministic Core to verify eligibility
5. Presents recommendations

**Example**:
- You've spent ₹199/month consistently on Netflix
- Opportunity Agent suggests: "You watch Netflix regularly. Consider upgrading to Premium"
- Also: "Your credit score is 750+. You qualify for this credit card with 1% cashback"

---

### 4. 💰 **Auto-Savings Agent**
**"The Smart Savings Suggester"**

**What it does**:
- Calculates how much you can safely save each month
- Simulates automatic transfers to savings accounts
- Checks if it's safe (won't leave you short on money)
- Asks for your approval before doing anything

**How it works**:
1. Looks at your predicted balance (from Intelligence Agent)
2. Looks at upcoming bills
3. Calculates surplus: "You'll have ₹3,000 extra next week"
4. Suggests: "Transfer ₹2,000 to savings account (keep ₹1,000 buffer)"
5. Asks you: "Should I do this?"
6. If you approve → Deterministic Core executes the transfer
7. Updates your Health Score

**Example**:
- Today: Balance ₹25,000
- Bills this month: ₹18,000
- Intelligence Agent predicts: Surplus of ₹3,000
- Auto-Savings Agent suggests: "Transfer ₹2,500 to savings, keep ₹500 buffer"
- You click ✅ "Yes"
- Transfer happens, Health Score goes up

---

### 5. 🧭 **Coordinator Agent**
**"The Traffic Controller"**

**What it does**:
- Receives your message
- Understands what you're really asking (intent)
- Decides which agent should handle it
- Collects all responses
- Sends back a unified answer

**How it works**:
1. You send a message: "I want to save money"
2. Coordinator uses an LLM to classify intent
3. Recognizes: This is an "auto-savings" question
4. Routes to Auto-Savings Agent + Intelligence Agent
5. Gets their responses
6. Coordinates final answer
7. Passes through Compliance Guard
8. Returns to you

**Example conversation flow**:
```
You: "How much can I save this month?"
     │
     ▼
Coordinator: "What's the intent? → 'auto_savings' + 'forecast'"
     │
     ├─→ Intelligence Agent: [Predicts balance]
     │
     └─→ Auto-Savings Agent: [Suggests amount]
                    │
                    ▼
        Compliance Guard: "Is this safe? ✓ Yes"
                    │
                    ▼
        Response: "You can safely save ₹2,500"
```

---

## Core Safety Layer

### 🔢 Deterministic Core (`app/core/finance.py`)

This is the **single most important piece** of CareBank.

**Golden Rule**: 
> **⚠️ NO FINANCIAL NUMBER EVER COMES FROM AN LLM**
> **Every number users see is CALCULATED, not hallucinated**

### What it does:

1. **Calculate Health Score** (0-100)
   - 25% from savings ratio (how much you save each month)
   - 25% from expense stability (is your spending consistent?)
   - 25% from liquidity days (how many days of expenses can you cover?)
   - 25% from forecast confidence (how accurate are our predictions?)

2. **Forecast Impact** - What happens if you spend more?
   ```
   New Balance = Current Balance - Bills This Month - Extra Spending
   ```

3. **Check Eligibility** - Can you get a loan or product?
   ```
   Compare your profile against requirements:
   ✓ Credit score ≥ 750?
   ✓ Balance ≥ ₹5,000?
   ✓ Income ≥ ₹50,000/month?
   ```

4. **Calculate Surplus** - How much extra do you have?
   ```
   Surplus = Income - (Expected Bills + Emergency Reserve)
   ```

### Why this matters:

❌ **Bad**: "Your health score is 85 because the AI feels optimistic"  
✅ **Good**: "Your health score is 85 because: savings 25/25, stability 20/25, liquidity 25/25, confidence 15/25"

Every number can be traced back to a formula. This builds trust.

---

## Compliance Guard

### 🛡️ The Safety Bouncer

Before ANY response goes to the user, Compliance Guard checks:

1. **Blacklist Check** - Are there banned words?
   - Banned: "guarantee", "promise", "risk-free", "100% safe"
   - These are illegal claims in finance

2. **Number Verification** - Do all numbers come from Deterministic Core?
   - Agent says: "Your balance is ₹25,000"
   - Compliance Guard: "Check! This came from the Banking API ✓"
   - Agent says: "You'll definitely get rich"
   - Compliance Guard: "BLOCK! This is hallucination ✗"

3. **Disclaimer Injection** - Are legal disclaimers present?
   - Adds: "*This is informational, not formal financial advice*"

4. **Audit Logging** - What happened?
   - Records every decision for regulatory review

### Why this matters:

Financial advice is heavily regulated. One wrong word can be illegal. The Compliance Guard ensures CareBank never:
- Makes false guarantees
- Gives unqualified advice
- Misleads users
- Violates financial regulations

---

## Mock Banking API

### 🏦 The Fake Bank (carebank-mockbank)

This pretends to be a real bank, providing test data:

### Endpoints:

| Endpoint | What it gives | Example |
|----------|---------------|---------|
| `GET /transactions` | List of all spends | `[{amount: -2500, merchant: "Amazon", date: ...}]` |
| `GET /balances/{user_id}` | Current balance | `{user_id: "user1", balance: 25000}` |
| `GET /products` | Available products | `[{name: "CashBack Card", interest: 0.05}]` |
| `POST /transactions` | Simulate new spend | Creates transaction, triggers Redis event |

### Data structure example:

```json
{
  "transaction": {
    "id": "txn_001",
    "user_id": "user1",
    "amount": -2500,
    "category": "dining",
    "merchant": "Restaurant XYZ",
    "timestamp": "2026-02-27T12:30:00Z",
    "description": "Lunch with team"
  }
}
```

### Real-time Updates:

When a transaction is posted:
1. MockBank creates a transaction record
2. Posts message to Redis Pub/Sub channel: `transactions:user1`
3. Backend listener picks it up
4. Re-calculates Health Score
5. Sends update to frontend
6. User sees their score change instantly ⚡

---

## How Everything Communicates

### 📡 Data Flow #1: User Asks a Question

```
┌─────────────────────────────────────────────────────────┐
│ FRONTEND (User types: "How much can I save?")           │
└────────────────────────┬────────────────────────────────┘
                         │ POST /api/chat
                         ▼
        ┌────────────────────────────────┐
        │ COORDINATOR AGENT receices     │
        │ message: "How much can I save?"│
        └────────┬───────────────────────┘
                 │ Uses LLM to classify intent
                 ▼
        ┌────────────────────────────────┐
        │ Intent: "auto_savings"         │
        │ Confidence: 0.95               │
        └────────┬───────────────────────┘
                 │ Route to agents
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────────┐  ┌──────────────────┐
│Intelligence      │  │Auto-Savings      │
│Agent            │  │Agent             │
├──────────────────┤  ├──────────────────┤
│1. Get balance    │  │1. Get prediction │
│2. Get trans.     │  │2. Calculate safe │
│3. Forecast 7d    │  │   transfer amt   │
│4. Return data    │  │3. Return suggest.│
└────────┬─────────┘  └─────────┬────────┘
         │                      │
         └──────────┬───────────┘
                    ▼
        ┌────────────────────────────┐
        │DETERMINISTIC CORE           │
        │ • Verify forecast           │
        │ • Calculate surplus safely  │
        │ • Ensure no overdraft       │
        └────────┬───────────────────┘
                 │ Combined data
                 ▼
        ┌────────────────────────────┐
        │COMMUNICATION AGENT         │
        │ • Writes friendly response │
        │ • Explains the numbers     │
        └────────┬───────────────────┘
                 │ Raw response
                 ▼
        ┌────────────────────────────┐
        │COMPLIANCE GUARD            │
        │ ✓ Check for banned terms   │
        │ ✓ Verify all numbers       │
        │ ✓ Add disclaimers          │
        │ ✓ Log decision             │
        └────────┬───────────────────┘
                 │ Safe response
                 ▼
        ┌────────────────────────────┐
        │Back to FRONTEND            │
        │Display to user             │
        └────────────────────────────┘
```

### 📡 Data Flow #2: Transaction Happens in Mock Bank

```
┌──────────────────────────────────┐
│ New transaction in MockBank      │
│ User spent ₹2,500 at restaurant  │
└────────┬───────────────────────┘
         │ POST /transactions
         ▼
┌──────────────────────────────────┐
│ MockBank processes               │
│ Updates balance: 25000 → 22500   │
└────────┬───────────────────────┘
         │ Publish to Redis
         │ Channel: transactions:user1
         ▼
┌──────────────────────────────────┐
│ BACKEND LISTENER                 │
│ Detects new transaction          │
└────────┬───────────────────────┘
         │ Fetch updated data
         ▼
┌──────────────────────────────────┐
│ INTELLIGENCE AGENT               │
│ Recalculate forecast             │
│ (New balance for next week)      │
└────────┬───────────────────────┘
         │ New forecast data
         ▼
┌──────────────────────────────────┐
│ DETERMINISTIC CORE               │
│ Recalculate Health Score         │
│ (Liquidity days changed)         │
└────────┬───────────────────────┘
         │ New score: 78 (was 82)
         ▼
┌──────────────────────────────────┐
│ WEBSOCKET to FRONTEND            │
│ Send Health Score update         │
└────────┬───────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│ USER SEES                        │
│ Health Score meter drops to 78   │
│ (Animation shows change)         │
└──────────────────────────────────┘
```

### 📡 Data Flow #3: What-If Scenario

```
USER: "What if I buy a ₹10,000 laptop?"
         │
         ▼
    COORDINATOR routes to Intelligence Agent
         │
         ▼
    INTELLIGENCE: Looks at your data
         │
         ├─ Current balance: ₹25,000
         ├─ Expected bills: ₹18,000
         └─ Proposed expense: ₹10,000
         │
         ▼
    DETERMINISTIC CORE runs calculation:
         New_Balance = 25,000 - 18,000 - 10,000 = -₹3,000 ❌
         │
         ▼
    COMMUNICATION AGENT writes response:
         "No, you can't afford it. You'd have -₹3,000
          (₹3,000 short). Wait 2 months and save more."
         │
         ▼
    COMPLIANCE GUARD checks:
         ✓ Numbers verified (from Core)
         ✓ No false promises
         ✓ Honest assessment
         │
         ▼
    SENDS TO USER with visualization
         (Bar chart showing: balance drop below zero)
```

---

## Security & Trust

### 🔒 How CareBank Stays Safe & Honest

#### 1. **Number Isolation** (Deterministic Core)
- **Problem**: LLMs can hallucinate ("You have ₹100 billion!")
- **Solution**: All financial math in pure Python functions
- **Result**: Every number is calculable, verifiable, traceable

#### 2. **Compliance Blocking** (Compliance Guard)
- **Problem**: LLMs might accidentally make illegal claims
- **Solution**: Intercept all outputs and check against regulatory blacklist
- **Result**: Banned terms are removed, disclaimers are mandatory

#### 3. **Agent Specialization**
- **Problem**: One general AI might give contradictory advice
- **Solution**: Each agent is an expert in one area
- **Result**: Coordinator ensures consistency, no cross-contamination

#### 4. **Audit Trail**
- **Problem**: Hard to debug what went wrong
- **Solution**: Every decision is logged with metadata
- **Result**: Regulators can review all interactions

#### 5. **Redis Real-time Events**
- **Problem**: Stale data leads to wrong recommendations
- **Solution**: Transaction updates through Redis Pub/Sub
- **Result**: Health Score updates instantly, not hours later

#### 6. **Sandboxed Simulation**
- **Problem**: What-if scenarios might harm the actual account
- **Solution**: All simulations are in-memory, never execute
- **Result**: Users can explore any scenario safely

---

## Real-World Example: Health Score

Let's trace how a Health Score is calculated end-to-end:

### Scenario
- User: Alice
- Balance: ₹25,000
- Monthly income: ₹50,000
- Monthly expenses: ₹40,000
- Transactions: 100 entries in 3 months

### Step 1: Data Collection
```
MockBank API returns:
{
  "balance": 25000,
  "transactions": [
    {id: "1", amount: -2500, category: "food"},
    {id: "2", amount: -8000, category: "bills"},
    ... 98 more
  ]
}
```

### Step 2: Intelligence Agent Analyzes
```python
# Intelligence Agent does:
transactions = fetch_from_mockbank()
profile = aggregate_spending_profile(transactions)
  → "Alice is a stable saver (persona: 'prudent')"

forecast = forecast_balance(transactions)
  → "Predicted balance next week: ₹22,500"
  → "Forecast error: ±₹1,200"
```

### Step 3: Deterministic Core Calculates Score
```python
# Core does pure math:

# Factor 1: Savings Ratio
savings = 50000 - 40000 = ₹10,000
savings_ratio = 10000 / 50000 = 0.20 (20%)
savings_score = min(0.20 / 0.20, 1.0) * 25 = 25/25 ✓

# Factor 2: Expense Stability
monthly_expenses = [39500, 40200, 40100]
variance = 0.0017 (very small)
stability_score = (1 - 0.0017) * 25 = 24.95/25 ✓

# Factor 3: Liquidity Days
daily_expense = 40000 / 30 = ₹1,333
liquidity_days = 25000 / 1333 = 18.75 days
liquidity_score = min(18.75 / 30, 1.0) * 25 = 15.6/25 ⚠️

# Factor 4: Forecast Confidence
forecast_error = 0.048 (4.8%, very low)
confidence_score = (1 - 0.048) * 25 = 23.8/25 ✓

# TOTAL SCORE
total = 25 + 24.95 + 15.6 + 23.8 = 89.35 → Rounds to 89/100
```

### Step 4: Communication Agent Explains
```
"Your Financial Health Score is 89/100. Here's why:

✓ Excellent Savings (25/25): You save 20% of income
✓ Very Stable Spending (24.95/25): Your expenses barely vary
⚠️ Adequate Liquidity (15.6/25): You have 18 days of expenses saved
✓ Confident Forecast (23.8/25): Our predictions are very accurate

Recommendation: Build up your emergency fund to 30+ days of expenses."
```

### Step 5: Compliance Guard Checks
```
Output analysis:
✓ No banned terms ("guarantee", "promise", etc.)
✓ All numbers trace to formulas (25, 24.95, 15.6, 23.8 verified)
✓ Is this accurate? Yes, Math checks out
✓ Add disclaimer? Yes → "*For informational purposes only*"
```

### Step 6: Frontend Displays
```
┌─────────────────────────────┐
│  Health Score Meter         │
│        89/100               │
│  ████████░░ (gauge)        │
│                             │
│  Savings:        25/25 ✓    │
│  Stability:      24.95/25 ✓ │
│  Liquidity:      15.6/25 ⚠️  │
│  Confidence:     23.8/25 ✓  │
│                             │
│  Next Action:               │
│  → Build emergency fund     │
└─────────────────────────────┘
```

---

## How Agents Communicate (Technical)

### LangGraph: The Agent Orchestrator

```
Coordinator Agent uses LangGraph (a state machine):

User Message
    │
    ▼
Step 1: RECEIVE
  └─ Parse input, extract user_id

Step 2: CLASSIFY
  └─ Use LLM to understand intent
     "balance" → Communication Agent
     "forecast" → Intelligence Agent
     "save" → Auto-Savings Agent

Step 3: ROUTE
  └─ Load correct agent from registry
     registry = {
       "CommunicationAgent": CommunicationAgent(),
       "IntelligenceAgent": IntelligenceAgent(),
       ...
     }

Step 4: EXECUTE
  └─ Call agent._invoke(input)
     agent.process() → produces output

Step 5: VALIDATE
  └─ Pass through Compliance Guard
     guard.validate_and_refine(output)

Step 6: RESPOND
  └─ Return to user
     {response: "...", metadata: {...}}
```

### Agent Registry
```python
# In coordinator.py

_AGENT_REGISTRY = {
    "IntelligenceAgent": IntelligenceAgent(),
    "CommunicationAgent": CommunicationAgent(),
    "OpportunityAgent": OpportunityAgent(),
    "AutoSavingsAgent": AutoSavingsAgent(),
}

# When routing:
agent = _AGENT_REGISTRY["CommunicationAgent"]
response = agent._invoke(input_data)
```

---

## Project Dependencies & Technologies

### Backend Stack
```
Python 3.8+
├─ FastAPI (REST API server)
├─ LangChain (LLM integration)
├─ LangGraph (Agent orchestration)
├─ SQLAlchemy (Database ORM)
├─ Alembic (Database migrations)
├─ Prophet (Time-series forecasting)
├─ scikit-learn (Machine learning)
│  ├─ K-means clustering
│  └─ Isolation Forest (anomaly detection)
└─ Redis (Real-time event pub/sub)
```

### Frontend Stack
```
TypeScript + React + Vite
├─ Components (Health Score meter, Chat, etc.)
├─ Context API (State management)
├─ Fetch API (REST calls to backend)
├─ CSS (Styling)
└─ WebSocket (Real-time score updates)
```

### Mock Bank Stack
```
Python + FastAPI
├─ Mock data generation
├─ Redis Pub/Sub publisher
└─ Mockoon (Optional visual editor)
```

---

## Startup & Running Everything

### Start Backend
```bash
cd d:\PycharmProjects\carebank-backend
python -m uvicorn app.main:app --reload
# Server runs on http://localhost:8000
```

### Start Frontend
```bash
cd d:\WebstormProjects\carebank-frontend
npm install
npm run dev
# UI runs on http://localhost:5173
```

### Start Mock Bank
```bash
cd d:\PycharmProjects\carebank-mockbank
python main.py
# MockBank runs on http://localhost:5000
```

### Start Redis (for real-time events)
```bash
# Install Redis, then:
redis-server
```

---

## Common Questions

### Q1: Why 5 agents instead of 1 big LLM?
**A**: Specialization beats generalization. One doctor can't be expert in cardiology, pediatrics, and surgery simultaneously. Same for finance. Each agent:
- Has domain knowledge built in
- Can't contradict other agents
- Can be tested independently
- Can be swapped/upgraded separately

### Q2: What if an LLM starts hallucinating?
**A**: Two layers stop it:
1. **Deterministic Core** - All numbers are calculated, not generated
2. **Compliance Guard** - Validates every output against rules

Even if an LLM says "You have ₹1 trillion", the Core says "No, the real balance is ₹25,000."

### Q3: What makes this different from ChatGPT?
**A**: 
- **ChatGPT**: General AI, can hallucinate numbers, no financial expertise
- **CareBank**: 
  - Specialized agents with domain rules
  - Deterministic calculations for all numbers
  - Compliance enforcement
  - Real banking data integration
  - Audit trail for regulation

### Q4: How is user data protected?
**A**: 
- Bank API credentials stored securely (environment variables)
- All communication over HTTPS
- Redis events are internal (no external broadcast)
- Audit logs for compliance review
- No personal data stored permanently (mock data only in MVP)

### Q5: What's the difference between what Intelligence and Communication agents do?
**A**:
- **Intelligence**: Analyzes data, runs ML models, produces insights
- **Communication**: Takes those insights, explains them in human language, handles user interaction

Intelligence is the brain. Communication is the mouth.

---

## Architecture Benefits

✅ **Modularity** - Each agent is independent  
✅ **Scalability** - Can add more agents without breaking existing ones  
✅ **Safety** - Compliance layer blocks harmful outputs  
✅ **Auditability** - Every decision is logged  
✅ **Accuracy** - Deterministic calculations, no hallucination  
✅ **Real-time** - Redis Pub/Sub for instant updates  
✅ **Testability** - Each agent can be unit tested separately  

---

## What Happens Next (Future Phases)

### Phase 1 ✅ (Complete)
- Health Score calculation
- Deterministic Core
- MockBank integration

### Phase 2
- Coordinator Agent routing
- All 5 agents fully functional

### Phase 3
- Compliance Guard enforcement
- Regulatory audit log

### Phase 4
- Real Banking API integration (replace MockBank)
- User authentication
- Production database (PostgreSQL)

---

## Debugging Tips

### Health Score not updating?
1. Check MockBank is running: `GET http://localhost:5000/balances`
2. Check Redis is listening: `redis-cli ping`
3. Check backend logs: `tail -f carebank-backend/app.log`

### Agent returning wrong response?
1. Check Coordinator routing: What intent was classified?
2. Check agent input: What data did it receive?
3. Check Compliance Guard output: Was it modified?

### Frontend not connecting?
1. Check backend is running: `curl http://localhost:8000/health`
2. Check CORS settings in FastAPI
3. Check WebSocket endpoint for real-time updates

---

## Summary Diagram

```
┌────────────────────────────────────────────────────────┐
│                  CAREBANK SYSTEM                       │
├────────────────────────────────────────────────────────┤
│                                                        │
│  FRONTEND (React UI)                                   │
│  ├─ Health Score meter                                │
│  ├─ Chat interface                                    │
│  ├─ What-If simulator                                 │
│  └─ Notifications                                     │
│         │                                              │
│         │ REST API                                    │
│         ▼                                              │
│  COORDINATOR AGENT                                     │
│  ├─ Route requests                                    │
│  ├─ Maintain state                                    │
│  └─ Log interactions                                  │
│         │                                              │
│  ┌──────┴──────┬──────────┬──────────┬──────────┐    │
│  │             │          │          │          │    │
│  ▼             ▼          ▼          ▼          ▼    │
│ Intel    Comm      Opport    Auto-S   (+ more)     │
│ Agent    Agent     Agent     Agent                   │
│         │                                              │
│         ▼                                              │
│  DETERMINISTIC CORE (All calculations)                │
│  └─ Verified, auditable numbers                       │
│         │                                              │
│         ▼                                              │
│  COMPLIANCE GUARD (Safety)                            │
│  └─ Validate, block, log                              │
│         │                                              │
│  ↓ ↓ ↓ DATA SOURCES ↓ ↓ ↓                            │
│                                                        │
│  MockBank API ←← Redis Pub/Sub ←← Real API            │
│  (Test data)       (Events)      (Future)             │
│                                                        │
└────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Understand each agent**: Read the feature guides in `.github-private/docs/FEATURE-GUIDES/`
2. **Run the system**: Follow the startup commands above
3. **Trace a message**: Use the data flow diagrams to understand request path
4. **Read the code**: Start with `coordinator.py`, then each agent
5. **Run tests**: `pytest` to verify functionality

---

**Last Updated**: March 5, 2026  
**Status**: MVP Phase 1 Complete  
**Next Review**: Post-Phase 2 completion  

---

💡 **Pro Tip**: This guide pairs with the feature guides in `.github-private/docs/FEATURE-GUIDES/` for deep dives into specific components.
