"""
Background tasks for analytics and learning system

These tasks run in the background using Celery and django-background-tasks.

Celery Tasks (Scheduled):
- generate_daily_pnl_report: Daily P&L report (4:00 PM)
- update_learning_patterns: Update learning patterns (5:00 PM)
- send_weekly_summary: Weekly summary report (Friday 6:00 PM)

Background Tasks (On-demand):
- run_learning_analysis: Analyze learning sessions
- analyze_single_trade: Analyze individual trades
- calculate_session_metrics: Calculate session metrics
- validate_patterns: Validate pattern effectiveness
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from background_task import background
from celery import shared_task
from django.utils import timezone
from django.db.models import Sum, Avg, Count, Q

from apps.analytics.models import LearningSession, LearningPattern, PerformanceAnalysis
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


@shared_task(name='apps.analytics.tasks.update_learning_patterns')
def update_learning_patterns():
    """
    Update learning patterns for all active sessions

    Scheduled: Daily @ 5:00 PM (Mon-Fri)

    Workflow:
    1. Get all active learning sessions
    2. Analyze recent trades
    3. Discover new patterns
    4. Validate existing patterns
    5. Update pattern effectiveness scores

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Update Learning Patterns")
    logger.info("=" * 80)

    try:
        # Get all active learning sessions
        active_sessions = LearningSession.objects.filter(
            status='ACTIVE'
        )

        if not active_sessions.exists():
            logger.info("ℹ️ No active learning sessions")
            return {'success': True, 'sessions_processed': 0}

        sessions_processed = 0
        total_patterns_discovered = 0
        total_patterns_validated = 0

        for session in active_sessions:
            try:
                logger.info(f"Processing session: {session.name}")

                engine = LearningEngine()

                # Step 1: Analyze recent trades
                trades_analyzed = engine.analyze_trades(session)
                logger.info(f"  Analyzed {trades_analyzed} trades")

                # Step 2: Discover new patterns
                patterns_found = engine.discover_patterns(session)
                logger.info(f"  Discovered {patterns_found} new patterns")
                total_patterns_discovered += patterns_found

                # Step 3: Validate existing patterns
                patterns = LearningPattern.objects.filter(
                    session=session,
                    validation_status='TESTING'
                )

                from apps.analytics.services.pattern_recognition import PatternRecognizer
                recognizer = PatternRecognizer(session)
                validated_count = 0

                for pattern in patterns:
                    is_valid = recognizer.validate_pattern(pattern)
                    if is_valid:
                        pattern.validation_status = 'ACTIVE'
                        pattern.last_validated = timezone.now()
                        pattern.save()
                        validated_count += 1

                logger.info(f"  Validated {validated_count} patterns")
                total_patterns_validated += validated_count

                sessions_processed += 1

            except Exception as e:
                logger.error(f"Error processing session {session.name}: {e}")

        logger.info(
            f"✅ Learning patterns updated: {sessions_processed} sessions, "
            f"{total_patterns_discovered} new patterns, {total_patterns_validated} validated"
        )
        logger.info("=" * 80)

        return {
            'success': True,
            'sessions_processed': sessions_processed,
            'patterns_discovered': total_patterns_discovered,
            'patterns_validated': total_patterns_validated
        }

    except Exception as e:
        logger.error(f"Error updating learning patterns: {e}", exc_info=True)
        return {'success': False, 'message': str(e)}


