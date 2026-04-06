"""
Strategy Celery Tasks

Automated tasks for strategy evaluation and execution.

=============================================================================
DAILY TRADING WORKFLOW (IST Timezone)
=============================================================================

PRE-MARKET (8:00 - 9:15 AM):
- 8:55 AM: setup_trading_day - Evaluate data, determine if day is tradable

MARKET OPEN (9:15 AM):
- 9:15 AM: start_trading_day - Validate market opening, check news/changes

STRATEGY EVALUATION (9:30 - 9:45 AM):
- 9:30 AM: evaluate_options_strategy - Decide strangle vs iron condor
- 9:40 AM: start_options_trade - Begin implementing option trades
- 9:40 AM: execute_futures_algorithm - Screen and present futures opportunities

AVERAGING WINDOW (9:40 - 10:30 AM):
- 9:40-10:30 AM: batch_options_averaging - Options averaging in batches

MONITORING (10:30 AM - 3:00 PM):
- Every 10 min: check_futures_averaging - Check if futures need averaging

DAY CLOSE (3:22 - 3:30 PM):
- 3:22 PM: close_trading_day - Close positions with profit conditions

=============================================================================
SHARED SERVICES
=============================================================================

This module uses shared services to avoid code duplication:
- TradingContext: Unified context for account, config, position queries
- TradeConfirmationService: Telegram confirmation flow
- TradingCoreConfig: Position sizing, notification levels

Both Celery tasks and web views use the SAME APIs via these services.

=============================================================================
"""

import logging
from decimal import Decimal
from datetime import date, datetime, timedelta
from celery import shared_task
from django.utils import timezone

# Models
from apps.accounts.models import BrokerAccount
from apps.positions.models import Position

# Strategy entry functions
from apps.strategies.strategies.kotak_strangle import execute_kotak_strangle_entry
from apps.strategies.strategies.icici_futures import (
    screen_futures_opportunities
)

# Position services
from apps.positions.services.delta_monitor import monitor_delta
from apps.positions.services.averaging_manager import (
    get_averaging_recommendation
)
from apps.positions.services.exit_manager import should_exit_position

# Core utilities (shared with web app)
from apps.alerts.services.telegram_client import send_telegram_notification
from apps.alerts.services.notification_service import notify
from apps.core.utils.task_logger import TaskLogger
from apps.core.utils.decorators import task_enabled_guard
from apps.core.services.trading_context import get_trading_context

logger = logging.getLogger(__name__)


# =============================================================================
# KOTAK STRANGLE TASKS
# =============================================================================

