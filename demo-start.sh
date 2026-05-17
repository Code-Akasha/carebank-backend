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
echo "║           CareBank Demo Launcher                         ║"
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

# ── Seeding Disabled ──────────────────────────────────────────────────
echo -e "${GREEN}[4/5] Seeding skipped (Manual Setup Mode Enabled)${NC}"

# ── Done ──────────────────────────────────────────────────────────────
echo -e "${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║           CAREBANK IS READY (CLEAN SLATE)!               ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  Frontend:    cd ../carebank-frontend && npm run dev     ║"
echo "║              → http://localhost:5173                     ║"
echo "║  Backend:     http://localhost:8000/docs                 ║"
echo "║  Proxy:       http://localhost:8001/docs                 ║"
echo "║                                                          ║"
echo "║  Manual Setup Instructions:                              ║"
echo "║  1. Open http://localhost:5173                           ║"
echo "║  2. Click 'Register' and create a new account manually   ║"
echo "║  3. The proxy profile and default settings will be       ║"
echo "║     auto-created on signup!                              ║"
echo "║                                                          ║"
echo "║  Stop:  docker compose -f docker-compose.full.yml down   ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "\n${CYAN}Manual Test Flow:${NC}"
echo "  1. Start frontend: cd ../carebank-frontend && npm run dev"
echo "  2. Register your user at http://localhost:5173"
echo "  3. Log in and verify your dashboard (starts with initial balance)"
echo "  4. Create beneficiaries and set up payments manually"

