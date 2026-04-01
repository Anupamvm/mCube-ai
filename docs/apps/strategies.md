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
| `services/consolidated_sr_calculator.py` | **Conservative S/R (Pivot + OI)** |
| `services/oi_support_resistance.py` | OI-based S/R calculation |
| `services/support_resistance_calculator.py` | Pivot-based S/R calculation |
| `services/strangle_news_analyzer.py` | News-based asymmetric bias for strangle |
| `services/adaptive_sl_target.py` | 3-tier SL/target engine (S/R → ATR×regime → volatility%) |
| `services/market_regime.py` | Market regime detection (TRENDING/RANGING/VOLATILE/BREAKOUT/NORMAL) |
| `services/contract_prefilter.py` | Lightweight DB-only contract pre-filter |
| `services/trade_validation.py` | Post-score R:R and regime validation gate |
| `services/llm_context_builder.py` | Enriched LLM context with regime + scoring summary |
| `analyzers/enhanced_futures_analyzer.py` | 13-component parallel analysis (315pts → 100 scale) |
| `shared/strike_calculator.py` | Strike adjustment for S/R proximity |
| `filters/global_markets.py` | Global market stability filter |
| `filters/event_calendar.py` | Economic events filter |
| `tasks.py` | Scheduled strategy tasks |
| `tasks_strangle.py` | Strangle-specific scheduled tasks (dynamic schedule) |

**Task Safety (March 2026):**
- `screen_futures_opportunities` and `execute_futures_algorithm` have **idempotency guards** (Redis key per day) to prevent duplicate runs from Beat double-fire or scheduler restarts
- Manual triggers bypass the idempotency guard
- All entry tasks check `is_circuit_breaker_active()` and `create_position()` uses a Redis lock to prevent race conditions

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

# Base Delta:
#   ≤ 2 days to expiry: 0.75%
#   > 2 days: 0.5%

# VIX Adjustments (multi-factor):
VIX < 10:        delta_multiplier = 0.9   (tighter, higher premium)
VIX 10-12.5:     delta_multiplier = 1.0   (standard)
VIX 12.5-14:     delta_multiplier = 1.5   (wider, safety +50%)
VIX 14-18:       delta_multiplier = 1.8   (much wider +80%)
VIX > 18:        delta_multiplier = 2.0   (extreme volatility)
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

1. **Trend Adjustment**: 1.1-1.3× based on bullish/bearish bias
2. **Volatility Adjustment**: Based on 5-day historical volatility
3. **OI Adjustment**: Open Interest buildup patterns
4. **PCR Adjustment**: Put-Call Ratio
5. **News-Based Asymmetric Bias**: Call vs put skew from news sentiment
6. **Psychological Levels**: Avoid strikes near round numbers (25000, 25500)

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

### Screening Process (13-Factor Composite, 315pts → 100 scale)

```
1.  OI & F&O Analysis      (45 pts) - Long/short buildup, OI change patterns
2.  Technical Momentum      (35 pts) - RSI, MACD, Bollinger Bands, DMA
3.  Trend Confirmation      (30 pts) - DMA crossovers, 52W breakout detection
4.  Volume Quality          (25 pts) - Volume vs average, delivery trend
5.  Institutional Flow      (25 pts) - FII, MF, promoter changes
6.  Fundamental Quality     (20 pts) - Piotroski F-Score, profit growth, ROE
7.  Risk Adjustment         (30 pts) - Beta scaling, volatility regime
8.  News Sentiment          (25 pts) - Recent news sentiment analysis
9.  Analyst Consensus       (20 pts) - Analyst target price consensus
10. Research Reports        (15 pts) - LLM-analyzed research sentiment
11. Investor Calls          (10 pts) - Earnings call sentiment
12. Momentum Acceleration   (20 pts) - Short-term momentum change
13. MTF Confluence          (15 pts) - Multi-timeframe alignment
```

### Composite Scoring

13 components contribute a raw total of 315 points, normalized to a 0-100 scale:

