# CareBank Project Configuration

> **Runtime instructions for AI agents working on this project.**

---

## 📋 Phase Plans Directory

All implementation plans are stored in `.agent/project/plans/`:

```
.agent/project/plans/
├── README.md
├── backend/          # Backend (carebank-backend) phase plans
│   ├── PLAN-phase1-infrastructure.md       ✅ COMPLETE
│   └── PLAN-phase2-agent-orchestration.md  ⬜ PENDING
└── frontend/         # Frontend (carebank-frontend) phase plans
    └── PLAN-phase1-shell-setup.md          ✅ COMPLETE
```

**Before starting any implementation:**
1. Check `.agent/project/plans/backend/` or `frontend/` for the relevant phase plan
2. If no plan exists, create one using `/plan` workflow
3. Reference `SOLUTION.md` and `.github-private/docs/FEATURE-GUIDES/` for specifications

## 📖 Key Documentation

| Document | Path | Purpose |
|----------|------|---------|
| Solution Architecture | `.agent/project/SOLUTION.md` | Full system design, agents, features |
| Problem Statement | `.agent/project/PROBLEM_STATEMENT.md` | Hackathon requirements |
| Feature Guides | `.github-private/docs/FEATURE-GUIDES/` | Per-component implementation specs |
| MVP Phases | `.github-private/docs/MVP-PHASES.md` | 6-phase timeline with dependencies |
| Tech Stack | `.github-private/docs/TECH-STACK.md` | Technology choices and setup |
