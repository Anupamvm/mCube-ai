#!/bin/bash

# ============================================================================
# mCube-ai Complete Installation & Run Script
# ============================================================================
# This script handles the complete setup of the mCube-ai project including:
# - Creating virtual environment (if needed)
# - Creating .env file with credentials
# - Installing all Python dependencies
# - Creating required directories
# - Running Django migrations
# - Creating Django superuser
# - Setting up broker accounts and credentials
# - Starting all services in separate terminal windows
# ============================================================================

set -e  # Exit on error

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Parse command line arguments
SKIP_INSTALL=false
SKIP_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --install-only)
            SKIP_RUN=true
            shift
            ;;
        --run-only|--skip-install)
            SKIP_INSTALL=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./install_and_run.sh [OPTIONS]"
            echo ""
            echo "By default, installs everything and starts all services in separate terminals."
            echo ""
            echo "Options:"
            echo "  --install-only    Install only, don't start services"
            echo "  --run-only        Skip installation, just start services"
            echo "  --skip-install    Same as --run-only"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./install_and_run.sh              # Install and start all services"
            echo "  ./install_and_run.sh --install-only   # Install only"
            echo "  ./install_and_run.sh --run-only       # Just start services"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# ============================================================================
# DYNAMIC CELERY CONCURRENCY
# ============================================================================
# Calculate Celery worker concurrency based on available CPU cores
# Uses half the cores to leave resources for other processes (Django, Redis, etc.)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    CPU_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
else
    # Linux
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

echo "============================================"
echo "mCube-ai Complete Installation & Run"
echo "============================================"
echo "CPU Cores: $CPU_CORES | Celery Workers: $CELERY_CONCURRENCY"

# ============================================================================
# SYSTEM REQUIREMENTS CHECK (Always runs)
# ============================================================================
echo ""
echo "Checking system requirements..."
echo "--------------------------------------------"

# Check for Homebrew (macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v brew &> /dev/null; then
        echo "Homebrew not found. Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        echo "✓ Homebrew installed"
    else
        echo "✓ Homebrew is installed"
    fi
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "   Install with: brew install python3"
    else
        echo "   Install with: sudo apt-get install python3 python3-pip python3-venv"
    fi
    exit 1
else
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo "✓ Python $PYTHON_VERSION is installed"
fi

# Check for python3-venv and build tools on Linux
if [[ "$OSTYPE" != "darwin"* ]]; then
    if command -v apt-get &> /dev/null; then
        NEED_APT=false
        python3 -c "import venv" &> /dev/null || NEED_APT=true
        # Check for gcc (needed to compile cryptography, Pillow, lxml, etc.)
        command -v gcc &> /dev/null || NEED_APT=true
        # tmux is required as the terminal fallback on headless/server Ubuntu
        # (gnome-terminal often crashes with snap/GLIBC conflicts on Ubuntu servers)
        command -v tmux &> /dev/null || NEED_APT=true

        if [ "$NEED_APT" = true ]; then
            echo "Installing required system packages (venv, build tools, tmux)..."
            sudo apt-get update -qq
            sudo apt-get install -y python3-venv python3-pip python3-dev \
                build-essential libffi-dev libssl-dev libpq-dev tmux
            echo "✓ System packages installed"
        else
            echo "✓ System packages already installed"
        fi
    elif command -v yum &> /dev/null; then
        if ! python3 -c "import venv" &> /dev/null || ! command -v tmux &> /dev/null; then
            echo "Installing required system packages..."
            sudo yum install -y python3-venv python3-pip python3-devel gcc libffi-devel openssl-devel tmux
            echo "✓ System packages installed"
        fi
    else
        if ! python3 -c "import venv" &> /dev/null; then
            echo "❌ Could not install python3-venv automatically."
            echo "   Please install it manually: sudo apt-get install python3-venv python3-dev build-essential"
            exit 1
        fi
    fi
fi

# Check for Node.js >= 18 (required for Next.js 16)
# Ubuntu's system 'nodejs' package can be v10/v12 — too old. Re-install via nodesource if needed.
_install_node() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install node
    elif command -v apt-get &> /dev/null; then
        echo "  Installing Node.js 20 via NodeSource..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - > /dev/null 2>&1
        sudo apt-get install -y nodejs > /dev/null 2>&1
    elif command -v yum &> /dev/null; then
        curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash - > /dev/null 2>&1
        sudo yum install -y nodejs > /dev/null 2>&1
    else
        echo "❌ Could not install Node.js automatically. Please install Node.js 18+ manually."
        exit 1
    fi
}

if ! command -v node &> /dev/null; then
    echo "Node.js not found. Installing Node.js 20..."
    _install_node
    echo "✓ Node.js $(node --version) installed"
