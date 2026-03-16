"""
Core Celery Tasks

Infrastructure, market-open observation, and pre-market review tasks.
None of these tasks place orders or modify positions — they are purely
observational and informational, feeding data into Redis so downstream
trading tasks can gate on it.

Task schedule overview (all Mon–Fri):
  06:45  health_check_brokers          — broker API reachability
  08:55  review_overnight_positions    — news impact on carried positions
  09:00  send_morning_briefing         — single consolidated briefing msg
  09:00–09:20 (every 5 min)
         monitor_opening_volatility    — VIX + gap flags for strategy gate
"""

import logging
from datetime import timedelta
from decimal import Decimal
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.alerts.services.telegram_client import send_telegram_notification
from apps.alerts.services.notification_service import notify
from apps.core.utils.decorators import task_enabled_guard

logger = logging.getLogger(__name__)


def _broker_error_summary(e: Exception) -> str:
    """Return only the first line of an exception string — keeps user-visible errors clean."""
    return str(e).splitlines()[0][:120]

# ── Redis key registry ────────────────────────────────────────────────────────
# Documented here so all consumers have a single source of truth.

BROKER_HEALTH_KEY = 'broker_health'
BROKER_HEALTH_TTL = 7200           # 2 h: 06:45 → past 08:55 setup

MARKET_STABLE_KEY = 'market_stable_for_trading'
MARKET_VIX_KEY = 'market_open_vix'
MARKET_GAP_KEY = 'market_open_gap_pct'
MARKET_VOLATILITY_TTL = 3600       # 1 h: enough to cover 09:00–10:00 window

# VIX above this level flags the market as elevated-risk.
_VIX_WARN_THRESHOLD = 20.0
# |gap %| above this flags the open as a volatile gap.
_GAP_WARN_THRESHOLD = 1.5


@shared_task(name='apps.core.tasks.health_check_brokers')
@task_enabled_guard('health-check-brokers')
def health_check_brokers():
    """
    Broker API connectivity check (06:45 AM Mon–Fri).

    Attempts a lightweight read call against each active broker API.
    Results are stored in Redis under BROKER_HEALTH_KEY for two hours
    so setup_trading_day (08:55) and execute_futures_algorithm (09:40)
    can gate on them without re-running the check.

    On any failure: sends a CRITICAL Telegram alert immediately so the
    trader has 2+ hours to resolve auth/network issues before market open.

    Does NOT place orders or modify any state.
    """
    from apps.accounts.models import BrokerAccount

    results = {}
    failed_brokers = []

    # ── Kotak Neo ─────────────────────────────────────────────────────────────
    kotak_accounts = BrokerAccount.objects.filter(broker='KOTAK', is_active=True)
    if kotak_accounts.exists():
        try:
            from tools.neo import get_neo_api
            neo = get_neo_api()
            # get_margin() is a lightweight read — no order risk
            neo.get_margin()
            results['neo'] = 'OK'
            logger.info("health_check_brokers: Kotak Neo OK")
        except Exception as e:
            results['neo'] = f'FAIL: {e}'
            failed_brokers.append(f"Kotak Neo: {e}")
            logger.error(f"health_check_brokers: Kotak Neo FAIL — {e}")
    else:
        results['neo'] = 'NO_ACCOUNT'
        logger.info("health_check_brokers: No active Kotak account, skipping Neo check")

    # ── ICICI Breeze ──────────────────────────────────────────────────────────
    icici_accounts = BrokerAccount.objects.filter(broker='ICICI', is_active=True)
    if icici_accounts.exists():
        try:
            from apps.brokers.integrations.breeze_module.api_classes import get_breeze_api
            breeze = get_breeze_api()
            # Instantiation calls get_breeze_client() which validates the session
            _ = breeze.breeze   # access the underlying client to trigger init
            results['breeze'] = 'OK'
            logger.info("health_check_brokers: ICICI Breeze OK")
        except Exception as e:
            results['breeze'] = f'FAIL: {e}'
            failed_brokers.append(f"ICICI Breeze: {e}")
            logger.error(f"health_check_brokers: ICICI Breeze FAIL — {e}")
    else:
        results['breeze'] = 'NO_ACCOUNT'
        logger.info("health_check_brokers: No active ICICI account, skipping Breeze check")

    # ── Persist results ───────────────────────────────────────────────────────
    cache.set(BROKER_HEALTH_KEY, results, timeout=BROKER_HEALTH_TTL)
    logger.info(f"health_check_brokers: results stored → {results}")

    # ── Alert on failures ─────────────────────────────────────────────────────
    if failed_brokers:
        # Strip full exception tracebacks — show only first line per broker
        clean_failures = []
        for f in failed_brokers:
            # f is e.g. "Kotak Neo: ConnectionError: ..."
            parts = f.split(': ', 1)
            if len(parts) == 2:
                broker_name, err = parts
                clean_failures.append(f"{broker_name}: {_broker_error_summary(Exception(err))}")
            else:
                clean_failures.append(f)
        notify('BROKER_HEALTH',
            title='Broker Health Check Failed',
            task='health_check_brokers',
            context=clean_failures + [
                "Market opens in ~2.5 hours",
                "Resolve authentication issues before 09:15",
            ],
            collapsible=False,
        )
    else:
        active_brokers = [k for k, v in results.items() if v == 'OK']
        if active_brokers:
            logger.info(f"health_check_brokers: all active brokers healthy: {active_brokers}")

    return {
        'success': True,
        'results': results,
        'failed': failed_brokers,
    }


