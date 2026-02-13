# Algorithm Study Guide

This guide provides a deep dive into the three trading algorithms implemented in mCube. Study this after understanding the app-level documentation.

---

## Table of Contents

1. [Weekly Nifty Short Strangle](#1-weekly-nifty-short-strangle)
2. [Broken Iron Condor](#2-broken-iron-condor)
3. [LLM-Validated Futures](#3-llm-validated-futures)
4. [Common Concepts](#4-common-concepts)
5. [How to Study These Algorithms](#5-how-to-study-these-algorithms)

---

## 1. Weekly Nifty Short Strangle

**Location**: `apps/strategies/services/kotak_strangle.py`

### What is a Short Strangle?

A short strangle sells both a Call (CE) and a Put (PE) option at the same time:
- **Sell CE** at a strike ABOVE current price (expecting price won't go that high)
- **Sell PE** at a strike BELOW current price (expecting price won't go that low)

**Profit**: If NIFTY stays between the two strikes until expiry, both options expire worthless and you keep the premium.

**Risk**: If NIFTY moves sharply in either direction, losses can be unlimited.

### Algorithm Flow

```
Every Thursday (Weekly Expiry Day)
      |
      v
1. CHECK ENTRY CONDITIONS
   |-- Is market open? (9:15 AM - 3:30 PM)
   |-- Is it Thursday?
   |-- Is VIX in acceptable range? (12-25)
   |-- Any major events today? (RBI, Budget, etc.)
   |-- Account has no existing position?
   |
   v
2. CALCULATE STRIKE PRICES
   |
   |  Get current NIFTY spot price (e.g., 24,500)
   |
   |  Calculate VIX-adjusted distance:
   |    base_distance = 200 points
   |    vix_multiplier = current_vix / 15  (normalize to VIX 15)
   |    adjusted_distance = base_distance * vix_multiplier
   |
   |  Example with VIX = 18:
   |    vix_multiplier = 18/15 = 1.2
   |    adjusted_distance = 200 * 1.2 = 240 points
   |
   |  CE Strike = 24,500 + 240 = 24,750 (round to nearest 50)
   |  PE Strike = 24,500 - 240 = 24,250 (round to nearest 50)
   |
   v
3. VALIDATE WITH PREMIUM CHECK
   |
   |  Get premium for both options
   |  Minimum premium required: Rs 50 per lot
   |
   |  If premium < 50:
   |    Move strike closer by 50 points
   |    Re-check premium
   |
   v
4. CALCULATE POSITION SIZE
   |
   |  available_margin = account.get_available_margin()
   |  margin_per_lot = get_margin_requirement('NIFTY', CE_strike, PE_strike)
   |
   |  max_lots = available_margin / margin_per_lot
   |  lots_to_trade = min(max_lots, configured_max_lots)
   |
   |  Apply 50% rule: use only 50% of available margin
   |
   v
5. PLACE ORDERS
   |
   |  Create Position record (status: PENDING)
   |
   |  Place CE sell order
   |  Place PE sell order
   |
   |  Wait for execution
   |
   |  Update Position (status: ACTIVE)
   |
   v
6. MONITOR POSITION (Every 30 seconds)
   |
   |  Calculate current delta:
   |    total_delta = CE_delta + PE_delta
   |
   |  If |total_delta| > 300:
   |    TRIGGER ADJUSTMENT (see Delta Management)
   |
   |  Calculate current P&L:
   |    entry_premium = CE_entry + PE_entry
   |    current_premium = CE_current + PE_current
   |    pnl = (entry_premium - current_premium) * lot_size * lots
   |
   |  Check stop-loss:
   |    If pnl < -max_loss: EXIT ALL
   |
   |  Check target:
   |    If pnl > target_profit: EXIT ALL
   |
   v
7. EXIT POSITION
   |
   |  Priority order:
   |    1. Stop-loss hit
   |    2. Target achieved
   |    3. End of day (3:15 PM)
   |    4. Expiry (Thursday 3:25 PM)
   |
   |  Place buy orders for both legs
   |  Update Position (status: CLOSED)
   |  Record final P&L
```

### Delta Management

Delta measures how much option price changes when underlying moves by 1 point.

```
Delta Monitoring Algorithm:

1. Every 30 seconds:
   combined_delta = abs(CE_delta) + abs(PE_delta)

   Note: CE delta is negative (we sold), PE delta is positive (we sold)

2. If combined_delta > 300 (threshold):

   Determine which side is "heavy":
   If CE losing more: market moved UP
   If PE losing more: market moved DOWN

3. ADJUSTMENT OPTIONS:

   Option A: Roll the losing leg
   - Close the losing leg
   - Open new leg further from current price

   Option B: Add hedge
   - Buy protective option on losing side

   Option C: Exit entire position
   - If adjustment would exceed margin
   - If market too volatile

4. Log adjustment action
   Send Telegram alert
```

### Key Configuration

```python
# In strategy config or SystemSettings
STRANGLE_CONFIG = {
    'base_strike_distance': 200,    # Base points from spot
    'vix_normalization': 15,        # VIX baseline
    'min_premium': 50,              # Minimum premium per option
    'delta_threshold': 300,         # Delta adjustment trigger
    'max_loss_pct': 50,             # Stop-loss at 50% of premium
    'target_pct': 80,               # Target at 80% of premium
    'entry_window_start': '09:30',  # Entry after 9:30 AM
    'entry_window_end': '14:00',    # No new entry after 2 PM
    'exit_time': '15:15',           # Exit by 3:15 PM
}
```

### Files to Study

1. `apps/strategies/services/kotak_strangle.py` - Main algorithm
2. `apps/positions/services/delta_monitor.py` - Delta management
3. `apps/positions/services/exit_manager.py` - Exit logic
4. `apps/brokers/services/kotak_neo.py` - Order placement

---

## 2. Broken Iron Condor

**Location**: `apps/strategies/services/kotak_strangle.py` (same file, different mode)

### What is a Broken Iron Condor?

A regular Iron Condor has 4 legs (2 CE, 2 PE). Our "Broken" Iron Condor has 3 legs:
- **Sell CE** (same as strangle)
- **Sell PE** (same as strangle)
- **Buy PE** further OTM (protection against big fall)

This is "broken" because we only hedge one side (puts), leaving calls unhedged.

### Why Use This?

- **Limited downside risk**: If market crashes, the long PE protects us
- **Higher cost**: We pay for the protective PE
- **Asymmetric view**: Protects against sudden falls (more common than sudden rises)

### Algorithm Flow

```
Same as Short Strangle, with these modifications:

STEP 2: CALCULATE STRIKES (Modified)
   |
   |  CE Strike = spot + adjusted_distance
   |  PE Strike = spot - adjusted_distance
   |  PE_HEDGE Strike = PE Strike - 200  (further OTM)
   |
   |  Example:
   |    Spot: 24,500
   |    CE Strike: 24,750 (SELL)
   |    PE Strike: 24,250 (SELL)
   |    PE Hedge: 24,050 (BUY)
   |
   v
STEP 5: PLACE ORDERS (Modified)
   |
   |  Place 3 orders:
   |    1. SELL CE at 24,750
   |    2. SELL PE at 24,250
   |    3. BUY PE at 24,050 (hedge)
   |
   v
STEP 7: EXIT (Modified)
   |
   |  Exit all 3 legs together
   |  Calculate net P&L including hedge cost
```

### P&L Calculation

```
Entry:
  Received: CE premium + PE premium
  Paid: PE hedge premium
  Net Credit = (CE + PE) - PE_hedge

At Exit:
  Pay: CE current + PE current
  Receive: PE hedge current
  Net Debit = (CE + PE) - PE_hedge

P&L = Net Credit - Net Debit
```

### Configuration

```python
BROKEN_IC_CONFIG = {
    'hedge_distance': 200,          # PE hedge 200 points below short PE
    'hedge_ratio': 1.0,             # Same lots for hedge
    # Other configs same as strangle
}
```

---

## 3. LLM-Validated Futures

**Location**: `apps/strategies/services/icici_futures.py`

### What is This Strategy?

This strategy trades stock futures (not options) with AI validation:
1. **Pre-market scan** (8:30 AM) — screen stocks using 12 technical/fundamental factors
2. **Active execution** (9:40 AM) — re-validate with live prices, send TOP 3 to Telegram
3. **Validate with LLM** before taking the trade
4. **Average down** if position goes against us (controlled risk)

### The 12-Factor Composite Score (300 points scaled to 100)

```
Factor Analysis Algorithm:

For each F&O stock, calculate:

1. TRENDLYNE DURABILITY SCORE (Weight: 15%)
   |-- Measures: Financial health, debt levels, profitability
   |-- Source: TLStockData.trendlyne_durability_score
   |-- Score: 0-100
   |-- Bullish if: > 60

2. TRENDLYNE MOMENTUM SCORE (Weight: 15%)
   |-- Measures: Price momentum, relative strength
   |-- Source: TLStockData.trendlyne_momentum_score
   |-- Score: 0-100
   |-- Bullish if: > 60

3. OI BUILDUP ANALYSIS (Weight: 20%)
   |-- Measures: Open Interest + Price movement
   |-- Source: ContractData (futures)
   |
   |-- Logic:
   |      Price UP + OI UP = LONG_BUILDUP (Bullish) = 100
   |      Price DOWN + OI UP = SHORT_BUILDUP (Bearish) = 0
   |      Price UP + OI DOWN = SHORT_COVERING (Neutral) = 50
   |      Price DOWN + OI DOWN = LONG_UNWINDING (Neutral) = 50

4. PUT-CALL RATIO (Weight: 10%)
   |-- Measures: Market sentiment via options
   |-- Source: ContractData (options)
   |
   |-- Logic:
   |      PCR > 1.2 = Very Bullish = 100
   |      PCR 1.0-1.2 = Bullish = 75
   |      PCR 0.8-1.0 = Neutral = 50
   |      PCR < 0.8 = Bearish = 25

5. DMA POSITION (Weight: 10%)
   |-- Measures: Price vs Moving Averages
   |-- Source: TLStockData (sma_20, sma_50, sma_200)
   |
   |-- Logic:
   |      Above all 3 DMAs = 100
   |      Above 2 DMAs = 75
   |      Above 1 DMA = 50
   |      Below all = 25

6. RSI ANALYSIS (Weight: 10%)
   |-- Measures: Relative Strength Index
   |-- Source: TLStockData.rsi
   |
   |-- Logic:
   |      RSI 50-70 = Bullish momentum = 100
   |      RSI 30-50 = Neutral = 50
   |      RSI < 30 = Oversold (potential reversal) = 75
   |      RSI > 70 = Overbought (avoid) = 25

7. VOLUME ANALYSIS (Weight: 5%)
   |-- Measures: Volume vs average
   |-- Source: TLStockData (avg_day_volume, current_volume)
   |
   |-- Logic:
   |      Volume > 1.5x average = Confirmation = 100
   |      Volume 1.0-1.5x = Normal = 75
   |      Volume < 1.0x = Weak = 50

8. DELIVERY PERCENTAGE (Weight: 5%)
   |-- Measures: Cash market conviction
   |-- Source: TLStockData.delivery_pct
   |
   |-- Logic:
   |      Delivery > 50% = Strong conviction = 100
   |      Delivery 30-50% = Normal = 75
   |      Delivery < 30% = Speculative = 50

9. SECTOR ANALYSIS (Weight: 10%)
   |-- Measures: Sector momentum
   |-- Source: TLStockData (sector peers)
   |
   |-- Logic:
   |      > 70% sector stocks bullish = 100
   |      50-70% bullish = 75
   |      30-50% bullish = 50
   |      < 30% bullish = 25

COMPOSITE SCORE = Sum(factor_score * weight)
Range: 0-100
```

### Algorithm Flow

```
Every Market Day — Two-Phase Process
      |
      v
--- PHASE 1: PRE-MARKET SCAN (8:30 AM) ---
   |
   |  screen-futures-opportunities task runs
   |  Scans top 50 F&O stocks by volume
   |  Runs 12-factor scoring model (300 points scaled to 100)
   |  Results cached for Phase 2
   |
--- PHASE 2: EXECUTION (9:40 AM) ---
   |
   |  execute-futures-algorithm task runs
   |  Re-validates with live prices
   |
1. SCREEN ALL F&O STOCKS
   |
   |  For each stock in F&O list (~180 stocks):
   |    Calculate 12-factor composite score
   |
   |  Filter: composite_score >= 65
   |
   |  Result: List of potential candidates
   |
   v
2. RANK CANDIDATES
   |
   |  Sort by composite_score (descending)
   |  Take top 3 candidates (configurable)
   |
   v
3. CHECK ACCOUNT CONSTRAINTS
   |
   |  For each candidate:
   |    Does account already have a position? (ONE POSITION RULE)
   |    Is there enough margin?
   |    Is the stock not in exclusion list?
   |
   v
4. LLM VALIDATION (Critical Step)
   |
   |  For top candidate:
   |
   |  4a. Gather Context (RAG System)
   |      |-- Recent news about the stock
   |      |-- Sector news
   |      |-- Investor call insights
   |      |-- Market sentiment
   |
   |  4b. Build Validation Prompt
   |      """
   |      You are an expert stock analyst. Evaluate this trade:
   |
   |      Symbol: RELIANCE
   |      Direction: LONG
   |      Composite Score: 78
   |
   |      TECHNICAL CONTEXT:
   |      - OI Buildup: LONG_BUILDUP
   |      - PCR: 1.15 (Bullish)
   |      - RSI: 62
   |      - Above 20/50/200 DMA
   |
   |      NEWS CONTEXT:
   |      [Recent news summaries from RAG]
   |
   |      Respond with:
   |      DECISION: APPROVED/REJECTED
   |      CONFIDENCE: 0-100
   |      REASONING: ...
   |      RISKS: ...
   |      """
   |
   |  4c. Get LLM Response
   |      If confidence >= 70%: PROCEED
   |      If confidence < 70%: SKIP, try next candidate
   |
   v
5. CALCULATE POSITION SIZE
   |
   |  available_margin = account.get_available_margin()
   |  margin_per_lot = get_futures_margin(symbol)
   |
   |  Apply 50% rule:
   |    usable_margin = available_margin * 0.5
   |
   |  lots = usable_margin / margin_per_lot
   |  lots = min(lots, max_lots_config)
   |
   v
6. CREATE TRADE SUGGESTION
   |
   |  TradeSuggestion.objects.create(
   |      symbol=symbol,
   |      direction='LONG',
   |      composite_score=score,
   |      llm_validation=validation_result,
   |      status='PENDING_APPROVAL'
   |  )
   |
   |  Send Telegram notification with APPROVE/REJECT buttons
   |
   v
7. WAIT FOR APPROVAL (Optional based on config)
   |
   |  If auto_trade_enabled:
   |      Auto-approve if confidence > 80%
   |  Else:
   |      Wait for human approval via Telegram
   |
   v
8. EXECUTE TRADE
   |
   |  Place market order for futures
   |  Create Position record
   |  Set stop-loss and target
   |
   v
9. MONITOR POSITION
   |
   |  Every 5 minutes:
   |    Update current price
   |    Calculate unrealized P&L
   |    Check stop-loss / target
   |
   |  If price moves against us:
   |    Consider AVERAGING (see below)
   |
   v
10. EXIT POSITION
    |
    |  Reasons:
    |    - Stop-loss hit (configured %)
    |    - Target achieved (configured %)
    |    - End of day (optional)
    |    - Manual exit via Telegram
    |    - Expiry approaching (3 days before)
```

### Averaging Protocol

```
Averaging Algorithm:

When position is in loss (checked every 10 minutes, 9:30 AM - 3:00 PM):

1. CHECK AVERAGING CONDITIONS
   |
   |  loss_pct = (current_price - avg_price) / avg_price * 100
   |
   |  Trigger: loss_pct >= 1% from current average price
   |  Max 2 additional entries (3 total)
   |
   |  First Average:
   |    Additional: 20% of remaining balance
   |
   |  Second Average:
   |    Additional: 50% of remaining balance
   |    Final attempt
   |
   v
2. VALIDATE AVERAGING
   |
   |  Re-run LLM validation with:
   |    - Current market conditions
   |    - Why price moved against us
   |    - News that may have affected
   |
   |  If LLM says AVOID: Don't average
   |
   v
3. CALCULATE NEW AVERAGE
   |
   |  new_avg_price = (old_qty * old_price + new_qty * new_price)
   |                  / (old_qty + new_qty)
   |
   |  Update Position with new average
   |
   v
4. UPDATE TARGETS
   |
   |  Recalculate stop-loss from new average
   |  Recalculate target from new average
```

### Key Configuration

```python
FUTURES_CONFIG = {
    'min_composite_score': 65,      # Minimum score to qualify (configurable via UI)
    'top_contracts': 50,            # Number of top-volume contracts to scan
    'batch_size': 3,                # Contracts per parallel analysis batch
    'this_month_volume': 1000,      # Min volume for current month contracts
    'next_month_volume': 800,       # Min volume for next month contracts
    'llm_confidence_threshold': 70, # Minimum LLM confidence
    'stop_loss_pct': 2,             # 2% stop-loss (initial)
    'stop_loss_after_avg': 0.5,     # 0.5% stop-loss (after averaging)
    'max_lots': 5,                  # Maximum lots per position
    'margin_usage': 50,             # Use 50% of available margin
    'averaging_enabled': True,
    'max_averages': 2,              # 2 additional entries (3 total)
    'avg_trigger': 1,               # Average at 1% loss from avg price
}
```

### Files to Study

1. `apps/strategies/services/icici_futures.py` - Main algorithm
2. `apps/trading/services/futures_analyzer.py` - 9-factor analysis
3. `apps/llm/services/trade_validator.py` - LLM validation
4. `apps/llm/services/rag_system.py` - Context gathering
5. `apps/positions/services/averaging_manager.py` - Averaging logic

---

## 4. Common Concepts

### Support and Resistance Calculation (CRITICAL)

All algorithms use a **Consolidated Conservative S/R** approach that combines multiple methods and selects the most conservative (closest to price) levels.

```
┌─────────────────────────────────────────────────────────────────────┐
│                  CONSOLIDATED S/R CALCULATOR                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Method 1: PIVOT POINTS (Historical Price Data)                     │
│  ─────────────────────────────────────────────                      │
│  Pivot = (High + Low + Close) / 3                                   │
│  R1 = (2 × Pivot) - Low                                             │
│  R2 = Pivot + (High - Low)                                          │
│  S1 = (2 × Pivot) - High                                            │
│  S2 = Pivot - (High - Low)                                          │
│                                                                     │
│  Method 2: OI-BASED S/R (Options Open Interest)                     │
│  ─────────────────────────────────────────────                      │
│  Highest PUT OI Strike = Support (PUT writers defend this level)    │
│  Highest CALL OI Strike = Resistance (CALL writers defend this)     │
│                                                                     │
│  CONSERVATIVE SELECTION:                                            │
│  ─────────────────────────                                          │
│  For SUPPORT:    Select HIGHER value (closer to current price)      │
│  For RESISTANCE: Select LOWER value (closer to current price)       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Example at NIFTY 25,746:**

| Level | Pivot-Based | OI-Based | Conservative Selection |
|-------|-------------|----------|------------------------|
| S1    | 25,143      | 25,700   | **25,700** (from OI) - Higher = Closer |
| R1    | 25,419      | 26,000   | **25,419** (from Pivot) - Lower = Closer |

**Why Conservative?**
- Tighter trading range = Less room for adverse moves
- Market participants (OI) + Technical levels (Pivot) both considered
- Safer for strike selection and position averaging decisions

**Files:**
- `apps/strategies/services/consolidated_sr_calculator.py` - Main hub
- `apps/strategies/services/oi_support_resistance.py` - OI-based calculation
- `apps/strategies/services/support_resistance_calculator.py` - Pivot-based calculation

**Usage in Algorithms:**
```python
from apps.strategies.services.consolidated_sr_calculator import get_conservative_sr

# Get conservative S/R for any symbol
sr = get_conservative_sr('NIFTY', current_price=25746)

# Returns:
# {
#     'conservative_support': {'s1': 25700, 's1_source': 'oi', ...},
#     'conservative_resistance': {'r1': 25419, 'r1_source': 'pivot', ...},
#     'methods_used': ['pivot_points', 'oi_based']
# }
```

---

### ONE POSITION PER ACCOUNT Rule

```
This is CRITICAL and enforced everywhere:

def can_open_position(account):
    active_positions = Position.objects.filter(
        account=account,
        status='ACTIVE'
    ).count()

    return active_positions == 0

If this returns False, NO new position can be opened.
This prevents over-leveraging and simplifies risk management.
```

### 50% Margin Rule

```
def calculate_usable_margin(account):
    total_margin = account.get_available_margin()

    # For new positions, use only 50%
    usable = total_margin * 0.50

    # Keep 50% for:
    # - Averaging if position goes against us
    # - Margin calls
    # - Unexpected volatility

    return usable
```

### Stop-Loss Hierarchy

```
Positions are exited in this priority order:

1. STOP-LOSS (Highest Priority)
   |-- If loss > configured max_loss
   |-- Immediate market order to close
   |-- No delays, no questions

2. TARGET
   |-- If profit > configured target
   |-- Lock in profits
   |-- May use limit orders

3. END OF DAY
   |-- At configured exit_time (usually 3:15 PM)
   |-- Close all intraday positions
   |-- May carry overnight if configured

4. EXPIRY
   |-- Options: Close by 3:25 PM on expiry day
   |-- Futures: Close 3 days before expiry
   |-- Avoid physical settlement issues

5. MANUAL
   |-- Via Telegram /close command
   |-- Via web interface
```

### Market Hours Check

```python
def is_market_open():
    now = datetime.now(IST)

    # Basic time check
    market_start = time(9, 15)
    market_end = time(15, 30)

    if not (market_start <= now.time() <= market_end):
        return False

    # Day check (Monday to Friday)
    if now.weekday() > 4:  # Saturday or Sunday
        return False

    # Holiday check
    if NseFlag.is_holiday(now.date()):
        return False

    return True
```

### VIX-Based Adjustments

```
VIX (Volatility Index) affects several parameters:

VIX Range -> Adjustment
--------------------------
< 12      -> Low volatility, tighter strikes, lower premiums
12-18     -> Normal, use base parameters
18-25     -> Elevated, wider strikes, higher premiums
> 25      -> High volatility, may skip trading or reduce size

Example in Strangle:
    if vix < 12:
        strike_distance = base_distance * 0.8
    elif vix > 25:
        strike_distance = base_distance * 1.5
        position_size = position_size * 0.5  # Reduce size
```

---

## 5. How to Study These Algorithms

### Step-by-Step Learning Path

**Week 1: Understand the Basics**
1. Read `apps/core/models.py` - Understand credentials and scheduling
2. Read `apps/accounts/models.py` - Understand account structure
3. Read `apps/positions/models.py` - Understand position lifecycle

**Week 2: Study the Data Layer**
1. Read `apps/data/models.py` - Understand data structures
2. Read `apps/data/data_analyzers.py` - Study the 6 analyzers
3. Run `python manage.py shell` and query TLStockData to see real data

**Week 3: Study Strangle Algorithm**
1. Read `apps/strategies/services/kotak_strangle.py` line by line
2. Add print statements to trace execution
3. Run in test mode (paper trading) to see the flow

**Week 4: Study Futures Algorithm**
1. Read `apps/trading/services/futures_analyzer.py` - 9-factor analysis
2. Read `apps/strategies/services/icici_futures.py` - Main algorithm
3. Read `apps/llm/services/trade_validator.py` - LLM validation

**Week 5: Study Exit and Risk Management**
1. Read `apps/positions/services/exit_manager.py`
2. Read `apps/positions/services/delta_monitor.py`
3. Read `apps/risk/services/risk_manager.py`

### Debugging Tips

```python
# Add logging to trace algorithm flow
import logging
logger = logging.getLogger(__name__)

def my_function():
    logger.info("Starting function with params: %s", params)
    # ... logic ...
    logger.info("Result: %s", result)
```

```bash
# Watch logs in real-time
tail -f logs/mcube.log | grep -E "(strangle|futures|position)"
```

### Testing Changes

1. **Always test in paper trading mode first**
   - Set `account.is_paper = True`
   - Orders won't actually execute

2. **Use small position sizes**
   - Set `max_lots = 1` in config
   - Limits potential losses during testing

3. **Monitor via Telegram**
   - Use `/status` command frequently
   - Watch for alerts

4. **Check database state**
   ```python
   # Django shell
   from apps.positions.models import Position
   Position.objects.filter(status='ACTIVE').values('symbol', 'direction', 'pnl')
   ```

### Common Modifications

**Change strike calculation**:
- File: `apps/strategies/services/kotak_strangle.py`
- Function: `calculate_strikes()`

**Change entry filters**:
- File: `apps/strategies/services/icici_futures.py`
- Function: `check_entry_conditions()`

**Change composite score weights**:
- File: `apps/trading/services/futures_analyzer.py`
- Variable: `FACTOR_WEIGHTS`

**Change LLM prompt**:
- File: `apps/llm/services/trade_validator.py`
- Function: `build_validation_prompt()`

---

## Summary

| Algorithm | When | What | Risk |
|-----------|------|------|------|
| Short Strangle | Thursday expiry | Sell CE + PE | Unlimited |
| Broken IC | Thursday expiry | Sell CE + PE, Buy PE hedge | Limited downside |
| LLM Futures | Daily (scan 8:30 AM, execute 9:40 AM) | Long/Short futures with 12-factor + AI validation | Controlled with SL + averaging |

All algorithms share:
- ONE POSITION PER ACCOUNT rule
- 50% margin usage rule
- Stop-loss protection
- Telegram notifications
- Circuit breaker protection

---

*Study the code, trace the execution, and ask questions. Understanding these algorithms is key to making safe modifications.*