else
    _NODE_MAJOR=$(node --version 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')
    if [ -z "$_NODE_MAJOR" ] || [ "$_NODE_MAJOR" -lt 18 ]; then
        echo "Node.js $( node --version ) is too old (need >= 18). Upgrading to Node.js 20..."
        _install_node
        echo "✓ Node.js $(node --version) installed"
    else
        echo "✓ Node.js $(node --version) is installed"
    fi
fi

# Check for Redis
if ! command -v redis-server &> /dev/null; then
    echo "Redis not found. Installing Redis..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install redis
        echo "✓ Redis installed"
    elif command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y redis-server
        echo "✓ Redis installed"
    elif command -v yum &> /dev/null; then
        sudo yum install -y redis
        echo "✓ Redis installed"
    else
        echo "❌ Could not install Redis automatically."
        echo "   Please install Redis manually and try again."
        exit 1
    fi
else
    echo "✓ Redis is installed"
fi

# Start Redis if not running
if ! redis-cli ping &> /dev/null; then
    echo "Starting Redis..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew services start redis
    else
        sudo systemctl start redis-server 2>/dev/null || sudo service redis-server start 2>/dev/null || redis-server --daemonize yes
    fi
    sleep 2
    if redis-cli ping &> /dev/null; then
        echo "✓ Redis started successfully"
    else
        echo "❌ Failed to start Redis. Please start it manually."
        exit 1
    fi
else
    echo "✓ Redis is running"
fi

echo ""
echo "✓ All system requirements satisfied"

# ============================================================================
# INSTALLATION SECTION
# ============================================================================

if [ "$SKIP_INSTALL" = false ]; then

# ============================================================================
# STEP 1: Create virtual environment (if needed)
# ============================================================================
echo ""
echo "Step 1/10: Checking virtual environment..."
echo "--------------------------------------------"
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# ============================================================================
# STEP 2: Create .env file with credentials
# ============================================================================
echo ""
echo "Step 2/10: Setting up .env file..."
echo "--------------------------------------------"
# Detect server IP for ALLOWED_HOSTS (covers remote browser access to the server)
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ip route get 1 2>/dev/null | awk '{print $NF; exit}' || echo "")
ALLOWED_HOSTS_VALUE="localhost,127.0.0.1"
if [ -n "$SERVER_IP" ]; then
    ALLOWED_HOSTS_VALUE="localhost,127.0.0.1,$SERVER_IP"
    echo "  Detected server IP: $SERVER_IP (added to ALLOWED_HOSTS)"
fi

cat > .env << ENVEOF
# Django
SECRET_KEY=django-insecure-mcube-ai-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=${ALLOWED_HOSTS_VALUE}

# Redis
REDIS_URL=redis://localhost:6379/0

# Kotak Neo API (v2 — TOTP + MPIN auth)
# IMPORTANT: TOTP must be registered at the Kotak Neo Trade API portal:
# https://www.kotakneo.com/platform/kotak-neo-trade-api/totp-registration/
# This is SEPARATE from the regular Kotak Neo app TOTP.
KOTAK_CONSUMER_KEY=4259b484-2863-4869-815c-75be1ac81fc3
KOTAK_UCC=A0YPQ
KOTAK_MOBILE=+919890688965

# ICICI Breeze API
ICICI_API_KEY=6561_m2784f16J&R88P3429@66Y89^46
ICICI_API_SECRET=l6_(162788u1p629549_)499O158881c

# Trendlyne
TRENDLYNE_API_KEY=

# News APIs
NEWS_API_KEY=d027318d9f16ac02e0487003402cab70

# Alerts
TELEGRAM_BOT_TOKEN=6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo
TELEGRAM_CHAT_ID=788423838
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=deepseek-coder:33b

# Paper Trading
PAPER_TRADING=True
ENVEOF
echo "✓ .env file created with credentials"

# ============================================================================
# STEP 3: Upgrade pip, setuptools, and wheel
# ============================================================================
echo ""
echo "Step 3/10: Upgrading pip, setuptools, and wheel..."
echo "--------------------------------------------"
python3 -m pip install --upgrade pip setuptools wheel

# ============================================================================
# STEP 4: Clear pip cache
# ============================================================================
echo ""
echo "Step 4/10: Clearing pip cache..."
echo "--------------------------------------------"
python3 -m pip cache purge 2>/dev/null || true

# ============================================================================
# STEP 4.5: Remove unused legacy packages that cause dependency conflicts
# ============================================================================
echo ""
echo "Step 4.5/10: Removing unused legacy packages..."
echo "--------------------------------------------"
# These packages are not used by the project but may have been installed previously
# and cause dependency conflicts with newer versions of common packages
LEGACY_PACKAGES="mindsdb tensorflow tensorflow-cpu streamlit langchain langchain-core langchain-community snowflake-connector-python anthropic"
for pkg in $LEGACY_PACKAGES; do
    if python3 -m pip show "$pkg" > /dev/null 2>&1; then
        echo "  Removing unused package: $pkg"
        python3 -m pip uninstall -y "$pkg" > /dev/null 2>&1 || true
    fi
done
echo "✓ Legacy packages cleaned up"

# ============================================================================
# STEP 5: Install Python requirements
# ============================================================================
echo ""
echo "Step 5/10: Installing Python requirements..."
echo "--------------------------------------------"
python3 -m pip install --no-cache-dir -r requirements.txt

# ============================================================================
# STEP 6: Install kotak-neo-api
# ============================================================================
echo ""
echo "Step 6/10: Installing kotak-neo-api..."
echo "--------------------------------------------"
python3 -m pip install -e ./kotak-neo-api

