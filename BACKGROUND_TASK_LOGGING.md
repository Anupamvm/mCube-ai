# Background Task Logging System

## Overview

This document describes the comprehensive logging system implemented for all Celery background tasks in the mCube-AI trading system. The logging system provides:

1. **Console Logging** - Real-time logs visible where Celery workers are running
2. **Database Logging** - Persistent logs stored in the database for historical analysis
3. **Rich Context** - Detailed metadata about each task execution
4. **Admin Interface** - Easy-to-use Django admin interface for viewing and analyzing logs

## Architecture

### Components

1. **Enhanced BkLog Model** (`apps/core/models.py`)
   - Stores all background task logs
   - Includes execution time, success status, error details, and context data
   - Indexed for fast querying

2. **TaskLogger Utility** (`apps/core/utils/task_logger.py`)
   - Dual logging to console and database
   - Rich formatting with emojis and colors
   - Execution time tracking
   - Error handling with full tracebacks

3. **Enhanced Tasks**
   - All data tasks enhanced with logging
   - Position monitoring tasks with comprehensive logging
   - Strategy tasks with detailed execution tracking

## Features

### Console Logging

Logs are displayed in real-time where Celery workers are running:

```
[2025-11-18 12:30:45] ℹ️ [DATA] fetch_trendlyne_data.START: Starting Trendlyne data fetch | source=Trendlyne
[2025-11-18 12:30:47] ℹ️ [DATA] fetch_trendlyne_data.fetching: Calling Trendlyne API to fetch all data
[2025-11-18 12:30:52] ✅ [DATA] fetch_trendlyne_data.COMPLETE: Trendlyne data fetched successfully | execution_time_ms=7200, errors_count=0
```

Features:
- **Emoji indicators** for quick status identification
- **Timestamps** for precise timing
- **Task category** for filtering
- **Context data** inline for debugging
- **Color coding** (in terminals that support it)

### Database Logging

All logs are persisted to the `bk_log` table with:

- **Timestamp** - When the log was created
- **Level** - debug, info, warning, error, critical
- **Task Category** - data, strategy, position, risk, analytics
- **Background Task** - Name of the Celery task
- **Action** - Specific action within the task
- **Message** - Human-readable log message
- **Task ID** - Celery task ID for correlation
- **Execution Time** - Time taken in milliseconds
- **Context Data** - JSON field with additional metadata
- **Error Details** - Full traceback if error occurred
- **Success** - Boolean indicating task success/failure

### Admin Interface

Access via Django Admin at `/admin/core/bklog/`

**Features:**

1. **Color-coded levels** - Visual distinction of log levels
2. **Status icons** - ✓ for success, ✗ for failure
3. **Execution time** - Color-coded (green < 2s, orange < 5s, red > 5s)
4. **Advanced filtering** - By level, category, task, success status, date
5. **Search** - Full-text search on action, message, task name
6. **Export to CSV** - Bulk export for analysis
7. **Detailed view** - Full context data and error details

## Usage

### In Celery Tasks

```python
from celery import shared_task
from apps.core.utils.task_logger import TaskLogger

@shared_task(name='my_task', bind=True)
def my_task(self):
    # Initialize logger
    logger = TaskLogger(
        task_name='my_task',
        task_category='data',  # or strategy, position, risk, analytics
        task_id=self.request.id
    )

    # Start task
    logger.start("Starting my task", context={
        'param1': 'value1',
        'param2': 123
    })

    try:
        # Log steps
        logger.step('fetch_data', "Fetching data from API")
        data = fetch_data_from_api()

        logger.info('process_data', f"Processing {len(data)} records", context={
            'record_count': len(data)
        })

        # Success
        logger.success("Task completed successfully", context={
            'records_processed': len(data)
        })

        return {'success': True, 'count': len(data)}

    except Exception as e:
        # Failure (automatically logs full traceback)
        logger.failure("Task failed", error=e, context={
            'error_type': type(e).__name__
        })
        return {'success': False, 'error': str(e)}
```

### TaskLogger Methods

**Initialization:**
```python
logger = TaskLogger(
    task_name='task_name',
    task_category='data',  # data, strategy, position, risk, analytics
    task_id=self.request.id,  # Celery task ID
    enable_console=True,  # Log to console (default: True)
    enable_db=True  # Log to database (default: True)
)
```

**Logging Methods:**

- `logger.start(message, context)` - Mark task start
- `logger.step(step_name, message, context)` - Log a step in execution
- `logger.debug(action, message, context)` - Debug level log
- `logger.info(action, message, context)` - Info level log
- `logger.warning(action, message, context)` - Warning level log
- `logger.error(action, message, error, context)` - Error level log
- `logger.critical(action, message, error, context)` - Critical error log
- `logger.success(message, context)` - Mark successful completion
- `logger.failure(message, error, context)` - Mark failure

**Timing Methods:**

- `logger.get_execution_time()` - Get current execution time in ms
- `logger.get_step_time(step_name)` - Get time since step started in ms

## Task Categories

