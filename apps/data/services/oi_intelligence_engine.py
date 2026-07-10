"""
OI Intelligence Engine

Converts raw daily OI snapshots into institutional-grade interpretation:
  - Classifies each day's buildup (Long Build-up, Short Build-up, etc.)
  - Calculates a 0-100 OI Momentum Score from weighted recent history
  - Detects consecutive patterns and advanced signals (capitulation, squeeze, etc.)
  - Generates weekly/monthly summaries and an AI narrative via rule-based templates
  - Preserves each day's snapshot before ContractData is overwritten
  - Auto-purges history older than 65 trading days
"""

import logging
from datetime import date, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.data.models import (
    ContractData,
    ContractStockData,
    TLStockData,
    OIHistorySnapshot,
    OIIntelligence,
)

logger = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────────

BUILDUP_LABELS = {
    'LONG_BUILDUP': 'Long Build-up',
    'SHORT_BUILDUP': 'Short Build-up',
    'LONG_UNWINDING': 'Long Unwinding',
    'SHORT_COVERING': 'Short Covering',
    'NEUTRAL': 'Neutral',
}

BUILDUP_SENTIMENTS = {
    'LONG_BUILDUP': 'BULLISH',
    'SHORT_BUILDUP': 'BEARISH',
    'LONG_UNWINDING': 'BEARISH',
    'SHORT_COVERING': 'BULLISH',
    'NEUTRAL': 'NEUTRAL',
}

BULLISH_TYPES = {'LONG_BUILDUP', 'SHORT_COVERING'}
BEARISH_TYPES = {'SHORT_BUILDUP', 'LONG_UNWINDING'}

# Momentum score weights: most-recent session carries highest weight
# Applied to last 20 sessions; sessions beyond 20 score with flat low weight
SESSION_WEIGHTS = {
    0: 10,   # today
    1: 8,
    2: 7,
    3: 6,
    4: 5,
    5: 4,
    6: 4,
    7: 3,
    8: 3,
    9: 3,
    10: 2, 11: 2, 12: 2, 13: 2, 14: 2,
    15: 1, 16: 1, 17: 1, 18: 1, 19: 1,
}

BUILDUP_POINT_VALUES = {
    'LONG_BUILDUP': 100,
    'SHORT_COVERING': 70,
    'NEUTRAL': 50,
    'LONG_UNWINDING': 30,
    'SHORT_BUILDUP': 0,
}

# Days of history to keep
HISTORY_RETENTION_DAYS = 65


# ─── Core classification ──────────────────────────────────────────────────────

def classify_buildup(price_change_pct: Optional[float], oi_change_pct: Optional[float]):
    """
    Classify today's OI buildup from price and OI direction.

    Returns (buildup_type, label, interpretation, confidence_score)
    """
    if price_change_pct is None or oi_change_pct is None:
        return 'NEUTRAL', 'Neutral', 'Insufficient data for OI classification.', 40.0

    # Magnitude-based confidence — larger moves = higher conviction
    magnitude = (abs(price_change_pct) + abs(oi_change_pct)) / 2
    confidence = min(40.0 + magnitude * 5.0, 95.0)

    if price_change_pct > 0 and oi_change_pct > 0:
        buildup = 'LONG_BUILDUP'
        interp = (
            "Fresh buyers are entering — new long positions being added. "
            "Rising price with rising OI indicates strong bullish conviction. "
            "Most favourable OI structure for long trades."
        )
    elif price_change_pct < 0 and oi_change_pct > 0:
        buildup = 'SHORT_BUILDUP'
        interp = (
            "New short sellers are entering — bearish conviction increasing. "
            "Falling price with rising OI signals fresh short build-up. "
            "Selling pressure is strengthening."
        )
    elif price_change_pct > 0 and oi_change_pct < 0:
        buildup = 'SHORT_COVERING'
        interp = (
            "Existing shorts are closing positions — buying driven by exits, not fresh optimism. "
            "Price rises but OI falls, suggesting the rally may not be sustainable. "
            "Short covering typically carries lower bullish confidence than Long Build-up."
        )
    elif price_change_pct < 0 and oi_change_pct < 0:
        buildup = 'LONG_UNWINDING'
        interp = (
            "Existing longs are exiting — weak hands getting out. "
            "Falling price with falling OI indicates long liquidation. "
            "Often appears near market bottoms; watch for follow-through on the next session."
        )
    else:
        buildup = 'NEUTRAL'
        interp = "No clear directional bias — price and OI changes are minimal."
        confidence = 40.0

    return buildup, BUILDUP_LABELS[buildup], interp, round(confidence, 1)


