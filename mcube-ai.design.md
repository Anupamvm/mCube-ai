# mCube: Multi-Strategy F&O Trading System
## Complete System Design & Implementation Plan

**Version:** 2.0
**Date:** November 2024
**Capital:** ₹7.2 Crores (Kotak: ₹6Cr Options | ICICI: ₹1.2Cr Futures)
**Tech Stack:** Django 4.2+ | SQLite | Redis | Celery | Bootstrap 5 | Ollama
**Target Returns:** ₹12-15L monthly (1.7-2.1% monthly, 20-25% annually)

---

## Table of Contents

### Part I: System Foundation
1. [Trading Philosophy & Core Principles](#1-trading-philosophy--core-principles)
2. [System Architecture](#2-system-architecture)
3. [Account Configuration](#3-account-configuration)
4. [Critical Business Rules](#4-critical-business-rules)

### Part II: Trading Strategies
5. [Kotak Strangle Strategy](#5-kotak-strangle-strategy)
6. [ICICI Futures Strategy](#6-icici-futures-strategy)
7. [Risk Management Framework](#7-risk-management-framework)

### Part III: Technical Implementation
8. [Django Project Structure](#8-django-project-structure)
9. [Database Models](#9-database-models)
10. [Broker API Integration](#10-broker-api-integration)
11. [Background Task Automation](#11-background-task-automation)

### Part IV: Advanced Features
12. [Self-Learning System](#12-self-learning-system)
13. [Pattern Recognition](#13-pattern-recognition)
14. [LLM-Based Trade Validation](#14-llm-based-trade-validation)

### Part V: Deployment & Operations
15. [Configuration & Setup](#15-configuration--setup)
16. [Testing Strategy](#16-testing-strategy)
17. [Deployment Guide](#17-deployment-guide)

### Part VI: Implementation Plan
18. [Phase-by-Phase Implementation Plan](#18-phase-by-phase-implementation-plan)
19. [Development Checklist](#19-development-checklist)
20. [Quality Assurance Criteria](#20-quality-assurance-criteria)

---

# Part I: System Foundation

<a name="1-trading-philosophy--core-principles"></a>
## 1. Trading Philosophy & Core Principles

### Primary Mandate
**Capital preservation takes absolute precedence over aggressive returns.**

### Five Core Tenets
1. **Non-action over risky action** — Not trading is superior to trading with insufficient conviction
2. **Capital protection first** — Preserve principal before seeking growth
3. **Process over outcomes** — Disciplined execution matters more than individual results
4. **Discipline over intelligence** — Systematic adherence beats clever speculation
5. **Consistency compounds** — Small, repeatable wins accumulate into substantial returns

### Sacred Position Rules

```
✅ ONE POSITION PER ACCOUNT AT ANY TIME
   - Before ANY entry decision, verify no active position exists
   - If position active → Monitor only, NO new entries
   - This rule is non-negotiable and enforced at code level

✅ 50% MARGIN USAGE FOR INITIAL TRADE
   - Use only 50% of available margin for the first trade
   - Reserve remaining 50% for:
     * Averaging opportunities (futures only)
     * Emergency adjustments (strangle rebalancing)
     * Unexpected margin calls

✅ EXPIRY SELECTION DISCIPLINE
   - Options: If < 1 day to expiry → skip to next weekly expiry
   - Futures: If < 15 days to expiry → skip to next monthly expiry
   - Never trade instruments near expiry due to gamma risk

✅ EXIT DISCIPLINE
   - Target hit → Exit immediately
   - Stop-loss hit → Exit immediately
   - EOD (3:15 PM) → Exit ONLY if minimum profit threshold achieved (50%)
   - If minimum profit NOT achieved → Hold position (accept overnight risk)

✅ FUTURES AVERAGING PROTOCOL
   - Maximum 3 averaging attempts per position
   - Average 1st only 20% of current balance
   - Average 2nd 50% of current balance margin
   - Average 3rd 50% of current balance margin
   - Trigger: Position down by 1% from entry
   - Action: Add equal quantity at current price
   - Adjust: Tighten stop-loss to 0.5% from new average price

✅ STRANGLE DELTA MANAGEMENT
   - Monitor net delta continuously
   - Alert when |delta| > 300
   - Generate manual adjustment recommendations
   - User executes adjustments (not automated)
```

---

<a name="2-system-architecture"></a>
## 2. System Architecture

### High-Level System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    mCube Django Application                  │
│                      (Standalone System)                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │      Frontend (Django Templates + Bootstrap 5)        │  │
│  │   • Real-time Dashboard (P&L, positions, alerts)      │  │
│  │   • Trade Approval Interface                          │  │
│  │   • Strategy Configuration Panel                      │  │
│  │   • Analytics & Performance Charts                    │  │
│  └───────────────────────────────────────────────────────┘  │
│                           ↕                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           Django Backend (9 Applications)             │  │
│  │                                                         │  │
│  │  • core/        Base models, utilities, constants     │  │
│  │  • accounts/    Broker accounts (Kotak, ICICI) , data accounts (trendlyne)        │  │
│  │  • strategies/  Trading strategy logic                │  │
│  │  • positions/   Position tracking & monitoring        │  │
│  │  • orders/      Order management & execution          │  │
│  │  • risk/        Risk limits & circuit breakers        │  │
│  │  • data/        Market data, OI, news aggregation     │  │
│  │  • llm/         LLM-based validation (Ollama)         │  │
│  │  • analytics/   P&L tracking, learning engine         │  │
│  │  • alerts/      Telegram    │  │
│  └───────────────────────────────────────────────────────┘  │
│                           ↕                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │          Celery Workers (Background Tasks)            │  │
│  │   • Market data sync (every 1 minute, 9AM-3:30PM)     │  │
│  │   • Position monitoring (every 5 seconds)             │  │
│  │   • Strategy evaluation (scheduled)                   │  │
│  │   • Daily P&L reports (EOD)                           │  │
│  └───────────────────────────────────────────────────────┘  │
│                           ↕                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Data Storage (Local)                     │  │
│  │   • SQLite     All application data                   │  │
│  │   • Redis      Cache & Celery message broker          │  │
│  │   • ChromaDB   Vector store for trading knowledge     │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                     External Services                        │
│  • Kotak Neo API          Option chain, order placement     │
│  • ICICI Breeze API       Futures data, order execution     │
│  • Trendlyne scraping     Stock fundamentals, sector data   │
│  • NSE/BSE APIs           Live market data, indices         │
│  • News APIs              Market sentiment, events          │
│  • Ollama                 Local LLM server (DeepSeek)       │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Framework** | Django 4.2+ | Web application framework |
| **Database** | SQLite | Embedded database (development & production) |
| **Cache** | Redis 5.0+ | Caching and Celery message broker |
| **Task Queue** | Celery 5.3+ | Asynchronous task execution |
| **Frontend** | Bootstrap 5 + HTMX | Responsive UI with real-time updates |
| **AI/ML** | Ollama (DeepSeek-Coder) | Local LLM for trade validation |
| **Vector DB** | ChromaDB | RAG system for trading knowledge |
| **APIs** | Kotak Neo, ICICI Breeze | Broker integration |
| **Alerts** | Telegram Bot, Twilio | Multi-channel notifications |

---

<a name="3-account-configuration"></a>
## 3. Account Configuration

### Kotak Securities Account (₹6 Crores — Options Trading)

```python
KOTAK_ACCOUNT_CONFIG = {
    'broker': 'KOTAK',
    'allocated_capital': 6_00_00_000,  # ₹6 Crores
    'strategy': 'WEEKLY_NIFTY_STRANGLE',

    'risk_parameters': {
        'max_margin_usage': 0.40,              # Use only 40% of total capital
        'initial_margin_for_first_trade': 0.50, # 50% of available (not total)
        'max_concurrent_positions': 1,          # ONE POSITION RULE
        'stop_loss_per_position': 1_00_000,    # ₹1 Lakh
        'daily_loss_limit': 2_00_000,          # ₹2 Lakhs
        'weekly_profit_target': 1_75_000,      # ₹1.75 Lakhs
        'monthly_profit_target': 7_00_000,     # ₹7 Lakhs
    },

    'strategy_parameters': {
        'instrument': 'NIFTY',
        'base_delta_pct': 0.50,                # 0.5% base delta for strike selection
        'min_days_to_expiry': 1,               # Skip if < 1 day
        'min_profit_pct_to_exit': 50.0,        # Only exit EOD if ≥ 50% profit
        'exit_day': 'THURSDAY',                # Primary exit day
        'exit_time': '15:15',                  # 3:15 PM IST
        'delta_rebalance_threshold': 300,      # Alert if |net_delta| > 300
    }
}
```

**Strategy:** Sell out-of-the-money (OTM) weekly Nifty call and put options simultaneously to collect premium while maintaining delta neutrality.

**Target Return:** ₹6-8 Lakhs monthly (1.0-1.3% on ₹6Cr capital)

---

### ICICI Securities Account (₹1.2 Crores — Futures Trading)

```python
ICICI_ACCOUNT_CONFIG = {
    'broker': 'ICICI',
    'allocated_capital': 1_20_00_000,  # ₹1.2 Crores
    'max_leverage': 5,                  # Can take up to ₹6 Cr exposure
    'strategy': 'LLM_VALIDATED_FUTURES',

    'risk_parameters': {
        'max_total_exposure': 6_00_00_000,     # ₹6 Crores max exposure
        'single_position_max': 1_50_00_000,    # ₹1.5 Crores per position
        'max_concurrent_positions': 1,          # ONE POSITION RULE
        'initial_margin_for_first_trade': 0.50, # 50% of available margin
        'per_trade_risk': 60_000,              # ₹60,000 max loss per trade
        'daily_loss_limit': 1_50_000,          # ₹1.5 Lakhs
        'weekly_profit_target': 1_50_000,      # ₹1.5 Lakhs
        'monthly_profit_target': 6_00_000,     # ₹6 Lakhs
    },

    'strategy_parameters': {
        'min_days_to_expiry': 15,              # Skip if < 15 days
        'default_stop_loss_pct': 0.005,        # 0.5%
        'default_target_pct': 0.01,            # 1.0%
        'min_risk_reward_ratio': 2.0,          # Minimum 1:2 RR
        'min_profit_pct_to_exit': 50.0,        # Only exit EOD if ≥ 50% profit

        # Averaging parameters
        'allow_averaging': True,
        'max_average_attempts': 2,             # Maximum 2 averaging attempts
        'average_trigger_loss_pct': 1.0,       # Average when down 1%

        # LLM validation
        'min_llm_confidence': 0.70,            # 70% minimum confidence
        'require_human_approval': True,         # Always require manual approval
    }
}
```

**Strategy:** Directional futures trading based on multi-factor quantitative screening (OI analysis, sector strength, technical indicators) validated by local LLM.

**Target Return:** ₹6 Lakhs monthly (~5% on margin, 0.5% on exposure)

---

<a name="4-critical-business-rules"></a>
## 4. Critical Business Rules

### Morning Decision Flow (9:00 AM - 11:30 AM)

```python
def morning_check(account):
    """
    CRITICAL: Check existing position FIRST before any entry evaluation

    Morning Routine:
    1. Check if an active position exists for this account
    2. If YES → Enter MONITOR-ONLY mode, block all new entries
    3. If NO → Proceed to evaluate entry conditions

    Returns:
        dict: {'action': str, 'position': Position|None, 'allow_new_entry': bool}
    """

    # RULE 1: Check for existing active position
    existing_position = Position.objects.filter(
        account=account,
        status='ACTIVE'
    ).first()

    if existing_position:
        logger.info(f"✋ Active position exists: {existing_position.instrument}")
        logger.info("📊 MONITOR MODE - No new entry permitted")
        return {
            'action': 'MONITOR',
            'position': existing_position,
            'allow_new_entry': False
        }

    logger.info("✅ No active position - Entry evaluation permitted")
    return {
        'action': 'EVALUATE_ENTRY',
        'position': None,
        'allow_new_entry': True
    }
```

### Margin Management Rule

```python
def calculate_usable_margin(account):
    """
    CRITICAL: Use only 50% of available margin for first trade

    Rationale:
    - Reserve 50% buffer for averaging opportunities (futures)
    - Reserve 50% buffer for emergency adjustments (strangles)
    - Reserve 50% buffer for unexpected margin requirements
    - Never deploy 100% of capital to maintain flexibility

    Returns:
        Decimal: Amount of margin usable for initial position
    """

    available_margin = account.get_available_capital()

    # Use 50% for first trade, reserve 50%
    usable_margin = available_margin * Decimal('0.50')
    reserved_margin = available_margin - usable_margin

    logger.info(f"Available Capital: ₹{available_margin:,.0f}")
    logger.info(f"Using (50%):       ₹{usable_margin:,.0f}")
    logger.info(f"Reserved (50%):    ₹{reserved_margin:,.0f}")

    return usable_margin
```

### Expiry Selection Rules

```python
def select_expiry_for_options(instrument='NIFTY'):
    """
    CRITICAL: Don't trade options with < 1 day to expiry

    Gamma risk explodes near expiry. Skip to next weekly expiry if current
    expiry is less than 1 day away.
    """
    from datetime import date

    current_expiry = get_current_weekly_expiry(instrument)
    days_to_expiry = (current_expiry - date.today()).days

    if days_to_expiry < 1:
        selected_expiry = get_next_weekly_expiry(instrument)
        days_remaining = (selected_expiry - date.today()).days

        logger.warning(f"⚠️ Only {days_to_expiry} days to current expiry")
        logger.info(f"✅ Using NEXT WEEK expiry: {selected_expiry} ({days_remaining} days)")

        return selected_expiry

    logger.info(f"✅ Current expiry acceptable: {current_expiry} ({days_to_expiry} days)")
    return current_expiry


def select_expiry_for_futures(symbol):
    """
    CRITICAL: Don't trade futures with < 15 days to expiry

    Near-month futures lose liquidity and spread widens. Skip to next monthly
    expiry if current expiry is less than 15 days away.
    """
    from datetime import date

    current_expiry = get_current_month_expiry(symbol)
    days_to_expiry = (current_expiry - date.today()).days

    if days_to_expiry < 15:
        selected_expiry = get_next_month_expiry(symbol)
        days_remaining = (selected_expiry - date.today()).days

        logger.warning(f"⚠️ Only {days_to_expiry} days to current expiry")
        logger.info(f"✅ Using NEXT MONTH expiry: {selected_expiry} ({days_remaining} days)")

        return selected_expiry

    logger.info(f"✅ Current expiry acceptable: {current_expiry} ({days_to_expiry} days)")
    return current_expiry
```

---

# Part II: Trading Strategies

<a name="5-kotak-strangle-strategy"></a>
## 5. Kotak Strangle Strategy

### Strategy Overview

**Concept:** Sell out-of-the-money (OTM) Nifty weekly call and put options simultaneously to collect premium income while maintaining delta neutrality (market-neutral position).

**Instrument:** Nifty 50 Index Options (weekly expiry)
**Direction:** Market-neutral (short strangle)
**Target Return:** ₹6-8 Lakhs monthly (1.0-1.3% on ₹6 Crore capital)
**Risk Profile:** Defined maximum loss (100% of premium), undefined upside (premium decay)

### Core Strike Selection Formula

```python
def calculate_strikes(spot_price, days_to_expiry, vix):
    """
    Calculate OTM call and put strikes for short strangle

    Formula:
        strike_distance = spot × (adjusted_delta / 100) × days_to_expiry

    Where adjusted_delta adjusts for volatility regime:
        - Normal VIX (< 15): 0.5% base delta
        - Elevated VIX (15-18): 0.5% × 1.10 = 0.55%
        - High VIX (> 18): 0.5% × 1.20 = 0.6%

    Example:
        Nifty = 24,000
        Days = 4
        VIX = 14 (normal)

        strike_distance = 24,000 × 0.005 × 4 = 480 points
        Call Strike = 24,480 → Round to 24,500
        Put Strike = 23,520 → Round to 23,500
    """

    base_delta = 0.5  # 0.5% base delta distance

    # Adjust delta based on volatility regime
    if vix > 18:
        adjusted_delta = base_delta * 1.20
        reason = "High VIX - increasing strike distance for safety"
    elif vix > 15:
        adjusted_delta = base_delta * 1.10
        reason = "Elevated VIX - slight increase in strike distance"
    else:
        adjusted_delta = base_delta
        reason = "Normal VIX - standard strike distance"

    logger.info(f"Adjusted Delta: {adjusted_delta}% ({reason})")

    # Calculate strike distance in points
    strike_distance = spot_price * (adjusted_delta / 100) * days_to_expiry

    # Calculate raw strikes
    call_strike_raw = spot_price + strike_distance
    put_strike_raw = spot_price - strike_distance

    # Round to nearest 100 (Nifty strike interval)
    call_strike = round(call_strike_raw / 100) * 100
    put_strike = round(put_strike_raw / 100) * 100

    return {
        'call_strike': int(call_strike),
        'put_strike': int(put_strike),
        'strike_distance': strike_distance,
        'adjusted_delta': adjusted_delta
    }
```

### Entry Filters (ALL Must Pass)

```python
def run_entry_filters():
    """
    Execute ALL entry filters for strangle strategy

    Filter Logic: ALL must pass (conservative approach)
    If ANY filter fails, skip the trade entirely
    """

    filters_passed = []
    filters_failed = []

    # FILTER 1: Global Market Stability
    sgx_change = get_sgx_nifty_change()
    nasdaq_change = get_nasdaq_change()
    dow_change = get_dow_jones_change()

    if abs(sgx_change) > 0.5:
        filters_failed.append(f"SGX Nifty moved {sgx_change:.2f}% (limit: ±0.5%)")
    elif abs(nasdaq_change) > 1.0 or abs(dow_change) > 1.0:
        filters_failed.append("US markets too volatile (limit: ±1.0%)")
    else:
        filters_passed.append("Global markets stable")

    # FILTER 2: Recent Nifty Price Movement
    yesterday_change = get_nifty_change(days=1)
    three_day_change = get_nifty_change(days=3)

    if abs(yesterday_change) > 1.0:
        filters_failed.append(f"Nifty moved {yesterday_change:.2f}% yesterday")
    elif abs(three_day_change) > 2.0:
        filters_failed.append(f"Nifty moved {three_day_change:.2f}% in 3 days")
    else:
        filters_passed.append("Nifty price movement within acceptable range")

    # FILTER 3: Economic Event Calendar
    events = get_events_next_n_days(5)
    major_events = [e for e in events if e['importance'] == 'HIGH']

    if major_events:
        filters_failed.append(f"Major event upcoming: {major_events[0]['title']}")
    else:
        filters_passed.append("No major economic events in next 5 days")

    # FILTER 4: Market Regime Check
    vix = get_india_vix()
    current_price = get_nifty_spot()
    bb_upper, bb_lower = get_bollinger_bands(period=20, std_dev=2)

    if current_price > bb_upper or current_price < bb_lower:
        filters_failed.append("Nifty at Bollinger Band extreme")
    elif vix > 20:
        filters_failed.append(f"India VIX too high: {vix:.1f}")
    else:
        filters_passed.append("Market regime favorable")

    # FILTER 5: Existing Position Check (ONE POSITION RULE)
    if has_active_position():
        filters_failed.append("Active position already exists")
    else:
        filters_passed.append("No existing position - slot available")

    return filters_passed, filters_failed
```

---

<a name="6-icici-futures-strategy"></a>
## 6. ICICI Futures Strategy

### Strategy Overview

**Concept:** Directional futures trading based on multi-factor quantitative screening (OI analysis + sector strength + technical indicators) validated by local LLM before execution.

**Instruments:** Top 50 liquid stock futures (Nifty/Bank Nifty/individual stocks)
**Direction:** Long or Short (directional)
**Target Return:** ₹6 Lakhs monthly (~5% on margin, 0.5% on exposure)
**Risk Profile:** Defined stop-loss, averaging allowed (max 2 attempts)

### Stock Screening Process

The screening process uses a multi-layered approach:

1. **Liquidity Filter** → Top 50 stocks by volume
2. **OI Analysis** → Primary signal from futures + options OI
3. **Sector Analysis** → ALL timeframes (3D, 7D, 21D) must align
4. **Technical Analysis** → Support/resistance, RSI, trend
5. **Scoring** → Minimum 65/100 composite score
6. **LLM Validation** → Final gate with human approval

### OI Analysis (Primary Signal Generator)

```python
def analyze_oi(symbol):
    """
    Analyze Open Interest (OI) to generate primary trading signal

    OI Interpretation:
    1. Long Buildup:     OI ↑ + Price ↑ → BULLISH
    2. Short Buildup:    OI ↑ + Price ↓ → BEARISH
    3. Short Covering:   OI ↓ + Price ↑ → BULLISH
    4. Long Unwinding:   OI ↓ + Price ↓ → BEARISH

    Also analyzes options OI via Put-Call Ratio (PCR):
    - PCR > 1.3 → Bullish (strong put base)
    - PCR < 0.7 → Bearish (strong call base)
    """

    # Get futures OI
    futures_oi = get_futures_oi(symbol)

    oi_change_pct = (
        (futures_oi['current'] - futures_oi['previous']) /
        futures_oi['previous'] * 100
    )

    price_change_pct = (
        (futures_oi['ltp'] - futures_oi['prev_close']) /
        futures_oi['prev_close'] * 100
    )

    # Interpret signal based on OI + price movement
    if oi_change_pct > 5 and price_change_pct > 0:
        futures_signal = 'BULLISH'
        futures_reason = f'Long buildup: OI +{oi_change_pct:.1f}%, Price +{price_change_pct:.1f}%'
    elif oi_change_pct > 5 and price_change_pct < 0:
        futures_signal = 'BEARISH'
        futures_reason = f'Short buildup: OI +{oi_change_pct:.1f}%, Price {price_change_pct:.1f}%'
    elif oi_change_pct < -5 and price_change_pct > 0:
        futures_signal = 'BULLISH'
        futures_reason = f'Short covering: OI {oi_change_pct:.1f}%, Price +{price_change_pct:.1f}%'
    elif oi_change_pct < -5 and price_change_pct < 0:
        futures_signal = 'BEARISH'
        futures_reason = f'Long unwinding: OI {oi_change_pct:.1f}%, Price {price_change_pct:.1f}%'
    else:
        futures_signal = 'NEUTRAL'
        futures_reason = f'No significant OI change'

    # Options OI analysis
    options_oi = get_options_oi_chain(symbol)
    total_call_oi = sum(strike['oi'] for strike in options_oi['calls'])
    total_put_oi = sum(strike['oi'] for strike in options_oi['puts'])
    pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0

    if pcr > 1.3:
        options_signal = 'BULLISH'
    elif pcr < 0.7:
        options_signal = 'BEARISH'
    else:
        options_signal = 'NEUTRAL'

    # Combined verdict
    signals = [futures_signal, options_signal]

    if signals.count('BULLISH') >= 2:
        overall_signal = 'BULLISH'
        confidence = 0.85
    elif signals.count('BEARISH') >= 2:
        overall_signal = 'BEARISH'
        confidence = 0.85
    else:
        overall_signal = futures_signal
        confidence = 0.65

    return {
        'signal': overall_signal,
        'confidence': confidence,
        'futures_reason': futures_reason,
        'pcr': pcr
    }
```

### Sector Analysis (CRITICAL Filter)

```python
def analyze_sector(symbol):
    """
    Analyze sector strength across multiple timeframes

    CRITICAL RULE:
    - For LONG: ALL timeframes (3D, 7D, 21D) must be POSITIVE
    - For SHORT: ALL timeframes (3D, 7D, 21D) must be NEGATIVE
    - Mixed signals → DON'T TRADE (wait for clarity)

    This is a NON-NEGOTIABLE filter.
    """

    sector = get_stock_sector(symbol)
    sector_index = get_sector_index(sector)

    # Multi-timeframe performance
    perf_3d = get_performance(sector_index, days=3)
    perf_7d = get_performance(sector_index, days=7)
    perf_21d = get_performance(sector_index, days=21)

    # For LONG: ALL must be positive
    if perf_3d > 0 and perf_7d > 0 and perf_21d > 0:
        verdict = 'STRONG_BULLISH'
        allow_long = True
        allow_short = False
        reason = f'All timeframes positive - strong sector tailwind'

    # For SHORT: ALL must be negative
    elif perf_3d < 0 and perf_7d < 0 and perf_21d < 0:
        verdict = 'STRONG_BEARISH'
        allow_long = False
        allow_short = True
        reason = f'All timeframes negative - strong sector headwind'

    # Mixed signals → DON'T TRADE
    else:
        verdict = 'MIXED'
        allow_long = False
        allow_short = False
        reason = f'Mixed sector signals - no clear trend'

    return {
        'verdict': verdict,
        'allow_long': allow_long,
        'allow_short': allow_short,
        'reason': reason,
        'performance': {'3d': perf_3d, '7d': perf_7d, '21d': perf_21d}
    }
```

---

<a name="7-risk-management-framework"></a>
## 7. Risk Management Framework

### Multi-Level Risk Controls

The system implements a four-level risk management hierarchy:

1. **Position-Level Risk**
   - Stop-loss enforcement
   - Target achievement
   - Position sizing limits
   - Expiry checks

2. **Account-Level Risk**
   - Daily loss limits
   - Weekly loss limits
   - Monthly profit targets
   - ONE POSITION RULE enforcement

3. **System-Level Risk**
   - Maximum drawdown monitoring (15%)
   - Circuit breakers
   - Account deactivation on breach
   - Emergency position closure

4. **Adaptive Risk**
   - Learning-based adjustments
   - Pattern-based risk sizing
   - Win rate consideration
   - Profit factor weighting

---

# Part III: Technical Implementation

<a name="8-django-project-structure"></a>
## 8. Django Project Structure

```
mcube/
├── manage.py
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── README.md
│
├── config/                              # Django project settings
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── celery.py
│
├── apps/                                # Django applications (9 apps)
│   ├── core/                            # Core utilities
│   ├── accounts/                        # Broker accounts
│   ├── strategies/                      # Trading strategies
│   ├── positions/                       # Position tracking
│   ├── orders/                          # Order management
│   ├── risk/                            # Risk management
│   ├── data/                            # Market data
│   ├── llm/                             # LLM integration
│   ├── analytics/                       # Analytics & learning
│   └── alerts/                          # Notifications
│
├── templates/                           # Global templates
├── static/                              # Static assets
├── data/                                # Data storage
│   ├── db.sqlite3
│   ├── chromadb/
│   └── backups/
└── logs/                                # Application logs
```

---

<a name="9-database-models"></a>
## 9. Database Models

### Core Models

```python
# apps/core/models.py
from django.db import models

class TimeStampedModel(models.Model):
    """Abstract base model with timestamps"""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']
```

### Account Models

```python
# apps/accounts/models.py

class BrokerAccount(TimeStampedModel):
    """Broker account model"""

    BROKER_CHOICES = [
        ('KOTAK', 'Kotak Securities'),
        ('ICICI', 'ICICI Securities'),
    ]

    broker = models.CharField(max_length=20, choices=BROKER_CHOICES)
    account_number = models.CharField(max_length=50, unique=True)
    account_name = models.CharField(max_length=100)
    allocated_capital = models.DecimalField(max_digits=15, decimal_places=2)

    is_active = models.BooleanField(default=True)
    is_paper_trading = models.BooleanField(default=True)

    max_daily_loss = models.DecimalField(max_digits=15, decimal_places=2)
    max_weekly_loss = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = 'broker_accounts'

    def get_available_capital(self):
        """Calculate available capital not deployed in positions"""
        from apps.positions.models import Position

        deployed = Position.objects.filter(
            account=self, status='ACTIVE'
        ).aggregate(total=models.Sum('margin_used'))['total'] or Decimal('0')

        return self.allocated_capital - deployed
```

### Position Models

```python
# apps/positions/models.py

class Position(TimeStampedModel):
    """
    Position model

    CRITICAL: ONE POSITION PER ACCOUNT enforced at application level
    """

    DIRECTION_CHOICES = [
        ('LONG', 'Long'),
        ('SHORT', 'Short'),
        ('NEUTRAL', 'Neutral'),  # For strangles
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
    ]

    account = models.ForeignKey('accounts.BrokerAccount', on_delete=models.CASCADE)
    strategy_type = models.CharField(max_length=50)
    instrument = models.CharField(max_length=100)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)

    quantity = models.IntegerField()
    entry_price = models.DecimalField(max_digits=15, decimal_places=2)
    current_price = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    stop_loss = models.DecimalField(max_digits=15, decimal_places=2)
    target = models.DecimalField(max_digits=15, decimal_places=2)

    # Strangle-specific
    call_strike = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    put_strike = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    premium_collected = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_delta = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    expiry_date = models.DateField()
    margin_used = models.DecimalField(max_digits=15, decimal_places=2)
    entry_value = models.DecimalField(max_digits=15, decimal_places=2)

    status = models.CharField(max_length=20, default='ACTIVE', choices=STATUS_CHOICES)
    entry_time = models.DateTimeField(auto_now_add=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    exit_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    realized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    unrealized_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # Averaging (futures only)
    averaging_count = models.IntegerField(default=0)
    partial_booked = models.BooleanField(default=False)

    class Meta:
        db_table = 'positions'
        ordering = ['-entry_time']
        indexes = [
            models.Index(fields=['account', 'status']),
        ]

    @classmethod
    def has_active_position(cls, account):
        """Check if active position exists - ONE POSITION RULE"""
        return cls.objects.filter(account=account, status='ACTIVE').exists()

    @classmethod
    def get_active_position(cls, account):
        """Get active position"""
        return cls.objects.filter(account=account, status='ACTIVE').first()
```

### Strategy Models

```python
# apps/strategies/models.py

class StrategyConfig(TimeStampedModel):
    """Strategy configuration"""

    account = models.ForeignKey('accounts.BrokerAccount', on_delete=models.CASCADE)
    strategy_type = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    # Position rules
    initial_margin_usage_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=50.00,
        help_text="Use 50% margin for first trade"
    )
    min_profit_pct_to_exit = models.DecimalField(
        max_digits=5, decimal_places=2, default=50.00
    )

    # Kotak specific
    base_delta_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0.50)
    min_days_to_expiry = models.IntegerField(default=1)

    # ICICI specific
    min_days_to_future_expiry = models.IntegerField(default=15)
    allow_averaging = models.BooleanField(default=True)
    max_average_attempts = models.IntegerField(default=2)
    average_down_threshold_pct = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)

    class Meta:
        db_table = 'strategy_configs'


class StrategyLearning(TimeStampedModel):
    """Self-learning system to track pattern performance"""

    strategy_type = models.CharField(max_length=50)
    pattern_name = models.CharField(max_length=100)
    pattern_description = models.TextField()

    entry_conditions = models.JSONField(default=dict)
    market_conditions = models.JSONField(default=dict)

    times_occurred = models.IntegerField(default=0)
    times_profitable = models.IntegerField(default=0)

    avg_profit_pct = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    avg_loss_pct = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    win_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    profit_factor = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    insights = models.TextField(blank=True)

    class Meta:
        db_table = 'strategy_learning'
        unique_together = ['strategy_type', 'pattern_name']
```

---

<a name="15-configuration--setup"></a>
## 15. Configuration & Setup

### requirements.txt

```txt
# Django
Django==4.2.7
django-environ==0.11.2

# Database (SQLite is default, no extra driver needed)

# Cache & Celery
redis==5.0.1
celery==5.3.4
django-celery-beat==2.5.0

# API Clients
requests==2.31.0
websocket-client==1.6.4

# Data Processing
pandas==2.1.3
numpy==1.26.2
ta-lib==0.4.28

# LLM & AI
chromadb==0.4.18
sentence-transformers==2.2.2

# Web Scraping
beautifulsoup4==4.12.2
lxml==4.9.3

# Alerts
python-telegram-bot==20.7
twilio==8.10.0

# Utilities
python-dateutil==2.8.2
pytz==2023.3

# Development
pytest==7.4.3
pytest-django==4.7.0
black==23.11.0
```

### .env.example

```bash
# Django
SECRET_KEY=your-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Redis
REDIS_URL=redis://localhost:6379/0

# Kotak Neo API
KOTAK_CONSUMER_KEY=
KOTAK_CONSUMER_SECRET=
KOTAK_MOBILE=
KOTAK_PASSWORD=

# ICICI Breeze API
ICICI_API_KEY=
ICICI_API_SECRET=

# Trendlyne
TRENDLYNE_API_KEY=

# News APIs
NEWS_API_KEY=

# Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# Ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=deepseek-coder:33b

# Paper Trading
PAPER_TRADING=True
```

---

# Part VI: Implementation Plan

<a name="18-phase-by-phase-implementation-plan"></a>
## 18. Phase-by-Phase Implementation Plan

### PHASE 1: Foundation & Project Setup (Week 1-2)

**Objective:** Set up Django project structure, database models, and core utilities

#### Week 1: Django Project Initialization

**Day 1-2: Project Setup**
- [ ] Create Django project `mcube`
- [ ] Set up virtual environment
- [ ] Install all dependencies from requirements.txt
- [ ] Configure settings.py with environment variables
- [ ] Set up SQLite database
- [ ] Configure Redis connection
- [ ] Set up logging configuration
- [ ] Create .gitignore and initialize git repository

**Day 3-4: Core App Development**
- [ ] Create `apps/core` app
- [ ] Implement `TimeStampedModel` base class
- [ ] Create `apps/core/constants.py` with all system constants
- [ ] Implement utility functions in `apps/core/utils.py`:
  - [ ] Date/time helpers (get_current_weekly_expiry, get_next_weekly_expiry, etc.)
  - [ ] Decimal/money formatting helpers
  - [ ] Market hours validation
  - [ ] Trading day validation
- [ ] Create management command: `init_system.py`

**Day 5-7: Database Models**
- [ ] Create all 9 Django apps
- [ ] Implement all database models:
  - [ ] `apps/core/models.py` - TimeStampedModel
  - [ ] `apps/accounts/models.py` - BrokerAccount, APICredential
  - [ ] `apps/strategies/models.py` - StrategyConfig, StrategyLearning
  - [ ] `apps/positions/models.py` - Position, MonitorLog
  - [ ] `apps/orders/models.py` - Order, Execution
  - [ ] `apps/risk/models.py` - RiskLimit, CircuitBreaker
  - [ ] `apps/data/models.py` - MarketData, OptionChain, Event
  - [ ] `apps/llm/models.py` - LLMValidation, LLMPrompt
  - [ ] `apps/analytics/models.py` - DailyPnL, Performance
  - [ ] `apps/alerts/models.py` - Alert, AlertLog
- [ ] Run makemigrations and migrate
- [ ] Register all models in admin.py

#### Week 2: Core Business Logic

**Day 8-9: Business Rules Implementation**
- [ ] Implement `morning_check(account)` in `apps/positions/services/position_manager.py`
- [ ] Implement `calculate_usable_margin(account)` in `apps/accounts/services/margin_manager.py`
- [ ] Implement `select_expiry_for_options()` in `apps/core/utils.py`
- [ ] Implement `select_expiry_for_futures()` in `apps/core/utils.py`
- [ ] Implement `should_exit_position(position)` in `apps/positions/services/exit_manager.py`
- [ ] Add comprehensive logging to all functions
- [ ] Write unit tests for all business rules

**Day 10-12: Broker API Integration - Base Classes**
- [ ] Create `apps/accounts/services/base_broker.py`
- [ ] Implement abstract `BaseBrokerClient` class with methods:
  - [ ] `authenticate()`
  - [ ] `place_order()`
  - [ ] `get_positions()`
  - [ ] `get_live_quote()`
  - [ ] `get_option_chain()`
- [ ] Create mock broker client for testing: `apps/accounts/services/mock_broker.py`
- [ ] Implement paper trading mode logic

**Day 13-14: Testing & Documentation**
- [ ] Write unit tests for all core functionality
- [ ] Test ONE POSITION RULE enforcement
- [ ] Test 50% margin usage calculation
- [ ] Test expiry selection logic (1 day / 15 days rules)
- [ ] Document all implemented features
- [ ] Create initial README.md

---

### PHASE 2: Kotak Strangle Strategy (Week 3-4)

**Objective:** Implement complete Kotak strangle strategy with all entry/exit logic

#### Week 3: Strike Selection & Entry Filters

**Day 15-16: Strike Selection Algorithm**
- [ ] Implement `calculate_strikes()` in `apps/strategies/strategies/kotak_strangle.py`
- [ ] Implement VIX-based delta adjustment logic
- [ ] Test strike calculation with various scenarios
- [ ] Implement support/resistance adjustment logic
- [ ] Implement directional bias adjustment

**Day 17-19: Entry Filters**
- [ ] Create filter framework in `apps/strategies/filters/`
- [ ] Implement `global_markets.py` filter:
  - [ ] SGX Nifty change filter
  - [ ] Nasdaq/Dow Jones change filter
- [ ] Implement `event_calendar.py` filter:
  - [ ] Economic event calendar integration
  - [ ] Major event detection
- [ ] Implement `volatility.py` filter:
  - [ ] India VIX threshold check
  - [ ] Bollinger Bands extreme detection
- [ ] Implement `run_entry_filters()` orchestration function
- [ ] Test filter combinations

**Day 20-21: Complete Entry Workflow**
- [ ] Implement `execute_kotak_strangle_entry()` in `apps/strategies/strategies/kotak_strangle.py`
- [ ] Integrate all steps:
  - [ ] Morning position check
  - [ ] Entry timing validation
  - [ ] Filter execution
  - [ ] Expiry selection
  - [ ] Strike calculation
  - [ ] Premium validation
  - [ ] Position sizing (50% margin rule)
  - [ ] Order placement
- [ ] Add comprehensive logging at each step
- [ ] Test complete workflow end-to-end

#### Week 4: Delta Management & Exit Logic

**Day 22-24: Delta Monitoring**
- [ ] Implement `monitor_and_manage_delta()` in `apps/positions/services/delta_monitor.py`
- [ ] Implement delta calculation for short options
- [ ] Implement net delta monitoring
- [ ] Implement `generate_adjustment_recommendation()`
- [ ] Create delta alert system (Telegram/Email)
- [ ] Test delta monitoring with mock data

**Day 25-26: Exit Logic**
- [ ] Implement `check_kotak_exit_conditions()` in `apps/positions/services/exit_manager.py`
- [ ] Implement exit rules:
  - [ ] Stop-loss check (100% loss)
  - [ ] Target check (70% profit)
  - [ ] Thursday 3:15 PM conditional exit
  - [ ] Friday EOD mandatory exit
- [ ] Implement minimum profit check (50%)
- [ ] Test all exit scenarios

**Day 27-28: Integration & Testing**
- [ ] Integrate strangle strategy with position management
- [ ] Create Celery task for entry evaluation
- [ ] Create Celery task for delta monitoring
- [ ] Create Celery task for exit evaluation
- [ ] End-to-end testing with paper trading mode
- [ ] Document Kotak strategy completely

---

### PHASE 3: ICICI Futures Strategy (Week 5-6)

**Objective:** Implement complete futures strategy with screening and LLM validation

#### Week 5: Stock Screening & OI Analysis

**Day 29-30: Screening Framework**
- [ ] Implement `screen_futures_opportunities()` in `apps/strategies/strategies/icici_futures.py`
- [ ] Implement liquidity filter
- [ ] Create candidate scoring system
- [ ] Implement top-N candidate selection

**Day 31-32: OI Analysis**
- [ ] Implement `analyze_oi()` in `apps/data/analyzers/oi_analyzer.py`
- [ ] Implement futures OI analysis:
  - [ ] Long buildup detection
  - [ ] Short buildup detection
  - [ ] Short covering detection
  - [ ] Long unwinding detection
- [ ] Implement options OI analysis:
  - [ ] PCR calculation
  - [ ] PCR interpretation
- [ ] Implement combined verdict logic
- [ ] Test OI analysis with historical data

**Day 33-35: Sector Analysis**
- [ ] Implement `analyze_sector()` in `apps/data/analyzers/sector_analyzer.py`
- [ ] Implement multi-timeframe performance tracking (3D, 7D, 21D)
- [ ] Implement CRITICAL filter logic:
  - [ ] ALL timeframes positive for LONG
  - [ ] ALL timeframes negative for SHORT
  - [ ] Mixed signals → NO TRADE
- [ ] Test sector analysis with mock data
- [ ] Integrate with screening process

#### Week 6: LLM Integration & Entry Workflow

**Day 36-38: LLM Integration**
- [ ] Set up Ollama local server
- [ ] Download DeepSeek-Coder model
- [ ] Implement `apps/llm/services/ollama_client.py`
- [ ] Implement `validate_with_llm()` in `apps/llm/services/trade_validator.py`
- [ ] Create comprehensive validation prompt template
- [ ] Implement LLM response parsing
- [ ] Test LLM validation with sample candidates
- [ ] Implement confidence threshold check (70%)

**Day 39-40: Averaging Logic**
- [ ] Implement `should_average_position()` in `apps/positions/services/averaging_manager.py`
- [ ] Implement averaging rules:
  - [ ] Max 2 attempts check
  - [ ] 1% loss trigger check
  - [ ] Margin availability check
  - [ ] New average price calculation
  - [ ] Stop-loss adjustment (0.5% from avg)
- [ ] Test averaging logic

**Day 41-42: Complete Entry Workflow**
- [ ] Implement `execute_icici_futures_entry()` in `apps/strategies/strategies/icici_futures.py`
- [ ] Integrate all components:
  - [ ] Existing position check
  - [ ] Expiry selection (15-day rule)
  - [ ] Position sizing (50% margin + risk-based)
  - [ ] Order placement
- [ ] Create Celery task for screening
- [ ] Create Celery task for entry execution
- [ ] End-to-end testing with paper trading
- [ ] Document ICICI strategy completely

---

### PHASE 4: UI & Dashboard (Week 7-8)

**Objective:** Build web interface for monitoring and control

#### Week 7: Core Templates & Dashboard

**Day 43-45: Base Templates**
- [ ] Create `templates/base.html` with Bootstrap 5
- [ ] Create navigation bar with account switcher
- [ ] Create `templates/home.html` landing page
- [ ] Implement flash messages display
- [ ] Create responsive layout
- [ ] Add Chart.js for visualizations
- [ ] Add HTMX for real-time updates

**Day 46-49: Main Dashboard**
- [ ] Create `apps/analytics/templates/analytics/dashboard.html`
- [ ] Implement real-time P&L display
- [ ] Implement active positions card
- [ ] Implement today's trades timeline
- [ ] Implement account summary cards (Kotak, ICICI)
- [ ] Implement risk metrics display:
  - [ ] Daily P&L vs limit
  - [ ] Weekly P&L vs target
  - [ ] Current drawdown
- [ ] Implement delta monitoring card (for strangles)
- [ ] Add auto-refresh with HTMX (every 5 seconds)
- [ ] Test dashboard responsiveness

#### Week 8: Additional Views

**Day 50-52: Position Management Views**
- [ ] Create `apps/positions/templates/positions/position_list.html`
- [ ] Create `apps/positions/templates/positions/position_detail.html`
- [ ] Implement position editing form
- [ ] Implement manual exit button
- [ ] Implement averaging approval interface
- [ ] Add position history view

**Day 53-54: Strategy Configuration Views**
- [ ] Create strategy configuration forms
- [ ] Implement parameter editing interface
- [ ] Add strategy enable/disable toggle
- [ ] Create filter configuration UI

**Day 55-56: Testing & Polish**
- [ ] Cross-browser testing
- [ ] Mobile responsiveness testing
- [ ] UI/UX improvements
- [ ] Add loading states
- [ ] Add error messages
- [ ] Performance optimization

---

### PHASE 5: Background Tasks & Automation (Week 9)

**Objective:** Implement Celery tasks for automation

#### Week 9: Celery Configuration & Tasks

**Day 57-58: Celery Setup**
- [ ] Configure Celery in `config/celery.py`
- [ ] Set up Celery Beat schedule in `config/settings.py`
- [ ] Configure Redis as broker
- [ ] Test Celery worker startup
- [ ] Configure task logging

**Day 59-61: Core Celery Tasks**
- [ ] Create `apps/data/tasks.py`:
  - [ ] `sync_market_data()` - Every 1 minute during market hours
  - [ ] `sync_option_chain()` - Every 5 minutes
- [ ] Create `apps/positions/tasks.py`:
  - [ ] `monitor_all_positions()` - Every 5 seconds
  - [ ] `update_position_pnl()` - Every 10 seconds
- [ ] Create `apps/strategies/tasks.py`:
  - [ ] `evaluate_kotak_entry()` - Mon/Tue 10:00 AM
  - [ ] `evaluate_kotak_exit()` - Thu/Fri 3:15 PM
  - [ ] `screen_icici_opportunities()` - Every 30 minutes
- [ ] Create `apps/risk/tasks.py`:
  - [ ] `check_risk_limits()` - Every 1 minute
  - [ ] `monitor_circuit_breakers()` - Every 30 seconds
- [ ] Create `apps/analytics/tasks.py`:
  - [ ] `generate_daily_report()` - 4:00 PM daily
  - [ ] `update_learning_patterns()` - EOD

**Day 62-63: Task Testing**
- [ ] Test all Celery tasks individually
- [ ] Test task scheduling
- [ ] Test error handling and retries
- [ ] Monitor task execution logs
- [ ] Optimize task performance

---

### PHASE 6: Risk Management & Circuit Breakers (Week 10)

**Objective:** Implement comprehensive risk management system

#### Week 10: Risk Implementation

**Day 64-66: Risk Manager**
- [ ] Implement `apps/risk/services/risk_manager.py`
- [ ] Implement position-level risk checks
- [ ] Implement account-level risk checks
- [ ] Implement system-level risk checks
- [ ] Implement circuit breaker logic:
  - [ ] Daily loss limit breach
  - [ ] Weekly loss limit breach
  - [ ] Maximum drawdown breach
- [ ] Implement emergency position closure
- [ ] Implement account deactivation
- [ ] Test all risk scenarios

**Day 67-68: Adaptive Risk**
- [ ] Implement `apps/risk/services/adaptive_risk.py`
- [ ] Implement pattern-based risk adjustment
- [ ] Implement win rate consideration
- [ ] Implement profit factor weighting
- [ ] Test adaptive risk logic

**Day 69-70: Integration & Testing**
- [ ] Integrate risk manager with all strategies
- [ ] Test circuit breaker activation
- [ ] Test risk limit enforcement
- [ ] Simulate adverse scenarios
- [ ] Document risk management system

---

### PHASE 7: Alert System (Week 11)

**Objective:** Implement multi-channel alert system

#### Week 11: Alerts Implementation

**Day 71-73: Alert Services**
- [ ] Implement `apps/alerts/services/telegram_client.py`:
  - [ ] Bot initialization
  - [ ] Message sending
  - [ ] Rich formatting support
  - [ ] Image/chart sending
- [ ] Implement `apps/alerts/services/email_client.py`:
  - [ ] SMTP configuration
  - [ ] HTML email templates
  - [ ] Attachment support
- [ ] Implement `apps/alerts/services/sms_client.py`:
  - [ ] Twilio integration
  - [ ] SMS sending for critical alerts

**Day 74-76: Alert Orchestration**
- [ ] Create alert priority system (INFO, WARNING, CRITICAL)
- [ ] Implement channel routing logic:
  - [ ] INFO → Telegram
  - [ ] WARNING → Telegram + Email
  - [ ] CRITICAL → Telegram + Email + SMS
- [ ] Create alert templates
- [ ] Implement alert deduplication
- [ ] Test all alert channels

**Day 77: Integration**
- [ ] Integrate alerts with all strategies
- [ ] Integrate alerts with risk manager
- [ ] Integrate alerts with position monitoring
- [ ] Test end-to-end alert flow

---

### PHASE 8: Self-Learning System (Week 12)

**Objective:** Implement pattern recognition and learning

#### Week 12: Learning Implementation

**Day 78-80: Pattern Recognition**
- [ ] Implement `apps/analytics/services/pattern_recognition.py`
- [ ] Implement entry pattern detection
- [ ] Implement exit pattern detection
- [ ] Implement market condition capture
- [ ] Store patterns in StrategyLearning model

**Day 81-83: Learning Engine**
- [ ] Implement `apps/analytics/services/learning_engine.py`
- [ ] Implement performance metric calculation:
  - [ ] Win rate
  - [ ] Profit factor
  - [ ] Average profit/loss
- [ ] Implement pattern updating on trade completion
- [ ] Implement LLM-based insight generation
- [ ] Test learning engine

**Day 84: Integration**
- [ ] Integrate learning with strategies
- [ ] Create learning insights dashboard
- [ ] Test pattern detection
- [ ] Document learning system

---

### PHASE 9: Broker API Integration (Week 13-14)

**Objective:** Implement actual broker API clients

#### Week 13-14: Broker Implementation

**Day 85-88: Kotak Neo API**
- [ ] Implement `apps/accounts/services/kotak_client.py`
- [ ] Implement authentication flow
- [ ] Implement order placement
- [ ] Implement position fetching
- [ ] Implement option chain retrieval
- [ ] Implement live quotes
- [ ] Test with paper trading first
- [ ] Test with small real orders

**Day 89-92: ICICI Breeze API**
- [ ] Implement `apps/accounts/services/icici_client.py`
- [ ] Implement authentication flow
- [ ] Implement futures order placement
- [ ] Implement position fetching
- [ ] Implement live quotes
- [ ] Implement OI data retrieval
- [ ] Test with paper trading first
- [ ] Test with small real orders

**Day 93-98: Integration & Testing**
- [ ] Integrate broker clients with strategies
- [ ] Test complete order flow
- [ ] Test position syncing
- [ ] Handle API errors gracefully
- [ ] Implement retry logic
- [ ] Implement rate limiting
- [ ] Document broker integration

---

### PHASE 10: Testing & Deployment (Week 15-16)

**Objective:** Comprehensive testing and production deployment

#### Week 15: Testing

**Day 99-101: Unit Testing**
- [ ] Write unit tests for all models
- [ ] Write unit tests for all business logic
- [ ] Write unit tests for all utilities
- [ ] Achieve >80% code coverage
- [ ] Fix all failing tests

**Day 102-104: Integration Testing**
- [ ] Test Kotak strategy end-to-end
- [ ] Test ICICI strategy end-to-end
- [ ] Test risk management system
- [ ] Test alert system
- [ ] Test UI workflows
- [ ] Test Celery tasks

**Day 105: Paper Trading Validation**
- [ ] Run system in paper trading mode for 1 week
- [ ] Monitor all positions
- [ ] Verify P&L calculations
- [ ] Verify risk limit enforcement
- [ ] Verify alert delivery
- [ ] Fix any issues discovered

#### Week 16: Deployment

**Day 106-108: Production Setup**
- [ ] Set up production server
- [ ] Install all dependencies
- [ ] Configure environment variables
- [ ] Set up SSL certificates
- [ ] Configure firewall
- [ ] Set up backup system
- [ ] Configure monitoring (optional: use tools like Sentry)

**Day 109-110: Deployment**
- [ ] Deploy application to production
- [ ] Configure systemd services for:
  - [ ] Django application (Gunicorn)
  - [ ] Celery worker
  - [ ] Celery beat
  - [ ] Redis
- [ ] Test all services
- [ ] Verify system health
- [ ] Enable paper trading mode

**Day 111-112: Go-Live Preparation**
- [ ] Final security audit
- [ ] Final performance testing
- [ ] Create deployment checklist
- [ ] Create rollback plan
- [ ] Document production procedures
- [ ] Train on system operation

---

<a name="19-development-checklist"></a>
## 19. Development Checklist

### Pre-Development Checklist

- [ ] Review complete design document
- [ ] Understand all business rules
- [ ] Set up development environment
- [ ] Install required software (Python, Redis, Ollama)
- [ ] Create project repository
- [ ] Set up IDE/editor

### Critical Implementation Checkpoints

**ONE POSITION RULE Enforcement:**
- [ ] Implemented `Position.has_active_position(account)` class method
- [ ] Called before EVERY entry evaluation
- [ ] Enforced in morning check
- [ ] Enforced in entry workflow
- [ ] Unit tested thoroughly

**50% Margin Usage:**
- [ ] Implemented `calculate_usable_margin()` function
- [ ] Used in position sizing for Kotak strategy
- [ ] Used in position sizing for ICICI strategy
- [ ] Tested with various capital amounts
- [ ] Verified reserve calculation

**Expiry Selection:**
- [ ] Implemented `select_expiry_for_options()` with 1-day rule
- [ ] Implemented `select_expiry_for_futures()` with 15-day rule
- [ ] Both functions skip to next expiry correctly
- [ ] Tested with mock dates near expiry
- [ ] Integrated with entry workflows

**Exit Discipline:**
- [ ] Implemented minimum profit check (50%)
- [ ] EOD exits only if profit threshold met
- [ ] Hold logic implemented for under-performing positions
- [ ] Warnings logged when holding overnight
- [ ] Tested all exit scenarios

**Averaging Logic:**
- [ ] Max 2 attempts enforced
- [ ] 1% loss trigger implemented
- [ ] Margin availability checked
- [ ] Stop-loss tightened to 0.5% from new average
- [ ] Tested averaging workflow

**Delta Management:**
- [ ] Net delta calculation implemented
- [ ] 300 threshold monitoring active
- [ ] Manual adjustment recommendations generated
- [ ] Alerts sent to user
- [ ] NO automatic execution (user confirms)

### Quality Gates

Each phase must pass these gates before proceeding:

1. **Code Quality**
   - [ ] All code follows PEP 8 style guide
   - [ ] All functions have docstrings
   - [ ] No linter warnings
   - [ ] Type hints used where appropriate

2. **Testing**
   - [ ] Unit tests written for all functions
   - [ ] All tests passing
   - [ ] >80% code coverage
   - [ ] Integration tests pass

3. **Documentation**
   - [ ] README updated
   - [ ] Inline comments added for complex logic
   - [ ] API documentation generated
   - [ ] User guide updated

4. **Security**
   - [ ] No credentials in code
   - [ ] Environment variables used
   - [ ] Input validation implemented
   - [ ] SQL injection prevention verified

5. **Performance**
   - [ ] No N+1 query issues
   - [ ] Database indexes added
   - [ ] Celery tasks optimized
   - [ ] Page load times acceptable (<2s)

---

<a name="20-quality-assurance-criteria"></a>
## 20. Quality Assurance Criteria

### Functional Testing

**Kotak Strangle Strategy:**
- [ ] Entry filters ALL work correctly
- [ ] Strike selection formula produces correct strikes
- [ ] VIX adjustment works
- [ ] Support/resistance adjustment works
- [ ] Position sizing uses 50% margin
- [ ] Orders placed correctly (paper mode)
- [ ] Delta monitoring works
- [ ] Delta alerts sent when threshold breached
- [ ] Exit logic honors minimum profit rule
- [ ] Thursday/Friday exit timing correct

**ICICI Futures Strategy:**
- [ ] Screening identifies correct candidates
- [ ] OI analysis produces correct signals
- [ ] Sector analysis filters correctly (ALL timeframes)
- [ ] LLM validation returns structured response
- [ ] Position sizing uses 50% margin + risk-based
- [ ] Averaging triggers at 1% loss
- [ ] Averaging limited to 2 attempts
- [ ] Stop-loss tightens after averaging
- [ ] Exit logic honors minimum profit rule

**Risk Management:**
- [ ] Daily loss limit enforced
- [ ] Weekly loss limit enforced
- [ ] Circuit breakers activate correctly
- [ ] All positions closed on circuit breaker
- [ ] Account deactivated on breach
- [ ] Critical alerts sent

**UI/Dashboard:**
- [ ] Real-time updates work (HTMX)
- [ ] P&L displays correctly
- [ ] Position details accurate
- [ ] Charts render correctly
- [ ] Forms submit successfully
- [ ] Responsive on mobile devices

### Non-Functional Testing

**Performance:**
- [ ] Dashboard loads in <2 seconds
- [ ] Position monitoring completes in <1 second
- [ ] Market data sync completes in <5 seconds
- [ ] Celery tasks don't timeout
- [ ] Database queries optimized

**Reliability:**
- [ ] System recovers from broker API failures
- [ ] System recovers from network issues
- [ ] System recovers from Celery worker crashes
- [ ] Data integrity maintained
- [ ] No data loss on failures

**Security:**
- [ ] Credentials stored securely
- [ ] API tokens encrypted
- [ ] No SQL injection vulnerabilities
- [ ] No XSS vulnerabilities
- [ ] CSRF protection enabled

**Maintainability:**
- [ ] Code is readable
- [ ] Functions are modular
- [ ] Separation of concerns maintained
- [ ] Easy to add new strategies
- [ ] Easy to add new filters

---

## Final Pre-Production Checklist

### Week Before Go-Live

- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Paper trading successful for 1 week
- [ ] All P&L calculations verified
- [ ] All risk limits tested
- [ ] All alerts working
- [ ] Backup system tested
- [ ] Rollback plan documented
- [ ] Team trained on system
- [ ] Monitoring configured

### Day of Go-Live

- [ ] Morning system health check
- [ ] Verify broker API connectivity
- [ ] Verify Celery workers running
- [ ] Verify Redis running
- [ ] Verify Ollama running
- [ ] Verify alert channels working
- [ ] Start with paper trading = True
- [ ] Monitor first 2 hours closely
- [ ] Switch to paper trading = False (with approval)
- [ ] Monitor continuously

### Post Go-Live (First Week)

- [ ] Daily system health checks
- [ ] Daily P&L reconciliation
- [ ] Daily review of alerts
- [ ] Daily review of logs
- [ ] Daily review of positions
- [ ] Address any issues immediately
- [ ] Document lessons learned

---

## Success Criteria

The project is considered successful when:

1. **System Stability**
   - Uptime > 99.5% during market hours
   - Zero data loss incidents
   - All critical business rules enforced

2. **Performance**
   - Target monthly returns achieved (₹12-15L)
   - Risk limits never breached
   - Win rate > 60%
   - Profit factor > 1.5

3. **Automation**
   - 90%+ of trades automated (entry signals)
   - 100% of risk monitoring automated
   - 100% of alerts delivered successfully

4. **User Experience**
   - Dashboard accessible 24/7
   - Real-time updates working
   - Alerts delivered within 1 minute
   - System easy to operate

---

## Post-Implementation Roadmap

### Month 2-3: Optimization
- Fine-tune strategy parameters based on live results
- Optimize filter thresholds
- Enhance LLM prompts
- Improve UI/UX based on feedback

### Month 4-6: Expansion
- Add new strategies (Iron Condor, Calendar Spread)
- Add more instruments (Bank Nifty, Fin Nifty)
- Implement advanced pattern recognition
- Add portfolio optimization

### Month 7-12: Scale
- Increase capital allocation
- Add more broker accounts
- Implement multi-strategy portfolio
- Build advanced analytics

---

**END OF IMPLEMENTATION PLAN**

This document is comprehensive and ready for execution. All critical business rules are documented, all phases are planned, and all quality gates are defined. The system is designed for conservative, disciplined trading with capital preservation as the primary objective.

**Remember:** ONE POSITION PER ACCOUNT. 50% MARGIN FOR FIRST TRADE. Always verify before coding.
