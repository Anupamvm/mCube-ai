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

echo "============================================"
echo "mCube-ai Complete Installation & Run"
echo "============================================"

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
    echo "   Install with: brew install python3"
    exit 1
else
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo "✓ Python $PYTHON_VERSION is installed"
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
cat > .env << 'ENVEOF'
# Django
SECRET_KEY=django-insecure-mcube-ai-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Redis
REDIS_URL=redis://localhost:6379/0

# Kotak Neo API
KOTAK_CONSUMER_KEY=NkmJfGnAehLpdDm3wSPFR7iCMj4a
KOTAK_CONSUMER_SECRET=H8Q60_oBa2PkSOBJXnk7zbOvGqUa
KOTAK_MOBILE=AAQHA1835B
KOTAK_PASSWORD=Anupamvm2@

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
pip cache purge 2>/dev/null || true

# ============================================================================
# STEP 5: Install Python requirements
# ============================================================================
echo ""
echo "Step 5/10: Installing Python requirements..."
echo "--------------------------------------------"
pip install --no-cache-dir -r requirements.txt

# ============================================================================
# STEP 6: Install kotak-neo-api
# ============================================================================
echo ""
echo "Step 6/10: Installing kotak-neo-api..."
echo "--------------------------------------------"
pip install -e ./kotak-neo-api

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

echo "✓ Created directories:"
echo "  - logs/       (for application logs)"
echo "  - llm_models/ (for LLM model files)"
echo "  - static/     (for static files)"
echo "  - media/      (for uploaded media)"
echo "  - templates/  (for Django templates)"

# ============================================================================
# STEP 8: Run Django makemigrations
# ============================================================================
echo ""
echo "Step 8/10: Running Django makemigrations..."
echo "--------------------------------------------"
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

# Kotak Neo CredentialStore
kotak_creds, created = CredentialStore.objects.update_or_create(
    service='kotakneo',
    name='default',
    defaults={
        'api_key': 'NkmJfGnAehLpdDm3wSPFR7iCMj4a',
        'api_secret': 'H8Q60_oBa2PkSOBJXnk7zbOvGqUa',
        'username': 'AAQHA1835B',  # PAN (used for login)
        'password': 'Anupamvm2@',
        'neo_password': 'Anupamvm2@',  # MPIN (update if different)
        'pan': 'AAQHA1835B',  # PAN number
    }
)

if created:
    print('✓ Created Kotak Neo CredentialStore')
else:
    print('✓ Updated Kotak Neo CredentialStore')