# ─── Momentum score ───────────────────────────────────────────────────────────

def calculate_oi_momentum_score(history: list) -> float:
    """
    Compute a 0-100 OI Momentum Score from a list of OIHistorySnapshot records,
    ordered most-recent first.

    Higher score = stronger bullish OI positioning.
    """
    if not history:
        return 50.0

    total_weight = 0
    weighted_sum = 0.0

    for i, snap in enumerate(history[:20]):
        weight = SESSION_WEIGHTS.get(i, 1)
        points = BUILDUP_POINT_VALUES.get(snap.buildup_type, 50)
        weighted_sum += weight * points
        total_weight += weight

    if total_weight == 0:
        return 50.0

    return round(weighted_sum / total_weight, 1)


# ─── Consecutive pattern ──────────────────────────────────────────────────────

def detect_consecutive_pattern(history: list) -> tuple:
    """
    Find the longest consecutive run of the same buildup type at the start
    of history (most-recent first).

    Returns (n_days, buildup_type, label)
    """
    if not history:
        return 1, 'NEUTRAL', 'Neutral'

    current_type = history[0].buildup_type
    count = 1
    for snap in history[1:]:
        if snap.buildup_type == current_type:
            count += 1
        else:
            break

    return count, current_type, BUILDUP_LABELS[current_type]


# ─── Advanced pattern detection ────────────────────────────────────────────────

def detect_advanced_pattern(history: list, consecutive_days: int, consecutive_type: str) -> tuple:
    """
    Detect advanced institutional patterns from recent history.

    Returns (pattern_key, pattern_description)
    """
    if len(history) < 3:
        return 'NONE', ''

    types = [s.buildup_type for s in history[:10]]

    # Capitulation: Long Unwinding streak followed by Short Covering
    if len(types) >= 3:
        if types[0] in ('SHORT_COVERING', 'LONG_BUILDUP') and types[1] == 'LONG_UNWINDING' and types[2] == 'LONG_UNWINDING':
            return 'CAPITULATION', (
                "Potential capitulation bottom detected — extended long unwinding now reversing. "
                "Weak hands appear to have been flushed out."
            )

    # Short squeeze setup: consecutive Short Build-up followed by Short Covering
    if len(types) >= 3:
        if types[0] == 'SHORT_COVERING' and all(t == 'SHORT_BUILDUP' for t in types[1:4]):
            return 'SHORT_SQUEEZE', (
                "Short squeeze setup — extended short positioning now reversing. "
                "Shorts forced to cover as price bounces."
            )

    # Distribution: multiple Long Build-up then rapid shift to Short Build-up
    if len(types) >= 5:
        if types[0] in ('SHORT_BUILDUP', 'LONG_UNWINDING') and sum(1 for t in types[1:5] if t == 'LONG_BUILDUP') >= 3:
            return 'DISTRIBUTION', (
                "Distribution pattern detected — prior accumulation days now followed by selling pressure. "
                "Institutional money may be exiting long positions."
            )

    # Strong accumulation: 4+ consecutive Long Build-up
    if consecutive_days >= 4 and consecutive_type == 'LONG_BUILDUP':
        return 'ACCUMULATION', (
            f"{consecutive_days}-session institutional accumulation streak. "
            "Persistent fresh long additions signal high conviction buying."
        )

    # Persistent bearish: 4+ consecutive Short Build-up
    if consecutive_days >= 4 and consecutive_type == 'SHORT_BUILDUP':
        return 'DISTRIBUTION', (
            f"{consecutive_days} consecutive short build-up sessions. "
            "Institutional traders appear to be building a significant short position."
        )

    # Trend exhaustion: many sessions then OI dropping
    if len(types) >= 6:
        recent = types[:3]
        prior = types[3:6]
        if all(t == 'SHORT_COVERING' for t in recent) and all(t == 'LONG_BUILDUP' for t in prior):
            return 'TREND_EXHAUSTION', (
                "Trend exhaustion signal — earlier Long Build-up sessions now transitioning to Short Covering. "
                "Fresh buying has dried up; rally may be losing steam."
            )

    # High conviction trend
    if len(history) >= 10:
        bullish_in_10 = sum(1 for s in history[:10] if s.buildup_type in BULLISH_TYPES)
        if bullish_in_10 >= 8:
            return 'HIGH_CONVICTION', (
                f"{bullish_in_10}/10 recent sessions show bullish OI structure. "
                "High conviction uptrend backed by consistent institutional buying."
            )

    return 'NONE', ''