@shared_task(name='apps.analytics.tasks.send_weekly_summary')
def send_weekly_summary():
    """
    Send weekly summary report

    Scheduled: Friday @ 6:00 PM

    Workflow:
    1. Get all trades from this week
    2. Calculate weekly P&L, win rate
    3. Show top performers and worst trades
    4. Learning insights and pattern effectiveness
    5. Risk metrics and limit utilization
    6. Send comprehensive report via Telegram

    Returns:
        dict: Task execution summary
    """
    logger.info("=" * 80)
    logger.info("CELERY TASK: Weekly Summary Report")
    logger.info("=" * 80)

    try:
        # Get Monday of current week
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = today

        report_lines = ["📊 WEEKLY SUMMARY REPORT\n"]
        report_lines.append(f"Week: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}\n")
        report_lines.append("=" * 40 + "\n\n")

        # Get all positions closed this week
        weekly_positions = Position.objects.filter(
            status='CLOSED',
            exit_timestamp__date__gte=week_start,
            exit_timestamp__date__lte=week_end
        )

        if not weekly_positions.exists():
            report_text = "".join(report_lines) + "ℹ️ No trades this week"
            send_telegram_notification(report_text, notification_type='INFO')
            return {'success': True, 'trades_count': 0}

        # Calculate weekly metrics
        total_trades = weekly_positions.count()
        total_pnl = weekly_positions.aggregate(Sum('realized_pnl'))['realized_pnl__sum'] or Decimal('0.00')
        winners = weekly_positions.filter(realized_pnl__gt=0).count()
        losers = weekly_positions.filter(realized_pnl__lt=0).count()
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

        # Average P&L
        avg_winner = weekly_positions.filter(realized_pnl__gt=0).aggregate(
            Avg('realized_pnl')
        )['realized_pnl__avg'] or Decimal('0.00')
        avg_loser = weekly_positions.filter(realized_pnl__lt=0).aggregate(
            Avg('realized_pnl')
        )['realized_pnl__avg'] or Decimal('0.00')

        # Overall summary
        pnl_icon = "📈" if total_pnl > 0 else "📉" if total_pnl < 0 else "➖"

        report_lines.append(f"{pnl_icon} WEEKLY PERFORMANCE\n")
        report_lines.append(f"Total P&L: ₹{total_pnl:,.0f}\n")
        report_lines.append(f"Total Trades: {total_trades}\n")
        report_lines.append(f"Winners: {winners} ({win_rate:.1f}%)\n")
        report_lines.append(f"Losers: {losers}\n")
        report_lines.append(f"Avg Winner: ₹{avg_winner:,.0f}\n")
        report_lines.append(f"Avg Loser: ₹{avg_loser:,.0f}\n\n")

        # Top 3 winners
        top_winners = weekly_positions.filter(realized_pnl__gt=0).order_by('-realized_pnl')[:3]
        if top_winners.exists():
            report_lines.append("🏆 TOP WINNERS:\n")
            for i, pos in enumerate(top_winners, 1):
                report_lines.append(
                    f"{i}. {pos.instrument} - ₹{pos.realized_pnl:,.0f} "
                    f"({pos.strategy_type})\n"
                )
            report_lines.append("\n")

        # Top 3 losers
        top_losers = weekly_positions.filter(realized_pnl__lt=0).order_by('realized_pnl')[:3]
        if top_losers.exists():
            report_lines.append("📉 TOP LOSERS:\n")
            for i, pos in enumerate(top_losers, 1):
                report_lines.append(
                    f"{i}. {pos.instrument} - ₹{pos.realized_pnl:,.0f} "
                    f"({pos.strategy_type})\n"
                )
            report_lines.append("\n")

        # Strategy performance breakdown
        report_lines.append("📊 STRATEGY BREAKDOWN:\n")
        strategy_stats = weekly_positions.values('strategy_type').annotate(
            count=Count('id'),
            total_pnl=Sum('realized_pnl')
        ).order_by('-total_pnl')

        for stat in strategy_stats:
            strategy_pnl = stat['total_pnl'] or Decimal('0.00')
            strategy_icon = "✅" if strategy_pnl > 0 else "❌"
            report_lines.append(
                f"{strategy_icon} {stat['strategy_type']}: "
                f"₹{strategy_pnl:,.0f} ({stat['count']} trades)\n"
            )

        # Send report
        report_text = "".join(report_lines)
        send_telegram_notification(
            report_text,
            notification_type='INFO'
        )

        logger.info(
            f"✅ Weekly summary sent: ₹{total_pnl:,.0f}, {total_trades} trades, "
            f"{win_rate:.1f}% win rate"
        )
        logger.info("=" * 80)

        return {
            'success': True,
            'total_pnl': float(total_pnl),
            'total_trades': total_trades,
            'win_rate': float(win_rate)
        }

    except Exception as e:
        logger.error(f"Error sending weekly summary: {e}", exc_info=True)
        send_telegram_notification(
            f"❌ ERROR: Weekly summary generation failed\n{str(e)}",
            notification_type='ERROR'
        )
        return {'success': False, 'message': str(e)}


