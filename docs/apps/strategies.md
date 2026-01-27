# Strategies App Documentation

**Location**: `apps/strategies/`

The strategies app contains the trading algorithms - the brain of mCube. This is where entry decisions are made, strikes are calculated, and positions are sized.

---

## What This App Does

1. **Entry Evaluation** - Determines if market conditions are right for entry
2. **Strike Calculation** - Calculates optimal option strikes based on VIX
3. **Position Sizing** - Determines how many lots to trade
4. **Filter Application** - Applies entry filters (global markets, events, volatility)
5. **Risk Metrics** - Calculates max profit, max loss, breakeven points

---

## Files Overview

| File | Purpose |
|------|---------|
| `strategies/kotak_strangle.py` | Nifty Short Strangle algorithm (26KB) |
| `strategies/kotak_broken_iron_condor.py` | Iron Condor with insurance (40KB) |
| `strategies/icici_futures.py` | Futures trading algorithm (32KB) |
| `services/strangle_delta_algorithm.py` | Strike calculation logic |
| `services/market_condition_validator.py` | Entry filter validation |
| `services/historical_analysis.py` | Historical data analysis |
| `services/technical_analysis.py` | Technical indicators |
| `services/greeks_calculator.py` | Black-Scholes Greeks |
| `filters/global_markets.py` | Global market stability filter |
| `filters/event_calendar.py` | Economic events filter |
| `tasks.py` | Scheduled strategy tasks |

---

## Strategy 1: Nifty Short Strangle (Kotak)

**File**: `strategies/kotak_strangle.py`

### Concept

Sell both a CALL and PUT option at out-of-the-money strikes. You collect premium upfront. If NIFTY stays between your strikes until expiry, you keep all the premium.

### When to Enter

- **Day**: Monday or Tuesday (gives time for theta decay)
- **Time**: 9:30 AM - 11:30 AM (entry window)
- **Expiry**: Weekly expiry (Thursday), minimum 1 day to expiry

### Entry Filters

Before any entry, these filters must pass:

```python
# 1. Global Markets Filter
- SGX Nifty change < 0.5%
- US markets (Dow, Nasdaq) change < 1.0%

# 2. Economic Events Filter
- No HIGH importance events in next 5 days
- No RBI policy, Budget, FOMC, etc.

# 3. Volatility Filter
- Intraday gap < 0.75%
- Intraday swing < 1.5%
- 3-day movement < delta-based threshold
- VIX spike < 20% from previous day

# 4. Position Filter
- No active position exists (ONE POSITION RULE)
```

### Strike Calculation Algorithm

The heart of the strangle strategy is calculating optimal strikes.

```python
# Base Formula
strike_distance = spot_price × delta% × days_to_expiry

# Where delta% is adjusted for VIX:
VIX < 10:        delta_multiplier = 0.9   (very tight)
VIX 10-11.5:     delta_multiplier = 1.0   (normal)
VIX 11.5-12.5:   delta_multiplier = 1.0   (optimal)
VIX 12.5-14:     delta_multiplier = 1.5   (wider)
VIX 14-18:       delta_multiplier = 1.8   (much wider)
VIX > 18:        delta_multiplier = 2.0   (very wide)
```

**Example Calculation**:
```
Spot: 24,150
VIX: 12.3 (normal, multiplier = 1.0)
Base Delta: 0.5%
Days to Expiry: 3

Strike Distance = 24,150 × 0.5% × 3 × 1.0 = 362 points

Call Strike = 24,150 + 362 = 24,512 → Round to 24,500
Put Strike = 24,150 - 362 = 23,788 → Round to 23,800

Final: SELL 24500 CE + SELL 23800 PE
```

### Additional Adjustments

The algorithm also adjusts for:

1. **Trend Adjustment**: If bullish trend, widen call by 15%
2. **Volatility Adjustment**: Based on 5-day price movement
3. **OI Analysis**: Based on put-call ratio
4. **Psychological Levels**: Avoid strikes near round numbers (25000, 25500)

