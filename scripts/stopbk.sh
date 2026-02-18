#!/bin/bash

# =============================================================================
# mCube-ai Background Services Stop Script
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Dynamically determine project directory (parent of scripts/)
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

echo -e "${YELLOW}=== Stopping mCube-ai Background Services ===${NC}"

# Stop Celery processes gracefully
pkill -TERM -f "celery.*mcube_ai" 2>/dev/null

sleep 2

# Force kill if still running
pkill -9 -f "celery.*mcube_ai" 2>/dev/null

# Clean up PID files
rm -f "$PROJECT_DIR/logs/pids/"*.pid 2>/dev/null

echo -e "${GREEN}[OK] All Celery services stopped${NC}"
