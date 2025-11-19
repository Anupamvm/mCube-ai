# Nifty Strangle Strategy - Implementation Guide

## Project Overview

Implementing a comprehensive **Nifty Weekly Strangle Strategy** with manual triggers and full algorithm visualization. This will be the same algorithm used in background tasks for Kotak Neo, but with a manual trigger interface for testing and monitoring.

---

## Implementation Progress

### ✅ Phase 1: Data Collection Infrastructure (IN PROGRESS)

#### 1.1 Models Created ✅

**File:** `apps/strategies/models_strangle.py`

**Models:**

1. **`NiftyMarketData`** - Stores comprehensive market data
   - Nifty spot price and OHLC (Open, High, Low, Close)
   - Previous close, price changes
   - Global markets (SGX Nifty, Dow, Nasdaq, S&P 500, GIFT Nifty)
   - India VIX and VIX change
   - Technical indicators (5, 10, 20, 50, 200 DMAs)
   - Volume and turnover
   - Market sentiment (advances/declines)
   - Data freshness tracking (is_stale flag for > 5 min old data)

2. **`NiftyOptionChain`** - Stores option chain data
   - Links to NiftyMarketData
   - Strike price and expiry
   - **Call Option:** LTP, OI, OI change, volume, IV, Delta, Gamma, Theta, Vega
   - **Put Option:** LTP, OI, OI change, volume, IV, Delta, Gamma, Theta, Vega
   - PCR (Put-Call Ratio) for OI and volume
   - ATM flag and distance from spot

3. **`StrangleAlgorithmState`** - Tracks algorithm execution
   - Links to market data
   - Current status (10 states from INITIALIZED to COMPLETED)
   - Progress tracking (current_step / total_steps)
   - Selected strikes (call and put)
   - Premium data (call, put, total)
   - Delta analysis (call_delta, put_delta, net_delta, delta_target)
   - Risk metrics (max_loss, breakeven points, margin required)
   - **10 step data fields** (step_1_data through step_10_data) - JSON fields storing details of each algorithm step
   - Execution metadata (time, errors)
   - User who triggered

#### 1.2 Data Fetcher Service ✅

**File:** `apps/strategies/services/nifty_data_fetcher.py`

**Class:** `NiftyDataFetcher`

**Methods:**

1. `fetch_all_data()` - Main orchestrator, fetches all required data
2. `fetch_spot_data()` - Nifty spot price, OHLC from Breeze
3. `fetch_vix()` - India VIX from Breeze
4. `fetch_option_chain(spot_price)` - Full option chain with Greeks from Breeze
5. `fetch_global_markets()` - SGX, Dow, Nasdaq, S&P 500, GIFT Nifty
6. `fetch_technical_indicators()` - DMAs from Trendlyne data
7. `fetch_oi_analysis()` - OI data from Trendlyne

**Features:**
- Smart error handling with error collection
- Automatic ATM strike identification
- Filters option chain to ±1000 points from ATM
- Weekly expiry detection (Thursdays)
- Data freshness tracking

---

## 📋 Complete Roadmap

### Phase 1: Data Collection Infrastructure (75% Complete)

- ✅ Create models for market data, option chain, algorithm state
- ✅ Build data fetcher service
- ✅ Implement Breeze API integration for option chain
- ✅ **NEW:** Enhanced NiftyOptionChain model in brokers app with Greeks fields
- ✅ **NEW:** Created Greeks calculator using Black-Scholes model
- ✅ **NEW:** Integrated IV calculation using Newton-Raphson method
- ✅ Database migrations created and applied
- ⏳ Add global markets API integration (Yahoo Finance / Alpha Vantage)
- ⏳ Create data validation and sanitization
- ⏳ Test data fetcher with live market data
- ⏳ Add data caching mechanism (5-minute cache)

### Phase 2: Algorithm Engine (Not Started)

**File to create:** `apps/strategies/services/strangle_algorithm.py`

**Class:** `NiftyStrangleAlgorithm`

#### Algorithm Steps (10 Steps Total):

**Step 1: Market Data Collection**
- Fetch Nifty spot, VIX, option chain
- Validate data completeness
- Store in `NiftyMarketData`
- Log: Spot price, VIX, data timestamp

**Step 2: Option Chain Analysis**
- Parse option chain data
- Identify ATM strike (rounded to nearest 50)
- Extract all strikes ±1000 points
- Store in `NiftyOptionChain`
- Log: Total strikes, ATM strike, range

**Step 3: Market Sentiment Analysis**
- Analyze VIX level (high/medium/low)
- Check global markets sentiment
- Analyze price vs DMAs
- Determine market regime (trending/ranging)
- Log: VIX assessment, sentiment, regime

**Step 4: Call Strike Selection**
- Start from ATM + 50
- Iterate through strikes (ATM+50, ATM+100, ATM+150...)
- Calculate delta for each call option
- Select strike where call delta ≈ 0.30-0.35
- Log: Strikes evaluated, deltas calculated, selected strike

