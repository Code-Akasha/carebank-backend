@echo off
echo Committing changes in logical groups...

REM Commit 1: Database migration changes
git add alembic/env.py
git commit -m "feat: add user_mpin model import to alembic migration"

REM Commit 2: API schema updates
git add app/schemas/models.py
git commit -m "feat: add TransactionTriggerCreate schema for transaction API"

REM Commit 3: Route updates
git add app/routes/transactions.py
git commit -m "refactor: use TransactionTriggerCreate schema in transaction trigger endpoint"

REM Commit 4: Startup script improvements
git add startup.bat
git commit -m "improve: enhance startup script with better error handling and optional component flags"

echo All commits completed!
pause