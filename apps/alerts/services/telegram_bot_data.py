"""
Telegram Bot Data Mixin

Provides @sync_to_async data-fetching methods for the Telegram bot.
All methods use close_old_connections() for thread safety.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class DataMixin:
    """Data-fetching methods for TelegramBotHandler"""

    # =========================================================================
    # MAIN MENU DATA
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_main_menu_data(self) -> dict:
        """Get snapshot data for the main menu header."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import NseFlag

        try:
            vix = NseFlag.get('nseVix', '—')
            vix_status = NseFlag.get('vixStatus', '')
            is_tradable = NseFlag.get('isDayTradable', 'No')
            current_pnl = NseFlag.get('currentPos', '0')
            open_positions = NseFlag.get('openPositions', '0')

            return {
                'vix': vix,
                'vix_status': vix_status,
                'is_tradable': is_tradable,
                'current_pnl': current_pnl,
                'open_positions': open_positions,
            }
        except Exception as e:
            logger.error(f"Error fetching main menu data: {e}")
            return {
                'vix': '—',
                'vix_status': '',
                'is_tradable': 'N/A',
                'current_pnl': '0',
                'open_positions': '0',
            }

    # =========================================================================
    # P&L DATA
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_daily_pnl_data(self) -> dict:
        """Get today's P&L data."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import NseFlag

        try:
            # Try DailyPnL first
            from apps.analytics.models import DailyPnL
            today = date.today()

            pnl_records = DailyPnL.objects.filter(date=today)

            if pnl_records.exists():
                total_realized = sum(r.realized_pnl for r in pnl_records)
                total_unrealized = sum(r.unrealized_pnl for r in pnl_records)
                total_pnl = sum(r.total_pnl for r in pnl_records)
                total_trades = sum(r.trades_count for r in pnl_records)
                total_wins = sum(r.winning_trades for r in pnl_records)
                total_losses = sum(r.losing_trades for r in pnl_records)

                return {
                    'realized': float(total_realized),
                    'unrealized': float(total_unrealized),
                    'total': float(total_pnl),
                    'trades': total_trades,
                    'wins': total_wins,
                    'losses': total_losses,
                    'win_pct': round(total_wins / total_trades * 100) if total_trades > 0 else 0,
                    'source': 'DailyPnL',
                }

            # Fallback to NseFlag
            current_pnl = NseFlag.get('currentPos', '0')
            try:
                pnl_val = float(current_pnl)
            except (ValueError, TypeError):
                pnl_val = 0.0

            return {
                'realized': 0.0,
                'unrealized': pnl_val,
                'total': pnl_val,
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'win_pct': 0,
                'source': 'NseFlag',
            }

        except Exception as e:
            logger.error(f"Error fetching P&L data: {e}")
            return {
                'realized': 0.0,
                'unrealized': 0.0,
                'total': 0.0,
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'win_pct': 0,
                'source': 'error',
            }

    # =========================================================================
    # MARKET DATA
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_market_data(self) -> dict:
        """Get market snapshot data."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import NseFlag

        try:
            return {
                'vix': NseFlag.get('nseVix', '—'),
                'vix_status': NseFlag.get('vixStatus', ''),
                'is_tradable': NseFlag.get('isDayTradable', 'No'),
                'daily_delta': NseFlag.get('dailyDelta', '—'),
                'open_positions': NseFlag.get('openPositions', '0'),
            }
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return {
                'vix': '—',
                'vix_status': '',
                'is_tradable': 'N/A',
                'daily_delta': '—',
                'open_positions': '0',
            }

    # =========================================================================
    # RISK DATA
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_risk_dashboard_data(self) -> dict:
        """Get risk dashboard data."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.risk.models import RiskLimit, CircuitBreaker

            # Get risk limits
            risk_limits = []
            for rl in RiskLimit.objects.select_related('account').all():
                pct = float(rl.current_value / rl.limit_value * 100) if rl.limit_value > 0 else 0
                risk_limits.append({
                    'type': rl.limit_type,
                    'current': float(rl.current_value),
                    'limit': float(rl.limit_value),
                    'pct': round(pct, 1),
                    'breached': rl.is_breached,
                })

            # Get active circuit breakers
            active_breakers = CircuitBreaker.objects.filter(is_active=True).count()

            return {
                'risk_limits': risk_limits,
                'active_circuit_breakers': active_breakers,
            }
        except Exception as e:
            logger.error(f"Error fetching risk data: {e}")
            return {
                'risk_limits': [],
                'active_circuit_breakers': 0,
            }

    # =========================================================================
    # TASK MANAGEMENT DATA
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_task_summary(self) -> dict:
        """Get task counts by category."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import TASK_DEFAULT_CONFIG

        try:
            categories = {}
            for task_key, config in TASK_DEFAULT_CONFIG.items():
                cat = config.get('category', 'other')
                if cat not in categories:
                    categories[cat] = {'total': 0, 'active': 0}
                categories[cat]['total'] += 1

                if CeleryTaskState.is_task_enabled(task_key):
                    categories[cat]['active'] += 1

            return categories
        except Exception as e:
            logger.error(f"Error fetching task summary: {e}")
            return {}

    @sync_to_async(thread_sensitive=False)
    def _get_category_tasks(self, category: str) -> list:
        """Get tasks for a specific category."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import TASK_DEFAULT_CONFIG

        try:
            tasks = []
            for task_key, config in TASK_DEFAULT_CONFIG.items():
                if config.get('category') != category:
                    continue

                is_enabled = CeleryTaskState.is_task_enabled(task_key)

                # Build schedule description
                sched_type = config.get('schedule_type', 'crontab')
                if sched_type == 'crontab':
                    h = config.get('default_hour', 0)
                    m = config.get('default_minute', 0)
                    sched_desc = f"{h:02d}:{m:02d}"
                elif sched_type == 'recurring':
                    sh = config.get('default_recurring_start_hour', 0)
                    sm = config.get('default_recurring_start_minute', 0)
                    eh = config.get('default_recurring_end_hour', 0)
                    em = config.get('default_recurring_end_minute', 0)
                    iv = config.get('default_recurring_interval_minutes', 5)
                    sched_desc = f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d} q{iv}m"
                elif sched_type == 'interval':
                    secs = config.get('default_interval_seconds', 30)
                    sched_desc = f"q{secs}s"
                else:
                    sched_desc = ''

                tasks.append({
                    'key': task_key,
                    'name': config.get('display_name', task_key),
                    'is_enabled': is_enabled,
                    'schedule': sched_desc,
                })

            return tasks
        except Exception as e:
            logger.error(f"Error fetching category tasks: {e}")
            return []

    @sync_to_async(thread_sensitive=False)
    def _toggle_task(self, task_key: str) -> dict:
        """Toggle a task's enabled state and restart beat."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import TASK_DEFAULT_CONFIG

        try:
            current_state = CeleryTaskState.is_task_enabled(task_key)
            new_state = not current_state

            config = TASK_DEFAULT_CONFIG.get(task_key, {})
            task_path = ''
            # Get task_path from static schedule
            try:
                from mcube_ai.celery import get_static_schedule
                sched = get_static_schedule()
                if task_key in sched:
                    task_path = sched[task_key].get('task', '')
            except Exception:
                pass

            CeleryTaskState.set_task_state(
                task_key=task_key,
                enabled=new_state,
                task_path=task_path,
                display_name=config.get('display_name', task_key.replace('-', ' ').title()),
                user='telegram_bot',
            )

            # Restart beat to pick up changes
            from apps.core.views import ensure_celery_running
            ensure_celery_running()

            return {
                'success': True,
                'task_key': task_key,
                'is_enabled': new_state,
                'display_name': config.get('display_name', task_key),
            }
        except Exception as e:
            logger.error(f"Error toggling task {task_key}: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _run_task_immediately(self, task_key: str) -> dict:
        """Run a task immediately via Celery send_task."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from mcube_ai.celery import get_static_schedule
            from celery import current_app

            static_schedule = get_static_schedule()
            task_config = static_schedule.get(task_key)

            if not task_config:
                return {'success': False, 'error': f'Task "{task_key}" not found'}

            task_path = task_config.get('task')
            if not task_path:
                return {'success': False, 'error': f'No task path for "{task_key}"'}

            task_kwargs = task_config.get('kwargs', {}).copy()
            task_kwargs['_bypass_guard'] = True

            result = current_app.send_task(task_path, kwargs=task_kwargs)

            logger.info(f"Telegram bot triggered task: {task_key} ({task_path}), ID: {result.id}")

            return {
                'success': True,
                'task_key': task_key,
                'task_id': result.id,
            }
        except Exception as e:
            logger.error(f"Error running task {task_key}: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _bulk_toggle_tasks(self, enable: bool) -> dict:
        """Enable or disable all tasks."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import TASK_DEFAULT_CONFIG

        try:
            count = 0
            for task_key, config in TASK_DEFAULT_CONFIG.items():
                task_path = ''
                try:
                    from mcube_ai.celery import get_static_schedule
                    sched = get_static_schedule()
                    if task_key in sched:
                        task_path = sched[task_key].get('task', '')
                except Exception:
                    pass

                CeleryTaskState.set_task_state(
                    task_key=task_key,
                    enabled=enable,
                    task_path=task_path,
                    display_name=config.get('display_name', task_key.replace('-', ' ').title()),
                    user='telegram_bot',
                )
                count += 1

            # Restart beat
            from apps.core.views import ensure_celery_running
            ensure_celery_running()

            action = 'enabled' if enable else 'disabled'
            return {'success': True, 'message': f'{count} tasks {action}'}
        except Exception as e:
            logger.error(f"Error bulk toggling tasks: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # SYSTEM HEALTH DATA
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_system_health(self) -> dict:
        """Get system health status."""
        from django.db import close_old_connections
        close_old_connections()

        import subprocess
        from apps.core.models import NseFlag, BkLog

        health = {
            'worker': False,
            'beat': False,
            'redis': False,
            'breeze': False,
            'kotak': False,
            'last_task_ago': '—',
            'errors_24h': 0,
        }

        try:
            # Check Celery worker
            result = subprocess.run(
                ['pgrep', '-f', 'celery.*mcube.*worker'],
                capture_output=True, text=True
            )
            health['worker'] = result.returncode == 0 and bool(result.stdout.strip())

            # Check Celery beat
            result = subprocess.run(
                ['pgrep', '-f', 'celery.*mcube.*beat'],
                capture_output=True, text=True
            )
            health['beat'] = result.returncode == 0 and bool(result.stdout.strip())

            # Check Redis
            result = subprocess.run(
                ['redis-cli', 'ping'],
                capture_output=True, text=True
            )
            health['redis'] = result.returncode == 0 and 'PONG' in result.stdout

            # Check Breeze session
            breeze_token = NseFlag.get('breeze_session_token', '')
            health['breeze'] = bool(breeze_token)

            # Check Kotak session
            try:
                from apps.accounts.models import BrokerAccount
                kotak_acct = BrokerAccount.objects.filter(broker='KOTAK', is_active=True).first()
                health['kotak'] = kotak_acct is not None
            except Exception:
                pass

            # Last task execution
            try:
                from django.utils import timezone
                last_log = BkLog.objects.order_by('-timestamp').first()
                if last_log:
                    delta = timezone.now() - last_log.timestamp
                    if delta.total_seconds() < 60:
                        health['last_task_ago'] = f'{int(delta.total_seconds())}s ago'
                    elif delta.total_seconds() < 3600:
                        health['last_task_ago'] = f'{int(delta.total_seconds() / 60)} min ago'
                    else:
                        health['last_task_ago'] = f'{int(delta.total_seconds() / 3600)}h ago'
            except Exception:
                pass

            # Errors in last 24h
            try:
                from django.utils import timezone
                cutoff = timezone.now() - timedelta(hours=24)
                health['errors_24h'] = BkLog.objects.filter(
                    timestamp__gte=cutoff,
                    level__in=['error', 'critical']
                ).count()
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error checking system health: {e}")

        return health

    # =========================================================================
    # QUICK ACTIONS
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _pause_trading(self) -> dict:
        """Pause trading by setting isDayTradable to No."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.core.models import NseFlag
            NseFlag.set('isDayTradable', 'No', 'Paused via Telegram bot')
            return {'success': True, 'message': 'Trading paused'}
        except Exception as e:
            logger.error(f"Error pausing trading: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _resume_trading(self) -> dict:
        """Resume trading by setting isDayTradable to Yes."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.core.models import NseFlag
            NseFlag.set('isDayTradable', 'Yes', 'Resumed via Telegram bot')
            return {'success': True, 'message': 'Trading resumed'}
        except Exception as e:
            logger.error(f"Error resuming trading: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _trigger_close_all(self) -> dict:
        """Trigger close_trading_day task."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from celery import current_app
            from mcube_ai.celery import get_static_schedule

            static_schedule = get_static_schedule()
            task_config = static_schedule.get('close-trading-day')

            if not task_config:
                return {'success': False, 'error': 'close-trading-day task not found'}

            task_path = task_config.get('task')
            task_kwargs = task_config.get('kwargs', {}).copy()
            task_kwargs['_bypass_guard'] = True

            result = current_app.send_task(task_path, kwargs=task_kwargs)
            return {'success': True, 'task_id': result.id, 'message': 'Close trading day triggered'}
        except Exception as e:
            logger.error(f"Error triggering close all: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _refresh_breeze(self) -> dict:
        """Trigger breeze session refresh."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from celery import current_app
            from mcube_ai.celery import get_static_schedule

            static_schedule = get_static_schedule()
            task_config = static_schedule.get('refresh-breeze-session')

            if not task_config:
                return {'success': False, 'error': 'refresh-breeze-session task not found'}

            task_path = task_config.get('task')
            task_kwargs = task_config.get('kwargs', {}).copy()
            task_kwargs['_bypass_guard'] = True

            result = current_app.send_task(task_path, kwargs=task_kwargs)
            return {'success': True, 'task_id': result.id, 'message': 'Breeze refresh triggered'}
        except Exception as e:
            logger.error(f"Error refreshing breeze: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _run_futures_algo(self) -> dict:
        """Trigger futures algorithm task."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from celery import current_app
            from mcube_ai.celery import get_static_schedule

            static_schedule = get_static_schedule()
            task_config = static_schedule.get('execute-futures-algorithm')

            if not task_config:
                return {'success': False, 'error': 'execute-futures-algorithm task not found'}

            task_path = task_config.get('task')
            task_kwargs = task_config.get('kwargs', {}).copy()
            task_kwargs['_bypass_guard'] = True

            result = current_app.send_task(task_path, kwargs=task_kwargs)
            return {'success': True, 'task_id': result.id, 'message': 'Futures algorithm triggered'}
        except Exception as e:
            logger.error(f"Error running futures algo: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _force_data_sync(self) -> dict:
        """Trigger morning data sync task."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from celery import current_app
            from mcube_ai.celery import get_static_schedule

            static_schedule = get_static_schedule()
            task_config = static_schedule.get('morning-data-sync')

            if not task_config:
                return {'success': False, 'error': 'morning-data-sync task not found'}

            task_path = task_config.get('task')
            task_kwargs = task_config.get('kwargs', {}).copy()
            task_kwargs['_bypass_guard'] = True

            result = current_app.send_task(task_path, kwargs=task_kwargs)
            return {'success': True, 'task_id': result.id, 'message': 'Data sync triggered'}
        except Exception as e:
            logger.error(f"Error forcing data sync: {e}")
            return {'success': False, 'error': str(e)}