# ============================================================================
# STEP 6.5: Build Next.js portfolio frontend
# ============================================================================
echo ""
echo "Step 6.5/10: Building Next.js portfolio frontend..."
echo "--------------------------------------------"

# Bake the correct API base URL into the Next.js bundle.
# NEXT_PUBLIC_ env vars are resolved at build time, not runtime.
# Use the detected server IP so browser requests reach Django from any machine.
_FRONTEND_API_BASE="http://localhost:8001/investments/api"
if [ -n "$SERVER_IP" ]; then
    _FRONTEND_API_BASE="http://$SERVER_IP:8001/investments/api"
fi

cat > "$SCRIPT_DIR/portfolio_frontend/.env.local" << FRONTENDENV
NEXT_PUBLIC_API_BASE=${_FRONTEND_API_BASE}
FRONTENDENV

echo "  API base baked into bundle: ${_FRONTEND_API_BASE}"

cd "$SCRIPT_DIR/portfolio_frontend"
echo "  Installing npm packages..."
# Use a temp file so set -e can see npm's exit code (pipe would hide it)
_npm_log=$(mktemp)
npm install 2>&1 | tee "$_npm_log" | tail -3
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "❌ npm install failed. See: $_npm_log"; exit 1; }
rm -f "$_npm_log"
echo "  Running production build..."
npm run build
cd "$SCRIPT_DIR"
echo "✓ Next.js portfolio frontend built (serves on port 3001)"

# ============================================================================
# STEP 7: Create necessary directories
# ============================================================================
echo ""
echo "Step 7/10: Creating necessary directories..."
echo "--------------------------------------------"
mkdir -p logs
mkdir -p llm_models
mkdir -p static
mkdir -p media
mkdir -p templates
mkdir -p data/SecurityMaster

echo "✓ Created directories:"
echo "  - logs/               (for application logs)"
echo "  - llm_models/         (for LLM model files)"
echo "  - static/             (for static files)"
echo "  - media/              (for uploaded media)"
echo "  - templates/          (for Django templates)"
echo "  - data/SecurityMaster (for ICICI SecurityMaster files)"

# ============================================================================
# STEP 7.5: Check and repair SQLite database if malformed
# ============================================================================
echo ""
echo "Step 7.5/10: Checking database integrity..."
echo "--------------------------------------------"
DB_FILE="$SCRIPT_DIR/db.sqlite3"

# Always remove stale WAL sidecar files — they are NOT tracked by git but can
# be left behind after a crash or an unclean shutdown and will corrupt the DB.
rm -f "${DB_FILE}-shm" "${DB_FILE}-wal"

if [ -f "$DB_FILE" ]; then
    if command -v sqlite3 &> /dev/null; then
        INTEGRITY=$(sqlite3 "$DB_FILE" "PRAGMA integrity_check;" 2>/dev/null | head -1)
        if [ "$INTEGRITY" != "ok" ]; then
            echo "  ⚠ Database is malformed (integrity_check: $INTEGRITY). Attempting recovery..."
            DUMP_FILE=$(mktemp /tmp/mcube_db_dump_XXXXXX.sql)
            if sqlite3 "$DB_FILE" ".dump" > "$DUMP_FILE" 2>/dev/null && [ -s "$DUMP_FILE" ]; then
                mv "$DB_FILE" "${DB_FILE}.bak"
                if sqlite3 "$DB_FILE" < "$DUMP_FILE" 2>/dev/null; then
                    echo "  ✓ Database recovered from dump (backup: db.sqlite3.bak)"
                else
                    echo "  ⚠ Dump import failed. Starting with a fresh database (backup: db.sqlite3.bak)."
                    rm -f "$DB_FILE"
                fi
            else
                echo "  ⚠ Cannot dump database. Starting with a fresh database (backup: db.sqlite3.bak)."
                mv "$DB_FILE" "${DB_FILE}.bak"
            fi
            rm -f "$DUMP_FILE"
        else
            echo "✓ Database integrity OK"
        fi
    else
        echo "  (sqlite3 CLI not found — skipping integrity check)"
    fi
else
    echo "✓ No existing database — will be created by migrate"
fi

# ============================================================================
# STEP 8: Run Django makemigrations
# ============================================================================
echo ""
echo "Step 8/10: Running Django makemigrations..."
echo "--------------------------------------------"

# Heal ALL migration inconsistencies from a previous failed installation.
# A partial install may leave some migrations applied whose dependencies are not,
# causing InconsistentMigrationHistory on makemigrations.
# We loop until every applied migration has all its declared dependencies recorded.
# recorder.record_applied() is exactly what Django's --fake does internally —
# it writes a row to django_migrations without touching any database schema.
python manage.py shell -c "
from django.db.migrations.recorder import MigrationRecorder
from django.db.migrations.loader import MigrationLoader
from django.db import connection

try:
    for _pass in range(50):  # cap to avoid infinite loop
        recorder = MigrationRecorder(connection)
        loader   = MigrationLoader(connection, ignore_no_migrations=True)
        applied  = set(recorder.applied_migrations())

        missing = set()
        for migration in applied:
            if migration not in loader.graph.node_map:
                continue
            for parent in loader.graph.node_map[migration].parents:
                if parent not in applied:
                    missing.add(parent)

        if not missing:
            if _pass > 0:
                print('  All migration inconsistencies resolved.')
            break

        for app, name in sorted(missing):
            print('  Recording missing dependency: ' + app + '.' + name)
            recorder.record_applied(app, name)

