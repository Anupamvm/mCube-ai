# Positions App Documentation

**Location**: `apps/positions/`

The positions app manages the complete lifecycle of trading positions - from entry to monitoring to exit.

---

## What This App Does

1. **Position Tracking** - Stores all active and closed positions
2. **P&L Calculation** - Calculates realized and unrealized profit/loss
3. **Exit Management** - Handles stop-loss, target, and EOD exits
4. **Averaging** - Manages position averaging (adding to losing positions)
5. **Delta Monitoring** - Tracks option Greeks for strangle positions
6. **S/R Exit Engine** - Structural stop-loss and target management with multi-timeframe analysis
7. **Position Monitor Dashboard** - Anti-spam single-message Telegram dashboard per trading day
8. **Hold Flag Management** - Smart re-alert logic when user holds an exit suggestion

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | Position and MonitorLog models |
| `admin.py` | Django admin interface |
| `tasks.py` | Celery tasks for monitoring |
| `services/position_manager.py` | Position lifecycle management |
| `services/exit_manager.py` | Exit condition checking |
| `services/averaging_manager.py` | Position averaging logic |
| `services/delta_monitor.py` | Option delta monitoring |
| `services/pnl_updater.py` | P&L calculations |
| `services/position_sync.py` | Sync with broker data |
| `services/monitor_dashboard.py` | Anti-spam dashboard (one Telegram message per day, edited) |
| `services/sr_exit_engine.py` | S/R exit engine — `apply_sl_and_target()` public API |
| `services/sr_exit_engine_utils.py` | Pure Python utilities for SR calculations |
| `services/sr_mtf_enricher.py` | Multi-timeframe S/R enrichment (4 timeframes) |
| `services/sr_level_strength.py` | Level strength annotator + confidence scorer (0-100) |
| `services/order_block_detector.py` | Order block (base candle zone) detection |
| `services/oi_wall_enricher.py` | OI wall enrichment (gamma walls, OI delta, strike pinning) |
| `services/sr_strategy_adapter.py` | Strategy-specific S/R adapters (Futures, Strangle, BIC) |
| `services/sr_risk_interface.py` | Adaptive SL placer, structural pressure monitor, partial close advisor |

---

## Key Model: Position

```python
# Core Fields
account = ForeignKey(BrokerAccount)     # Which account
strategy_type = CharField()              # STRANGLE or FUTURES
instrument = CharField()                 # NIFTY, RELIANCE, etc.
direction = CharField()                  # LONG, SHORT, or NEUTRAL
quantity = IntegerField()                # Number of shares/contracts
lot_size = IntegerField()                # Lot size (e.g., 50 for NIFTY)

# Pricing
entry_price = DecimalField()             # Price at entry
current_price = DecimalField()           # Latest price
stop_loss = DecimalField()               # SL price (nullable)
target = DecimalField()                  # Target price (nullable)

# Strangle-Specific Fields
call_strike = DecimalField()             # Call option strike
put_strike = DecimalField()              # Put option strike
call_premium = DecimalField()            # Premium received for call
put_premium = DecimalField()             # Premium received for put
premium_collected = DecimalField()       # Total premium collected
current_delta = DecimalField()           # Net delta of position

# Status & Timing
status = CharField()                     # ACTIVE or CLOSED
entry_time = DateTimeField()             # When position was opened
exit_time = DateTimeField()              # When position was closed
expiry_date = DateField()                # Contract expiry

# P&L Tracking
realized_pnl = DecimalField()            # P&L from closed portion
unrealized_pnl = DecimalField()          # P&L on open portion
margin_used = DecimalField()             # Margin deployed

# Averaging
averaging_count = IntegerField()         # How many times averaged
original_entry_price = DecimalField()    # Price before any averaging

# S/R Tracking (March 2026)
sr_tracking = JSONField()           # SR cache, MTF cache, OB cache, OI wall cache, volatility event flag
```

### Key Methods

```python
from apps.positions.models import Position

# Check if account has active position (ONE POSITION RULE)
has_position = Position.has_active_position(account)

# Get active position
position = Position.get_active_position(account)

# Update current price and recalculate P&L
position.update_current_price(new_price)

# Calculate P&L
pnl = position.calculate_unrealized_pnl()

# Check if stop-loss hit
if position.is_stop_loss_hit():
    position.close_position(exit_price, "Stop-loss triggered")

# Check if target hit
if position.is_target_hit():
    position.close_position(exit_price, "Target achieved")
```

---

## The ONE POSITION RULE

**This is the most critical rule in the system.**

