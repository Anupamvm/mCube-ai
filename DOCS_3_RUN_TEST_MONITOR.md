# System Test Page - Run, Test, and Monitoring Guide

## Complete Instructions for Running, Testing, and Monitoring the mCube AI Trading System

---

## Table of Contents

1. [Starting the System](#starting-the-system)
2. [Running Tests](#running-tests)
3. [Understanding Test Results](#understanding-test-results)
4. [Test Categories Explained](#test-categories-explained)
5. [Monitoring and Logs](#monitoring-and-logs)
6. [Troubleshooting Guide](#troubleshooting-guide)
7. [Performance Monitoring](#performance-monitoring)
8. [Maintenance Tasks](#maintenance-tasks)

---

## Starting the System

### Quick Start (All-in-One)

```bash
# Navigate to project directory
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai

# Activate virtual environment
source venv/bin/activate

# Start Redis (Terminal 1)
redis-server

# Start Ollama (Terminal 2, optional but recommended)
ollama serve

# Start Django (Terminal 3)
python manage.py runserver

# Start Celery worker (Terminal 4, for background tasks)
celery -A mcube_ai worker -l info

# Access test page
# Open browser: http://localhost:8000/system/test/
```

### Detailed Startup Steps

#### Step 1: Prepare Terminals

You'll need **4-5 terminal windows** open simultaneously:

```
Terminal 1: Redis
Terminal 2: Ollama (optional)
Terminal 3: Django
Terminal 4: Celery Worker
Terminal 5: Monitoring/Logs (optional)
```

#### Step 2: Start Redis

```bash
# Terminal 1
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai

# Option A: Using Homebrew (macOS)
redis-server

# Option B: Using installed redis
redis-server /usr/local/etc/redis.conf

# Option C: Using Docker
docker run -d -p 6379:6379 redis:latest

# Verify Redis is running
redis-cli ping
# Expected output: PONG
```

#### Step 3: Start Ollama (Optional but Recommended)

```bash
# Terminal 2
# In a new terminal window

# Start Ollama service
ollama serve

# In another terminal window, pull the model (one-time)
ollama pull deepseek-r1:7b

# Verify it's working
curl http://localhost:11434/api/tags
# Should return JSON with models list
```

#### Step 4: Start Django Development Server

```bash
# Terminal 3
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai

# Activate virtual environment
source venv/bin/activate

# Run development server
python manage.py runserver

# Expected output:
# Starting development server at http://127.0.0.1:8000/
# Quit the server with CONTROL-C.
```

#### Step 5: Start Celery Worker (Optional but Recommended)

```bash
# Terminal 4
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai

# Activate virtual environment
source venv/bin/activate

# Start Celery worker
celery -A mcube_ai worker -l info

# Expected output:
# . ____ .___.___ _________
# |    |    | ___  |_____   | Celery x.x.x (...)
# |    |    |     |  _____) | License: BSD
# ----------- [config] -----------
# . concurrency: 4 (prefork)
# . max concurrency: 4
```

### Startup Status Checklist

After all services start, verify:

```
✓ Redis: redis-cli ping returns PONG
✓ Ollama: curl http://localhost:11434/api/tags returns models (optional)
✓ Django: http://127.0.0.1:8000/admin/ loads (not showing errors)
✓ Celery: Celery worker shows "ready to accept tasks"
```

### Stopping Services

```bash
# Stop Django (Ctrl+C in Terminal 3)
^C

# Stop Celery (Ctrl+C in Terminal 4)
^C

# Stop Ollama (Ctrl+C in Terminal 2)
^C

# Stop Redis
redis-cli shutdown
# OR (Ctrl+C in Terminal 1)
^C
```

---

## Running Tests

### Access Test Page

```
URL: http://localhost:8000/system/test/
```

### What Happens

1. **Page loads** (should be instant)
2. **Authentication check** (redirects to login if needed)
3. **Permission check** (admin-only access)
4. **Test execution** (all 40+ tests run automatically)
5. **Results render** (displays in categories)
6. **Auto-refresh** (refreshes every 5 minutes)

### Manual Refresh

Click the **"Refresh Tests"** button at the top-right to run tests immediately without waiting 5 minutes.

### Test Execution Time

```
First load: 5-15 seconds (tests run)
Subsequent refreshes: 2-5 seconds (cached results)
```

---

## Understanding Test Results

### Test Status Indicators

```
✓ (Green checkmark): Test PASSED - functionality working
✗ (Red X): Test FAILED - functionality not working or not configured
```

### Result Display Format

Each test shows:

```
[Status Icon] Test Name
   Detailed message about test results
```

### Example Results

```
✓ Database Connection
  Database connection successful

✓ Broker Limits Access
  Found 5 records. Latest: 2025-11-15 14:30:00

✗ F&O Data Freshness
  No F&O data files found

✓ Redis Connection
  Connected to localhost:6379/0

✗ Trendlyne Credentials
  No Trendlyne credentials found in database
```

### Statistics Dashboard

**Top of page shows**:

```
Total Tests: 40 tests across all categories
Passed: 35 tests successfully verified
Failed: 5 tests (configuration missing or service not running)
Pass Rate: 87.5% success rate

Last Updated: 2025-11-15 14:45:23
```

### What "Failing" Tests Mean

**NOT all failures are problems!** Common reasons:

1. **Configuration Missing**
   - Credentials not entered in Django admin
   - Service not configured
   - Solution: Add credentials in Django admin

2. **Service Not Running**
   - Redis not started
   - Ollama not running
   - Solution: Start the service

3. **Data Not Available Yet**
   - First time running Trendlyne scrape
   - No historical data yet
   - Solution: Run data collection task

4. **Optional Features**
   - LLM might be optional
   - Some brokers might not be needed
   - Solution: Ignore if not needed

---

## Test Categories Explained

### 1. Database Category (3 tests)

**Purpose**: Verify database is functioning

| Test | Expected | When Fails |
|------|----------|-----------|
| Database Connection | ✓ Always | DB file missing or corrupt |
| Migrations Status | ✓ Always | Migrations not applied |
| Database Tables | ✓ Always | Database not initialized |

**Action if Failing**:
```bash
python manage.py migrate
```

---

### 2. Brokers Category (5 tests)

**Purpose**: Verify broker integrations and data

| Test | Expected | When Fails |
|------|----------|-----------|
| Broker Limits Access | ✓ if data exists | Never fetched from broker |
| Broker Positions | ✓ if data exists | No positions in DB |
| Option Chain Data | ✓ if data exists | Not downloaded yet |
| Historical Price | ✓ if data exists | Not downloaded yet |
| Credentials | ✗ if not configured | Add credentials in admin |

**When These Might Fail (and it's OK)**:
- New installation without data
- No broker API calls made yet
- Credentials not configured (expected)

**Action**:
- Configure credentials in Django admin
- Run broker API sync tasks
- Check logs for API errors

---

### 3. Trendlyne Category (8 tests)

**Purpose**: Verify Trendlyne data scraping setup

| Test | Expected | When Fails |
|------|----------|-----------|
| Credentials | ✗ if not set up | Add in Django admin |
| Website Access | ✓ Always | Network issue or blocked |
| ChromeDriver | ✓ if Selenium installed | Install selenium |
| Data Directory | ✗ first time | Will pass after first scrape |
| F&O Data Freshness | ✗ first time | Run scrape task |
| Market Snapshot | ✗ first time | Run scrape task |
| Forecaster Data | ✗ first time | Run scrape task |
| Dependencies | ✓ Always | Missing Python packages |

**Initial Setup Expected Results**:
```
✓ Website Access
✓ ChromeDriver
✓ Dependencies
✗ Credentials (expected, add in admin)
✗ Data Directory (expected, will populate after first scrape)
✗ F&O Data (expected, will populate after first scrape)
✗ Market Snapshot (expected, will populate after first scrape)
✗ Forecaster Data (expected, will populate after first scrape)
```

**After Configuring and Running Scraper**:
```
✓ Website Access
✓ ChromeDriver
✓ Credentials
✓ Data Directory
✓ F&O Data Freshness
✓ Market Snapshot Data
✓ Forecaster Data
✓ Dependencies
```

---

### 4. Data App Category (5 tests)

**Purpose**: Verify market data storage

| Test | Expected | When Fails |
|------|----------|-----------|
| Market Data | ✓ if exists | No data collected |
| Trendlyne Stock | ✓ if exists | Scraper not run |
| Contract Data | ✓ if exists | F&O data not fetched |
| News Articles | ✓ if exists | Scraper not configured |
| Knowledge Base | ✓ if RAG in use | RAG system not used |

---

### 5. Orders Category (3 tests)

**Purpose**: Verify order system

| Test | Expected | When Fails |
|------|----------|-----------|
| Order Records | ✓ Always (0+ records) | DB issue |
| Executions | ✓ Always (0+ records) | DB issue |
| Order Creation | ✓ Always | Model issue |

**Expected Initially**:
```
✓ Order Records: Total: 0, Pending: 0, Filled: 0
✓ Order Executions: Found 0 executions
✓ Order Creation: Order model methods accessible
```

---

### 6. Positions Category (4 tests)

**Purpose**: Verify position management

| Test | Expected | When Fails |
|------|----------|-----------|
| Position Records | ✓ Always | DB issue |
| One Position Rule | ✓ Always | Model issue |
| P&L Calculation | ✓ Always | Calculation issue |
| Monitoring | ✓ Always | DB issue |

---

### 7. Accounts Category (3 tests)

**Purpose**: Verify account configuration

| Test | Expected | When Fails |
|------|----------|-----------|
| Broker Accounts | ✗ if not configured | Add in Django admin |
| API Credentials | ✗ if not configured | Add in Django admin |
| Capital Calc | ✗ if no accounts | Create broker account |

**After Configuration**:
```
✓ Broker Accounts: Total: 1, Active: 1
✓ API Credentials: Total: 1, Valid: 0 (until authenticated)
✓ Capital Calculations: Available: 100000, Total P&L: 0.00
```

---

### 8. LLM Category (3 tests)

**Purpose**: Verify LLM integration (optional)

| Test | Expected | When Fails |
|------|----------|-----------|
| Ollama Connection | ✓ if running | Ollama not started |
| LLM Validations | ✓ if exists | No validations yet |
| Prompt Templates | ✓ Always | DB issue |

**If Not Using LLM** (OK to fail):
```
✗ Ollama Connection: Error: Connection refused (expected if not needed)
✓ Prompt Templates: Total: 0, Active: 0
```

---

### 9. Redis Category (1 test)

**Purpose**: Verify Celery broker

| Test | Expected | When Fails |
|------|----------|-----------|
| Redis Connection | ✓ Always | Redis not running |

**If Fails**:
```bash
# Start Redis
redis-server
# OR
brew services start redis
```

---

### 10. Background Tasks Category (2 tests)

**Purpose**: Verify task system

| Test | Expected | When Fails |
|------|----------|-----------|
| Background Tasks | ✓ Always | DB issue |
| Task Definitions | ✓ Always | Module issue |

---

### 11. Django Admin Category (2 tests)

**Purpose**: Verify admin system

| Test | Expected | When Fails |
|------|----------|-----------|
| Admin Models | ✓ Always | Registration issue |
| Admin URL | ✓ Always | URL config issue |

---

## Monitoring and Logs

### Django Logs

**Location**: `logs/mcube_ai.log` (configured in settings.py)

```bash
# View real-time logs
tail -f logs/mcube_ai.log

# View last 100 lines
tail -100 logs/mcube_ai.log

# Search for errors
grep ERROR logs/mcube_ai.log

# Search for warnings
grep WARNING logs/mcube_ai.log

# View logs for specific date
grep "2025-11-15" logs/mcube_ai.log
```

### Console Output (Development Server)

```bash
# Django development server output
# Shows:
# - HTTP requests and responses
# - Database queries (if DEBUG=True)
# - Errors and warnings
# - Template rendering issues

# Example:
# [15/Nov/2025 14:30:45] "GET /system/test/ HTTP/1.1" 200 15432
# [15/Nov/2025 14:30:46] "POST /api/data/sync HTTP/1.1" 202 156
```

### Celery Logs

```bash
# View in Terminal running Celery worker
# Shows:
# - Task executions
# - Task completion/failure
# - Worker status
# - Queue information

# Example:
# [tasks] Received task: apps.data.tasks.sync_market_data[abc123-def456]
# [tasks] Task apps.data.tasks.sync_market_data[abc123] succeeded in 12.34s
```

### Redis Logs

```bash
# View Redis logs (if running in foreground)
redis-server

# Check Redis connections
redis-cli info
# Shows connected clients, memory usage, etc.

# Monitor Redis commands (real-time)
redis-cli monitor

# Check queue status
redis-cli LLEN celery
# Returns number of pending tasks
```

### Log Configuration

See `/mcube_ai/settings.py`:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'mcube_ai.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {'handlers': ['console', 'file'], 'level': 'INFO'},
        'celery': {'handlers': ['console', 'file'], 'level': 'INFO'},
        'apps': {'handlers': ['console', 'file'], 'level': 'DEBUG'},
    },
}
```

### Monitoring Command

```bash
# Create a monitoring script
cat > monitor.sh << 'EOF'
#!/bin/bash

echo "=== System Status ==="
echo ""
echo "Redis Status:"
redis-cli ping

echo ""
echo "Django Status:"
curl -s http://localhost:8000/admin/ | grep -q "Django administration" && echo "✓ Django OK" || echo "✗ Django Down"

echo ""
echo "Test Page Status:"
curl -s http://localhost:8000/system/test/ | grep -q "System Test Dashboard" && echo "✓ Test Page OK" || echo "✗ Test Page Down"

echo ""
echo "Celery Status:"
celery -A mcube_ai inspect active

echo ""
echo "Recent Logs:"
tail -5 logs/mcube_ai.log
EOF

# Make it executable
chmod +x monitor.sh

# Run it
./monitor.sh
```

---

## Troubleshooting Guide

### Common Issues and Solutions

#### Issue 1: Test Page Not Loading

**Symptoms**:
- Page doesn't load at all
- HTTP 500 error
- Page takes >30 seconds to load

**Causes and Solutions**:

```bash
# Check Django is running
curl http://localhost:8000/admin/

# Check logs for errors
tail -50 logs/mcube_ai.log

# Check database
python manage.py dbshell
> SELECT COUNT(*) FROM auth_user;
> .exit

# Restart Django
# (Stop with Ctrl+C in Django terminal)
python manage.py runserver

# Check for syntax errors
python -m py_compile apps/core/views.py
```

---

#### Issue 2: "Permission Denied" on Test Page

**Symptoms**:
- Redirected to login page
- After login, still see "Permission Denied"

**Causes and Solutions**:

```bash
# Verify you're logged in as superuser
python manage.py shell
from django.contrib.auth.models import User
User.objects.filter(is_superuser=True)
# Should show your admin user

# If no superuser, create one
python manage.py createsuperuser

# Verify user is active
user = User.objects.get(username='admin')
print(user.is_active)  # Should be True
print(user.is_superuser)  # Should be True

exit()
```

---

#### Issue 3: Redis Connection Failed

**Symptoms**:
- Test shows: ✗ Redis Connection: Error: Connection refused
- Celery shows: Connection refused

**Causes and Solutions**:

```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# If not running, start it
redis-server

# Or using Homebrew
brew services start redis

# Check Redis config
redis-cli CONFIG GET port
# Should show port 6379

# Verify connection string in settings
# Should be: redis://localhost:6379/0
```

---

#### Issue 4: Tests Running Slowly

**Symptoms**:
- Each test takes 10+ seconds
- Page takes >30 seconds to load
- Network requests timing out

**Causes and Solutions**:

```bash
# Check network connectivity
ping -c 1 google.com
ping -c 1 trendlyne.com

# Check Ollama connectivity (if using)
curl http://localhost:11434/api/tags

# Check Redis responsiveness
redis-cli PING

# Monitor Django processes
ps aux | grep python

# Check system resources
top -n 1 | head -20  # CPU and memory

# Reduce timeout in settings if needed
# Current: 5-10 second timeouts
```

---

#### Issue 5: Trendlyne Tests Failing

**Symptoms**:
```
✗ Trendlyne Credentials: No Trendlyne credentials found
✗ Website Access: Error: Connection timeout
✗ Data Directory: No data directories found
```

**Causes and Solutions**:

```bash
# Check credentials are configured
python manage.py shell
from apps.core.models import CredentialStore
creds = CredentialStore.objects.filter(service='trendlyne').first()
print(creds)  # Should show credentials object
exit()

# Check network access to Trendlyne
curl https://trendlyne.com -I

# Check Selenium installation
python -c "import selenium; print(selenium.__version__)"

# Check ChromeDriver
python -c "import chromedriver_autoinstaller; chromedriver_autoinstaller.install()"

# Check Chrome browser exists
which google-chrome chromium chromium-browser
```

---

#### Issue 6: Database Errors

**Symptoms**:
```
✗ Database Tables: Missing: broker_limits, orders, positions
```

**Causes and Solutions**:

```bash
# Check migration status
python manage.py showmigrations

# Apply missing migrations
python manage.py migrate

# Verify tables exist
python manage.py dbshell
> .tables
> .exit

# If tables missing, recreate database
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

---

### Debug Mode

Enable detailed debugging:

```python
# In mcube_ai/settings.py

# Already enabled in development
DEBUG = True

# Increase logging
LOGGING['loggers']['apps']['level'] = 'DEBUG'
```

### Django Shell for Investigation

```bash
# Start Django shell
python manage.py shell

# Import models
from apps.brokers.models import BrokerLimit
from apps.orders.models import Order
from apps.positions.models import Position

# Check data
print(f"Orders: {Order.objects.count()}")
print(f"Positions: {Position.objects.count()}")
print(f"Broker Limits: {BrokerLimit.objects.count()}")

# Check credentials
from apps.core.models import CredentialStore
for cred in CredentialStore.objects.all():
    print(f"{cred.service}: {cred.username}")

# Exit
exit()
```

---

## Performance Monitoring

### Check Resource Usage

```bash
# System resources
top -n 1

# Memory usage
free -h
# or
vm_stat  # macOS

# Disk usage
df -h

# Network connections
netstat -an | grep 6379  # Redis
netstat -an | grep 8000  # Django
```

### Database Performance

```bash
# Check database size
ls -lh db.sqlite3

# Enable query logging (settings.py)
LOGGING = {
    'handlers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}

# Monitor active connections
python manage.py dbshell
> .tables
> SELECT COUNT(*) FROM auth_user;
```

### Task Queue Performance

```bash
# Check pending tasks
redis-cli LLEN celery

# Check active tasks
celery -A mcube_ai inspect active

# Check task statistics
celery -A mcube_ai inspect stats
```

---

## Maintenance Tasks

### Daily Maintenance

```bash
# Check test results (already automated)
# Visit: http://localhost:8000/system/test/

# Review logs for errors
grep ERROR logs/mcube_ai.log

# Verify services are running
redis-cli ping
curl http://localhost:8000/admin/ > /dev/null
```

### Weekly Maintenance

```bash
# Clean up old logs (keep last 7 days)
find logs -name "*.log" -mtime +7 -delete

# Verify data freshness
python manage.py shell
from apps.data.models import MarketData
latest = MarketData.objects.latest('timestamp')
print(f"Latest data: {latest.timestamp}")
exit()

# Check database integrity
python manage.py check

# Review failed tasks
celery -A mcube_ai inspect failed
```

### Monthly Maintenance

```bash
# Database optimization
python manage.py shell
from django.core.management import call_command
call_command('optimize')  # SQLite command
exit()

# Clear old records (keep 30 days)
python manage.py shell
from django.utils import timezone
from datetime import timedelta
from apps.data.models import MarketData

cutoff = timezone.now() - timedelta(days=30)
deleted = MarketData.objects.filter(timestamp__lt=cutoff).delete()
print(f"Deleted: {deleted}")
exit()

# Update system dependencies
pip install --upgrade -r requirements.txt
```

### Backup Tasks

```bash
# Backup database
cp db.sqlite3 backups/db_$(date +%Y%m%d_%H%M%S).sqlite3

# Backup logs
tar -czf backups/logs_$(date +%Y%m%d).tar.gz logs/

# Backup credentials (encrypted)
python manage.py dumpdata apps.core.models.CredentialStore > backups/credentials.json
# Keep this file secure!
```

---

## Summary

### Testing Flow

```
1. Start all services (Redis, Ollama, Django, Celery)
   ↓
2. Access http://localhost:8000/system/test/
   ↓
3. Wait for tests to execute (5-15 seconds)
   ↓
4. Review results:
   - Green (✓) = Working
   - Red (✗) = Check logs or configure
   ↓
5. Click "Refresh Tests" to re-run
   ↓
6. Check logs for any errors
   ↓
7. Configure missing services as needed
   ↓
8. Repeat until all critical tests pass
```

### Success Criteria

✓ All critical tests (Database, Redis) are passing
✓ Page loads in < 15 seconds
✓ No console errors in Django terminal
✓ No ERROR in logs/mcube_ai.log
✓ All required services running

Once you see green checkmarks on the test page, your system is healthy and ready to use!
