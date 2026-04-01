# mCube AI — Comprehensive Algorithmic Trading System Review

**Date:** 2026-03-23
**Scope:** Full quantitative/strategic audit — architecture, algorithms, options evaluation, backtesting, risk metrics, capital efficiency, operational constraints
**Capital Under Management:** Rs.7.2 Cr (Kotak Rs.6 Cr options + ICICI Rs.1.2 Cr futures)
**Target:** Rs.12-14L/month (~2% monthly return)
**Verification:** 115 claims verified against source code (93.0% confirmed). All code snippets include exact file:line references. See `VERIFICATION_REPORT.md` for full audit trail.

---

## Table of Contents

1. [System Architecture Review](#section-1-system-architecture-review)
2. [Deep Dive — Kotak Strangle (Options)](#section-2-deep-dive--kotak-strangle-options-neutral)
3. [Deep Dive — ICICI Futures (Directional)](#section-3-deep-dive--icici-futures-directional)
4. [Deep Dive — S/R Exit Engine & Position Management](#section-4-deep-dive--sr-exit-engine--position-management)
5. [Options-Specific Evaluation](#section-5-options-specific-evaluation)
6. [Backtesting & Data Integrity](#section-6-backtesting--data-integrity)
7. [Performance & Risk Metrics](#section-7-performance--risk-metrics)
8. [Capital Efficiency & Portfolio Construction](#section-8-capital-efficiency--portfolio-construction)
9. [Operational & Real-World Constraints](#section-9-operational--real-world-constraints)
10. [Consolidated Priority Matrix](#consolidated-priority-matrix)

---

## Section 1: System Architecture Review

### Architecture Overview

mCube AI is a Django 4.2 + Celery + Redis + SQLite monolith deployed as a single-server trading platform. The system decomposes into **11 Django apps**: core, accounts, positions, strategies, risk, data, llm, analytics, alerts, brokers, trading — plus an `algo_test` app for manual testing.

#### Data Flow Pipeline

```
Trendlyne CSVs (7:00 AM fetch → 8:50 AM import)
    → ContractData, ContractStockData, TLStockData models
    → Pre-market data update (8:50 AM)
    → Live market data refresh (every 5 min, 9:15 AM–3:30 PM)
    → Post-market full refresh (3:35 PM)
    → EOD aggregation (4:30 PM)
```

#### Task Scheduling Architecture

**28 static Celery tasks** across **6 queues** with a custom `DBReloadScheduler`:

| Queue | Tasks | Frequency |
|-------|-------|-----------|
| `risk` | health-check-brokers, check-risk-limits, monitor-circuit-breakers | Pre-market + every 1 min |
| `data` | morning-data-sync, pre-market, live-market, post-market | Scheduled + every 5 min |
| `strategies` | evaluate-options, screen-futures, execute-futures, start-options, batch-averaging, delta-monitor | 9:30–10:30 AM + every 5–15 min |
| `monitoring` | **monitor-and-manage-positions**, check-confirmations, review-overnight, alert-pre-close, reconcile-eod | **Every 1 min** + scheduled |
| `reports` | daily-pnl-report, sync-benchmark, daily-aggregation, equity-curves | EOD 4:00–5:00 PM |
| `alerts` | flush-notification-buffer | Periodic |

**High-frequency core loop:** `monitor-and-manage-positions` runs every minute 9:00 AM–3:59 PM, performing broker sync → P&L calculation → SR engine evaluation → exit condition checks → notification dispatch.

#### Distributed Lock Pattern

```python
# apps/positions/tasks.py
_MONITOR_LOCK_KEY = 'monitor_and_manage_positions_lock'
_MONITOR_LOCK_TTL = 55  # seconds (just under 1-min beat)
acquired = cache.add(_MONITOR_LOCK_KEY, '1', timeout=_MONITOR_LOCK_TTL)
```

Uses Redis `cache.add()` (atomic SET-if-not-exists) with 55s TTL. Cleanup via `cache.delete()` in `finally` block. Broker sync failures tracked with 3-strike escalation (10-min TTL).

#### Task Enablement

All tasks governed by `CeleryTaskState` model — **default is DISABLED**. Each task must be explicitly enabled in DB. Supports custom schedule overrides (crontab/interval/recurring) per task.

### Strengths

- **Clean separation of concerns** — 6 queues isolate risk, data, strategy, monitoring, reporting workloads
- **Dynamic task scheduling** — tasks can be enabled/disabled via DB without code deploy
- **Unified notification framework** — `notify()` API with template registry, aggregation buffer, escalation tracker replaces raw Telegram calls
- **Singleton config pattern** — `TradingCoreConfig` ensures consistent behavior across all concurrent tasks
- **NseFlag runtime state** — lightweight key-value store for trading flags avoids heavy model queries
- **Broker sync failure tracking** — 3-strike escalation with auto-notification prevents silent failures
- **Task execution logging** — `TaskExecutionLog` records duration, status, result summary for every task run
- **WAL mode SQLite** — `PRAGMA journal_mode=WAL` + `synchronous=NORMAL` enables concurrent reads

### Weaknesses

- **[CRITICAL] SQLite under concurrent Celery workers** — 6 queues with 4+ tasks/minute writing to a single 42 MB SQLite file. WAL mode helps read concurrency but serializes ALL writes. Under sustained load (monitor + risk + data tasks simultaneously), `database is locked` errors are likely. The 30s timeout mitigates but doesn't eliminate contention. `apps/positions/tasks.py`, `apps/risk/services/risk_manager.py`
- **[CRITICAL] No test coverage for critical paths** — Only 349 LOC of tests across entire codebase. Zero tests for position monitoring, SR exit engine, distributed locking, broker integration, risk limits, data pipeline. A live trading system managing Rs.7.2 Cr has no automated safety net. `apps/algo_test/tests.py` (78 lines), `apps/trading/tests.py` (269 lines), `apps/brokers/tests.py` (empty)
- **[HIGH] Redis single point of failure** — Celery broker (DB 0), result backend (DB 1), distributed locks, cache, aggregation buffer all on `localhost:6379`. No sentinel, no replication, no persistence guarantees. Redis crash = all tasks stop + locks lost + overlapping monitor cycles. `mcube_ai/settings.py`
- **[HIGH] No CI/CD pipeline** — No `.github/`, `Jenkinsfile`, `.gitlab-ci.yml`, `Makefile`, `tox.ini`, `pytest.ini`. Code deploys are manual with no automated testing gate
- **[MEDIUM] 5-minute hard task limit vs broker latency** — `task_time_limit=300s`, `task_soft_time_limit=240s`. Monitor task syncs from 2 brokers (5-30s each) + SR engine per position. With 4+ positions: ~40-50s broker sync + SR computation could approach soft limit. `mcube_ai/celery.py:527-549`
- **[MEDIUM] Task enablement default = disabled** — After DB reset/migration, all 28 tasks are off. No startup verification or health check confirms expected tasks are running
- **[LOW] Telegram bot token in settings** — Should be environment variable only. `mcube_ai/settings.py`

### Recommended Changes

1. **[P1, Medium effort] Migrate to PostgreSQL** — SQLite is fundamentally wrong for concurrent write workloads. PostgreSQL with connection pooling (pgbouncer) eliminates write contention. Migration path: `django-admin dumpdata` → swap `DATABASES` engine → `loaddata`. Keep SQLite for local dev only
2. **[P1, High effort] Build test suite for critical paths** — Priority: position monitoring loop, SR exit engine trigger logic, risk limit enforcement, broker sync error handling. Target 80% coverage on `apps/positions/`, `apps/risk/`, `apps/trading/`
3. **[P2, Low effort] Add Redis sentinel or Valkey cluster** — At minimum, enable Redis persistence (`appendonly yes`, `appendfsync everysec`). Ideally deploy Redis Sentinel for automatic failover
4. **[P2, Medium effort] Implement CI/CD** — GitHub Actions: lint → test → type-check on every push. Block merge on test failure. Add pre-commit hooks for formatting
5. **[P3, Low effort] Add task health monitoring** — Startup check that verifies expected tasks are enabled. Periodic heartbeat task that alerts if critical tasks haven't run in expected window
6. **[P3, Low effort] Move all secrets to environment variables** — Telegram token, broker credentials, LLM endpoint — all via `.env` with `python-decouple` or `django-environ`

---

## Section 2: Deep Dive — Kotak Strangle (Options, Neutral)

### Strategy Overview

Short weekly Nifty OTM strangle selling theta decay. Entry Monday-Wednesday 9:00-11:30 AM, exit Thursday EOD (50% profit) or mandatory Friday close. One position per account.

### Entry Pipeline

1. **Enhanced analysis** — 11-factor scoring (275 pts → 100 scale), minimum 50/100 to proceed
2. **Hard reject filters** — 9 gates (VIX <10 or >18, gap >1.5%, FII outflow >Rs.2000 Cr, etc.)
3. **4-step strike adjustment:**
   - Base: `calculate_strangle_strikes()` with VIX + delta adjustments
   - S/R proximity: move 50 pts away if within 100 pts of support/resistance
   - Premium targeting: iterate up to 5× moving strikes 50-100 pts to hit 3.0-3.5 INR target (floor 1.75 INR)
   - Liquidity check: OI >= 100,000 (warning only, non-blocking)

### Strike Distance Formula (CRITICAL)

**File:** `apps/strategies/services/strangle_delta_algorithm.py:446`

```python
# Verified exact code at line 446:
strike_distance = self.spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(self.days_to_expiry))

# Same formula in shared/strike_calculator.py:477:
base_strike_distance = spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(days_to_expiry))
```

The adjusted delta is computed as (lines 397-405):
```python
self.adjusted_delta = (
    self.base_delta *          # Factor 1: 0.75% (≤2 DTE) or 0.5% (>2 DTE)
    self.vix_adjustment *      # Factor 2: 0.9×–2.0× (see VIX buckets)
    self.trend_adjustment *    # Factor 3: 1.0–1.05×
    self.volatility_adjustment * # Factor 4: 0.95–1.15×
    self.oi_adjustment *       # Factor 5: 1.0–1.1×
    self.pcr_adjustment *      # Factor 6: 1.0–1.05×
    self.news_adjustment       # Factor 7: 1.0–1.15×
)
```

Base delta (lines 46-52): `0.75%` for ≤2 DTE, `0.5%` for >2 DTE. Final strikes rounded to nearest 50 (lines 484-485): `int(round((spot + call_distance) / 50) * 50)`.

**Problem:** This is **linear in DTE**. Option price sensitivity scales with **sqrt(T)**, not T. For a 5-day expiry, this formula produces 5× the base distance, while sqrt(5) ≈ 2.24× would be correct. The result: systematically overshooting strike distance for longer DTE, leading to lower premium collection and sub-optimal capital utilization.

### VIX Multiplier Discontinuities (CRITICAL)

**File:** `apps/strategies/services/strangle_delta_algorithm.py:89-103`

```python
if vix_val < 10:           # Line 89-90
    adj = Decimal('0.9')
elif vix_val < 12.5:       # Line 92-93
    adj = Decimal('1.0')
elif vix_val < 14:         # Line 95-96  ← 50% JUMP
    adj = Decimal('1.5')
elif vix_val < 18:         # Line 98-99
    adj = Decimal('1.8')
else:                      # Line 102-103
    adj = Decimal('2.0')
```

| VIX Range | Multiplier | Jump at Boundary |
|-----------|-----------|------------------|
| < 10 | 0.9× | — |
| 10–12.5 | 1.0× | +11% at VIX=10 |
| **12.5–14** | **1.5×** | **+50% at VIX=12.5** |
| 14–18 | 1.8× | +20% at VIX=14 |
| > 18 | 2.0× | +11% at VIX=18 |

The 1.0× → 1.5× jump at VIX=12.5 means a trivial VIX change (12.4 → 12.6) produces a **50% wider strike distance**. This creates unstable behavior at boundary values — the strategy may flip between tight and wide strikes on noise.

**Note:** The `market_condition_validator.py` uses different VIX boundaries (10, 11.5, 12.5, 14) for classification vs the delta algorithm (10, 12.5, 14, 18). This inconsistency means a VIX of 11.5 is classified as "LOW" by the validator but gets the same 1.0× multiplier as "NORMAL" in the delta algorithm.

### 11-Factor Scoring System

**File:** `apps/strategies/analyzers/enhanced_strangle_analyzer.py:71-85`

| Component | Weight (pts) | % of Total |
|-----------|-------------|------------|
| VIX Regime | 35 | 12.7% |
| Global Markets Sentiment | 30 | 10.9% |
| Market Breadth | 25 | 9.1% |
| News Sentiment | 30 | 10.9% |
| PCR Analysis | 25 | 9.1% |
| OI Patterns | 25 | 9.1% |
| Economic Event Proximity | 20 | 7.3% |
| Gap & Movement Analysis | 25 | 9.1% |
| Recent Nifty Momentum | 25 | 9.1% |
| FII/DII Flow | 20 | 7.3% |
| Technical Structure | 15 | 5.5% |
| **Total** | **275** | **100%** |

Sweet spot: VIX 12-14 scores 35/35 (100%). Entry threshold: 50/100.

### Position Sizing

**File:** `apps/trading/services/strangle_position_sizer.py:36`

```python
NIFTY_LOT_SIZE = Decimal('50')
```

**Margin calculation:** Higher_strike × 50 × 16% = margin per lot. Uses 50% margin utilization, 15% reserve buffer.

**Averaging protocol (lines 24-30):**
- Attempt 1: 20% of current balance at 1% loss trigger
- Attempt 2: 50% of remaining
- Attempt 3: 50% of remaining

### Hard Reject Filters

**File:** `apps/strategies/analyzers/enhanced_strangle_analyzer.py:54-64`

| Filter | Reject Condition |
|--------|-----------------|
| VIX | < 10 or > 18 |
| News sentiment | < -0.4 |
| Market gap | > 1.5% |
| FII 3-day outflow | > Rs.2000 Cr |
| 9:15-9:30 movement | > 0.5% |
| Nifty 1-day change | > ±1.5% |
| Nifty 3-day change | > ±2.5% |
| Nifty 5-day change | > ±3.0% (skip entire week) |
| Major economic event | Within 2 days |

### Strengths

- **Multi-factor delta adjustment** — 7 independent factors (VIX, trend, realized vol, OI, PCR, news) adjust strike distance dynamically rather than using fixed OTM percentage
- **4-step strike refinement** — Base → S/R avoidance → premium targeting → liquidity check provides layered safety
- **Premium targeting with floor** — 3.0-3.5 INR target with 1.75 INR safety floor prevents selling worthless options
- **Comprehensive hard reject filters** — 9 gates (8 hard rejects + 1 warning) prevent entry during adverse conditions (events, extreme moves, unfavorable VIX)
- **S/R proximity adjustment** — Moves strikes away from key levels where option selling is riskier
- **Consecutive red days rule** — Widens PUT strike after 3+ consecutive red days

### Weaknesses

- **[CRITICAL] Strike distance linear in DTE** — `spot × delta% × DTE` vs correct `spot × delta% × sqrt(DTE)`. For 5-day expiry, overshoots by ~2.2×. For 1 DTE, correct. Systematically produces wider-than-necessary strikes for Mon/Tue entries. `strangle_delta_algorithm.py:446`
- **[CRITICAL] NIFTY lot size hardcoded wrong** — `NIFTY_LOT_SIZE = 50` but current Nifty lot size is **65** (changed by NSE). This means position sizing calculates 50-unit lots when actual lots are 65 units — margin requirements are 30% understated. `strangle_position_sizer.py:36`
- **[CRITICAL] VIX multiplier has 50% discontinuity** — VIX crossing 12.5 causes 1.0× → 1.5× jump. A 0.2-point VIX fluctuation can swing strike distance by 50%. Should use continuous function. `strangle_delta_algorithm.py:90-96`
- **[HIGH] No gamma monitoring** — For a short weekly options strategy, gamma exposure is the dominant risk near expiry (Thursday/Friday). The system monitors only delta (and that crudely — see Section 5). Gamma blow-up on Thursday afternoon is the #1 risk to this strategy and is completely unmonitored. `delta_monitor.py`
- **[HIGH] Averaging protocol increases exposure into losing trades** — 20%, 50%, 50% at 1% loss trigger is pro-cyclical: adds to losing positions. An anti-martingale approach (reduce size on losses) would be safer for a theta strategy
- **[HIGH] No rolling logic** — Position expires or is closed, never rolled to next week. Rolling (closing current + opening next week) can preserve premium and reduce gamma risk vs holding to expiry
- **[MEDIUM] Binary hard reject gates** — All-or-nothing filters with no gradual degradation. VIX at 9.9 → full reject; VIX at 10.1 → full pass. No intermediate caution zones
- **[MEDIUM] One-position-per-account constraint** — Capital sits idle ~3 days/week (entry Mon-Wed, exit Thu-Fri). No staggered entries or multi-expiry positions
- **[LOW] Liquidity check is warning-only** — OI >= 100,000 threshold generates a warning but doesn't block entry. In low-liquidity strikes, this could lead to significant slippage

### Recommended Changes

1. **[P1, Low effort] Fix lot size** — Replace `NIFTY_LOT_SIZE = 50` with dynamic fetch from `ContractData.objects.filter(symbol='NIFTY').first().lot_size` (Trendlyne-imported daily). Keep hardcoded 65 as fallback only. `strangle_position_sizer.py:36`
2. **[P1, Low effort] Fix strike distance formula** — Change `× days_to_expiry` to `× sqrt(days_to_expiry)`. One line change. `strangle_delta_algorithm.py:446`
3. **[P1, Low effort] Smooth VIX multiplier** — Replace discrete buckets with continuous function: `multiplier = 0.8 + 0.08 × VIX` (clamped [0.9, 2.0]). Or use linear interpolation between current breakpoints. `strangle_delta_algorithm.py:72-113`
4. **[P1, Medium effort] Add gamma monitoring** — Use existing `greeks_calculator.py` BS implementation to compute position gamma. Alert when gamma × expected_move_1SD > threshold (e.g., 5% of premium collected). Especially critical Thu/Fri
5. **[P2, Medium effort] Implement rolling logic** — When position approaches Thu EOD with < 50% profit, auto-evaluate roll to next week instead of hold/close binary
6. **[P2, Low effort] Convert averaging to anti-martingale** — Reduce lot count (not increase) when position is losing. Or at minimum, cap averaging to 1 attempt instead of 3
7. **[P3, Medium effort] Add staggered entries** — Allow 2 positions with different expiries to reduce idle capital

---

## Section 3: Deep Dive — ICICI Futures (Directional)

### Strategy Overview

13-component quantitative scoring for directional stock futures. Entry 9:15 AM–3:00 PM, minimum 15 DTE, 50% margin utilization, one position per account. LLM validation gate (confidence threshold not explicitly enforced in validator code — may be in calling strategy).

### 13-Component Scoring System (315 pts → 100 scale)

**File:** `apps/strategies/analyzers/enhanced_futures_analyzer.py`

| # | Component | Max Pts | % Weight | Sub-Components |
|---|-----------|---------|----------|----------------|
| 1 | OI & F&O Analysis | 45 | 14.3% | OI Buildup (20), PCR (10), MWPL (5), Rollover (10) |
| 2 | Technical Momentum | 35 | 11.1% | RSI (5), MACD (10), MFI (5), ADX (10), ROC (5) |
| 3 | Trend Confirmation | 30 | 9.5% | DMA Position (10), Price Range (10), Breakout (5), 52W (5) |
| 4 | Volume Quality | 25 | 7.9% | Volume Surge (10), Delivery % (5), VWAP (5), Delivery Trend (5) |
| 5 | Institutional Flow | 25 | 7.9% | FII (10), MF (5), Promoter (5), Total Institutional (5) |
| 6 | Fundamental Quality | 20 | 6.3% | Piotroski (10), Profit Growth (5), ROE (5) |
| 7 | Risk Adjustment | 30 | 9.5% | Beta (10), Volatility (10), Valuation (10) |
| 8 | News Sentiment | 25 | 7.9% | Stock News (15), Market News (5), Sector News (5) |
| 9 | Analyst Consensus | 20 | 6.3% | Upside % (10), Rec Ratio (5), Coverage (5) |
| 10 | Research Reports | 15 | 4.8% | Report Sentiment (10), Risk/Catalysts (5) |
| 11 | Investor Calls | 10 | 3.2% | Management Tone (5), Trading Signal (5) |
| 12 | Momentum Acceleration | 20 | 6.3% | Acceleration Pattern (10), Consistency (5), Direction (5) |
| 13 | MTF Confluence | 15 | 4.8% | Weekly (5), Monthly (5), Short-term (5) |

**Normalization:** `composite_score = (raw / 315) × 100`. Passing threshold: **65/100**.

**Recommendation tiers:** 80+ = STRONG_ENTRY, 65-79 = ENTRY, 50-64 = WEAK_ENTRY, <50 = NO_ENTRY.

### Hard Reject Filters (6 Hard Rejects + 1 Soft Warning)

**File:** `apps/strategies/analyzers/enhanced_futures_analyzer.py:239-515`

| Filter | Threshold | Type |
|--------|-----------|------|
| MWPL | < 80% | **Hard reject** — near ban risk |
| Volatility | < 60% annualized | **Hard reject** — too volatile |
| Piotroski F-Score | ≥ 4 | **Hard reject** — weak fundamentals (< 4). Graduated scoring above threshold: ≥7=10pts, ≥5=6pts, ≥4=3pts |
| Promoter Pledge | < 30% | **Hard reject** — financial stress (≥ 30%) |
| FII Change QoQ | > -2% | **Hard reject** — institutional exodus (≤ -2%) |
| News Sentiment | Negative market | **Soft warning only** — logs but does NOT reject (proceeds with caution flag) |
| Analyst Upside (LONG) | ≥ 8% | **Hard reject** — insufficient upside |

### Adaptive SL/Target — 3-Tier Fallback

**File:** `apps/strategies/services/adaptive_sl_target.py`

| Tier | Source | SL Logic | Target Logic |
|------|--------|----------|-------------|
| 1. S/R-Based | SR exit engine | SR_SL ± ATR buffer (0.3-0.5× ATR by score) | SR_TGT ± ATR buffer |
| 2. ATR-Adaptive | Market regime | price ± regime_mult × ATR | price ± regime_mult × ATR |
| 3. Vol%-Scaled | Annualized volatility | 1.5%-3.5% scaled by vol/30 | 2× SL distance |

**Regime multipliers (Tier 2):**

| Regime | SL Multiplier | Target Multiplier |
|--------|--------------|-------------------|
| TRENDING | 1.5× ATR | 3.0× ATR |
| RANGING | 1.0× ATR | 2.0× ATR |
| VOLATILE | 2.0× ATR | 3.5× ATR |
| BREAKOUT | 1.2× ATR | 3.0× ATR |
| NORMAL | 2.0× ATR | 2.0× ATR |

**Post-tier adjustments:** S1/R1 tightening (LONG: S1 × 0.995, SHORT: R1 × 1.005), dual targets (Target_2 = 1.5× stretch), R:R gate (flagged if < min_rr, default 1.5). Note: Hard R:R < 1.0 reject is in `trade_validation.py:44`, not in the SL/target module.

### Market Regime Detection

**File:** `apps/strategies/services/market_regime.py:110-135`

Priority ordering: **VOLATILE > BREAKOUT > TRENDING > RANGING > NORMAL**

| Regime | Conditions | Confidence Base |
|--------|-----------|----------------|
| VOLATILE | ATR expansion > 1.5× AND VIX > 16 | 60% (+10% per additional threshold) |
| BREAKOUT | ADX 20-30 | 60% |
| TRENDING | ADX > 25, ATR exp < 1.3×, VIX < 18 | 60% |
| RANGING | ADX < 20, ATR exp < 1.0× | 60% |
| NORMAL | Default fallback | 50% |

### LLM Validation Gate

**File:** `apps/llm/services/trade_validator.py`

- Model: `deepseek-r1:7b` via Ollama (localhost:11434)
- Confidence threshold: **Not explicitly enforced in trade_validator.py** — confidence is extracted from LLM response (default fallback: 50%) but no hard gate was found in the validator itself. May be enforced by the calling strategy code
- Context: regime, scoring breakdown, risk profile, signals, warnings
- Fallback: if LLM down → `error_result` with `approved: False` (trade blocked, **no score-only fallback**)
- If vector store unavailable → LLM-only validation (no RAG context)

### Strengths

- **Comprehensive multi-factor scoring** — 13 components covering fundamentals, technicals, institutional flows, sentiment, momentum, and multi-timeframe alignment provide holistic stock assessment
- **Hard reject filters** — 6 hard rejects + 1 soft warning prevent entry on structurally unsound stocks (high MWPL, weak Piotroski, promoter pledge stress)
- **3-tier adaptive SL/target** — Graceful fallback from structural (S/R) to statistical (ATR) to percentage-based, ensuring every trade has defined risk
- **Regime-aware parameters** — SL/target multipliers adapt to market conditions (wider in volatile, tighter in ranging)
- **R:R gate** — Hard reject below 1.0 prevents negative-expectancy entries
- **Phased component rollout** — Components 12 (Momentum Acceleration) and 13 (MTF Confluence) marked as Phase 2/3, showing disciplined feature progression
- **Dual targets** — Base target + 1.5× stretch target allows partial booking

### Weaknesses

- **[HIGH] 13-component weights are heuristic, not empirically calibrated** — No evidence of weight optimization against historical outcomes. Risk of spurious signal aggregation where noise from 13 loosely-correlated factors dominates signal. OI & F&O (45 pts, 14.3%) is weighted highest but may not be the strongest predictor. `enhanced_futures_analyzer.py:88`
- **[HIGH] LLM validation gate introduces model risk** — `deepseek-r1:7b` is a small model that may hallucinate confidence scores. Confidence threshold not explicitly enforced in `trade_validator.py` (extracted but no hard gate found). If LLM is down, returns `error_result` with `approved: False` — all trades are blocked with no score-only fallback. Single point of failure for the entire futures strategy. `trade_validator.py`
- **[HIGH] Binary hard reject gates** — Piotroski < 4 → reject, ≥ 4 → pass. While scoring IS graduated above the threshold (≥7=10pts, ≥5=6pts, ≥4=3pts), there is no compensating mechanism below it. A stock with Piotroski 3 but stellar technicals and institutional buying is rejected outright
- **[MEDIUM] RSI dead zone filter (45-55) in prefilter** — Excludes stocks in consolidation. Legitimate consolidation-breakout setups (ADX rising from low, RSI neutral) are filtered out before scoring begins. `contract_prefilter.py:79-82`
- **[MEDIUM] One-position-per-account** — Rs.1.2 Cr is fully deployed or idle. No partial allocation, no portfolio of 2-3 positions to diversify single-stock risk
- **[MEDIUM] Sector alignment requires ALL timeframes** — 3D, 7D, and 21D must all support direction. Overly restrictive: a strong 3D reversal in a weak 21D sector (sector rotation play) is rejected. `icici_futures.py:631-640`
- **[MEDIUM] No component redundancy analysis** — RSI appears in both prefilter AND Technical Momentum scoring. MACD and MFI are correlated with RSI. ADX appears in prefilter, regime detection, AND scoring. Redundant signals inflate confidence without adding information
- **[LOW] Regime detection uses only ADX + ATR + VIX** — No volume regime (accumulation/distribution), no cross-asset correlation, no volatility term structure

### Recommended Changes

1. **[P1, Medium effort] Add LLM fallback** — When LLM is down, fall back to score-only with a higher threshold (e.g., 75 instead of 65). Never block all trades on LLM failure. `trade_validator.py`
2. **[P2, High effort] Calibrate component weights** — Run historical attribution: for each closed trade, decompose which components predicted the outcome. Use logistic regression or gradient boosting to find optimal weights. Even a simple correlation analysis would improve on heuristic weights
3. **[P2, Low effort] Soften hard reject gates** — Replace binary Piotroski gate with scoring penalty: Piotroski < 4 → -15 pts instead of outright rejection. Keep MWPL > 80% as hard reject (regulatory risk)
4. **[P2, Low effort] Relax RSI dead zone** — Remove from prefilter; let the full scoring system evaluate consolidating stocks. ADX already captures trend strength
5. **[P3, Medium effort] Remove component redundancy** — Deduplicate RSI/ADX across prefilter, regime, and scoring. Each factor should influence the decision in exactly one place
6. **[P3, Low effort] Allow 2-position portfolio** — Split Rs.1.2 Cr into 2 × Rs.60L positions. Diversifies single-stock risk, improves capital utilization

---

## Section 4: Deep Dive — S/R Exit Engine & Position Management

### Architecture Overview

The S/R Exit Engine is a multi-factor support/resistance system that manages stop-loss and target calculations. It operates as the primary exit decision maker, called once per position per minute during market hours.

**Public API:** `apply_sl_and_target(position, dashboard, now)` → returns `{sl_triggered, sl_reason, structural_pressure}`

#### Core Components

```
SRExitEngine.evaluate()
├── _update_volatility_event_flag()
├── MultiFactorSRCalculator.compute_enhanced()
│   ├── compute() — 8-source weighted SR
│   ├── MTFSREnricher.compute_mtf_stacking()
│   ├── OrderBlockDetector.detect_blocks()
│   ├── OIWallEnricher.compute_walls()
│   └── LevelStrengthAnnotator.annotate()
├── GapDownFilter.detect_gap()
├── SLTriggerChecker.should_trigger_sl()
│   ├── _check_long_sl() / _check_short_sl() / _check_neutral_sl()
│   └── StructuralPressureMonitor.check()
└── TargetCalculator.calculate()
```

### 8-Source Weighted S/R Calculator

| Source | Weight | Data |
|--------|--------|------|
| Pivot Points | 20% | S1/S2/S3, R1/R2/R3 |
| Previous Day H/L | 15% | Yesterday's high/low |
| Swing H/L | 15% | Last 20 bars, 5-min |
| VWAP & Bands | 15% | Intraday ±1σ, ±2σ |
| Moving Averages | 15% | MA20, MA50, MA100, MA200 |
| High Volume Nodes | 10% | Top 5 volume clusters |
| ATR Zones | 5% | price ± 1×ATR, ± 2×ATR |
| Psychological Levels | 5% | Round numbers, 100-pt bands |

Levels clustered within 0.3% → scores summed, weighted-average price used.

### Level Confidence Scorer (0–100)

| Component | Max Points | Criteria |
|-----------|-----------|----------|
| Source Agreement | 25 | # source types × 4 pts (max 6 types) |
| MTF Confluence | 20 | 5 pts per confirming timeframe (max 4 TFs) |
| Touch History | 20 | 5 pts per bounce (max 4, 20-day lookback) |
| OI Reinforcement | 15 | Proximity to gamma wall (<0.5% = 15, <1% = 8, <2% = 3) |
| Volume at Level | 10 | HVN concentration score × 3 |
| Recency Decay | 10 | Max 10, -2 pts per day since last touch |

### Score-Gated Trigger Rules

**Constants** (`sr_exit_engine.py:174-176`):
```python
SCORE_INSTITUTIONAL = 76    # single Condition A triggers
SCORE_STRONG = 56           # either A or B + 15-min
SCORE_MODERATE = 31         # both A+B required
```

| Score Range | Label | Trigger Requirement |
|-------------|-------|-------------------|
| 76–100 | Institutional | Condition A alone (price breaks level by cond_a_pct) |
| 56–75 | Strong | Either A or B + 15-min no-recovery |
| 31–55 | Moderate | Both A AND B |
| 0–30 | Weak | Both A AND B + 15-min no-recovery |

**Trigger logic** (verified at `sr_exit_engine.py:902-924` for LONG, `953-966` for SHORT):
```python
strict_mode = self._is_expiry_day_gamma_mode() or self._is_low_liquidity_day()

if level_score >= SCORE_INSTITUTIONAL and not strict_mode:
    triggered = True  # Condition A alone
elif level_score >= SCORE_STRONG and not strict_mode:
    triggered = cond_b or self._not_recovering_15min(level, 'LONG')
else:
    if not cond_b: return False, 'CONDITION_B_NOT_MET'
    if not self._not_recovering_15min(level, 'LONG'): return False, 'PRICE_RECOVERING_15MIN'
    triggered = True
```

**Strict mode** (expiry day before 14:00 via `EXPIRY_GAMMA_MODE_HOUR = 14` at line 179 / low-liquidity): Always requires both A+B regardless of score.

**ATR-adaptive thresholds** (`sr_exit_engine_utils.py:222-247`):
```python
cond_a = 0.3 * atr_pct           # clamped [0.003, 0.010]
cond_b = 2.0 * cond_a            # always 2× cond_a
# Backward compat: atr_pct=0 → (0.005, 0.010)
```

### 3-Stage Warning System

1. **NEAR_SL** — Buffer < 1% of SL (step 4 in tasks.py)
2. **STRUCTURAL_PRESSURE** — Condition A met, B pending (~5-min lead time, 10-min cooldown)
3. **TRIGGER** — Full conditions met → exit confirmation flow

### Strategy-Specific Adapters (Shadow-Run)

| Adapter | Strategy | Key Signals |
|---------|----------|------------|
| FuturesStrategyAdapter | LONG/SHORT | breakout_quality, conviction, trend_continuation |
| StrangleRangeGuard | NEUTRAL | range_integrity (S1/R1 both ≥40), early_breakout, premium_adj_leg |
| BrokenIronCondorGuard | NEUTRAL/BIC | range_stability_score, gamma_squeeze_risk, delta_hedge_suggestion |

All adapters are **shadow-run only** — produce signals and log to sr_eval but take no automatic action. Confirmed: `sr_strategy_adapter.py:1-16` docstring explicitly states "Signal dicts are added to sr_eval and logged, but have NO effect on the existing SL/target logic unless tasks.py explicitly reads them."

**Adaptive SL multipliers** (verified `sr_risk_interface.py:70-76`):
- Score > 70: 0.3×ATR (tight — high-confidence level)
- Score > 40: 0.5×ATR (standard)
- Score ≤ 40: 0.8×ATR (wide — noisy level)
- Vacuum proximity bonus: +0.05-0.5× if price near liquidity gap (`sr_risk_interface.py:94-117`)
- Structural pressure cooldown: 10 min (`sr_risk_interface.py:29-30`)
- Partial close advisor: 50% close when score 40-60 AND Cond A met AND Cond B not met (`sr_risk_interface.py:227-276`)

### Strengths

- **Confidence-scored exits** — Score-gated triggers replace brittle hardcoded thresholds. Institutional-quality levels trigger faster; weak levels require more confirmation
- **ATR-adaptive conditions** — Dynamic `scale_sl_conditions(atr_pct)` prevents false SL on high-vol days and catches real breaks on calm days
- **8-source weighted SR** — Combines structural (pivots, swing HL), statistical (VWAP, MAs), volume-based (HVN), and psychological levels for robust support/resistance
- **6-layer enrichment** — MTF confluence, order blocks, OI walls, strategy adapters, adaptive SL, structural pressure monitoring each add independent signal quality
- **Volatility event bypass** — price > 2×ATR spike bypasses structural SR logic, auto-clears after 3 calm candles. Prevents whipsaw exits during flash crashes
- **15-min recovery filter** — Confirms breakout is structural (15-min close still beyond level), not a false tick
- **Gap noise window** — 9:30-9:45 extension on gap days prevents false SL triggers from opening noise
- **Graceful degradation** — Each enrichment layer has independent cache and fallback. OI unavailable? Falls back to base 8-source. MTF stale? Continues without confluence data

### Weaknesses

- **[MEDIUM] 15-minute SR cache during fast moves** — Markets can move 1-2% in 15 minutes (especially options near expiry). Cached SR levels may be stale by the time they're used for trigger decisions. OI wall cache is 5 min (better) but base SR is 15 min. `sr_exit_engine.py`
- **[MEDIUM] Strategy adapters are shadow-run only** — FuturesStrategyAdapter, StrangleRangeGuard, BrokenIronCondorGuard produce valuable signals but don't influence actual exit decisions. The intelligence exists but isn't utilized
- **[MEDIUM] Session extremes not explicitly reset at day boundary** — `session_low`/`session_high` are sticky in tracker. For multi-day positions, previous day's extremes carry over. Not a problem if new positions start fresh, but edge case if position held overnight
- **[LOW] OI wall depends on daily ContractData updates** — If Trendlyne import fails, OI wall detection returns empty. Gracefully handled but reduces exit engine accuracy
- **[LOW] No maximum SR cache size** — `sr_tracking` JSONField grows with each enrichment layer. For long-running positions, this could become large (though practically limited to one trading day)

### Recommended Changes

1. **[P2, Medium effort] Reduce SR cache TTL to 5 min during last hour** — 14:30-15:30 is when intraday levels shift fastest. Reduce base SR cache from 15 min to 5 min for this window
2. **[P2, Medium effort] Activate strategy adapter signals** — Start with StrangleRangeGuard: if `range_integrity=False`, auto-tighten SL by 0.2×ATR. Graduate from shadow-run to advisory to automatic
3. **[P3, Low effort] Explicit session reset** — Add `tracker.reset_session()` call at 9:15 AM for overnight positions to clear stale extremes
4. **[P3, Low effort] Add real-time OI fallback** — If ContractData OI is stale (>4 hours), fetch live OI from broker API for gamma wall calculation

---

## Section 5: Options-Specific Evaluation

### Greeks Usage Assessment

#### What Exists vs. What's Used

| Capability | Implementation | Actually Used? |
|-----------|---------------|---------------|
| Black-Scholes pricing | `greeks_calculator.py` — full BS with NR IV estimation | Used in `nifty_data_fetcher.py` for option chain analysis |
| Delta calculation (BS) | `greeks_calculator.py:364-365` — proper N(d1) | **NOT used by delta monitor** |
| Delta monitoring | `delta_monitor.py:41-107` — crude moneyness buckets | **Primary risk metric** |
| Gamma calculation | `greeks_calculator.py:366` | **NOT used anywhere for monitoring** |
| Theta calculation | `greeks_calculator.py:368-369` | **NOT used for P&L attribution** |
| Vega calculation | `greeks_calculator.py:367` | **NOT used for risk management** |
| IV estimation | `greeks_calculator.py:255-312` — Newton-Raphson | Used in option chain |

### Delta Monitor — Crude Approximation (CRITICAL)

**File:** `apps/positions/services/delta_monitor.py:41-107`

The delta monitor uses **discrete moneyness buckets** (`moneyness = spot / strike` at line 71) instead of Black-Scholes:

**Call options (lines 73-88):**
| Line | Moneyness (spot/strike) | Assigned Delta |
|------|------------------------|---------------|
| 76 | > 1.02 (deep ITM) | 0.70 |
| 78 | > 1.00 (ATM) | 0.50 |
| 80 | > 0.98 (slightly OTM) | 0.40 |
| 82 | > 0.95 (OTM) | 0.25 |
| 84 | else (deep OTM) | 0.10 |

**Put options (lines 90-106):**
| Line | Moneyness | Assigned Delta |
|------|-----------|---------------|
| 93 | < 0.98 (deep ITM) | -0.70 |
| 95 | < 1.00 (ATM) | -0.50 |
| 97 | < 1.02 (slightly OTM) | -0.40 |
| 99 | < 1.05 (OTM) | -0.25 |
| 101 | else (deep OTM) | -0.10 |

**Line 64 TODO comment:**
```python
# TODO: Replace with proper Black-Scholes delta calculation using py_vollib
```

**No import of greeks_calculator** — the file imports only `logging`, `Decimal`, `Dict`, `timezone`, `Position`, `send_telegram_notification`, and `notify`. The BS calculator (`greeks_calculator.py`) exists but is only imported by `nifty_data_fetcher.py`.

**Impact:** This approximation has ~30-50% error compared to BS delta, especially for ATM options where actual delta varies continuously from 0.40-0.60 based on IV and time. For a short strangle strategy where delta monitoring is the primary risk metric, this error is significant.

**Alert threshold:** `delta_threshold: Decimal = Decimal('300')` (line 177). Net delta calculation: `net_delta = (call_delta × quantity) + (put_delta × quantity)` (line 152). DTE uses calendar days: `days_to_expiry = (position.expiry_date - timezone.now().date()).days` (line 132). With crude delta, this threshold itself is unreliable — the system may alert at actual net delta of 200 or miss alerts at actual 450.

### Calendar Days vs Trading Days

**File:** `apps/strategies/services/greeks_calculator.py`

The BS implementation uses calendar days for time-to-expiry (verified at lines 17-30 and 343):
```python
# greeks_calculator.py:17-30
def calculate_days_to_expiry(expiry_date: date) -> float:
    today = dt_date.today()
    days = (expiry_date - today).days
    return max(days, 0.001)  # Avoid zero days

# greeks_calculator.py:343
time_to_expiry = days / 365.0  # Calendar year, not trading days
```

The delta monitor also uses calendar days (`delta_monitor.py:132`):
```python
days_to_expiry = (position.expiry_date - timezone.now().date()).days
```

For a Friday expiry:
- Friday at 10 AM: T = 5 hours = 0.00057 years (calendar)
- But actual trading time: 5 hours = 1 trading day equivalent

On weekends: Saturday has DTE = 2 calendar days but 0 trading days. This introduces ~40% error in BS calculations over weekends, affecting:
- IV estimation (overstated on Friday afternoon)
- Delta (understated for near-ATM options on Friday)
- Theta (understated — actual daily theta is higher than calendar-adjusted)

Risk-free rate hardcoded at 6.5% (line 317): `risk_free_rate: float = 0.065  # 6.5% as of 2024-25`

### Missing Risk Dimensions

1. **No gamma monitoring** — For short weekly options, gamma is the dominant risk. Near expiry, gamma can cause delta to swing from 0.3 to 0.8 on a 50-point Nifty move. The system has no gamma threshold, no gamma P&L attribution, no gamma-adjusted delta projection

2. **No vega risk management** — VIX spikes increase premium on short options (adverse for seller). The system uses VIX for entry decisions but doesn't monitor vega exposure on open positions. A 3-point VIX spike on an open strangle could add Rs.2-3L of adverse mark-to-market

3. **No skew/smile modeling** — Strike selection is symmetric (same distance for call/put). Real-world Nifty has significant put skew — OTM puts are relatively more expensive than OTM calls. Symmetric strikes leave put premium higher than call, creating unbalanced risk

4. **No volatility surface awareness** — Flat vol assumption across strikes and expiries. The term structure (front-month IV vs back-month) and skew are not considered

5. **No dividend consideration in BS** — Nifty has implicit dividends from constituent stocks that affect option pricing. The BS model uses `risk_free_rate = 6.5%` but no dividend yield adjustment

### Iron Condor Insurance Risk

**File:** `apps/strategies/strategies/kotak_broken_iron_condor.py:270-345`

```
Risk Budget = Max Profit × 2.0 (default risk multiplier)
Insurance Strike = Put Strike - (Risk Budget / Quantity)
```

The insurance put distance depends solely on premium collected, not on how far OTM the insurance put ends up. A very wide strangle (low premium) would place insurance very close; a tight strangle (high premium) would place insurance far away — inverse of what's needed for tail protection.

### Strengths

- **Full BS implementation exists** — `greeks_calculator.py` has a correct Black-Scholes implementation with Newton-Raphson IV estimation. The capability exists; it's just not connected to monitoring
- **Delta monitoring alerts** — Even crude, the system does monitor net delta and sends alerts at threshold breach (300). Better than nothing
- **VIX-aware entry decisions** — VIX drives both hard reject filters (>18) and strike distance multipliers
- **Insurance option (Iron Condor)** — BIC strategy provides downside protection, addressing tail risk partially

### Weaknesses

- **[CRITICAL] Delta monitor uses crude approximation while BS exists** — `delta_monitor.py` uses 5-bucket moneyness approximation with ~30-50% error while `greeks_calculator.py` has a proper BS delta calculator. This is the primary risk metric for a strategy managing Rs.6 Cr in short options. The TODO comment at line 64 acknowledges this. `delta_monitor.py:41-107` vs `greeks_calculator.py:364-365`
- **[CRITICAL] No gamma monitoring** — Gamma is the dominant risk for short weekly options, especially Thu/Fri near expiry. Gamma blow-up can turn a Rs.2L profit into a Rs.10L loss in minutes. Completely unmonitored
- **[HIGH] Calendar days vs trading days** — ~40% error on weekends/holidays affects BS calculations for delta, IV, theta. Friday afternoon delta is systematically miscalculated
- **[HIGH] No vega risk management** — VIX spike of 3-5 points can add Rs.2-5L adverse mark-to-market on open short options. No monitoring, no threshold, no hedging
- **[HIGH] No skew/smile modeling** — Symmetric strike selection ignores Nifty put skew. Put premium is 20-40% higher than call at same delta — creates unbalanced exposure
- **[MEDIUM] BS model assumes lognormal returns** — Indian indices have fat tails, especially on event days (RBI policy, budget, global shocks). BS underestimates tail probabilities by 3-5×
- **[MEDIUM] Iron Condor insurance doesn't account for distance** — Risk budget based purely on premium × 2.0, not on actual tail exposure. `kotak_broken_iron_condor.py:270-345`
- **[LOW] Risk-free rate hardcoded at 6.5%** — `greeks_calculator.py:317`. Should track current T-bill rate

### Recommended Changes

1. **[P1, Low effort] Connect BS delta to monitor** — Replace moneyness buckets in `delta_monitor.py` with `greeks_calculator.calculate_greeks()`. The function exists; it just needs to be called. ~20 lines of code
2. **[P1, Medium effort] Add gamma monitoring** — Extend delta monitor to compute and track position gamma. Alert when `gamma × lot_size × expected_1SD_move > X%` of premium collected. Use existing BS calculator
3. **[P1, Low effort] Switch to trading days** — Replace calendar days with `numpy.busday_count()` or a simple trading calendar. Apply to both BS calculations and strike distance formula
4. **[P2, Medium effort] Add vega monitoring** — Track position vega from BS calculator. Alert when `vega × expected_VIX_change > Y%` of premium collected
5. **[P2, Medium effort] Model Nifty skew** — Fetch IV for both call and put strikes from option chain. Adjust strike distances so both legs have approximately equal probability of breach (equal delta, not equal distance)
6. **[P3, Low effort] Fix Iron Condor insurance** — Scale risk multiplier by how far OTM the insurance put is placed. Closer insurance = lower multiplier needed

---

## Section 6: Backtesting & Data Integrity

### Current Backtesting Capability

**File:** `apps/algo_test/`

The backtesting framework consists of:

1. **AlgoTestScenario** — Stores saved test scenarios (inputs + results as JSON). Manual parameter entry, no historical replay
2. **OptionsTestLog** — Logs single-point options algorithm evaluations (spot, VIX, DTE → strikes, delta, decision)
3. **FuturesTestLog** — Logs single-point futures scoring (symbol, price → 13 component scores, decision)
4. **PositionMonitorSnapshot** — Manual snapshots of position state at a point in time

**What exists:** A "what-if calculator" that can evaluate the algorithm at a single point in time with user-provided inputs. Not a backtesting engine.

**What doesn't exist:**
- No historical replay engine (feed past data through strategy, simulate trades)
- No walk-forward validation
- No Monte Carlo simulation
- No out-of-sample testing methodology
- No transaction cost modeling in test results
- No drawdown analysis across test scenarios

### Analytics/Learning Pipeline

**File:** `apps/analytics/services/`

| Service | Capability | Status |
|---------|-----------|--------|
| `learning_engine.py` | Analyze closed trades, compute entry/exit scores | Functional (min 10 trades) |
| `pattern_recognition.py` | Discover timing patterns (entry hour, exit day) | Partial (strike + market condition TODO) |
| `parameter_optimizer.py` | Suggest timing + risk parameter changes | Partial (strike adjustment TODO) |
| `ml_data_collector.py` | Log user decisions with market context for ML training | Functional (Phase 1) |

**Learning workflow:** `analyze_trades()` → `discover_patterns()` → `generate_suggestions()` — but operates only on live trade history, not simulated scenarios.

### Data Integrity Risks

1. **Survivorship bias** — Trendlyne data uses today's F&O stock universe for historical analysis. Stocks that were delisted, moved out of F&O, or went bankrupt are excluded from the training set. This inflates historical win rates

2. **No tick-level options data** — Options data is daily granularity from Trendlyne + 5-min live updates. Intraday gamma events, flash crashes, and expiry-day pin risk are invisible in historical analysis

3. **Lookahead bias risk** — Some Trendlyne fields (analyst consensus, target prices) may incorporate forward-looking estimates. If used in historical analysis, these introduce future information

4. **No corporate action adjustment** — Historical prices from Trendlyne may not be split/bonus adjusted. A stock that split 5:1 would show as a massive price drop, corrupting technical indicators

5. **1-year historical depth only** — `apps/strategies/services/historical_analysis.py` uses 1-year lookback. Insufficient for testing regime-diverse scenarios (COVID crash 2020, 2022 bear market, 2024 bull run)

6. **Parameter optimizer uses in-sample data** — Suggestions are generated from the same data used to discover patterns. No train/test split, no cross-validation. High overfitting risk

### Strengths

- **ML data collection pipeline** — `UserDecisionLog` captures every human decision with full market context snapshot. Valuable for future supervised learning
- **Trade performance analysis** — `TradePerformance` model tracks max favorable/adverse excursion, entry/exit quality scores, lessons learned
- **Pattern discovery framework** — Structure exists for entry timing, exit timing, strike selection patterns. Partially implemented but extensible
- **Financial year analytics** — `FinancialYearSummary` provides April-March FY reporting with monthly breakdown

### Weaknesses

- **[CRITICAL] No backtesting engine** — Cannot validate strategies against historical data. The algo_test framework is a point-in-time calculator, not a replay engine. For a system managing Rs.7.2 Cr, every strategy parameter is essentially untested against historical market conditions. `apps/algo_test/`
- **[HIGH] No walk-forward validation** — Parameter optimizer generates suggestions from in-sample patterns with no out-of-sample validation. Overfitting risk is very high
- **[HIGH] Survivorship bias in historical data** — Trendlyne universe is today's F&O stocks. Backtest results are systematically optimistic
- **[HIGH] 1-year historical depth** — Insufficient for regime-diverse testing. The 2020 COVID crash, 2022 rate hike cycle, and 2024 election volatility are all outside the lookback window
- **[MEDIUM] No tick-level options data** — Daily/5-min granularity misses intraday gamma events that are the primary risk to the strangle strategy
- **[MEDIUM] Pattern recognition incomplete** — Strike selection and market condition pattern discovery are marked TODO. Only entry timing (hour of day) and exit timing (day of week) are implemented. `pattern_recognition.py:127-157`
- **[LOW] No corporate action adjustment verification** — Historical prices may not be split/bonus adjusted

### Recommended Changes

1. **[P1, High effort] Build walk-forward backtesting engine** — Implement historical replay: feed past ContractData + MarketData through strategy logic, simulate entries/exits with realistic slippage/costs. Use rolling window: train on 6 months, test on next 1 month, slide forward
2. **[P1, Medium effort] Add out-of-sample validation** — Split historical data: 70% train, 15% validation, 15% test. Parameter optimizer must only use training data
3. **[P2, Medium effort] Obtain deeper historical data** — Source 3-5 years of F&O data (NSE Bhav copies, options chain snapshots). Include delisted stocks to correct survivorship bias
4. **[P2, Medium effort] Add Monte Carlo simulation** — Randomize entry/exit timing, slippage, and VIX levels to stress-test strategy robustness
5. **[P3, Medium effort] Implement transaction cost model** — Model STT, brokerage, exchange fees, GST, and slippage in all backtests. See Section 9 for cost details

---

## Section 7: Performance & Risk Metrics

### Currently Tracked Metrics

| Metric | Model | Granularity |
|--------|-------|------------|
| Daily P&L | `DailyPnL` | Per account per day |
| Weekly/Monthly performance | `Performance` | Aggregated periods |
| Win rate | `Performance.win_rate` | Per period |
| Profit factor | `Performance.profit_factor` | Per period |
| Sharpe ratio | `Performance.sharpe_ratio` | Per period |
| Max drawdown | `Performance.max_drawdown`, `DailyPnL.max_drawdown` | Per period / daily |
| Daily/weekly loss limits | `RiskLimit` | Real-time |
| Circuit breaker | `CircuitBreaker` | Event-driven |
| Per-position drawdown | Position SL monitoring | Real-time (every minute) |
| Trade-level MFE/MAE | `TradePerformance.max_favorable_excursion/max_adverse_excursion` | Per trade (TODO: needs tick data) |
| Financial year summary | `FinancialYearSummary` | FY (April-March) |

### Risk Limit Architecture

**File:** `apps/risk/services/risk_manager.py`

- **Daily loss limit:** Checked every minute via `check_daily_loss_limit(account)`. Compares today's cumulative loss against `account.max_daily_loss`. Warning at 80%, breach at 100%
- **Weekly loss limit:** Aggregates Monday-current day. Same thresholds
- **Circuit breaker:** On breach → deactivate account (24-hour cooldown). Manual mode: sends Telegram exit suggestions via `TradeConfirmationService`. Autonomous mode: auto-closes all positions immediately
- **Action levels:** NONE → WARNING → EMERGENCY_EXIT (note: STOP_TRADING mentioned in code comments but never used in actual logic)

### Missing Metrics

| Metric | Why It Matters | Priority |
|--------|---------------|----------|
| **Sortino ratio** | Distinguishes harmful downside volatility from beneficial upside. Sharpe penalizes upside gains | P1 |
| **CVaR / Expected Shortfall** | Tail risk measure — what's the average loss in the worst 5% of days? Critical for short options | P1 |
| **Max drawdown duration** | How long to recover from peak? A Rs.5L drawdown recovered in 2 days ≠ 2 months | P1 |
| **Skewness of returns** | Short options have negative skew (small frequent gains, rare large losses). Must track this | P2 |
| **Kurtosis** | Fat tail measure. Higher kurtosis = more extreme events than normal distribution predicts | P2 |
| **Rolling Sharpe/Sortino** | Detect strategy degradation over time. A declining rolling Sharpe is an early warning | P2 |
| **Win rate × payoff ratio decomposition** | High win rate (80%) with 1:5 payoff ratio = negative expectancy. Must track together | P2 |
| **Strategy attribution** | Which of the 13 scoring components actually predict profitable trades? | P2 |
| **Calmar ratio** | Annualized return / max drawdown. Measures return per unit of drawdown risk | P3 |
| **Correlation between strategies** | If strangle and futures both lose on the same days, diversification benefit is zero | P3 |
| **Greeks P&L attribution** | Decompose daily P&L into theta + delta + gamma + vega components. Essential for options | P3 |

### Strengths

- **Real-time risk enforcement** — Every-minute checks with automatic circuit breaker activation. Not just monitoring but actual enforcement
- **Mode-aware circuit breaker** — Manual mode sends Telegram confirmation; autonomous mode auto-closes. Respects user's notification level preference
- **Multi-level escalation** — WARNING (80%) → EMERGENCY_EXIT (100% breach → circuit breaker) provides graduated response
- **Financial year analytics** — `FinancialYearSummary` tracks monthly breakdown, best/worst periods, return on margin — aligned with Indian FY (April-March)
- **Trade-level analysis** — `TradePerformance` model supports entry/exit quality scoring, MFE/MAE, lessons learned

### Weaknesses

- **[HIGH] No tail risk metrics** — CVaR/Expected Shortfall is not calculated. For a short options strategy, tail risk is the existential threat. Daily loss limits catch individual bad days but don't measure the distribution's fat tail behavior
- **[HIGH] No drawdown duration tracking** — System tracks max drawdown magnitude but not how long recovery takes. A 2-week drawdown may require strategy adjustment; a 2-day drawdown may not
- **[HIGH] No strategy attribution** — With 13 scoring components, there's no mechanism to determine which components actually predict profitable trades. Weights could be actively harmful and nobody would know
- **[MEDIUM] No Greeks P&L decomposition** — For options, daily P&L is a mix of theta decay (wanted), delta movement (unwanted), gamma (dangerous), and vega (exposure). Without decomposition, you can't tell if profit came from skill (correct strike selection) or luck (market didn't move)
- **[MEDIUM] Sharpe ratio field exists but calculation method unknown** — `Performance.sharpe_ratio` is a DecimalField, but the calculation methodology (risk-free rate? annualized? rolling window?) isn't documented in the model
- **[LOW] MFE/MAE marked as TODO** — `TradePerformance` has fields for max favorable/adverse excursion but the learning engine notes these require tick-by-tick data that doesn't exist

### Recommended Changes

1. **[P1, Medium effort] Implement CVaR/Expected Shortfall** — Calculate 5% CVaR from daily returns in `DailyPnL`. Alert when CVaR exceeds 1% of portfolio value. Add to daily report
2. **[P1, Low effort] Track max drawdown duration** — Extend `DailyPnL` to track consecutive drawdown days and peak-to-recovery time. Add `drawdown_start_date` and `drawdown_peak_loss` fields
3. **[P2, Medium effort] Add rolling risk metrics** — Compute 30-day rolling Sharpe, Sortino, and win rate. Display trend (improving/degrading) in daily report. Alert on significant degradation
4. **[P2, Medium effort] Build strategy attribution** — For each closed trade, correlate the 13 scoring components with outcome. Monthly report showing component-level accuracy
5. **[P2, Medium effort] Add Greeks P&L decomposition** — Use BS calculator to decompose daily options P&L into theta + delta + gamma + vega components. Essential for understanding strangle strategy performance
6. **[P3, Low effort] Add Sortino ratio** — Modify Sharpe calculation to use downside deviation only. More appropriate for strategies with asymmetric returns

---

## Section 8: Capital Efficiency & Portfolio Construction

### Current Capital Allocation

| Account | Capital | Strategy | Typical Deployment | Utilization |
|---------|---------|----------|-------------------|-------------|
| Kotak | Rs.6 Cr | Short strangle / Iron Condor | 50% margin, 1 position | ~50% × 3-4 days/week |
| ICICI | Rs.1.2 Cr | Directional futures | 50% margin, 1 position | ~50% × variable |
| **Total** | **Rs.7.2 Cr** | — | — | **Estimated 25-35%** |

### Capital Utilization Analysis

**Kotak Options (Rs.6 Cr):**
- Entry: Monday-Wednesday
- Exit: Thursday EOD (50% profit) or Friday mandatory
- Idle: ~2-3 days/week (Thursday post-exit → Monday entry)
- Margin per lot: ~Rs.1.92L (24000 × 50 × 16%). With correct lot size (65): ~Rs.2.50L/lot
- At 50% utilization: Rs.3 Cr deployed → ~12 lots
- **Effective utilization: ~50% × 4/5 days = ~40% weekly average**

**ICICI Futures (Rs.1.2 Cr):**
- Single position, variable duration (15+ DTE)
- Margin per lot: varies by stock (Rs.3-8L per lot typically)
- At 50% utilization: Rs.60L deployed
- **Binary: 50% when active, 0% when searching/idle**

**Combined portfolio: Rs.7.2 Cr capital generating ~Rs.12-14L/month = ~1.7-1.9% monthly return.**

At optimal utilization (80% deployed × 5 days/week), theoretical capacity is 2-3× current returns.

### Portfolio Construction Gaps

1. **No correlation analysis** — Both strategies suffer in a Nifty crash. Short strangle loses on delta+gamma; futures (if long) loses on direction. Tail risk is correlated, not diversified

2. **No capital rotation** — When strangle exits Thursday, Rs.3 Cr sits idle until Monday. No mechanism to deploy in overnight/intraday strategies or money market instruments

3. **No portfolio-level Greeks** — Aggregate delta, gamma, vega across all positions are not calculated. The strangle could be short 500 delta while the futures position is long 300 delta — net portfolio delta of 200 is unknown to the system

4. **No margin stress testing** — What happens if both positions need averaging simultaneously? Strangle averaging (20% + 50% + 50%) could consume remaining 50% margin buffer. If futures also needs averaging, there's no capital

5. **One-position-per-account constraint** — Both accounts limited to single positions. No portfolio diversification within accounts

### Strengths

- **Conservative margin utilization** — 50% default with 15% reserve buffer prevents margin calls under normal conditions
- **Account-level isolation** — Separate broker accounts for options vs futures prevents cross-strategy margin interference
- **Clear strategy assignment** — Each account has a defined strategy, avoiding confusion in execution and risk management

### Weaknesses

- **[HIGH] Estimated 25-35% capital utilization** — Rs.7.2 Cr deployed at ~35% efficiency means Rs.4.7 Cr sits idle on average. At risk-free 6.5%, this idle capital could earn Rs.30L/year without any trading risk
- **[HIGH] Correlated tail risk** — Both strategies lose in a market crash (Nifty -5% day). No hedge, no inverse correlation strategy, no tail risk protection beyond position-level SL
- **[HIGH] No portfolio-level Greeks aggregation** — Net delta, gamma, vega across all positions is unknown. The system manages positions individually but has no portfolio view
- **[MEDIUM] No margin stress scenario** — Simultaneous adverse moves on both accounts could require margin beyond 50% utilization. No pre-computation of worst-case margin requirements
- **[MEDIUM] No capital rotation** — Idle capital between strategy cycles generates zero return. Thursday-Monday gap (3 calendar days) on Rs.3 Cr = ~Rs.16K/week opportunity cost at 6.5% annual
- **[LOW] 50% margin utilization may be too conservative** — Industry standard for well-managed short options is 60-70% margin utilization with dynamic adjustment. 50% leaves significant capacity unused

### Recommended Changes

1. **[P1, Medium effort] Add portfolio-level Greeks dashboard** — Aggregate delta, gamma, vega across all open positions. Display in daily dashboard. Alert when net portfolio delta > threshold
2. **[P2, Medium effort] Implement margin stress testing** — Pre-compute margin requirements under stress scenarios (Nifty ±3%, ±5%, VIX spike to 25/30). Ensure combined margin stays within available capital
3. **[P2, High effort] Add uncorrelated strategy** — Consider: calendar spreads (benefits from IV changes), pair trades (market-neutral), or intraday momentum (low overnight risk). Target strategies with negative correlation to existing portfolio
4. **[P3, Medium effort] Implement capital rotation** — Sweep idle margin to liquid overnight instruments (TREPS, liquid fund). Auto-recall before market open. Even 6.5% overnight on Rs.3 Cr = Rs.8L/year
5. **[P3, Low effort] Evaluate margin utilization increase** — Backtest performance at 55-65% utilization. If drawdown remains within limits, increase from 50% to 60%

---

## Section 9: Operational & Real-World Constraints

### Transaction Cost Model (Indian Market)

#### Kotak Options (Short Strangle) — Per Trade Cycle

| Cost Component | Rate | Example (10 lots × 65 units × Rs.3 premium) |
|---------------|------|----------------------------------------------|
| **STT (sell)** | 0.0625% on premium | Rs.3 × 650 × 2 legs × 0.000625 = Rs.2.44 |
| **STT (on exercised ITM)** | 0.125% on settlement | **Rs.18,750 if one leg exercised at intrinsic Rs.150** |
| **Brokerage** | Flat Rs.20/order (Kotak) | Rs.20 × 4 orders (2 sell + 2 buy) = Rs.80 |
| **Exchange charges** | ~0.053% (NSE) | Rs.3 × 650 × 2 × 0.00053 = Rs.2.07 |
| **SEBI turnover fee** | Rs.10/Cr | Negligible |
| **Stamp duty** | 0.003% (buyer) | Rs.0.59 |
| **GST** | 18% on brokerage + exchange | (80 + 2.07) × 0.18 = Rs.14.77 |
| **Total (no exercise)** | — | **~Rs.100 per cycle** |
| **Total (one leg exercised)** | — | **~Rs.18,950 per cycle** |

**Critical insight:** STT on exercised options (0.125% of settlement value) is orders of magnitude higher than STT on premium. If one leg of the strangle is exercised (ITM at expiry), STT alone can wipe out 2-3 weeks of theta profit. **The system must ensure legs are squared off before expiry, never allowed to be exercised.**

The current system has mandatory Friday close logic, which addresses this — but any failure to close (system downtime, API failure, Telegram timeout) could result in exercise and massive STT hit.

#### ICICI Futures — Per Trade Cycle

| Cost Component | Rate | Example (Rs.10L position) |
|---------------|------|--------------------------|
| **STT** | 0.0125% (sell side) | Rs.125 |
| **Brokerage** | Flat Rs.20/order | Rs.40 (buy + sell) |
| **Exchange charges** | ~0.002% | Rs.20 |
| **SEBI fee** | Rs.10/Cr | Rs.1 |
| **Stamp duty** | 0.002% (buy) | Rs.20 |
| **GST** | 18% on above | Rs.14.58 |
| **Total** | — | **~Rs.220 per cycle** |

Futures cost structure is significantly cheaper than options on a per-trade basis.

### Execution Risks

1. **Batch execution (10 lots/order, 20s delay)** — Strangle entry of 12 lots requires 2 batches with 20s gap. In a fast market, the second batch may execute at a significantly different premium. `apps/trading/services/` execution logic

2. **Position sync every 1 minute** — May miss flash moves. A 200-point Nifty spike and recovery within 30 seconds is invisible to the monitor. For options near expiry, this could mean missing a critical SL trigger

3. **Live market data every 5 minutes** — Too slow for intraday options management. Delta can shift meaningfully in 5 minutes on a 50-point Nifty move. The SR exit engine uses 5-min candles, which adds another 5-min lag

4. **Broker API reliability** — TOTP auto-generation for login is a compliance gray area. API downtime during market hours means no position sync, no exits, no monitoring. No automated failover to manual trading

5. **Telegram as sole decision UI** — Critical exit confirmations (Rs.5-10L positions) are managed via Telegram inline keyboards. Network issues, Telegram outages, or accidental taps can result in missed/wrong decisions. No web fallback for critical actions

### System Risks

1. **SQLite write contention** — As discussed in Section 1. Under sustained load, monitor + risk + data tasks may compete for DB writes

2. **Redis SPOF** — No sentinel, no replication. Redis crash = all Celery tasks stop, distributed locks fail, overlapping monitor cycles possible

3. **No automated failover** — If primary system goes down during market hours, there is no secondary system, no manual runbook, no automated alerting that the system itself is down (Celery tasks can't alert if Celery is down)

4. **No formal disaster recovery** — No documented procedure for: system crash during open position, broker API failure during exit, database corruption, Redis data loss

### Strengths

- **Mandatory Friday close** — Prevents exercise-related STT (0.125%) which would be catastrophic for the strangle strategy
- **Flat brokerage structure** — Rs.20/order from both Kotak and ICICI makes transaction costs predictable and low for large positions
- **Batch execution with delay** — While adding slippage risk, the 20s delay prevents market impact on illiquid strikes
- **Position sync with failure tracking** — 3-strike escalation on broker sync failures provides early warning of API issues
- **Multiple mode support** — FULL_CONTROL/SUPERVISED/AUTONOMOUS modes allow user to adjust automation level based on market conditions

### Weaknesses

- **[CRITICAL] No system health monitoring** — If the entire mCube system goes down during market hours, there is no external watchdog to detect this. Open positions would have no monitoring, no SL enforcement, no alerts. For Rs.7.2 Cr under management, this is an existential risk
- **[HIGH] Exercise STT risk on system failure** — If Friday mandatory close fails (system down, API error, Telegram timeout), an ITM option leg could be exercised, incurring 0.125% STT (~Rs.18,750+ per lot). Current mitigation: mandatory Friday close + Telegram confirmation. No fallback
- **[HIGH] 5-minute data refresh too slow** — Options delta can shift significantly on a 50-point Nifty move (occurs multiple times daily). 5-minute data means the SR engine and delta monitor are always 2.5 minutes stale on average. `apps/data/tasks.py`
- **[HIGH] Telegram single point of failure for decisions** — Exit confirmations on Rs.5-10L positions depend on Telegram. No web UI fallback, no SMS backup, no phone call escalation
- **[MEDIUM] No disaster recovery plan** — No documented procedure for system crash, database corruption, Redis failure, or broker API extended outage during market hours
- **[MEDIUM] Batch execution slippage** — 20s delay between batches of 10 lots. On a volatile day, 20s can mean Rs.5-10 premium difference per unit. For 120 units (second batch): Rs.600-1,200 slippage per entry
- **[LOW] TOTP auto-generation compliance** — Automated TOTP generation for broker login may violate broker T&C regarding non-manual authentication

### Recommended Changes

1. **[P1, Medium effort] Add external health monitoring** — Deploy a lightweight watchdog (cron job or separate service) that checks: (a) Celery workers alive, (b) monitor task ran in last 2 minutes, (c) Redis responsive, (d) Django serving requests. Alert via SMS (not Telegram, which is in the blast radius) if any check fails
2. **[P1, Low effort] Add exercise prevention redundancy** — Add a secondary cron job (outside Celery) that checks for open options positions after 15:15 on Fridays and triggers emergency close via direct broker API call. Belt-and-suspenders for the STT risk
3. **[P2, Medium effort] Increase data refresh to 1-2 minutes** — Live market data at 1-2 minute intervals instead of 5 minutes. Reduces staleness for delta monitoring and SR engine. May require broker API rate limit review
4. **[P2, Medium effort] Add web UI for critical decisions** — Implement a web dashboard for exit confirmations as Telegram fallback. Auto-switch to web alerts if Telegram delivery fails
5. **[P2, Low effort] Document disaster recovery** — Write runbook for: (1) system crash during open position, (2) broker API failure during exit, (3) database corruption recovery, (4) Redis data loss recovery. Test quarterly
6. **[P3, Low effort] Reduce batch execution delay** — Evaluate reducing 20s to 5-10s. Monitor fill quality at shorter delays

---

## Consolidated Priority Matrix

### Critical Fixes (Deploy Within 1 Week)

| # | Finding | Impact | Effort | Location |
|---|---------|--------|--------|----------|
| 1 | **Fix NIFTY lot size** (50→65 in strangle sizer, 75→65 in IC sizer) | Position sizing 30% wrong, margin calc incorrect for live trades | Low (2 lines) | `strangle_position_sizer.py:36`, `iron_condor_position_sizer.py:28` |
| 2 | **Fix lot size fallbacks in neo.py** (25/50/75 defaults) | Wrong fallback when API fails | Low | `apps/brokers/integrations/kotak_neo.py:914-972,1295-1391` |
| 3 | **Connect BS delta to monitor** | Primary risk metric has ~30-50% error | Low (~20 LOC) | `delta_monitor.py:41-107` → use `greeks_calculator.py` |
| 4 | **Fix strike distance formula** (linear→sqrt DTE) | Systematic overshoot of strike distance for longer expiries | Low (1 line) | `strangle_delta_algorithm.py:446` |
| 5 | **Add external health monitoring** | No detection if entire system goes down during market hours | Medium | New service/cron |
| 6 | **Add exercise prevention redundancy** | STT catastrophe (Rs.18K+/lot) if Friday close fails | Low | New cron job |

### High Priority (Deploy Within 1 Month)

| # | Finding | Impact | Effort | Location |
|---|---------|--------|--------|----------|
| 7 | **Smooth VIX multiplier** (50% jump at 12.5) | Unstable strike selection at boundary values | Low | `strangle_delta_algorithm.py:72-113` |
| 8 | **Add gamma monitoring** | Missing dominant risk metric for short weekly options | Medium | Extend `delta_monitor.py` using `greeks_calculator.py` |
| 9 | **Switch calendar→trading days** | ~40% time-to-expiry error on weekends | Low | `greeks_calculator.py`, `strangle_delta_algorithm.py` |
| 10 | **Add LLM fallback** (score-only when LLM down) | Single point of failure for entire futures strategy | Low | `trade_validator.py` |
| 11 | **Migrate SQLite→PostgreSQL** | Write contention under concurrent Celery workers | Medium | `mcube_ai/settings.py` + migration |
| 12 | **Increase data refresh to 1-2 min** | 5-min data too slow for options management | Medium | `apps/data/tasks.py` |
| 13 | **Build critical path test suite** | Zero tests for live trading paths managing Rs.7.2 Cr | High | `apps/positions/`, `apps/risk/`, `apps/trading/` |
| 14 | **Implement CVaR/Expected Shortfall** | No tail risk measurement for short options | Medium | `apps/analytics/` |
| 15 | **Add vega monitoring** | VIX spikes unmonitored on open short options | Medium | Extend `delta_monitor.py` |

### Medium Priority (Deploy Within 3 Months)

| # | Finding | Impact | Effort | Location |
|---|---------|--------|--------|----------|
| 16 | Add portfolio-level Greeks dashboard | Net delta/gamma/vega unknown across positions | Medium | New service |
| 17 | Implement rolling logic for strangle | No premium optimization; binary hold/close | Medium | `kotak_strangle.py` |
| 18 | Build walk-forward backtesting engine | Cannot validate strategies against historical data | High | New `apps/backtest/` |
| 19 | Calibrate 13-component weights | Heuristic weights may be actively harmful | High | `enhanced_futures_analyzer.py` |
| 20 | Add margin stress testing | Simultaneous adverse moves could exceed margin | Medium | `apps/risk/` |
| 21 | Model Nifty skew for strike selection | Symmetric strikes ignore real-world put skew | Medium | `strangle_delta_algorithm.py` |
| 22 | Redis sentinel / persistence | Redis SPOF for entire task infrastructure | Medium | Infrastructure |
| 23 | Implement CI/CD | No automated testing gate for deployments | Medium | GitHub Actions |
| 24 | Add web UI for critical decisions | Telegram SPOF for exit confirmations | Medium | New views |
| 25 | Document disaster recovery | No runbook for system failures during market | Low | Documentation |
| 26 | Soften hard reject gates | Binary reject on Piotroski 3 vs 4 too harsh | Low | `enhanced_futures_analyzer.py` |
| 27 | Reduce SR cache TTL in last hour | 15-min cache stale during fast end-of-day moves | Medium | `sr_exit_engine.py` |
| 28 | Add drawdown duration tracking | Only magnitude tracked, not recovery time | Low | `apps/analytics/models.py` |

### Low Priority (Backlog)

| # | Finding | Impact | Effort | Location |
|---|---------|--------|--------|----------|
| 29 | Add staggered entries for strangle | Capital idle ~3 days/week | Medium | `kotak_strangle.py` |
| 30 | Convert averaging to anti-martingale | Pro-cyclical averaging increases risk | Low | `strangle_position_sizer.py` |
| 31 | Allow 2-position futures portfolio | Single-stock concentration risk | Medium | `icici_futures.py` |
| 32 | Capital rotation for idle funds | Rs.4.7 Cr idle average generating zero | Medium | New service |
| 33 | Add uncorrelated strategy | Both strategies lose in crash | High | New strategy |
| 34 | Remove component redundancy | RSI/ADX duplicated across prefilter/scoring | Low | Multiple files |
| 35 | Fix Iron Condor insurance distance | Risk multiplier doesn't account for OTM distance | Low | `kotak_broken_iron_condor.py` |
| 36 | Activate strategy adapter signals | Shadow-run adapters produce unused signals | Medium | `sr_strategy_adapter.py` |
| 37 | Obtain deeper historical data | 1-year lookback insufficient | Medium | Data sourcing |

---

## Summary

mCube AI is an ambitious and architecturally sophisticated trading platform with strong foundations in modular design, multi-factor analysis, and adaptive risk management. The 8-source SR exit engine, unified notification framework, and confidence-scored trigger system demonstrate deep domain knowledge.

However, for a system managing Rs.7.2 Cr in live capital, several critical gaps require immediate attention:

1. **Incorrect lot sizes** in position sizing (immediate fix, 2 lines of code)
2. **Crude delta approximation** while a proper BS calculator sits unused (low effort, high impact)
3. **No gamma/vega monitoring** for a short options strategy where these are dominant risks
4. **No external health monitoring** — if the system dies, nobody knows until they check manually
5. **No backtesting** — all strategy parameters are empirically unvalidated
6. **SQLite under concurrent writes** — architectural mismatch for the workload

The good news: most critical fixes (items 1-7) are low-effort changes. The system has the right building blocks (BS calculator, notification framework, risk limits) — they just need to be connected and activated. The medium-term work (backtesting, PostgreSQL, CI/CD, portfolio-level risk) builds on a solid foundation.

**Estimated implementation sequence:**
- Week 1: Items 1-6 (critical fixes, mostly low effort)
- Weeks 2-4: Items 7-15 (high priority, mixed effort)
- Months 2-3: Items 16-28 (medium priority, infrastructure + analytics)
- Ongoing: Items 29-37 (backlog, strategic improvements)
