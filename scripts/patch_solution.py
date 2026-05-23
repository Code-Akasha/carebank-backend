file_path = "d:/PycharmProjects/carebank-backend/.agent/project/SOLUTION.md"
with open(file_path, encoding="utf-8") as f:
    content = f.read()

# Replace Architecture Block
old_arch = """┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React/React Native)            │
│  • Dashboard with Financial Health Score meter              │
│  • What-If simulator input                                  │
│  • Notification center                                      │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              Coordinator Agent (LangGraph)                  │
│  • Maintains user session state                             │
│  • Routes queries to specialized agents                     │
│  • Logs all interactions for audit                          │
│  • Single source of truth for conversation                  │
└─────────────────────────────────────────────────────────────┘"""

new_arch = """┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React/React Native)            │
│  • Dashboard with Financial Health Score meter              │
│  • Auth Login & Admin Observability View                    │
└─────────────────────────────────────────────────────────────┘
                              │ (JWT via Header)
┌─────────────────────────────────────────────────────────────┐
│                    Auth Layer & API Gateway                 │
│  • Validates JWTs, injects isolated `user_id` context       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              Coordinator Agent (LangGraph)                  │
│  • Scopes all conversations strictly to `user_id`           │
│  • Offloads heavy tasks to Task Queue                       │
│  • Logs interactions to Event Ledger                        │
└─────────────────────────────────────────────────────────────┘
                              │ (via Background Task Queue / Celery)"""

content = content.replace(old_arch, new_arch)

# Add Task Workers & Admin roles
old_roles = """| **Coordinator** | Routes all requests, maintains state, logs interactions | LangGraph with memory |
| **Intelligence Agent** | Persona clustering, forecasting, anomaly detection | Prophet + Scikit-learn |
| **Communication Agent** | Nudge timing (heuristics) + all NLG | LLM (GPT-4/Claude) + rule-based fatigue control |
| **Opportunity Agent** | Subscription detection + product matching | Pattern matching + RAG + deterministic rules |
| **Auto-Savings Agent** | Micro-transfer simulation and execution (with approval) | Rule-based optimizer + LLM explanations |
| **Deterministic Core** | ALL financial calculations | Pure Python/Java functions |
| **Compliance Guard** | Intercepts and validates outputs | Rule-based + LLM validator |"""

new_roles = """| **Coordinator** | Routes requests natively scoped to user_id context | LangGraph + Auth Layer |
| **Intelligence Agent** | Forecasts (offloaded to workers) | Scikit-learn + FastAPI Background Tasks/Celery |
| **Communication Agent** | Nudges (offloaded to workers) | LLM rate limits + Message Queue |
| **Opportunity Agent** | Subscription detection + product matching | Pattern matching + RAG + deterministic rules |
| **Auto-Savings Agent** | Micro-transfer simulation and execution | Rule-based optimizer + LLM explanations |
| **Deterministic Core** | ALL financial calculations | Pure Python/Java functions |
| **Compliance Guard** | Intercepts and validates outputs | Rule-based + LLM validator |
| **Observability (New)**| Real-time system health and auditable action ledgers | Event Logger DB + Admin Dashboard UI |"""

content = content.replace(old_roles, new_roles)

# Change Architecture slide note
content = content.replace(
    "- Architecture slide showing 5 agents + Coordinator",
    "- Architecture slide highlighting Auth, Task Queue, Admin Dashboard, and 5 Agents",
)

# Update Tech Stack
old_stack = """| **Backend** | FastAPI | Fast to build, easy to demo |
| **Database** | PostgreSQL + pgvector | One stack for both structured + vector |
| **Forecasting** | Prophet | 10 lines of code, works on small data |
| **Clustering** | Scikit-learn K-means | Simple, explainable |
| **Anomaly Detection** | Isolation Forest | One import, works |
| **LLM** | OpenAI GPT-4 (API) | Reliable generation, focus on orchestration |
| **Vector Store** | pgvector | No extra infra |"""

new_stack = """| **Backend Layer** | FastAPI + pyjwt | Scales gracefully, enforces secure JWT multi-tenancy |
| **Background Processing** | Celery + Redis | Prevents blocking HTTP loops during heavy Prophet/LLM execution |
| **Database** | PostgreSQL + pgvector | Immutable `AgentLogs` + User Isolation, Structured + Vectors |
| **Forecasting** | Prophet | Time-series forecasting, wrapped in Task Workers |
| **Clustering** | Scikit-learn K-means | Unsupervised profiling |
| **Anomaly Detection** | Isolation Forest | Predicts high volatility |
| **LLM Inference** | OpenAI GPT-4 | Rate-limited and batched via workers to prevent bottlenecks |"""

content = content.replace(old_stack, new_stack)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated SOLUTION.md successfully!")
