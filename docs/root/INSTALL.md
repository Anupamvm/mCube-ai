# mCube-ai Installation Guide

## Quick Installation

For a fresh setup, simply run the installation script:

```bash
./install.sh
```

This single command will:
- ✓ Upgrade pip, setuptools, and wheel
- ✓ Clear pip cache (fixes AssertionError issues)
- ✓ Install all Python dependencies
- ✓ Install kotak-neo-api package
- ✓ Create required directories (logs, llm_models, static, media)
- ✓ Run Django migrations
- ✓ Create Django superuser
- ✓ Configure broker accounts and API credentials (Kotak Neo + ICICI Breeze)

## Prerequisites

Before running the installation:

1. **Python 3.10+** must be installed
2. **Virtual environment** must be created:
   ```bash
   python3 -m venv venv
   ```

## Fresh Installation

For a completely fresh setup on a new machine:

```bash
# 1. Clone the repository
git clone <repository-url>
cd mCube-ai

# 2. Create virtual environment
python3 -m venv venv

# 3. Run installation script
./install.sh
```

## What the Installation Script Does

### Step 1: Upgrade pip Tools
Upgrades pip from old versions (like 22.0.2) to the latest version (25.3) to fix dependency resolution bugs.

### Step 2: Clear pip Cache
Removes corrupted cache files (typically ~11GB) that can cause installation failures.

### Step 3: Install Python Requirements
Installs all packages from `requirements.txt` including:
- Django 4.2.7
- Celery 5.3.4
- Redis 5.0.1
- ChromaDB 0.4.18
- sentence-transformers 2.2.2
- PyTorch and other ML libraries
- Trading APIs (breeze-connect, yfinance)
- Web scraping tools (BeautifulSoup, Selenium)
- Testing frameworks (pytest)

### Step 4: Install kotak-neo-api
Installs the Kotak Neo API package in editable mode from the local directory.

### Step 5: Create Directories
Creates required directories:
- `logs/` - Application logs
- `llm_models/` - LLM model files
- `static/` - Static files (CSS, JS, images)
- `media/` - User-uploaded files
- `templates/` - Django templates

### Step 6-7: Database Setup
- Generates migration files (`makemigrations`)
- Applies all migrations to create database tables (`migrate`)

### Step 8: Create Superuser
Creates a Django admin account with:
- **Username:** anupamvm
- **Email:** anupamvm@gmail.com
- **Password:** Anupamvm1!

### Step 9: Configure Broker Accounts and Credentials
Automatically creates and configures:

**Kotak Neo Account:**
- Account Number: AAQHA1835B
- Allocated Capital: ₹6.0 Cr
- Strategy: Weekly Nifty Strangle
- API credentials configured

**ICICI Breeze Account:**
- Account Number: 52780531
- Allocated Capital: ₹1.2 Cr
- Strategy: LLM-validated Futures
- API credentials configured

**Trendlyne (Market Data Provider):**
- Username: avmgp.in@gmail.com
- Password: Anupamvm1!
- Service: Market data and analyst consensus

**Total System Capital: ₹7.2 Cr**

## Starting the Application

After installation, start the development server:

```bash
# Activate virtual environment
source venv/bin/activate

# Start Django development server
python manage.py runserver
```

Access the application at:
- **Main site:** http://localhost:8000/
- **Admin panel:** http://localhost:8000/admin/

## Optional Services

### Background Tasks
```bash
python manage.py process_tasks
```

### Celery Worker (requires Redis)
```bash
celery -A mcube_ai worker -l info
```

### Celery Beat Scheduler
```bash
celery -A mcube_ai beat -l info
```

## Troubleshooting

### Issue: "ValueError: Unable to configure handler 'file'"
**Solution:** The `logs/` directory is missing. Run:
```bash
mkdir -p logs
```
Or re-run the installation script which creates all required directories.

### Issue: pip AssertionError during installation
**Solution:** This is caused by an outdated pip version. The installation script fixes this by:
1. Upgrading pip to the latest version
2. Clearing the corrupted cache

### Issue: "No module named 'neo_api_client'"
**Solution:** The kotak-neo-api package wasn't installed. Run:
```bash
source venv/bin/activate
pip install -e ./kotak-neo-api
```

### Issue: Migration errors
**Solution:** Re-run migrations:
```bash
source venv/bin/activate
python manage.py makemigrations
python manage.py migrate
```

## Manual Installation Steps

If you prefer to run steps manually instead of using the script:

```bash
# Activate virtual environment
source venv/bin/activate

# Upgrade pip tools
python3 -m pip install --upgrade pip setuptools wheel

# Clear cache
pip cache purge

# Install requirements
pip install --no-cache-dir -r requirements.txt

# Install kotak-neo-api
pip install -e ./kotak-neo-api

# Create directories
mkdir -p logs llm_models static media templates

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser (interactive)
python manage.py createsuperuser
```

## System Requirements

- **OS:** Ubuntu 20.04+ or macOS 10.15+
- **Python:** 3.10 or higher
- **RAM:** Minimum 4GB (8GB recommended for ML features)
- **Disk:** ~15GB free space (for dependencies and ML models)

## Compatibility

The installation script works on:
- ✓ Ubuntu/Linux
- ✓ macOS
- ✗ Windows (use WSL2 instead)

## Next Steps

After installation:

1. **Configure API Keys** - Update `mcube_ai/settings.py` with your API credentials:
   - Telegram Bot Token
   - Trendlyne API Key
   - Broker API credentials

2. **Configure LLM** - Set up Ollama and download models:
   ```bash
   ollama pull deepseek-r1:7b
   ```

3. **Configure Redis** (for Celery):
   ```bash
   sudo apt-get install redis-server  # Ubuntu
   brew install redis                  # macOS
   redis-server
   ```

4. **Run Tests**:
   ```bash
   pytest
   ```

## Getting Help

If you encounter any issues:
1. Check this documentation
2. Review error messages in `logs/mcube_ai.log`
3. Ensure all prerequisites are met
4. Try re-running the installation script

## Upgrading

To update dependencies:

```bash
source venv/bin/activate
pip install --upgrade -r requirements.txt
python manage.py migrate
```

## Uninstalling

To completely remove the installation:

```bash
# Remove virtual environment
rm -rf venv/

# Remove database
rm db.sqlite3

# Remove logs
rm -rf logs/

# Remove cached Python files
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```
