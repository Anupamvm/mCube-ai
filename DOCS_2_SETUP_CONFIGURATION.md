# System Test Page - Setup and Configuration Guide

## Complete Instructions for Setting Up and Configuring the mCube AI Trading System Test Page

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Database Configuration](#database-configuration)
4. [Authentication Setup](#authentication-setup)
5. [API Credentials Configuration](#api-credentials-configuration)
6. [Third-Party Service Integration](#third-party-service-integration)
7. [Environment Variables](#environment-variables)
8. [Verification](#verification)

---

## Prerequisites

### System Requirements

```
- Python 3.10+
- Django 4.2+
- SQLite3 (default)
- Redis (for Celery)
- Chrome/Chromium browser (for Trendlyne scraping)
- 2GB+ free disk space
```

### Required Python Packages

```
Django==4.2.7
django-background-tasks==1.2.8
celery==5.3.4
redis==5.0.1
requests==2.31.0
selenium>=4.15.2
beautifulsoup4>=4.12.2
pandas>=2.2.0
chromadb==0.4.18
sentence-transformers==2.2.2
```

### Check Your Setup

```bash
# Check Python version
python --version  # Should be 3.10+

# Check Django version
python -m django --version  # Should be 4.2+

# Check installed packages
pip list | grep -E "Django|celery|redis|selenium"
```

---

## Initial Setup

### Step 1: Clone and Navigate to Project

```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai/
```

### Step 2: Create and Activate Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment (macOS/Linux)
source venv/bin/activate

# OR on Windows
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt

# Install any missing broker SDK packages
pip install breeze-connect  # ICICI Breeze
# For Kotak Neo, use the local SDK or install from source
```

### Step 4: Verify Installation

```bash
# Test Django
python manage.py check

# Should output: "System check identified no issues (0 silenced)."

# If you get errors about neo_api_client:
# This is a pre-existing issue. You can safely ignore it for testing.
```

---

## Database Configuration

### Step 1: Prepare Database

```bash
# Run migrations to set up database
python manage.py migrate

# This creates all necessary tables in db.sqlite3
```

### Step 2: Create Superuser

```bash
# Create an admin user
python manage.py createsuperuser

# Follow the prompts:
# Username: admin
# Email: admin@example.com
# Password: (enter secure password)
# Password (again): (confirm)

# Example:
# $ python manage.py createsuperuser
# Username: admin
# Email: admin@mcube.local
# Password:
# Password (again):
# Superuser created successfully.
```

### Step 3: Verify Database

```bash
# Open Django shell
python manage.py shell

# Check if user was created
from django.contrib.auth.models import User
User.objects.all()
# Output: <QuerySet [<User: admin>]>

# Exit shell
exit()
```

---

## Authentication Setup

### Create Admin Group (Optional but Recommended)

```bash
# Start Django shell
python manage.py shell

# Import models
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.models import User

# Create Admin group
admin_group, created = Group.objects.get_or_create(name='Admin')

# Get your admin user
admin_user = User.objects.get(username='admin')

# Add user to Admin group (optional - superuser already has access)
admin_user.groups.add(admin_group)

# Exit shell
exit()
```

### Understanding User Roles

The test page has two permission levels:

#### 1. Required: Django Superuser
- Full access to everything
- Can access test page automatically
- Can create other users

#### 2. Alternative: Admin Group Member
- Regular user added to "Admin" group
- Can access test page
- Limited to specific permissions

### Add Additional Admin Users

```bash
# In Django shell
from django.contrib.auth.models import User, Group

# Create new user
new_user = User.objects.create_user(
    username='admin2',
    email='admin2@example.com',
    password='secure_password_here'
)

# Option 1: Make superuser
new_user.is_superuser = True
new_user.is_staff = True
new_user.save()

# Option 2: Add to Admin group
admin_group = Group.objects.get(name='Admin')
new_user.groups.add(admin_group)
```

### Secure Password Management

**IMPORTANT**: Do NOT hardcode passwords in code!

```python
# WRONG - Never do this
password = "hardcoded_password"

# RIGHT - Use environment variables
import os
password = os.getenv('ADMIN_PASSWORD')

# RIGHT - Use secure input during setup
from getpass import getpass
password = getpass("Enter admin password: ")
```

---

## API Credentials Configuration

### Step 1: Access Django Admin

```bash
# Start Django development server
python manage.py runserver

# Open browser and navigate to:
# http://localhost:8000/admin/

# Login with your superuser credentials
# Username: admin
# Password: (your password)
```

### Step 2: Configure Broker Credentials

#### For ICICI Breeze:

1. Click on **"Credential Stores"** in Django admin
2. Click **"Add Credential Store"**
3. Fill in the form:
   ```
   Service: breeze
   Username: (your Breeze username/email)
   Password: (your Breeze password - encrypted in DB)
   API Key: (your Breeze API key)
   Extra Data: (any additional config as JSON)
   ```
4. Click **Save**

#### For Kotak Neo:

1. Click **"Add Credential Store"** again
2. Fill in the form:
   ```
   Service: kotakneo
   Username: (your Kotak Neo username)
   Password: (your Kotak Neo password)
   Session Token: (optional - set during login)
   Extra Data: (mobile number, etc.)
   ```
3. Click **Save**

### Step 3: Configure Trendlyne Credentials

1. Click **"Add Credential Store"**
2. Fill in:
   ```
   Service: trendlyne
   Username: (your Trendlyne email)
   Password: (your Trendlyne password)
   API Key: (if available)
   Extra Data: {}
   ```
3. Click **Save**

### Step 4: Create Broker Accounts

Navigate to **Broker Accounts** in Django admin:

```
Account Details:
  - Broker: ICICI (or KOTAK)
  - Account Number: UNIQUE_ACCOUNT_ID
  - Account Name: My Trading Account
  - Allocated Capital: 100000.00 (in INR)
  - Is Active: ✓ (checked)
  - Is Paper Trading: ✓ (checked for testing)
  - Max Daily Loss: 5000.00
  - Max Weekly Loss: 10000.00
  - Notes: Test account for development
```

### Step 5: Create API Credentials Link

For each Broker Account, create API credentials:

```
Associated Account: (select from dropdown)
Consumer Key: (from broker API settings)
Consumer Secret: (from broker API settings)
Access Token: (if using OAuth)
Refresh Token: (if using OAuth)
Mobile Number: (for Kotak)
Password: (encrypted)
Is Valid: ✓ (checked after testing)
Last Authenticated: (auto-filled)
Expires At: (set to future date)
```

---

## Third-Party Service Integration

### 1. Ollama Setup

#### Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl https://ollama.ai/install.sh | sh

# Windows
# Download from https://ollama.ai
```

#### Run Ollama Service

```bash
# Start Ollama (runs on localhost:11434 by default)
ollama serve

# In another terminal, pull a model
ollama pull deepseek-r1:7b

# Verify installation
curl http://localhost:11434/api/tags
```

#### Update Django Settings

Verify `/mcube_ai/settings.py`:

```python
OLLAMA_BASE_URL = 'http://localhost:11434'
OLLAMA_MODEL = 'deepseek-r1:7b'  # or other model
```

### 2. Redis Setup

#### Install Redis

```bash
# macOS
brew install redis

# Linux
sudo apt-get install redis-server

# Windows
# Use Windows Subsystem for Linux (WSL) or Docker
# Or download from https://github.com/microsoftarchive/redis/releases
```

#### Start Redis Service

```bash
# macOS
brew services start redis

# Linux
sudo systemctl start redis-server

# Verify it's running
redis-cli ping
# Should return: PONG
```

#### Update Django Settings

Verify `/mcube_ai/settings.py`:

```python
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
```

### 3. Trendlyne Setup

#### Prerequisites

- Trendlyne account with active subscription
- Chrome/Chromium browser installed
- Username and password saved in Django admin (see API Credentials section)

#### Configuration

1. **Store Credentials**:
   - Go to Django admin → Credential Stores
   - Add service='trendlyne' credentials

2. **Create Data Directory**:
   ```bash
   mkdir -p apps/data/trendlynedata
   mkdir -p apps/data/tldata
   chmod 755 apps/data/trendlynedata apps/data/tldata
   ```

3. **Verify Selenium Dependencies**:
   ```bash
   python -c "import selenium; print(selenium.__version__)"
   python -c "import chromedriver_autoinstaller; print('OK')"
   ```

---

## Environment Variables

### Create .env File

```bash
# Copy example file
cp .env.example .env

# Edit the file
nano .env  # or use your favorite editor
```

### Required Environment Variables

```env
# Django Configuration
DEBUG=True
SECRET_KEY=your-very-secret-key-here-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=sqlite:///db.sqlite3

# Redis/Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Ollama/LLM
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-r1:7b

# Trendlyne
TRENDLYNE_API_KEY=your-api-key-here
TRENDLYNE_USERNAME=your-username
TRENDLYNE_PASSWORD=your-password

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# Logging
LOG_LEVEL=DEBUG
LOG_FORMAT=verbose
```

### Load Environment Variables

If using python-dotenv:

```python
# In mcube_ai/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
```

### Sensitive Information Best Practices

```
⚠️ NEVER commit .env file to git
✓ Add .env to .gitignore
✓ Keep passwords out of code
✓ Use environment variables for secrets
✓ Rotate passwords regularly
✓ Use secure password managers
✓ Log credentials access
✓ Encrypt sensitive data at rest
```

---

## Verification

### Step 1: Verify Django Setup

```bash
# Run Django checks
python manage.py check

# Expected output:
# System check identified no issues (0 silenced).
```

### Step 2: Start Services

```bash
# Terminal 1: Start Redis
redis-cli ping  # Check if running, or:
redis-server

# Terminal 2: Start Ollama
ollama serve

# Terminal 3: Start Django
python manage.py runserver
```

### Step 3: Login to Django Admin

```
Open browser: http://localhost:8000/admin/
Username: admin
Password: (your password)

Verify you can see:
- ✓ Authentication and Authorization section
- ✓ Users (with 'admin' user listed)
- ✓ Groups (with 'Admin' group if created)
- ✓ Credential Stores (should show your credentials)
- ✓ Broker Accounts (if configured)
```

### Step 4: Access Test Page

```
Open browser: http://localhost:8000/system/test/

You should see:
- ✓ Page title: "mCube AI - System Test Dashboard"
- ✓ Statistics cards showing test results
- ✓ Multiple test categories listed
- ✓ Test results with checkmarks (✓) or X marks (✗)
- ✓ Auto-refresh countdown (5 minutes)
```

### Step 5: Verify Each Component

#### Database Tests
```
Expected: All should PASS (✓)
- Database Connection ✓
- Migrations Status ✓
- Database Tables ✓
```

#### Brokers Tests
```
Expected: Depends on configuration
- Broker Limits Access: ✓ or ✗ (if no data yet)
- Broker Positions: ✓ or ✗
- Option Chain: ✓ or ✗
- Historical Data: ✓ or ✗
- Credentials: ✗ (fail if not configured, ✓ if configured)
```

#### Trendlyne Tests
```
Expected: Depends on Trendlyne setup
- Trendlyne Credentials: ✓ or ✗
- Website Access: ✓
- ChromeDriver: ✓
- Data Directory: ✓ or ✗
- F&O Data: ✗ (until first scrape)
- Market Snapshot: ✗ (until first scrape)
- Forecaster Data: ✗ (until first scrape)
- Dependencies: ✓
```

#### Redis Tests
```
Expected: Should PASS if Redis is running
- Redis Connection: ✓
```

#### Background Tasks
```
Expected: Should PASS
- Background Tasks: ✓
- Task Definitions: ✓
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'neo_api_client'"

**Cause**: Pre-existing dependency issue with Kotak Neo SDK

**Solution Options**:
1. Ignore it (test page still works for other components)
2. Comment out Kotak Neo import in `apps/brokers/integrations/kotak_neo.py`
3. Install correct SDK from Kotak

### Issue: "Permission Denied" on test page

**Cause**: Not logged in or not an admin user

**Solution**:
1. Go to http://localhost:8000/admin/
2. Login with superuser credentials
3. Then visit http://localhost:8000/system/test/

### Issue: Redis Connection Failed

**Cause**: Redis not running

**Solution**:
```bash
# Check if Redis is running
redis-cli ping

# If not, start it
redis-server

# Or with Homebrew
brew services start redis
```

### Issue: Ollama Connection Failed

**Cause**: Ollama service not running

**Solution**:
```bash
# Start Ollama in another terminal
ollama serve

# Pull the model if not already done
ollama pull deepseek-r1:7b

# Verify connection
curl http://localhost:11434/api/tags
```

### Issue: Database tables don't exist

**Cause**: Migrations not applied

**Solution**:
```bash
# Apply all migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

### Issue: Trendlyne tests all failing

**Cause**: Credentials not configured or Selenium issue

**Solution**:
1. Check Django admin → Credential Stores → trendlyne exists
2. Verify Chrome browser is installed
3. Check Selenium is installed: `pip list | grep -i selenium`
4. Check chromedriver-autoinstaller: `pip list | grep chromedriver`

---

## Summary Checklist

- [ ] Python 3.10+ installed
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Database migrations applied (`python manage.py migrate`)
- [ ] Superuser created (`python manage.py createsuperuser`)
- [ ] Redis installed and running
- [ ] Ollama installed and running (optional but recommended)
- [ ] Broker credentials configured in Django admin
- [ ] Trendlyne credentials configured (if using Trendlyne)
- [ ] Django development server running (`python manage.py runserver`)
- [ ] Test page accessible at http://localhost:8000/system/test/
- [ ] All required services running (Redis, Ollama if needed)

Once all items are checked, your system is ready for testing!
