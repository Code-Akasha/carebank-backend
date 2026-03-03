@echo off
setlocal ENABLEDELAYEDEXPANSION

REM --- Shared credentials ---
set "MOCKBANK_JWT_SECRET=3d15aa43fbe1494ab21fb2e4f7c6b721"
set "DB_HOST=localhost"
set "DB_PORT=5432"
set "DB_USER=carebank"
set "DB_PASSWORD=Jefino 1537"
set "DB_NAME=carebank_db"
set "REDIS_URL=redis://localhost:6379"
set "MOCK_BANK_URL=http://localhost:8001"

REM --- Directories ---
set "BACKEND_DIR=%~dp0"
set "MOCKBANK_DIR=%~dp0..\carebank-mockbank"

if not exist "%MOCKBANK_DIR%\main.py" (
    echo [WARN] Could not find carebank-mockbank at %MOCKBANK_DIR%
    set /p MOCKBANK_DIR="Enter absolute path to carebank-mockbank: "
)

REM --- Install python-dotenv in mockbank venv if missing ---
if exist "%MOCKBANK_DIR%\.venv\Scripts\pip.exe" (
    "%MOCKBANK_DIR%\.venv\Scripts\pip.exe" install -q python-dotenv
)

REM --- Initialise PostgreSQL tables ---
echo Initialising database tables...
cd /d "%BACKEND_DIR%"
if exist ".venv\Scripts\activate" (
    call .venv\Scripts\activate
    set DB_HOST=%DB_HOST%
    set DB_PORT=%DB_PORT%
    set DB_USER=%DB_USER%
    set DB_PASSWORD=%DB_PASSWORD%
    set DB_NAME=%DB_NAME%
    python scripts\setup_postgres.py
)

REM --- Start MockBank ---
echo Starting MockBank API on port 8001...
if exist "%MOCKBANK_DIR%\.venv\Scripts\activate" (
    start "MockBank API" cmd /k "cd /d %MOCKBANK_DIR% && call .venv\Scripts\activate && uvicorn main:app --host 0.0.0.0 --port 8001 --reload"
) else (
    start "MockBank API" cmd /k "cd /d %MOCKBANK_DIR% && uvicorn main:app --host 0.0.0.0 --port 8001 --reload"
)

REM --- Start Backend ---
echo Starting CareBank Backend on port 8000...
if exist "%BACKEND_DIR%\.venv\Scripts\activate" (
    start "CareBank Backend" cmd /k "cd /d %BACKEND_DIR% && call .venv\Scripts\activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
) else (
    start "CareBank Backend" cmd /k "cd /d %BACKEND_DIR% && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
)

echo Waiting for services to start...
timeout /t 6 /nobreak >nul

echo Launching CareBank Dashboard CLI...
cd /d "%BACKEND_DIR%"
if exist ".venv\Scripts\activate" (
    call .venv\Scripts\activate
)
set MOCKBANK_JWT_SECRET=%MOCKBANK_JWT_SECRET%
set DB_HOST=%DB_HOST%
set DB_PORT=%DB_PORT%
set DB_USER=%DB_USER%
set DB_PASSWORD=%DB_PASSWORD%
set DB_NAME=%DB_NAME%
set REDIS_URL=%REDIS_URL%
set MOCK_BANK_URL=%MOCK_BANK_URL%
python scripts\dashboard_cli.py