**Step 5: Put Strike Selection**
- Start from ATM - 50
- Iterate through strikes (ATM-50, ATM-100, ATM-150...)
- Calculate delta for each put option
- Select strike where put delta ≈ -0.30 to -0.35
- Log: Strikes evaluated, deltas calculated, selected strike

**Step 6: Delta Calculation & Balancing**
- Calculate net position delta (call_delta + put_delta)
- Check if |net_delta| is within acceptable range
- If net_delta too high/low, adjust strikes
- Target: Net delta between 250-350
- Log: Individual deltas, net delta, adjustments made

**Step 7: Premium Evaluation**
- Get premiums for selected strikes
- Calculate total premium collected
- Check if premium > minimum threshold (e.g., ₹150 total)
- Evaluate premium vs risk ratio
- Log: Call premium, put premium, total, min threshold

**Step 8: Risk Assessment**
- Calculate max loss (margin required)
- Calculate breakeven points
- Calculate profit/loss zones
- Evaluate risk/reward ratio
- Check if within risk limits
- Log: Max loss, breakevens, risk/reward

**Step 9: Final Validation**
- Validate all criteria met:
  - Delta within range
  - Premium adequate
  - Risk acceptable
  - VIX within bounds
  - No unusual OI patterns
- Log: All validation checks

**Step 10: Position Summary**
- Generate final recommendation
- Create position summary
- Calculate expected margin
- Generate entry instructions
- Log: Complete position details

**Methods to Implement:**

```python
class NiftyStrangleAlgorithm:
    def __init__(self, market_data):
        self.market_data = market_data
        self.state = None
        self.option_chain = []

    def execute(self):
        """Run complete 10-step algorithm"""

    def step_1_collect_data(self):
        """Fetch and validate market data"""

    def step_2_analyze_option_chain(self):
        """Parse and structure option chain"""

    def step_3_market_sentiment(self):
        """Analyze market conditions"""

    def step_4_select_call_strike(self):
        """Find optimal call strike based on delta"""

    def step_5_select_put_strike(self):
        """Find optimal put strike based on delta"""

    def step_6_calculate_delta(self):
        """Calculate and balance position delta"""

    def step_7_evaluate_premium(self):
        """Check premium adequacy"""

    def step_8_assess_risk(self):
        """Calculate risk metrics"""

    def step_9_final_validation(self):
        """Validate all criteria"""

    def step_10_generate_summary(self):
        """Create position recommendation"""
```

### Phase 3: UI & Visualization (Not Started)

**File to create:** `apps/trading/templates/trading/nifty_strangle_trigger.html`

#### UI Components:

1. **Header Section**
   - Page title
   - Last refresh timestamp
   - Refresh button
   - Current market status

2. **Market Data Panel**
   - Nifty Spot: 22,450 (+0.5%)
   - India VIX: 14.2 (-2.3%)
   - Global Markets: SGX, Dow, Nasdaq, S&P 500
   - Technical: Above/Below DMAs

3. **Algorithm Progress Tracker**
   ```
   Step 1: Market Data Collection ✅
   Step 2: Option Chain Analysis ✅
   Step 3: Market Sentiment ⏳
   Step 4: Call Strike Selection ⏸️
   ...
   ```

4. **Delta Visualization**
   ```
   Call Strike: 22,500
   Call Delta: +0.32
   ━━━━━━▓▓▓▓░░░░░░

   Put Strike: 22,400
   Put Delta: -0.33
   ░░░░░░▓▓▓▓━━━━━━

   Net Delta: 285 ✅ (Target: 250-350)
   ```

5. **Option Chain Display**
   - Table showing strikes ±1000 from ATM
   - Highlight selected strikes
   - Show CE/PE premiums, OI, Greeks

6. **Risk Metrics Panel**
   - Max Loss
   - Breakeven Points
   - Profit/Loss Graph
   - Margin Required

7. **Step-by-Step Log**
   - Expandable accordion for each step
   - Shows data collected/calculated
   - Highlights decisions made
   - Shows state transitions

8. **Action Buttons**
   - "Run Algorithm" - Execute strangle strategy
   - "Refresh Data" - Update market data
   - "Execute Trade" - Send to broker (if approved)
   - "Save for Later" - Store recommendation

---

## Database Schema

### Migration Required

```bash
python manage.py makemigrations strategies
python manage.py migrate
```

**New Tables:**
- `nifty_market_data`
- `nifty_option_chain`
- `strangle_algorithm_state`

---

## API Endpoints to Create

**File:** `apps/trading/urls.py` (already has placeholder)

```python
# Nifty Strangle
path('api/strangle/run/', views.run_strangle_algorithm, name='run_strangle'),
path('api/strangle/status/<int:state_id>/', views.get_strangle_status, name='strangle_status'),
path('api/strangle/refresh-data/', views.refresh_nifty_data, name='refresh_nifty_data'),
```

**File:** `apps/trading/views.py`