Before ANY position entry, you MUST check:

```python
if Position.has_active_position(account):
    return "Cannot open - active position exists"
```

This is enforced in:
- `services/position_manager.py` - `morning_check()` function
- `services/position_manager.py` - `create_position()` function

---

## Position Lifecycle

```
1. Morning Check
   ├── Active position exists? → MONITOR ONLY mode
   └── No active position? → EVALUATE ENTRY mode

2. Position Entry (if allowed)
   └── create_position() → New ACTIVE position

3. Monitoring (Every 10-30 seconds)
   ├── update_position_pnl() → Refresh current price
   ├── check_exit_conditions() → Check SL/Target
   └── monitor_delta() → Check option deltas (strangle only)

4. Exit Triggered
   ├── STOP_LOSS hit → Immediate exit
   ├── TARGET hit → Immediate exit
   ├── EOD (3:15 PM) → Exit if profit >= 50%
   └── EXPIRY day → Mandatory exit

5. Position Closed
   └── Status = CLOSED, realized_pnl calculated
```

---

## Services

### Position Manager (`services/position_manager.py`)

Main service for position lifecycle.

```python
from apps.positions.services.position_manager import (
    morning_check,
    create_position,
    update_position_price,
    close_position,
    average_position,
    get_position_summary,
)
```

#### morning_check(account)

Called at market open. Determines what mode we're in.

```python
result = morning_check(account)
# Returns:
# {
#     'action': 'MONITOR_ONLY' or 'EVALUATE_ENTRY',
#     'reason': 'Active position exists' or 'No active position',
#     'position': Position or None
# }
```

#### create_position(account, strategy_type, instrument, direction, ...)

Creates a new position (enforces ONE POSITION RULE).

```python
success, position, message = create_position(
    account=account,
    strategy_type='STRANGLE',
    instrument='NIFTY',
    direction='NEUTRAL',
    quantity=50,
    lot_size=50,
    entry_price=100,  # Premium
    call_strike=24500,
    put_strike=24000,
    expiry_date=date(2025, 1, 30),
    margin_used=80000,
)
```

#### close_position(position, exit_price, exit_reason)

Closes a position and calculates realized P&L.

```python
success, message = close_position(
    position=position,
    exit_price=150,
    exit_reason="Stop-loss triggered"
)
```

### Exit Manager (`services/exit_manager.py`)

Handles all exit condition checking.

```python
from apps.positions.services.exit_manager import (
    check_exit_conditions,
    should_exit_position,
)
```

#### check_exit_conditions(position)

Checks all exit scenarios with priority:

```python
result = check_exit_conditions(position)
# Returns:
# {
#     'should_exit': True/False,
#     'exit_reason': 'Stop-loss hit',
#     'exit_price': Decimal('150'),
#     'priority': 1  # 1=highest
# }
```

**Exit Priority Order**:
1. Stop-Loss Hit → IMMEDIATE EXIT
2. Target Hit → IMMEDIATE EXIT
3. EOD Exit (3:15 PM) → Only if profit >= 50%
4. Expiry Day → MANDATORY EXIT by 3:20 PM

### S/R Exit Engine (`services/sr_exit_engine.py`)

Structural stop-loss and target management.

```python
from apps.positions.services.sr_exit_engine import apply_sl_and_target

result = apply_sl_and_target(position, dashboard, now=None)
# Returns:
# {
#     'sl_triggered': bool,
#     'sl_reason': 'STRUCTURAL_SL' or similar,
#     'structural_pressure': {
#         'should_warn': bool,
#         'reason': str,
#         'level': float,
#         'score': int (0-100),
#     } or None,
#     'updated_sl': price,
#     'updated_target': price,
# }
```

**3-Stage Warning System**:
1. **NEAR_SL** — Within 1% of stop-loss (once per day per position)
2. **STRUCTURAL_PRESSURE** — Condition A met, Condition B pending (5 min lead time)
3. **TRIGGER** — Both conditions met → exit fired

**Score-Gated Trigger Rules** (LevelConfidenceScorer 0-100):
- ≥76 (institutional): Condition A alone triggers
- 56-75 (strong): A or B + 15-min confirmation
- <56 (moderate): Both A+B required
- Strict mode (expiry day before 14:00 IST): Always requires both A+B

### Averaging Manager (`services/averaging_manager.py`)

Handles position averaging (futures only).

```python
from apps.positions.services.averaging_manager import (
    should_average_position,
    execute_averaging,
)
```

#### should_average_position(position, current_price)

Checks if averaging should trigger.

