# Optimized Strangle Trading Workflow

## Overview

This document describes the new **modular, UI-configurable** strangle trading workflow implemented for mCube-ai. The workflow consists of **7 separate celery tasks** that execute throughout the trading day, with all timings configurable via Django Admin (no code changes needed).

---

## 📋 Trading Day Timeline

| Time | Task | Description |
|------|------|-------------|
| **9:00 AM** | PreMarket | Fetch SGX Nifty, US markets, Trendlyne data, VIX, events |
| **9:15 AM** | MarketOpen | Capture opening state & gap analysis |
| **9:30 AM** | TradeStart | Evaluate 0.5% movement threshold & start entries |
| **9:30-10:00 AM** | (Staggered) | Execute entries every 5 mins (if conditions met) |
| **9:00-3:30 PM** | TradeMonitor | Monitor positions (delta, P&L, targets) every 5 mins |
| **3:15 PM** | TradeStop | Evaluate exit conditions (Thu/Fri) |
| **3:30 PM** | DayClose | Reconciliation & position updates |
| **3:40 PM** | **AnalyzeDay** | **Comprehensive analysis & learning** |

---

## 🔧 Configuration (UI-Based)

### All task timings are configurable via Django Admin:

**Admin URL:** `/admin/strategies/tradingscheduleconfig/`

### Available Configuration Options:

- **Scheduled Time** - When to run the task (IST)
- **Enabled/Disabled** - Turn tasks on/off
- **Recurring** - For monitoring tasks (every N minutes)
- **Interval** - Minutes between recurring task executions
- **Days of Week** - Which days to run (Mon-Fri, etc.)
- **Task Parameters** - Strategy-specific parameters (JSON)

---

## 📊 Task Details

### 1. PreMarket Data Fetch (9:00 AM)

**Task:** `apps.strategies.tasks_strangle.premarket_data_fetch`

**Purpose:** Collect all market data before market opens

**Fetches:**
- ✅ SGX Nifty futures data (Singapore Exchange)
- ✅ US market close (Nasdaq, Dow Jones)
- ✅ Trendlyne stock data (21 CSV files)
- ✅ India VIX
- ✅ Economic event calendar (next 5 days)
- ✅ Global market indices

**Database Models:**
- `SGXNiftyData` - Stores SGX Nifty pre-market data
- `TLStockData` - Trendlyne comprehensive stock data
- `Event` - Economic events calendar

**Telegram Notification:** ✅ Sends pre-market summary

---

### 2. Market Opening Validation (9:15 AM)

**Task:** `apps.strategies.tasks_strangle.market_opening_validation`

**Purpose:** Capture how market opened

**Captures:**
- Opening price (9:15 AM Nifty)
- Gap analysis (vs previous close)
- Gap type (GAP_UP, GAP_DOWN, FLAT)
- Opening sentiment (BULLISH, BEARISH, NEUTRAL, VOLATILE)
- VIX at opening
- Volume analysis
- Is expiry day?
- Is event day?

**Database Models:**
- `MarketOpeningState` - Complete opening state record

**Telegram Notification:** ✅ Sends opening summary with gap details

**Critical for:** Trade Start task uses this to calculate 9:15-9:30 movement

---

### 3. Trade Start Evaluation (9:30 AM)

**Task:** `apps.strategies.tasks_strangle.trade_start_evaluation`

**Purpose:** Validate movement threshold & start strangle entries

**Logic:**
1. Fetch current Nifty price (9:30)
2. Calculate movement from 9:15 to 9:30
3. **Check if substantial (>0.5%)**
4. If YES → Run entry filters
5. If all filters pass → Execute strangle entry
6. Schedule staggered entries (every 5 mins till 10:00 AM)

**Entry Windows:** 9:30, 9:35, 9:40, 9:45, 9:50, 9:55, 10:00 (7 opportunities)

**Filters:**
- Global market stability
- Economic events
- Market regime (VIX, Bollinger Bands)
- ONE POSITION RULE

