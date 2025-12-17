# Trading Strategies

This document covers the trading philosophy, core rules, and both trading strategies used by mCube.

---

## Trading Philosophy

### Primary Mandate

**Capital preservation takes absolute precedence over aggressive returns.**

### Five Core Tenets

1. **Non-action over risky action** - Not trading is superior to trading with insufficient conviction
2. **Capital protection first** - Preserve principal before seeking growth
3. **Process over outcomes** - Disciplined execution matters more than individual results
4. **Discipline over intelligence** - Systematic adherence beats clever speculation
5. **Consistency compounds** - Small, repeatable wins accumulate into substantial returns

---

## Sacred Position Rules (Non-Negotiable)

These rules are enforced at the code level and cannot be overridden:

### Rule 1: ONE POSITION PER ACCOUNT

```
Before ANY entry decision, verify no active position exists.
If position active → MONITOR only, NO new entries.
This rule is non-negotiable.
```

**Code Enforcement:**
```python
def morning_check(account):
    existing = Position.objects.filter(
        account=account,
        status='ACTIVE'
    ).first()

    if existing:
        return {'action': 'MONITOR', 'allow_new_entry': False}
    return {'action': 'EVALUATE_ENTRY', 'allow_new_entry': True}
```

---

### Rule 2: 50% MARGIN FOR FIRST TRADE

```
Use only 50% of available margin for first trade.
Reserve remaining 50% for:
  • Averaging opportunities (futures)
  • Emergency adjustments (strangle rebalancing)
  • Unexpected margin calls
```

**Code Enforcement:**
```python
def calculate_usable_margin(account):
    available = account.get_available_capital()
    usable = available * Decimal('0.50')
    return usable
```

---

### Rule 3: EXPIRY SELECTION

```
Options:  If < 1 day to expiry  → Skip to next weekly expiry
Futures:  If < 15 days to expiry → Skip to next monthly expiry
```

**Rationale:** Near-expiry instruments have high gamma risk (options) or liquidity issues (futures).

---

### Rule 4: EXIT DISCIPLINE

```
Target hit     → Exit immediately
Stop-loss hit  → Exit immediately
EOD (3:15 PM)  → Exit ONLY if >= 50% of target achieved
               → Otherwise HOLD position (accept overnight risk)
```

---

### Rule 5: FUTURES AVERAGING PROTOCOL

```
Maximum 3 averaging attempts per position
Average 1st: 20% of current balance
Average 2nd: 50% of current balance
Average 3rd: 50% of current balance

Trigger: Position down by 1% from entry
Action: Add equal quantity at current price
Adjust: Tighten stop-loss to 0.5% from new average price
```

---

### Rule 6: STRANGLE DELTA MANAGEMENT

```
Monitor net delta continuously
Alert when |delta| > 300
Generate manual adjustment recommendations
User executes adjustments (NOT automated)
```

---

## Account Configuration

### Kotak Account (Options Trading)

| Parameter | Value |
|-----------|-------|
| Capital | Rs 6 Crores |
| Strategy | Weekly Nifty Strangle |
| Max Margin Usage | 40% of total |
| Initial Trade Margin | 50% of available |
| Max Concurrent Positions | 1 |
| Stop Loss per Position | Rs 1 Lakh |
| Daily Loss Limit | Rs 2 Lakhs |
| Weekly Profit Target | Rs 1.75 Lakhs |
| Monthly Profit Target | Rs 7 Lakhs |

### ICICI Account (Futures Trading)

| Parameter | Value |
|-----------|-------|
| Capital | Rs 1.2 Crores |
| Strategy | LLM-Validated Futures |
| Max Leverage | 5x |
| Max Exposure | Rs 6 Crores |
| Single Position Max | Rs 1.5 Crores |
| Initial Trade Margin | 50% of available |
| Max Concurrent Positions | 1 |
| Per Trade Risk | Rs 60,000 |
| Daily Loss Limit | Rs 1.5 Lakhs |
| Monthly Profit Target | Rs 6 Lakhs |

---

## Strategy 1: Kotak Strangle (Options)

### Overview

**Concept:** Sell out-of-the-money (OTM) Nifty weekly call and put options simultaneously to collect premium while maintaining delta neutrality.

**Instrument:** Nifty 50 Index Options (weekly expiry)
**Direction:** Market-neutral (short strangle)
**Target Return:** Rs 6-8 Lakhs monthly

### Strike Selection Formula

