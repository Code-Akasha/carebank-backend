---
trigger: always_on
---

# 🔄 Git Sync Rule

> **MANDATORY:** Always fetch the latest remote state before making any code edits or commits.

## Before ANY File Edits

1. Run `git fetch origin` to get the latest remote state
2. Check if the current branch is behind: `git status -uno`
3. If behind, pull/rebase before editing: `git pull --rebase`

## Why This Matters

- Prevents merge conflicts caused by editing stale files
- Ensures you're always building on top of the latest team changes
- Avoids painful force-push scenarios after failed PRs

## Rule

```
❌ WRONG: Start editing files → commit → push → discover conflicts
✅ CORRECT: git fetch → check if behind → rebase if needed → THEN edit → commit → push
```

> 🔴 **This rule applies at the START of every session and before every `/commit` workflow.**