# ─── Weekly and monthly summaries ─────────────────────────────────────────────

def generate_weekly_summary(last_5: list) -> str:
    if not last_5:
        return "Insufficient data for weekly summary."

    counts = {}
    for snap in last_5:
        counts[snap.buildup_type] = counts.get(snap.buildup_type, 0) + 1

    dominant = max(counts, key=counts.get)
    n = counts[dominant]
    total = len(last_5)

    sentiment = BUILDUP_SENTIMENTS.get(dominant, 'NEUTRAL')
    label = BUILDUP_LABELS.get(dominant, dominant)

    if dominant == 'LONG_BUILDUP':
        verdict = "Bullish — fresh long positions are being added consistently."
    elif dominant == 'SHORT_BUILDUP':
        verdict = "Bearish — persistent short selling with rising OI."
    elif dominant == 'SHORT_COVERING':
        verdict = "Cautiously bullish — shorts covering, but fresh longs not yet entering."
    elif dominant == 'LONG_UNWINDING':
        verdict = "Weak — longs exiting; potential continuation of downtrend."
    else:
        verdict = "Neutral — no dominant positioning bias this week."

    parts = [f"Last {total} sessions: {n} × {label}."]
    if len(counts) > 1:
        others = ", ".join(
            f"{v} × {BUILDUP_LABELS.get(k, k)}"
            for k, v in counts.items() if k != dominant
        )
        parts.append(f"Also: {others}.")
    parts.append(verdict)
    return " ".join(parts)


def generate_monthly_summary(last_20: list) -> str:
    if not last_20:
        return "Insufficient data for monthly summary."

    total = len(last_20)
    bullish = sum(1 for s in last_20 if s.buildup_type in BULLISH_TYPES)
    bearish = sum(1 for s in last_20 if s.buildup_type in BEARISH_TYPES)
    neutral = total - bullish - bearish

    bullish_pct = round(bullish / total * 100)
    bearish_pct = round(bearish / total * 100)

    lb = sum(1 for s in last_20 if s.buildup_type == 'LONG_BUILDUP')
    sb = sum(1 for s in last_20 if s.buildup_type == 'SHORT_BUILDUP')
    sc = sum(1 for s in last_20 if s.buildup_type == 'SHORT_COVERING')
    lu = sum(1 for s in last_20 if s.buildup_type == 'LONG_UNWINDING')

    if bullish_pct >= 70:
        character = "Dominant Bullish Accumulation"
        note = "Strong institutional buying across the month."
    elif bullish_pct >= 55:
        character = "Moderately Bullish"
        note = "More bullish sessions than bearish, with some consolidation."
    elif bearish_pct >= 70:
        character = "Dominant Bearish Distribution"
        note = "Sustained institutional selling pressure across the month."
    elif bearish_pct >= 55:
        character = "Moderately Bearish"
        note = "Bears have the edge over the past month."
    else:
        character = "Mixed / Neutral"
        note = "No clear dominant positioning bias over the past month."

    breakdown = (
        f"Long Build-up: {lb}, Short Build-up: {sb}, "
        f"Short Covering: {sc}, Long Unwinding: {lu}"
    )
    return (
        f"Last {total} sessions — {bullish_pct}% bullish, {bearish_pct}% bearish. "
        f"{character}. {note} Breakdown: {breakdown}."
    )


# ─── AI Narrative ─────────────────────────────────────────────────────────────

