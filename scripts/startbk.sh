#!/bin/bash

# =============================================================================
# mCube-ai Background Services Startup Script
# =============================================================================
# Starts Celery Beat (scheduler) and Workers for all queues
# Usage: ./scripts/startbk.sh
# =============================================================================

PROJECT_DIR="/Users/anupammangudkar/Projects/mCube-ai"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/logs/pids"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create directories if they don't exist
mkdir -p "$LOG_DIR"
mkdir -p "$PID_DIR"

cd "$PROJECT_DIR"

# Activate virtual environment
source "$PROJECT_DIR/venv/bin/activate"

# =============================================================================
# DYNAMIC CELERY CONCURRENCY
# =============================================================================
# Calculate concurrency based on available CPU cores (half of cores)
if [[ "$OSTYPE" == "darwin"* ]]; then
    CPU_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
else
    CPU_CORES=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 4)
fi

# Use half the cores, minimum 2, maximum 32
CELERY_CONCURRENCY=$((CPU_CORES / 2))
if [ "$CELERY_CONCURRENCY" -lt 2 ]; then
    CELERY_CONCURRENCY=2
elif [ "$CELERY_CONCURRENCY" -gt 32 ]; then
    CELERY_CONCURRENCY=32
fi

export CELERY_CONCURRENCY

echo -e "${YELLOW}=== mCube-ai Background Services ===${NC}"
echo -e "CPU Cores: $CPU_CORES | Celery Workers: $CELERY_CONCURRENCY"
echo ""

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}[ERROR] Redis is not running!${NC}"
    echo "Start Redis first with: brew services start redis (or redis-server)"
    exit 1
fi
echo -e "${GREEN}[OK] Redis is running${NC}"

# Function to stop existing processes
stop_existing() {
    echo -e "${YELLOW}Stopping any existing Celery processes...${NC}"
    pkill -f "celery.*mcube_ai" 2>/dev/null
    sleep 2
}

# Stop existing processes first
stop_existing

# Start Celery Beat (Scheduler)
echo -e "${YELLOW}Starting Celery Beat (Scheduler)...${NC}"
nohup celery -A mcube_ai beat --loglevel=info >> "$LOG_DIR/celery_beat.log" 2>&1 &
BEAT_PID=$!
echo $BEAT_PID > "$PID_DIR/celery_beat.pid"
sleep 2

if ps -p $BEAT_PID > /dev/null 2>&1; then
    echo -e "${GREEN}[OK] Celery Beat started (PID: $BEAT_PID)${NC}"
else
    echo -e "${RED}[FAILED] Celery Beat failed to start${NC}"
fi

# Start Celery Worker with all queues
echo -e "${YELLOW}Starting Celery Worker (all queues, concurrency=$CELERY_CONCURRENCY)...${NC}"
nohup celery -A mcube_ai worker \
    --queues=data,strategies,monitoring,risk,reports,celery \
    --loglevel=info \
    --concurrency=$CELERY_CONCURRENCY >> "$LOG_DIR/celery_worker.log" 2>&1 &
WORKER_PID=$!
echo $WORKER_PID > "$PID_DIR/celery_worker.pid"
sleep 2

if ps -p $WORKER_PID > /dev/null 2>&1; then
    echo -e "${GREEN}[OK] Celery Worker started (PID: $WORKER_PID)${NC}"
else
    echo -e "${RED}[FAILED] Celery Worker failed to start${NC}"
fi

sleep 2

# Verify processes are running
echo ""
echo -e "${YELLOW}=== Status ===${NC}"

if pgrep -f "celery.*beat.*mcube_ai" > /dev/null; then
    echo -e "${GREEN}[RUNNING] Celery Beat${NC}"
else
    echo -e "${RED}[NOT RUNNING] Celery Beat${NC}"
fi

if pgrep -f "celery.*worker.*mcube_ai" > /dev/null; then
    echo -e "${GREEN}[RUNNING] Celery Worker${NC}"
else
    echo -e "${RED}[NOT RUNNING] Celery Worker${NC}"
fi

echo ""
echo -e "${YELLOW}Logs:${NC}"
echo "  Beat:   $LOG_DIR/celery_beat.log"
echo "  Worker: $LOG_DIR/celery_worker.log"
echo ""
echo -e "${YELLOW}To stop all services:${NC} ./scripts/stopbk.sh"
echo -e "${YELLOW}To view logs:${NC} tail -f $LOG_DIR/celery_worker.log"
