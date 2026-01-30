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
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.db.models import Sum

from apps.analytics.models import LearningSession, LearningPattern
from apps.analytics.services.learning_engine import LearningEngine
from apps.positions.models import Position
from apps.accounts.models import BrokerAccount
from apps.alerts.services.telegram_client import send_telegram_notification

logger = logging.getLogger(__name__)


# =============================================================================
# CELERY SCHEDULED TASKS
# =============================================================================

@shared_task(name='apps.analytics.tasks.generate_daily_pnl_report')
def generate_daily_pnl_report():
    """
    Generate daily P&L report for all accounts

    Scheduled: Daily @ 4:00 PM (Mon-Fri)

    Workflow:
    1. Get all accounts and calculate daily P&L
    2. Get all positions closed today
    3. Calculate win rate, average P&L
    4. Generate summary report
    5. Send via Telegram

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Daily P&L Report Generation")
    logger.info("=" * 80)

    try:
        today = timezone.now().date()

        # Get all broker accounts
        all_accounts = BrokerAccount.objects.all()

        if not all_accounts.exists():
            logger.info("ℹ️ No accounts to report on")
            return {'success': True, 'accounts_reported': 0}

        report_lines = ["📊 DAILY P&L REPORT\n"]
        report_lines.append(f"Date: {today.strftime('%Y-%m-%d (%A)')}\n")
        report_lines.append("=" * 40 + "\n\n")

        total_daily_pnl = Decimal('0.00')
        total_positions_closed = 0
        total_winners = 0
        total_losers = 0

        for account in all_accounts:
            try:
                # Get positions closed today
                positions_closed_today = Position.objects.filter(
                    account=account,
                    status='CLOSED',
                    exit_timestamp__date=today
                )

                if not positions_closed_today.exists():
                    continue

                # Calculate daily P&L for this account
                daily_pnl = positions_closed_today.aggregate(
                    total=Sum('realized_pnl')
                )['total'] or Decimal('0.00')

                # Count winners and losers
                winners = positions_closed_today.filter(realized_pnl__gt=0).count()
                losers = positions_closed_today.filter(realized_pnl__lt=0).count()
                breakeven = positions_closed_today.filter(realized_pnl=0).count()

                # Win rate
                total_trades = positions_closed_today.count()
                win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

                # Account summary
                pnl_icon = "📈" if daily_pnl > 0 else "📉" if daily_pnl < 0 else "➖"

                report_lines.append(f"{pnl_icon} {account.account_name} ({account.broker})\n")
                report_lines.append(f"  Daily P&L: ₹{daily_pnl:,.0f}\n")
                report_lines.append(f"  Trades: {total_trades} ({winners}W/{losers}L/{breakeven}BE)\n")
                report_lines.append(f"  Win Rate: {win_rate:.1f}%\n\n")

                # Update totals
                total_daily_pnl += daily_pnl
                total_positions_closed += total_trades
                total_winners += winners
                total_losers += losers

            except Exception as e:
                logger.error(f"Error processing account {account.account_name}: {e}")
                report_lines.append(f"❌ Error for {account.account_name}\n\n")

        # Overall summary
        overall_win_rate = (total_winners / total_positions_closed * 100) if total_positions_closed > 0 else 0
        overall_icon = "📈" if total_daily_pnl > 0 else "📉" if total_daily_pnl < 0 else "➖"

        report_lines.append("=" * 40 + "\n")
        report_lines.append(f"{overall_icon} OVERALL SUMMARY\n")
        report_lines.append(f"Total P&L: ₹{total_daily_pnl:,.0f}\n")
        report_lines.append(f"Total Trades: {total_positions_closed}\n")
        report_lines.append(f"Winners: {total_winners} | Losers: {total_losers}\n")
        report_lines.append(f"Win Rate: {overall_win_rate:.1f}%\n")

        # Send report
        report_text = "".join(report_lines)
        send_telegram_notification(
            report_text,
            notification_type='INFO'
        )

        logger.info(f"✅ Daily P&L report generated: ₹{total_daily_pnl:,.0f}, {total_positions_closed} trades")
        logger.info("=" * 80)

        return {
            'success': True,
            'total_pnl': float(total_daily_pnl),
            'total_trades': total_positions_closed,
            'win_rate': float(overall_win_rate)
        }

    except Exception as e:
        logger.error(f"Error generating daily P&L report: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Daily P&L report generation failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}




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
                    exit_timestamp__date=today,
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