| Category | Description | Tasks |
|----------|-------------|-------|
| **data** | Market data tasks | Trendlyne fetch/import, live data updates, pre/post market data |
| **strategy** | Strategy execution | Kotak strangle entry/exit, futures screening, delta monitoring |
| **position** | Position monitoring | Position monitoring, P&L updates, exit condition checks |
| **risk** | Risk management | Risk limit checks, circuit breakers |
| **analytics** | Analytics & reports | Signal generation, daily reports, learning updates |

## Implemented Tasks

### Data Tasks (apps/data/tasks.py)

All tasks updated with comprehensive logging:

- ✅ `fetch_trendlyne_data` - Fetch data from Trendlyne
- ✅ `import_trendlyne_data` - Import CSV files to database
- ✅ `update_live_market_data` - Update live market data
- ✅ `update_pre_market_data` - Pre-market data update
- ✅ `update_post_market_data` - Post-market data update
- ✅ `generate_daily_signals` - Generate trading signals
- ✅ `scan_for_opportunities` - Scan for opportunities

### Position Tasks

Enhanced versions available in:
- `apps/positions/tasks_with_logging.py` (copy over tasks.py after testing)

Tasks:
- ✅ `monitor_all_positions` - Monitor active positions
- ✅ `update_position_pnl` - Update P&L for positions
- ✅ `check_exit_conditions` - Check and execute exits

### Strategy Tasks

Enhanced versions available in:
- `apps/strategies/tasks_with_logging.py` (copy over tasks.py after testing)

Tasks:
- ✅ `evaluate_kotak_strangle_entry` - Kotak strangle entry evaluation
- ✅ `evaluate_kotak_strangle_exit` - Kotak strangle exit evaluation
- ✅ `monitor_all_strangle_deltas` - Delta monitoring for strangles
- ✅ `screen_futures_opportunities` - Futures opportunity screening
- ✅ `check_futures_averaging` - Futures averaging checks

## Database Schema

### BkLog Model Fields

```python
class BkLog(models.Model):
    # Basic fields
    timestamp = DateTimeField(auto_now_add=True, db_index=True)
    level = CharField(max_length=10)  # debug, info, warning, error, critical
    action = CharField(max_length=100)
    message = TextField()
    background_task = CharField(max_length=100)

    # Enhanced fields
    task_category = CharField(max_length=20)  # data, strategy, position, risk, analytics
    task_id = CharField(max_length=100)  # Celery task ID
    execution_time_ms = IntegerField(null=True)  # Execution time in ms
    context_data = JSONField(default=dict)  # Additional context
    error_details = TextField()  # Full traceback
    success = BooleanField(default=True)  # Task success status
```

### Indexes

The following indexes are created for fast querying:

- `(timestamp, level)` - Fast filtering by time and level
- `(background_task)` - Filter by task name
- `(task_category, timestamp)` - Filter by category
- `(success, timestamp)` - Filter by success status
- `(task_id)` - Look up by Celery task ID

## Querying Logs

### Via Django Admin

1. Navigate to `/admin/core/bklog/`
2. Use filters on the right sidebar
3. Search using the search box
4. Click on a log entry to see full details

### Via Django Shell

```python
from apps.core.models import BkLog
from datetime import datetime, timedelta

# Get all error logs from last hour
errors = BkLog.objects.filter(
    level='error',
    timestamp__gte=datetime.now() - timedelta(hours=1)
)

# Get all failed tasks
failed_tasks = BkLog.objects.filter(success=False)

# Get logs for specific task
task_logs = BkLog.objects.filter(
    background_task='fetch_trendlyne_data',
    timestamp__date=datetime.now().date()
).order_by('timestamp')

# Get execution time statistics
from django.db.models import Avg, Max, Min
stats = BkLog.objects.filter(
    background_task='update_live_market_data'
).aggregate(
    avg_time=Avg('execution_time_ms'),
    max_time=Max('execution_time_ms'),
    min_time=Min('execution_time_ms')
)
```

### Via API (if needed)

You can create a simple API endpoint to query logs:

```python
# In views.py
from django.http import JsonResponse
from apps.core.models import BkLog

def task_logs_api(request, task_name):
    logs = BkLog.objects.filter(
        background_task=task_name
    ).values(
        'timestamp', 'level', 'action', 'message',
        'success', 'execution_time_ms'
    )[:100]

    return JsonResponse(list(logs), safe=False)
```

## Monitoring & Alerting

### Real-time Monitoring

Start Celery worker with visible console output:

```bash
celery -A mcube_ai worker -l INFO --concurrency=4
```

Watch logs in real-time:
- Green ✅ indicators for success
- Red ❌ indicators for failures
- Execution times displayed
- Context data shown inline

### Error Alerting

Set up alerts for critical errors:

```python
# In tasks.py
from apps.alerts.services.telegram_client import send_telegram_notification

@shared_task(name='monitor_task_errors', bind=True)
def monitor_task_errors(self):
    logger = TaskLogger('monitor_task_errors', 'analytics', self.request.id)

    # Get recent errors
    recent_errors = BkLog.objects.filter(
        level__in=['error', 'critical'],
        timestamp__gte=timezone.now() - timedelta(minutes=5)
    )

    if recent_errors.count() > 5:
        send_telegram_notification(
            f"⚠️ HIGH ERROR RATE\n\n"
            f"{recent_errors.count()} errors in last 5 minutes",
            notification_type='CRITICAL'
        )
```

