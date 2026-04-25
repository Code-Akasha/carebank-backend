@echo off
setlocal ENABLEDELAYEDEXPANSION

REM --- Directories ---
set "BACKEND_DIR=%~dp0"
set "MOCKBANK_DIR=%~dp0..\carebank-mockbank"
set "FRONTEND_DIR=D:\WebstormProjects\carebank-frontend"
set "RUN_MOCKBANK=1"
set "RUN_FRONTEND=1"

if not exist "%BACKEND_DIR%\.env" (
    echo [WARN] Backend .env not found at %BACKEND_DIR%\.env
)

call :load_env_file "%BACKEND_DIR%\.env"
call :load_env_file "%MOCKBANK_DIR%\.env"

if not defined DB_HOST set "DB_HOST=localhost"
if not defined DB_PORT set "DB_PORT=5432"
if not defined DB_USER set "DB_USER=carebank"
if not defined DB_NAME set "DB_NAME=carebank_db"
if not defined REDIS_URL set "REDIS_URL=redis://localhost:6379"
if not defined BANKING_API_URL set "BANKING_API_URL=http://localhost:8001"
if not defined PG_SUPERUSER_HOST set "PG_SUPERUSER_HOST=%DB_HOST%"
if not defined PG_SUPERUSER_PORT set "PG_SUPERUSER_PORT=%DB_PORT%"
if not defined PG_SUPERUSER_USER set "PG_SUPERUSER_USER=postgres"
if not defined PG_SUPERUSER_DB set "PG_SUPERUSER_DB=postgres"
if not defined PG_SUPERUSER_PASSWORD (
    if defined DB_PASSWORD set "PG_SUPERUSER_PASSWORD=%DB_PASSWORD%"
)

if not defined MOCKBANK_JWT_SECRET (
    if defined BANKING_API_SECRET set "MOCKBANK_JWT_SECRET=%BANKING_API_SECRET%"
)
if not defined JWT_SECRET (
    if defined BANKING_API_SECRET set "JWT_SECRET=%BANKING_API_SECRET%"
)

set "MOCK_BANK_URL=%BANKING_API_URL%"

if not exist "%MOCKBANK_DIR%\main.py" (
    echo [WARN] Could not find carebank-mockbank at %MOCKBANK_DIR%
    set "RUN_MOCKBANK=0"
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [WARN] Could not find carebank-frontend at %FRONTEND_DIR%
    set "RUN_FRONTEND=0"
)

REM --- Install python-dotenv in mockbank venv if missing ---
if "%RUN_MOCKBANK%"=="1" if exist "%MOCKBANK_DIR%\.venv" (
    cmd /c "cd /d %MOCKBANK_DIR% && uv pip install -q python-dotenv"
)

REM --- Initialise PostgreSQL tables ---
echo Initialising database tables...
cd /d "%BACKEND_DIR%"
set DB_HOST=%DB_HOST%
set DB_PORT=%DB_PORT%
set DB_USER=%DB_USER%
set DB_PASSWORD=%DB_PASSWORD%
set DB_NAME=%DB_NAME%
uv run scripts\setup_postgres.py

REM --- Start MockBank ---
if "%RUN_MOCKBANK%"=="1" (
    echo Starting MockBank API on port 8001...
    start "MockBank API" cmd /k "cd /d %MOCKBANK_DIR% && uv run uvicorn main:app --host 0.0.0.0 --port 8001 --reload"
) else (
    echo [WARN] Skipping MockBank startup.
)

REM --- Start Backend ---
echo Starting CareBank Backend on port 8000...
start "CareBank Backend" cmd /k "cd /d %BACKEND_DIR% && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

REM --- Wait for Backend before starting Frontend ---
echo Waiting for backend to become ready...
call :wait_for_backend
if errorlevel 1 (
    echo [WARN] Backend not responding yet, starting frontend anyway...
) else (
    echo [OK] Backend is ready!
)

REM --- Seed demo users before frontend starts ---
echo Seeding demo users ^(skips existing^)...
cd /d "%BACKEND_DIR%"
uv run scripts\register_demo_users.py

REM --- Start Frontend (after backend is confirmed ready) ---
if "%RUN_FRONTEND%"=="1" (
    echo Starting CareBank Frontend on port 5173...
    if exist "%FRONTEND_DIR%\node_modules" (
        start "CareBank Frontend" cmd /k "cd /d %FRONTEND_DIR% && npm run dev -- --host 0.0.0.0 --port 5173"
    ) else (
        start "CareBank Frontend" cmd /k "cd /d %FRONTEND_DIR% && npm install && npm run dev -- --host 0.0.0.0 --port 5173"
    )
) else (
    echo [WARN] Skipping Frontend startup.
)

echo Startup completed without interactive CLI prompts.

goto :eof

:wait_for_backend
set "WAIT_URL=http://localhost:8000/docs"
set "MAX_ATTEMPTS=20"
for /L %%I in (1,1,%MAX_ATTEMPTS%) do (
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%WAIT_URL%' -UseBasicParsing -TimeoutSec 2 ^| Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
    if not errorlevel 1 exit /b 0
    timeout /t 1 /nobreak >nul
)
exit /b 1

:load_env_file
set "ENV_FILE=%~1"
if not exist "%ENV_FILE%" goto :eof
for /f "usebackq tokens=* delims=" %%L in ("%ENV_FILE%") do (
    set "line=%%L"
    if not "!line!"=="" if not "!line:~0,1!"=="#" (
        for /f "tokens=1* delims==" %%A in ("!line!") do (
            set "k=%%A"
            set "v=%%B"
            if not "!k!"=="" (
                if defined v (
                    if "!v:~0,1!"=="\"" if "!v:~-1!"=="\"" set "v=!v:~1,-1!"
                    set "!k!=!v!"
                )
            )
        )
    )
)
goto :eof