**Telegram Notification:** ✅ Sends entry decision (started/skipped) with reason

---

### 4. Staggered Entry Execution

**Task:** `apps.strategies.tasks_strangle.execute_single_entry`

**Purpose:** Execute individual strangle entries at 5-min intervals

**Strike Selection:**
- VIX-based delta adjustment (0.5% base, adjusted for volatility)
- OTM call & put strikes
- Adaptive to market conditions

**Position Sizing:**
- 50% margin usage (first trade)
- Reserve 50% for adjustments/emergencies

**Validation:** Each entry re-validates filters before execution

---

### 5. Trade Monitoring (Recurring - Every 5 mins)

**Task:** `apps.strategies.tasks_strangle.trade_monitoring`

**Purpose:** Continuous monitoring during market hours

**Monitors:**
- Real-time P&L
- **Delta monitoring** (alert if |delta| > 300)
- Target achievement (70% profit)
- Stop-loss checks
- Trailing stop-loss
- Position Greeks

**Schedule:** Runs every 5 minutes from 9:00 AM to 3:30 PM (Mon-Fri)

---

### 6. Trade Stop / Exit Evaluation (3:15 PM)

**Task:** `apps.strategies.tasks_strangle.trade_stop_evaluation`

**Purpose:** Evaluate exit conditions before market close

**Exit Rules:**
- **Thursday:** Exit if profit >= 50%
- **Friday:** **Mandatory exit** (EOD)
- Any day: Exit if target (70%) achieved

**Parameters:**
- `mandatory=False` (Thursday)
- `mandatory=True` (Friday)

**Telegram Notification:** ✅ Sends exit decision with P&L

---

### 7. Day Close Reconciliation (3:30 PM)

**Task:** `apps.strategies.tasks_strangle.day_close_reconciliation`

**Purpose:** End-of-day position updates

**Actions:**
- Update all position P&Ls
- Sync with broker
- Verify margin usage
- Calculate day summary

**Telegram Notification:** ✅ Sends day close summary (positions, P&L)

---

### 8. Day Analysis & Learning (3:40 PM) ⭐

**Task:** `apps.strategies.tasks_strangle.analyze_day`

**Purpose:** **Comprehensive analysis for continuous improvement**

This is the **learning engine** of the system. It analyzes the entire trading day and generates insights for future improvement.

#### Analysis Components:

##### 📊 **Performance Analysis**
- Trade-by-trade breakdown
- Win rate calculation
- P&L attribution
- Capital efficiency

##### 🎯 **Filter Effectiveness**
- Which filters were run
- Which filters passed/failed
- Filter accuracy over time
- Identify false positives/negatives

##### ⏰ **Entry Timing Analysis**
- Best entry times (9:30 vs 9:40 vs 9:55)
- Entry time vs profitability correlation
- Optimal entry window identification

##### 🎨 **Strike Selection Analysis**
- Strike selection performance
- VIX adjustment effectiveness
- OTM distance optimization

##### 🚪 **Exit Timing Analysis**
- Exit timing effectiveness
- Should we exit earlier/later?
- Exit reasons breakdown (target, SL, EOD)

##### 🔍 **Pattern Recognition**
- Successful patterns (e.g., "Gap up + range bound")
- Failed patterns to avoid
- Market regime detection (Trending/Range/Volatile)

##### 💡 **Learning Insights Generation**
- Key learnings from the day
- Parameter adjustment recommendations
- Confidence score updates
- SGX prediction accuracy

##### 📈 **SGX Correlation Analysis**
- How accurate was SGX in predicting Indian market?
- Track correlation over time
- Adjust reliance on SGX based on accuracy

#### Database Models:
- `DailyTradingAnalysis` - Complete day analysis record
- `TradingInsight` - Individual learning insights

#### Telegram Notification:
✅ Sends comprehensive report with:
- Performance summary
- Market regime
- Key learnings (top 3)
- Recommendations (top 3)

---

## 🗄️ Database Models

### New Models Created:

1. **`TradingScheduleConfig`**
   - UI-configurable task scheduling
   - Enables/disables tasks
   - Configures timing and parameters

2. **`SGXNiftyData`**
   - SGX Nifty pre-market data
   - Implied gap calculation
   - Correlation tracking

3. **`MarketOpeningState`**
   - Complete opening state (9:15 AM)
   - Gap analysis
   - 9:15-9:30 movement tracking
   - Substantial movement flag

4. **`DailyTradingAnalysis`**
   - Comprehensive day analysis
   - Performance metrics
   - Filter effectiveness
   - Pattern recognition
   - Learning insights

5. **`TradingInsight`**
   - Individual insights
   - Confidence scores
   - Validation tracking
   - Action recommendations

---

## 🚀 Setup Instructions

### 1. Create Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 2. Setup Initial Schedule

```bash
python manage.py setup_trading_schedule
```

This creates default schedule configuration for all 7 tasks.

### 3. Configure via Django Admin

1. Open Admin: `http://localhost:8000/admin/`
2. Navigate to: **Strategies → Trading Schedule Configurations**
3. Adjust timings as needed
4. Enable/disable tasks

### 4. Restart Celery Beat

```bash
# Stop existing Celery Beat
pkill -f "celery beat"

# Start Celery Beat with new schedule
celery -A mcube_ai beat --loglevel=info
```

### 5. Start Celery Workers

```bash
# Main worker
celery -A mcube_ai worker --loglevel=info -Q strategies,monitoring,data,risk,reports

# Or separate workers for each queue
celery -A mcube_ai worker --loglevel=info -Q strategies -n strategies@%h
celery -A mcube_ai worker --loglevel=info -Q monitoring -n monitoring@%h
celery -A mcube_ai worker --loglevel=info -Q data -n data@%h
```

---

## 📱 Telegram Notifications

All tasks send Telegram notifications at key points:

- ✅ Pre-market summary (9:00 AM)
- ✅ Opening analysis (9:15 AM)
- ✅ Entry decision (9:30 AM)
- ✅ Exit notifications (3:15 PM)
- ✅ Day close summary (3:30 PM)
- ✅ **Comprehensive day analysis (3:40 PM)**

---

## 🎓 Learning & Improvement

### How the System Learns:

1. **Daily Analysis (3:40 PM)**
   - Analyzes all trades from the day
   - Identifies patterns (successful & failed)
   - Generates insights

2. **Insight Storage**
   - Stores insights in `TradingInsight` model
   - Tracks validation/contradiction over time
   - Builds confidence scores

3. **Pattern Recognition**
   - Identifies market conditions that led to success
   - Flags conditions to avoid
   - Updates strategy parameters

4. **Parameter Adjustment**
   - Recommends strike distance adjustments
   - Suggests entry time optimizations
   - Fine-tunes filter thresholds

5. **SGX Correlation Tracking**
   - Measures SGX prediction accuracy daily
   - Adjusts reliance on SGX based on historical accuracy
   - Learns when SGX is reliable vs unreliable

---

## 🔄 Workflow Optimizations

### Compared to Original Workflow:

| Feature | Old Workflow | New Workflow |
|---------|-------------|--------------|
| Entry Time | Fixed 10:00 AM | Dynamic 9:30 AM (after validation) |
| Movement Check | None | 9:15-9:30 movement (>0.5%) |
| Entry Frequency | One-time | Staggered (every 5 mins, 7 opportunities) |
| Task Configuration | Hardcoded | **UI-configurable** |
| Learning | None | **Comprehensive daily analysis** |
| SGX Data | Placeholder | **Real SGX Nifty fetch** |
| Opening Analysis | None | **Complete opening state capture** |
| Exit Strategy | Basic EOD | Conditional (Thu 50%, Fri mandatory) |

---

## 📖 Example Trading Day

### 9:00 AM - PreMarket
```
SGX Nifty: +0.45%
US Nasdaq: +0.60%
US Dow: +0.30%
India VIX: 14.2
Events: None major
```