### Position Sizing

```python
# Calculate usable margin (50% of available)
usable_margin = available_margin × 0.50

# Calculate max lots
max_lots = usable_margin / margin_per_lot

# Apply conservative sizing (usually 1 lot initially)
recommended_lots = min(max_lots, conservative_limit)
```

### Risk Metrics

```python
# For a strangle
max_profit = premium_collected
max_loss = UNLIMITED (theoretical)
breakeven_upper = call_strike + (total_premium / lot_size)
breakeven_lower = put_strike - (total_premium / lot_size)
```

### Exit Conditions

1. **Stop-Loss**: Premium doubles (100% loss on premium)
2. **Target**: 70% of premium collected
3. **EOD Thursday**: Exit if profit >= 50%
4. **Expiry Friday**: Mandatory exit by 3:20 PM

---

## Strategy 2: Broken Iron Condor (Kotak)

**File**: `strategies/kotak_broken_iron_condor.py`

### Concept

Same as strangle, but with an insurance PUT to cap downside risk.

### 3-Leg Structure

```
Leg 1: SELL CALL @ OTM strike (same as strangle)
Leg 2: SELL PUT @ OTM strike (same as strangle)
Leg 3: BUY PUT @ further OTM strike (INSURANCE)
```

### Insurance Strike Calculation

```python
# Risk Budget = Max Profit × Risk Multiplier (default: 2.0)
risk_budget = max_profit × 2.0

# Insurance Strike
insurance_strike = put_strike - (risk_budget / quantity)

# Example:
# Put Strike: 23,500
# Max Profit: Rs 30,000
# Risk Budget: Rs 60,000 (2x profit)
# Quantity: 50
# Insurance Strike = 23,500 - 1,200 = 22,300
```

### Benefits

- **Capped Max Loss**: Risk budget defines maximum loss
- **Lower Margin**: Insurance reduces margin requirement
- **Risk/Reward**: 1:2 ratio (risk Rs 60K to make Rs 30K)

---

## Strategy 3: LLM-Validated Futures (ICICI)

**File**: `strategies/icici_futures.py`

### Concept

Directional futures trading with AI validation. Screen stocks using multiple factors, validate with LLM, then trade.

### Screening Process (9 Factors)

```
1. Liquidity Filter     - Volume must be sufficient
2. OI Analysis          - Long/short buildup detection
3. Sector Analysis      - Sector alignment (3D, 7D, 21D)
4. Technical Indicators - RSI, MACD, moving averages
5. Trendlyne Scores     - Durability, valuation, momentum
6. Support/Resistance   - Key price levels
7. Volume Analysis      - Volume patterns
8. Historical Analysis  - Recent price movements
9. Composite Scoring    - Combined verdict
```

### Composite Scoring

Each factor contributes to a score out of 100:

```python
OI Score (max 40):
  - Strong long buildup: 40
  - Moderate buildup: 25
  - Neutral: 15
  - Short buildup: 0

Sector Score (max 25):
  - All timeframes aligned: 25
  - Most aligned: 15
  - Mixed: 5

Technical Score (max 35):
  - Strong buy signals: 35
  - Moderate: 20
  - Neutral: 10
```

**Minimum Score**: 65/100 to qualify

### LLM Validation

After scoring, the trade is validated by LLM:

```python
# LLM receives:
- Stock symbol and direction
- Composite score and breakdown
- Recent news sentiment
- Market context

# LLM returns:
- APPROVED or REJECTED
- Confidence score (0-100%)
- Reasoning
- Risk factors

# Minimum confidence: 70%
```

### Entry Decision

```python
if composite_score >= 65 and llm_confidence >= 70:
    create_trade_suggestion()  # Goes to approval queue
```

### Position Sizing (Futures)

```python
# Based on risk, not margin
max_loss_per_trade = account.max_daily_loss / 3  # e.g., Rs 50K
risk_per_share = entry_price - stop_loss
max_quantity = max_loss_per_trade / risk_per_share
recommended_lots = max_quantity / lot_size
```