except Exception:
    pass  # Fresh DB (migrations table does not exist yet) — migrate handles it
" 2>/dev/null || true

python manage.py makemigrations

# ============================================================================
# STEP 9: Run Django migrate
# ============================================================================
echo ""
echo "Step 9/10: Running Django migrate..."
echo "--------------------------------------------"
python manage.py migrate

# ============================================================================
# STEP 10: Create Django superuser and broker credentials
# ============================================================================
echo ""
echo "Step 10/10: Creating Django superuser and broker credentials..."
echo "--------------------------------------------"

# Create superuser
python manage.py shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()

# Check if superuser already exists
username = 'anupamvm'
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username=username,
        email='anupamvm@gmail.com',
        password='Anupamvm1!'
    )
    print('✓ Superuser created successfully!')
else:
    print('✓ Superuser already exists!')
EOF

# Create broker accounts and API credentials
python manage.py shell <<'EOF'
from decimal import Decimal
from apps.accounts.models import BrokerAccount
from apps.core.models import CredentialStore
from apps.core.constants import BROKER_KOTAK, BROKER_ICICI

print("Setting up broker accounts...")

# ============================================================================
# Kotak Neo Account
# ============================================================================
kotak_account, created = BrokerAccount.objects.update_or_create(
    broker=BROKER_KOTAK,
    account_number='AAQHA1835B',
    defaults={
        'account_name': 'Kotak Neo - Main',
        'allocated_capital': Decimal('60000000'),  # ₹6 Crores
        'is_active': True,
        'is_paper_trading': True,  # Start with paper trading
        'max_daily_loss': Decimal('200000'),  # ₹2 Lakhs
        'max_weekly_loss': Decimal('500000'),  # ₹5 Lakhs
        'notes': 'Kotak account for Weekly Nifty Strangle strategy'
    }
)

if created:
    print(f'✓ Created Kotak account: {kotak_account.account_name}')
else:
    print(f'✓ Updated Kotak account: {kotak_account.account_name}')

# ============================================================================
# ICICI Breeze Account
# ============================================================================
icici_account, created = BrokerAccount.objects.update_or_create(
    broker=BROKER_ICICI,
    account_number='52780531',
    defaults={
        'account_name': 'ICICI Breeze - Main',
        'allocated_capital': Decimal('12000000'),  # ₹1.2 Crores
        'is_active': True,
        'is_paper_trading': True,  # Start with paper trading
        'max_daily_loss': Decimal('150000'),  # ₹1.5 Lakhs
        'max_weekly_loss': Decimal('400000'),  # ₹4 Lakhs
        'notes': 'ICICI account for LLM-validated Futures strategy'
    }
)

if created:
    print(f'✓ Created ICICI account: {icici_account.account_name}')
else:
    print(f'✓ Updated ICICI account: {icici_account.account_name}')

# ============================================================================
# CredentialStore - Broker API Credentials (replaces old APICredential model)
# ============================================================================

print("\nSetting up CredentialStore for broker APIs...")

# Kotak Neo CredentialStore (v2 API — TOTP + MPIN auth)
kotak_creds, created = CredentialStore.objects.update_or_create(
    service='kotakneo',
    name='default',
    defaults={
        'api_key': '4259b484-2863-4869-815c-75be1ac81fc3',  # Consumer Key
        'ucc': 'A0YPQ',  # Unique Client Code (zero not O)
        'mobile_number': '+919890688965',  # Registered mobile number (Neo v2 requires +91 prefix)
        'neo_password': '284321',  # MPIN
        'totp_secret': 'RBOWJJRPMPNPHDL4X6FIGZ3AZ4',  # TOTP secret from Trade API registration
        'username': '+919890688965',  # Mobile number (legacy field, kept for compat)
    }
)

if created:
    print('✓ Created Kotak Neo CredentialStore')
else:
    print('✓ Updated Kotak Neo CredentialStore')

# ICICI Breeze CredentialStore (API credentials + Login credentials for auto-login)
# Always update API credentials; session_token is NOT in defaults so it is preserved.
breeze_creds, created = CredentialStore.objects.update_or_create(
    service='breeze',
    name='default',
    defaults={
        'api_key': '6561_m2784f16J&R88P3429@66Y89^46',
        'api_secret': 'l6_(162788u1p629549_)499O158881c',
        'username': '9890688965',
        'password': 'Anupamvm2@',
    }
)

if created:
    print('✓ Created ICICI Breeze CredentialStore (with auto-login credentials)')
else:
    print('✓ Updated ICICI Breeze CredentialStore (session_token preserved)')

# ============================================================================
# Trendlyne Credentials (Market Data Provider)
# ============================================================================
trendlyne_creds, created = CredentialStore.objects.update_or_create(
    service='trendlyne',
    name='default',
    defaults={
        'username': 'avmgp.in@gmail.com',
        'password': 'Anupamvm1!',
    }
)

if created:
    print('✓ Created Trendlyne credentials')