```python
def calculate_strikes(spot_price, days_to_expiry, vix):
    """
    Formula:
        strike_distance = spot × (adjusted_delta / 100) × days_to_expiry

    Base delta: 0.5%
    VIX Adjustments:
        Normal (< 15):    0.5% base
        Elevated (15-18): 0.5% × 1.10 = 0.55%
        High (> 18):      0.5% × 1.20 = 0.60%

    Example:
        Nifty = 24,000
        Days = 4
        VIX = 14 (normal)

        strike_distance = 24,000 × 0.005 × 4 = 480 points
        Call Strike = 24,500 (rounded)
        Put Strike = 23,500 (rounded)
    """

    base_delta = 0.5

    if vix > 18:
        adjusted_delta = base_delta * 1.20
    elif vix > 15:
        adjusted_delta = base_delta * 1.10
    else:
        adjusted_delta = base_delta

    strike_distance = spot_price * (adjusted_delta / 100) * days_to_expiry

    call_strike = round((spot_price + strike_distance) / 100) * 100
    put_strike = round((spot_price - strike_distance) / 100) * 100

    return call_strike, put_strike
```

### Entry Filters (ALL Must Pass)

1. **Global Market Stability**
   - SGX Nifty change < ±0.5%
   - Nasdaq/Dow change < ±1.0%

2. **Recent Nifty Movement**
   - Yesterday change < ±1.0%
   - 3-day change < ±2.0%

3. **Economic Calendar**
   - No major events in next 5 days

4. **Market Regime**
   - Not at Bollinger Band extremes
   - India VIX < 20

5. **Position Check**
   - No active position exists

### Entry Timing

- **Days:** Monday or Tuesday (gives 4-5 days to expiry)
- **Time:** 10:00 AM - 11:30 AM IST

### Exit Rules

| Condition | Action |
|-----------|--------|
| Stop-loss hit (100% loss) | Exit immediately |
| Target hit (70% profit) | Exit immediately |
| Thursday 3:15 PM | Exit only if >= 50% target |
| Friday EOD | Mandatory exit |

### Delta Management

```python
def monitor_delta(position):
    """
    Calculate and monitor net delta.
    Alert when |net_delta| > 300.
    Generate adjustment recommendation.
    """

    call_delta = calculate_option_delta(position.call_strike, 'CE')
    put_delta = calculate_option_delta(position.put_strike, 'PE')

    # For short strangle: net_delta = put_delta - call_delta
    net_delta = put_delta - call_delta

    if abs(net_delta) > 300:
        send_telegram_alert(
            f"Delta Alert: Net delta = {net_delta}\n"
            f"Consider adjustment"
        )
```

---

## Strategy 2: ICICI Futures (Directional)

### Overview

**Concept:** Directional futures trading based on multi-factor quantitative screening validated by LLM before execution.

**Instruments:** Top 50 liquid stock futures
**Direction:** Long or Short (directional)
**Target Return:** Rs 4-6 Lakhs monthly

### Stock Screening Process

```
1. Liquidity Filter → Top 50 stocks by volume
       ↓
2. OI Analysis → Primary signal from futures + options OI
       ↓
3. Sector Analysis → ALL timeframes (3D, 7D, 21D) must align
       ↓
4. Technical Analysis → Support/resistance, RSI, trend
       ↓
5. Scoring → Minimum 65/100 composite score
       ↓
6. LLM Validation → Final gate with human approval
```

### OI Analysis (Primary Signal)

```python
def analyze_oi(symbol):
    """
    OI Interpretation:
        Long Buildup:   OI ↑ + Price ↑ → BULLISH
        Short Buildup:  OI ↑ + Price ↓ → BEARISH
        Short Covering: OI ↓ + Price ↑ → BULLISH
        Long Unwinding: OI ↓ + Price ↓ → BEARISH

    Also uses Put-Call Ratio (PCR):
        PCR > 1.3 → Bullish (strong put base)
        PCR < 0.7 → Bearish (strong call base)
    """

    oi_change = get_oi_change_pct(symbol)
    price_change = get_price_change_pct(symbol)

    if oi_change > 5 and price_change > 0:
        return 'BULLISH', 'Long buildup'
    elif oi_change > 5 and price_change < 0:
        return 'BEARISH', 'Short buildup'
    elif oi_change < -5 and price_change > 0:
        return 'BULLISH', 'Short covering'
    elif oi_change < -5 and price_change < 0:
        return 'BEARISH', 'Long unwinding'
    else:
        return 'NEUTRAL', 'No significant OI change'
```

### Sector Analysis (Critical Filter)