### Averaging Protocol

If position goes against you:

```python
# Averaging Triggers when:
- Position loss >= 1% from entry
- Previous averaging attempts < 3

# Averaging Action:
1. Add equal quantity at current price
2. Calculate new weighted average
3. Tighten stop-loss to 0.5% from new average
4. Increment averaging_count
```

---

## Services

### Strike Delta Algorithm (`services/strangle_delta_algorithm.py`)

```python
from apps.strategies.services.strangle_delta_algorithm import StrangleDeltaAlgorithm

algo = StrangleDeltaAlgorithm()
strikes = algo.calculate_strikes(
    spot=24150,
    vix=12.3,
    days_to_expiry=3,
    trend='NEUTRAL'
)
# Returns: {'call_strike': 24500, 'put_strike': 23800}
```

### Market Condition Validator (`services/market_condition_validator.py`)

```python
from apps.strategies.services.market_condition_validator import MarketConditionValidator

validator = MarketConditionValidator()
result = validator.validate_entry_conditions()
# Returns: {'can_trade': True/False, 'reasons': [...]}
```

### Greeks Calculator (`services/greeks_calculator.py`)

```python
from apps.strategies.services.greeks_calculator import calculate_greeks

greeks = calculate_greeks(
    spot=24150,
    strike=24500,
    days_to_expiry=3,
    volatility=0.15,
    option_type='CALL'
)
# Returns: {'delta': 0.35, 'gamma': 0.002, 'theta': -5.2, 'vega': 12.5}
```

---

## Filters

### Global Markets (`filters/global_markets.py`)

```python
from apps.strategies.filters.global_markets import check_global_market_stability

result = check_global_market_stability()
# Returns: {'passed': True/False, 'details': {...}}
```

### Event Calendar (`filters/event_calendar.py`)

```python
from apps.strategies.filters.event_calendar import check_economic_events

result = check_economic_events(days_ahead=5)
# Returns: {'passed': True/False, 'events': [...]}
```

---

## Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `evaluate_kotak_strangle_entry` | Mon/Tue 10:00 AM | Strangle entry check |
| `evaluate_kotak_strangle_exit` | Thu 3:15, Fri 3:25 | Exit evaluation |
| `screen_and_execute_futures` | Every 30 min | Futures screening |
| `monitor_delta_positions` | Every 5 min | Delta monitoring |

---

## How to Study This App

1. **Start with `kotak_strangle.py`** - Most documented algorithm
2. **Read `strangle_delta_algorithm.py`** - Understand strike calculation
3. **Study `icici_futures.py`** - Learn the scoring system
4. **Check `filters/`** - See entry validation
5. **Review `tasks.py`** - Understand scheduling

---

## Algorithm Study Guide

### Strangle Strike Calculation

1. Get current spot price
2. Get VIX and calculate multiplier
3. Calculate base strike distance
4. Apply trend adjustment
5. Apply psychological level avoidance
6. Round to nearest strike interval

### Futures Composite Scoring

1. Fetch OI data → Calculate OI score
2. Analyze sector → Calculate sector score
3. Check technicals → Calculate technical score
4. Sum scores → Check threshold
5. If qualified, send to LLM
6. If LLM approves, create suggestion

---

## Key Files for Each Strategy

### Strangle
- Entry: `strategies/kotak_strangle.py:evaluate_entry()`
- Strikes: `services/strangle_delta_algorithm.py`
- Exit: `strategies/kotak_strangle.py:evaluate_exit()`

### Iron Condor
- Entry: `strategies/kotak_broken_iron_condor.py:evaluate_entry()`
- Insurance: `strategies/kotak_broken_iron_condor.py:calculate_insurance_strike()`

### Futures
- Screening: `strategies/icici_futures.py:screen_candidates()`
- Scoring: `strategies/icici_futures.py:calculate_composite_score()`
- Entry: `strategies/icici_futures.py:execute_entry()`

---

*For questions, check the code comments or ask the team.*
