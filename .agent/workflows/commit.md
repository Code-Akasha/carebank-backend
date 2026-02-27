---
description: Commit and push changes to the appropriate branch following project rules.
---

# /commit - Commit and Push Changes

$ARGUMENTS

---

## Task

This workflow automates the process of committing and pushing changes to the correct feature branch or develop branch, adhering to the project's Git workflow rules.

### Steps:

// turbo
1. **Fetch Latest Changes (MANDATORY)**
   - Always fetch the latest remote state before anything else: `git fetch origin`
   - Check if the current branch is behind its remote: `git status -uno`
   - If behind, rebase onto the latest: `git pull --rebase origin <current-branch>` or `git rebase origin/develop` if on a feature branch
   - **This step prevents merge conflicts on push and ensures we're always working on the latest code.**

2. **Verify Current State & Branch**
   - Check the git status to see what has changed.
   - Determine the correct branch based on the modified files and the `GEMINI.md` branching rules.
   - If currently on `main`, or if the requested branch doesn't exist locally, create and checkout the appropriate branch using `git checkout -b <branch-name>`.
   - **Backend feature branches**: `feature/coordinator-agent`, `feature/intelligence-agent`, `feature/health-score`, `feature/what-if-simulation`, `feature/auto-savings`, `feature/opportunity-agent`, `feature/compliance-guard`, `feature/mockbank-integration`
   - **Frontend feature branches**: `feature/dashboard-layout`, `feature/health-score-meter`, `feature/transaction-list`, `feature/what-if-ui`, `feature/notification-system`, `feature/autosavings-approval`, `feature/api-integration`
   - **Remember: No direct commits to `main`.**

// turbo
3. **Add Files**
   - Stage the changes using `git add <files>` or `git add .` if appropriate.

// turbo
4. **Commit Changes**
   - Generate a conventional commit message (format: `<type>(<scope>): <subject>`) based on the staged changes.
   - Commit the changes using `git commit -m "..."`.

// turbo
5. **Push to Remote**
   - Push the branch to the remote repository.
   - If the branch is new on the remote, set the upstream: `git push -u origin <branch-name>`
   - Otherwise, just push: `git push`

6. **Provide PR Instructions**
   - Notify the user of the successful push.
   - Remind the user that a Pull Request is required to merge into `develop` (and eventually `main`).

---

## Usage Examples

```
/commit
/commit message="feat(auth): added login page"
/commit branch="feature/dashboard-layout"
```

---

## Caution

- **Always fetch before committing** — stale branches cause merge conflicts.
- Always strictly observe the project's branch naming conventions.
- Never commit to `main` directly.
- Ensure the commit message format strictly follows conventional commits.
- If rebase conflicts occur, resolve them before proceeding.
