# mCube AI — Algorithm Verification Report

**Date:** 2026-03-23
**Method:** Line-by-line source code inspection via 7 parallel verification agents
**Scope:** Every algorithmic claim in SYSTEM_REVIEW.md cross-referenced against actual code

---

## Verification Summary

| Category | Claims Verified | Confirmed | Corrections Found | Incorrect |
|----------|----------------|-----------|-------------------|-----------|
| Lot Sizes & Strike Formula | 6 | 6 | 0 | 0 |
| Delta Monitor & Greeks | 14 | 14 | 0 | 0 |
| VIX Buckets & Strangle Scoring | 12 | 11 | 1 | 0 |
| 13-Component Futures Scoring | 17 | 13 | 2 | 2 |
| SR Exit Engine Triggers | 16 | 16 | 0 | 0 |
| Risk Manager & Monitoring | 33 | 31 | 0 | 2 |
| Exit Manager & Notifications | 17 | 16 | 0 | 1 |
| **Total** | **115** | **107** | **3** | **5** |

**Overall accuracy: 107/115 confirmed (93.0%). 5 claims need correction, 3 need clarification.**

---

## CONFIRMED Critical Findings (Verified Against Source)

### 1. NIFTY Lot Size Hardcoded Wrong in BOTH Position Sizers

**CONFIRMED**

| File | Line | Constant | Value | Actual Nifty Lot |
|------|------|----------|-------|-----------------|
| `apps/trading/services/strangle_position_sizer.py` | 36 | `NIFTY_LOT_SIZE` | `Decimal('50')` | 65 |
| `apps/trading/services/iron_condor_position_sizer.py` | 28 | `NIFTY_LOT_SIZE` | `Decimal('75')` (comment: "updated from 50 to 75") | 65 |

**Evidence that 65 is correct:** `apps/brokers/models.py:207` — `BrokerPosition.lot_size` field has `help_text="Lot size from broker API (e.g., 65 for NIFTY)"`

**Dynamic source exists but unused by sizers:** `apps/data/importers.py:172` — `'lot_size': self._safe_int(row, 'Lot Size', 1)` populates `ContractData.lot_size` from Trendlyne CSV daily.

**Neo API fallback defaults also wrong:**
- `apps/brokers/integrations/kotak_neo.py:914` — `scrip.get('lLotSize', scrip.get('iLotSize', 50))` (default 50)
- `kotak_neo.py:925` — `return 50` (futures fallback)
- `kotak_neo.py:958` — `scrip.get('lLotSize', scrip.get('iLotSize', 25))` (NIFTY options default 25)
- `kotak_neo.py:1360,1376,1386` — `'lot_size': 75` (various futures fallbacks)

---

### 2. Strike Distance Formula Linear in DTE (Not sqrt)

**CONFIRMED — Two independent files use identical linear formula**

**File 1:** `apps/strategies/services/strangle_delta_algorithm.py:446`
```python
strike_distance = self.spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(self.days_to_expiry))
```

**File 2:** `apps/strategies/shared/strike_calculator.py:477`
```python
base_strike_distance = spot_price * (adjusted_delta / Decimal('100')) * Decimal(str(days_to_expiry))
```

Both multiply by `days_to_expiry` directly. Neither uses `sqrt(days_to_expiry)` or `Decimal(str(days_to_expiry)).sqrt()` or `math.sqrt()`.

---

### 3. Delta Monitor Uses Crude Approximation (BS Calculator Exists but Unused)

**CONFIRMED**

**Crude approximation in delta_monitor.py:**

Call delta buckets (`delta_monitor.py:73-88`):
| Line | Condition (`moneyness = spot/strike`) | Assigned Delta |
|------|---------------------------------------|---------------|
| 76 | `> 1.02` (deep ITM) | 0.70 |
| 78 | `> 1.00` (ATM) | 0.50 |
| 80 | `> 0.98` (slightly OTM) | 0.40 |
| 82 | `> 0.95` (OTM) | 0.25 |
| 84 | `else` (deep OTM) | 0.10 |