else:
    print('✓ Updated Trendlyne credentials')

# ============================================================================
# Telegram Bot Credentials
# ============================================================================
telegram_creds, created = CredentialStore.objects.update_or_create(
    service='telegram',
    name='default',
    defaults={
        'api_key': '6386769117:AAHt_4krbiU0KlBdCLhhVgC-TCQVUnzvywo',  # Bot token
        'username': '788423838',  # Your chat ID (stored in username field)
    }
)

if created:
    print('✓ Created Telegram bot credentials (@dmcube_bot)')
else:
    print('✓ Updated Telegram bot credentials (@dmcube_bot)')

# ============================================================================
# GNews.io Credentials (News Data Provider)
# ============================================================================
gnewsio_creds, created = CredentialStore.objects.update_or_create(
    service='gnewsio',
    name='default',
    defaults={
        'api_key': 'd027318d9f16ac02e0487003402cab70',
        'username': 'avmgp.in@gmail.com',
        'password': 'Anupamvm1!',
    }
)

if created:
    print('✓ Created GNews.io credentials')
else:
    print('✓ Updated GNews.io credentials')

print('\n✓ All broker accounts and credentials configured!')
print(f'  - Kotak: {kotak_account.account_name} (₹{kotak_account.allocated_capital:,.0f})')
print(f'  - ICICI: {icici_account.account_name} (₹{icici_account.allocated_capital:,.0f})')
print(f'  - Total Capital: ₹{kotak_account.allocated_capital + icici_account.allocated_capital:,.0f}')
print(f'  - Kotak Neo API: CredentialStore configured (PAN: AAQHA1835B)')
print(f'  - ICICI Breeze API: CredentialStore configured')
print(f'  - Trendlyne: Market data access configured')
print(f'  - GNews.io: News data provider configured')
print(f'  - Telegram Bot: @dmcube_bot configured (Chat ID: 788423838)')
EOF

# ============================================================================
# Installation Complete
# ============================================================================
echo ""
echo "============================================"
echo "Installation Complete! ✓"
echo "============================================"
echo ""
echo "Summary:"
echo "  ✓ All Python dependencies installed"
echo "  ✓ Database initialized and migrated"
echo "  ✓ Required directories created"
echo "  ✓ Django superuser configured"
echo "  ✓ Broker accounts and API credentials configured"

fi  # End of SKIP_INSTALL check

# ============================================================================
# START SERVICES SECTION
# ============================================================================

if [ "$SKIP_RUN" = false ]; then

echo ""
echo "============================================"
echo "Starting mCube Services..."
echo "============================================"
echo ""

# Ensure we're in the correct directory
cd "$SCRIPT_DIR"

# ============================================================================
# Ensure Redis is running
# ============================================================================
echo "Ensuring Redis is running..."
if ! redis-cli ping &> /dev/null; then
    echo "Starting Redis..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew services start redis
    else
        sudo systemctl start redis-server 2>/dev/null || sudo service redis-server start 2>/dev/null || redis-server --daemonize yes
    fi
    sleep 2
    if redis-cli ping &> /dev/null; then
        echo "✓ Redis started"
    else
        echo "❌ Redis failed to start. Celery requires Redis."
        exit 1
    fi
else
    echo "✓ Redis is running"
fi

# ============================================================================
# Stop any existing services first
# ============================================================================
echo "Stopping any existing services..."

# Kill existing Django server — use SIGKILL so it releases port 8001 immediately.
# pkill covers the normal case; fuser/lsof covers stale or renamed processes.
pkill -9 -f "manage.py runserver" 2>/dev/null || true
if command -v fuser &>/dev/null; then
    fuser -k 8001/tcp 2>/dev/null || true
elif command -v lsof &>/dev/null; then
    lsof -ti tcp:8001 | xargs -r kill -9 2>/dev/null || true
fi

# Kill existing Telegram bot (all possible patterns)
pkill -f "run_telegram_bot" 2>/dev/null || true
pkill -f "telegram_bot" 2>/dev/null || true

# Delete existing Telegram webhook (prevents conflicts)
echo "Clearing Telegram webhook..."
_TG_TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" "$SCRIPT_DIR/.env" 2>/dev/null | cut -d'=' -f2-)
if [ -n "$_TG_TOKEN" ]; then
    curl -s "https://api.telegram.org/bot${_TG_TOKEN}/deleteWebhook" > /dev/null 2>&1 || true
fi

# IMPORTANT: Telegram polling only allows ONE bot instance globally
echo ""
echo "⚠️  TELEGRAM BOT WARNING:"
echo "   Only ONE polling bot instance can run at a time (across ALL machines)."
echo "   If the bot is running on another machine (office/home), it will conflict!"
echo ""

# Kill existing Next.js frontend
pkill -f "next.*start" 2>/dev/null || true
if command -v fuser &>/dev/null; then
    fuser -k 3001/tcp 2>/dev/null || true
elif command -v lsof &>/dev/null; then
    lsof -ti tcp:3001 | xargs -r kill -9 2>/dev/null || true
fi

# Kill existing Celery workers
pkill -f "celery.*mcube" 2>/dev/null || true

# Remove stale lock file
rm -f /tmp/mcube_telegram_bot.lock