def generate_ai_narrative(
    buildup_type: str,
    consecutive_days: int,
    consecutive_type: str,
    oi_momentum_score: float,
    pattern: str,
    pattern_description: str,
    weekly_summary: str,
    monthly_summary: str,
    history: list,
) -> str:
    """
    Rule-based narrative paragraph — no LLM required.
    """
    label = BUILDUP_LABELS.get(buildup_type, buildup_type)
    consec_label = BUILDUP_LABELS.get(consecutive_type, consecutive_type)

    # Opening sentence about current session
    if buildup_type == 'LONG_BUILDUP':
        opening = f"Today's session shows a {label}, the most constructive OI structure, with fresh buyers entering as price and OI both advance."
    elif buildup_type == 'SHORT_BUILDUP':
        opening = f"Today exhibits a {label} — new short sellers are positioning as price declines with rising OI, signalling increasing bearish conviction."
    elif buildup_type == 'SHORT_COVERING':
        opening = f"Today's {label} indicates existing shorts are closing out positions. While price rises, the lack of fresh long participation suggests caution."
    elif buildup_type == 'LONG_UNWINDING':
        opening = f"Today shows {label} — longs are exiting positions, driving price lower alongside falling OI. This often appears near market bottoms."
    else:
        opening = "Today's OI movement is neutral with no clear directional bias."

    # Consecutive context
    if consecutive_days >= 3:
        consec_note = f" This is the {consecutive_days}{'rd' if consecutive_days == 3 else 'th'} consecutive session of {consec_label}, suggesting {'strengthening institutional conviction' if consecutive_type in BULLISH_TYPES else 'persistent bearish positioning'}."
    elif consecutive_days == 2:
        consec_note = f" This follows a second straight session of {consec_label}."
    else:
        consec_note = ""

    # Momentum context
    if oi_momentum_score >= 75:
        momentum_note = " The OI Momentum Score of {:.0f}/100 reflects strong bullish positioning over recent sessions.".format(oi_momentum_score)
    elif oi_momentum_score >= 55:
        momentum_note = " The OI Momentum Score of {:.0f}/100 indicates moderately positive positioning.".format(oi_momentum_score)
    elif oi_momentum_score >= 40:
        momentum_note = " The OI Momentum Score of {:.0f}/100 is neutral — no dominant bias in recent sessions.".format(oi_momentum_score)
    else:
        momentum_note = " The OI Momentum Score of {:.0f}/100 reflects bearish positioning in recent sessions.".format(oi_momentum_score)

    # Pattern note
    pattern_note = f" {pattern_description}" if pattern_description else ""

    # Monthly character
    monthly_note = ""
    if history and len(history) >= 15:
        total = len(history[:20])
        bullish = sum(1 for s in history[:20] if s.buildup_type in BULLISH_TYPES)
        pct = round(bullish / total * 100)
        if pct >= 65:
            monthly_note = f" Over the past {total} sessions, {pct}% were bullish OI days, confirming a broader accumulation trend."
        elif pct <= 35:
            monthly_note = f" Over the past {total} sessions, only {pct}% were bullish OI days, reflecting broader distribution pressure."

    return opening + consec_note + momentum_note + pattern_note + monthly_note


# ─── Snapshot capture ─────────────────────────────────────────────────────────

def capture_snapshot(symbol: str, trading_date: date) -> Optional[OIHistorySnapshot]:
    """
    Read current ContractData + ContractStockData + TLStockData for a symbol
    and save/update an OIHistorySnapshot record.
    """
    futures = ContractData.objects.filter(
        symbol=symbol,
        option_type__in=['FUT', 'FUTURES', 'FUTURE'],
    ).order_by('-traded_contracts').first()

    csd = ContractStockData.objects.filter(nse_code=symbol).first()
    tl = TLStockData.objects.filter(nsecode=symbol).first()

    if not futures and not csd:
        return None

    price_change_pct = None
    if tl:
        price_change_pct = tl.day_change_pct
    elif futures:
        price_change_pct = futures.pct_day_change

    oi_change_pct = None
    if csd:
        oi_change_pct = csd.fno_total_oi_change_pct
    elif futures:
        oi_change_pct = futures.pct_oi_change

    buildup, _label, _interp, confidence = classify_buildup(price_change_pct, oi_change_pct)

    snap, _ = OIHistorySnapshot.objects.update_or_create(
        symbol=symbol,
        trading_date=trading_date,
        defaults={
            'close_price': tl.current_price if tl else (futures.spot if futures else None),
            'price_change_pct': price_change_pct,
            'futures_price': futures.price if futures else None,
            'oi': futures.oi if futures else None,
            'oi_change_pct': oi_change_pct,
            'total_fno_oi': csd.fno_total_oi if csd else None,
            'pcr_oi': csd.fno_pcr_oi if csd else None,
            'mwpl_pct': csd.fno_mwpl_pct if csd else None,
            'rollover_pct': csd.fno_rollover_pct if csd else None,
            'volume': tl.day_volume if tl else None,
            'traded_contracts': futures.traded_contracts if futures else None,
            'delivery_pct': tl.delivery_volume_pct_eod if tl else None,
            'buildup_type': buildup,
            'confidence_score': confidence,
        }
    )
    return snap


# ─── Main orchestrator ────────────────────────────────────────────────────────