Put delta buckets (`delta_monitor.py:90-106`):
| Line | Condition | Assigned Delta |
|------|-----------|---------------|
| 93 | `< 0.98` (deep ITM) | -0.70 |
| 95 | `< 1.00` (ATM) | -0.50 |
| 97 | `< 1.02` (slightly OTM) | -0.40 |
| 99 | `< 1.05` (OTM) | -0.25 |
| 101 | `else` (deep OTM) | -0.10 |

**TODO comment at line 64:**
```python
# TODO: Replace with proper Black-Scholes delta calculation using py_vollib
```

**BS calculator exists but is NOT imported by delta_monitor.py.** Imports (`delta_monitor.py:28-36`):
```python
import logging
from decimal import Decimal
from typing import Dict
from django.utils import timezone
from apps.positions.models import Position
from apps.alerts.services.telegram_client import send_telegram_notification
from apps.alerts.services.notification_service import notify
```
No reference to `greeks_calculator` anywhere in the file.

**BS calculator location:** `apps/strategies/services/greeks_calculator.py` — has full implementation:
- `calculate_delta()` at lines 138-160 (proper N(d1) formula)
- `calculate_gamma()` at line 180
- `calculate_vega()` at line 202
- `calculate_theta()` at lines 224-252
- Only imported by `apps/strategies/services/nifty_data_fetcher.py`

**Alert threshold:** `delta_monitor.py:177` — `delta_threshold: Decimal = Decimal('300')`

---

### 4. VIX Multiplier 50% Discontinuity at 12.5

**CONFIRMED**

`apps/strategies/services/strangle_delta_algorithm.py:89-103`:
```python
if vix_val < 10:
    adj = Decimal('0.9')       # Line 89-90
elif vix_val < 12.5:
    adj = Decimal('1.0')       # Line 92-93
elif vix_val < 14:
    adj = Decimal('1.5')       # Line 95-96  ← 50% JUMP from 1.0
elif vix_val < 18:
    adj = Decimal('1.8')       # Line 98-99
else:
    adj = Decimal('2.0')       # Line 102-103
```

VIX at 12.4 → 1.0×. VIX at 12.6 → 1.5×. **50% jump confirmed.**

---

### 5. Calendar Days (Not Trading Days) in Both Key Files

**CONFIRMED**

**greeks_calculator.py:17-30:**
```python
def calculate_days_to_expiry(expiry_date: date) -> float:
    today = dt_date.today()
    days = (expiry_date - today).days
    return max(days, 0.001)
```
Converted to years at line 343: `time_to_expiry = days / 365.0`

**delta_monitor.py:132:**
```python
days_to_expiry = (position.expiry_date - timezone.now().date()).days
```

Both use standard calendar date arithmetic. Neither uses trading days or `numpy.busday_count()`.

---

### 6. No Gamma or Vega Monitoring

**CONFIRMED — Codebase-wide search found no gamma/vega threshold monitoring**

- `greeks_calculator.py` computes gamma and vega but only for option chain analysis
- `delta_monitor.py` monitors only delta (crude approximation)
- `sr_exit_engine.py:179` has `EXPIRY_GAMMA_MODE_HOUR = 14` but this is a time constant, not gamma monitoring
- `sr_strategy_adapter.py` references "gamma walls" but these are OI concentration zones, not option Greeks gamma
- No gamma threshold, gamma P&L attribution, or gamma-based alerting exists anywhere
- No vega threshold or vega exposure monitoring on open positions

---

### 7. 13-Component Futures Scoring (315 pts)

**CONFIRMED — All 13 components verified**

`apps/strategies/analyzers/enhanced_futures_analyzer.py:72-87`:
```python
WEIGHTS = {
    'oi_fno': 45,
    'technical_momentum': 35,
    'trend_confirmation': 30,
    'volume_quality': 25,
    'institutional_flow': 25,
    'fundamental_quality': 20,
    'risk_adjustment': 30,
    'news_sentiment': 25,
    'analyst_consensus': 20,
    'research_reports': 15,
    'investor_calls': 10,
    'momentum_acceleration': 20,
    'mtf_confluence': 15,
}
TOTAL_WEIGHT = sum(WEIGHTS.values())  # 315
```