### 9:15 AM - Market Open
```
Gap: +0.35% (GAP_UP)
Sentiment: BULLISH
VIX: 14.5
Volume: 1.2x average
```

### 9:30 AM - Trade Start
```
9:15-9:30 Movement: +0.65% (SUBSTANTIAL ✅)
Filters: ALL PASSED ✅
Action: START STRANGLE ENTRIES
Scheduled: 7 entry attempts (9:30-10:00)
```

### 9:30-10:00 AM - Staggered Entries
```
9:30: Entry #1 placed (Call 24500, Put 23500)
9:35: Entry #2 placed (Call 24550, Put 23450)
9:40: Filters failed (volatility spike)
9:45: Entry #3 placed
...
```

### 9:00-3:30 PM - Monitoring
```
Every 5 mins:
- P&L: ₹45,000 (unrealized)
- Delta: -120 (within threshold)
- Target: 70% = ₹105,000 (not reached)
```

### 3:15 PM - Trade Stop (Thursday)
```
Current P&L: ₹85,000 (65% profit)
Threshold: 50%
Action: EXIT POSITION ✅
```

### 3:30 PM - Day Close
```
Positions closed: 3
Total P&L: ₹85,000
ROI: 1.06%
```

### 3:40 PM - Day Analysis
```
Win Rate: 100% (3/3)
Best Entry Time: 9:30 AM
Best Exit Time: 3:15 PM
Market Regime: RANGE_BOUND
SGX Accuracy: 85%

Key Learnings:
1. Early entries (9:30-9:35) showed best results
2. Exit at 3:15 PM optimal on Thursdays
3. SGX prediction was highly accurate today

Recommendations:
1. Prefer 9:30 entries on gap-up days
2. Consider 3:00 PM exits when profit > 60%
3. Increase reliance on SGX for gap prediction
```

---

## 🛠️ Troubleshooting

### Tasks Not Running?

1. **Check Celery Beat is running:**
   ```bash
   ps aux | grep "celery beat"
   ```

2. **Check task is enabled:**
   - Admin → Trading Schedule Configurations
   - Verify `is_enabled = True`

3. **Check Celery logs:**
   ```bash
   tail -f celery-beat.log
   ```

### Schedule Not Updating?

**Restart Celery Beat** after making changes in Admin:
```bash
pkill -f "celery beat"
celery -A mcube_ai beat --loglevel=info
```

### Database Errors?

**Run migrations:**
```bash
python manage.py makemigrations strategies
python manage.py migrate
```

---

## 📊 Admin URLs

- **Schedule Configuration:** `/admin/strategies/tradingscheduleconfig/`
- **Market Opening States:** `/admin/strategies/marketopeningstate/`
- **SGX Nifty Data:** `/admin/strategies/sgxniftydata/`
- **Daily Analysis:** `/admin/strategies/dailytradinganalysis/`
- **Trading Insights:** `/admin/strategies/tradinginsight/`

---

## 🔗 Related Files

- **Tasks:** `apps/strategies/tasks_strangle.py`
- **Models:** `apps/strategies/models.py`
- **Dynamic Scheduler:** `apps/strategies/services/dynamic_scheduler.py`
- **Celery Config:** `mcube_ai/celery.py`
- **Admin:** `apps/strategies/admin.py`
- **Setup Command:** `apps/strategies/management/commands/setup_trading_schedule.py`

---

## ✅ Key Benefits

1. **✅ UI-Configurable** - Change timings without touching code
2. **✅ Modular** - Each phase is a separate task
3. **✅ Intelligent** - Movement validation before entry
4. **✅ Adaptive** - Staggered entries for better execution
5. **✅ Learning** - Comprehensive daily analysis & insights
6. **✅ Trackable** - Complete audit trail (opening state, analysis)
7. **✅ Optimized** - Better entry timing, exit strategies
8. **✅ Resilient** - Tasks can be enabled/disabled individually

---

**Last Updated:** 2025-11-17
**Version:** 1.0
**Author:** Claude Code (mCube-ai)