@shared_task(name='apps.strategies.tasks.evaluate_kotak_strangle_entry')
def evaluate_kotak_strangle_entry():
    """
    Evaluate Kotak Strangle entry

    Scheduled: Monday & Tuesday @ 10:00 AM

    Workflow:
    1. Get Kotak account
    2. Check if entry is allowed (ONE POSITION RULE)
    3. Execute entry workflow
    4. Send notification with result
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Kotak Strangle Entry Evaluation")
    logger.info("=" * 80)

    try:
        # Get Kotak account
        kotak_account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()

        if not kotak_account:
            logger.error("❌ No active Kotak account found")
            return {'success': False, 'message': 'No active Kotak account'}

        logger.info(f"Account: {kotak_account.account_name}")

        # Execute entry workflow
        result = execute_kotak_strangle_entry(kotak_account)

        # Send notification
        if result['success']:
            notify('JOB_COMPLETED',
                title='Kotak Strangle Entry',
                instrument=f"Position #{result['position'].id}",
                metrics={
                    'Call Strike': str(result['details']['strikes']['call_strike']),
                    'Put Strike': str(result['details']['strikes']['put_strike']),
                    'Premium': f"₹{result['details']['premium_collected']:,.0f}",
                    'Margin': f"₹{result['details']['margin_used']:,.0f}",
                },
                collapsible=False,
            )
        else:
            notify('SYSTEM_STATUS',
                title='Kotak Strangle Entry Skipped',
                context=[result['message']],
                collapsible=False,
            )

        logger.info("=" * 80)
        return result

    except Exception as e:
        logger.error(f"Error in Kotak entry evaluation: {e}", exc_info=True)
        notify('TASK_ERROR',
            title='Kotak Entry Failed',
            context=[str(e)],
            task='evaluate_kotak_strangle_entry',
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.evaluate_kotak_strangle_exit')
def evaluate_kotak_strangle_exit(profit_threshold=10000, mandatory=False):
    """
    Evaluate Kotak Strangle exit

    Scheduled: Daily @ 3:15 PM (Mon-Fri)

    Exit Logic:
    - Exit if unrealized P&L >= profit_threshold (e.g., ₹10,000)
    - Exit if Friday (mandatory EOD exit before expiry)
    - Exit if stop-loss hit (checked separately every 30s)
    - Only runs if open positions exist

    Args:
        profit_threshold: Minimum profit required to trigger exit (default: ₹10,000)
        mandatory: If True, exit regardless of profit (Friday EOD)
    """
    logger.info("=" * 80)
    logger.info(f"CELERY TASK: Kotak Strangle Exit Evaluation")
    logger.info(f"Profit Threshold: ₹{profit_threshold:,.0f}, Mandatory: {mandatory}")
    logger.info("=" * 80)

    try:
        # Get Kotak account
        kotak_account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()

        if not kotak_account:
            logger.error("❌ No active Kotak account found")
            return {'success': False, 'message': 'No active Kotak account'}

        # Get active position
        position = Position.get_active_position(kotak_account)

        if not position:
            logger.info("ℹ️ No active position to evaluate for exit")
            return {'success': False, 'message': 'No active position'}

        logger.info(f"Evaluating position {position.id} for exit")
        logger.info(f"Current P&L: ₹{position.unrealized_pnl:,.0f}")

        # Check exit conditions
        current_time = timezone.now()
        should_exit, reason, exit_type = should_exit_position(position, current_time)

        # Check if Friday (mandatory exit)
        if current_time.weekday() == 4:  # Friday
            mandatory = True

        # NEW: Check profit threshold
        if position.unrealized_pnl >= Decimal(str(profit_threshold)):
            should_exit = True
            reason = f"Profit target reached: ₹{position.unrealized_pnl:,.0f} >= ₹{profit_threshold:,.0f}"
            logger.info(f"✅ Profit threshold reached: ₹{position.unrealized_pnl:,.0f}")

        if mandatory:
            # Friday - exit regardless
            should_exit = True
            reason = "Mandatory Friday EOD exit (before weekly expiry)"

        if should_exit:
            from apps.core.models import TradingCoreConfig
            config = TradingCoreConfig.get_instance()

            # Manual mode: send suggestion, do NOT auto-execute
            if config.requires_confirmation('EXIT'):
                from apps.trading.services.trade_confirmation import get_confirmation_service
                conf_service = get_confirmation_service()
                success, result = conf_service.request_exit_confirmation(
                    position, reason, current_pnl=position.unrealized_pnl
                )
                mode_label = config.get_notification_level_display_short()
                if success:
                    logger.info(f"Exit suggestion sent for pos #{position.id}: {reason}")
                    return {
                        'success': True,
                        'awaiting_confirmation': True,
                        'message': f'Exit suggestion sent ({mode_label}): {reason}',
                    }
                else:
                    notify('TASK_ERROR',
                        title='Exit Suggestion Failed',
                        instrument=position.instrument,
                        metrics={'P&L': f"₹{position.unrealized_pnl:,.0f}"},
                        context=[reason, 'Please review and close manually.'],
                        position_id=position.id,
                    )
                    return {'success': False, 'message': f'Suggestion send failed: {result}'}

            # Autonomous mode: auto-execute
            from apps.positions.services.position_manager import close_position

            success, message = close_position(
                position=position,
                exit_price=position.current_price,
                exit_reason=reason
            )

            if success:
                notify('TRADE_EXECUTED',
                    title='Position Closed',
                    instrument=position.instrument,
                    metrics={'P&L': f"₹{position.realized_pnl:,.0f}"},
                    context=[reason],
                    position_id=position.id,
                )
                return {'success': True, 'message': f'Position closed: {reason}'}
            else:
                notify('TASK_ERROR',
                    title='Position Close Failed',
                    instrument=position.instrument,
                    context=[message.splitlines()[0]],
                    position_id=position.id,
                )
                return {'success': False, 'message': message}
        else:
            logger.info(f"ℹ️ Exit conditions not met: {reason}")
            return {'success': False, 'message': f'Exit not required: {reason}'}

    except Exception as e:
        logger.error(f"Error in Kotak exit evaluation: {e}", exc_info=True)
        notify('TASK_ERROR',
            title='Kotak Exit Failed',
            context=[str(e)],
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.monitor_all_strangle_deltas')
def monitor_all_strangle_deltas(delta_threshold=300):
    """
    Monitor delta for all active strangle positions

    Scheduled: Every 15 minutes during market hours (configurable via UI)

    Checks delta for all strangles and sends alerts if |delta| > delta_threshold

    Args:
        delta_threshold: Alert if |Net Delta| exceeds this value (default: 300)
    """
    logger.info("CELERY TASK: Delta Monitoring for All Strangles")
    logger.info(f"Delta Threshold: {delta_threshold}")

    try:
        # Get all active strangle positions
        strangle_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type='WEEKLY_NIFTY_STRANGLE'
        )

        if not strangle_positions.exists():
            logger.info("ℹ️ No active strangle positions to monitor")
            return {'success': True, 'positions_monitored': 0}

        monitored_count = 0
        alerts_sent = 0

        for position in strangle_positions:
            try:
                delta_result = monitor_delta(position, delta_threshold=Decimal(str(delta_threshold)))

                if delta_result['delta_exceeded']:
                    alerts_sent += 1

                monitored_count += 1

            except Exception as e:
                logger.error(f"Error monitoring delta for position {position.id}: {e}")

        logger.info(f"✅ Monitored {monitored_count} positions, {alerts_sent} alerts sent")

        return {
            'success': True,
            'positions_monitored': monitored_count,
            'alerts_sent': alerts_sent
        }

    except Exception as e:
        logger.error(f"Error in delta monitoring: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


# =============================================================================
# STRATEGY EXECUTION TASKS - DAILY WORKFLOW
# =============================================================================

@shared_task(name='apps.strategies.tasks.setup_trading_day', bind=True)
@task_enabled_guard('setup-trading-day')
def setup_trading_day(self):
    """
    Setup Trading Day (8:55 AM Daily)

    Evaluates all data and determines if the day is tradable:
    1. Check data freshness (Trendlyne, news)
    2. Check if trading day (not holiday)
    3. Analyze overnight global markets
    4. Assess pre-market risk level
    5. Set initial tradability flag
    """
    task_logger = TaskLogger(
        task_name='setup_trading_day',
        task_category='strategies',
        task_id=self.request.id
    )

    task_logger.start("Setting up trading day - evaluating pre-market conditions")

    try:
        from apps.strategies.models import TradingDaySetup, SGXNiftyData
        from apps.data.models import TLStockData, NewsArticle

        today = date.today()

        # Get or create today's setup record
        setup, created = TradingDaySetup.objects.get_or_create(
            trading_date=today,
            defaults={'is_trading_day': True}
        )

        task_logger.step('data_check', "Checking data freshness")

        # Check Trendlyne data freshness (updated today)
        trendlyne_count = TLStockData.objects.filter(
            updated_at__date=today
        ).count()
        setup.trendlyne_data_fresh = trendlyne_count > 100

        # Check news data freshness
        news_count = NewsArticle.objects.filter(
            created_at__date=today
        ).count()
        setup.news_data_fresh = news_count > 0

        task_logger.step('calendar_check', "Checking trading calendar")

        # Check if weekend
        if today.weekday() >= 5:
            setup.is_trading_day = False
            setup.setup_tradable = False
            setup.setup_reason = "Weekend - market closed"
            setup.save()

            task_logger.success("Setup complete - Weekend, no trading", context={
                'is_trading_day': False
            })
            return {'success': True, 'tradable': False, 'reason': 'Weekend'}

        # TODO: Check NSE holiday calendar
        # For now, assume weekdays are trading days

        task_logger.step('global_markets', "Analyzing overnight global markets")

        # Get SGX Nifty data if available
        try:
            sgx_data = SGXNiftyData.objects.filter(trading_date=today).first()
            if sgx_data:
                setup.sgx_nifty_change = sgx_data.sgx_change_percent
        except Exception:
            pass

        # Assess overnight risk based on global changes
        # TODO: Fetch actual US market data
        overnight_risk = 'MEDIUM'
        if setup.sgx_nifty_change:
            if abs(setup.sgx_nifty_change) > 2:
                overnight_risk = 'HIGH'
            elif abs(setup.sgx_nifty_change) > 3:
                overnight_risk = 'EXTREME'
            elif abs(setup.sgx_nifty_change) < 0.5:
                overnight_risk = 'LOW'

        setup.overnight_risk_level = overnight_risk

        # Check broker connection
        # Primary: count active accounts in DB (existing logic)
        # Secondary: read live health-check result stored by health_check_brokers at 06:45
        try:
            from apps.accounts.models import BrokerAccount
            active_accounts = BrokerAccount.objects.filter(is_active=True).count()
            setup.broker_connection_ok = active_accounts > 0
        except Exception:
            setup.broker_connection_ok = False

        # Enrich with live API health check result (if task ran at 06:45)
        from django.core.cache import cache
        from apps.core.tasks import BROKER_HEALTH_KEY
        broker_health = cache.get(BROKER_HEALTH_KEY)
        broker_health_failures = []
        if broker_health:
            for broker_name, status in broker_health.items():
                if status not in ('OK', 'NO_ACCOUNT') and not status.startswith('OK'):
                    broker_health_failures.append(f"{broker_name}: {status}")
            if broker_health_failures:
                setup.broker_connection_ok = False
                setup.setup_reason = (
                    "Broker API health check failed: "
                    + "; ".join(broker_health_failures)
                )
        else:
            # Health check task did not run — log but don't block trading
            logger.warning(
                "setup_trading_day: broker_health not in cache — "
                "health-check-brokers task may not have run at 06:45"
            )

        task_logger.step('decision', "Making setup tradability decision")

        # Make setup decision
        if not setup.is_trading_day:
            setup.setup_tradable = False
            setup.setup_reason = "Not a trading day"
        elif overnight_risk == 'EXTREME':
            setup.setup_tradable = False
            setup.setup_reason = f"Extreme overnight risk: SGX change {setup.sgx_nifty_change}%"
        elif not setup.broker_connection_ok:
            setup.setup_tradable = False
            setup.setup_reason = "No active broker accounts"
        else:
            setup.setup_tradable = True
            setup.setup_reason = f"Day cleared for trading (Risk: {overnight_risk})"

        setup.setup_completed_at = timezone.now()
        setup.save()

        # Send notification
        if setup.setup_tradable:
            notify('SYSTEM_STATUS',
                title='Trading Day Setup',
                metrics={
                    'Risk Level': overnight_risk,
                    'SGX Change': f"{setup.sgx_nifty_change or 'N/A'}%",
                },
                context=['Day cleared for trading. Waiting for market open validation at 9:15 AM.'],
                collapsible=False,
            )
        else:
            notify('SYSTEM_STATUS',
                title='No Trading Today',
                context=[setup.setup_reason],
                collapsible=False,
            )

        task_logger.success("Trading day setup completed", context={
            'tradable': setup.setup_tradable,
            'risk_level': overnight_risk,
            'reason': setup.setup_reason
        })

        return {
            'success': True,
            'tradable': setup.setup_tradable,
            'risk_level': overnight_risk,
            'reason': setup.setup_reason
        }

    except Exception as e:
        task_logger.failure("Error in setup_trading_day", error=e)
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.strategies.tasks.start_trading_day', bind=True)
@task_enabled_guard('start-trading-day')
def start_trading_day(self):
    """
    Start Trading Day (9:15 AM Daily)

    Validates market opening conditions:
    1. Check market opening price and gap
    2. Validate VIX levels
    3. Check for major news impact
    4. Assess 52-week high proximity
    5. Final tradability decision
    """
    task_logger = TaskLogger(
        task_name='start_trading_day',
        task_category='strategies',
        task_id=self.request.id
    )

    task_logger.start("Starting trading day - validating market opening")

    try:
        from apps.strategies.models import TradingDaySetup
        from apps.data.models import NewsArticle

        today = date.today()

        # Get today's setup (must exist from setup_trading_day)
        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
        except TradingDaySetup.DoesNotExist:
            task_logger.error('no_setup', "No setup record found for today")
            return {'success': False, 'error': 'Setup not completed'}

        # If setup already determined no trading, skip
        if not setup.setup_tradable:
            task_logger.info('skipped', f"Skipping - setup already decided no trading: {setup.setup_reason}")
            return {'success': True, 'tradable': False, 'reason': setup.setup_reason}

        task_logger.step('market_data', "Fetching market opening data")

        # TODO: Fetch actual market data from broker
        # For now, use placeholder logic
        try:
            from apps.data.models import ContractStockData
            nifty_data = ContractStockData.objects.filter(nse_code='NIFTY').first()
            if nifty_data:
                setup.nifty_open = nifty_data.close_price  # Placeholder
                setup.nifty_prev_close = nifty_data.close_price
        except Exception:
            pass

        # Calculate gap if we have data
        if setup.nifty_open and setup.nifty_prev_close:
            setup.gap_percent = ((setup.nifty_open - setup.nifty_prev_close) / setup.nifty_prev_close) * 100

        task_logger.step('vix_check', "Checking VIX levels")

        # TODO: Fetch actual VIX
        # Placeholder VIX logic
        setup.vix_open = Decimal('18.5')  # Placeholder
        if setup.vix_open:
            if setup.vix_open < 15:
                setup.vix_level = 'LOW'
            elif setup.vix_open < 20:
                setup.vix_level = 'NORMAL'
            elif setup.vix_open < 25:
                setup.vix_level = 'ELEVATED'
            else:
                setup.vix_level = 'HIGH'

        task_logger.step('52w_check', "Checking 52-week high proximity")

        # TODO: Fetch actual 52-week high
        # Placeholder logic
        setup.nifty_52w_high = Decimal('26000')  # Placeholder
        if setup.nifty_open and setup.nifty_52w_high:
            setup.distance_from_52w_high_pct = ((setup.nifty_52w_high - setup.nifty_open) / setup.nifty_52w_high) * 100
            setup.near_52w_high = setup.distance_from_52w_high_pct < 2

        task_logger.step('news_check', "Checking for major news impact")

        # Check recent news sentiment
        recent_news = NewsArticle.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=12)
        ).values_list('sentiment_label', flat=True)

        if recent_news:
            negative_count = sum(1 for s in recent_news if s in ['NEGATIVE', 'VERY_NEGATIVE'])
            positive_count = sum(1 for s in recent_news if s in ['POSITIVE', 'VERY_POSITIVE'])
            total = len(recent_news)

            if negative_count > total * 0.6:
                setup.news_sentiment = 'NEGATIVE'
                setup.major_news_detected = True
            elif positive_count > total * 0.6:
                setup.news_sentiment = 'POSITIVE'
            else:
                setup.news_sentiment = 'NEUTRAL'

        task_logger.step('decision', "Making final tradability decision")

        # Make final decision
        reasons = []

        # Check gap
        if setup.gap_percent and abs(setup.gap_percent) > 1.5:
            reasons.append(f"Large gap: {setup.gap_percent:.2f}%")

        # Check VIX
        if setup.vix_level == 'HIGH':
            reasons.append(f"High VIX: {setup.vix_open}")

        # Check news
        if setup.major_news_detected and setup.news_sentiment == 'NEGATIVE':
            reasons.append("Major negative news detected")

        # Final decision
        if len(reasons) >= 2:
            setup.start_tradable = False
            setup.start_reason = "Multiple risk factors: " + ", ".join(reasons)
            setup.is_tradable = False
            setup.tradable_reason = setup.start_reason
            setup.recommended_strategy = 'NONE'
        elif len(reasons) == 1:
            setup.start_tradable = True
            setup.start_reason = f"Proceed with caution: {reasons[0]}"
            setup.is_tradable = True
            setup.tradable_reason = setup.start_reason
            setup.futures_trading_allowed = True
            setup.options_strangle_allowed = True
            setup.recommended_strategy = 'ALL'
        else:
            setup.start_tradable = True
            setup.start_reason = "All conditions favorable"
            setup.is_tradable = True
            setup.tradable_reason = "Day cleared for trading"
            setup.futures_trading_allowed = True
            setup.options_strangle_allowed = True
            setup.options_iron_condor_allowed = True
            setup.recommended_strategy = 'ALL'

        # Adjust strategy based on VIX and 52w high
        if setup.is_tradable:
            if setup.vix_level in ['ELEVATED', 'HIGH'] or setup.near_52w_high:
                setup.options_iron_condor_allowed = True
                setup.recommended_strategy = 'IRON_CONDOR'

        setup.start_validated_at = timezone.now()
        setup.save()

        # Send notification
        if setup.is_tradable:
            strategy_lines = [
                f"Recommended: {setup.get_recommended_strategy_display()}",
                f"Futures: {'Enabled' if setup.futures_trading_allowed else 'Disabled'}",
                f"Strangle: {'Enabled' if setup.options_strangle_allowed else 'Disabled'}",
                f"Iron Condor: {'Enabled' if setup.options_iron_condor_allowed else 'Disabled'}",
            ]
            metrics = {
                'VIX': f"{setup.vix_open} ({setup.vix_level})",
                'Near 52W High': 'Yes' if setup.near_52w_high else 'No',
            }
            if setup.gap_percent:
                metrics['Gap'] = f"{setup.gap_percent:.2f}%"
            notify('SYSTEM_STATUS',
                title='Trading Day Started',
                metrics=metrics,
                context=strategy_lines,
                collapsible=False,
            )
        else:
            notify('RISK_WARNING',
                title='Trading Paused',
                context=[setup.start_reason, 'Will re-evaluate conditions.'],
            )

        task_logger.success("Trading day validation completed", context={
            'tradable': setup.is_tradable,
            'strategy': setup.recommended_strategy,
            'reason': setup.start_reason
        })

        return {
            'success': True,
            'tradable': setup.is_tradable,
            'strategy': setup.recommended_strategy,
            'reason': setup.start_reason
        }

    except Exception as e:
        task_logger.failure("Error in start_trading_day", error=e)
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.strategies.tasks.evaluate_options_strategy', bind=True)
@task_enabled_guard('evaluate-options-strategy')
def evaluate_options_strategy(self):
    """
    Evaluate Options Strategy (9:30 AM Daily)

    Decides between strangle and iron condor based on:
    1. VIX levels (high VIX = iron condor preferred)
    2. 52-week high proximity (near = iron condor)
    3. First 15 min movement (high movement = wait)
    4. Previous day's close
    """
    task_logger = TaskLogger(
        task_name='evaluate_options_strategy',
        task_category='strategies',
        task_id=self.request.id
    )

    task_logger.start("Evaluating options strategy - strangle vs iron condor")

    try:
        from apps.strategies.models import TradingDaySetup
        from apps.core.models import TradingCoreConfig

        today = date.today()
        config = TradingCoreConfig.get_instance()

        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
        except TradingDaySetup.DoesNotExist:
            task_logger.error('no_setup', "No setup record found")
            return {'success': False, 'error': 'Setup not found'}

        if not setup.is_tradable:
            task_logger.info('skipped', "Day not tradable, skipping options evaluation")
            return {'success': True, 'skipped': True, 'reason': setup.tradable_reason}

        # ── Opening volatility soft gate ──────────────────────────────────────
        # monitor_opening_volatility (09:00–09:20) writes this flag.
        # If False → market opened wild; mark strategy as WAIT so
        # start_options_trade (09:40) does not enter. We do NOT auto-reschedule:
        # conditions may change and the trader is already notified.
        from django.core.cache import cache
        from apps.core.tasks import MARKET_STABLE_KEY, MARKET_VIX_KEY, MARKET_GAP_KEY
        market_stable = cache.get(MARKET_STABLE_KEY)  # None = task didn't run
        if market_stable is False:
            vix_now = cache.get(MARKET_VIX_KEY, 'N/A')
            gap_now = cache.get(MARKET_GAP_KEY, 'N/A')
            task_logger.info(
                'market_unstable',
                f"Opening volatility gate triggered (VIX={vix_now}, gap={gap_now}%). "
                f"Setting strategy=WAIT."
            )
            setup.options_strategy_evaluated = True
            setup.options_evaluated_at = timezone.now()
            setup.options_strategy_selected = 'WAIT'
            setup.save()
            notify('SYSTEM_STATUS',
                title='Options Evaluation Deferred',
                metrics={'VIX': str(vix_now), 'Gap': f"{gap_now}%"},
                context=['Strategy set to WAIT — no options entry at 09:40.'],
            )
            return {
                'success': True,
                'deferred': True,
                'reason': 'market_unstable_at_open',
                'vix': vix_now,
                'gap_pct': gap_now,
            }

        task_logger.step('movement_check', "Checking first 15 minute movement")

        # TODO: Calculate actual 9:15 to 9:30 movement
        # Placeholder logic
        first_15_min_movement = Decimal('0.3')  # Placeholder

        # If market moved >0.5% in first 15 min, market is volatile
        is_volatile = abs(first_15_min_movement) > Decimal('0.5')

        task_logger.step('strategy_decision', "Deciding options strategy")

        selected_strategy = 'STRANGLE'
        strategy_reason = []

        # VIX-based decision
        if setup.vix_level in ['ELEVATED', 'HIGH']:
            selected_strategy = 'IRON_CONDOR'
            strategy_reason.append(f"High VIX ({setup.vix_open})")

        # 52-week high proximity
        if setup.near_52w_high:
            selected_strategy = 'IRON_CONDOR'
            strategy_reason.append("Near 52-week high")

        # Volatility check
        if is_volatile:
            selected_strategy = 'WAIT'
            strategy_reason.append(f"High initial movement ({first_15_min_movement}%)")

        # Update setup
        setup.options_strategy_evaluated = True
        setup.options_evaluated_at = timezone.now()
        setup.options_strategy_selected = selected_strategy
        setup.save()

        # Send notification
        if selected_strategy == 'WAIT':
            notify('SYSTEM_STATUS',
                title='Options Strategy: Wait',
                context=[
                    f"Reason: {', '.join(strategy_reason)}",
                    'Will re-evaluate at 9:40 AM.',
                ],
                collapsible=False,
            )
        else:
            if config.requires_confirmation('ENTRY'):
                next_step = 'Position will be presented for your verification at 9:40 AM.'
            else:
                next_step = 'Trade will execute automatically at 9:40 AM.'

            notify('SYSTEM_STATUS',
                title='Options Strategy Selected',
                metrics={
                    'Strategy': selected_strategy,
                    'VIX': f"{setup.vix_open} ({setup.vix_level})",
                    'Mode': config.get_notification_level_display_short(),
                },
                context=[next_step],
                collapsible=False,
            )

        task_logger.success("Options strategy evaluation completed", context={
            'strategy': selected_strategy,
            'reason': strategy_reason
        })

        return {
            'success': True,
            'strategy': selected_strategy,
            'reason': strategy_reason
        }

    except Exception as e:
        task_logger.failure("Error in evaluate_options_strategy", error=e)
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.strategies.tasks.start_options_trade', bind=True)
@task_enabled_guard('start-options-trade')
def start_options_trade(self):
    """
    Start Options Trade (9:40 AM Daily)

    Implements the selected options strategy with Telegram confirmation:
    1. Get strategy from TradingCoreConfig (or TradingDaySetup)
    2. Check movement threshold
    3. Generate trade suggestion
    4. Send for Telegram confirmation (if enabled)
    5. OR auto-execute (if confirmation disabled)
    """
    task_logger = TaskLogger(
        task_name='start_options_trade',
        task_category='strategies',
        task_id=self.request.id
    )

    task_logger.start("Starting options trade implementation")

    try:
        from apps.strategies.models import TradingDaySetup
        from apps.core.models import TradingCoreConfig
        from apps.trading.services.trade_confirmation import get_confirmation_service

        today = date.today()

        # Get core config
        config = TradingCoreConfig.get_instance()

        # Check if options trading is enabled
        if not config.is_options_enabled():
            task_logger.info('skipped', "Options trading disabled in Core Config")
            notify('SYSTEM_STATUS',
                title='Options Trade Skipped',
                context=['Trading disabled in Core Config'],
                collapsible=False,
            )
            return {'success': True, 'skipped': True, 'reason': 'Options trading disabled'}

        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
        except TradingDaySetup.DoesNotExist:
            return {'success': False, 'error': 'Setup not found'}

        if not setup.is_tradable:
            return {'success': True, 'skipped': True, 'reason': 'Day not tradable'}

        # ====================================================================
        # STEP 1: Check movement threshold
        # ====================================================================
        current_movement = _calculate_movement_since_open()

        if abs(current_movement) > float(config.movement_threshold):
            notify('RISK_WARNING',
                title='Options Entry Skipped',
                metrics={
                    'Movement': f"{current_movement:.2f}%",
                    'Threshold': f"{config.movement_threshold}%",
                },
                context=['Market too volatile for safe entry.'],
            )
            task_logger.info('movement_exceeded', f"Movement {current_movement:.2f}% exceeds threshold")
            return {'success': False, 'reason': 'movement_exceeded', 'movement': current_movement}

        # ====================================================================
        # STEP 2: Determine strategy
        # ====================================================================
        # Use TradingCoreConfig strategy if set to specific value
        # Otherwise fall back to TradingDaySetup evaluated strategy
        if config.options_strategy == 'AUTO':
            # Use auto-selected strategy from config or setup
            strategy = config.get_auto_strategy()
            if not strategy or strategy == 'WAIT':
                strategy = setup.options_strategy_selected if setup.options_strategy_evaluated else None
        else:
            strategy = config.options_strategy

        if not strategy or strategy == 'WAIT':
            task_logger.info('waiting', "Strategy is WAIT or not determined")
            return {'success': True, 'skipped': True, 'reason': 'Waiting for better conditions'}

        task_logger.step('strategy', f"Using strategy: {strategy}")

        # ====================================================================
        # STEP 3: Get account and generate suggestion
        # ====================================================================
        account = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()
        if not account:
            return {'success': False, 'error': 'No active Kotak account'}

        # ── Pre-trade validation ─────────────────────────────────────────────
        from apps.trading.services.pre_trade_validator import PreTradeValidator
        from apps.core.constants import (
            STRATEGY_KOTAK_STRANGLE,
            STRATEGY_KOTAK_BROKEN_IRON_CONDOR,
        )
        strategy_type_map = {
            'STRANGLE': STRATEGY_KOTAK_STRANGLE,
            'SHORT_STRANGLE': STRATEGY_KOTAK_STRANGLE,
            'BROKEN_IRON_CONDOR': STRATEGY_KOTAK_BROKEN_IRON_CONDOR,
            'IRON_CONDOR': STRATEGY_KOTAK_BROKEN_IRON_CONDOR,
        }
        validator = PreTradeValidator()
        is_ok, reasons = validator.validate(
            account,
            strategy_type=strategy_type_map.get(strategy, strategy),
        )
        if not is_ok:
            task_logger.warning('pre_trade_blocked', f"Pre-trade validation failed: {reasons}")
            notify('RISK_WARNING',
                title='Options Trade Blocked',
                instrument=strategy,
                context=reasons,
                actions=['No order placed.'],
            )
            return {'success': False, 'blocked_by': reasons}
        # ────────────────────────────────────────────────────────────────────

        # Call existing entry functions which generate suggestions
        # These functions return a dict with 'suggestion' if successful
        if strategy == 'STRANGLE' or strategy == 'SHORT_STRANGLE':
            # Use existing strangle entry function
            result = execute_kotak_strangle_entry(account)

            if not result.get('success'):
                error_msg = result.get('message', result.get('error', 'Strangle entry failed'))
                task_logger.warning('strangle_failed', error_msg)
                return {'success': False, 'error': error_msg}

            suggestion = result.get('suggestion')
            if not suggestion:
                return {'success': False, 'error': 'No suggestion returned from strangle entry'}

        elif strategy == 'BROKEN_IRON_CONDOR' or strategy == 'IRON_CONDOR':
            from apps.strategies.strategies.kotak_broken_iron_condor import execute_kotak_broken_iron_condor_entry

            result = execute_kotak_broken_iron_condor_entry(account)

            if not result.get('success'):
                error_msg = result.get('message', result.get('error', 'Iron condor entry failed'))
                task_logger.warning('iron_condor_failed', error_msg)
                return {'success': False, 'error': error_msg}

            suggestion = result.get('suggestion')
            if not suggestion:
                return {'success': False, 'error': 'No suggestion returned from iron condor entry'}

        else:
            return {'success': False, 'error': f'Unknown strategy: {strategy}'}

        # ====================================================================
        # STEP 4: Calculate position size based on sizing mode
        # ====================================================================
        if config.is_simulated():
            # Simulated mode - paper trade
            lots = config.get_lots_for_trade('OPTIONS')
            task_logger.info('simulated', f"SIMULATED MODE: Would trade {lots} lots (no real orders)")
            suggestion.recommended_lots = lots
            suggestion.algorithm_reasoning = f"[SIMULATED] VIX: {setup.vix_open}, Movement: {current_movement:.2f}%"
            suggestion.status = 'SIMULATED'
            suggestion.save()

            notify('SYSTEM_STATUS',
                title='Simulated Options Trade',
                metrics={
                    'Strategy': strategy,
                    'Lots': str(lots),
                    'Movement': f"{current_movement:.2f}%",
                },
                context=['Paper trade mode - no real orders placed.'],
                collapsible=False,
            )
            return {'success': True, 'simulated': True, 'lots': lots, 'strategy': strategy}

        elif config.is_auto_sizing():
            # Auto mode - calculate from broker margin
            from apps.trading.services.margin_service import get_available_margin, get_margin_per_lot
            try:
                available_margin = get_available_margin()
                margin_per_lot = get_margin_per_lot('OPTIONS', strategy)
                lots = config.get_lots_for_trade('OPTIONS', available_margin, margin_per_lot)
                task_logger.info('auto_sizing', f"Auto calculated lots: {lots} (margin: {available_margin}, per_lot: {margin_per_lot})")
            except Exception as e:
                task_logger.warning('margin_error', f"Error getting margin, defaulting to 1 lot: {e}")
                lots = 1
        else:
            # Manual or Test mode
            lots = config.get_lots_for_trade('OPTIONS')

        # Update suggestion with config values
        suggestion.recommended_lots = lots
        suggestion.algorithm_reasoning = f"VIX: {setup.vix_open}, Movement: {current_movement:.2f}%, Mode: {config.position_sizing_mode}"
        suggestion.status = 'PENDING_CONFIRMATION' if config.requires_confirmation('ENTRY') else 'APPROVED'
        suggestion.save()

        # ====================================================================
        # STEP 5: Send for confirmation OR auto-execute
        # ====================================================================
        if config.requires_confirmation('ENTRY'):
            # Send confirmation request to Telegram
            confirmation_service = get_confirmation_service()
            success, result = confirmation_service.request_options_confirmation(suggestion, config)

            if success:
                task_logger.success("Options confirmation request sent", context={
                    'suggestion_id': suggestion.id,
                    'strategy': strategy,
                    'message_id': result
                })
                return {
                    'success': True,
                    'awaiting_confirmation': True,
                    'suggestion_id': suggestion.id,
                    'strategy': strategy
                }
            else:
                task_logger.warning('telegram_failed', f"Failed to send Telegram: {result}")
                # Manual mode: Telegram failed — do NOT fall through to auto-execute.
                # The suggestion is pending but undelivered; abort and alert.
                notify('TASK_ERROR',
                    title='Confirmation Request Failed',
                    instrument=strategy,
                    context=[
                        'Telegram delivery failed. Trade NOT executed.',
                        'Please trigger manually if desired.',
                    ],
                )
                return {
                    'success': False,
                    'awaiting_confirmation': False,
                    'message': f'Telegram confirmation failed — trade aborted in manual mode.',
                }

        # Auto-execute (AUTONOMOUS mode only — confirmation not required)
        mode_label = config.get_notification_level_display_short()
        task_logger.step('execute', f"Auto-executing {strategy} strategy ({mode_label})")

        confirmation_service = get_confirmation_service()
        result = confirmation_service.execute_options_trade(suggestion, lots)

        # Update setup
        setup.options_trade_started = result.get('success', False)
        setup.options_trade_started_at = timezone.now()
        setup.save()

        if result.get('success'):
            notify('TRADE_EXECUTED',
                title='Options Trade Executed',
                metrics={
                    'Strategy': strategy,
                    'Lots': str(lots),
                    'Sizing': config.get_position_sizing_display_short(),
                },
                context=['Averaging will continue until 10:30 AM.'],
            )
        else:
            notify('TASK_ERROR',
                title='Options Trade Failed',
                instrument=strategy,
                context=[result.get('error', 'Unknown error')],
            )

        task_logger.success("Options trade completed", context=result)
        return result

    except Exception as e:
        task_logger.failure("Error in start_options_trade", error=e)
        return {'success': False, 'error': str(e)}


def _calculate_movement_since_open() -> float:
    """
    Calculate NIFTY % movement from 9:15 open to current.

    Returns:
        float: Movement percentage (positive or negative)
    """
    try:
        from apps.data.models import ContractStockData

        nifty = ContractStockData.objects.filter(symbol='NIFTY').first()
        if not nifty:
            return 0.0

        day_open = float(nifty.day_open) if nifty.day_open else 0
        current = float(nifty.close_price) if nifty.close_price else 0

        if day_open <= 0:
            return 0.0

        movement = ((current - day_open) / day_open) * 100
        return movement

    except Exception:
        return 0.0


@shared_task(name='apps.strategies.tasks.batch_options_averaging', bind=True)
@task_enabled_guard(['batch-options-averaging', 'batch-options-averaging-10am'])
def batch_options_averaging(self):
    """
    Batch Options Averaging (9:40 AM - 10:15 AM, every 5 minutes)

    Executes averaging for options positions:
    1. Check if within averaging window
    2. Evaluate if averaging needed
    3. Execute averaging if conditions met
    """
    task_logger = TaskLogger(
        task_name='batch_options_averaging',
        task_category='strategies',
        task_id=self.request.id
    )

    task_logger.start("Batch options averaging check")

    try:
        from apps.strategies.models import TradingDaySetup

        today = date.today()
        now = timezone.now()

        # Check if within averaging window (9:40 - 10:15)
        averaging_start = now.replace(hour=9, minute=40, second=0, microsecond=0)
        averaging_end = now.replace(hour=10, minute=15, second=0, microsecond=0)

        if not (averaging_start <= now <= averaging_end):
            task_logger.info('outside_window', "Outside averaging window")
            return {'success': True, 'skipped': True, 'reason': 'Outside averaging window'}

        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
        except TradingDaySetup.DoesNotExist:
            return {'success': False, 'error': 'Setup not found'}

        if not setup.options_trade_started:
            return {'success': True, 'skipped': True, 'reason': 'No options trade started'}

        task_logger.step('check_positions', "Checking positions for averaging")

        # Get core config for confirmation settings
        from apps.core.models import TradingCoreConfig
        config = TradingCoreConfig.get_instance()

        # Get active options positions
        options_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type__in=['WEEKLY_NIFTY_STRANGLE', 'IRON_CONDOR']
        )

        averaged_count = 0
        skipped_count = 0

        for position in options_positions:
            # Check if averaging needed
            recommendation = get_averaging_recommendation(position, position.current_price)

            if recommendation.get('should_average'):
                # Determine lots based on sizing mode
                if config.is_simulated():
                    task_logger.info('simulated_averaging', f"SIMULATED: Would average position {position.id}")
                    averaged_count += 1
                    continue

                lots = config.get_lots_for_trade('OPTIONS')

                # Check if confirmation required
                if config.requires_confirmation('AVERAGING'):
                    # Send confirmation request
                    from apps.trading.services.trade_confirmation import get_confirmation_service
                    confirmation_service = get_confirmation_service()
                    success, result = confirmation_service.request_averaging_confirmation(position, lots)
                    if success:
                        task_logger.info('averaging_confirmation', f"Confirmation sent for position {position.id}")
                    else:
                        task_logger.warning('averaging_confirm_failed', f"Failed to send confirmation: {result}")
                    skipped_count += 1
                else:
                    # Auto-execute averaging (SUPERVISED with AVERAGING or AUTONOMOUS mode)
                    from apps.trading.services.trade_confirmation import get_confirmation_service
                    confirmation_service = get_confirmation_service()
                    result = confirmation_service.execute_averaging(position, lots)
                    if result.get('success'):
                        task_logger.info('averaging_executed', f"Averaging executed for position {position.id}")
                        averaged_count += 1
                    else:
                        task_logger.warning('averaging_failed', f"Averaging failed: {result.get('error')}")

        # Check if averaging window complete
        if now >= averaging_end:
            setup.averaging_completed = True
            setup.averaging_completed_at = timezone.now()
            setup.save()

        task_logger.success("Batch averaging completed", context={
            'positions_checked': options_positions.count(),
            'averaged': averaged_count,
            'awaiting_confirmation': skipped_count,
            'mode': config.notification_level
        })

        return {
            'success': True,
            'positions_checked': options_positions.count(),
            'averaged': averaged_count,
            'awaiting_confirmation': skipped_count,
            'simulated': config.is_simulated()
        }

    except Exception as e:
        task_logger.failure("Error in batch_options_averaging", error=e)
        return {'success': False, 'error': str(e)}


def _save_screening_as_trade_suggestions(top_candidates, today):
    """
    Create TradeSuggestion records from screening results so they appear at
    /trading/triggers/#futures.

    The screening task uses FuturesSuggestion, but the web UI reads TradeSuggestion.
    This helper bridges the gap by creating lightweight TradeSuggestion records
    with the data available from screening (no full algo details — those come later
    from execute_futures_algorithm at 9:40 AM which deduplicates by symbol+expiry).
    """
    try:
        from django.contrib.auth import get_user_model
        from apps.data.models import ContractData
        from apps.trading.models import TradeSuggestion

        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            logger.warning("No superuser found — skipping TradeSuggestion creation from screening")
            return

        # Pre-fetch nearest future expiry for all symbols in one query
        symbol_list = [c['symbol'] for c in top_candidates]
        contracts = (
            ContractData.objects
            .filter(symbol__in=symbol_list, option_type='FUTURE', expiry__gte=str(today))
            .order_by('symbol', 'expiry')
            .values('symbol', 'expiry', 'price', 'lot_size')
        )
        # Keep only nearest expiry per symbol
        nearest = {}
        for row in contracts:
            sym = row['symbol']
            if sym not in nearest:
                nearest[sym] = row

        # Existing TradeSuggestion records for today (dedup by instrument+expiry_date)
        existing = set(
            TradeSuggestion.objects.filter(
                created_at__date=today,
                suggestion_type='FUTURES',
                strategy='icici_futures',
            ).values_list('instrument', 'expiry_date')
        )

        saved = 0
        for candidate in top_candidates:
            symbol = candidate['symbol']
            contract = nearest.get(symbol)
            if not contract:
                logger.debug(f"No ContractData found for {symbol} — skipping TradeSuggestion")
                continue

            try:
                from datetime import datetime as _dt
                expiry_date = _dt.strptime(contract['expiry'], '%Y-%m-%d').date()
            except Exception:
                continue

            if (symbol, expiry_date) in existing:
                logger.debug(f"TradeSuggestion already exists for {symbol} {expiry_date} — skipping")
                continue

            oi_data = candidate.get('oi_analysis', {})
            tech_data = candidate.get('technical_analysis', {})
            sector_data = candidate.get('sector_analysis', {})

            # Normalize direction to LONG/SHORT
            raw_dir = candidate.get('direction', 'NEUTRAL')
            direction = 'LONG' if raw_dir == 'BULLISH' else ('SHORT' if raw_dir == 'BEARISH' else raw_dir)

            algorithm_reasoning = {
                'composite_score': candidate['composite_score'],
                'source': 'screening',
                'oi_analysis': oi_data,
                'technical_analysis': tech_data,
                'sector_analysis': sector_data,
                'metrics': {
                    'futures_price': float(contract.get('price') or 0),
                    'lot_size': contract.get('lot_size') or 0,
                    'volume_rank': candidate.get('volume_rank', 0),
                    'oi_buildup_type': oi_data.get('buildup_type', ''),
                    'oi_change_pct': oi_data.get('oi_change_pct'),
                },
                'scores': {
                    'oi': oi_data.get('score', 0),
                    'technical': tech_data.get('score', 0),
                    'sector': sector_data.get('score', 0),
                },
                'explanation': [
                    f"OI: {oi_data.get('buildup_type', 'N/A')} (change: {oi_data.get('oi_change_pct', 'N/A')}%)",
                    f"Technical: {tech_data.get('verdict', 'N/A')}",
                    f"Sector: {sector_data.get('verdict', 'N/A')}",
                ],
                'execution_log': [f"Screened at 9:30 AM — score {candidate['composite_score']}/100"],
            }

            TradeSuggestion.objects.create(
                user=user,
                source='auto',
                strategy='icici_futures',
                suggestion_type='FUTURES',
                instrument=symbol,
                direction=direction,
                spot_price=contract.get('price'),
                expiry_date=expiry_date,
                days_to_expiry=(expiry_date - today).days,
                status='SUGGESTED',
                algorithm_reasoning=algorithm_reasoning,
                position_details={'lot_size': contract.get('lot_size') or 0},
            )
            existing.add((symbol, expiry_date))
            saved += 1
            logger.info(f"Created TradeSuggestion for {symbol} ({direction}) from screening")

        logger.info(f"Screening → TradeSuggestion: saved {saved}/{len(top_candidates)}")

    except Exception as e:
        logger.warning(f"Could not create TradeSuggestion from screening results: {e}")


@shared_task(name='apps.strategies.tasks.screen_futures_opportunities')
@task_enabled_guard('screen-futures-opportunities')
def screen_futures_opportunities_task():
    """
    Screen Futures Opportunities (9:30 AM Daily)

    Runs 15 min after market open (9:15 AM) for price stability.
    Screens top 30 futures by volume and saves top 5 suggestions:
    1. Get top 30 futures by volume
    2. Analyze OI buildup, technical, sector
    3. Score and rank candidates
    4. Save top 5 to FuturesSuggestion + TradeSuggestion (for web UI at /trading/triggers/#futures)
    5. Send Telegram notification
    """
    # Idempotency guard: prevent Beat double-fire on same day
    from django.core.cache import cache as _cache
    from django.utils import timezone as _tz
    _idem_key = f'strategy_run_screen_futures_{_tz.localdate()}'
    if not _cache.add(_idem_key, '1', timeout=3600):
        logger.info("screen_futures_opportunities: already ran today — skipping duplicate")
        return {'success': True, 'skipped': True, 'reason': 'idempotency_guard'}

    logger.info("=" * 80)
    logger.info("CELERY TASK: Futures Opportunity Screening")
    logger.info("=" * 80)

    try:
        from apps.strategies.models import TradingDaySetup, FuturesSuggestion

        today = date.today()

        # Check if day is tradable
        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
            if not setup.futures_trading_allowed:
                logger.info("Futures trading not allowed today")
                return {'success': True, 'skipped': True, 'reason': 'Futures not allowed'}
        except TradingDaySetup.DoesNotExist:
            pass  # Continue anyway for manual runs

        # Screen for opportunities (top 30 by volume)
        candidates = screen_futures_opportunities(
            min_volume_rank=30,  # Top 30 by volume
            min_score=60
        )

        if not candidates:
            logger.info("ℹ️ No qualified candidates found")
            return {'success': True, 'candidates_found': 0}

        # Save top 5 to database
        top_5 = candidates[:5]

        # Clear previous suggestions for today
        FuturesSuggestion.objects.filter(trading_date=today).delete()

        for i, candidate in enumerate(top_5, 1):
            FuturesSuggestion.objects.create(
                trading_date=today,
                rank=i,
                symbol=candidate['symbol'],
                stock_name=candidate.get('stock_name', ''),
                direction=candidate['direction'],
                volume_rank=candidate.get('volume_rank', 0),
                volume_vs_avg=candidate.get('volume_vs_avg'),
                composite_score=candidate['composite_score'],
                oi_score=candidate.get('oi_analysis', {}).get('score'),
                technical_score=candidate.get('technical_analysis', {}).get('score'),
                sector_score=candidate.get('sector_analysis', {}).get('score'),
                oi_buildup_type=candidate.get('oi_analysis', {}).get('buildup_type', ''),
                oi_change_pct=candidate.get('oi_analysis', {}).get('oi_change_pct'),
                suggested_entry_price=candidate.get('entry_price'),
                suggested_stop_loss=candidate.get('stop_loss'),
                suggested_target=candidate.get('target'),
            )

        # Update setup
        try:
            setup.futures_screened = True
            setup.futures_screened_at = timezone.now()
            setup.futures_suggestions = [c['symbol'] for c in top_5]
            setup.save()
        except Exception:
            pass

        # ===== ALSO SAVE AS TradeSuggestion FOR WEB UI =====
        # The /trading/triggers/#futures page reads TradeSuggestion, not FuturesSuggestion.
        # Look up the nearest ContractData expiry per symbol and create lightweight records.
        _save_screening_as_trade_suggestions(top_5, today)

        # Send notification
        candidate_lines = []
        for i, candidate in enumerate(top_5, 1):
            candidate_lines.append(
                f"{i}. {candidate['symbol']} ({candidate['direction']}) — "
                f"Score: {candidate['composite_score']}/100, "
                f"OI: {candidate.get('oi_analysis', {}).get('buildup_type', 'N/A')}"
            )

        notify('JOB_COMPLETED',
            title='Futures Screening',
            metrics={'Candidates': str(len(candidates))},
            context=candidate_lines,
            collapsible=True,
        )

        logger.info(f"✅ Found {len(candidates)} candidates, saved top 5")

        return {
            'success': True,
            'candidates_found': len(candidates),
            'top_5': [c['symbol'] for c in top_5]
        }

    except Exception as e:
        logger.error(f"Error in futures screening: {e}", exc_info=True)
        notify('TASK_ERROR',
            title='Futures Screening Failed',
            context=[str(e)],
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.close_trading_day', bind=True)
@task_enabled_guard('close-trading-day')
def close_trading_day(self):
    """
    Close Trading Day (3:25 PM Daily)

    Closes option positions with conditions:
    1. Only close if in profit and profit >= 5000
    2. Close in batches every 20 seconds for 2 minutes
    3. Force close at 3:28 PM regardless of profit
    4. Only applies to Nifty option positions
    """
    task_logger = TaskLogger(
        task_name='close_trading_day',
        task_category='strategies',
        task_id=self.request.id
    )

    task_logger.start("Closing trading day - processing option positions")

    try:
        from apps.strategies.models import TradingDaySetup
        from apps.positions.services.position_manager import close_position
        import time

        today = date.today()
        now = timezone.now()

        # Get setup record
        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
        except TradingDaySetup.DoesNotExist:
            setup = None

        # Get core config for confirmation settings
        from apps.core.models import TradingCoreConfig
        config = TradingCoreConfig.get_instance()

        task_logger.step('get_positions', "Getting open option positions")

        # Get active Nifty option positions
        option_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type__in=['WEEKLY_NIFTY_STRANGLE', 'IRON_CONDOR'],
            instrument__contains='NIFTY'
        )

        if not option_positions.exists():
            task_logger.info('no_positions', "No open option positions to close")

            if setup:
                setup.day_closed = True
                setup.day_closed_at = timezone.now()
                setup.close_summary = {'positions_closed': 0, 'reason': 'No positions'}
                setup.save()

            return {'success': True, 'positions_closed': 0, 'reason': 'No positions'}

        # Check for simulated mode
        if config.is_simulated():
            total_pnl = sum(p.unrealized_pnl or Decimal('0') for p in option_positions)
            task_logger.info('simulated', f"SIMULATED: Would close {option_positions.count()} positions, P&L: {total_pnl}")
            notify('SYSTEM_STATUS',
                title='Simulated Day Close',
                metrics={
                    'Positions': str(option_positions.count()),
                    'Hypothetical P&L': f"₹{total_pnl:,.0f}",
                },
                context=['Paper trade mode - no real closes.'],
                collapsible=False,
            )
            return {'success': True, 'simulated': True, 'positions': option_positions.count()}

        mode_label = config.get_notification_level_display_short()
        task_logger.step('close_positions', f"Processing {option_positions.count()} positions ({mode_label})")

        MIN_PROFIT = Decimal('5000')
        close_results = {
            'total': option_positions.count(),
            'closed': 0,
            'skipped': 0,
            'forced': 0,
            'total_pnl': Decimal('0'),
            'details': []
        }

        # Force close time: 3:28 PM
        force_close_time = now.replace(hour=15, minute=28, second=0, microsecond=0)

        batch_count = 0
        max_batches = 6  # 6 batches x 20 seconds = 2 minutes

        for position in option_positions:
            current_time = timezone.now()

            # Calculate position P&L
            position_pnl = position.unrealized_pnl or Decimal('0')

            # Check if force close time reached
            is_force_close = current_time >= force_close_time

            # Decide whether to close
            close_reason = ""

            if is_force_close:
                close_reason = "EOD"   # maps to ⏰ END OF DAY EXIT in the suggestion message
                close_results['forced'] += 1
            elif position_pnl >= MIN_PROFIT:
                close_reason = f"Profit target met: ₹{position_pnl:,.0f}"
            else:
                close_results['skipped'] += 1
                close_results['details'].append({
                    'position_id': position.id,
                    'symbol': position.instrument,
                    'pnl': float(position_pnl),
                    'action': 'skipped',
                    'reason': f'Profit ₹{position_pnl:,.0f} < ₹{MIN_PROFIT:,.0f}'
                })
                continue

            # Close the position - always check confirmation in manual mode,
            # even for force close (3:28 PM deadline — user gets an urgent suggestion).
            task_logger.info('closing', f"Closing position {position.id}: {close_reason}")

            if config.requires_confirmation('EXIT'):
                # Send confirmation request
                from apps.trading.services.trade_confirmation import get_confirmation_service
                confirmation_service = get_confirmation_service()
                success, result = confirmation_service.request_exit_confirmation(position, close_reason)
                if success:
                    task_logger.info('exit_confirmation', f"Exit confirmation sent for position {position.id}")
                close_results['details'].append({
                    'position_id': position.id,
                    'symbol': position.instrument,
                    'pnl': float(position_pnl),
                    'action': 'pending_confirmation',
                    'reason': close_reason
                })
                continue  # Don't close yet - wait for confirmation

            try:
                success, msg = close_position(
                    position=position,
                    exit_price=position.current_price,
                    exit_reason=close_reason
                )

                if success:
                    close_results['closed'] += 1
                    close_results['total_pnl'] += position.realized_pnl or Decimal('0')
                    close_results['details'].append({
                        'position_id': position.id,
                        'symbol': position.instrument,
                        'pnl': float(position.realized_pnl or 0),
                        'action': 'closed',
                        'reason': close_reason
                    })

            except Exception as e:
                task_logger.warning('close_error', f"Error closing position {position.id}: {e}")
                close_results['details'].append({
                    'position_id': position.id,
                    'symbol': position.instrument,
                    'action': 'error',
                    'reason': str(e)
                })

            # Batch delay (20 seconds between closes)
            batch_count += 1
            if batch_count < max_batches and not is_force_close:
                time.sleep(20)  # Wait 20 seconds before next close

        # Update setup
        if setup:
            setup.day_closed = True
            setup.day_closed_at = timezone.now()
            setup.close_summary = {
                'total': close_results['total'],
                'closed': close_results['closed'],
                'skipped': close_results['skipped'],
                'forced': close_results['forced'],
                'total_pnl': float(close_results['total_pnl'])
            }
            setup.save()

        # Send notification
        pending_count = len([d for d in close_results['details'] if d.get('action') == 'pending_confirmation'])
        close_metrics = {
            'Closed': str(close_results['closed']),
            'Skipped': str(close_results['skipped']),
            'P&L': f"₹{close_results['total_pnl']:,.0f}",
        }
        if pending_count > 0:
            close_metrics['Pending'] = str(pending_count)
        notify('JOB_COMPLETED',
            title='Trading Day Closed',
            status='SUCCESS' if close_results['total_pnl'] >= 0 else 'WARNING',
            metrics=close_metrics,
            collapsible=False,
        )

        task_logger.success("Trading day close completed", context={
            'closed': close_results['closed'],
            'total_pnl': float(close_results['total_pnl'])
        })

        return {'success': True, **close_results}

    except Exception as e:
        task_logger.failure("Error in close_trading_day", error=e)
        notify('TASK_ERROR',
            title='Close Trading Day Failed',
            context=[str(e)],
        )
        return {'success': False, 'error': str(e)}


# =============================================================================
# FUTURES AVERAGING TASK
# =============================================================================

@shared_task(name='apps.strategies.tasks.check_futures_averaging')
@task_enabled_guard('check-futures-averaging')
def check_futures_averaging():
    """
    Check if active futures positions need averaging.

    SCHEDULE: Every 10 minutes during market hours (9:00 AM - 3:00 PM)

    WORKFLOW:
    1. Create TradingContext (shared with web app)
    2. Skip if simulated mode (paper trading)
    3. Get all active futures positions
    4. For each position, check if averaging needed (1% loss trigger)
    5. Based on notification level:
       - FULL_CONTROL/SUPERVISED: Send Telegram confirmation request
       - AUTONOMOUS: Auto-execute averaging immediately

    USES SHARED SERVICES:
    - TradingContext: Config access, position queries
    - TradeConfirmationService: Telegram confirmation flow
    - get_averaging_recommendation: Position averaging logic
    """
    logger.info("CELERY TASK: Futures Averaging Check")

    # -------------------------------------------------------------------------
    # STEP 1: Create unified trading context (same API as web app)
    # -------------------------------------------------------------------------
    ctx = get_trading_context(task_name='check_futures_averaging')

    try:
        # -------------------------------------------------------------------------
        # STEP 2: Check simulated mode (paper trading - no real orders)
        # -------------------------------------------------------------------------
        if ctx.is_simulated():
            positions = ctx.get_active_futures_positions()
            logger.info(f"📝 SIMULATED: Would check {positions.count()} positions for averaging")
            return ctx.success_result(simulated=True, positions=positions.count())

        # -------------------------------------------------------------------------
        # STEP 3: Get active futures positions
        # -------------------------------------------------------------------------
        futures_positions = ctx.get_active_futures_positions()

        if not futures_positions.exists():
            logger.info("ℹ️ No active futures positions to check")
            return ctx.success_result(positions_checked=0)

        # -------------------------------------------------------------------------
        # STEP 4: Process each position for averaging
        # -------------------------------------------------------------------------
        mode_label = ctx.config.get_notification_level_display_short()
        checked_count = 0
        averaging_recommendations = 0
        auto_executed = 0

        for position in futures_positions:
            try:
                # Check if averaging needed using shared service
                recommendation = get_averaging_recommendation(position, position.current_price)

                if recommendation['should_average']:
                    preview = recommendation['preview']
                    lots = ctx.get_lots_for_trade('FUTURES')  # Uses TradingContext helper

                    # ---------------------------------------------------------
                    # STEP 5: Handle based on notification level
                    # ---------------------------------------------------------
                    if ctx.requires_confirmation('AVERAGING'):
                        # FULL_CONTROL or SUPERVISED: Send confirmation request
                        from apps.trading.services.trade_confirmation import get_confirmation_service
                        confirmation_service = get_confirmation_service()
                        success, result = confirmation_service.request_averaging_confirmation(
                            position, lots, preview
                        )

                        if success:
                            averaging_recommendations += 1
                        else:
                            # Fallback to simple notification
                            notify('SYSTEM_STATUS',
                                title='Averaging Recommendation',
                                instrument=position.instrument,
                                task='check_futures_averaging',
                                metrics={
                                    'Loss': f"{recommendation['details']['loss_pct']:.2f}%",
                                    'Current': f"₹{preview['averaging_price']:,.2f}",
                                },
                                position={
                                    'Direction': position.direction,
                                    'Entry': f"₹{preview['current_entry']:,.2f}",
                                    'Add': f"{preview['quantity_to_add']} qty",
                                    'New Avg': f"₹{preview['new_average_entry']:,.2f}",
                                },
                                context=['Confirmation required'],
                                position_id=position.id,
                            )
                            averaging_recommendations += 1
                    else:
                        # AUTONOMOUS mode: Auto-execute averaging
                        from apps.trading.services.trade_confirmation import get_confirmation_service
                        confirmation_service = get_confirmation_service()
                        result = confirmation_service.execute_averaging(position, lots)

                        if result.get('success'):
                            auto_executed += 1
                            notify('TRADE_EXECUTED',
                                title='Auto-Averaged',
                                instrument=position.instrument,
                                task='check_futures_averaging',
                                metrics={
                                    'Added': f"{lots} lots",
                                    'New Avg': f"₹{result.get('new_avg', 0):,.2f}",
                                },
                                position_id=position.id,
                                collapsible=False,
                            )
                        else:
                            logger.warning(f"Auto-averaging failed for {position.id}: {result.get('error')}")

                checked_count += 1

            except Exception as e:
                logger.error(f"Error checking averaging for position {position.id}: {e}")

        logger.info(
            f"✅ Checked {checked_count} positions, "
            f"{averaging_recommendations} recommendations, {auto_executed} auto-executed"
        )

        return ctx.success_result(
            positions_checked=checked_count,
            averaging_recommendations=averaging_recommendations,
            auto_executed=auto_executed,
            mode=ctx.config.notification_level
        )

    except Exception as e:
        logger.error(f"Error in averaging check: {e}", exc_info=True)
        return ctx.error_result(str(e))


# =============================================================================
# FUTURES ALGORITHM SCHEDULED TASK (PARALLELIZED)
# =============================================================================

@shared_task(
    name='apps.strategies.tasks.analyze_futures_batch',
    bind=True,
    soft_time_limit=540,  # 9 minutes soft limit (return partial results)
    time_limit=720,       # 12 minutes hard limit (3 min grace for graceful shutdown)
)
def analyze_futures_batch(self, contract_ids, min_score=65, regime='NORMAL'):
    """
    Analyze a batch of futures contracts (subtask for parallel execution).

    Args:
        contract_ids: List of ContractData IDs to analyze
        min_score: Minimum score for qualification
        regime: Market regime (TRENDING, RANGING, VOLATILE, BREAKOUT, NORMAL)

    Returns:
        dict: {
            'passed_summary': list of {symbol, expiry, score, direction, recommendation},
            'passed_full': list of full result dicts for saving,
            'errors': list of {symbol, error},
            'batch_size': int,
            'timed_out': bool (True if soft limit was hit)
        }
    """
    import time
    from celery.exceptions import SoftTimeLimitExceeded
    from apps.data.models import ContractData
    from apps.trading.futures_analyzer import enhanced_futures_analysis
    from apps.trading.services.analysis_service import build_suggestion_result

    passed_summary = []
    passed_full = []
    errors = []
    timed_out = False

    contracts = ContractData.objects.filter(id__in=contract_ids)
    analyzed_count = 0
    batch_start = time.time()
    MAX_BATCH_SECONDS = 480  # Stop starting new contracts after 8 min (leaves buffer for soft/hard limits)

    try:
        for contract in contracts:
            # Proactive time check: don't start a new contract if we're running low
            elapsed = time.time() - batch_start
            if elapsed > MAX_BATCH_SECONDS:
                timed_out = True
                logger.warning(
                    f"analyze_futures_batch proactive stop after {elapsed:.0f}s - "
                    f"{analyzed_count}/{len(contract_ids)} contracts done. Skipping remaining."
                )
                break

            try:
                contract_start = time.time()
                analysis_result = enhanced_futures_analysis(
                    stock_symbol=contract.symbol,
                    expiry_date=contract.expiry,
                    contract=contract,
                    regime=regime,
                )
                contract_elapsed = time.time() - contract_start
                logger.info(f"Analyzed {contract.symbol} in {contract_elapsed:.1f}s")

                composite_score = analysis_result.get('composite_score', 0)
                verdict = analysis_result.get('verdict', 'FAIL')
                direction = analysis_result.get('direction', 'NEUTRAL')
                hard_reject = analysis_result.get('hard_reject', False)

                if verdict == 'PASS':
                    # Post-score validation gate
                    validation = None
                    try:
                        from apps.strategies.services.trade_validation import TradeValidationLayer
                        validator = TradeValidationLayer()
                        validation = validator.validate(analysis_result, regime=regime)
                        if not validation['passed']:
                            logger.info(
                                f"Validation gate rejected {contract.symbol}: "
                                f"{validation.get('rejection_reason', 'unknown')}"
                            )
                    except Exception as val_err:
                        logger.warning(f"Validation gate error for {contract.symbol}: {val_err}")

                    # Build summary for notification
                    adjusted_score = validation['adjusted_score'] if validation else composite_score
                    rr_ratio = validation.get('rr_ratio', 0) if validation else 0
                    summary = {
                        'symbol': contract.symbol,
                        'expiry': str(contract.expiry),
                        'score': adjusted_score,
                        'verdict': verdict,
                        'direction': direction,
                        'hard_reject': hard_reject,
                        'reject_reason': analysis_result.get('reject_reason'),
                        'news_warning': analysis_result.get('news_warning'),
                        'recommendation': analysis_result.get('recommendation', 'N/A'),
                        'qualified': (
                            adjusted_score >= min_score
                            and not hard_reject
                            and (validation['passed'] if validation else True)
                        ),
                        'rr_ratio': rr_ratio,
                        'regime': regime,
                        'validation_warnings': validation.get('warnings', []) if validation else [],
                    }
                    passed_summary.append(summary)

                    # Build full result dict using shared function (eliminates duplication)
                    full_result = build_suggestion_result(contract, analysis_result)
                    passed_full.append(full_result)

                analyzed_count += 1

            except SoftTimeLimitExceeded:
                # Re-raise to outer handler — return partial results
                raise
            except Exception as e:
                logger.error(f"Error analyzing {contract.symbol}: {e}")
                errors.append({'symbol': contract.symbol, 'error': str(e)})
                analyzed_count += 1

    except SoftTimeLimitExceeded:
        # Soft time limit hit — return partial results instead of crashing
        timed_out = True
        logger.warning(
            f"analyze_futures_batch hit soft time limit after {analyzed_count}/{len(contract_ids)} contracts. "
            f"Returning partial results."
        )

    return {
        'passed_summary': passed_summary,
        'passed_full': passed_full,
        'errors': errors,
        'batch_size': len(contract_ids),
        'analyzed_count': analyzed_count,
        'timed_out': timed_out
    }


@shared_task(name='apps.strategies.tasks.aggregate_futures_results', bind=True)
def aggregate_futures_results(self, batch_results, min_score=65, orchestrator_task_id=None, regime='NORMAL'):
    """
    Aggregate results from parallel futures analysis batches (chord callback).

    Args:
        batch_results: List of results from analyze_futures_batch subtasks
        min_score: Minimum score for qualification (for notification)
        orchestrator_task_id: Original task ID for logging

    Returns:
        dict: Final aggregated result
    """
    from apps.trading.services.suggestion_service import save_futures_suggestions

    task_logger = TaskLogger(
        task_name='aggregate_futures_results',
        task_category='strategy',
        task_id=self.request.id
    )

    task_logger.start("Aggregating batch results", context={
        'batch_count': len(batch_results),
        'orchestrator_task_id': orchestrator_task_id
    })

    # Merge all batch results
    all_passed_summary = []
    all_passed_full = []
    all_errors = []
    total_analyzed = 0
    timed_out_batches = 0
    partial_contracts = 0

    for batch in batch_results:
        if batch:  # Handle potential None from failed subtasks
            all_passed_summary.extend(batch.get('passed_summary', []))
            all_passed_full.extend(batch.get('passed_full', []))
            all_errors.extend(batch.get('errors', []))
            total_analyzed += batch.get('analyzed_count', batch.get('batch_size', 0))

            # Track timed-out batches
            if batch.get('timed_out', False):
                timed_out_batches += 1
                partial_contracts += batch.get('batch_size', 0) - batch.get('analyzed_count', 0)

    task_logger.info('merged', f"Merged {len(batch_results)} batches", context={
        'total_analyzed': total_analyzed,
        'passed': len(all_passed_summary),
        'errors': len(all_errors),
        'timed_out_batches': timed_out_batches,
        'partial_contracts': partial_contracts
    })

    # Save all PASS candidates to database
    saved_count = 0
    if all_passed_full:
        task_logger.step('save_suggestions', f"Saving {len(all_passed_full)} PASS suggestions")
        try:
            # Convert expiry_date strings back to date objects
            for result in all_passed_full:
                if isinstance(result.get('expiry_date'), str):
                    from datetime import datetime as dt
                    result['expiry_date'] = dt.strptime(result['expiry_date'], '%Y-%m-%d').date()

            suggestion_ids = save_futures_suggestions(all_passed_full, source='auto')
            saved_count = len([s for s in suggestion_ids if s])
            task_logger.info('saved', f"Saved {saved_count} suggestions to database")
        except Exception as e:
            logger.error(f"Error saving suggestions: {e}")
            task_logger.warning('save_failed', f"Failed to save suggestions: {e}")

    # Get qualified candidates (score >= min_score, not hard rejected)
    qualified_candidates = [s for s in all_passed_summary if s.get('qualified', False)]
    qualified_candidates.sort(key=lambda x: x['score'], reverse=True)

    # Check TradingCoreConfig for confirmation settings
    from apps.core.models import TradingCoreConfig
    from apps.trading.models import TradeSuggestion

    config = TradingCoreConfig.get_instance()
    today = date.today()

    # Check for simulated mode - no real order confirmations
    if config.is_simulated():
        task_logger.info('simulated', f"SIMULATED MODE: {len(qualified_candidates)} qualified candidates (no real orders)")
        sim_context = []
        for i, candidate in enumerate(qualified_candidates[:5], 1):
            sim_context.append(
                f"{i}. {candidate['symbol']} ({candidate['direction']}) — Score: {candidate['score']}/100"
            )
        sim_context.append('Paper trade mode - no real orders')
        notify('SYSTEM_STATUS',
            title='Simulated Futures Results',
            metrics={
                'Analyzed': str(total_analyzed),
                'Passed': str(len(all_passed_summary)),
                'Qualified': str(len(qualified_candidates)),
                'Simulated Lots': str(config.simulated_futures_lots),
            },
            context=sim_context,
            collapsible=True,
        )

        task_logger.success("Simulated aggregation completed", context={
            'total_analyzed': total_analyzed, 'qualified': len(qualified_candidates)
        })
        return {
            'success': True, 'simulated': True,
            'candidates_found': total_analyzed, 'qualified': len(qualified_candidates)
        }

    # Send Telegram notification and optionally confirmation request
    task_logger.step('notify', "Processing results and sending notification")

    if qualified_candidates and config.requires_confirmation('ENTRY'):
        # Get TOP 3 for confirmation flow
        top_3_candidates = qualified_candidates[:3]

        # Find corresponding TradeSuggestion records
        top_3_suggestions = []
        for candidate in top_3_candidates:
            try:
                suggestion = TradeSuggestion.objects.filter(
                    instrument=candidate['symbol'],
                    created_at__date=today,
                    suggestion_type='FUTURES'
                ).order_by('-created_at').first()

                if suggestion:
                    # Update status to pending confirmation
                    suggestion.status = 'PENDING_CONFIRMATION'
                    suggestion.save()
                    top_3_suggestions.append(suggestion)
            except Exception as e:
                logger.warning(f"Could not find suggestion for {candidate['symbol']}: {e}")

        if top_3_suggestions:
            # Send confirmation request with buttons
            from apps.trading.services.trade_confirmation import get_confirmation_service
            confirmation_service = get_confirmation_service()

            success, result = confirmation_service.request_futures_confirmation(top_3_suggestions)

            if success:
                task_logger.info('confirmation_sent', f"Futures confirmation sent for {len(top_3_suggestions)} candidates")
            else:
                task_logger.warning('confirmation_failed', f"Failed to send confirmation: {result}")
                # Fall back to regular notification
                _send_futures_summary_notification(
                    today, total_analyzed, all_passed_summary, qualified_candidates,
                    all_errors, timed_out_batches, partial_contracts, min_score
                )
        else:
            # No suggestions found, send regular notification
            _send_futures_summary_notification(
                today, total_analyzed, all_passed_summary, qualified_candidates,
                all_errors, timed_out_batches, partial_contracts, min_score
            )

    elif qualified_candidates:
        # SUPERVISED or AUTONOMOUS mode - send notification (no confirmation required)
        sizing_label = config.get_position_sizing_display_short()

        qual_context = []
        if timed_out_batches > 0:
            qual_context.append(f"{timed_out_batches} batch(es) timed out ({partial_contracts} contracts skipped)")

        for i, candidate in enumerate(qualified_candidates[:5], 1):
            rr = candidate.get('rr_ratio', 0)
            rr_str = f" | R:R 1:{rr:.1f}" if rr > 0 else ""
            qual_context.append(
                f"{i}. {candidate['symbol']} ({candidate['direction']}) — "
                f"Score: {candidate['score']}/100{rr_str} | {candidate['recommendation']}"
            )

        if len(qualified_candidates) > 5:
            qual_context.append(f"... and {len(qualified_candidates) - 5} more")

        if config.is_autonomous():
            qual_context.append('Autonomous mode - no confirmation needed')
        else:
            qual_context.append('Ready for manual verification')

        notify('JOB_COMPLETED',
            title='Futures Algorithm',
            metrics={
                'Analyzed': str(total_analyzed),
                'Passed': str(len(all_passed_summary)),
                'Qualified': str(len(qualified_candidates)),
                'Regime': regime,
                'Sizing': sizing_label,
            },
            context=qual_context,
            collapsible=True,
        )
    else:
        # No qualified candidates - show top 3 highest-scoring stocks
        all_passed_sorted = sorted(all_passed_summary, key=lambda x: x['score'], reverse=True)
        top_3 = all_passed_sorted[:3]

        no_qual_context = [f'No candidates above threshold (score >= {min_score})']

        if timed_out_batches > 0:
            no_qual_context.append(f"{timed_out_batches} batch(es) timed out ({partial_contracts} contracts skipped)")

        if top_3:
            no_qual_context.append('Top 3 by score:')
            for i, candidate in enumerate(top_3, 1):
                no_qual_context.append(
                    f"{i}. {candidate['symbol']} ({candidate['direction']}) — Score: {candidate['score']}/100"
                )
            no_qual_context.append('Consider manual review if scores are close to threshold')

        notify('SYSTEM_STATUS',
            title='Futures Algorithm',
            metrics={
                'Analyzed': str(total_analyzed),
                'Passed': str(len(all_passed_summary)),
                'Errors': str(len(all_errors)),
            },
            context=no_qual_context,
            collapsible=True,
        )

    task_logger.success("Aggregation completed", context={
        'total_analyzed': total_analyzed,
        'passed': len(all_passed_summary),
        'qualified': len(qualified_candidates),
        'saved': saved_count,
        'timed_out_batches': timed_out_batches,
        'partial_contracts': partial_contracts
    })

    return {
        'success': True,
        'candidates_found': total_analyzed,
        'passed': len(all_passed_summary),
        'qualified': len(qualified_candidates),
        'saved': saved_count,
        'errors': len(all_errors),
        'timed_out_batches': timed_out_batches,
        'partial_contracts': partial_contracts,
        'qualified_candidates': qualified_candidates[:5]
    }


def _send_futures_summary_notification(
    today, total_analyzed, all_passed_summary, qualified_candidates,
    all_errors, timed_out_batches, partial_contracts, min_score
):
    """
    Send summary notification for futures algorithm results.

    Called when confirmation flow fails or as fallback.
    """
    fallback_context = []

    if timed_out_batches > 0:
        fallback_context.append(f"{timed_out_batches} batch(es) timed out ({partial_contracts} contracts skipped)")

    for i, candidate in enumerate(qualified_candidates[:5], 1):
        fallback_context.append(
            f"{i}. {candidate['symbol']} ({candidate['direction']}) — "
            f"Score: {candidate['score']}/100 | {candidate['recommendation']}"
        )

    if len(qualified_candidates) > 5:
        fallback_context.append(f"... and {len(qualified_candidates) - 5} more")

    fallback_context.append('Ready for manual verification')

    notify('JOB_COMPLETED',
        title='Futures Algorithm Results',
        metrics={
            'Analyzed': str(total_analyzed),
            'Passed': str(len(all_passed_summary)),
            'Qualified': str(len(qualified_candidates)),
        },
        context=fallback_context,
    )


@shared_task(name='apps.strategies.tasks.execute_futures_algorithm', bind=True)
@task_enabled_guard('execute-futures-algorithm')
def execute_futures_algorithm(self, this_month_volume=1000, next_month_volume=800, min_score=65, top_contracts=50, batch_size=2, _manual_trigger=False):
    """
    Screen Futures Opportunities - Scheduled Daily @ 9:40 AM (Parallelized)

    This is the main futures trading algorithm. It screens high-volume futures contracts,
    scores them using a 12-component analysis framework, and presents TOP 3 candidates
    to the user via Telegram for confirmation.

    ==========================================================================
    SCHEDULE: 9:40 AM IST (after market stabilizes post-open)
    ==========================================================================

    WORKFLOW:
    1. PRE-CHECKS: Validate trading day (not holiday/weekend), check Core Config
    2. SCREENING: Get top 50 futures contracts by trading volume
    3. PARALLEL ANALYSIS: Split into batches, analyze concurrently using Celery chord
    4. SCORING: 12-component analysis (OI, DMA, technical, sector, etc.)
    5. FILTERING: Qualify contracts with score >= 65 (configurable)
    6. CALLBACK: Aggregate results, save to DB, send Telegram notification
    7. CONFIRMATION: Present TOP 3 to user with Approve/Reject buttons
    8. EXECUTION: On user confirmation, execute trade with batching

    12-COMPONENT SCORING SYSTEM:
    - Open Interest Buildup & Change
    - DMA Position (20/50/200) & Crossovers
    - Volume Pattern & Liquidity
    - RSI, MACD, Bollinger Bands
    - Sector Strength
    - Basis Premium & Cost of Carry
    - Support/Resistance Levels

    NOTIFICATION LEVELS (from TradingCoreConfig):
    - FULL_CONTROL: Sends TOP 3 for confirmation, waits for user
    - SUPERVISED: Same as FULL_CONTROL (entries require confirmation)
    - AUTONOMOUS: Auto-executes top candidate (no confirmation)
    - SIMULATED: Paper trade only, no real orders

    POSITION SIZING (from TradingCoreConfig):
    - TEST: 1 lot each
    - MANUAL: Fixed lots from config
    - AUTO: Calculated from broker margin
    - SIMULATED: Hypothetical large positions

    Args:
        this_month_volume: Min volume for current month contracts (default: 1000)
        next_month_volume: Min volume for next month contracts (default: 800)
        min_score: Minimum composite score to qualify (default: 65)
        top_contracts: Number of top contracts to analyze (default: 50)
        batch_size: Contracts per parallel task (default: 3)

    Returns:
        dict: Chord dispatch info with batch_count and total_contracts

    RELATED TASKS:
    - analyze_futures_batch: Subtask for parallel contract analysis
    - aggregate_futures_results: Callback that handles scoring and notification
    """
    from celery import chord
    from apps.core.models import CeleryTaskState

    task_logger = TaskLogger(
        task_name='execute_futures_algorithm',
        task_category='strategy',
        task_id=self.request.id
    )

    # Idempotency guard: prevent Beat double-fire on same day (manual trigger bypasses)
    if not _manual_trigger:
        from django.core.cache import cache as _cache
        _idem_key = f'strategy_run_execute_futures_{date.today()}'
        if not _cache.add(_idem_key, '1', timeout=3600):
            task_logger.info('skipped', "Already ran today — idempotency guard")
            return {'success': True, 'skipped': True, 'reason': 'idempotency_guard'}

    # Load task_params from CeleryTaskState if available
    try:
        task_state = CeleryTaskState.objects.filter(task_key='execute-futures-algorithm').first()
        if task_state and task_state.task_params:
            params = task_state.task_params
            top_contracts = params.get('top_contracts', top_contracts)
            batch_size = params.get('batch_size', batch_size)
            this_month_volume = params.get('this_month_volume', this_month_volume)
            next_month_volume = params.get('next_month_volume', next_month_volume)
            min_score = params.get('min_score', min_score)
            task_logger.info('params_loaded', "Loaded task_params from CeleryTaskState", context=params)
    except Exception as e:
        logger.warning(f"Could not load task_params: {e}")

    task_logger.start("Starting Futures Algorithm (parallel)", context={
        'this_month_volume': this_month_volume,
        'next_month_volume': next_month_volume,
        'min_score': min_score,
        'top_contracts': top_contracts,
        'batch_size': batch_size
    })

    try:
        from apps.data.models import ContractData
        from apps.core.models import NseFlag

        # ===== STEP 1: Check trading day validity =====
        today = date.today()

        if _manual_trigger:
            task_logger.info('manual_trigger', "Manual trigger - skipping trading day/config checks")
        else:
            task_logger.step('check_trading_day', "Checking if trading is allowed today")

            # Check NSE holiday flag (key-value store)
            if NseFlag.get_bool('is_holiday', default=False):
                task_logger.info('skipped', "Today is a market holiday", context={'date': str(today)})
                return {'success': True, 'skipped': True, 'reason': 'Market holiday'}

            # Check day of week (skip weekends)
            if today.weekday() >= 5:  # Saturday=5, Sunday=6
                task_logger.info('skipped', "Weekend - markets closed", context={'day': today.strftime('%A')})
                return {'success': True, 'skipped': True, 'reason': 'Weekend'}

            # Check time of day — prevent execution outside trading window
            # Wider than strict market hours (9:15-15:30) since task is scheduled at 9:40 AM
            from apps.core.utils.date_utils import IST
            from datetime import time as dt_time
            now_ist = datetime.now(IST)
            if not (dt_time(8, 0) <= now_ist.time() <= dt_time(16, 0)):
                task_logger.info('skipped', f"Outside trading window (8 AM - 4 PM IST), current: {now_ist.strftime('%H:%M')}")
                return {'success': True, 'skipped': True, 'reason': 'Outside trading hours'}

            # Check if futures trading is enabled in core config
            from apps.core.models import TradingCoreConfig
            core_config = TradingCoreConfig.get_instance()
            if not core_config.is_futures_enabled():
                task_logger.info('skipped', "Futures trading disabled in Core Config")
                notify('SYSTEM_STATUS',
                    title='Futures Algorithm Skipped',
                    context=['Trading disabled in Core Config'],
                    collapsible=False,
                )
                return {'success': True, 'skipped': True, 'reason': 'Futures trading disabled'}

        # ===== STEP 2: Get ICICI account =====
        task_logger.step('get_account', "Getting active ICICI futures account")

        icici_account = BrokerAccount.objects.filter(
            broker='ICICI',
            is_active=True
        ).first()

        if not icici_account:
            task_logger.warning('no_account', "No active ICICI account found")
            notify('RISK_WARNING',
                title='Futures Algorithm',
                context=['No active ICICI account found. Please configure account.'],
            )
            return {'success': False, 'error': 'No active ICICI account'}

        task_logger.info('account_found', f"Using account: {icici_account.account_name}")

        # ===== PRE-TRADE VALIDATION =====
        if not _manual_trigger:
            from apps.trading.services.pre_trade_validator import PreTradeValidator
            from apps.core.constants import STRATEGY_KOTAK_BROKEN_IRON_CONDOR
            validator = PreTradeValidator()
            is_ok, reasons = validator.validate(
                icici_account,
                strategy_type='LLM_VALIDATED_FUTURES',
            )
            if not is_ok:
                task_logger.warning('pre_trade_blocked', f"Pre-trade validation failed: {reasons}")
                notify('RISK_WARNING',
                    title='Futures Trade Blocked',
                    context=reasons,
                    actions=['No order placed.'],
                )
                return {'success': False, 'blocked_by': reasons}

        # ===== STEP 2b: Detect market regime =====
        task_logger.step('regime', "Detecting market regime")
        try:
            from apps.strategies.services.market_regime import get_market_regime
            regime_data = get_market_regime('NIFTY')
            regime = regime_data.get('regime', 'NORMAL')
            task_logger.info('regime_detected', f"Market regime: {regime}", context=regime_data)
        except Exception as regime_err:
            logger.warning(f"Regime detection failed, using NORMAL: {regime_err}")
            regime = 'NORMAL'
            regime_data = {'regime': 'NORMAL', 'confidence': 0}

        # ===== STEP 3: Get filtered contracts =====
        task_logger.step('get_contracts', f"Screening top {top_contracts} futures contracts by volume")

        # Use model manager for standardized query
        futures_contracts = ContractData.objects.get_tradable_futures(
            this_month_volume=this_month_volume,
            next_month_volume=next_month_volume,
            limit=top_contracts
        )

        # Get contract IDs for subtasks
        contract_ids = list(futures_contracts.values_list('id', flat=True))
        pre_filter_count = len(contract_ids)

        # ===== STEP 3b: Pre-filter contracts (lightweight, no API calls) =====
        try:
            from apps.strategies.services.contract_prefilter import prefilter_contracts
            contract_ids = prefilter_contracts(futures_contracts, max_count=top_contracts)
            task_logger.info('prefiltered', f"Pre-filter: {pre_filter_count} → {len(contract_ids)} contracts")
        except Exception as pf_err:
            logger.warning(f"Contract pre-filter failed, using all: {pf_err}")

        contract_count = len(contract_ids)

        task_logger.info('contracts_found', f"Found {contract_count} contracts (from {pre_filter_count} pre-filter)", context={
            'this_month_volume': this_month_volume,
            'next_month_volume': next_month_volume,
            'pre_filter_count': pre_filter_count,
        })

        if contract_count == 0:
            task_logger.warning('no_contracts', "No contracts match volume/filter criteria")
            notify('SYSTEM_STATUS',
                title='Futures Algorithm',
                metrics={'Contracts': '0'},
                context=['No contracts match volume criteria'],
                collapsible=False,
            )
            return {'success': True, 'candidates_found': 0, 'qualified': 0}

        # ===== STEP 4: Split into batches and dispatch chord =====
        task_logger.step('dispatch', f"Dispatching {contract_count} contracts in batches of {batch_size}")

        # Split contract IDs into batches
        batches = [contract_ids[i:i + batch_size] for i in range(0, len(contract_ids), batch_size)]

        task_logger.info('batches_created', f"Created {len(batches)} batches", context={
            'batch_count': len(batches),
            'batch_size': batch_size,
            'total_contracts': contract_count
        })

        # Create chord: parallel subtasks + callback (pass regime to batches)
        subtasks = [
            analyze_futures_batch.s(batch, min_score=min_score, regime=regime)
            for batch in batches
        ]

        callback = aggregate_futures_results.s(
            min_score=min_score,
            orchestrator_task_id=self.request.id,
            regime=regime,
        )

        # Dispatch chord
        chord_result = chord(subtasks)(callback)

        task_logger.success("Chord dispatched successfully", context={
            'chord_id': str(chord_result.id),
            'subtask_count': len(subtasks),
            'total_contracts': contract_count
        })

        return {
            'success': True,
            'dispatched': True,
            'chord_id': str(chord_result.id),
            'batch_count': len(batches),
            'total_contracts': contract_count,
            'message': f"Dispatched {len(batches)} parallel tasks for {contract_count} contracts"
        }

    except Exception as e:
        task_logger.failure("Futures Algorithm failed", error=e)
        notify('TASK_ERROR',
            title='Futures Algorithm Failed',
            context=[str(e)],
        )
        return {'success': False, 'error': str(e)}