Normalization (`lines 196-197`):
```python
raw_score = sum(self.scores.values())
composite_score = int((raw_score / self.TOTAL_WEIGHT) * 100)
```

---

### 8. SR Exit Engine Score-Gated Triggers

**CONFIRMED — All thresholds and logic verified**

`apps/positions/services/sr_exit_engine.py:174-176`:
```python
SCORE_INSTITUTIONAL = 76
SCORE_STRONG = 56
SCORE_MODERATE = 31
```

Trigger logic (`sr_exit_engine.py:902-924`, LONG direction):
```python
strict_mode = self._is_expiry_day_gamma_mode() or self._is_low_liquidity_day()

if level_score >= SCORE_INSTITUTIONAL and not strict_mode:
    triggered = True  # Condition A alone
elif level_score >= SCORE_STRONG and not strict_mode:
    triggered = cond_b or self._not_recovering_15min(level, 'LONG')  # A or B + 15min
else:
    if not cond_b: return False, 'CONDITION_B_NOT_MET'
    if not self._not_recovering_15min(level, 'LONG'): return False, 'PRICE_RECOVERING_15MIN'
    triggered = True  # Both A+B + 15min
```

ATR-adaptive thresholds (`sr_exit_engine_utils.py:222-247`):
```python
cond_a = 0.3 * atr_pct          # clamped [0.003, 0.010]
cond_b = 2.0 * cond_a           # always 2× cond_a
```

---

### 9. 8-Source Weighted SR Calculator

**CONFIRMED**

`sr_exit_engine.py:147-156`:
```python
SR_SOURCE_WEIGHTS = {
    'pivot': 0.20,
    'prev_day_hl': 0.15,
    'swing_hl': 0.15,
    'vwap': 0.15,
    'moving_averages': 0.15,
    'hvn': 0.10,
    'atr_zones': 0.05,
    'psychological': 0.05,
}
```

---

### 10. Level Confidence Scorer (0-100)

**CONFIRMED**

`sr_level_strength.py:32-40`:
```python
_COMPONENT_MAX = {
    'source_agreement': 25,
    'mtf_confluence':   20,
    'touch_history':    20,
    'oi_reinforcement': 15,
    'volume_at_level':  10,
    'recency':          10,
}
```

---

### 11. Adaptive SL Placer Multipliers

**CONFIRMED**

`sr_risk_interface.py:70-76`:
```python
if level_score > 70:
    multiplier = 0.3   # tight
elif level_score > 40:
    multiplier = 0.5   # standard
else:
    multiplier = 0.8   # wide
```

---

### 12. Distributed Lock & Monitoring Workflow

**CONFIRMED**

`apps/positions/tasks.py:51-62`:
```python
_MONITOR_LOCK_KEY = 'monitor_and_manage_positions_lock'
_MONITOR_LOCK_TTL = 55
_SYNC_FAIL_KEY_PREFIX = 'pos_sync_fail_count'
_SYNC_FAIL_THRESHOLD = 3
_SYNC_FAIL_TTL = 600  # 10 min
```

Exit suggestion cooldown (`monitor_dashboard.py:28`): `EXIT_SUGGESTION_COOLDOWN_MINUTES = 5`

P&L change gates (`notification_templates.py:58,92`):
- SL_TRIGGERED: `min_pnl_change_pct=2.0`
- EXIT_SUGGESTION: `min_pnl_change_pct=1.0`

Hold flag clearing (`tasks.py:547-556`): Clears at `hour >= 15 and minute >= 30`

Near-SL warning (`tasks.py:290`): `buffer_pct < 1.0`

---

### 13. Risk Manager Circuit Breaker

**CONFIRMED (with correction)**