# Clear Python cache to avoid stale imports
find "$SCRIPT_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Wait until port 8001 is actually free (max 10 seconds)
echo "Waiting for port 8001 to be free..."
for _i in $(seq 1 10); do
    _port_free=true
    if command -v fuser &>/dev/null; then
        fuser 8001/tcp > /dev/null 2>&1 && _port_free=false
    elif command -v lsof &>/dev/null; then
        lsof -i tcp:8001 > /dev/null 2>&1 && _port_free=false
    fi
    if [ "$_port_free" = true ]; then
        echo "✓ Port 8001 is free"
        break
    fi
    echo "  Still waiting for port 8001... ($_i/10)"
    sleep 1
done

# ============================================================================
# Ensure the Next.js frontend is built before starting it
# (handles --run-only on a fresh clone where build was never run)
# ============================================================================
if [ ! -d "$SCRIPT_DIR/portfolio_frontend/.next" ]; then
    echo ""
    echo "Portfolio frontend not yet built — building now..."
    _RUN_SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "")
    _RUN_API_BASE="http://localhost:8001/investments/api"
    [ -n "$_RUN_SERVER_IP" ] && _RUN_API_BASE="http://$_RUN_SERVER_IP:8001/investments/api"
    cat > "$SCRIPT_DIR/portfolio_frontend/.env.local" << RUNENV
NEXT_PUBLIC_API_BASE=${_RUN_API_BASE}
RUNENV
    cd "$SCRIPT_DIR/portfolio_frontend"
    npm install
    npm run build
    cd "$SCRIPT_DIR"
    echo "✓ Portfolio frontend built"
fi

# ============================================================================
# Open Terminal windows for each service (macOS)
# ============================================================================

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - Use AppleScript to open new Terminal windows

    echo "Opening Terminal windows for each service..."
    echo ""

    # Terminal 1: Django Server
    osascript <<APPLESCRIPT
    tell application "Terminal"
        activate
        do script "cd '$SCRIPT_DIR' && source venv/bin/activate && echo '============================================' && echo 'mCube Django Server' && echo '============================================' && echo '' && lsof -ti tcp:8001 | xargs kill 2>/dev/null; sleep 1; python manage.py runserver 0.0.0.0:8001"
        set custom title of front window to "mCube - Django Server"
    end tell
APPLESCRIPT

    echo "✓ Django server starting in new terminal..."
    echo "  URL: http://localhost:8001"

    sleep 1

    # Terminal 2: Telegram Bot
    osascript <<APPLESCRIPT
    tell application "Terminal"
        activate
        do script "cd '$SCRIPT_DIR' && source venv/bin/activate && echo '============================================' && echo 'mCube Telegram Bot' && echo '============================================' && echo '' && python manage.py run_telegram_bot"
        set custom title of front window to "mCube - Telegram Bot"
    end tell
APPLESCRIPT

    echo "✓ Telegram bot starting in new terminal..."
    echo "  Bot: @dmcube_bot"

    sleep 1

    # Terminal 3: Celery Worker (use venv python -m celery to ensure correct environment)
    # Using tee to write to both terminal AND log file
    osascript <<APPLESCRIPT
    tell application "Terminal"
        activate
        do script "cd '$SCRIPT_DIR' && echo '============================================' && echo 'mCube Celery Worker' && echo '============================================' && echo 'Logs: logs/celery_worker.log' && echo '' && ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=$CELERY_CONCURRENCY 2>&1 | tee -a logs/celery_worker.log"
        set custom title of front window to "mCube - Celery Worker"
    end tell
APPLESCRIPT

    echo "✓ Celery worker starting in new terminal..."
    echo "  Queues: data, strategies, monitoring, risk, reports, celery"
    echo "  Log file: logs/celery_worker.log"

    sleep 1

    # Terminal 4: Celery Beat (Scheduler) (use venv python -m celery)
    # Using tee to write to both terminal AND log file
    osascript <<APPLESCRIPT
    tell application "Terminal"
        activate
        do script "cd '$SCRIPT_DIR' && echo '============================================' && echo 'mCube Celery Beat (Scheduler)' && echo '============================================' && echo 'Logs: logs/celery_beat.log' && echo '' && rm -f celerybeat-schedule.db && ./venv/bin/python -m celery -A mcube_ai beat --scheduler=mcube_ai.celery:DBReloadScheduler -l info 2>&1 | tee -a logs/celery_beat.log"
        set custom title of front window to "mCube - Celery Beat"
    end tell
APPLESCRIPT

    echo "✓ Celery beat (scheduler) starting in new terminal..."
    echo "  Scheduled tasks enabled"
    echo "  Log file: logs/celery_beat.log"

    sleep 1

    # Terminal 5: Next.js Portfolio Frontend
    osascript <<APPLESCRIPT
    tell application "Terminal"
        activate
        do script "cd '$SCRIPT_DIR/portfolio_frontend' && echo '============================================' && echo 'mCube Portfolio Frontend (Next.js)' && echo '============================================' && echo '' && npm start"
        set custom title of front window to "mCube - Portfolio Frontend"
    end tell
