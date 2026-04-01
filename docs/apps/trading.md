# Trading App Documentation

**Location**: `apps/trading/`

The trading app provides the user interface and workflow for trade suggestions, approvals, and execution.

---

## What This App Does

1. **Trade Suggestions** - Stores algorithm-generated trade ideas
2. **Approval Workflow** - Manual or auto-approval of trades
3. **Execution Control** - Manages order placement with progress tracking
4. **Position Sizing** - Calculates optimal position sizes
5. **Trading UI** - Web interface for manual trading
6. **Trade Confirmation Service** - Telegram confirmation flow for futures, options, and exit actions

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | TradeSuggestion, AutoTradeConfig, TradeSuggestionLog, OrderExecutionControl, PositionSize, TakenTrade |
| `tasks.py` | check_confirmation_timeouts (every 1 min during market hours) |
| `views.py` | Web views (legacy, 3065 lines) |
| `api_views.py` | API endpoints (legacy, 136KB) |
| `views/` | Refactored view modules |
| `api/` | Refactored API modules |
| `services/` | Business logic |
| `futures_analyzer.py` | 9-step futures analysis (126KB) |
| `services/trade_confirmation.py` | Telegram confirmation flow (futures selection, options, exit) |
| `urls.py` | URL routing |

---

## Key Models

### TradeSuggestion

Stores algorithm-generated trade ideas with complete reasoning.

```python
# Core Fields
user = ForeignKey(User)
source = CharField()                # 'auto' or 'manual'
strategy = CharField()              # 'kotak_strangle', 'kotak_broken_iron_condor', 'icici_futures'
suggestion_type = CharField()       # OPTIONS or FUTURES
instrument = CharField()            # NIFTY, RELIANCE, etc.
direction = CharField()             # LONG, SHORT, NEUTRAL
status = CharField()                # SUGGESTED, PENDING_CONFIRMATION, TAKEN, REJECTED, etc.

# Market Data at Suggestion
spot_price = DecimalField()
vix = DecimalField()
expiry_date = DateField()
days_to_expiry = IntegerField()

# Strike Details (Options)
call_strike = DecimalField()
put_strike = DecimalField()
call_premium = DecimalField()
put_premium = DecimalField()
total_premium = DecimalField()

# Position Sizing
recommended_lots = IntegerField()
margin_required = DecimalField()
margin_available = DecimalField()

# Risk Metrics
max_profit = DecimalField()
max_loss = DecimalField()
risk_reward_ratio = DecimalField()

# Algorithm Reasoning
algorithm_reasoning = JSONField()   # Complete analysis details
position_details = JSONField()      # Recommended parameters

# Tracking
is_auto_trade = BooleanField()      # Auto-approved?
executed_position = OneToOneField(Position)  # Linked position

# Telegram Confirmation Flow Fields
telegram_message_id = CharField()        # Telegram message ID for confirmation
user_modified_lots = IntegerField()      # User-modified lot count (if different)
confirmation_requested_at = DateTimeField()  # When confirmation was sent
confirmation_timeout_minutes = IntegerField()  # Timeout period (default 5)
revalidation_sent = BooleanField()       # One revalidation per suggestion
escalated = BooleanField()               # Escalation alert sent

# Computed Properties (from position_details/algorithm_reasoning JSON)
composite_score                          # 0-100 composite score (property)
regime                                   # Market regime at time of suggestion (property)
```

### Status Flow

```
SUGGESTED → PENDING_CONFIRMATION → TAKEN → ACTIVE → CLOSED → SUCCESSFUL/LOSS/BREAKEVEN
         ↘ REJECTED                  ↗
         ↘ EXPIRED
         ↘ CANCELLED
```

### AutoTradeConfig

Configuration for auto-trading per strategy.

```python
# Fields
user = ForeignKey(User)
strategy = CharField()              # Strategy type
is_enabled = BooleanField()         # Auto-trade enabled?
auto_approve_threshold = IntegerField()  # Min confidence/score
max_daily_positions = IntegerField()
max_daily_loss = DecimalField()
require_human_on_weekend = BooleanField()
require_human_on_high_vix = BooleanField()
vix_threshold = DecimalField()      # High VIX threshold
```

### OrderExecutionControl

Controls ongoing batch order execution.

```python
# Fields
suggestion = OneToOneField(TradeSuggestion)
is_cancelled = BooleanField()       # Stop execution?
cancel_reason = TextField()
batches_completed = IntegerField()
total_batches = IntegerField()
last_heartbeat = DateTimeField()    # Execution alive check
```

### TradeSuggestionLog

Audit trail for all trade suggestion activities.

```python
# Fields
suggestion = ForeignKey(TradeSuggestion)
action = CharField()                # CREATED, APPROVED, AUTO_APPROVED, REJECTED, EXECUTED, EXPIRED, CANCELLED
user = ForeignKey(User, nullable)
notes = TextField()
created_at = DateTimeField()
```

### TakenTrade

Dedicated model for user-accepted trades with full lifecycle tracking. Links suggestions to actual positions.

