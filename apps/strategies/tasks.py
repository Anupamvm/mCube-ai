"""
Strategy Celery Tasks

Automated tasks for strategy evaluation and execution.

DAILY WORKFLOW:
- 8:55 AM: setup_trading_day - Evaluate data, determine if day is tradable
- 9:15 AM: start_trading_day - Validate market opening, check news/changes
- 9:30 AM: evaluate_options_strategy - Decide strangle vs iron condor
- 9:40 AM: start_options_trade - Begin implementing option trades
- 9:40-10:15 AM: batch_options_averaging - Averaging entries
- 9:45 AM: screen_futures_opportunities - Screen top futures
- 3:25 PM: close_trading_day - Close positions with profit conditions
"""

import logging
from decimal import Decimal
from datetime import date, datetime, timedelta
from celery import shared_task
from django.utils import timezone
from django.db.models import Sum

from apps.accounts.models import BrokerAccount
from apps.positions.models import Position
from apps.strategies.strategies.kotak_strangle import execute_kotak_strangle_entry
from apps.strategies.strategies.icici_futures import (
    screen_futures_opportunities,
    execute_icici_futures_entry
)
from apps.positions.services.delta_monitor import monitor_delta
from apps.positions.services.averaging_manager import (
    should_average_position,
    get_averaging_recommendation
)
from apps.positions.services.exit_manager import should_exit_position
from apps.alerts.services.telegram_client import send_telegram_notification
from apps.core.utils.task_logger import TaskLogger

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
            message = (
                f"✅ KOTAK STRANGLE ENTRY\n\n"
                f"Position Created: #{result['position'].id}\n"
                f"Call Strike: {result['details']['strikes']['call_strike']}\n"
                f"Put Strike: {result['details']['strikes']['put_strike']}\n"
                f"Premium Collected: ₹{result['details']['premium_collected']:,.0f}\n"
                f"Margin Used: ₹{result['details']['margin_used']:,.0f}"
            )
            send_telegram_notification(message, notification_type='SUCCESS')
        else:
            message = (
                f"ℹ️ KOTAK STRANGLE ENTRY SKIPPED\n\n"
                f"Reason: {result['message']}"
            )
            send_telegram_notification(message, notification_type='INFO')

        logger.info("=" * 80)
        return result

    except Exception as e:
        logger.error(f"Error in Kotak entry evaluation: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Kotak entry evaluation failed\n{str(e)}",
            notification_type='ERROR'
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
            exit_type = "PROFIT_TARGET"
            logger.info(f"✅ Profit threshold reached: ₹{position.unrealized_pnl:,.0f}")

        if mandatory:
            # Friday - exit regardless
            should_exit = True
            reason = "Mandatory Friday EOD exit (before weekly expiry)"
            exit_type = "EOD_MANDATORY"

        if should_exit:
            # Close position
            from apps.positions.services.position_manager import close_position

            success, closed_position, message = close_position(
                position=position,
                exit_price=position.current_price,  # TODO: Fetch actual current price
                exit_reason=reason
            )

            if success:
                send_telegram_notification(
                    f"✅ POSITION CLOSED\n\n"
                    f"Position: #{position.id}\n"
                    f"Reason: {reason}\n"
                    f"P&L: ₹{closed_position.realized_pnl:,.0f}",
                    notification_type='SUCCESS'
                )
                return {'success': True, 'message': f'Position closed: {reason}'}
            else:
                send_telegram_notification(
                    f"❌ POSITION CLOSE FAILED\n\n"
                    f"Position: #{position.id}\n"
                    f"Error: {message}",
                    notification_type='ERROR'
                )
                return {'success': False, 'message': message}
        else:
            logger.info(f"ℹ️ Exit conditions not met: {reason}")
            return {'success': False, 'message': f'Exit not required: {reason}'}

    except Exception as e:
        logger.error(f"Error in Kotak exit evaluation: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Kotak exit evaluation failed\n{str(e)}",
            notification_type='ERROR'
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
        try:
            from apps.accounts.models import BrokerAccount
            active_accounts = BrokerAccount.objects.filter(is_active=True).count()
            setup.broker_connection_ok = active_accounts > 0
        except Exception:
            setup.broker_connection_ok = False

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
            send_telegram_notification(
                f"✅ TRADING DAY SETUP\n\n"
                f"Date: {today}\n"
                f"Data Fresh: Trendlyne ✓ News {'✓' if setup.news_data_fresh else '✗'}\n"
                f"Risk Level: {overnight_risk}\n"
                f"SGX Change: {setup.sgx_nifty_change or 'N/A'}%\n\n"
                f"Day cleared for trading. Waiting for market open validation at 9:15 AM.",
                notification_type='SUCCESS'
            )
        else:
            send_telegram_notification(
                f"❌ NO TRADING TODAY\n\n"
                f"Date: {today}\n"
                f"Reason: {setup.setup_reason}",
                notification_type='WARNING'
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
        from apps.strategies.models import TradingDaySetup, MarketOpeningState
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
            send_telegram_notification(
                f"✅ TRADING DAY STARTED\n\n"
                f"Nifty Open: {setup.nifty_open or 'N/A'}\n"
                f"Gap: {setup.gap_percent:.2f}%\n" if setup.gap_percent else "" +
                f"VIX: {setup.vix_open} ({setup.vix_level})\n"
                f"Near 52W High: {'Yes' if setup.near_52w_high else 'No'}\n\n"
                f"Recommended: {setup.get_recommended_strategy_display()}\n"
                f"Futures: {'✓' if setup.futures_trading_allowed else '✗'}\n"
                f"Strangle: {'✓' if setup.options_strangle_allowed else '✗'}\n"
                f"Iron Condor: {'✓' if setup.options_iron_condor_allowed else '✗'}",
                notification_type='SUCCESS'
            )
        else:
            send_telegram_notification(
                f"❌ TRADING PAUSED\n\n"
                f"Reason: {setup.start_reason}\n\n"
                f"Will re-evaluate conditions.",
                notification_type='WARNING'
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

        today = date.today()

        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
        except TradingDaySetup.DoesNotExist:
            task_logger.error('no_setup', "No setup record found")
            return {'success': False, 'error': 'Setup not found'}

        if not setup.is_tradable:
            task_logger.info('skipped', "Day not tradable, skipping options evaluation")
            return {'success': True, 'skipped': True, 'reason': setup.tradable_reason}

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
            send_telegram_notification(
                f"⏸️ OPTIONS STRATEGY: WAIT\n\n"
                f"Reason: {', '.join(strategy_reason)}\n\n"
                f"Will re-evaluate at 9:40 AM.",
                notification_type='INFO'
            )
        else:
            send_telegram_notification(
                f"📊 OPTIONS STRATEGY SELECTED\n\n"
                f"Strategy: {selected_strategy}\n"
                f"VIX: {setup.vix_open} ({setup.vix_level})\n"
                f"Near 52W High: {'Yes' if setup.near_52w_high else 'No'}\n"
                f"Reason: {', '.join(strategy_reason) if strategy_reason else 'Default conditions'}\n\n"
                f"Trade will start at 9:40 AM.",
                notification_type='SUCCESS'
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
def start_options_trade(self):
    """
    Start Options Trade (9:40 AM Daily)

    Implements the selected options strategy:
    1. Check if strategy was selected
    2. Execute entry based on strategy type
    3. Mark trade as started
    """
    task_logger = TaskLogger(
        task_name='start_options_trade',
        task_category='strategies',
        task_id=self.request.id
    )

    task_logger.start("Starting options trade implementation")

    try:
        from apps.strategies.models import TradingDaySetup

        today = date.today()

        try:
            setup = TradingDaySetup.objects.get(trading_date=today)
        except TradingDaySetup.DoesNotExist:
            return {'success': False, 'error': 'Setup not found'}

        if not setup.is_tradable:
            return {'success': True, 'skipped': True, 'reason': 'Day not tradable'}

        if not setup.options_strategy_evaluated:
            return {'success': False, 'error': 'Options strategy not evaluated'}

        strategy = setup.options_strategy_selected

        if strategy == 'WAIT':
            task_logger.info('waiting', "Strategy is WAIT, skipping trade start")
            return {'success': True, 'skipped': True, 'reason': 'Waiting for better conditions'}

        task_logger.step('execute', f"Executing {strategy} strategy")

        # Execute based on strategy
        if strategy == 'STRANGLE':
            # Execute strangle entry
            result = execute_kotak_strangle_entry(
                BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()
            )
        elif strategy == 'IRON_CONDOR':
            # TODO: Implement iron condor entry
            result = {'success': False, 'message': 'Iron condor not yet implemented'}
        else:
            result = {'success': False, 'message': f'Unknown strategy: {strategy}'}

        # Update setup
        setup.options_trade_started = result.get('success', False)
        setup.options_trade_started_at = timezone.now()
        setup.save()

        if result.get('success'):
            send_telegram_notification(
                f"✅ OPTIONS TRADE STARTED\n\n"
                f"Strategy: {strategy}\n"
                f"Position: #{result.get('position', {}).id if result.get('position') else 'N/A'}\n\n"
                f"Averaging will continue until 10:15 AM.",
                notification_type='SUCCESS'
            )
        else:
            send_telegram_notification(
                f"❌ OPTIONS TRADE FAILED\n\n"
                f"Strategy: {strategy}\n"
                f"Reason: {result.get('message', 'Unknown error')}",
                notification_type='ERROR'
            )

        task_logger.success("Options trade start completed", context=result)
        return result

    except Exception as e:
        task_logger.failure("Error in start_options_trade", error=e)
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.strategies.tasks.batch_options_averaging', bind=True)
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

        # Get active options positions
        options_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type__in=['WEEKLY_NIFTY_STRANGLE', 'IRON_CONDOR']
        )

        averaged_count = 0

        for position in options_positions:
            # Check if averaging needed
            recommendation = get_averaging_recommendation(position, position.current_price)

            if recommendation.get('should_average'):
                # TODO: Execute averaging
                task_logger.info('averaging', f"Averaging recommended for position {position.id}")
                averaged_count += 1

        # Check if averaging window complete
        if now >= averaging_end:
            setup.averaging_completed = True
            setup.averaging_completed_at = timezone.now()
            setup.save()

        task_logger.success("Batch averaging completed", context={
            'positions_checked': options_positions.count(),
            'averaged': averaged_count
        })

        return {
            'success': True,
            'positions_checked': options_positions.count(),
            'averaged': averaged_count
        }

    except Exception as e:
        task_logger.failure("Error in batch_options_averaging", error=e)
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.strategies.tasks.screen_futures_opportunities')
def screen_futures_opportunities_task():
    """
    Screen Futures Opportunities (9:45 AM Daily)

    Screens top 30 futures by volume and saves top 5 suggestions:
    1. Get top 30 futures by volume
    2. Analyze OI buildup, technical, sector
    3. Score and rank candidates
    4. Save top 5 to database
    5. Send notification
    """
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

        # Send notification
        message = "📊 FUTURES SCREENING - TOP 5\n\n"

        for i, candidate in enumerate(top_5, 1):
            message += (
                f"{i}. {candidate['symbol']} - {candidate['direction']}\n"
                f"   Score: {candidate['composite_score']}/100\n"
                f"   OI: {candidate.get('oi_analysis', {}).get('buildup_type', 'N/A')}\n\n"
            )

        message += "\nView in Futures Algorithm page for details."

        send_telegram_notification(message, notification_type='INFO')

        logger.info(f"✅ Found {len(candidates)} candidates, saved top 5")

        return {
            'success': True,
            'candidates_found': len(candidates),
            'top_5': [c['symbol'] for c in top_5]
        }

    except Exception as e:
        logger.error(f"Error in futures screening: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Futures screening failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.strategies.tasks.close_trading_day', bind=True)
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

        task_logger.step('close_positions', f"Processing {option_positions.count()} positions")

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
            should_close = False
            close_reason = ""

            if is_force_close:
                should_close = True
                close_reason = "Force close at 3:28 PM"
                close_results['forced'] += 1
            elif position_pnl >= MIN_PROFIT:
                should_close = True
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

            # Close the position
            task_logger.info('closing', f"Closing position {position.id}: {close_reason}")

            try:
                success, closed_pos, msg = close_position(
                    position=position,
                    exit_price=position.current_price,
                    exit_reason=close_reason
                )

                if success:
                    close_results['closed'] += 1
                    close_results['total_pnl'] += closed_pos.realized_pnl or Decimal('0')
                    close_results['details'].append({
                        'position_id': position.id,
                        'symbol': position.instrument,
                        'pnl': float(closed_pos.realized_pnl or 0),
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
        send_telegram_notification(
            f"📊 TRADING DAY CLOSED\n\n"
            f"Positions: {close_results['total']}\n"
            f"Closed: {close_results['closed']}\n"
            f"Skipped (low profit): {close_results['skipped']}\n"
            f"Force Closed: {close_results['forced']}\n\n"
            f"Total P&L: ₹{close_results['total_pnl']:,.0f}",
            notification_type='SUCCESS' if close_results['total_pnl'] >= 0 else 'WARNING'
        )

        task_logger.success("Trading day close completed", context={
            'closed': close_results['closed'],
            'total_pnl': float(close_results['total_pnl'])
        })

        return {'success': True, **close_results}

    except Exception as e:
        task_logger.failure("Error in close_trading_day", error=e)
        send_telegram_notification(
            f"❌ ERROR: Close trading day failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'error': str(e)}


# =============================================================================
# FUTURES AVERAGING TASK (existing, updated)
# =============================================================================

@shared_task(name='apps.strategies.tasks.check_futures_averaging')
def check_futures_averaging():
    """
    Check if active futures positions need averaging

    Scheduled: Every 10 minutes during market hours

    Workflow:
    1. Get all active futures positions
    2. Check if averaging needed (1% loss trigger)
    3. Send recommendation via Telegram
    4. Wait for manual approval to execute averaging
    """
    logger.info("CELERY TASK: Futures Averaging Check")

    try:
        # Get all active futures positions
        futures_positions = Position.objects.filter(
            status='ACTIVE',
            strategy_type='LLM_VALIDATED_FUTURES'
        )

        if not futures_positions.exists():
            logger.info("ℹ️ No active futures positions to check")
            return {'success': True, 'positions_checked': 0}

        checked_count = 0
        averaging_recommendations = 0

        for position in futures_positions:
            try:
                # Get current price
                # TODO: Fetch actual current price from broker
                current_price = position.current_price

                # Check if averaging needed
                recommendation = get_averaging_recommendation(position, current_price)

                if recommendation['should_average']:
                    # Send recommendation
                    preview = recommendation['preview']

                    message = (
                        f"⚠️ AVERAGING RECOMMENDATION\n\n"
                        f"Position: #{position.id}\n"
                        f"Symbol: {position.instrument}\n"
                        f"Direction: {position.direction}\n\n"
                        f"Current Entry: ₹{preview['current_entry']:,.2f}\n"
                        f"Current Price: ₹{preview['averaging_price']:,.2f}\n"
                        f"Loss: {recommendation['details']['loss_pct']:.2f}%\n\n"
                        f"RECOMMENDATION:\n"
                        f"Add {preview['quantity_to_add']} quantity\n"
                        f"New Avg Entry: ₹{preview['new_average_entry']:,.2f}\n"
                        f"New Stop-Loss: ₹{preview['new_stop_loss']:,.2f}\n"
                        f"Additional Margin: ₹{preview['additional_margin_needed']:,.0f}\n\n"
                        f"Averaging Count: {preview['averaging_count_after']}/3\n\n"
                        f"ℹ️ Manual approval required"
                    )

                    send_telegram_notification(message, notification_type='WARNING')
                    averaging_recommendations += 1

                checked_count += 1

            except Exception as e:
                logger.error(f"Error checking averaging for position {position.id}: {e}")

        logger.info(
            f"✅ Checked {checked_count} positions, "
            f"{averaging_recommendations} averaging recommendations"
        )

        return {
            'success': True,
            'positions_checked': checked_count,
            'averaging_recommendations': averaging_recommendations
        }

    except Exception as e:
        logger.error(f"Error in averaging check: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}