APPLESCRIPT

    echo "✓ Portfolio frontend starting in new terminal..."
    echo "  URL: http://localhost:3001"

    sleep 1

else
    # Linux - Use gnome-terminal, konsole, xterm, or run in background

    # Ensure logs directory exists for background mode
    mkdir -p "$SCRIPT_DIR/logs"

    # gnome-terminal launched from within a snap app (e.g. VS Code installed as
    # snap) inherits snap-injected env vars (GIO_MODULE_DIR, GTK_PATH, etc.) that
    # force it to load GIO/GTK modules from the snap cache. Those modules carry an
    # RPATH pointing to /snap/core20/current/lib which loads an older libpthread,
    # which in turn can't resolve __libc_pthread_init from the newer system libc →
    # GLIBC_PRIVATE symbol lookup crash.
    # Fix: strip the snap-injected vars before every gnome-terminal invocation.
    # VS Code snap saves the original (pre-snap) values with _VSCODE_SNAP_ORIG
    # suffix — all were empty before VS Code, so we simply unset them.
    _gt() {
        env -u GIO_MODULE_DIR \
            -u GTK_PATH \
            -u GTK_EXE_PREFIX \
            -u GTK_IM_MODULE_FILE \
            gnome-terminal "$@"
    }

    # Also skip GUI terminals entirely when there is no display (headless/SSH).
    GNOME_TERMINAL_OK=false
    HAS_DISPLAY=false
    [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ] && HAS_DISPLAY=true

    if [ "$HAS_DISPLAY" = true ] && command -v gnome-terminal &> /dev/null; then
        # --version succeeds even on broken snap/core20 installs (the GLIBC error
        # is triggered lazily during VTE init, only when a window opens).
        # Use the cleaned launcher to run a quick window test.
        _gt_err_file=$(mktemp /tmp/.gt_check_XXXXXX 2>/dev/null || echo "/tmp/.gt_check_$$")
        _gt -- bash -c "exit 0" 2>"$_gt_err_file" &
        _gt_test_pid=$!
        sleep 0.5
        if grep -qi "symbol lookup\|undefined symbol\|GLIBC_PRIVATE" "$_gt_err_file" 2>/dev/null; then
            kill "$_gt_test_pid" 2>/dev/null; wait "$_gt_test_pid" 2>/dev/null || true
            echo "gnome-terminal snap/GLIBC conflict persists — falling back to tmux..."
        else
            wait "$_gt_test_pid" 2>/dev/null || true
            GNOME_TERMINAL_OK=true
        fi
        rm -f "$_gt_err_file"
    fi

    if [ "$GNOME_TERMINAL_OK" = true ]; then
        echo "Opening gnome-terminal windows for each service..."

        # Django Server
        _gt --title="mCube - Django Server" -- bash -c "fuser -k 8001/tcp 2>/dev/null; sleep 1; cd '$SCRIPT_DIR' && ./venv/bin/python manage.py runserver 0.0.0.0:8001; exec bash"
        sleep 1

        # Telegram Bot
        _gt --title="mCube - Telegram Bot" -- bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python manage.py run_telegram_bot; exec bash"
        sleep 1

        # Celery Worker (with tee to log file)
        _gt --title="mCube - Celery Worker" -- bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=$CELERY_CONCURRENCY 2>&1 | tee -a logs/celery_worker.log; exec bash"
        sleep 1

        # Celery Beat (with tee to log file)
        _gt --title="mCube - Celery Beat" -- bash -c "cd '$SCRIPT_DIR' && rm -f celerybeat-schedule.db && ./venv/bin/python -m celery -A mcube_ai beat --scheduler=mcube_ai.celery:DBReloadScheduler -l info 2>&1 | tee -a logs/celery_beat.log; exec bash"
        sleep 1

        # Portfolio Frontend (Next.js)
        _gt --title="mCube - Portfolio Frontend" -- bash -c "cd '$SCRIPT_DIR/portfolio_frontend' && npm start; exec bash"

        echo "✓ All services started in gnome-terminal windows"

    elif command -v konsole &> /dev/null; then
        echo "Opening konsole windows for each service..."

        konsole --new-tab -e bash -c "fuser -k 8001/tcp 2>/dev/null; sleep 1; cd '$SCRIPT_DIR' && ./venv/bin/python manage.py runserver 0.0.0.0:8001" &
        sleep 1
        konsole --new-tab -e bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python manage.py run_telegram_bot" &
        sleep 1
        konsole --new-tab -e bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=$CELERY_CONCURRENCY 2>&1 | tee -a logs/celery_worker.log" &
        sleep 1
        konsole --new-tab -e bash -c "cd '$SCRIPT_DIR' && rm -f celerybeat-schedule.db && ./venv/bin/python -m celery -A mcube_ai beat --scheduler=mcube_ai.celery:DBReloadScheduler -l info 2>&1 | tee -a logs/celery_beat.log" &
        sleep 1
        konsole --new-tab -e bash -c "cd '$SCRIPT_DIR/portfolio_frontend' && npm start" &

        echo "✓ All services started in konsole windows"

    elif command -v xterm &> /dev/null; then
        echo "Opening xterm windows for each service..."

        xterm -title "mCube - Django Server" -e bash -c "fuser -k 8001/tcp 2>/dev/null; sleep 1; cd '$SCRIPT_DIR' && ./venv/bin/python manage.py runserver 0.0.0.0:8001" &
        sleep 1
        xterm -title "mCube - Telegram Bot" -e bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python manage.py run_telegram_bot" &
        sleep 1
        xterm -title "mCube - Celery Worker" -e bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=$CELERY_CONCURRENCY 2>&1 | tee -a logs/celery_worker.log" &
        sleep 1
        xterm -title "mCube - Celery Beat" -e bash -c "cd '$SCRIPT_DIR' && rm -f celerybeat-schedule.db && ./venv/bin/python -m celery -A mcube_ai beat --scheduler=mcube_ai.celery:DBReloadScheduler -l info 2>&1 | tee -a logs/celery_beat.log" &
        sleep 1
        xterm -title "mCube - Portfolio Frontend" -e bash -c "cd '$SCRIPT_DIR/portfolio_frontend' && npm start" &

        echo "✓ All services started in xterm windows"

    elif command -v tmux &> /dev/null; then
        echo "Starting services in tmux sessions (reattachable)..."

        tmux new-session  -d -s mcube-django   "fuser -k 8001/tcp 2>/dev/null; sleep 1; cd '$SCRIPT_DIR' && ./venv/bin/python manage.py runserver 0.0.0.0:8001"
        tmux new-session  -d -s mcube-bot      "cd '$SCRIPT_DIR' && ./venv/bin/python manage.py run_telegram_bot"
        tmux new-session  -d -s mcube-worker   "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=$CELERY_CONCURRENCY 2>&1 | tee -a logs/celery_worker.log"
        rm -f celerybeat-schedule.db
        tmux new-session  -d -s mcube-beat     "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai beat --scheduler=mcube_ai.celery:DBReloadScheduler -l info 2>&1 | tee -a logs/celery_beat.log"
        tmux new-session  -d -s mcube-frontend "cd '$SCRIPT_DIR/portfolio_frontend' && npm start 2>&1 | tee -a '$SCRIPT_DIR/logs/portfolio_frontend.log'"

        echo "✓ All services started in tmux sessions"
        echo ""
        echo "Reattach with:"
        echo "  tmux attach -t mcube-django"
        echo "  tmux attach -t mcube-bot"
        echo "  tmux attach -t mcube-worker"
        echo "  tmux attach -t mcube-beat"
        echo "  tmux attach -t mcube-frontend"

    else
        echo "No GUI terminal or tmux found. Starting services in background (headless mode)..."
        echo "Logs will be written to: $SCRIPT_DIR/logs/"

        cd "$SCRIPT_DIR"
        fuser -k 8001/tcp 2>/dev/null; sleep 1
        nohup ./venv/bin/python manage.py runserver 0.0.0.0:8001 > logs/django_server.log 2>&1 &
        echo "  ✓ Django server started (PID: $!) - log: logs/django_server.log"

        nohup ./venv/bin/python manage.py run_telegram_bot > logs/telegram_bot.log 2>&1 &
        echo "  ✓ Telegram bot started (PID: $!) - log: logs/telegram_bot.log"

        nohup ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=$CELERY_CONCURRENCY > logs/celery_worker.log 2>&1 &
        echo "  ✓ Celery worker started (PID: $!) - log: logs/celery_worker.log"

        rm -f celerybeat-schedule.db
        nohup ./venv/bin/python -m celery -A mcube_ai beat --scheduler=mcube_ai.celery:DBReloadScheduler -l info > logs/celery_beat.log 2>&1 &
        echo "  ✓ Celery beat started (PID: $!) - log: logs/celery_beat.log"

        cd "$SCRIPT_DIR/portfolio_frontend"
        nohup npm start > "$SCRIPT_DIR/logs/portfolio_frontend.log" 2>&1 &
        echo "  ✓ Portfolio frontend started (PID: $!) - log: logs/portfolio_frontend.log"
        cd "$SCRIPT_DIR"

        echo ""
        echo "To view logs in real-time:"
        echo "  tail -f logs/django_server.log"
        echo "  tail -f logs/telegram_bot.log"
        echo "  tail -f logs/celery_worker.log"
        echo "  tail -f logs/celery_beat.log"
        echo "  tail -f logs/portfolio_frontend.log"
    fi
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "============================================"
echo "All Services Started! ✓"
echo "============================================"
echo ""
echo "Running Services (in separate terminals):"
echo "  1. Django Server:      http://localhost:8001"
echo "  2. Telegram Bot:       @dmcube_bot"
echo "  3. Celery Worker:      Processing async tasks"
echo "  4. Celery Beat:        Scheduling periodic tasks"
echo "  5. Portfolio Frontend: http://localhost:3001"
echo ""
echo "Admin Panel:        http://localhost:8001/admin/"
echo "Investments (Django): http://localhost:8001/investments/"
echo "Investments (Next.js): http://localhost:3001/"
echo ""
echo "Login Credentials:"
echo "  Username: anupamvm"
echo "  Password: Anupamvm1!"
echo ""
echo "To stop all services:"
echo "  ./stop_services.sh"
echo ""
echo "============================================"

fi  # End of SKIP_RUN check