```python
# Core References
user = ForeignKey(User)
suggestion = OneToOneField(TradeSuggestion, nullable)
position = OneToOneField(Position, nullable)
account = ForeignKey(BrokerAccount)

# Trade Details
strategy = CharField()              # kotak_strangle, kotak_broken_iron_condor, icici_futures
trade_type = CharField()            # OPTIONS, FUTURES
instrument = CharField()
direction = CharField()             # LONG, SHORT, NEUTRAL

# Status: PENDING_EXECUTION → EXECUTED → ACTIVE → CLOSED | CANCELLED | FAILED
# Outcome: PROFIT | LOSS | BREAKEVEN | PENDING
status = CharField()
outcome = CharField()

# P&L: entry_price, exit_price, quantity, lot_size, realized_pnl, charges, net_pnl, return_on_margin
# Timestamps: taken_at, executed_at, closed_at

# Key methods: mark_executed(), mark_active(), mark_closed(), sync_from_position(), sync_suggestion_status()
```

---

## Workflow: Trade Suggestion to Execution

```
1. Algorithm generates analysis
   └── Strategy app evaluates market conditions

2. Create TradeSuggestion
   └── services/trade_suggestions.py:create_suggestion()

3. Auto-Approval Check
   ├── Check AutoTradeConfig for user/strategy
   ├── Compare confidence to threshold
   └── Auto-approve if criteria met

4. Manual Approval (if not auto)
   └── User approves via UI or Telegram

5. Execution
   ├── Create OrderExecutionControl
   ├── Place orders via broker
   ├── Track progress (batches)
   └── Create Position on success

6. Position Tracking
   └── Link TradeSuggestion to Position
```

---

## Services

### Trade Suggestions (`services/trade_suggestions.py`)

```python
from apps.trading.services.trade_suggestions import TradeSuggestionService

service = TradeSuggestionService()

# Create a suggestion
suggestion = service.create_suggestion(
    user=user,
    strategy='kotak_strangle',
    algorithm_result=result,
)

# Check if should auto-approve
if service.should_auto_approve(suggestion):
    service.auto_approve(suggestion)
```

### Trade Approval Handler (`services/trade_approval_handler.py`)

```python
from apps.trading.services.trade_approval_handler import TradeApprovalHandler

handler = TradeApprovalHandler()

# Approve a trade
success, position, message = handler.approve_trade(suggestion)

# Reject a trade
success, message = handler.reject_trade(suggestion, reason="High VIX")
```

### Position Sizing (`services/position_sizer.py`)

```python
from apps.trading.services.position_sizer import PositionSizer

sizer = PositionSizer(account)

# Calculate position size
result = sizer.calculate(
    symbol='RELIANCE',
    direction='LONG',
    entry_price=3100,
    stop_loss=3050,
)

# Result:
# {
#     'recommended_lots': 5,
#     'margin_required': 225000,
#     'max_loss': 50000,
#     'risk_reward': 2.5
# }
```

---

## API Endpoints

### Trade Suggestions

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/suggestions/` | GET | List all suggestions |
| `/api/suggestions/<id>/` | GET | Get suggestion details |
| `/api/suggestions/update/` | POST | Update suggestion status |

### Position Sizing

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/calculate-position/` | POST | Calculate position sizing |
| `/api/calculate-pnl/` | POST | Calculate P&L scenarios |

### Order Execution

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/place-futures-order/` | POST | Place futures order |
| `/api/create-execution-control/` | POST | Create execution control |
| `/api/cancel-execution/` | POST | Cancel ongoing execution |
| `/api/execution-progress/<id>/` | GET | Get execution progress |

### Positions

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/get-positions/` | GET | Get live positions |
| `/api/close-position/` | POST | Close a position |
| `/api/close-live-position/` | POST | Close via broker API |

---

## Futures Analyzer

**File**: `futures_analyzer.py` (126KB)

The 9-step analysis framework for futures trading.

```python
from apps.trading.futures_analyzer import analyze_futures

result = analyze_futures('RELIANCE', '2026-01-30')

# Returns comprehensive analysis:
# {
#     'step_1_price': {...},        # Real-time price
#     'step_2_basis': {...},        # Basis & cost of carry
#     'step_3_oi': {...},           # Open interest analysis
#     'step_4_dma': {...},          # Moving averages
#     'step_5_sector': {...},       # Sector strength
#     'step_6_volume': {...},       # Volume patterns
#     'step_7_technical': {...},    # RSI, MACD, etc.
#     'step_8_sr': {...},           # Support/resistance (CONSERVATIVE)
#     'step_9_verdict': {...},      # Final verdict
# }
```

### Step 8: Support/Resistance (Conservative Approach)

Step 8 uses the **Consolidated Conservative S/R Calculator** which combines:
- **Pivot Points** from historical price data
- **OI-Based S/R** from highest PUT/CALL open interest strikes

