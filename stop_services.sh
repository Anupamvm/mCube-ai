#!/bin/bash

# ============================================================================
# mCube-ai Stop Services Script
# ============================================================================
# Stops all running mCube services
# ============================================================================

echo "============================================"
echo "Stopping mCube Services..."
echo "============================================"
echo ""

# Stop Django server
echo "Stopping Django server..."
pkill -f "manage.py runserver" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Django server stopped"
else
    echo "  (Django server was not running)"
fi

# Stop Telegram bot
echo "Stopping Telegram bot..."
pkill -f "run_telegram_bot" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Telegram bot stopped"
else
    echo "  (Telegram bot was not running)"
fi

# Remove telegram lock file
rm -f /tmp/mcube_telegram_bot.lock

# Stop Celery workers (matches both old and new startup methods)
echo "Stopping Celery workers..."
pkill -f "celery.*mcube.*worker" 2>/dev/null
RESULT=$?
pkill -f "celery -A mcube_ai worker" 2>/dev/null
if [ $RESULT -eq 0 ] || [ $? -eq 0 ]; then
    echo "✓ Celery workers stopped"
else
    echo "  (Celery workers were not running)"
fi

# Stop Celery beat (matches both old and new startup methods)
echo "Stopping Celery beat..."
pkill -f "celery.*mcube.*beat" 2>/dev/null
RESULT=$?
pkill -f "celery -A mcube_ai beat" 2>/dev/null
if [ $RESULT -eq 0 ] || [ $? -eq 0 ]; then
    echo "✓ Celery beat stopped"
else
    echo "  (Celery beat was not running)"
fi

# Stop background tasks
echo "Stopping background tasks..."
pkill -f "process_tasks" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Background tasks stopped"
else
    echo "  (Background tasks were not running)"
fi

# Clean up PID files
rm -f .pids/*.pid 2>/dev/null

echo ""
echo "============================================"
echo "All Services Stopped ✓"
echo "============================================"
echo ""
echo "To start services again:"
echo "  ./install_and_run.sh --run-only"
echo ""
