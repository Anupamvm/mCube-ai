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

echo -e "${YELLOW}=== mCube-ai Background Services ===${NC}"
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
celery -A mcube_ai beat \
    --loglevel=info \
    --logfile="$LOG_DIR/celery_beat.log" \
    --pidfile="$PID_DIR/celery_beat.pid" \
    --detach

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[OK] Celery Beat started${NC}"
else
    echo -e "${RED}[FAILED] Celery Beat failed to start${NC}"
fi

# Start Celery Worker with all queues
echo -e "${YELLOW}Starting Celery Worker (all queues)...${NC}"
celery -A mcube_ai worker \
    --queues=data,strategies,monitoring,risk,reports \
    --loglevel=info \
    --logfile="$LOG_DIR/celery_worker.log" \
    --pidfile="$PID_DIR/celery_worker.pid" \
    --concurrency=4 \
    --detach

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[OK] Celery Worker started${NC}"
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