- Manual vs Autonomous differentiation: `risk_manager.py:279` — `is_manual_mode = not core_config.is_autonomous()`
- Manual mode sends exit suggestion via `TradeConfirmationService` (line 287-293)
- Autonomous mode auto-closes positions (line 301-324)
- 24-hour cooldown: `risk_manager.py:411-413` — `cooldown_until = timezone.now() + timedelta(hours=24)`

---

### 14. Market Regime Detection

**CONFIRMED — All conditions exact**

`apps/strategies/services/market_regime.py`:

| Regime | Conditions | Line |
|--------|-----------|------|
| VOLATILE | ATR expansion > 1.5 AND VIX > 16 | 143 |
| BREAKOUT | 20 <= ADX <= 30 | 153 |
| TRENDING | ADX > 25, ATR < 1.3×, VIX < 18 | 155-165 |
| RANGING | ADX < 20, ATR < 1.0× | 167-175 |
| NORMAL | Default fallback | — |

Priority: VOLATILE > BREAKOUT > TRENDING > RANGING > NORMAL (if/elif chain at lines 116-135)

---

### 15. Adaptive SL/Target 3-Tier Fallback

**CONFIRMED**

`apps/strategies/services/adaptive_sl_target.py`:

| Tier | Lines | Source |
|------|-------|--------|
| 1. SR-Based | 75-97 | SR exit engine levels ± ATR buffer |
| 2. ATR-Adaptive | 103-124 | Regime multipliers × ATR |
| 3. Vol%-Scaled | 129-149 | Scaled % from annualized volatility |

Regime multipliers (lines 104-110):
```python
regime_multipliers = {
    "TRENDING":  (1.5, 3.0),
    "RANGING":   (1.0, 2.0),
    "VOLATILE":  (2.0, 3.5),
    "NORMAL":    (2.0, 2.0),
    "BREAKOUT":  (1.2, 3.0),
}
```

Dual targets (line 166): `target_2 = target_1 + (target_1 - price) * 0.5`

S1/R1 tightening (lines 154-160): LONG → `support_s1 * 0.995`, SHORT → `resistance_r1 * 1.005`

---

### 16. Celery Configuration

**CONFIRMED**

`mcube_ai/celery.py:535-544`:
```python
task_time_limit=300,              # 5 min hard limit
task_soft_time_limit=240,         # 4 min soft limit
worker_prefetch_multiplier=4,
worker_max_tasks_per_child=1000,
```

---

## CORRECTIONS to SYSTEM_REVIEW.md

### Correction 1: Strangle Scoring Has 11 Components (Not 10)

**Original claim:** "10-factor scoring (275 pts → 100 scale)"

**Actual code:** `enhanced_strangle_analyzer.py:71-84` defines **11 components**:

| Component | Weight |
|-----------|--------|
| vix_regime | 35 |
| global_markets | 30 |
| market_breadth | 25 |
| news_sentiment | 30 |
| pcr_analysis | 25 |
| oi_patterns | 25 |
| event_proximity | 20 |
| gap_movement | 25 |
| recent_nifty_momentum | 25 |
| fii_dii_flow | 20 |
| **technical_structure** | **15** |
| **Total** | **275** |

The 11th component `technical_structure` (15 pts) was missed in the original review. Total remains 275 pts.

---

### Correction 2: News Sentiment Is Soft Warning, Not Hard Reject (Futures)

**Original claim:** "7 hard reject filters" for futures strategy

**Actual code:** `enhanced_futures_analyzer.py:448-451` — News sentiment check explicitly does NOT raise `HardRejectError`:
```python
if not passed:
    # Soft warning — log but do NOT raise HardRejectError
    self.details['news_warning'] = news_result.get('message', 'Negative market sentiment')
    logger.warning(f"  Market News: {news_result.get('message', '')[:60]} - WARNING (proceeding)")
```

**Corrected:** 6 hard reject filters + 1 soft warning. Hard rejects: MWPL, Volatility, Piotroski, Promoter Pledge, FII Change, Analyst Upside.

---

### Correction 3: LLM 70% Confidence Threshold Not Enforced in Code