def process_stock_oi_intelligence(symbol: str, trading_date: date) -> Optional[OIIntelligence]:
    """
    Full pipeline for one stock:
      1. Capture today's snapshot from live ContractData
      2. Load 65-day history
      3. Compute momentum score, consecutive pattern, advanced pattern
      4. Generate summaries + narrative
      5. Save OIIntelligence record
    """
    try:
        with transaction.atomic():
            # Step 1: capture snapshot
            snap = capture_snapshot(symbol, trading_date)
            if not snap:
                logger.debug(f"[OI Intelligence] No data for {symbol} on {trading_date} — skipping")
                return None

            # Step 2: load recent history (most-recent first)
            history = list(
                OIHistorySnapshot.objects.filter(symbol=symbol)
                .order_by('-trading_date')[:20]
            )

            if not history:
                return None

            # Step 3: compute scores and patterns
            momentum_score = calculate_oi_momentum_score(history)
            snap.oi_momentum_score = momentum_score
            snap.save(update_fields=['oi_momentum_score'])

            consecutive_days, consecutive_type, _consec_label = detect_consecutive_pattern(history)
            pattern_key, pattern_desc = detect_advanced_pattern(history, consecutive_days, consecutive_type)

            buildup = history[0].buildup_type
            _b, buildup_label, interpretation, confidence = classify_buildup(
                snap.price_change_pct, snap.oi_change_pct
            )

            # Step 4: summaries
            weekly_summary = generate_weekly_summary(history[:5])
            monthly_summary = generate_monthly_summary(history[:20])
            narrative = generate_ai_narrative(
                buildup_type=buildup,
                consecutive_days=consecutive_days,
                consecutive_type=consecutive_type,
                oi_momentum_score=momentum_score,
                pattern=pattern_key,
                pattern_description=pattern_desc,
                weekly_summary=weekly_summary,
                monthly_summary=monthly_summary,
                history=history,
            )

            # Monthly stats for display
            total_20 = len(history[:20])
            bullish_count = sum(1 for s in history[:20] if s.buildup_type in BULLISH_TYPES)
            bearish_count = total_20 - bullish_count
            last_5_types = [s.buildup_type for s in history[:5]]

            # Step 5: save intelligence record
            intel, _ = OIIntelligence.objects.update_or_create(
                symbol=symbol,
                trading_date=trading_date,
                defaults={
                    'buildup_type': buildup,
                    'buildup_label': buildup_label,
                    'interpretation_text': interpretation,
                    'consecutive_days': consecutive_days,
                    'consecutive_type': consecutive_type,
                    'pattern_detected': pattern_key,
                    'pattern_description': pattern_desc,
                    'oi_momentum_score': momentum_score,
                    'confidence_level': confidence,
                    'weekly_summary': weekly_summary,
                    'monthly_summary': monthly_summary,
                    'ai_narrative': narrative,
                    'last_20_bullish_count': bullish_count,
                    'last_20_bearish_count': bearish_count,
                    'last_5_buildup_types': last_5_types,
                }
            )
            return intel

    except Exception as e:
        logger.error(f"[OI Intelligence] Error processing {symbol}: {e}", exc_info=True)
        return None


def purge_old_snapshots():
    """Remove OIHistorySnapshot records older than HISTORY_RETENTION_DAYS trading days."""
    cutoff = date.today() - timedelta(days=HISTORY_RETENTION_DAYS * 1.5)  # calendar days buffer
    deleted, _ = OIHistorySnapshot.objects.filter(trading_date__lt=cutoff).delete()
    if deleted:
        logger.info(f"[OI Intelligence] Purged {deleted} old OI history snapshots (before {cutoff})")
    return deleted


def run_daily_oi_intelligence(trading_date: Optional[date] = None):
    """
    Process OI intelligence for all F&O stocks with data today.
    Called by the Celery task after Trendlyne import completes.
    """
    if trading_date is None:
        trading_date = timezone.localdate()

    symbols = list(
        ContractData.objects.filter(option_type__in=['FUT', 'FUTURES', 'FUTURE'])
        .values_list('symbol', flat=True)
        .distinct()
    )

    if not symbols:
        logger.warning("[OI Intelligence] No FUTURE contracts found in ContractData — is data imported?")
        return {'processed': 0, 'errors': 0}

    logger.info(f"[OI Intelligence] Processing {len(symbols)} symbols for {trading_date}")

    processed = 0
    errors = 0
    for symbol in symbols:
        result = process_stock_oi_intelligence(symbol, trading_date)
        if result:
            processed += 1
        else:
            errors += 1

    # Purge stale records
    purge_old_snapshots()

    logger.info(f"[OI Intelligence] Done — processed={processed}, skipped/errors={errors}")
    return {'processed': processed, 'errors': errors, 'total': len(symbols)}