```python
# Step 8 internally calls:
from apps.strategies.services.consolidated_sr_calculator import get_conservative_sr

sr_data = get_conservative_sr(symbol, current_price)

# Conservative selection:
# - Support: Uses HIGHER value (closer to price) from all methods
# - Resistance: Uses LOWER value (closer to price) from all methods
```

This ensures tighter, safer trading ranges when making entry/exit decisions.

---

## Views Structure

### Refactored Views (`views/`)

| File | Purpose |
|------|---------|
| `suggestion_views.py` | Trade suggestion management |
| `algorithm_views.py` | Algorithm triggers (81KB) |
| `verification_views.py` | Trade verification (59KB) |
| `execution_views.py` | Order execution (46KB) |
| `session_views.py` | Broker session management |
| `template_views.py` | Page templates |

### Refactored API (`api/`)

| File | Purpose |
|------|---------|
| `position_sizing.py` | Position sizing endpoints |
| `order_views.py` | Order placement |
| `margin_views.py` | Margin data |
| `suggestion_views.py` | Suggestion management |
| `position_management_views.py` | Position operations (48KB) |
| `historical_data_views.py` | Historical data (30KB) |

---

## Web URLs

| URL | Purpose |
|-----|---------|
| `/trading/triggers/` | Manual trigger interface |
| `/trading/suggestions/` | List pending suggestions |
| `/trading/suggestion/<id>/` | Suggestion detail |
| `/trading/config/auto-trade/` | Auto-trade configuration |
| `/trading/history/` | Suggestion history |

---

## How Auto-Trade Works

1. **Configuration**: User sets up `AutoTradeConfig`:
   ```python
   config = AutoTradeConfig.objects.create(
       user=user,
       strategy='kotak_strangle',
       is_enabled=True,
       auto_approve_threshold=75,  # Min LLM confidence
       max_daily_positions=1,
       vix_threshold=18,
   )
   ```

2. **Suggestion Created**: Algorithm creates suggestion

3. **Auto-Check**:
   ```python
   if config.is_enabled:
       if suggestion.confidence >= config.auto_approve_threshold:
           if vix <= config.vix_threshold:
               if not is_weekend or not config.require_human_on_weekend:
                   auto_approve(suggestion)
   ```

4. **Execution**: Auto-approved trades execute immediately

---

## Execution Control

For large orders (batched execution):

```python
# Create control
control = OrderExecutionControl.objects.create(
    suggestion=suggestion,
    total_batches=9,
)

# During execution, check if cancelled
while batch_num <= control.total_batches:
    if not control.should_continue():
        break  # User cancelled

    execute_batch(batch_num)
    control.update_progress(batch_num)
    time.sleep(delay)

# Mark complete
control.mark_complete()
```

### Trade Confirmation Service (`services/trade_confirmation.py`)

Telegram-based confirmation for all trade actions.

```python
from apps.trading.services.trade_confirmation import TradeConfirmationService

service = TradeConfirmationService()

# Exit confirmation (manual mode)
service.request_exit_confirmation(position, reason, current_pnl)
# Sends rich message with P&L %, price context, [✅ Close Now] [⏸️ Hold] buttons

# Options confirmation
service.request_options_confirmation(suggestion, config)

# Futures confirmation (two-step)
service.request_futures_confirmation(suggestions, breeze)
# Step 1: Selection screen with top 3 candidates
# Step 2: Detail view with full analysis
```

**Confirmation Timeout Flow** (via `check_confirmation_timeouts` task, every 1 min, 9:15-15:30):
1. Find suggestions with `status='PENDING_CONFIRMATION'` and `revalidation_sent=False`
2. Check if `confirmation_requested_at + timeout_minutes` exceeded
3. Call `revalidate_after_timeout()` — market conditions may have changed
4. Set `revalidation_sent=True` (once per suggestion)
5. After 15 min (`_ESCALATION_MINUTES`): send CRITICAL_ERROR notification, set `escalated=True`

---

## How to Study This App

1. **Start with `models.py`** - Understand the data structures
2. **Read `services/trade_suggestions.py`** - Learn suggestion flow
3. **Study `services/trade_approval_handler.py`** - Approval logic
4. **Check `futures_analyzer.py`** - 9-step analysis
5. **Review `api/` modules** - See available endpoints

---

## Common Tasks for Developers

### Add New Suggestion Field

1. Add to `TradeSuggestion` model
2. Create migration
3. Update `trade_suggestions.py` to populate
4. Update API response if needed

### Add New API Endpoint

1. Add to appropriate file in `api/`
2. Add URL in `urls.py`
3. Document the endpoint

### Modify Approval Logic

1. Edit `trade_approval_handler.py`
2. Update `approve_trade()` or `should_auto_approve()`
3. Test thoroughly

---

## Key Business Rules

1. **ONE POSITION RULE** - Checked before execution
2. **Auto-Approval** - Based on confidence threshold
3. **VIX Check** - Can require human approval on high VIX
4. **Weekend Check** - Can require human approval on weekends
5. **Batch Execution** - Large orders split into batches

---

*For questions, check the code comments or ask the team.*
