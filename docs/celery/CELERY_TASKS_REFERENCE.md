# mCube AI Trading System - Celery Tasks Reference

**Complete Guide to Background Tasks and Automation**

Last Updated: November 17, 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Task Queue Architecture](#task-queue-architecture)
3. [Data Tasks](#data-tasks)
4. [Strategy Tasks](#strategy-tasks)
5. [Position Monitoring Tasks](#position-monitoring-tasks)
6. [Risk Management Tasks](#risk-management-tasks)
7. [Analytics & Reporting Tasks](#analytics--reporting-tasks)
8. [Task Schedules Summary](#task-schedules-summary)
9. [Task Dependencies](#task-dependencies)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The mCube AI Trading System uses **Celery** for distributed task execution with **Redis** as the message broker. Tasks are organized into **5 queues** for optimized performance:

- **data** - Market data fetching and synchronization
- **strategies** - Strategy evaluation and trade signal generation
- **monitoring** - Real-time position monitoring
- **risk** - Risk management and circuit breakers
- **reports** - Analytics and reporting

### Key Configuration

```python
# mcube_ai/celery.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
CELERY_TIMEZONE = 'Asia/Kolkata'  # IST
```

### Task Execution Settings

- **Task Time Limit:** 5 minutes (hard limit)
- **Soft Time Limit:** 4 minutes (raises exception)
- **Worker Prefetch:** 4 tasks per worker
- **Max Tasks Per Worker:** 1000 (auto-restart to prevent memory leaks)

---

## Task Queue Architecture

```
┌─────────────────────────────────────────────────┐
│           Redis (Message Broker)                │
│         redis://localhost:6379/0                │
└─────────────────┬───────────────────────────────┘
                  │
      ┌───────────┴───────────┐
      │   Celery Beat         │
      │   (Scheduler)         │
      └───────────┬───────────┘
                  │
      ┌───────────┴────────────────────────────┐
      │                                        │
┌─────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
│  data      │  │ strategies  │  │ monitoring  │
│  Queue     │  │   Queue     │  │   Queue     │
└────────────┘  └─────────────┘  └─────────────┘
      │                │                │
┌─────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
│   risk     │  │  reports    │  │             │
│   Queue    │  │   Queue     │  │             │
└────────────┘  └─────────────┘  └─────────────┘
```

---

## Data Tasks

### 1. `fetch_trendlyne_data`

**Queue:** `data`
**Schedule:** Daily @ 8:30 AM
**Execution Time:** ~2-5 minutes

**Purpose:**
Fetches market data from Trendlyne including:
- Market snapshot (all stocks)
- F&O data (futures & options)
- Analyst consensus data (21 CSV files)

**Success Criteria:**
- All CSV files downloaded successfully
- Files saved to `apps/data/tldata/`

**Dependencies:**
- None (runs first in daily sequence)

**Error Handling:**
- Retries: 3 attempts with 60s delay
- Alerts on failure via Telegram

---

### 2. `import_trendlyne_data`

**Queue:** `data`
**Schedule:** Daily @ 9:00 AM
**Execution Time:** ~3-7 minutes

**Purpose:**
Imports downloaded Trendlyne CSV files into database:

1. **Market Snapshot** → `MarketSnapshot` model
2. **F&O Data** → `ContractData` model
3. **Stock Metrics** → `ContractStockData` model
4. **Forecaster Data** → `ForecasterData` model (21 files)

**Database Updates:**
- ~3000 stock records updated
- ~15,000 F&O contracts updated
- ~50-100 forecaster entries per file

**Dependencies:**
- Requires `fetch_trendlyne_data` to complete first

---

### 3. `update_pre_market_data`

**Queue:** `data`
**Schedule:** Mon-Fri @ 8:30 AM
**Execution Time:** ~1-2 minutes

**Purpose:**
Updates pre-market data for Nifty 50 stocks before market opens

**Data Sources:**
- NSE/BSE pre-market quotes
- Overnight news events
- Global market cues

---

### 4. `update_live_market_data`

**Queue:** `data`
**Schedule:** Every 5 minutes (9:00 AM - 3:30 PM, Mon-Fri)
**Execution Time:** ~30-60 seconds

**Purpose:**
Real-time synchronization of market data during trading hours:

- Current prices (LTP) only for trades taken or positions identified.
- Live volume
- Open Interest (OI)
- Greeks (Delta, Gamma, Theta, Vega)

**Critical for:**
- Position P&L updates
- Stop-loss/target monitoring
- Entry point detection

---

### 5. `update_post_market_data`

**Queue:** `data`
**Schedule:** Mon-Fri @ 3:30 PM
**Execution Time:** ~3-5 minutes

**Purpose:**
Complete market data update after market closes:

- Final closing prices
- Total volume and OI
- Corporate actions
- Dividend announcements

---

## Strategy Tasks

### 6. `evaluate_kotak_strangle_entry`

**Queue:** `strategies`
**Schedule:** All market open days @ 09:40 AM
**Execution Time:** ~2-4 minutes
**Schedule End time:** **Schedule:** All market open days @ 10:15 AM

**Purpose:**
Evaluates and executes Kotak weekly strangle strategy entry

**Workflow:**
1. ✅ Check ONE POSITION RULE (no existing position)
2. ✅ Validate entry timing (all trading 9:40 AM and stop placeing orders at End Time 10:15 Am)
3. ✅ Run entry filters (market stability, VIX, events)
4. ✅ Calculate OTM strikes (0.5% base delta)
5. ✅ Check premium collected vs target
6. ✅ Validate 50% margin usage
7. ✅ LLM validation (optional)
8. ✅ Place orders (if all filters pass)
9. ✅ Send Telegram notification

**Entry Filters (ALL must pass):**
- Global markets stable (SGX ±0.5%, US ±1.0%)
- Nifty stable (±1.0% yesterday, ±2.0% last 3 days)
- No major economic events (next 5 days)
- VIX < 20
- No existing position

**Success Criteria:**
- Position created with status `ACTIVE`
- Premium collected ≥ target
- Margin used ≤ 50% of available

---

### 7. `evaluate_kotak_strangle_exit`

**Queue:** `strategies`
**Schedule:**
- Exit everyday if profit is greater than configured number ( Say 10k)
- Trigger and check at 3:15pm whenever there is open positions

**Execution Time:** ~1-2 minutes. Only if open positions

**Purpose:**
Evaluates and executes Kotak strangle exit conditions

**Exit Rules:**

**Thursday 3:15 PM (Conditional):**
- Exit ONLY if ≥50% profit achieved
- Otherwise, hold overnight


**Other Exit Triggers (checked every 30s):**
- Stop-loss hit (100% of premium)
- Target hit (70% profit)

**Telegram Notification:**
- Exit reason
- Realized P&L
- Position details

---

### 8. `monitor_all_strangle_deltas`

**Queue:** `monitoring`
**Schedule:** Every 15 minutes (9:00 AM - 3:30 PM) Configurable through UI
**Execution Time:** ~10-30 seconds

**Purpose:**
Monitors net delta for all active strangle positions

**Alert Threshold:** |Net Delta| > 300

**When Delta Exceeded:**
1. ⚠️ Send Telegram warning
2. 📊 Provide adjustment recommendation
3. ⏸ Wait for manual approval (NOT auto-executed)

**Delta Management (Manual):**
- User reviews delta imbalance
- User decides whether to adjust
- Adjustments made via Telegram bot commands

---

### 9. `screen_futures_opportunities`

**Queue:** `strategies`
**Schedule:** Every 30 minutes (9:00 AM - 2:30 PM, Mon-Fri)
**Execution Time:** ~5-10 minutes

**Purpose:**
Screens for ICICI futures trading opportunities using multi-factor analysis

**Screening Pipeline:**

1. **Liquidity Filter** - Top 50 stocks by volume
2. **OI Analysis** - Long/Short buildup detection
3. **Sector Analysis** - ALL timeframes (3D, 7D, 21D) must align
4. **Technical Analysis** - RSI, MACD, DMAs
5. **Composite Scoring** - Minimum 65/100
6. **LLM Validation** - Final gate (70% confidence)

**Output:**
- Top 3 candidates sent via Telegram
- Includes composite score, OI signal, sector verdict
- **Manual approval required** for execution

**Example Output:**
```
📊 FUTURES OPPORTUNITIES

1. RELIANCE - LONG
   Score: 85/100
   OI: Long Buildup
   Sector: STRONG_BULLISH

2. HDFCBANK - LONG
   Score: 78/100
   OI: Short Covering
   Sector: STRONG_BULLISH

3. TCS - SHORT
   Score: 72/100
   OI: Short Buildup
   Sector: STRONG_BEARISH

ℹ️ Manual approval required to execute entry
```

---

### 10. `check_futures_averaging`

**Queue:** `monitoring`
**Schedule:** Every 10 minutes (9:00 AM - 3:30 PM)
**Execution Time:** ~20-40 seconds

**Purpose:**
Checks if active futures positions need averaging (dollar-cost averaging)

**Averaging Rules:**
- **Trigger:** Position down 1% from entry
- **Max Attempts:** 2 averaging attempts per position
- **Quantities:**
  - 1st Average: 20% of current balance
  - 2nd Average: 50% of current balance
- **Stop-Loss Adjustment:** Tighten to 0.5% from new average
- **Approval:** Requires Telegram confirmation before execution

**Recommendation Message:**
```
⚠️ AVERAGING RECOMMENDATION

Position: #123
Symbol: RELIANCE
Direction: LONG

Current Entry: ₹2,500.00
Current Price: ₹2,475.00
Loss: 1.00%

RECOMMENDATION:
Add 500 quantity
New Avg Entry: ₹2,487.50
New Stop-Loss: ₹2,475.13
Additional Margin: ₹75,000

Averaging Count: 1/2

ℹ️ Manual approval required
```

---

## Position Monitoring Tasks

### 11. `monitor_all_positions`

**Queue:** `monitoring`
**Schedule:** Every 10 seconds (during market hours)
**Execution Time:** <5 seconds

**Purpose:**
Real-time monitoring of all active positions

**Actions:**
1. Fetch current prices from broker API
2. Update position records
3. Calculate unrealized P&L
4. Log significant changes

**Performance:**
- Must complete in <5 seconds
- Handles up to 50 concurrent positions
- Lightweight updates only

---

### 12. `update_position_pnl`

**Queue:** `monitoring`
**Schedule:** Every 15 seconds
**Execution Time:** <10 seconds

**Purpose:**
Updates P&L for all active positions and sends alerts

**P&L Alerts:**

**Profit Alert (>5%):**
```
🎉 PROFIT ALERT

Position #123
Instrument: RELIANCE
P&L: ₹12,500 (6.2%)
```

**Loss Alert (<-3%):**
```
⚠️ LOSS ALERT

Position #123
Instrument: HDFCBANK
P&L: -₹8,200 (-3.5%)
```

---

### 13. `check_exit_conditions`

**Queue:** `monitoring`
**Schedule:** Every 30 seconds
**Execution Time:** ~5-15 seconds

**Purpose:**
Checks and executes exit conditions for all active positions

**Exit Conditions:**

1. **Stop-Loss Hit** → Auto-exit immediately
2. **Target Hit** → Auto-exit immediately
3. **EOD (3:15 PM)**:
   - Exit if ≥50% profit achieved
   - Hold if <50% profit (accept overnight risk)
4. **Friday EOD** → Mandatory exit (options near expiry)

**Auto-Exit Notification:**
Always validate from Telegram
```
✅ AUTO-EXIT EXECUTED

Position: #123
Instrument: RELIANCE
Reason: Target Hit
Exit Type: TARGET
P&L: ₹15,000
```

---

## Risk Management Tasks

### 14. `check_risk_limits_all_accounts`

**Queue:** `risk`
**Schedule:** Every 1 minute
**Execution Time:** ~10-30 seconds

**Purpose:**
Monitors and enforces risk limits for all active accounts

**Risk Limits Monitored:**

1. **Daily Loss Limit**
   - Kotak: ₹2,00,000
   - ICICI: ₹1,50,000

2. **Weekly Loss Limit**
   - Calculated from Monday start

3. **Maximum Drawdown**
   - Alert at 10%
   - Circuit breaker at 15%

**Actions on Breach:**

**🚨 CRITICAL - CIRCUIT BREAKER ACTIVATION:**
1. ✅ Close ALL active positions immediately
2. ✅ Deactivate account (no new trades)
3. ✅ Activate 24-hour cooldown
4. ✅ Send critical Telegram alert

**Warning Alert (80% utilization):**
```
⚠️ RISK WARNING ⚠️

Account: ICICI Securities
Broker: ICICI

LIMITS APPROACHING:
• Daily Loss: ₹1,20,000 / ₹1,50,000 (80.0%)

⚠️ Exercise caution with new positions
```

**Breach Alert:**
```
🚨🚨 CIRCUIT BREAKER ACTIVATED 🚨🚨

Account: ICICI Securities
Broker: ICICI

BREACHED LIMITS:
• Daily Loss: ₹1,55,000 / ₹1,50,000

ACTIONS TAKEN:
✅ All positions closed
✅ Account deactivated
✅ 24-hour cooldown activated

⚠️ IMMEDIATE ATTENTION REQUIRED
```

---

### 15. `monitor_circuit_breakers`

**Queue:** `risk`
**Schedule:** Every 30 seconds
**Execution Time:** <10 seconds

**Purpose:**
Monitors active circuit breakers and manages cooldown periods

**Monitoring:**
- Checks if cooldown periods expired
- Verifies all positions were closed
- Sends periodic reminders (every 6 hours)

**Cooldown Expired Notification:**
```
⏰ CIRCUIT BREAKER COOLDOWN EXPIRED

Account: ICICI Securities
Broker: ICICI
Trigger: DAILY_LOSS_LIMIT
Triggered: 2025-11-16 14:25:30
Cooldown Ended: 2025-11-17 14:25:30

MANUAL REVIEW REQUIRED:
1. Review account status
2. Verify all positions closed
3. Check margin availability
4. Reset circuit breaker manually if approved

⚠️ Account remains deactivated until manual reset
```

---

### 16. `generate_daily_risk_report`

**Queue:** `reports`
**Schedule:** Daily @ 6:00 PM (Mon-Fri)
**Execution Time:** ~30-60 seconds

**Purpose:**
Generates comprehensive daily risk report for all accounts

**Report Includes:**
- Account status (ACTIVE/DEACTIVATED)
- Risk limit utilization
- Active circuit breakers
- Breach and warning summary

---

## Analytics & Reporting Tasks

### 17. `generate_daily_pnl_report`

**Queue:** `reports`
**Schedule:** Daily @ 4:00 PM (Mon-Fri)
**Execution Time:** ~30-60 seconds

**Purpose:**
Generates comprehensive daily P&L report

**Report Contents:**

```
📊 DAILY P&L REPORT
Date: 2025-11-17 (Monday)
========================================

📈 ICICI Securities (ICICI)
  Daily P&L: ₹25,000
  Trades: 2 (2W/0L/0BE)
  Win Rate: 100.0%

📉 Kotak Securities (KOTAK)
  Daily P&L: -₹5,000
  Trades: 1 (0W/1L/0BE)
  Win Rate: 0.0%

========================================
📈 OVERALL SUMMARY
Total P&L: ₹20,000
Total Trades: 3
Winners: 2 | Losers: 1
Win Rate: 66.7%
```

**Metrics Included:**
- Total P&L by account
- Win/Loss/Breakeven count
- Win rate percentage
- Overall summary

---

### 18. `update_learning_patterns`

**Queue:** `reports`
**Schedule:** Daily @ 5:00 PM (Mon-Fri)
**Execution Time:** ~2-5 minutes

**Purpose:**
Updates learning patterns for the self-learning system

**Workflow:**
1. Analyze all closed trades from today
2. Discover new trading patterns
3. Validate existing patterns
4. Update pattern effectiveness scores
5. Generate parameter suggestions

**Pattern Types Detected:**
- Entry timing patterns
- Exit timing patterns
- Market condition patterns
- Win/loss patterns

---

### 19. `send_weekly_summary`

**Queue:** `reports`
**Schedule:** Friday @ 6:00 PM
**Execution Time:** ~1-2 minutes

**Purpose:**
Sends comprehensive weekly summary report

**Report Contents:**

```
📊 WEEKLY SUMMARY REPORT
Week: 2025-11-11 to 2025-11-17
========================================

📈 WEEKLY PERFORMANCE
Total P&L: ₹75,000
Total Trades: 12
Winners: 8 (66.7%)
Losers: 4
Avg Winner: ₹15,000
Avg Loser: -₹8,000

🏆 TOP WINNERS:
1. RELIANCE - ₹25,000 (LLM_VALIDATED_FUTURES)
2. HDFCBANK - ₹18,000 (WEEKLY_NIFTY_STRANGLE)
3. TCS - ₹12,000 (LLM_VALIDATED_FUTURES)

📉 TOP LOSERS:
1. INFY - -₹12,000 (LLM_VALIDATED_FUTURES)
2. WIPRO - -₹8,000 (LLM_VALIDATED_FUTURES)
3. NIFTY - -₹5,000 (WEEKLY_NIFTY_STRANGLE)

📊 STRATEGY BREAKDOWN:
✅ LLM_VALIDATED_FUTURES: ₹45,000 (8 trades)
✅ WEEKLY_NIFTY_STRANGLE: ₹30,000 (4 trades)
```

---

## Task Schedules Summary

### Quick Reference Table

| Task Name | Queue | Frequency | Time | Duration |
|-----------|-------|-----------|------|----------|
| `fetch_trendlyne_data` | data | Daily | 8:30 AM | 2-5 min |
| `import_trendlyne_data` | data | Daily | 9:00 AM | 3-7 min |
| `update_pre_market_data` | data | Daily (Mon-Fri) | 8:30 AM | 1-2 min |
| `update_live_market_data` | data | Every 5 min | 9:00-15:30 | 30-60 sec |
| `update_post_market_data` | data | Daily (Mon-Fri) | 3:30 PM | 3-5 min |
| `evaluate_kotak_strangle_entry` | strategies | Mon & Tue | 10:00 AM | 2-4 min |
| `evaluate_kotak_strangle_exit` | strategies | Thu & Fri | 3:15 PM | 1-2 min |
| `monitor_all_strangle_deltas` | monitoring | Every 5 min | 9:00-15:30 | 10-30 sec |
| `screen_futures_opportunities` | strategies | Every 30 min | 9:00-14:30 | 5-10 min |
| `check_futures_averaging` | monitoring | Every 10 min | 9:00-15:30 | 20-40 sec |
| `monitor_all_positions` | monitoring | Every 10 sec | Market hours | <5 sec |
| `update_position_pnl` | monitoring | Every 15 sec | Always | <10 sec |
| `check_exit_conditions` | monitoring | Every 30 sec | Always | 5-15 sec |
| `check_risk_limits_all_accounts` | risk | Every 1 min | Always | 10-30 sec |
| `monitor_circuit_breakers` | risk | Every 30 sec | Always | <10 sec |
| `generate_daily_risk_report` | reports | Daily | 6:00 PM | 30-60 sec |
| `generate_daily_pnl_report` | reports | Daily (Mon-Fri) | 4:00 PM | 30-60 sec |
| `update_learning_patterns` | reports | Daily (Mon-Fri) | 5:00 PM | 2-5 min |
| `send_weekly_summary` | reports | Friday | 6:00 PM | 1-2 min |

---

## Task Dependencies

### Morning Sequence (8:30 AM - 10:00 AM)

```
8:30 AM  fetch_trendlyne_data (2-5 min)
            ↓
8:30 AM  update_pre_market_data (parallel, 1-2 min)
            ↓
9:00 AM  import_trendlyne_data (requires fetch complete, 3-7 min)
            ↓
9:00 AM  update_live_market_data starts (every 5 min)
            ↓
9:00 AM  screen_futures_opportunities starts (every 30 min)
            ↓
10:00 AM evaluate_kotak_strangle_entry (Mon/Tue only)
```

### During Market Hours (9:00 AM - 3:30 PM)

**Continuous Tasks:**
- `monitor_all_positions` (every 10 sec)
- `update_position_pnl` (every 15 sec)
- `check_exit_conditions` (every 30 sec)
- `monitor_circuit_breakers` (every 30 sec)
- `check_risk_limits_all_accounts` (every 1 min)
- `update_live_market_data` (every 5 min)
- `monitor_all_strangle_deltas` (every 5 min)
- `check_futures_averaging` (every 10 min)
- `screen_futures_opportunities` (every 30 min)

### End of Day (3:15 PM - 6:00 PM)

```
3:15 PM  evaluate_kotak_strangle_exit (Thu/Fri only)
            ↓
3:30 PM  update_post_market_data
            ↓
4:00 PM  generate_daily_pnl_report
            ↓
5:00 PM  update_learning_patterns
            ↓
6:00 PM  generate_daily_risk_report
            ↓
6:00 PM  send_weekly_summary (Friday only)
```

---

## Troubleshooting

### Common Issues

#### 1. Task Not Executing

**Check:**
```bash
# Check if Celery worker is running
ps aux | grep celery

# Check if Celery Beat is running
ps aux | grep celery-beat

# Check task in queue
redis-cli
> LLEN celery

# Check for errors
tail -f logs/celery_worker.log
tail -f logs/celery_beat.log
```

**Solutions:**
- Restart Celery worker: `sudo systemctl restart celery-worker`
- Restart Celery Beat: `sudo systemctl restart celery-beat`
- Check Redis: `redis-cli ping` (should return PONG)

---

#### 2. Task Timeout

**Symptoms:**
- Task shows as "PENDING" indefinitely
- Logs show "SoftTimeLimitExceeded"

**Solutions:**
- Increase task time limit in `celery.py`
- Optimize task code
- Break into smaller sub-tasks

---

#### 3. Memory Leaks

**Symptoms:**
- Worker memory grows over time
- Worker becomes unresponsive

**Solutions:**
- Workers auto-restart after 1000 tasks (already configured)
- Monitor: `ps aux | grep celery | awk '{print $6}'`
- Manual restart if needed

---

#### 4. Missing Scheduled Tasks

**Check Beat Schedule:**
```bash
# View loaded schedule
celery -A mcube_ai inspect scheduled

# Check beat log
tail -f logs/celery_beat.log
```

**Solutions:**
- Verify task is in `celery.py` beat schedule
- Restart Celery Beat
- Check timezone settings (`Asia/Kolkata`)

---

## Performance Monitoring

### Key Metrics

1. **Task Execution Time:**
   - Monitor via Celery Flower: `http://localhost:5555`
   - Check task duration in logs

2. **Queue Length:**
   ```bash
   redis-cli LLEN celery
   redis-cli LLEN celery:data
   redis-cli LLEN celery:monitoring
   ```

3. **Worker Utilization:**
   ```bash
   celery -A mcube_ai inspect active
   celery -A mcube_ai inspect stats
   ```

4. **Failed Tasks:**
   ```bash
   celery -A mcube_ai inspect registered
   celery -A mcube_ai purge  # Clear all tasks (careful!)
   ```

---

## Best Practices

1. **Always check logs** before debugging
2. **Monitor Redis memory** usage
3. **Use task retries** for transient failures
4. **Separate long-running tasks** into dedicated queues
5. **Set appropriate timeouts** for each task type
6. **Monitor Telegram alerts** for critical failures

---

**End of Celery Tasks Reference**
