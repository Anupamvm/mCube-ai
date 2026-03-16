"""
Background tasks for analytics system

Celery Scheduled Tasks:
=======================
Daily Tasks (4:00-5:00 PM, Mon-Fri):
- generate_daily_pnl_report: Daily P&L report (4:00 PM)
- sync_benchmark_data: Sync Nifty/BankNifty data (4:00 PM)
- daily_data_aggregation: Sync trades and update DailyPnL (4:30 PM)
- update_equity_curves: Update DailyEquityCurve (5:00 PM)

On-demand Tasks (Celery):
- run_learning_analysis: Analyze learning sessions
- analyze_single_trade: Analyze individual trades
- calculate_session_metrics: Calculate session metrics
- validate_patterns: Validate pattern effectiveness
"""

import logging
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from django.db.models import Sum

from apps.analytics.models import LearningSession
from apps.analytics.services.learning_engine import LearningEngine
from apps.positions.models import Position
from apps.accounts.models import BrokerAccount
from apps.alerts.services.telegram_client import send_telegram_notification
from apps.alerts.services.notification_service import notify
from apps.core.utils.decorators import task_enabled_guard

logger = logging.getLogger(__name__)


# =============================================================================
# CELERY SCHEDULED TASKS
# =============================================================================

@shared_task(name='apps.analytics.tasks.generate_daily_pnl_report')
@task_enabled_guard('generate-daily-pnl-report')
def generate_daily_pnl_report():
    """
    Generate daily P&L report for all accounts.

    Covers:
    - Positions closed today (realized P&L)
    - Positions still open (entered today or carried forward) with unrealized P&L
    - Per-position breakdown with entry price, LTP, and P&L %

    Scheduled: Daily @ 4:00 PM (Mon-Fri)

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Daily P&L Report Generation")
    logger.info("=" * 80)

    try:
        today = timezone.now().date()

        all_accounts = BrokerAccount.objects.all()
        if not all_accounts.exists():
            logger.info("ℹ️ No accounts to report on")
            return {'success': True, 'accounts_reported': 0}

        report_lines = ["📊 DAILY P&L REPORT\n"]
        report_lines.append(f"Date: {today.strftime('%Y-%m-%d (%A)')}\n")
        report_lines.append("=" * 40 + "\n\n")

        grand_realized = Decimal('0.00')
        grand_unrealized = Decimal('0.00')
        grand_today_change = Decimal('0.00')  # Today's actual P&L change
        grand_closed_count = 0
        grand_open_count = 0
        grand_winners = 0
        grand_losers = 0
        any_activity = False

        # ── Portfolio-level today's change from PortfolioPnlTracker ─────────
        # The open positions page auto-saves P&L snapshots every ~2 min,
        # including live prices from BOTH brokers. This is the authoritative
        # source for today's P&L — more accurate than MonitorLog which may
        # have stale prices for some brokers.
        from apps.positions.models import PortfolioPnlTracker
        from datetime import timedelta

        _portfolio_today_change = Decimal('0')
        _portfolio_day_open = None
        _portfolio_now = None
        _has_portfolio_tracker = False

        today_tracker = PortfolioPnlTracker.objects.filter(date=today).first()
        if today_tracker and today_tracker.snapshots:
            snaps = today_tracker.snapshots
            _portfolio_day_open = Decimal(str(snaps[0]['pnl']))
            _portfolio_now = Decimal(str(snaps[-1]['pnl']))
            _portfolio_today_change = _portfolio_now - _portfolio_day_open
            _has_portfolio_tracker = True

        # Also find previous trading day's close for reference
        _prev_day_close_pnl = None
        for days_back in range(1, 8):
            check_date = today - timedelta(days=days_back)
            prev_tracker = PortfolioPnlTracker.objects.filter(date=check_date).first()
            if prev_tracker and prev_tracker.snapshots:
                _prev_day_close_pnl = Decimal(str(prev_tracker.snapshots[-1]['pnl']))
                break

        # Today's change = current P&L - day open P&L (first snapshot)
        # This captures the actual intraday move since market open,
        # which is what the user sees on the broker dashboard.
        # (Prev close may differ due to weekend gaps, corporate actions, etc.)

        for account in all_accounts:
            try:
                # --- Closed today ---
                closed_today = Position.objects.filter(
                    account=account,
                    status='CLOSED',
                    exit_time__date=today
                )

                # --- Open positions (entered today OR carried forward) ---
                open_positions = Position.objects.filter(
                    account=account,
                    status__in=['OPEN', 'ACTIVE']
                )

                if not closed_today.exists() and not open_positions.exists():
                    continue

                any_activity = True
                report_lines.append(f"🏦 {account.account_name}\n")
                report_lines.append("-" * 30 + "\n")

                # -- Closed positions section --
                if closed_today.exists():
                    acct_realized = closed_today.aggregate(
                        total=Sum('realized_pnl')
                    )['total'] or Decimal('0.00')
                    winners = closed_today.filter(realized_pnl__gt=0).count()
                    losers = closed_today.filter(realized_pnl__lt=0).count()
                    closed_count = closed_today.count()
                    win_rate = (winners / closed_count * 100) if closed_count > 0 else 0

                    pnl_icon = "📈" if acct_realized > 0 else "📉" if acct_realized < 0 else "➖"
                    report_lines.append(f"\n{pnl_icon} Closed Trades: {closed_count}\n")
                    report_lines.append(f"  Realized P&L: ₹{acct_realized:,.0f}\n")
                    report_lines.append(f"  Win Rate: {win_rate:.0f}% ({winners}W/{losers}L)\n")

                    for pos in closed_today.order_by('-realized_pnl'):
                        pnl_pct = _calc_pnl_pct(pos.entry_price, pos.exit_price, pos.direction)
                        icon = "✅" if pos.realized_pnl > 0 else "❌" if pos.realized_pnl < 0 else "➖"
                        lot_label = f"{pos.lots} lot{'s' if pos.lots != 1 else ''}" if pos.lot_size > 1 else f"Qty: {pos.quantity}"
                        report_lines.append(
                            f"  {icon} {pos.instrument} {pos.direction}\n"
                            f"     Entry: ₹{pos.entry_price:,.2f} → Exit: ₹{pos.exit_price:,.2f} ({pnl_pct})\n"
                            f"     P&L: ₹{pos.realized_pnl:,.0f} | {lot_label}\n"
                        )
                        if pos.exit_reason:
                            report_lines.append(f"     Reason: {pos.exit_reason}\n")

                    grand_realized += acct_realized
                    grand_closed_count += closed_count
                    grand_winners += winners
                    grand_losers += losers

                # -- Open positions section --
                if open_positions.exists():
                    from apps.positions.models import MonitorLog

                    open_entered_today = open_positions.filter(entry_time__date=today)
                    open_carried = open_positions.exclude(entry_time__date=today)

                    acct_unrealized = open_positions.aggregate(
                        total=Sum('unrealized_pnl')
                    )['total'] or Decimal('0.00')

                    open_icon = "📈" if acct_unrealized > 0 else "📉" if acct_unrealized < 0 else "➖"
                    report_lines.append(f"\n{open_icon} Open Positions: {open_positions.count()}\n")
                    report_lines.append(f"  Unrealized P&L: ₹{acct_unrealized:,.0f}\n")

                    if open_entered_today.exists():
                        report_lines.append(f"\n  🆕 Entered Today ({open_entered_today.count()}):\n")
                        for pos in open_entered_today:
                            pnl_pct = _calc_pnl_pct(pos.entry_price, pos.current_price, pos.direction)
                            u_pnl = pos.unrealized_pnl or Decimal('0')
                            icon = "🟢" if u_pnl > 0 else "🔴" if u_pnl < 0 else "⚪"
                            lot_label = f"{pos.lots} lot{'s' if pos.lots != 1 else ''}" if pos.lot_size > 1 else f"Qty: {pos.quantity}"
                            report_lines.append(
                                f"  {icon} {pos.instrument} {pos.direction}\n"
                                f"     Avg: ₹{pos.entry_price:,.2f} → LTP: ₹{pos.current_price:,.2f} ({pnl_pct})\n"
                                f"     P&L: ₹{u_pnl:,.0f} | {lot_label}\n"
                            )
                            if pos.stop_loss:
                                report_lines.append(f"     SL: ₹{pos.stop_loss:,.2f}")
                                if pos.target:
                                    report_lines.append(f" | TGT: ₹{pos.target:,.2f}")
                                report_lines.append("\n")

                    if open_carried.exists():
                        report_lines.append(f"\n  📦 Carried Forward ({open_carried.count()}):\n")
                        for pos in open_carried:
                            pnl_pct = _calc_pnl_pct(pos.entry_price, pos.current_price, pos.direction)
                            u_pnl = pos.unrealized_pnl or Decimal('0')
                            icon = "🟢" if u_pnl > 0 else "🔴" if u_pnl < 0 else "⚪"
                            days_held = (today - pos.entry_time.date()).days
                            lot_label = f"{pos.lots} lot{'s' if pos.lots != 1 else ''}" if pos.lot_size > 1 else f"Qty: {pos.quantity}"
                            report_lines.append(
                                f"  {icon} {pos.instrument} {pos.direction} (Day {days_held})\n"
                                f"     Avg: ₹{pos.entry_price:,.2f} → LTP: ₹{pos.current_price:,.2f} ({pnl_pct})\n"
                                f"     P&L: ₹{u_pnl:,.0f} | {lot_label}\n"
                            )

                    grand_unrealized += acct_unrealized
                    grand_open_count += open_positions.count()

                report_lines.append("\n")

            except Exception as e:
                logger.error(f"Error processing account {account.account_name}: {e}")
                report_lines.append(f"❌ Error for {account.account_name}\n  {str(e)[:100]}\n\n")

        # --- Overall Summary ---
        report_lines.append("=" * 40 + "\n")

        if not any_activity:
            report_lines.append("📭 No positions or trades today.\n")
        else:
            # Today's P&L from PortfolioPnlTracker (live broker prices, auto-saved)
            grand_today_change = _portfolio_today_change
            net_day_pnl = grand_realized + grand_today_change
            overall_icon = "📈" if net_day_pnl > 0 else "📉" if net_day_pnl < 0 else "➖"

            report_lines.append(f"{overall_icon} DAY SUMMARY\n")
            if grand_closed_count > 0:
                overall_win_rate = (grand_winners / grand_closed_count * 100)
                report_lines.append(f"Realized P&L: ₹{grand_realized:,.0f} ({grand_closed_count} closed)\n")
                report_lines.append(f"Win Rate: {overall_win_rate:.0f}% ({grand_winners}W/{grand_losers}L)\n")
            if grand_open_count > 0:
                report_lines.append(f"Today's Move: ₹{grand_today_change:+,.0f} ({grand_open_count} open)\n")
                report_lines.append(f"Total Unrealized: ₹{grand_unrealized:,.0f} (from entry)\n")
            report_lines.append(f"Net Day P&L: ₹{net_day_pnl:+,.0f}\n")

        # ── Build structured notification ────────────────────────────────────
        grand_today_change = _portfolio_today_change
        net_day_pnl = grand_realized + grand_today_change
        day_status = 'SUCCESS' if net_day_pnl >= 0 else 'WARNING'

        # Build per-account summary lines for the expandable section
        acct_summary = []
        for account in all_accounts:
            open_pos = Position.objects.filter(
                account=account, status__in=['OPEN', 'ACTIVE']
            )
            closed_pos = Position.objects.filter(
                account=account, status='CLOSED', exit_time__date=today
            )
            if not open_pos.exists() and not closed_pos.exists():
                continue

            acct_pnl = (open_pos.aggregate(total=Sum('unrealized_pnl'))['total'] or Decimal('0'))
            icon = "🟢" if acct_pnl > 0 else "🔴" if acct_pnl < 0 else "⚪"
            acct_summary.append(
                f"{icon} {account.account_name}: ₹{acct_pnl:+,.0f} ({open_pos.count()} open)"
            )
            # Per-position compact lines
            for pos in open_pos:
                if not pos.entry_time:
                    continue
                u = pos.unrealized_pnl or Decimal('0')
                pct = _calc_pnl_pct(pos.entry_price, pos.current_price, pos.direction)
                days = (today - pos.entry_time.date()).days if pos.entry_time else 0
                tag = "NEW" if days == 0 else f"D{days}"
                acct_summary.append(
                    f"  {pos.instrument} {pos.direction} [{tag}] ₹{u:+,.0f} ({pct})"
                )
            if closed_pos.exists():
                r = closed_pos.aggregate(total=Sum('realized_pnl'))['total'] or Decimal('0')
                acct_summary.append(f"  Closed: {closed_pos.count()} trades, ₹{r:+,.0f}")

        # Headline metrics (always visible above fold)
        metrics = {
            "Day P&L": f"₹{net_day_pnl:+,.0f}",
            "Unrealized": f"₹{grand_unrealized:,.0f}",
        }
        if grand_closed_count > 0:
            metrics["Realized"] = f"₹{grand_realized:+,.0f}"
            metrics["Win Rate"] = f"{grand_winners}W/{grand_losers}L"

        notify('JOB_COMPLETED',
            title='Daily P&L Report',
            status=day_status,
            task='generate_daily_pnl_report',
            metrics=metrics,
            context=acct_summary if acct_summary else ['No activity today'],
            collapsible=True,
        )

        grand_total = grand_realized + grand_unrealized
        logger.info(f"✅ Daily P&L report: realized=₹{grand_realized:,.0f}, unrealized=₹{grand_unrealized:,.0f}, net=₹{grand_total:,.0f}")
        logger.info("=" * 80)

        return {
            'success': True,
            'realized_pnl': float(grand_realized),
            'unrealized_pnl': float(grand_unrealized),
            'closed_trades': grand_closed_count,
            'open_positions': grand_open_count,
        }

    except Exception as e:
        logger.error(f"Error generating daily P&L report: {e}", exc_info=True)
        notify('TASK_ERROR',
            title='P&L Report Failed',
            task='generate_daily_pnl_report',
            context=[str(e)[:200]],
            collapsible=False,
        )
        return {'success': False, 'message': str(e)}


def _calc_pnl_pct(entry_price, compare_price, direction):
    """Calculate P&L percentage string given entry, compare price and direction."""
    if not entry_price or entry_price == 0 or not compare_price:
        return "0.0%"
    if direction == 'SHORT':
        pct = float((entry_price - compare_price) / entry_price * 100)
    else:
        pct = float((compare_price - entry_price) / entry_price * 100)
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"




# =============================================================================
# ON-DEMAND CELERY TASKS
# =============================================================================


@shared_task(name='apps.analytics.tasks.run_learning_analysis')
def run_learning_analysis(session_id):
    """
    Run complete learning analysis for a session.

    This task:
    1. Analyzes all new closed trades
    2. Discovers patterns
    3. Generates parameter suggestions
    4. Calculates performance metrics

    Args:
        session_id: ID of the LearningSession to analyze
    """
    try:
        session = LearningSession.objects.get(id=session_id)

        if not session.is_active():
            logger.warning(f"Session {session.name} is not active, skipping analysis")
            return

        logger.info(f"=🔬 Starting learning analysis for session: {session.name}")

        engine = LearningEngine()

        # Step 1: Analyze trades
        logger.info("Step 1: Analyzing trades...")
        trades_analyzed = engine.analyze_trades(session)
        logger.info(f"   Analyzed {trades_analyzed} trades")

        # Step 2: Discover patterns
        logger.info("Step 2: Discovering patterns...")
        patterns_found = engine.discover_patterns(session)
        logger.info(f"   Discovered {patterns_found} patterns")

        # Step 3: Generate suggestions
        logger.info("Step 3: Generating parameter suggestions...")
        suggestions_count = engine.suggest_improvements(session)
        logger.info(f"   Created {suggestions_count} suggestions")

        # Step 4: Calculate metrics
        logger.info("Step 4: Calculating performance metrics...")
        metrics = engine.calculate_metrics(session, time_period='all')
        logger.info(f"   Calculated metrics: {metrics}")

        logger.info(f"✅ Learning analysis complete for session: {session.name}")

        # Schedule next analysis if session is still running
        if session.is_active():
            # Run again in 1 hour
            schedule_next_learning_analysis.apply_async(
                args=[session_id],
                countdown=3600
            )

    except LearningSession.DoesNotExist:
        logger.error(f"Learning session {session_id} not found")
    except Exception as e:
        logger.error(f"Error in learning analysis: {e}", exc_info=True)


@shared_task(name='apps.analytics.tasks.schedule_next_learning_analysis')
def schedule_next_learning_analysis(session_id, schedule=3600):
    """
    Schedule the next learning analysis.

    Args:
        session_id: ID of the LearningSession
        schedule: Seconds until next run (default 1 hour)
    """
    try:
        session = LearningSession.objects.get(id=session_id)

        if session.is_active():
            logger.info(f"=📅 Scheduling next analysis for {session.name} in {schedule} seconds")
            run_learning_analysis.apply_async(
                args=[session_id],
                countdown=schedule
            )
        else:
            logger.info(f"Session {session.name} is no longer active, stopping scheduled analysis")

    except LearningSession.DoesNotExist:
        logger.error(f"Learning session {session_id} not found")
    except Exception as e:
        logger.error(f"Error scheduling next analysis: {e}", exc_info=True)


@shared_task(name='apps.analytics.tasks.analyze_single_trade')
def analyze_single_trade(position_id):
    """
    Analyze a single trade in the background.

    Args:
        position_id: ID of the Position to analyze
    """
    try:
        from apps.positions.models import Position
        position = Position.objects.get(id=position_id)

        # Check if already analyzed
        if hasattr(position, 'performance_analysis'):
            logger.info(f"Position {position_id} already has performance analysis")
            return

        logger.info(f"Analyzing position: {position.symbol}")

        engine = LearningEngine()
        performance = engine._analyze_single_trade(position)

        logger.info(f"✅ Created performance analysis for {position.symbol}: Score {performance.entry_score}")

    except Exception as e:
        logger.error(f"Error analyzing position {position_id}: {e}", exc_info=True)


@shared_task(name='apps.analytics.tasks.calculate_session_metrics')
def calculate_session_metrics(session_id, time_period='all'):
    """
    Calculate and save performance metrics for a session.

    Args:
        session_id: ID of the LearningSession
        time_period: Time period to calculate ('all', 'last_7_days', 'last_30_days')
    """
    try:
        session = LearningSession.objects.get(id=session_id)

        logger.info(f"=📊 Calculating {time_period} metrics for {session.name}")

        engine = LearningEngine()
        metrics = engine.calculate_metrics(session, time_period=time_period)

        logger.info(f"✅ Metrics calculated: {metrics}")

    except LearningSession.DoesNotExist:
        logger.error(f"Learning session {session_id} not found")
    except Exception as e:
        logger.error(f"Error calculating metrics: {e}", exc_info=True)


@shared_task(name='apps.analytics.tasks.validate_patterns')
def validate_patterns(session_id):
    """
    Validate existing patterns with recent data.

    Args:
        session_id: ID of the LearningSession
    """
    try:
        from apps.analytics.models import LearningPattern
        from apps.analytics.services.pattern_recognition import PatternRecognizer

        session = LearningSession.objects.get(id=session_id)
        patterns = LearningPattern.objects.filter(session=session, validation_status='TESTING')

        logger.info(f"=🔍 Validating {patterns.count()} patterns for {session.name}")

        recognizer = PatternRecognizer(session)
        validated_count = 0

        for pattern in patterns:
            is_valid = recognizer.validate_pattern(pattern)
            if is_valid:
                pattern.validation_status = 'ACTIVE'
                pattern.last_validated = timezone.now()
                pattern.save()
                validated_count += 1

        logger.info(f"✅ Validated {validated_count} patterns")

    except LearningSession.DoesNotExist:
        logger.error(f"Learning session {session_id} not found")
    except Exception as e:
        logger.error(f"Error validating patterns: {e}", exc_info=True)


# Utility function to start continuous learning
def start_continuous_learning(session_id):
    """
    Start continuous learning for a session.

    This runs the initial analysis immediately and schedules recurring analysis.

    Args:
        session_id: ID of the LearningSession
    """
    logger.info(f"🚀 Starting continuous learning for session {session_id}")

    # Run initial analysis immediately
    run_learning_analysis.delay(session_id)

    logger.info(f"✅ Continuous learning started for session {session_id}")


# Utility function to stop continuous learning
def stop_continuous_learning(session_id):
    """
    Stop continuous learning for a session.

    This doesn't cancel already-queued tasks, but prevents new tasks from being scheduled.

    Args:
        session_id: ID of the LearningSession
    """
    logger.info(f"🛑 Stopping continuous learning for session {session_id}")

    # The session's is_active() status will be checked in the next task run
    # and will prevent further scheduling

    logger.info(f"✅ Continuous learning stopped for session {session_id}")


# =============================================================================
# NEW DATA PIPELINE TASKS (Phase 5)
# =============================================================================

@shared_task(name='apps.analytics.tasks.sync_benchmark_data')
@task_enabled_guard('sync-benchmark-data')
def sync_benchmark_data():
    """
    Sync benchmark data (Nifty/BankNifty) from Breeze historical API.

    Scheduled: Daily @ 4:00 PM (Mon-Fri)

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Sync Benchmark Data")
    logger.info("=" * 80)

    try:
        from apps.analytics.services.benchmark_analyzer import get_analyzer
        from datetime import date, timedelta

        analyzer = get_analyzer()

        today = date.today()
        # Sync last 5 days to catch any missed data
        from_date = today - timedelta(days=5)

        nifty_count = analyzer.fetch_benchmark_data('NIFTY50', from_date, today)
        banknifty_count = analyzer.fetch_benchmark_data('BANKNIFTY', from_date, today)

        logger.info(f"Synced benchmark data: Nifty={nifty_count}, BankNifty={banknifty_count}")
        logger.info("=" * 80)

        return {
            'success': True,
            'nifty_records': nifty_count,
            'banknifty_records': banknifty_count,
        }

    except Exception as e:
        logger.error(f"Error syncing benchmark data: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.analytics.tasks.daily_data_aggregation')
@task_enabled_guard('daily-data-aggregation')
def daily_data_aggregation():
    """
    Daily data aggregation - sync trades and update DailyPnL.

    Scheduled: Daily @ 4:30 PM (Mon-Fri)

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Daily Data Aggregation")
    logger.info("=" * 80)

    try:
        from apps.analytics.models import DailyPnL
        from datetime import date

        today = date.today()
        accounts = BrokerAccount.objects.filter(is_active=True)

        accounts_updated = 0
        for account in accounts:
            try:
                # Get positions closed today
                positions = Position.objects.filter(
                    account=account,
                    status='CLOSED',
                    exit_time__date=today,
                )

                if not positions.exists():
                    continue

                # Calculate P&L
                realized_pnl = positions.aggregate(total=Sum('realized_pnl'))['total'] or Decimal('0.00')
                winners = positions.filter(realized_pnl__gt=0).count()
                losers = positions.filter(realized_pnl__lt=0).count()

                # Update or create DailyPnL
                DailyPnL.objects.update_or_create(
                    account=account,
                    date=today,
                    defaults={
                        'realized_pnl': realized_pnl,
                        'unrealized_pnl': Decimal('0.00'),
                        'total_pnl': realized_pnl,
                        'trades_count': positions.count(),
                        'winning_trades': winners,
                        'losing_trades': losers,
                        'starting_capital': account.allocated_capital,
                        'ending_capital': account.allocated_capital + realized_pnl,
                    }
                )

                accounts_updated += 1

            except Exception as e:
                logger.error(f"Error aggregating data for {account.account_name}: {e}")

        logger.info(f"Daily aggregation complete: {accounts_updated} accounts updated")
        logger.info("=" * 80)

        return {'success': True, 'accounts_updated': accounts_updated}

    except Exception as e:
        logger.error(f"Error in daily aggregation: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


@shared_task(name='apps.analytics.tasks.update_equity_curves')
@task_enabled_guard('update-equity-curves')
def update_equity_curves():
    """
    Update DailyEquityCurve for all accounts.

    Scheduled: Daily @ 5:00 PM (Mon-Fri)

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Update Equity Curves")
    logger.info("=" * 80)

    try:
        from apps.analytics.services.returns_calculator import get_calculator
        from datetime import date

        calculator = get_calculator()
        today = date.today()

        accounts = BrokerAccount.objects.filter(is_active=True)
        curves_updated = 0

        for account in accounts:
            try:
                curve = calculator.calculate_daily_equity(account, today)
                if curve:
                    curves_updated += 1
            except Exception as e:
                logger.error(f"Error updating equity curve for {account.account_name}: {e}")

        logger.info(f"Equity curves updated: {curves_updated} accounts")
        logger.info("=" * 80)

        return {'success': True, 'curves_updated': curves_updated}

    except Exception as e:
        logger.error(f"Error updating equity curves: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}
