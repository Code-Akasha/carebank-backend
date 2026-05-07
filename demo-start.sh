#!/usr/bin/env bash
# ============================================================================
# CareBank Demo Launcher
# ============================================================================
# One-command demo setup:
#   chmod +x demo-start.sh && ./demo-start.sh
#
# This script:
# 1. Starts all services via Docker Compose
# 2. Waits for them to be healthy
# 3. Seeds demo data (users, transactions, recurring payments)
# 4. Prints access URLs and credentials
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose.full.yml"
# 3. See
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║           CareBank Demo Launcher                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Stop any existing containers ──────────────────────────────────────
echo -e "${YELLOW}[1/5] Stopping any existing containers...${NC}"
docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true

# ── Build and start ───────────────────────────────────────────────────
echo -e "${YELLOW}[2/5] Building and starting services...${NC}"
docker compose -f "$COMPOSE_FILE" up -d --build

# ── Wait for health ───────────────────────────────────────────────────
echo -e "${YELLOW}[3/5] Waiting for services to be healthy...${NC}"

wait_for_service() {
    local service=$1
    local url=$2
    local max_attempts=60
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q "200\|302"; then
            echo -e "  ${GREEN}✓${NC} $service is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done
    echo ""
    echo -e "  ${RED}✗${NC} $service failed to start"
    return 1
}

echo -n "  Waiting for Agentic Proxy (8001)"
wait_for_service "Agentic Proxy" "http://localhost:8001/" || exit 1

echo -n "  Waiting for Backend (8000)"
wait_for_service "Backend" "http://localhost:8000/docs" || exit 1

echo ""

# ── Install seed dependencies if needed ──────────────────────────────
echo -e "${YELLOW}[4/5] Seeding demo data...${NC}"

# Use the backend venv or system python
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif [ -f "../carebank-backend/.venv/bin/python" ]; then
    PYTHON="../carebank-backend/.venv/bin/python"
else
    PYTHON="python3"
fi

# Install httpx and pyjwt if not present
$PYTHON -c "import httpx, jwt" 2>/dev/null || {
    echo "  Installing seed dependencies (httpx, pyjwt)..."
    $PYTHON -m pip install -q httpx pyjwt
}

# Run seed script against the Docker Postgres instance exposed on 5433.
DB_HOST=localhost \
DB_PORT=5433 \
DB_USER=carebank \
DB_PASSWORD=${POSTGRES_PASSWORD:-carebank_dev_pwd} \
DB_NAME=carebank_db \
$PYTHON scripts/demo_seed.py --backend-url http://localhost:8000 --provider-url http://localhost:8001

# ── Done ──────────────────────────────────────────────────────────────
echo -e "${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║           DEMO IS READY!                                ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                        ║"
echo "║  Frontend:    cd ../carebank-frontend && npm run dev    ║"
echo "║              → http://localhost:5173                    ║"
echo "║  Backend:     http://localhost:8000/docs                ║"
echo "║  Proxy:       http://localhost:8001/docs                ║"
echo "║                                                        ║"
echo "║  Demo Logins:                                          ║"
echo "║  rajesh@demo.com  / Demo@2026!   (GOOD health)         ║"
echo "║  priya@demo.com   / Demo@2026!   (FAIR health)         ║"
echo "║  amit@demo.com    / Demo@2026!   (POOR health)         ║"
echo "║  admin@carebank.demo / AdminCare2026!  (Admin)         ║"
echo "║                                                        ║"
echo "║  Stop:  docker compose -f docker-compose.full.yml down ║"
echo "║                                                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "\n${CYAN}Demo Flow:${NC}"
echo "  1. Start frontend: cd ../carebank-frontend && npm run dev"
echo "  2. Open http://localhost:5173"
echo "  3. Login as rajesh@demo.com (good health)"
echo "  4. Show Dashboard → Health Score (should be ~75-85)"
echo "  5. Show Transactions (3 months of history)"
echo "  6. Chat: 'schedule my Dish TV payment for 5th of every month'"
echo "  7. Show Recurring Payments page"
echo "  8. Login as admin → see all users"
echo "  9. Login as amit@demo.com → show poor health score"