```python
result = should_average_position(position, current_price=100)
# Returns:
# {
#     'should_average': True/False,
#     'reason': 'Loss >= 1%, averaging recommended',
#     'loss_percent': 2.5,
#     'averaging_attempt': 1  # Current attempt (max 3)
# }
```

**Averaging Triggers**:
- Position is ACTIVE
- Position is down >= 1% from entry
- Averaging attempts < 3
- Sufficient margin available

#### execute_averaging(position, current_price)

Executes the averaging.

```python
success, message, details = execute_averaging(position, 100)
# Details include:
# - new_average_price (weighted average)
# - new_quantity (doubled)
# - new_stop_loss (tightened to 0.5% from new average)
```

### Delta Monitor (`services/delta_monitor.py`)

Monitors option Greeks for strangle positions.

```python
from apps.positions.services.delta_monitor import (
    calculate_strangle_delta,
    monitor_delta,
)
```

#### monitor_delta(position, threshold=300)

Checks if net delta exceeds threshold.

```python
result = monitor_delta(position, delta_threshold=300)
# Returns:
# {
#     'net_delta': 350,
#     'exceeded': True,
#     'recommendation': 'Consider adjusting position',
#     'suggested_action': 'Sell additional calls to reduce delta'
# }
```

**Delta Threshold**: |net_delta| > 300 triggers an alert.

---

## P&L Calculations

### For LONG Position
```
P&L = (current_price - entry_price) × quantity × lot_size
```

### For SHORT Position
```
P&L = (entry_price - current_price) × quantity × lot_size
```

### For NEUTRAL (Strangle)
```
P&L = premium_collected - current_exit_cost
```

---

## Celery Tasks

| Task | Frequency | Purpose |
|------|-----------|---------|
| `monitor_and_manage_positions` | Every 1 min (9 AM-3:59 PM) | Full monitoring cycle: P&L, SR engine, dashboard, exit checks |

---

## MonitorLog Model

Audit trail for all monitoring events.

```python
# Fields
position = ForeignKey(Position)
check_type = CharField()         # PNL_UPDATE, EXIT_SUGGESTION, STRUCTURAL_PRESSURE, AUTO_EXIT, NEAR_SL
result = CharField()             # OK, SUGGESTION_SENT, HELD_BY_USER, DUPLICATE_SKIPPED, EXECUTING
message = TextField()            # Description with IST timestamp
price_at_check = DecimalField()  # Price at time of check
pnl_at_check = DecimalField()    # P&L at time of check
action_taken = CharField()       # SUGGESTION_SENT, HELD_BY_USER, DUPLICATE_SKIPPED, AUTO_EXIT
```

---

## PositionMonitorDashboard

Anti-spam dashboard — one Telegram message per trading day, edited in place.

```python
# Fields
trading_date = DateField()          # One per trading day
message_id = IntegerField()         # Telegram message ID (for editing)
snapshots = JSONField()             # Last 3 snapshots [{price, pnl, pnl_pct, time}]
sr_tracking = JSONField()           # SR cache, gap flag, near_sl_warned, volatility_event_flag
last_snapshot = DateTimeField()     # Last update timestamp
```

---

## How to Study This App

1. **Start with `models.py`** - Understand Position fields
2. **Read `position_manager.py`** - Learn the ONE POSITION RULE
3. **Study `exit_manager.py`** - Understand exit priority
4. **Check `averaging_manager.py`** - Learn averaging logic
5. **Review `tasks.py`** - See automated monitoring

---

## Common Tasks for Developers

### Add a New Exit Condition

1. Add check in `exit_manager.py` - `check_exit_conditions()`
2. Give it appropriate priority
3. Test thoroughly - exits are critical

### Modify Averaging Logic

1. Edit `averaging_manager.py`
2. Update `should_average_position()` rules
3. Update margin calculations

### Add New Position Type

1. Add strategy_type choice in `models.py`
2. Update P&L calculation in `calculate_unrealized_pnl()`
3. Add specific fields if needed

---

## Key Business Rules

1. **ONE POSITION PER ACCOUNT** - Checked before any entry
2. **Exit Priority** - SL > Target > EOD > Expiry
3. **Averaging Limit** - Maximum 2 averaging attempts
4. **Delta Threshold** - Alert at |delta| > 300
5. **50% Profit Rule** - EOD exit only if profit >= 50%
6. **Hold Flag** - User can hold exit suggestion; re-alert only on reason change, >1% price move, or market close
7. **Dashboard Anti-Spam** - One Telegram message per day, edited in place with last 3 snapshots

---

*For questions, check the code comments or ask the team.*