**Original claim:** "LLM confidence gate at 70%"

**Actual code:** `apps/llm/services/trade_validator.py` extracts confidence from LLM response but has no hard threshold gate. Default fallback confidence is 50% (line 311). The threshold may be enforced in the calling code (`icici_futures.py:150`) but was not found as a hard gate in `trade_validator.py` itself.

**Also:** When LLM is down, it returns `error_result` with `approved: False` — there is NO score-only fallback. The trade is simply blocked.

---

### Correction 4: R:R Hard Reject Not at 1.0 in adaptive_sl_target.py

**Original claim:** "R:R gate (reject if < 1.0, warn if < 1.5)"

**Actual code:** `adaptive_sl_target.py:186-192` — The function parameter `min_rr` defaults to 1.5. The gate checks `if rr_ratio < min_rr` and sets `rr_rejected = True`. There is no separate 1.0 hard reject.

**Note:** The 1.0 hard reject DOES exist in `trade_validation.py:44`:
```python
if rr_ratio < 1.0:
    rejection_reason = "R:R below 1.0"
```

So the R:R < 1.0 hard reject is in `trade_validation.py`, not `adaptive_sl_target.py`. The review incorrectly attributed this to the SL/target module. The combined behavior is correct: trade_validation rejects < 1.0, adaptive_sl_target flags < 1.5.

---

### Correction 5: Piotroski Gate Is Graduated (Not Purely Binary)

**Original claim:** "Piotroski 3 → reject, Piotroski 4 → pass. No gradual degradation"

**Actual code:** The hard reject IS binary (< 4 = reject). But within the Fundamental Quality scoring component, Piotroski IS graduated (`enhanced_futures_analyzer.py:1259-1271`):
- ≥ 7: 10 pts
- ≥ 5: 6 pts
- ≥ 4: 3 pts
- < 4: 0 pts (and hard reject prevents reaching this)

The review's characterization of "no gradual degradation" is partially incorrect — there IS gradual scoring above the reject threshold.

---

### Correction 6: Action Levels — Only 3, Not 4

**Original claim:** "Action levels: NONE → WARNING → STOP_TRADING → EMERGENCY_EXIT"

**Actual code:** `risk_manager.py` comment at line 56 mentions STOP_TRADING but the code never sets this value. Only 3 levels are used: `NONE`, `WARNING`, `EMERGENCY_EXIT`.

---

## Fully Verified Algorithm Constants (Quick Reference)

### Strangle Strategy
| Constant | Value | File:Line |
|----------|-------|-----------|
| NIFTY_LOT_SIZE (strangle) | 50 | strangle_position_sizer.py:36 |
| NIFTY_LOT_SIZE (iron condor) | 75 | iron_condor_position_sizer.py:28 |
| Base delta (≤2 DTE) | 0.75% | strangle_delta_algorithm.py:48 |
| Base delta (>2 DTE) | 0.50% | strangle_delta_algorithm.py:51 |
| VIX < 10 multiplier | 0.9× | strangle_delta_algorithm.py:90 |
| VIX 10-12.5 multiplier | 1.0× | strangle_delta_algorithm.py:93 |
| VIX 12.5-14 multiplier | 1.5× | strangle_delta_algorithm.py:96 |
| VIX 14-18 multiplier | 1.8× | strangle_delta_algorithm.py:99 |
| VIX > 18 multiplier | 2.0× | strangle_delta_algorithm.py:103 |
| Strike rounding | 50 pts | strangle_delta_algorithm.py:484-485 |
| MIN_ENHANCED_SCORE | 50 | kotak_strangle.py:55 |
| Entry window | 9:00-11:30 AM | kotak_strangle.py:63-64 |
| Profit target | 50% | kotak_strangle.py:69 |
| Premium target min/max | 3.0/3.5 INR | strike_calculator.py:207-209 |
| Premium floor | 1.75 INR | strike_calculator.py:209 |
| Averaging: attempt 1/2/3 | 20%/50%/50% | strangle_position_sizer.py:25-31 |
| Averaging trigger | 1% loss | strangle_position_sizer.py:30 |
| Delta alert threshold | 300 | delta_monitor.py:177 |