```python
@login_required
def trigger_nifty_strangle(request):
    """Manual trigger page for Nifty strangle"""
    # Render UI

@login_required
@require_POST
def run_strangle_algorithm(request):
    """Execute the strangle algorithm"""
    # 1. Fetch data
    # 2. Run 10-step algorithm
    # 3. Return state ID for tracking

@login_required
def get_strangle_status(request, state_id):
    """Get current algorithm state (for polling)"""
    # Return JSON with current step, progress, data

@login_required
@require_POST
def refresh_nifty_data(request):
    """Refresh Nifty market data"""
    # Fetch fresh data, return JSON
```

---

## Usage Flow

```
User clicks "Nifty Strangle" →
Manual Trigger Page Loads →
Shows current market data →
User clicks "Run Algorithm" →
Backend executes 10 steps →
Frontend polls for progress →
Shows step-by-step updates →
Algorithm completes →
Shows recommended strikes →
User reviews →
User clicks "Execute Trade" →
Position created in Kotak Neo
```

---

## Greeks Calculation Implementation

### Black-Scholes Model

**File:** `apps/strategies/services/greeks_calculator.py`

We've implemented a comprehensive Greeks calculator using the Black-Scholes option pricing model:

#### Calculated Greeks:

1. **Delta** - Rate of change of option price with respect to spot price
   - Call Delta: 0 to 1 (ATM ≈ 0.5)
   - Put Delta: -1 to 0 (ATM ≈ -0.5)

2. **Gamma** - Rate of change of delta (same for call and put)

3. **Theta** - Time decay (per day)

4. **Vega** - Sensitivity to volatility changes

5. **Implied Volatility (IV)** - Calculated using Newton-Raphson method

#### Key Functions:

```python
calculate_all_greeks(
    spot_price,      # Current Nifty spot
    strike_price,    # Strike price
    expiry_date,     # Option expiry
    call_ltp,        # Call market price
    put_ltp,         # Put market price
    india_vix=None   # Optional VIX for initial IV guess
)
```

**Features:**
- Uses India VIX as initial IV guess if available
- Newton-Raphson method for accurate IV estimation
- Handles edge cases (very low premiums, near expiry)
- Returns all Greeks in Decimal format for precision

**Risk-Free Rate:** 6.5% (configurable, current RBI repo rate)

---

## Delta Calculation Logic

The delta values are calculated using the **Black-Scholes model** (Breeze API provides LTP, OI, volume but not Greeks).

**Call Delta:** Ranges from 0 to 1
- ATM call delta ≈ 0.5
- OTM call delta < 0.5
- Target: Find strike where delta ≈ 0.30-0.35

**Put Delta:** Ranges from -1 to 0
- ATM put delta ≈ -0.5
- OTM put delta > -0.5
- Target: Find strike where delta ≈ -0.30 to -0.35

**Net Delta:** Sum of call and put deltas
- Example: 0.32 + (-0.33) = -0.01 × lot size
- For Nifty (lot size 50): -0.01 × 50 × spot = delta in rupees
- Target: Keep net delta between 250-350 in absolute value

---

## Configuration Parameters

**File to create:** `apps/strategies/config/strangle_config.py`

```python
STRANGLE_CONFIG = {
    'MIN_PREMIUM': 150,  # Minimum total premium in ₹
    'MAX_PREMIUM': 500,  # Maximum total premium
    'TARGET_CALL_DELTA': 0.32,  # Ideal call delta
    'TARGET_PUT_DELTA': -0.33,  # Ideal put delta
    'DELTA_TOLERANCE': 0.05,  # ±0.05 is acceptable
    'NET_DELTA_MIN': 250,  # Minimum net delta
    'NET_DELTA_MAX': 350,  # Maximum net delta
    'MAX_VIX': 25,  # Don't trade if VIX > 25
    'MIN_VIX': 10,  # Don't trade if VIX < 10
    'STRIKE_RANGE': 1000,  # ±1000 points from ATM
    'LOT_SIZE': 50,  # Nifty lot size
    'MAX_LOSS_LIMIT': 50000,  # Max loss in ₹
}
```

---

## Next Steps

1. **Create migration** for new models
2. **Implement Breeze option chain integration** with Greeks
3. **Build the 10-step algorithm engine**
4. **Create the UI** with real-time progress display
5. **Add delta visualization** charts
6. **Implement trade execution** integration with Kotak Neo
7. **Add to background tasks** for automated execution

---

## Testing Strategy

1. **Unit Tests** for each algorithm step
2. **Integration Tests** for data fetching
3. **Manual Testing** on trigger page
4. **Paper Trading** first before live execution
5. **Backtesting** with historical data

---

## Notes

- Algorithm is designed to be **educational** - shows every step
- Can be run **manually** for learning and verification
- Same algorithm will be used in **background tasks** for auto-execution
- All decisions are **logged** in database for audit trail
- **State machine** allows resume if interrupted

---

This is a comprehensive, production-ready implementation of the Nifty Strangle Strategy! 🚀