# ICICI Breeze CredentialStore (API credentials + Login credentials for auto-login)
# Only set defaults for new entries - don't overwrite existing session tokens
breeze_creds, created = CredentialStore.objects.get_or_create(
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
    # Update only API key/secret if missing, preserve session_token and login credentials
    updated = False
    if not breeze_creds.api_key:
        breeze_creds.api_key = '6561_m2784f16J&R88P3429@66Y89^46'
        updated = True
    if not breeze_creds.api_secret:
        breeze_creds.api_secret = 'l6_(162788u1p629549_)499O158881c'
        updated = True
    if not breeze_creds.username:
        breeze_creds.username = '9890688965'
        updated = True
    if not breeze_creds.password:
        breeze_creds.password = 'Anupamvm2@'
        updated = True
    if updated:
        breeze_creds.save()
        print('✓ Updated ICICI Breeze CredentialStore (filled missing fields)')
    else:
        print('✓ ICICI Breeze CredentialStore exists (preserved existing credentials)')

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

# Kill existing Django server
pkill -f "manage.py runserver" 2>/dev/null || true

# Kill existing Telegram bot (all possible patterns)
pkill -f "run_telegram_bot" 2>/dev/null || true
pkill -f "telegram_bot" 2>/dev/null || true

# Delete existing Telegram webhook (prevents conflicts)
echo "Clearing Telegram webhook..."
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook" > /dev/null 2>&1 || true

# IMPORTANT: Telegram polling only allows ONE bot instance globally
echo ""
echo "⚠️  TELEGRAM BOT WARNING:"
echo "   Only ONE polling bot instance can run at a time (across ALL machines)."
echo "   If the bot is running on another machine (office/home), it will conflict!"
echo ""

# Kill existing Celery workers
pkill -f "celery.*mcube" 2>/dev/null || true

# Remove stale lock file
rm -f /tmp/mcube_telegram_bot.lock

# Clear Python cache to avoid stale imports
find "$SCRIPT_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

sleep 2

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
        do script "cd '$SCRIPT_DIR' && source venv/bin/activate && echo '============================================' && echo 'mCube Django Server' && echo '============================================' && echo '' && python manage.py runserver 0.0.0.0:8000"
        set custom title of front window to "mCube - Django Server"
    end tell
APPLESCRIPT

    echo "✓ Django server starting in new terminal..."
    echo "  URL: http://localhost:8000"

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
    osascript <<APPLESCRIPT
    tell application "Terminal"
        activate
        do script "cd '$SCRIPT_DIR' && echo '============================================' && echo 'mCube Celery Worker' && echo '============================================' && echo '' && ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=2"
        set custom title of front window to "mCube - Celery Worker"
    end tell
APPLESCRIPT

    echo "✓ Celery worker starting in new terminal..."
    echo "  Queues: data, strategies, monitoring, risk, reports, celery"

    sleep 1

    # Terminal 4: Celery Beat (Scheduler) (use venv python -m celery)
    osascript <<APPLESCRIPT
    tell application "Terminal"
        activate
        do script "cd '$SCRIPT_DIR' && echo '============================================' && echo 'mCube Celery Beat (Scheduler)' && echo '============================================' && echo '' && ./venv/bin/python -m celery -A mcube_ai beat -l info"
        set custom title of front window to "mCube - Celery Beat"
    end tell
APPLESCRIPT

    echo "✓ Celery beat (scheduler) starting in new terminal..."
    echo "  Scheduled tasks enabled"

    sleep 1

else
    # Linux - Use gnome-terminal or xterm

    if command -v gnome-terminal &> /dev/null; then
        echo "Opening gnome-terminal windows for each service..."

        # Django Server
        gnome-terminal --title="mCube - Django Server" -- bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python manage.py runserver 0.0.0.0:8000; exec bash"
        sleep 1

        # Telegram Bot
        gnome-terminal --title="mCube - Telegram Bot" -- bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python manage.py run_telegram_bot; exec bash"
        sleep 1

        # Celery Worker (use python -m celery for correct venv)
        gnome-terminal --title="mCube - Celery Worker" -- bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=2; exec bash"
        sleep 1

        # Celery Beat (use python -m celery for correct venv)
        gnome-terminal --title="mCube - Celery Beat" -- bash -c "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai beat -l info; exec bash"

    elif command -v xterm &> /dev/null; then
        echo "Opening xterm windows for each service..."

        xterm -title "mCube - Django Server" -e "cd '$SCRIPT_DIR' && ./venv/bin/python manage.py runserver 0.0.0.0:8000" &
        sleep 1
        xterm -title "mCube - Telegram Bot" -e "cd '$SCRIPT_DIR' && ./venv/bin/python manage.py run_telegram_bot" &
        sleep 1
        xterm -title "mCube - Celery Worker" -e "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=2" &
        sleep 1
        xterm -title "mCube - Celery Beat" -e "cd '$SCRIPT_DIR' && ./venv/bin/python -m celery -A mcube_ai beat -l info" &

    else
        echo "No supported terminal emulator found (gnome-terminal or xterm)"
        echo "Starting services in background instead..."

        nohup ./venv/bin/python manage.py runserver 0.0.0.0:8000 > logs/django_server.log 2>&1 &
        nohup ./venv/bin/python manage.py run_telegram_bot > logs/telegram_bot.log 2>&1 &
        nohup ./venv/bin/python -m celery -A mcube_ai worker -l info -Q data,strategies,monitoring,risk,reports,celery --concurrency=2 > logs/celery_worker.log 2>&1 &
        nohup ./venv/bin/python -m celery -A mcube_ai beat -l info > logs/celery_beat.log 2>&1 &

        echo "Services started in background. Check logs/ directory for output."
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
echo "  1. Django Server:    http://localhost:8000"
echo "  2. Telegram Bot:     @dmcube_bot"
echo "  3. Celery Worker:    Processing async tasks"
echo "  4. Celery Beat:      Scheduling periodic tasks"
echo "  5. Background Tasks: Django background processor"
echo ""
echo "Admin Panel: http://localhost:8000/admin/"
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
