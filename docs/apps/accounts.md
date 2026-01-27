# Accounts App Documentation

**Location**: `apps/accounts/`

The accounts app manages broker account information, capital allocation, and margin calculations.

---

## What This App Does

1. **Account Storage** - Stores broker account details (Kotak, ICICI)
2. **Capital Tracking** - Tracks allocated and available capital
3. **Margin Management** - Implements the 50% margin rule
4. **Loss Limits** - Defines daily and weekly loss thresholds

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | BrokerAccount model |
| `admin.py` | Django admin interface |
| `services/margin_manager.py` | Margin calculation logic |
| `urls.py` | URL routing (currently empty) |
| `views.py` | Views (currently empty) |

---

## Key Model: BrokerAccount

The main model that represents a trading account.

```python
# Fields
broker = CharField()              # 'KOTAK' or 'ICICI'
account_number = CharField()      # Unique account ID
account_name = CharField()        # Display name
allocated_capital = DecimalField()  # Total capital (e.g., Rs 6 Cr)
is_active = BooleanField()        # Can we trade on this account?
is_paper_trading = BooleanField() # Is this a paper trading account?
max_daily_loss = DecimalField()   # Circuit breaker trigger (e.g., Rs 50,000)
max_weekly_loss = DecimalField()  # Circuit breaker trigger (e.g., Rs 150,000)
notes = TextField()               # Any notes
created_at = DateTimeField()      # When created
updated_at = DateTimeField()      # Last modified
```

### Key Methods

```python
from apps.accounts.models import BrokerAccount

account = BrokerAccount.objects.get(broker='KOTAK')

# Get available capital (total - deployed in positions)
available = account.get_available_capital()

# Get total P&L (realized + unrealized)
total_pnl = account.get_total_pnl()

# Get today's P&L only
today_pnl = account.get_todays_pnl()

# Deactivate account (used by circuit breakers)
account.deactivate(reason="Daily loss limit hit")
```

---

## Margin Manager Service

**Location**: `services/margin_manager.py`

This service implements the critical **50% margin rule**.

### Why 50% Rule?

When you open a position, you only use 50% of available margin. The other 50% is reserved for:
- **Averaging**: If position goes against you, you can add more
- **Adjustments**: Emergency hedging if needed
- **Margin Calls**: Buffer against margin requirements increasing

### Key Functions

```python
from apps.accounts.services.margin_manager import (
    calculate_usable_margin,
    check_margin_availability,
    calculate_position_size,
    get_margin_utilization,
    validate_margin_for_averaging,
)
```

#### calculate_usable_margin(account)

Calculates how much margin you can actually use.

```python
result = calculate_usable_margin(account)
# Returns:
# {
#     'total_capital': Decimal('6000000'),
#     'deployed_margin': Decimal('150000'),
#     'available_margin': Decimal('5850000'),
#     'usable_margin': Decimal('2925000'),  # 50% of available
#     'reserved_margin': Decimal('2925000'), # Reserved for averaging
# }
```

#### check_margin_availability(account, required_margin)

Checks if you have enough margin for a trade.

```python
is_available, message = check_margin_availability(account, 100000)
# Returns:
# (True, "Margin available: Rs 2,925,000")
# or
# (False, "Insufficient margin: need Rs 100,000, have Rs 50,000")
```

#### calculate_position_size(account, price, lot_size, margin_per_lot)

Calculates optimal position size based on available margin.

```python
result = calculate_position_size(account, 24000, 50, 80000)
# Returns:
# {
#     'max_lots': 36,
#     'max_quantity': 1800,
#     'total_margin_required': Decimal('2880000'),
#     'total_value': Decimal('4320000'),
#     'remaining_margin': Decimal('45000'),
# }
```

#### validate_margin_for_averaging(account, current_margin, attempt_number)

Validates if you can average down a position.

```python
is_valid, message, margin_amount = validate_margin_for_averaging(
    account,
    current_position_margin=100000,
    averaging_attempt=1
)
# First average: Use 20% of available balance
# Second average: Use 50% of available balance
# Returns:
# (True, "Can average with Rs 50,000", Decimal('50000'))
```

### Averaging Rules

| Attempt | Margin to Use |
|---------|--------------|
| 1st average | 20% of available |
| 2nd average | 50% of available |
| Maximum | 2 attempts |

---

## Admin Interface

Access at `/admin/accounts/` to manage:

- **Broker Accounts** - View and edit account details
  - See allocated capital
  - Toggle active/inactive
  - Set loss limits

### Admin Features

- **Filters**: By broker, active status, paper trading mode
- **Search**: By account name or number
- **Fieldsets**: Organized into Basic, Capital, Status, Notes sections

---

## How Accounts Are Used

### In Position Entry

```python
from apps.accounts.models import BrokerAccount
from apps.accounts.services.margin_manager import check_margin_availability

# Get account
account = BrokerAccount.objects.get(broker='KOTAK', is_active=True)

# Check if we can trade
if not account.is_active:
    return "Account is disabled"

# Check margin
margin_ok, msg = check_margin_availability(account, required_margin)
if not margin_ok:
    return msg

# Proceed with position entry...
```

### In Risk Checks

```python
# Check daily loss
today_pnl = account.get_todays_pnl()
if today_pnl < -account.max_daily_loss:
    account.deactivate("Daily loss limit breached")
```

### In Reports

```python
# Get account summary
for account in BrokerAccount.objects.filter(is_active=True):
    print(f"{account.account_name}:")
    print(f"  Capital: {account.allocated_capital}")
    print(f"  Available: {account.get_available_capital()}")
    print(f"  Today's P&L: {account.get_todays_pnl()}")
```

---

## Database Schema

```
Table: broker_accounts
├── id (BigAutoField, primary key)
├── broker (CharField, choices: KOTAK/ICICI)
├── account_number (CharField, unique)
├── account_name (CharField)
├── allocated_capital (DecimalField)
├── is_active (BooleanField)
├── is_paper_trading (BooleanField)
├── max_daily_loss (DecimalField)
├── max_weekly_loss (DecimalField)
├── notes (TextField)
├── created_at (DateTimeField)
└── updated_at (DateTimeField)
```

---

## How to Study This App

1. **Read `models.py`** - Understand the BrokerAccount model
2. **Study `margin_manager.py`** - Learn the 50% rule implementation
3. **Check `admin.py`** - See how accounts are managed
4. **Search codebase** for `BrokerAccount` usage - See how other apps use it

---

## Common Tasks for Developers

### Add a New Broker

1. Add choice to `BROKER_CHOICES` in `models.py`
2. Create account via admin
3. Add broker integration in `apps/brokers/`

### Change Margin Rules

1. Edit `margin_manager.py`
2. Update `calculate_usable_margin()` function
3. Document the new rule

### Add Account Metrics

1. Add method to `BrokerAccount` model
2. Use `apps.positions.models.Position` for calculations
3. Add to admin display if needed

---

## Dependencies

**Imports from**:
- `apps.core.models` (TimeStampedModel base class)
- `apps.core.constants` (broker choices)

**Imported by**:
- `apps.positions` (position belongs to account)
- `apps.risk` (risk limits tied to account)
- `apps.trading` (execution uses account)
- `apps.strategies` (strategy entry checks account)
- `apps.alerts` (alerts mention account)

---

## Key Business Rules

1. **50% Margin Rule** - Never use more than 50% of available margin
2. **One Position Per Account** - Only one active position at a time
3. **Loss Limits** - Daily and weekly loss limits trigger circuit breakers
4. **Active Status** - Only active accounts can trade

---

*For questions, check the code comments or ask the team.*