```python
def analyze_sector(symbol):
    """
    CRITICAL RULE:
        For LONG:  ALL timeframes (3D, 7D, 21D) must be POSITIVE
        For SHORT: ALL timeframes (3D, 7D, 21D) must be NEGATIVE
        Mixed signals → DON'T TRADE
    """

    sector = get_stock_sector(symbol)

    perf_3d = get_sector_performance(sector, days=3)
    perf_7d = get_sector_performance(sector, days=7)
    perf_21d = get_sector_performance(sector, days=21)

    if perf_3d > 0 and perf_7d > 0 and perf_21d > 0:
        return 'STRONG_BULLISH', True, False  # allow_long, allow_short
    elif perf_3d < 0 and perf_7d < 0 and perf_21d < 0:
        return 'STRONG_BEARISH', False, True
    else:
        return 'MIXED', False, False  # DON'T TRADE
```

### LLM Validation

```python
def validate_with_llm(candidate):
    """
    Final validation gate using local LLM (Ollama).
    Minimum confidence: 70%
    Always requires human approval.
    """

    prompt = f"""
    Evaluate this trade:
    Symbol: {candidate.symbol}
    Direction: {candidate.direction}
    OI Signal: {candidate.oi_signal}
    Sector Trend: {candidate.sector_trend}
    Technical Score: {candidate.tech_score}

    Provide confidence score (0-100) and recommendation.
    """

    response = ollama_client.generate(prompt)
    confidence = parse_confidence(response)

    if confidence >= 70:
        send_telegram_for_approval(candidate, response)
    else:
        reject_candidate(candidate, "LLM confidence too low")
```

### Position Sizing

```python
def calculate_futures_position_size(account, symbol, direction):
    """
    Position sizing based on:
    1. 50% of available margin
    2. Risk-based sizing (0.5% SL with Rs 60K max loss)
    3. Single position max (Rs 1.5 Cr)
    """

    available = account.margin_available * Decimal('0.50')

    ltp = get_ltp(symbol)
    lot_size = get_lot_size(symbol)
    margin_per_lot = get_margin_per_lot(symbol)

    # Risk-based: Max Rs 60K loss with 0.5% SL
    max_loss = 60000
    sl_pct = 0.005
    risk_based_lots = max_loss / (ltp * lot_size * sl_pct)

    # Margin-based
    margin_based_lots = available / margin_per_lot

    # Take minimum
    final_lots = int(min(risk_based_lots, margin_based_lots))

    return final_lots
```

### Exit Rules

| Condition | Action |
|-----------|--------|
| Stop-loss hit (0.5%) | Exit immediately |
| Target hit (1.0%) | Exit immediately |
| EOD | Exit only if >= 50% target |
| Averaging trigger (1% loss) | Consider adding (max 3x) |

---

## Risk Management Framework

### Four-Level Risk Hierarchy

```
Level 1: Position-Level
    • Stop-loss enforcement
    • Target achievement
    • Position sizing limits
    • Expiry checks

Level 2: Account-Level
    • Daily loss limits
    • Weekly loss limits
    • Monthly targets
    • ONE POSITION rule

Level 3: System-Level
    • Max drawdown monitoring (15%)
    • Circuit breakers
    • Account deactivation
    • Emergency close all

Level 4: Adaptive Risk
    • Learning-based adjustments
    • Pattern-based sizing
    • Win rate consideration
```

### Circuit Breaker Triggers

| Trigger | Action |
|---------|--------|
| Daily loss > limit | Pause trading for day |
| Weekly loss > limit | Pause trading for week |
| Drawdown > 15% | Deactivate account |

---

## Daily Routine

### Morning (8:30 AM - 9:00 AM)

1. Check global market cues (SGX, US)
2. Review overnight news
3. Check existing positions
4. Verify broker connectivity

### Market Hours (9:15 AM - 3:30 PM)

1. Position monitoring (continuous)
2. Strategy evaluation (10:00 AM for strangle)
3. Risk checks (every minute)
4. Alerts via Telegram

### Evening (4:00 PM - 5:00 PM)

1. Daily P&L report
2. Position review
3. Next day preparation

---

## Quick Reference

### Entry Checklist

- [ ] No active position exists
- [ ] Within entry time window
- [ ] All filters passed
- [ ] Expiry > minimum days
- [ ] Margin calculated at 50%
- [ ] LLM approved (futures only)
- [ ] Human approval received

### Exit Checklist

- [ ] Check stop-loss first
- [ ] Check target second
- [ ] If EOD, check 50% profit rule
- [ ] Update position status
- [ ] Record P&L
- [ ] Send notification

---

*For detailed formulas and implementation, see [design/mcube-ai.design.md](design/mcube-ai.design.md)*
