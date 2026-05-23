# CHANGES.md — Architecture Documentation

> Files created on 2026-05-21

## New Files

| File | Description | Diagrams |
|---|---|---|
| `architecture/README.md` | Index with system overview, table of contents, presentation guide | 1 × component |
| `architecture/01-user-onboarding.md` | Signup → proxy profile seed → MPIN setup | 1 × sequence |
| `architecture/02-authentication-sessions.md` | Login, JWT lifecycle, dual-JWT architecture | 3 × sequence, 1 × component |
| `architecture/03-agent-pipeline.md` | Chat → Coordinator → specialist → NLG → compliance | 2 × component, 1 × sequence |
| `architecture/04-health-score.md` | 4-factor deterministic health score pipeline | 2 × flow, 1 × sequence |
| `architecture/05-what-if-simulator.md` | Expense simulation with risk classification | 2 × sequence |
| `architecture/06-transaction-lifecycle.md` | Initiation → proxy → webhook → reconciliation | 1 × state, 1 × sequence |
| `architecture/07-recurring-payments.md` | APScheduler cron, approval flow, manual trigger | 1 × state, 1 × sequence |
| `architecture/08-auto-savings.md` | Forecast surplus, safety threshold, recommendation | 1 × flow, 1 × sequence |
| `architecture/09-action-engine.md` | Two-phase proposal/execution, retries, idempotency | 1 × flow, 1 × sequence |
| `architecture/10-realtime-events.md` | SSE, Redis pub/sub, Telegram, reconnection | 1 × component, 2 × sequence |
| `architecture/11-admin-observability.md` | Admin dashboard, LLM config, dead letters, audit | 2 × component, 1 × sequence |
| `architecture/12-security-compliance.md` | Auth layers, MPIN, compliance guard, CORS, secrets | 2 × component, 1 × sequence, 1 × flow |
| `architecture/13-core-topology.md` | Unified architecture, context management, Telegram, Nudges | 2 × component, 2 × sequence |
| `architecture/CHANGES.md` | This file — diff summary | — |

## Summary

- **15 files** created in `architecture/`
- **13 workflow documents** + 1 index + 1 changelog
- **~29 Mermaid diagrams** embedded (sequence, component, flow, state)
- **12 example scenarios** with concrete JSON payloads
- **12 decision tables** mapping triggers → actions → outcomes
- **0 application code changes** — documentation only

## Diagram Formats

All diagrams use **embedded Mermaid** syntax compatible with:
- GitHub Markdown rendering
- Obsidian (native Mermaid support)
- VS Code Markdown Preview (with Mermaid extension)
- Any Mermaid-compatible renderer

No external image files needed — diagrams render inline from the fenced code blocks.