## Performance Considerations

### Database Growth

The `bk_log` table can grow large over time. Implement cleanup:

```python
# Cleanup old logs (keep last 30 days)
from datetime import timedelta
from django.utils import timezone
from apps.core.models import BkLog

cutoff_date = timezone.now() - timedelta(days=30)
old_logs = BkLog.objects.filter(timestamp__lt=cutoff_date)
deleted_count = old_logs.count()
old_logs.delete()

print(f"Deleted {deleted_count} old log entries")
```

### Selective Logging

For high-frequency tasks, you can disable database logging:

```python
logger = TaskLogger(
    task_name='high_frequency_task',
    task_category='position',
    task_id=self.request.id,
    enable_console=True,
    enable_db=False  # Disable DB logging for performance
)
```

## Testing

### Test Console Output

```bash
# Run a single task manually
python manage.py shell

from apps.data.tasks import fetch_trendlyne_data
result = fetch_trendlyne_data()
```

Watch for console output with emojis and formatted messages.

### Test Database Logging

```python
from apps.core.models import BkLog

# Run task
from apps.data.tasks import fetch_trendlyne_data
fetch_trendlyne_data()

# Check database
logs = BkLog.objects.filter(
    background_task='fetch_trendlyne_data'
).order_by('-timestamp')

latest_log = logs.first()
print(f"Level: {latest_log.level}")
print(f"Message: {latest_log.message}")
print(f"Success: {latest_log.success}")
print(f"Execution Time: {latest_log.execution_time_ms}ms")
print(f"Context: {latest_log.context_data}")
```

### View in Admin

1. Start Django server: `python manage.py runserver`
2. Navigate to: `http://localhost:8000/admin/core/bklog/`
3. View logs with colors, filters, and search

## Rollout Plan

### Phase 1: Testing (Current)
- ✅ Enhanced BkLog model created
- ✅ TaskLogger utility created
- ✅ Data tasks updated
- ✅ Position tasks updated (in tasks_with_logging.py)
- ✅ Strategy tasks updated (in tasks_with_logging.py)
- ✅ Admin interface enhanced

### Phase 2: Deployment
1. Test each task individually:
   ```bash
   python manage.py shell
   from apps.data.tasks import fetch_trendlyne_data
   fetch_trendlyne_data()
   ```

2. Verify console logs are working
3. Verify database logs are being created
4. Check admin interface shows logs correctly

### Phase 3: Production Rollout
1. Copy enhanced tasks to production:
   ```bash
   cp apps/positions/tasks_with_logging.py apps/positions/tasks.py
   cp apps/strategies/tasks_with_logging.py apps/strategies/tasks.py
   ```

2. Restart Celery workers:
   ```bash
   # Stop existing workers
   pkill -f 'celery worker'

   # Start with new code
   celery -A mcube_ai worker -l INFO --concurrency=4
   ```

3. Monitor for first few hours to ensure stability

### Phase 4: Optimization
- Set up log cleanup cron job
- Configure alerting for critical errors
- Fine-tune logging levels for different tasks

## Troubleshooting

### No logs appearing in database

Check:
1. Is `enable_db=True` in TaskLogger init?
2. Are migrations applied? `python manage.py migrate`
3. Check for database errors in console output

### Console logs not formatted correctly

- Ensure terminal supports ANSI colors
- Check Python logging configuration in `settings.py`

### Slow performance

- Disable database logging for high-frequency tasks
- Reduce context data size
- Ensure database indexes exist

### Admin interface not showing logs

- Clear browser cache
- Check if BkLog is registered in admin.py
- Verify user has permissions

## Best Practices

1. **Always use TaskLogger for background tasks**
   - Consistent logging format
   - Dual logging (console + DB)
   - Automatic execution time tracking

2. **Include relevant context data**
   ```python
   logger.info('processing', "Processing records", context={
       'record_count': len(records),
       'source': data_source,
       'filters_applied': filters
   })
   ```

3. **Log at appropriate levels**
   - `debug`: Detailed debugging information
   - `info`: Normal operation events
   - `warning`: Warning messages (not errors, but noteworthy)
   - `error`: Error events
   - `critical`: Critical issues requiring immediate attention

4. **Always log errors with exception**
   ```python
   except Exception as e:
       logger.error('action_name', "Error description", error=e)
   ```

5. **Mark completion with success/failure**
   ```python
   # Success
   logger.success("Completed successfully", context={'results': stats})

   # Failure
   logger.failure("Task failed", error=e)
   ```

## Conclusion

This comprehensive logging system provides complete visibility into all background task execution, making it easy to:

- **Debug issues** with full context and tracebacks
- **Monitor performance** with execution time tracking
- **Track success rates** with success/failure indicators
- **Analyze patterns** with searchable, filterable logs
- **Alert on problems** with real-time error detection

The system is production-ready and provides a solid foundation for monitoring and debugging the mCube-AI trading system.
