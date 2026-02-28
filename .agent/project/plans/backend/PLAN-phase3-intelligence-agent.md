# Phase 3: Intelligence Agent — Prophet, Clustering & Anomaly Detection (Hours 12-20)

> **Status: PENDING** | Branch: `feature/intelligence-agent`
> **References:** [Intelligence Agent Guide](file:///d:/WebstormProjects/.github-private/docs/FEATURE-GUIDES/intelligence-agent.md) · [Health Score Guide](file:///d:/WebstormProjects/.github-private/docs/FEATURE-GUIDES/health-score.md)

---

## Goal

Replace the Intelligence Agent stub with real ML capabilities: time-series forecasting (Prophet), user persona clustering (K-Means), and anomaly detection (Isolation Forest). Also build the Health Score service layer that connects Intelligence Agent forecasts to the existing Deterministic Core calculations.

## Dependencies

- ✅ Phase 1: Deterministic Core (`finance.py`), Transaction model, Balance model
- ✅ Phase 2: BaseAgent interface, CoordinatorState machine, audit logging
- MockBank transaction data (already available via `carebank-mockbank`)

## New Dependencies to Install

```
prophet>=1.1.0
scikit-learn>=1.4.0
pandas>=2.2.0
numpy>=1.26.0
```

---

## Tasks

### Task 1: Install ML Dependencies
- Add `prophet`, `scikit-learn`, `pandas`, `numpy` to `requirements.txt`
- `pip install -r requirements.txt`
- **Verify:** `python -c "from prophet import Prophet; print('OK')"`

> [!WARNING]
> Prophet has heavy native dependencies (cmdstanpy). If installation fails on Windows, use `prophet` with `cmdstanpy` backend or fallback to a simpler linear regression for the demo.

---

### Task 2: Forecasting Service (`app/services/forecast.py`)

**Implements Prophet time-series forecasting.**

```python
# Core function signature
def forecast_balance(transactions: list[dict], periods: int = 30) -> dict:
    """
    Input:  List of transactions [{date, amount, category}]
    Output: {
        predicted_balance: float,
        lower_bound: float,
        upper_bound: float,
        forecast_error: float,  # feeds into Health Score confidence factor
        daily_forecast: list    # for frontend chart
    }
    """
```

**Implementation details:**
- Convert transactions to Prophet format: `ds` (date), `y` (cumulative daily balance or daily net spend)
- Use `Prophet(interval_width=0.9)` for 90% confidence intervals
- Handle edge cases: < 10 data points → fallback to simple linear extrapolation
- Calculate `forecast_error` as normalized confidence interval width (feeds Health Score)

**Verify:** Given 30+ mock transactions, returns a valid forecast with confidence bounds.

---

### Task 3: Persona Clustering Service (`app/services/clustering.py`)

**Implements K-Means persona clustering.**

```python
# Core function signature
def cluster_persona(spending_profile: dict) -> dict:
    """
    Input:  {food: 0.35, transport: 0.15, entertainment: 0.25, shopping: 0.15, bills: 0.10}
    Output: {
        persona: "Social Spender",
        cluster_id: 2,
        confidence: 0.82,
        top_category: "food"
    }
    """
```

**Implementation details:**
- Pre-define 4 personas: `["Cautious Saver", "Balanced Manager", "Social Spender", "Impulse Buyer"]`
- Feature vector: spending percentages across categories (food, transport, entertainment, shopping, bills, other)
- Use pre-fitted centroids (hardcoded from mock data analysis) — no live training needed for MVP
- Assign persona by nearest centroid distance

**Verify:** Different spending profiles map to different personas.

---

### Task 4: Anomaly Detection Service (`app/services/anomaly.py`)

**Implements Isolation Forest anomaly detection.**

```python
# Core function signature
def detect_anomaly(amount: float, history: list[float]) -> dict:
    """
    Input:  Current transaction amount + list of historical amounts
    Output: {
        is_anomaly: bool,
        anomaly_score: float,  # -1 to 1 (negative = more anomalous)
        severity: "low" | "medium" | "high"
    }
    """
```

**Implementation details:**
- `IsolationForest(contamination=0.1, random_state=42)`
- Severity mapping: score < -0.3 → high, -0.3 to -0.1 → medium, else low
- Minimum history requirement: 5 transactions (else return `is_anomaly: False`)

**Verify:** A 10x-normal transaction is flagged; a normal transaction is not.

---

### Task 5: Upgrade Intelligence Agent (`app/agents/intelligence.py`)

Replace the stub with real service calls:

```python
class IntelligenceAgent(BaseAgent):
    def _invoke(self, agent_input: AgentInput) -> AgentOutput:
        intent = agent_input.intent
        context = agent_input.context

        if intent == "health_score":
            # Call forecast service → get forecast_error
            # Call clustering service → get persona
            # Call Deterministic Core → calculate_health_score()
            ...

        elif intent == "what_if":
            # Call forecast service twice (with/without simulated expense)
            # Call Deterministic Core → forecast_impact()
            ...

        elif intent == "anomaly_check":
            # Call anomaly detection service
            ...
```

**Key principle:** Intelligence Agent **orchestrates** the ML services but delegates all financial calculations to Deterministic Core. No LLM calls here.

**Verify:** Health query returns a real computed score, not hardcoded.

---

### Task 6: Health Score Service Layer (`app/services/health_score.py`)

**Bridges Intelligence Agent data with Deterministic Core calculation.**

```python
def compute_health_score(user_id: str, transactions: list[dict], balance: float) -> dict:
    """
    1. Calculate savings_ratio from transactions (income vs expenses)
    2. Calculate expense_variance (MoM volatility)
    3. Calculate liquidity_days (balance / avg_daily_expense)
    4. Get forecast_error from forecast service
    5. Pass all 4 to Deterministic Core calculate_health_score()
    6. Add explanation text
    """
```

**Verify:** Score endpoint returns real calculations (not placeholder values from Phase 1).

---

### Task 7: Update Health Score Route (`app/routes/health_score.py`)

Replace the placeholder values in the existing route with actual service calls:
- Fetch user's transactions (from DB or MockBank)
- Fetch user's balance
- Call `health_score.compute_health_score()`
- Return enriched response with `explanation` and `trend` fields

**Verify:** `GET /api/health-score/user_001` returns dynamically computed score.

---

### Task 8: What-If Simulation Route (`app/routes/simulate.py`)

**New endpoint for the What-If Simulator feature.**

```
POST /api/simulate
Body: { user_id, expense_amount, category, description }
Response: { current_forecast, simulated_forecast, impact, explanation }
```

- Call Intelligence Agent for dual forecast
- Call Deterministic Core for impact calculation
- Determine risk_level: low (>70% balance retained), medium (30-70%), high (<30%)
- Return structured response

**Verify:** Simulating a ₹5,000 expense returns correct impact with risk assessment.

---

### Task 9: Database — Transaction Data Helper

Create `app/services/data.py` with helpers to:
- Fetch transactions for a user (from DB with fallback to MockBank API)
- Aggregate spending by category (for clustering)
- Calculate monthly income/expenses (for health score factors)

These are shared utilities used by forecast, clustering, and health score services.

**Verify:** Helper returns structured transaction data suitable for Prophet.

---

### Task 10: Tests

#### `tests/test_intelligence.py`
- Prophet: Generates valid forecast from ≥ 10 data points
- Prophet: Handles < 10 data points gracefully (fallback)
- K-Means: Returns one of 4 valid persona labels
- K-Means: Different spending profiles → different personas
- Isolation Forest: Flags 10x-normal transaction
- Isolation Forest: Normal transaction NOT flagged
- Health Score: Computes non-zero score from real transaction data
- What-If: Returns both forecasts + correct impact

**Verify:** `pytest tests/test_intelligence.py -v` passes.

---

## Done When

- [ ] Prophet generates a 30-day forecast from mock transaction data
- [ ] K-Means assigns one of 4 personas from spending profile
- [ ] Isolation Forest flags unusual transactions
- [ ] Health Score endpoint returns dynamically computed score (not placeholder)
- [ ] What-If simulation returns dual forecast + impact analysis
- [ ] All intelligence tests pass

## File Structure After Phase 3

```
app/
├── agents/
│   ├── intelligence.py   # Upgraded from stub → real ML
│   └── ...
├── services/
│   ├── forecast.py       # Prophet time-series
│   ├── clustering.py     # K-Means persona
│   ├── anomaly.py        # Isolation Forest
│   ├── health_score.py   # Score computation service
│   └── data.py           # Transaction data helpers
├── routes/
│   ├── health_score.py   # Updated with real data
│   ├── simulate.py       # NEW: What-If endpoint
│   └── ...
└── ...
```

## Notes

- Prophet works best with ≥ 2 months of daily data. For demo, generate 60-90 days of mock transactions.
- K-Means centroids are pre-computed and hardcoded — no live training during requests.
- All final numbers MUST pass through Deterministic Core. Intelligence Agent provides data/predictions, but `finance.py` does all math.