### Futures Strategy
| Constant | Value | File:Line |
|----------|-------|-----------|
| Total scoring weight | 315 pts | enhanced_futures_analyzer.py:87 |
| Passing threshold | 65/100 | enhanced_futures_analyzer.py:202, trade_validation.py:86 |
| MWPL reject | ≥ 80% | enhanced_futures_analyzer.py:65 |
| Volatility reject | ≥ 60% | enhanced_futures_analyzer.py:66 |
| Piotroski reject | < 4 | enhanced_futures_analyzer.py:67 |
| Promoter pledge reject | ≥ 30% | enhanced_futures_analyzer.py:68 |
| FII change reject | ≤ -2% | enhanced_futures_analyzer.py:69 |
| Analyst upside reject (LONG) | < 8% | enhanced_futures_analyzer.py:70 |
| R:R hard reject | < 1.0 | trade_validation.py:44 |
| R:R warning | < 1.5 | trade_validation.py:47, adaptive_sl_target.py:30 |
| VOLATILE regime score req | ≥ 75 | trade_validation.py:59 |
| RSI dead zone | 45-55 | contract_prefilter.py:80 |
| ADX prefilter | > 15 | contract_prefilter.py:65 |
| LLM model | deepseek-r1:7b | settings.py |

### SR Exit Engine
| Constant | Value | File:Line |
|----------|-------|-----------|
| SCORE_INSTITUTIONAL | 76 | sr_exit_engine.py:174 |
| SCORE_STRONG | 56 | sr_exit_engine.py:175 |
| SCORE_MODERATE | 31 | sr_exit_engine.py:176 |
| SR_CACHE_TTL_MINUTES | 15 | sr_exit_engine.py:136 |
| OI_CACHE_TTL_MINUTES | 5 | oi_wall_enricher.py:38 |
| VIX_SPIKE_THRESHOLD | 0.20 | sr_exit_engine.py:144 |
| EXPIRY_GAMMA_MODE_HOUR | 14 | sr_exit_engine.py:179 |
| GAP_NOISE_EXTENSION_MINS | 15 | sr_exit_engine.py:142 |
| NOISE_WINDOW_START | 9:30 | sr_exit_engine.py:140-141 |
| Adaptive SL: score > 70 | 0.3× ATR | sr_risk_interface.py:71 |
| Adaptive SL: score > 40 | 0.5× ATR | sr_risk_interface.py:73 |
| Adaptive SL: score ≤ 40 | 0.8× ATR | sr_risk_interface.py:75 |
| Structural pressure cooldown | 10 min | sr_risk_interface.py:29 |
| Partial close: score range | 40-60 | sr_risk_interface.py:252 |
| Partial close: percentage | 50% | sr_risk_interface.py:268 |

### Risk Management
| Constant | Value | File:Line |
|----------|-------|-----------|
| Warning threshold | 80% | risk/models.py:79-84 |
| Circuit breaker cooldown | 24 hours | risk_manager.py:411-413 |
| Monitor lock TTL | 55s | positions/tasks.py:56 |
| Sync failure threshold | 3 strikes | positions/tasks.py:61 |
| Sync failure TTL | 600s (10 min) | positions/tasks.py:62 |
| Exit suggestion cooldown | 5 min | monitor_dashboard.py:28 |
| SL P&L change gate | 2% | notification_templates.py:58 |
| Exit P&L change gate | 1% | notification_templates.py:92 |
| Near-SL warning | < 1% buffer | positions/tasks.py:290 |
| Hold flag clear time | 15:30+ IST | positions/tasks.py:547-556 |

