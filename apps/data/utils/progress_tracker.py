"""
Progress Tracker for Long-Running Tasks

Provides a simple file-based progress tracking system for real-time
updates from management commands to web UI.

Features:
- Step-by-step progress tracking
- Detailed log history with timestamps
- Status indicators (running, completed, error)
- Automatic stale detection (5 min timeout)
"""

import json
import os
import time
from datetime import datetime
from django.conf import settings

# Progress file location - consistent with apps/data/tldata directory
PROGRESS_FILE = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata', 'progress.json')

# In-memory log buffer (also persisted to file)
_log_buffer = []


def update_progress(
    step: int,
    total_steps: int,
    message: str,
    status: str = 'running',
    details: dict = None
):
    """
    Update progress status for the current task.

    Args:
        step: Current step number (1-based)
        total_steps: Total number of steps
        message: Human-readable status message
        status: 'running', 'completed', 'error'
        details: Optional additional details dict
    """
    global _log_buffer

    timestamp = datetime.now()
    timestamp_str = timestamp.isoformat()
    time_display = timestamp.strftime('%H:%M:%S')

    # Add to log buffer
    log_entry = {
        'time': time_display,
        'step': step,
        'message': message,
        'status': status,
        'timestamp': timestamp_str
    }
    _log_buffer.append(log_entry)

    # Keep only last 50 log entries to prevent memory issues
    if len(_log_buffer) > 50:
        _log_buffer = _log_buffer[-50:]

    progress = {
        'step': step,
        'total_steps': total_steps,
        'message': message,
        'status': status,
        'percent': round((step / total_steps) * 100) if total_steps > 0 else 0,
        'timestamp': timestamp_str,
        'details': details or {},
        'logs': _log_buffer.copy()  # Include log history
    }

    # Ensure directory exists
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)

    # Write progress atomically
    temp_file = PROGRESS_FILE + '.tmp'
    with open(temp_file, 'w') as f:
        json.dump(progress, f, indent=2)
    os.replace(temp_file, PROGRESS_FILE)


def add_log(message: str, level: str = 'info'):
    """
    Add a log entry without changing the current step.
    Useful for sub-step logging.

    Args:
        message: Log message
        level: 'info', 'success', 'warning', 'error'
    """
    global _log_buffer

    timestamp = datetime.now()
    log_entry = {
        'time': timestamp.strftime('%H:%M:%S'),
        'message': message,
        'level': level,
        'timestamp': timestamp.isoformat()
    }
    _log_buffer.append(log_entry)

    # Keep only last 50 entries
    if len(_log_buffer) > 50:
        _log_buffer = _log_buffer[-50:]

    # Update the file with new log (read existing, add log, write back)
    try:
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                progress = json.load(f)
            progress['logs'] = _log_buffer.copy()
            progress['timestamp'] = timestamp.isoformat()

            temp_file = PROGRESS_FILE + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(progress, f, indent=2)
            os.replace(temp_file, PROGRESS_FILE)
    except Exception:
        pass  # Ignore errors in sub-logging


def get_progress() -> dict:
    """
    Get current progress status.

    Returns:
        dict with progress info or None if no progress file or stale
    """
    try:
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                progress = json.load(f)

            # Check if progress is stale (older than 5 minutes and still "running")
            if progress.get('status') == 'running':
                try:
                    ts = datetime.fromisoformat(progress['timestamp'])
                    age_seconds = (datetime.now() - ts).total_seconds()
                    if age_seconds > 300:  # 5 minutes
                        # Stale running task - mark as error and return it
                        progress['status'] = 'error'
                        progress['message'] = 'Task timed out or was interrupted'
                        progress['stale'] = True
                        return progress
                except (ValueError, KeyError):
                    pass

            return progress
    except (json.JSONDecodeError, IOError):
        pass
    return None


def clear_progress():
    """Remove progress file and clear log buffer."""
    global _log_buffer
    _log_buffer = []  # Clear the in-memory log buffer
    try:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
    except IOError:
        pass


def is_task_running() -> bool:
    """Check if a task is currently running."""
    progress = get_progress()
    if progress:
        # Consider stale if older than 5 minutes
        try:
            ts = datetime.fromisoformat(progress['timestamp'])
            age_seconds = (datetime.now() - ts).total_seconds()
            if age_seconds > 300:  # 5 minutes
                return False
            return progress.get('status') == 'running'
        except (ValueError, KeyError):
            pass
    return False
