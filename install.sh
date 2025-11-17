#!/bin/bash

# ============================================================================
# mCube-ai Complete Installation Script
# ============================================================================
# This script handles the complete setup of the mCube-ai project including:
# - Fixing pip installation issues
# - Installing all Python dependencies
# - Creating required directories
# - Running Django migrations
# - Creating Django superuser
# ============================================================================

set -e  # Exit on error

echo "============================================"
echo "mCube-ai Complete Installation"
echo "============================================"

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# ============================================================================
# STEP 1: Upgrade pip, setuptools, and wheel
# ============================================================================
echo ""
echo "Step 1/8: Upgrading pip, setuptools, and wheel..."
echo "--------------------------------------------"
python3 -m pip install --upgrade pip setuptools wheel

# ============================================================================
# STEP 2: Clear pip cache
# ============================================================================
echo ""
echo "Step 2/8: Clearing pip cache..."
echo "--------------------------------------------"
pip cache purge

# ============================================================================
# STEP 3: Install Python requirements
# ============================================================================
echo ""
echo "Step 3/8: Installing Python requirements..."
echo "--------------------------------------------"
pip install --no-cache-dir -r requirements.txt

# ============================================================================
# STEP 4: Install kotak-neo-api
# ============================================================================
echo ""
echo "Step 4/8: Installing kotak-neo-api..."
echo "--------------------------------------------"
pip install -e ./kotak-neo-api

# ============================================================================
# STEP 5: Create necessary directories
# ============================================================================
echo ""
echo "Step 5/8: Creating necessary directories..."
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
# STEP 6: Run Django makemigrations
# ============================================================================
echo ""
echo "Step 6/9: Running Django makemigrations..."
echo "--------------------------------------------"
python manage.py makemigrations

# ============================================================================
# STEP 7: Run Django migrate
# ============================================================================
echo ""
echo "Step 7/9: Running Django migrate..."
echo "--------------------------------------------"
python manage.py migrate

# ============================================================================
# STEP 8: Create Django superuser
# ============================================================================
echo ""
echo "Step 8/9: Creating Django superuser..."
echo "--------------------------------------------"
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

# ============================================================================
# STEP 9: Create Broker Accounts and API Credentials
# ============================================================================
echo ""
echo "Step 9/9: Creating broker accounts and API credentials..."
echo "--------------------------------------------"
python manage.py shell <<'EOF'
from decimal import Decimal
from apps.accounts.models import BrokerAccount, APICredential
from apps.core.constants import BROKER_KOTAK, BROKER_ICICI

print("Setting up broker accounts...")

# ============================================================================
# Kotak Neo Account
# ============================================================================
kotak_account, created = BrokerAccount.objects.get_or_create(
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

    # Create API credentials for Kotak
    APICredential.objects.create(
        account=kotak_account,
        consumer_key='NkmJfGnAehLpdDm3wSPFR7iCMj4a',
        consumer_secret='H8Q60_oBa2PkSOBJXnk7zbOvGqUa',
        access_token='284321',
        mobile_number='AAQHA1835B',
        password='Anupamvm2@',
        is_valid=False  # Needs authentication
    )
    print('  ✓ Created API credentials for Kotak')
else:
    print(f'✓ Kotak account already exists: {kotak_account.account_name}')

# ============================================================================
# ICICI Breeze Account
# ============================================================================
icici_account, created = BrokerAccount.objects.get_or_create(
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

    # Create API credentials for ICICI
    APICredential.objects.create(
        account=icici_account,
        consumer_key='6561_m2784f16J&R88P3429@66Y89^46',
        consumer_secret='l6_(162788u1p629549_)499O158881c',
        access_token='52780531',
        is_valid=False  # Needs authentication
    )
    print('  ✓ Created API credentials for ICICI')
else:
    print(f'✓ ICICI account already exists: {icici_account.account_name}')

# ============================================================================
# Trendlyne Credentials (Market Data Provider)
# ============================================================================
from apps.core.models import CredentialStore

trendlyne_creds, created = CredentialStore.objects.get_or_create(
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
    print('✓ Trendlyne credentials already exist')

print('\n✓ All broker accounts and credentials configured!')
print(f'  - Kotak: {kotak_account.account_name} (₹{kotak_account.allocated_capital:,.0f})')
print(f'  - ICICI: {icici_account.account_name} (₹{icici_account.allocated_capital:,.0f})')
print(f'  - Total Capital: ₹{kotak_account.allocated_capital + icici_account.allocated_capital:,.0f}')
print(f'  - Trendlyne: Market data access configured')
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
echo ""
echo "Superuser Credentials:"
echo "  Username: anupamvm"
echo "  Email:    anupamvm@gmail.com"
echo "  Password: Anupamvm1!"
echo ""
echo "Broker Accounts:"
echo "  Kotak Neo:    ₹6.0 Cr (Weekly Nifty Strangle)"
echo "  ICICI Breeze: ₹1.2 Cr (LLM-validated Futures)"
echo "  Trendlyne:    Market data provider (configured)"
echo "  Total Capital: ₹7.2 Cr"
echo ""
echo "Next Steps:"
echo "  1. Activate virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Start the development server:"
echo "     python manage.py runserver"
echo ""
echo "  3. Access the application:"
echo "     - Main site:   http://localhost:8000/"
echo "     - Admin panel: http://localhost:8000/admin/"
echo ""
echo "  4. (Optional) Start background tasks:"
echo "     python manage.py process_tasks"
echo ""
echo "  5. (Optional) Start Celery worker:"
echo "     celery -A mcube_ai worker -l info"
echo ""
echo "============================================"
echo ""