# =============================================================================
# BACKGROUND TASKS (On-demand, using django-background-tasks)
# =============================================================================


@background(schedule=0)
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

        logger.info(f"=� Starting learning analysis for session: {session.name}")

        engine = LearningEngine()

        # Step 1: Analyze trades
        logger.info("Step 1: Analyzing trades...")
        trades_analyzed = engine.analyze_trades(session)
        logger.info(f"   Analyzed {trades_analyzed} trades")

        # Step 2: Discover patterns
        logger.info("Step 2: Discovering patterns...")
        patterns_found = engine.discover_patterns(session)
        logger.info(f"   Discovered {patterns_found} patterns")

        # Step 3: Generate suggestions
        logger.info("Step 3: Generating parameter suggestions...")
        suggestions_count = engine.suggest_improvements(session)
        logger.info(f"   Created {suggestions_count} suggestions")

        # Step 4: Calculate metrics
        logger.info("Step 4: Calculating performance metrics...")
        metrics = engine.calculate_metrics(session, time_period='all')
        logger.info(f"   Calculated metrics: {metrics}")

        logger.info(f" Learning analysis complete for session: {session.name}")

        # Schedule next analysis if session is still running
        if session.is_active():
            # Run again in 1 hour (3600 seconds)
            schedule_next_learning_analysis(session_id, schedule=3600)

    except LearningSession.DoesNotExist:
        logger.error(f"Learning session {session_id} not found")
    except Exception as e:
        logger.error(f"Error in learning analysis: {e}", exc_info=True)


@background(schedule=0)
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
            logger.info(f"=� Scheduling next analysis for {session.name} in {schedule} seconds")
            run_learning_analysis(session_id, schedule=schedule)
        else:
            logger.info(f"Session {session.name} is no longer active, stopping scheduled analysis")

    except LearningSession.DoesNotExist:
        logger.error(f"Learning session {session_id} not found")
    except Exception as e:
        logger.error(f"Error scheduling next analysis: {e}", exc_info=True)


@background(schedule=0)
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

        logger.info(f"= Analyzing position: {position.symbol}")

        engine = LearningEngine()
        performance = engine._analyze_single_trade(position)

        logger.info(f" Created performance analysis for {position.symbol}: Score {performance.entry_score}")

    except Exception as e:
        logger.error(f"Error analyzing position {position_id}: {e}", exc_info=True)


@background(schedule=0)
def calculate_session_metrics(session_id, time_period='all'):
    """
    Calculate and save performance metrics for a session.

    Args:
        session_id: ID of the LearningSession
        time_period: Time period to calculate ('all', 'last_7_days', 'last_30_days')
    """
    try:
        session = LearningSession.objects.get(id=session_id)

        logger.info(f"=� Calculating {time_period} metrics for {session.name}")

        engine = LearningEngine()
        metrics = engine.calculate_metrics(session, time_period=time_period)

        logger.info(f" Metrics calculated: {metrics}")

    except LearningSession.DoesNotExist:
        logger.error(f"Learning session {session_id} not found")
    except Exception as e:
        logger.error(f"Error calculating metrics: {e}", exc_info=True)


@background(schedule=0)
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

        logger.info(f"=, Validating {patterns.count()} patterns for {session.name}")

        recognizer = PatternRecognizer(session)
        validated_count = 0

        for pattern in patterns:
            is_valid = recognizer.validate_pattern(pattern)
            if is_valid:
                pattern.validation_status = 'ACTIVE'
                pattern.last_validated = timezone.now()
                pattern.save()
                validated_count += 1

        logger.info(f" Validated {validated_count} patterns")

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
    logger.info(f"<� Starting continuous learning for session {session_id}")

    # Run initial analysis immediately
    run_learning_analysis(session_id, schedule=0)

    logger.info(f" Continuous learning started for session {session_id}")


# Utility function to stop continuous learning
def stop_continuous_learning(session_id):
    """
    Stop continuous learning for a session.

    This doesn't cancel already-queued tasks, but prevents new tasks from being scheduled.

    Args:
        session_id: ID of the LearningSession
    """
    logger.info(f"� Stopping continuous learning for session {session_id}")

    # The session's is_active() status will be checked in the next task run
    # and will prevent further scheduling

    logger.info(f" Continuous learning stopped for session {session_id}")