```python
# 13-Component System (315 pts raw → 100 scale)
# See "13-Factor Composite" above for full component list and weights.
#
# Raw score = sum of all 13 component scores (max 315)
# Normalized score = (raw_score / 315) × 100

# Recommendation Tiers:
Score >= 80:  STRONG BUY
Score 65-79:  BUY
Score < 65:   REJECT
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
- Previous averaging attempts < 2

# Averaging Action:
1. Add equal quantity at current price
2. Calculate new weighted average
3. Tighten stop-loss to 0.5% from new average
4. Increment averaging_count
```

---

## Screen Futures Algorithm (Automated Task)

**Task**: `execute_futures_algorithm` (9:40 AM daily)
**File**: `apps/strategies/tasks.py`

### Overview

The Screen Futures Algorithm is an automated opportunity scanner that:
1. Screens high-volume futures contracts
2. Analyzes using a 13-component scoring system (315 pts → 100 scale)
3. Presents TOP 3 candidates for user confirmation via Telegram
4. Executes trades with intelligent batching on approval

### Workflow

```
9:40 AM: execute_futures_algorithm triggers
    │
    ├─> Pre-checks (holiday, weekend, config)
    │
    ├─> Get TOP 50 contracts by volume
    │
    ├─> Split into batches of 3, dispatch parallel analysis
    │       (Celery chord: 17 parallel tasks)
    │
    ├─> Each batch runs 13-component scoring (315 pts → 100 scale):
    │     1. OI & F&O Analysis (45 pts)
    │     2. Technical Momentum (35 pts)
    │     3. Trend Confirmation (30 pts)
    │     4. Volume Quality (25 pts)
    │     5. Institutional Flow (25 pts)
    │     6. Fundamental Quality (20 pts)
    │     7. Risk Adjustment (30 pts)
    │     8. News Sentiment (25 pts)
    │     9. Analyst Consensus (20 pts)
    │    10. Research Reports (15 pts)
    │    11. Investor Calls (10 pts)
    │    12. Momentum Acceleration (20 pts)
    │    13. MTF Confluence (15 pts)
    │     → Composite Scoring (315 pts → 100 scale)
    │
    ├─> aggregate_futures_results callback:
    │     - Filter: score >= 65
    │     - Sort by score descending
    │     - Save to TradeSuggestion
    │
    └─> TWO-STEP TELEGRAM APPROVAL FLOW:

        STEP 1: SELECTION SCREEN
        ┌─────────────────────────────────────┐
        │ 📈 FUTURES OPPORTUNITIES            │
        │ 💰 Available Margin: ₹12,00,000     │
        │                                     │
        │ 1️⃣ RELIANCE 🟢 LONG                │
        │    Score: 82/100 | Entry: ₹2,450   │
        │    [📊 View RELIANCE]              │
        │                                     │
        │ 2️⃣ TATASTEEL 🟢 LONG               │
        │    Score: 78/100 | Entry: ₹142     │
        │    [📊 View TATASTEEL]             │
        │                                     │
        │ [❌ Skip All]                       │
        └─────────────────────────────────────┘

        STEP 2: DETAIL VIEW (on View click)
        ┌─────────────────────────────────────┐
        │ 📊 TRADE CONFIRMATION               │
        │                                     │
        │ Symbol: RELIANCE                    │
        │ Direction: 🟢 LONG                  │
        │ Score: 82/100                       │
        │                                     │
        │ 📍 PRICE LEVELS                     │
        │   Entry: ₹2,450.00                  │
        │   Stop-Loss: ₹2,425.00              │
        │   Target: ₹2,525.00                 │
        │                                     │
        │ 📐 POSITION SIZE                    │
        │   Lots: 2 | Margin: ₹1,20,000       │
        │                                     │
        │ ⚖️ RISK/REWARD = 1:3                │
        │                                     │
        │ [✅ Confirm Trade (2L)]             │
        │ [📊 Change Lots]                    │
        │ [◀️ Back] [❌ Skip]                  │
        └─────────────────────────────────────┘

        STEP 3: EXECUTION (on Confirm click)
        - Spawns background thread
        - Executes trade via Breeze API
        - Progress updates in same message
        - Uses batching for large orders
```

### 13-Component Scoring System