### Greeks & BS Model
| Constant | Value | File:Line |
|----------|-------|-----------|
| Risk-free rate | 6.5% | greeks_calculator.py:317 |
| IV initial guess | 20% | greeks_calculator.py:276 |
| IV max iterations | 100 | greeks_calculator.py:257 |
| IV convergence tolerance | 0.0001 | greeks_calculator.py:258 |
| IV bounds | 1%-500% | greeks_calculator.py (clamp logic) |
| Time basis | Calendar days / 365 | greeks_calculator.py:343 |

### Celery Configuration
| Constant | Value | File:Line |
|----------|-------|-----------|
| task_time_limit | 300s (5 min) | celery.py:535 |
| task_soft_time_limit | 240s (4 min) | celery.py:536 |
| worker_prefetch_multiplier | 4 | celery.py:543 |
| worker_max_tasks_per_child | 1000 | celery.py:544 |
| result_expires | 3600s (1 hr) | celery.py:540 |

---

### Correction 7: should_send_exit_suggestion() Returns Bool, Not Named Constants

**Original claim (in memory):** Returns named status constants `DUPLICATE_SKIPPED`, `HELD_BY_USER`, `SUGGESTION_SENT`

**Actual code:** `monitor_dashboard.py:551` — Function returns `bool` only (True = send, False = skip). Status tracking is via database fields (`last_exit_reason`, `last_exit_sent_at`), not return value enums.

---

### Additional Verified Claims (Exit Manager & Notifications)

All of the following were **CONFIRMED** by the 7th verification agent:

| Claim | File:Line | Status |
|-------|-----------|--------|
| Exit priority: SL → Target → EOD → Expiry | exit_manager.py:36-40 | CONFIRMED |
| Strangle EOD: Thursday 15:15, profit ≥ 50% | exit_manager.py:149-165 | CONFIRMED |
| Futures EOD: Any day 15:15, profit ≥ 50% | exit_manager.py:183-198 | CONFIRMED |
| Strategy types: WEEKLY_NIFTY_STRANGLE, LLM_VALIDATED_FUTURES | exit_manager.py:150,183 | CONFIRMED |
| Exit suggestion cooldown: 5 min | monitor_dashboard.py:28 | CONFIRMED |
| Dashboard rolling window: last 3 snapshots | monitor_dashboard.py:25,190-193 | CONFIRMED |
| Master dashboard: one message/day, edited in-place | monitor_dashboard.py:147-168,513-521 | CONFIRMED |
| Exit buttons: [✅ Close Now] [⏸ Hold / Wait] | trade_confirmation.py:486-489 | CONFIRMED |
| All Telegram bot callbacks (exit, options, futures) | telegram_bot.py:823-829,704,732,747-750,772-774 | CONFIRMED |
| 12 notification event types | notification_templates.py:48-163 | CONFIRMED |
| Aggregation window: 30-60s | notification_templates.py (per template) | CONFIRMED |
| Escalation thresholds: 3/5/10 occurrences | escalation_tracker.py:16-20 | CONFIRMED |
| `<blockquote expandable>` for collapsible=True | notification_formatter.py:108-111 | CONFIRMED |
| NotificationPayload.collapsible default=True | notification_payload.py:151 | CONFIRMED |
| P&L gate: 2% SL, 1% exit suggestion | notification_templates.py:54,92 | CONFIRMED |
| Hold handler shows re-alert conditions | telegram_bot.py:2312-2322 | CONFIRMED |

---

## Updated SYSTEM_REVIEW.md Corrections Required

The following edits should be applied to `SYSTEM_REVIEW.md`:

1. **Section 2:** Change "10-factor scoring" → "11-factor scoring" (add `technical_structure: 15 pts`)
2. **Section 3:** Change "7 hard reject filters" → "6 hard reject filters + 1 soft warning (news)"
3. **Section 3:** Remove "LLM confidence gate at 70%" or note as unverified in code
4. **Section 3:** Clarify Piotroski has graduated scoring above the reject threshold
5. **Section 4:** R:R < 1.0 hard reject is in `trade_validation.py`, not `adaptive_sl_target.py`
6. **Section 7:** Remove STOP_TRADING from action levels (only NONE, WARNING, EMERGENCY_EXIT)
