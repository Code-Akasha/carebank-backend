#!/usr/bin/env bash

set -e

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOCKBANK_DIR="$BACKEND_DIR/../carebank-mockbank"
FRONTEND_DIR="$(cd "$BACKEND_DIR/../../WebstormProjects/carebank-frontend" 2>/dev/null && pwd || echo "$BACKEND_DIR/../../WebstormProjects/carebank-frontend")"
RUN_MOCKBANK="${RUN_MOCKBANK:-1}"
RUN_FRONTEND="${RUN_FRONTEND:-1}"

# --- Setup .env files if missing ---
if [ ! -f "$BACKEND_DIR/.env" ]; then
  echo "[INFO] Creating default .env for Backend..."
  cat <<'EOT' > "$BACKEND_DIR/.env"
DB_HOST=localhost
DB_PORT=5432
DB_USER=carebank
DB_PASSWORD=carebank_pwd
DB_NAME=carebank_db
REDIS_URL=redis://localhost:6379
BANKING_API_URL=http://localhost:8001
BANKING_API_SECRET=supersecret123
OPENAI_API_KEY=your-api-key-here
EOT
fi

if [ ! -f "$MOCKBANK_DIR/.env" ]; then
  echo "[INFO] Creating default .env for MockBank..."
  mkdir -p "$MOCKBANK_DIR"
  cat <<'EOT' > "$MOCKBANK_DIR/.env"
BANKING_API_SECRET=supersecret123
EOT
fi

load_env_file() {
  local env_file="$1"
  if [ ! -f "$env_file" ]; then
    return 0
  fi

  while IFS= read -r line || [ -n "$line" ]; do
    if [ -z "$line" ] || [ "${line:0:1}" = "#" ]; then
      continue
    fi

    if ! echo "$line" | grep -q "="; then
      continue
    fi

    local key="${line%%=*}"
    local value="${line#*=}"
    if [ -n "$value" ] && [ "${value:0:1}" = '"' ] && [ "${value: -1}" = '"' ]; then
      value="${value:1:-1}"
    fi
    if [ -n "$key" ]; then
      export "$key=$value"
    fi
  done <"$env_file"
}

load_env_file "$BACKEND_DIR/.env"
load_env_file "$MOCKBANK_DIR/.env"

: "${DB_HOST:=localhost}"
: "${DB_PORT:=5432}"
: "${DB_USER:=carebank}"
: "${DB_NAME:=carebank_db}"
: "${REDIS_URL:=redis://localhost:6379}"
: "${BANKING_API_URL:=http://localhost:8001}"
: "${PG_SUPERUSER_HOST:=$DB_HOST}"
: "${PG_SUPERUSER_PORT:=$DB_PORT}"
: "${PG_SUPERUSER_USER:=postgres}"
: "${PG_SUPERUSER_DB:=postgres}"
if [ -z "${PG_SUPERUSER_PASSWORD:-}" ] && [ -n "${DB_PASSWORD:-}" ]; then
  PG_SUPERUSER_PASSWORD="$DB_PASSWORD"
  export PG_SUPERUSER_PASSWORD
fi

if [ -z "${MOCKBANK_JWT_SECRET:-}" ] && [ -n "${BANKING_API_SECRET:-}" ]; then
  MOCKBANK_JWT_SECRET="$BANKING_API_SECRET"
  export MOCKBANK_JWT_SECRET
fi
if [ -z "${JWT_SECRET:-}" ] && [ -n "${BANKING_API_SECRET:-}" ]; then
  JWT_SECRET="$BANKING_API_SECRET"
  export JWT_SECRET
fi

MOCK_BANK_URL="$BANKING_API_URL"
export MOCK_BANK_URL

if [ ! -f "$MOCKBANK_DIR/main.py" ]; then
  echo "[WARN] Could not find carebank-mockbank at $MOCKBANK_DIR"
  RUN_MOCKBANK="0"
fi

if [ ! -f "$FRONTEND_DIR/package.json" ]; then
  echo "[WARN] Could not find carebank-frontend at $FRONTEND_DIR"
  RUN_FRONTEND="0"
fi

# --- Setup Python Virtual Environments ---
setup_python_env() {
  local dir="$1"
  echo "Setting up Python environment for $dir..."
  if [ ! -d "$dir/.venv" ]; then
    python3 -m venv "$dir/.venv"
  fi
  if [ -f "$dir/requirements.txt" ]; then
    "$dir/.venv/bin/pip" install -q -r "$dir/requirements.txt"
  fi
}

echo "Configuring virtual environments..."
setup_python_env "$BACKEND_DIR"
if [ "$RUN_MOCKBANK" = "1" ]; then
  setup_python_env "$MOCKBANK_DIR"
fi

if [ "$RUN_MOCKBANK" = "1" ] && [ -x "$MOCKBANK_DIR/.venv/bin/pip" ]; then
  "$MOCKBANK_DIR/.venv/bin/pip" install -q python-dotenv
fi

echo "Initialising database tables..."
cd "$BACKEND_DIR"
export DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME
./.venv/bin/python scripts/setup_postgres.py

if [ "$RUN_MOCKBANK" = "1" ]; then
  echo "Starting MockBank API on port 8001..."
  if [ -f "$MOCKBANK_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    (cd "$MOCKBANK_DIR" && source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8001 --reload) &
  else
    (cd "$MOCKBANK_DIR" && uvicorn main:app --host 0.0.0.0 --port 8001 --reload) &
  fi
else
  echo "[WARN] Skipping MockBank startup."
fi

echo "Starting CareBank Backend on port 8000..."
if [ -f "$BACKEND_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  (cd "$BACKEND_DIR" && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
else
  (cd "$BACKEND_DIR" && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
fi

wait_for_backend() {
  local wait_url="http://localhost:8000/docs"
  local max_attempts=20
  local attempt=1

  while [ $attempt -le $max_attempts ]; do
    if curl -fsS --max-time 2 "$wait_url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done

  return 1
}

echo "Waiting for backend to become ready..."
if wait_for_backend; then
  echo "[OK] Backend is ready!"
else
  echo "[WARN] Backend not responding yet, starting frontend anyway..."
fi

echo "Seeding demo users (skips existing)..."
cd "$BACKEND_DIR"
./.venv/bin/python scripts/register_demo_users.py

if [ "$RUN_FRONTEND" = "1" ]; then
  echo "Starting CareBank Frontend on port 5173..."
  if [ -d "$FRONTEND_DIR/node_modules" ]; then
    (cd "$FRONTEND_DIR" && npm run dev -- --host 0.0.0.0 --port 5173) &
  else
    (cd "$FRONTEND_DIR" && npm install && npm run dev -- --host 0.0.0.0 --port 5173) &
  fi
else
  echo "[WARN] Skipping Frontend startup."
fi

echo "Startup completed without interactive CLI prompts."