| # | Component | Max Pts | Description |
|---|-----------|---------|-------------|
| 1 | OI & F&O Analysis | 45 | Long/short buildup, OI change patterns |
| 2 | Technical Momentum | 35 | RSI, MACD, Bollinger Bands, DMA position |
| 3 | Trend Confirmation | 30 | DMA crossovers, 52W breakout detection |
| 4 | Volume Quality | 25 | Volume vs average, delivery trend |
| 5 | Institutional Flow | 25 | FII, MF, promoter changes |
| 6 | Fundamental Quality | 20 | Piotroski F-Score, profit growth, ROE |
| 7 | Risk Adjustment | 30 | Beta scaling, volatility regime |
| 8 | News Sentiment | 25 | Recent news sentiment analysis |
| 9 | Analyst Consensus | 20 | Analyst target price consensus |
| 10 | Research Reports | 15 | LLM-analyzed research sentiment |
| 11 | Investor Calls | 10 | Earnings call sentiment |
| 12 | Momentum Acceleration | 20 | Short-term momentum change |
| 13 | MTF Confluence | 15 | Multi-timeframe alignment |
| | **Total** | **315** | **Normalized to 0-100 scale** |

### 7 Hard Reject Filters

Even with a high score, these conditions cause automatic rejection:

1. **MWPL**: Market-Wide Position Limit < 80%
2. **Volatility**: Intraday volatility < 60%
3. **Piotroski Score**: F-Score >= 4 required (poor fundamentals rejected)
4. **Promoter Pledge**: Promoter pledge < 30%
5. **FII Change**: FII change > -2%
6. **Blocking News**: No blocking news events
7. **Analyst Upside**: Analyst upside >= 8% (for LONG trades)

### Configuration (TradingCoreConfig)

**Notification Level Impact:**
| Level | Behavior |
|-------|----------|
| FULL_CONTROL | TOP 3 sent for confirmation, waits for user |
| SUPERVISED | Same (entries require confirmation) |
| AUTONOMOUS | Auto-executes top candidate |
| SIMULATED | Paper trade, no real orders |

**Position Sizing Impact:**
| Mode | Lots |
|------|------|
| TEST | 1 lot always |
| MANUAL | Fixed from config |
| AUTO | Calculated from margin |
| SIMULATED | Hypothetical large positions |

### Task Parameters (Configurable via UI)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `top_contracts` | 50 | Contracts to analyze |
| `batch_size` | 3 | Contracts per parallel task (set in celery.py kwargs) |
| `this_month_volume` | 1000 | Min volume (current month) |
| `next_month_volume` | 800 | Min volume (next month) |
| `min_score` | 65 | Minimum qualifying score |

Configure at: http://localhost:8000/system/celery-tasks/ → execute-futures-algorithm → Task Parameters

### Order Batching

For large positions (> 10 lots):
- Split into batches of 10 lots each
- 10-second delay between batches
- Progress updates via Telegram with **Stop Execution** button
- User can cancel remaining batches mid-execution

**During Execution:**
```
🔄 EXECUTING TRADE

Symbol: RELIANCE
Direction: LONG

📊 Progress: Batch 2/5
✅ Lots executed: 20/50

Waiting 10 seconds before next batch...
Click 'Stop' to cancel remaining batches.

[🛑 Stop Execution]
```

**On Stop Click:**
- Sets `is_cancelled=True` in `OrderExecutionControl`
- Background thread checks before each batch
- Already-placed orders are NOT reversed
- User sees summary of completed batches

---

## Support and Resistance System

All strategies use a **Consolidated Conservative S/R** system that combines multiple calculation methods.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│               ConsolidatedSRCalculator                          │
│         (apps/strategies/services/consolidated_sr_calculator.py) │
├─────────────────────────────────────────────────────────────────┤
│                           │                                     │
│          ┌────────────────┴────────────────┐                    │
│          ▼                                 ▼                    │
│  ┌───────────────────┐         ┌───────────────────────┐        │
│  │  Pivot Points     │         │  OI-Based S/R         │        │
│  │  (Historical)     │         │  (Options OI)         │        │
│  └───────────────────┘         └───────────────────────┘        │
│                           │                                     │
│          └────────────────┴────────────────┘                    │
│                           ▼                                     │
│              CONSERVATIVE SELECTION                             │
│   Support: HIGHER value (closer to price)                       │
│   Resistance: LOWER value (closer to price)                     │
└─────────────────────────────────────────────────────────────────┘
```

### Methods

**1. Pivot Points** (`support_resistance_calculator.py`)
- Uses 5-day historical high/low/close average
- Standard pivot point formula
- Source: `HistoricalPrice` table (Breeze API)

**2. OI-Based S/R** (`oi_support_resistance.py`)
- Highest PUT OI strike = Support (PUT writers defend this)
- Highest CALL OI strike = Resistance (CALL writers defend this)
- Source: `ContractData` table (F&O OI data)

### Usage

```python
from apps.strategies.services.consolidated_sr_calculator import (
    get_conservative_sr,
    ConsolidatedSRCalculator
)

