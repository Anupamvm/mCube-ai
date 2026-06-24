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

# Stop Next.js portfolio frontend
echo "Stopping portfolio frontend (Next.js)..."
pkill -f "next.*start" 2>/dev/null
pkill -f "next-server" 2>/dev/null
RESULT=$?
# Also free port 3001 in case the process name doesn't match
if command -v fuser &>/dev/null; then
    fuser -k 3001/tcp 2>/dev/null || true
elif command -v lsof &>/dev/null; then
    lsof -ti tcp:3001 | xargs -r kill -9 2>/dev/null || true
fi
if [ $RESULT -eq 0 ]; then
    echo "✓ Portfolio frontend stopped"
else
    echo "  (Portfolio frontend was not running)"
fi

# Clean up PID files
rm -f .pids/*.pid 2>/dev/null

# ============================================================================
# Close Terminal Windows (platform-specific)
# ============================================================================

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: Close the Terminal windows opened by install_and_run.sh.
    # The windows have custom titles like "mCube - Django Server".
    # We send "exit" to each window's shell (processes are already killed above)
    # so the shell exits cleanly, causing the tab/window to close automatically.
    echo ""
    echo "Closing mCube terminal windows..."
    osascript <<'APPLESCRIPT'
    tell application "Terminal"
        -- Collect matching windows first to avoid live-list mutation issues
        set mcubeWins to {}
        repeat with w in windows
            try
                if (custom title of w) contains "mCube" then
                    set end of mcubeWins to w
                end if
            end try
        end repeat
        -- Send "exit" to each window's shell so it closes on its own
        repeat with w in mcubeWins
            try
                do script "exit" in tab 1 of w
            end try
        end repeat
    end tell
APPLESCRIPT
    echo "✓ Terminal windows closed"

else
    # Linux: Close whatever install_and_run.sh opened.
    # The start script tries (in order): gnome-terminal → konsole → xterm → tmux → nohup background.
    # We handle each case below, sweeping ALL mCube instances (not just one per name).

    # 1. Kill ALL tmux sessions whose name starts with "mcube-"
    #    (covers duplicates from multiple start-script runs AND stale/crashed sessions)
    if command -v tmux &>/dev/null; then
        _mcube_sessions=$(tmux list-sessions -F "#{session_name}" 2>/dev/null | grep "^mcube-" || true)
        if [ -n "$_mcube_sessions" ]; then
            echo ""
            echo "Closing tmux sessions..."
            echo "$_mcube_sessions" | while read -r _session; do
                tmux kill-session -t "$_session" 2>/dev/null \
                    && echo "  ✓ Closed: $_session" || true
            done
        fi
    fi

    # 2. Close ALL GUI terminal windows whose title contains "mCube"
    #    (handles gnome-terminal / konsole / xterm; skipped on headless servers)
    #    Uses wmctrl (preferred — closes by window ID so all duplicates are caught)
    #    or xdotool as fallback.
    if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
        echo ""
        if command -v wmctrl &>/dev/null; then
            echo "Closing terminal windows (wmctrl)..."
            # List all windows, filter by "mCube", close each by window ID.
            # Closing by ID means every matching window is hit, even duplicates.
            _wids=$(wmctrl -l 2>/dev/null | grep -i "mCube" | awk '{print $1}')
            if [ -n "$_wids" ]; then
                echo "$_wids" | while read -r _wid; do
                    wmctrl -ic "$_wid" 2>/dev/null && echo "  ✓ Closed window: $_wid" || true
                done
            else
                echo "  (no matching terminal windows found)"
            fi
        elif command -v xdotool &>/dev/null; then
            echo "Closing terminal windows (xdotool)..."
            # search returns ALL matching window IDs; close each individually.
            _wids=$(xdotool search --name "mCube" 2>/dev/null || true)
            if [ -n "$_wids" ]; then
                echo "$_wids" | while read -r _wid; do
                    xdotool windowclose "$_wid" 2>/dev/null && echo "  ✓ Closed window: $_wid" || true
                done
            else
                echo "  (no matching terminal windows found)"
            fi
        else
            echo "  (wmctrl/xdotool not installed — terminal windows left open; processes are killed)"
            echo "  To enable auto-close: sudo apt-get install wmctrl"
        fi
    fi
    # Headless / nohup mode: no windows exist — processes already killed above by pkill.
fi

echo ""
echo "============================================"
echo "All Services Stopped ✓"
echo "============================================"
echo ""
echo "To start services again:"
echo "  ./install_and_run.sh --run-only"
echo ""
