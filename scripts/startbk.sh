#!/bin/bash

# =============================================================================
# mCube-ai Background Services Startup Script
# =============================================================================
# Starts Celery Beat (scheduler) and dedicated worker pools.
#
# Worker pools (Tier 2 dedicated architecture):
#
#   worker-critical  → monitoring + risk       (concurrency: 3)
#     These tasks run every minute and must NEVER be delayed by slow
#     data fetches or large analytics jobs.
#
#   worker-trading   → strategies              (concurrency: 2)
#     Sequential strategy execution.  Low concurrency prevents two
#     strategy tasks from racing to enter the same instrument.
#
#   worker-data      → data                    (concurrency: 4)
#     Parallelisable data fetches and imports.
#
#   worker-reports   → reports                 (concurrency: 1)
#     End-of-day analytics — non-urgent, single-threaded.
#
# Usage: ./scripts/startbk.sh
# =============================================================================

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/logs/pids"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

mkdir -p "$LOG_DIR" "$PID_DIR"

cd "$PROJECT_DIR"
source "$PROJECT_DIR/venv/bin/activate"

echo -e "${YELLOW}=== mCube-ai Background Services (Dedicated Workers) ===${NC}"
echo ""

# Verify Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}[ERROR] Redis is not running!${NC}"
    echo "Start Redis: sudo systemctl start redis-server"
    exit 1
fi
echo -e "${GREEN}[OK] Redis is running${NC}"

# Stop any existing Celery processes
echo -e "${YELLOW}Stopping any existing Celery processes...${NC}"
pkill -f "celery.*mcube_ai" 2>/dev/null
sleep 2

# Remove stale beat schedule so it rebuilds cleanly from DB
rm -f "$PROJECT_DIR/celerybeat-schedule.db"

PYTHON="$PROJECT_DIR/venv/bin/python"
CELERY_CMD="$PYTHON -m celery -A mcube_ai"

# Helper: start a worker and save its PID
start_worker() {
    local name="$1"
    local queues="$2"
    local concurrency="$3"
    local log_file="$LOG_DIR/celery_${name}.log"
    local pid_file="$PID_DIR/celery_${name}.pid"

    echo -e "${YELLOW}Starting worker-${name} (queues: ${queues}, concurrency: ${concurrency})...${NC}"

    nohup $CELERY_CMD worker \
        --queues="$queues" \
        --concurrency="$concurrency" \
        --hostname="${name}@%h" \
        --loglevel=info \
        --max-tasks-per-child=500 \
        >> "$log_file" 2>&1 &

    local pid=$!
    echo $pid > "$pid_file"
    sleep 1

    if ps -p $pid > /dev/null 2>&1; then
        echo -e "${GREEN}  [OK] worker-${name} started (PID: ${pid})${NC}"
    else
        echo -e "${RED}  [FAILED] worker-${name} failed to start — check $log_file${NC}"
    fi
}

# =============================================================================
# Celery Beat (Scheduler)
# =============================================================================
echo -e "${YELLOW}Starting Celery Beat...${NC}"
nohup $CELERY_CMD beat \
    --scheduler=mcube_ai.celery:DBReloadScheduler \
    --loglevel=info \
    >> "$LOG_DIR/celery_beat.log" 2>&1 &
BEAT_PID=$!
echo $BEAT_PID > "$PID_DIR/celery_beat.pid"
sleep 2

if ps -p $BEAT_PID > /dev/null 2>&1; then
    echo -e "${GREEN}[OK] Celery Beat started (PID: $BEAT_PID)${NC}"
else
    echo -e "${RED}[FAILED] Celery Beat failed to start${NC}"
fi

echo ""

# =============================================================================
# Dedicated Worker Pools
# =============================================================================

# CRITICAL — position monitoring + risk limits.
# Must never be starved.  Runs every-minute tasks.
start_worker "critical" "monitoring,risk" "3"

# TRADING — strategy execution (options + futures).
# Low concurrency: prevents two entry tasks running simultaneously.
start_worker "trading" "strategies" "2"

# DATA — market data fetches, Trendlyne imports, Breeze updates.
# Higher concurrency: tasks are I/O bound and independent.
start_worker "data" "data" "4"

# REPORTS — EOD analytics, equity curves, P&L aggregation.
# Single worker: non-urgent, keeps DB load predictable.
start_worker "reports" "reports" "1"

sleep 2

# =============================================================================
# Status
# =============================================================================
echo ""
echo -e "${YELLOW}=== Status ===${NC}"

check_worker() {
    local name="$1"
    if pgrep -f "celery.*worker.*${name}@" > /dev/null 2>&1; then
        echo -e "${GREEN}[RUNNING] worker-${name}${NC}"
    else
        echo -e "${RED}[NOT RUNNING] worker-${name}${NC}"
    fi
}

if pgrep -f "celery.*beat.*mcube_ai" > /dev/null; then
    echo -e "${GREEN}[RUNNING] Celery Beat${NC}"
else
    echo -e "${RED}[NOT RUNNING] Celery Beat${NC}"
fi

check_worker "critical"
check_worker "trading"
check_worker "data"
check_worker "reports"

echo ""
echo -e "${YELLOW}Logs:${NC}"
echo "  Beat:     $LOG_DIR/celery_beat.log"
echo "  Critical: $LOG_DIR/celery_critical.log"
echo "  Trading:  $LOG_DIR/celery_trading.log"
echo "  Data:     $LOG_DIR/celery_data.log"
echo "  Reports:  $LOG_DIR/celery_reports.log"
echo ""
echo -e "${YELLOW}To stop all services:${NC} ./scripts/stopbk.sh"
echo -e "${YELLOW}To tail a worker:${NC}   tail -f $LOG_DIR/celery_critical.log"