# Quick access
sr = get_conservative_sr('NIFTY', current_price=25746)
print(f"S1: {sr['conservative_support']['s1']} (from {sr['conservative_support']['s1_source']})")
print(f"R1: {sr['conservative_resistance']['r1']} (from {sr['conservative_resistance']['r1_source']})")

# Full analysis
calculator = ConsolidatedSRCalculator('NIFTY')
full_sr = calculator.calculate_all_sr_methods(current_price=25746)
# Returns S/R from all methods before conservative selection
```

### Where S/R is Used

| Algorithm | Usage | File |
|-----------|-------|------|
| **Strangle** | Adjust strikes away from S/R | `shared/strike_calculator.py` |
| **Futures** | Entry point validation | `technical_analysis.py` |
| **Averaging** | Check if averaging is safe | `averaging_analyzer.py` |
| **Level 2 Analysis** | Deep-dive S/R analysis | `level2_analyzers.py` |

### Strike Adjustment Logic

When placing option strikes:
- If **CALL** strike is within 100 pts of R1/R2 → Move UP 50 pts
- If **PUT** strike is within 100 pts of S1/S2 → Move DOWN 50 pts

```python
from apps.strategies.shared.strike_calculator import adjust_strikes_for_sr

result = adjust_strikes_for_sr(
    call_strike=25800,
    put_strike=25700,
    spot_price=25746
)
# If put_strike is at OI-based S1 (25700), it gets adjusted to 25650
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

### Main Strategy Tasks (`tasks.py`)

| Task | Schedule | Purpose |
|------|----------|---------|
| `setup_trading_day` | 8:55 AM | Evaluate data, determine if day is tradable |
| `start_trading_day` | 9:15 AM | Validate market opening, check news/changes |
| `evaluate_options_strategy` | 9:30 AM | Options strategy decision (strangle vs iron condor) |
| `start_options_trade` | 9:40 AM | Options entry execution |
| `execute_futures_algorithm` | 9:40 AM | Futures screening + execution (13-component, batched) |
| `screen_futures_opportunities` | 9:30 AM | Pre-market futures scan |
| `evaluate_kotak_strangle_entry` | Mon & Tue 10:00 AM | Kotak strangle entry evaluation |
| `evaluate_kotak_strangle_exit` | Via dynamic scheduler | Kotak strangle exit (profit threshold check) |
| `monitor_all_strangle_deltas` | Every 15 min | Delta drift monitoring (threshold: 300) |
| `batch_options_averaging` | 9:40-10:30 AM, every 1 min | Options averaging in batches |
| `check_futures_averaging` | Every 10 min (9:40-14:30) | Futures averaging checks |
| `close_trading_day` | 3:25 PM | Close positions with profit conditions |

### Strangle Dynamic Tasks (`tasks_strangle.py`)

| Task | Purpose |
|------|---------|
| `premarket_data_fetch` | Pre-market data collection |
| `market_opening_validation` | Market opening checks |
| `trade_start_evaluation` | Entry evaluation |
| `schedule_staggered_entries` | Staggered option entries |
| `execute_single_entry` | Individual entry execution |
| `trade_monitoring` | Active trade monitoring |
| `trade_stop_evaluation` | Stop/exit evaluation |
| `day_close_reconciliation` | End-of-day reconciliation |
| `analyze_day` | Day performance analysis |

### Futures Pipeline Tasks

| Task | Purpose |
|------|---------|
| `analyze_futures_batch` | Parallel batch analysis (13-component scoring per batch) |
| `aggregate_futures_results` | Callback: filter, sort, save top candidates to TradeSuggestion |

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