@shared_task(name='apps.core.tasks.monitor_opening_volatility')
@task_enabled_guard('monitor-opening-volatility')
def monitor_opening_volatility():
    """
    Opening volatility monitor (09:00–09:20, every 5 min, Mon–Fri).

    Measures India VIX and Nifty gap-vs-previous-close at market open.
    Writes market_stable_for_trading = True/False to Redis so that
    evaluate_options_strategy (09:30) can soft-defer if the open is wild.

    Thresholds (conservative defaults):
        VIX  > 20   → elevated risk
        |gap%| > 1.5% → volatile gap open
    Either condition alone marks the market as unstable.

    Sends a WARNING notification if unstable; logs silently if stable.
    Does NOT modify any trading state.
    """
    try:
        from apps.strategies.shared.market_data import get_vix, get_nifty_price
        from apps.brokers.models import HistoricalPrice

        now = timezone.now()

        # ── VIX ──────────────────────────────────────────────────────────────
        vix = float(get_vix())

        # ── Gap vs previous close ─────────────────────────────────────────────
        # Fetch yesterday's Nifty 50 close from HistoricalPrice.
        yesterday = (now - timedelta(days=1)).date()
        prev_close_obj = (
            HistoricalPrice.objects
            .filter(symbol='NIFTY 50', timestamp__date=yesterday)
            .order_by('-timestamp')
            .first()
        )
        current_price = float(get_nifty_price())
        if prev_close_obj and float(prev_close_obj.close) > 0:
            prev_close = float(prev_close_obj.close)
            gap_pct = (current_price - prev_close) / prev_close * 100
        else:
            gap_pct = 0.0
            logger.warning("monitor_opening_volatility: prev close not found, gap_pct=0")

        is_stable = (vix < _VIX_WARN_THRESHOLD) and (abs(gap_pct) < _GAP_WARN_THRESHOLD)

        # ── Persist to Redis ──────────────────────────────────────────────────
        cache.set(MARKET_STABLE_KEY, is_stable, timeout=MARKET_VOLATILITY_TTL)
        cache.set(MARKET_VIX_KEY, vix, timeout=MARKET_VOLATILITY_TTL)
        cache.set(MARKET_GAP_KEY, round(gap_pct, 3), timeout=MARKET_VOLATILITY_TTL)

        logger.info(
            f"monitor_opening_volatility: VIX={vix:.1f} gap={gap_pct:.2f}% "
            f"stable={is_stable}"
        )

        if not is_stable:
            reasons = []
            if vix >= _VIX_WARN_THRESHOLD:
                reasons.append(f"VIX={vix:.1f} (≥{_VIX_WARN_THRESHOLD})")
            if abs(gap_pct) >= _GAP_WARN_THRESHOLD:
                reasons.append(f"Gap={gap_pct:+.2f}% (≥±{_GAP_WARN_THRESHOLD}%)")
            notify('RISK_WARNING',
                title='Market Open: Elevated Volatility',
                task='monitor_opening_volatility',
                metrics={
                    'VIX': f"{vix:.1f}",
                    'Gap': f"{gap_pct:+.2f}%",
                },
                context=reasons + ["Strategy evaluation may be deferred until market stabilises"],
                collapsible=False,
            )

        return {
            'success': True,
            'vix': vix,
            'gap_pct': round(gap_pct, 3),
            'is_stable': is_stable,
        }

    except Exception as e:
        logger.error(f"monitor_opening_volatility failed: {e}", exc_info=True)
        # On failure: leave MARKET_STABLE_KEY absent so evaluate_options_strategy
        # treats missing flag as "proceed normally" (fail-open, not fail-closed).
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.core.tasks.review_overnight_positions')
@task_enabled_guard('review-overnight-positions')
def review_overnight_positions():
    """
    Overnight position news review (08:55 AM Mon–Fri).

    For every DB-OPEN position, checks if today's or yesterday's news
    contains high-impact negative sentiment for that instrument.
    Sends a WARNING alert listing at-risk positions so the trader can
    decide before market open whether to tighten SL or exit on open.

    Read-only: no positions are modified.
    """
    try:
        from apps.positions.models import Position
        from apps.data.models import NewsArticle

        open_positions = list(
            Position.objects.filter(status='OPEN').select_related('account')
        )
        if not open_positions:
            logger.info("review_overnight_positions: no open positions to review")
            return {'success': True, 'open_positions': 0}

        # Collect unique instrument symbols from open positions
        symbols = list({p.instrument for p in open_positions if p.instrument})
        if not symbols:
            return {'success': True, 'open_positions': len(open_positions), 'symbols': 0}

        # News window: last 24 hours
        since = timezone.now() - timedelta(hours=24)

        at_risk = []
        for symbol in symbols:
            # JSONField array membership filter: checks if symbol is in the array
            negative_news = NewsArticle.objects.filter(
                created_at__gte=since,
                sentiment_label='NEGATIVE',
                symbols_mentioned__contains=symbol,
            ).order_by('-created_at').first()

            if negative_news:
                at_risk.append({
                    'symbol': symbol,
                    'title': negative_news.title[:100] if hasattr(negative_news, 'title') else '',
                    'sentiment': negative_news.sentiment_label,
                    'article_id': negative_news.id,
                })

        if at_risk:
            lines = [
                f"⚠️ <b>Overnight Risk Review</b>  [08:55]\n",
                f"Negative news detected for held positions:\n",
            ]
            for item in at_risk:
                lines.append(f"  • <b>{item['symbol']}</b>: {item['title']}")
            lines.append(
                "\nReview positions before market opens. "
                "Consider tightening stop-losses."
            )
            at_risk_lines = [f"{item['symbol']}: {item['title']}" for item in at_risk]
            notify('RISK_WARNING',
                title='Overnight Position Risk',
                task='review_overnight_positions',
                context=at_risk_lines + [
                    "Review positions before market opens",
                    "Consider tightening stop-losses",
                ],
                collapsible=False,
            )
        else:
            logger.info(
                f"review_overnight_positions: no negative news for {symbols}"
            )

        return {
            'success': True,
            'open_positions': len(open_positions),
            'symbols_checked': len(symbols),
            'at_risk_count': len(at_risk),
            'at_risk_symbols': [i['symbol'] for i in at_risk],
        }

    except Exception as e:
        logger.error(f"review_overnight_positions failed: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.core.tasks.send_morning_briefing')
@task_enabled_guard('send-morning-briefing')
def send_morning_briefing():
    """
    Morning briefing (09:00 AM Mon–Fri).

    Sends ONE consolidated Telegram message covering everything the trader
    needs to know at market open — replacing multiple scattered pre-market
    notifications with a single, structured digest.

    Sections:
      ✅ Broker connectivity
      📊 VIX + opening gap
      ⚠️ Overnight risks (from review_overnight_positions)
      📋 Open positions at market open
      🟢/🔴 Trading day status (from setup_trading_day)
    """
    try:
        from apps.positions.models import Position
        from apps.strategies.models import TradingDaySetup
        from datetime import date

        now = timezone.now()
        today = date.today()
        lines = [f"📊 <b>mCube Morning Brief</b>  {today.strftime('%d %b %Y')}\n"]

        # ── Config / mode ─────────────────────────────────────────────────────
        from apps.core.models import TradingCoreConfig
        from apps.alerts.services.notification_payload import NotificationPayload
        from apps.alerts.services.telegram_client import send_notification as _send_notif

        config = TradingCoreConfig.get_instance()
        mode_label = config.get_notification_level_display_short()
        sizing_label = config.get_position_sizing_display_short()

        # ── Broker health ─────────────────────────────────────────────────────
        broker_health = cache.get(BROKER_HEALTH_KEY, {})
        neo_icon = '✅' if broker_health.get('neo') == 'OK' else (
            '➖' if broker_health.get('neo') == 'NO_ACCOUNT' else '❌'
        )
        breeze_icon = '✅' if broker_health.get('breeze') == 'OK' else (
            '➖' if broker_health.get('breeze') == 'NO_ACCOUNT' else '❌'
        )

        # ── Market open stats ─────────────────────────────────────────────────
        vix = cache.get(MARKET_VIX_KEY)
        gap = cache.get(MARKET_GAP_KEY)
        is_stable = cache.get(MARKET_STABLE_KEY, True)
        stable_icon = '🟢' if is_stable else '🔴'
        vix_str = f"{vix:.1f}" if vix is not None else 'N/A'
        gap_str = f"{gap:+.2f}%" if gap is not None else 'N/A'

        # ── Trading day setup ─────────────────────────────────────────────────
        day_status = "setup not run yet"
        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
            tradable_icon = '✅' if setup.is_tradable else '❌'
            day_status = f"{tradable_icon} {(setup.setup_reason or '')[:80]}"
        except TradingDaySetup.DoesNotExist:
            day_status = "⚠️ setup not run yet"

        # ── Open positions ────────────────────────────────────────────────────
        open_pos = list(Position.objects.filter(status='OPEN'))
        pos_lines = []
        for pos in open_pos:
            _pnl = pos.unrealized_pnl or 0
            _emoji = '🟢' if _pnl >= 0 else '🔴'
            pos_lines.append(f"{_emoji} {pos.label}  ₹{_pnl:+,.0f}")

        # Build payload
        market_section = {
            'Brokers': f"Neo {neo_icon}  ·  Breeze {breeze_icon}",
            'VIX': f"{vix_str}",
            'Gap': f"{gap_str}",
            'Stability': f"{stable_icon} {'Stable' if is_stable else 'Elevated Risk'}",
            'Day': day_status,
        }

        open_positions_context: list[str] = (
            pos_lines if pos_lines else ["No open positions — clean start"]
        )

        payload = NotificationPayload(
            title='Morning Briefing',
            status='INFO',
            task='send_morning_briefing',
            timestamp=now,
            metrics={
                'Mode': mode_label,
                'Sizing': sizing_label,
            },
            market=market_section,
            context=open_positions_context,
            priority='INFO',
            mode_label=mode_label,
            sizing_label=sizing_label,
        )
        _send_notif(payload)

        return {
            'success': True,
            'open_positions': len(open_pos),
            'vix': vix,
            'gap_pct': gap,
            'market_stable': is_stable,
        }

    except Exception as e:
        logger.error(f"send_morning_briefing failed: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
