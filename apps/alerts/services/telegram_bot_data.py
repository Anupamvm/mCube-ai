"""
Telegram Bot Data Mixin

Provides @sync_to_async data-fetching methods for the Telegram bot.
All methods use close_old_connections() for thread safety.
"""

import logging
from datetime import date, timedelta
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
        """
        Trigger breeze session refresh on-demand (via Telegram quick action).

        Uses BreezeSessionManager directly instead of dispatching a Celery task.
        The scheduled refresh-breeze-session task was removed — all Breeze
        logins are now on-demand only, limited to one auto-login per day.
        """
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.brokers.services.breeze_session import BreezeSessionManager

            manager = BreezeSessionManager()
            is_valid, msg = manager.is_session_valid()

            if is_valid:
                return {'success': True, 'message': f'Breeze session already valid: {msg}'}

            # Check market hours and daily limit before attempting refresh
            from apps.brokers.utils.auth_manager import can_attempt_auto_login
            can_login, reason = can_attempt_auto_login('breeze')
            if not can_login:
                return {'success': False, 'error': f'Breeze login blocked: {reason}'}

            # Attempt refresh (subject to daily auto-login limit)
            success, refresh_msg = manager.refresh_session()
            if success:
                return {'success': True, 'message': f'Breeze session refreshed: {refresh_msg}'}
            else:
                return {'success': False, 'error': f'Refresh failed: {refresh_msg}'}
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

    # =========================================================================
    # ALGORITHM DEPENDENCY MANAGEMENT
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_algorithm_status(self) -> dict:
        """Return {algo_key: {is_active, own_count, enabled_count}} for each algorithm.

        An algorithm is "active" only when ALL its own_tasks are enabled.
        """
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import ALGORITHM_TASK_GROUPS

        try:
            result = {}
            for algo_key, group in ALGORITHM_TASK_GROUPS.items():
                own_tasks = group['own_tasks']
                enabled_count = sum(
                    1 for t in own_tasks if CeleryTaskState.is_task_enabled(t)
                )
                result[algo_key] = {
                    'is_active': enabled_count == len(own_tasks),
                    'own_count': len(own_tasks),
                    'enabled_count': enabled_count,
                    'display_name': group['display_name'],
                    'emoji': group['emoji'],
                }
            return result
        except Exception as e:
            logger.error(f"Error fetching algorithm status: {e}")
            return {}

    @sync_to_async(thread_sensitive=False)
    def _get_algorithm_enable_preview(self, algo_key: str) -> dict:
        """Return grouped preview of tasks that will be enabled for an algorithm."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import ALGORITHM_TASK_GROUPS, TASK_DEFAULT_CONFIG

        try:
            group = ALGORITHM_TASK_GROUPS.get(algo_key)
            if not group:
                return {'error': f'Unknown algorithm: {algo_key}'}

            def _task_info(task_key):
                config = TASK_DEFAULT_CONFIG.get(task_key, {})
                sched_type = config.get('schedule_type', 'crontab')
                if sched_type == 'crontab':
                    h = config.get('default_hour', 0)
                    m = config.get('default_minute', 0)
                    sched = f"{h:02d}:{m:02d}"
                elif sched_type == 'recurring':
                    sh = config.get('default_recurring_start_hour', 0)
                    sm = config.get('default_recurring_start_minute', 0)
                    eh = config.get('default_recurring_end_hour', 0)
                    em = config.get('default_recurring_end_minute', 0)
                    iv = config.get('default_recurring_interval_minutes', 5)
                    sched = f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d} q{iv}m"
                elif sched_type == 'interval':
                    secs = config.get('default_interval_seconds', 30)
                    sched = f"q{secs}s"
                else:
                    sched = ''
                return {
                    'key': task_key,
                    'name': config.get('display_name', task_key),
                    'schedule': sched,
                    'is_enabled': CeleryTaskState.is_task_enabled(task_key),
                }

            # Find which other algos share tasks
            other_algos = [
                ALGORITHM_TASK_GROUPS[k]['display_name']
                for k in ALGORITHM_TASK_GROUPS if k != algo_key
            ]

            return {
                'algo_key': algo_key,
                'display_name': group['display_name'],
                'emoji': group['emoji'],
                'own_tasks': [_task_info(t) for t in group['own_tasks']],
                'shared_tasks': [_task_info(t) for t in group['shared_tasks']],
                'monitoring_tasks': [_task_info(t) for t in group['monitoring_tasks']],
                'shared_with': ', '.join(other_algos),
            }
        except Exception as e:
            logger.error(f"Error building enable preview for {algo_key}: {e}")
            return {'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _get_algorithm_disable_preview(self, algo_key: str) -> dict:
        """Return smart disable preview: tasks to disable vs tasks to keep."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import ALGORITHM_TASK_GROUPS, TASK_DEFAULT_CONFIG

        try:
            group = ALGORITHM_TASK_GROUPS.get(algo_key)
            if not group:
                return {'error': f'Unknown algorithm: {algo_key}'}

            def _task_info(task_key):
                config = TASK_DEFAULT_CONFIG.get(task_key, {})
                return {
                    'key': task_key,
                    'name': config.get('display_name', task_key),
                }

            # Check which OTHER algorithms are active (all own_tasks enabled)
            active_others = []
            for other_key, other_group in ALGORITHM_TASK_GROUPS.items():
                if other_key == algo_key:
                    continue
                all_own_enabled = all(
                    CeleryTaskState.is_task_enabled(t) for t in other_group['own_tasks']
                )
                if all_own_enabled:
                    active_others.append(other_group['display_name'])

            # Own tasks: always disable
            tasks_to_disable = [_task_info(t) for t in group['own_tasks']]

            # Shared + monitoring: only disable if no other algo is active
            tasks_to_keep = []
            if active_others:
                reason = f"Needed by {', '.join(active_others)}"
                for t in group['shared_tasks'] + group['monitoring_tasks']:
                    tasks_to_keep.append({**_task_info(t), 'reason': reason})
            else:
                for t in group['shared_tasks'] + group['monitoring_tasks']:
                    tasks_to_disable.append(_task_info(t))

            return {
                'algo_key': algo_key,
                'display_name': group['display_name'],
                'emoji': group['emoji'],
                'tasks_to_disable': tasks_to_disable,
                'tasks_to_keep': tasks_to_keep,
                'active_others': active_others,
            }
        except Exception as e:
            logger.error(f"Error building disable preview for {algo_key}: {e}")
            return {'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _enable_algorithm(self, algo_key: str) -> dict:
        """Enable all tasks (own + shared + monitoring) for an algorithm."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import ALGORITHM_TASK_GROUPS, TASK_DEFAULT_CONFIG

        try:
            group = ALGORITHM_TASK_GROUPS.get(algo_key)
            if not group:
                return {'success': False, 'error': f'Unknown algorithm: {algo_key}'}

            all_tasks = group['own_tasks'] + group['shared_tasks'] + group['monitoring_tasks']
            enabled_count = 0

            # Resolve task paths from static schedule once
            task_paths = {}
            try:
                from mcube_ai.celery import get_static_schedule
                sched = get_static_schedule()
                task_paths = {k: v.get('task', '') for k, v in sched.items()}
            except Exception:
                pass

            for task_key in all_tasks:
                config = TASK_DEFAULT_CONFIG.get(task_key, {})
                CeleryTaskState.set_task_state(
                    task_key=task_key,
                    enabled=True,
                    task_path=task_paths.get(task_key, ''),
                    display_name=config.get('display_name', task_key.replace('-', ' ').title()),
                    user='telegram_bot',
                )
                enabled_count += 1

            # Restart beat once
            from apps.core.views import ensure_celery_running
            ensure_celery_running()

            return {
                'success': True,
                'message': f"{group['display_name']} enabled ({enabled_count} tasks)",
                'count': enabled_count,
            }
        except Exception as e:
            logger.error(f"Error enabling algorithm {algo_key}: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _disable_algorithm(self, algo_key: str) -> dict:
        """Disable algorithm tasks. Shared/monitoring tasks kept if another algo is active."""
        from django.db import close_old_connections
        close_old_connections()

        from apps.core.models import CeleryTaskState
        from apps.core.task_config import ALGORITHM_TASK_GROUPS, TASK_DEFAULT_CONFIG

        try:
            group = ALGORITHM_TASK_GROUPS.get(algo_key)
            if not group:
                return {'success': False, 'error': f'Unknown algorithm: {algo_key}'}

            # Check which OTHER algorithms are active
            active_others = []
            for other_key, other_group in ALGORITHM_TASK_GROUPS.items():
                if other_key == algo_key:
                    continue
                all_own_enabled = all(
                    CeleryTaskState.is_task_enabled(t) for t in other_group['own_tasks']
                )
                if all_own_enabled:
                    active_others.append(other_group['display_name'])

            # Always disable own tasks
            tasks_to_disable = list(group['own_tasks'])

            # Only disable shared/monitoring if no other algo is active
            if not active_others:
                tasks_to_disable += group['shared_tasks'] + group['monitoring_tasks']

            kept_count = 0
            if active_others:
                kept_count = len(group['shared_tasks']) + len(group['monitoring_tasks'])

            # Resolve task paths from static schedule once
            task_paths = {}
            try:
                from mcube_ai.celery import get_static_schedule
                sched = get_static_schedule()
                task_paths = {k: v.get('task', '') for k, v in sched.items()}
            except Exception:
                pass

            disabled_count = 0
            for task_key in tasks_to_disable:
                config = TASK_DEFAULT_CONFIG.get(task_key, {})
                CeleryTaskState.set_task_state(
                    task_key=task_key,
                    enabled=False,
                    task_path=task_paths.get(task_key, ''),
                    display_name=config.get('display_name', task_key.replace('-', ' ').title()),
                    user='telegram_bot',
                )
                disabled_count += 1

            # Restart beat once
            from apps.core.views import ensure_celery_running
            ensure_celery_running()

            msg = f"{group['display_name']} disabled ({disabled_count} tasks)"
            if kept_count:
                msg += f" | {kept_count} kept ({', '.join(active_others)})"

            return {
                'success': True,
                'message': msg,
                'disabled': disabled_count,
                'kept': kept_count,
            }
        except Exception as e:
            logger.error(f"Error disabling algorithm {algo_key}: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # ORDER BOOK DATA
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_breeze_orders(self) -> dict:
        """Get today's orders from ICICI Breeze."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.brokers.services.breeze_session import get_breeze_client
            breeze = get_breeze_client()
            if not breeze:
                return {'success': False, 'orders': [], 'error': 'Breeze session not available'}

            from apps.brokers.integrations.breeze import get_order_list
            today_str = date.today().strftime('%Y-%m-%d')
            result = get_order_list(from_date=today_str, to_date=today_str)

            if result and result.get('success'):
                return {'success': True, 'orders': result.get('orders', [])}
            return {'success': False, 'orders': [], 'error': result.get('error', 'Failed')}
        except Exception as e:
            logger.error(f"Error fetching Breeze orders: {e}")
            return {'success': False, 'orders': [], 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _get_kotak_orders(self) -> dict:
        """Get today's orders from Kotak Neo."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from tools.neo import NeoAPI
            neo = NeoAPI()
            orders = neo.get_orders()
            if orders is not None:
                return {'success': True, 'orders': orders if isinstance(orders, list) else []}
            return {'success': False, 'orders': [], 'error': 'No orders data'}
        except Exception as e:
            logger.error(f"Error fetching Kotak orders: {e}")
            return {'success': False, 'orders': [], 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _cancel_kotak_order(self, order_id: str) -> dict:
        """Cancel a Kotak Neo order."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from tools.neo import NeoAPI
            neo = NeoAPI()
            success = neo.cancel_order(order_id)
            if success:
                return {'success': True, 'message': f'Order {order_id} cancelled'}
            return {'success': False, 'error': 'Cancellation failed'}
        except Exception as e:
            logger.error(f"Error cancelling Kotak order {order_id}: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # MARGIN / LIMITS DATA
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_breeze_margin(self) -> dict:
        """Get margin data from ICICI Breeze."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.brokers.services.breeze_session import get_breeze_client
            breeze = get_breeze_client()
            if not breeze:
                return {'success': False, 'error': 'Breeze session not available'}

            from apps.brokers.integrations.breeze import get_nfo_margin
            margin = get_nfo_margin()
            if margin:
                cash_limit = float(margin.get('cash_limit', 0) or 0)
                blocked = float(margin.get('block_by_trade', 0) or 0)
                available = cash_limit - blocked
                return {
                    'success': True,
                    'cash_limit': cash_limit,
                    'blocked': blocked,
                    'available': available,
                    'pct': round(available / cash_limit * 100, 1) if cash_limit > 0 else 0,
                }
            return {'success': False, 'error': 'No margin data'}
        except Exception as e:
            logger.error(f"Error fetching Breeze margin: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _get_kotak_margin(self) -> dict:
        """Get margin data from Kotak Neo."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from tools.neo import NeoAPI
            neo = NeoAPI()
            margin = neo.get_margin()
            if margin:
                total = float(margin.get('total_margin', 0) or 0)
                used = float(margin.get('used_margin', 0) or 0)
                available = float(margin.get('available_margin', 0) or 0)
                return {
                    'success': True,
                    'total': total,
                    'used': used,
                    'available': available,
                    'pct': round(available / total * 100, 1) if total > 0 else 0,
                }
            return {'success': False, 'error': 'No margin data'}
        except Exception as e:
            logger.error(f"Error fetching Kotak margin: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _get_margin_summary_for_header(self) -> dict:
        """Get a compact margin summary for the main menu header."""
        from django.db import close_old_connections
        close_old_connections()

        result = {'breeze_free': None, 'kotak_free': None}

        try:
            # Breeze
            try:
                from apps.brokers.services.breeze_session import get_breeze_client
                breeze = get_breeze_client()
                if breeze:
                    from apps.brokers.integrations.breeze import get_nfo_margin
                    margin = get_nfo_margin()
                    if margin:
                        cash = float(margin.get('cash_limit', 0) or 0)
                        blocked = float(margin.get('block_by_trade', 0) or 0)
                        result['breeze_free'] = cash - blocked
            except Exception as e:
                logger.debug(f"Breeze margin header: {e}")

            # Kotak
            try:
                from tools.neo import NeoAPI
                neo = NeoAPI()
                margin = neo.get_margin()
                if margin:
                    result['kotak_free'] = float(margin.get('available_margin', 0) or 0)
            except Exception as e:
                logger.debug(f"Kotak margin header: {e}")

        except Exception as e:
            logger.error(f"Error fetching margin summary: {e}")

        return result

    # =========================================================================
    # POSITION SL/TARGET MODIFICATION
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_position_detail(self, position_id: int) -> dict:
        """Get position detail for SL/Target modification."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.positions.models import Position
            pos = Position.objects.get(id=position_id)
            return {
                'success': True,
                'id': pos.id,
                'instrument': pos.instrument,
                'direction': pos.direction,
                'entry_price': float(pos.entry_price),
                'current_price': float(pos.current_price) if pos.current_price else None,
                'stop_loss': float(pos.stop_loss) if pos.stop_loss else None,
                'target': float(pos.target) if pos.target else None,
                'quantity': pos.quantity,
                'lot_size': pos.lot_size,
                'unrealized_pnl': float(pos.unrealized_pnl) if pos.unrealized_pnl else 0,
            }
        except Exception as e:
            logger.error(f"Error fetching position {position_id}: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _update_position_sl(self, position_id: int, new_sl: float) -> dict:
        """Update stop loss for a position."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.positions.models import Position
            pos = Position.objects.get(id=position_id)
            old_sl = float(pos.stop_loss) if pos.stop_loss else None
            pos.stop_loss = Decimal(str(new_sl))
            pos.save(update_fields=['stop_loss'])
            return {
                'success': True,
                'old_sl': old_sl,
                'new_sl': new_sl,
                'instrument': pos.instrument,
            }
        except Exception as e:
            logger.error(f"Error updating SL for position {position_id}: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _update_position_target(self, position_id: int, new_target: float) -> dict:
        """Update target for a position."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.positions.models import Position
            pos = Position.objects.get(id=position_id)
            old_target = float(pos.target) if pos.target else None
            pos.target = Decimal(str(new_target))
            pos.save(update_fields=['target'])
            return {
                'success': True,
                'old_target': old_target,
                'new_target': new_target,
                'instrument': pos.instrument,
            }
        except Exception as e:
            logger.error(f"Error updating target for position {position_id}: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # TRADE HISTORY
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_trade_history(self, count: int = 10) -> dict:
        """Get recent closed trades from TakenTrade model."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.trading.models import TakenTrade
            trades = list(
                TakenTrade.objects
                .filter(status='CLOSED')
                .order_by('-exit_time', '-id')[:count]
                .values(
                    'id', 'instrument', 'trade_type', 'direction',
                    'realized_pnl', 'net_pnl', 'outcome', 'exit_time',
                    'entry_price', 'exit_price', 'quantity',
                )
            )

            # Summary stats
            all_closed = TakenTrade.objects.filter(status='CLOSED')
            total_count = all_closed.count()
            wins = all_closed.filter(outcome='PROFIT').count()
            losses = all_closed.filter(outcome='LOSS').count()

            total_pnl = sum(
                float(t.get('net_pnl') or t.get('realized_pnl') or 0)
                for t in trades
            )

            return {
                'success': True,
                'trades': trades,
                'total_count': total_count,
                'wins': wins,
                'losses': losses,
                'win_rate': round(wins / total_count * 100, 1) if total_count > 0 else 0,
                'total_pnl': total_pnl,
            }
        except Exception as e:
            logger.error(f"Error fetching trade history: {e}")
            return {'success': False, 'trades': [], 'error': str(e)}

    # =========================================================================
    # BROKER SESSION STATUS & LOGIN
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_broker_session_status(self) -> dict:
        """Check session validity for both brokers."""
        from django.db import close_old_connections
        close_old_connections()

        result = {
            'breeze_valid': False,
            'breeze_since': None,
            'kotak_valid': False,
            'kotak_since': None,
        }

        try:
            from apps.core.models import NseFlag

            # Breeze
            breeze_token = NseFlag.get('breeze_session_token', '')
            result['breeze_valid'] = bool(breeze_token)
            breeze_time = NseFlag.get('breeze_session_time', '')
            if breeze_time:
                result['breeze_since'] = breeze_time

            # Kotak
            try:
                from apps.core.models import CredentialStore
                creds = CredentialStore.objects.filter(service='kotak_neo').first()
                if creds and creds.neo_base_url:
                    result['kotak_valid'] = True
                    if creds.auto_login_date:
                        result['kotak_since'] = str(creds.auto_login_date)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error checking broker sessions: {e}")

        return result

    @sync_to_async(thread_sensitive=False)
    def _trigger_kotak_login(self) -> dict:
        """Trigger Kotak Neo login (TOTP + MPIN, no user input needed)."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from tools.neo import NeoAPI
            neo = NeoAPI()
            success = neo.login()
            if success:
                return {'success': True, 'message': 'Kotak Neo login successful'}
            return {'success': False, 'error': 'Login failed'}
        except Exception as e:
            logger.error(f"Error triggering Kotak login: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _trigger_breeze_login(self) -> dict:
        """Trigger Breeze login — uses the same auto_login_breeze path as the management command."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.brokers.services.breeze_auto_login import auto_login_breeze
            from apps.brokers.utils.auth_manager import reset_auto_login_status

            # Reset any previous failed/in_progress state so a manual trigger is never blocked.
            reset_auto_login_status('breeze')

            success, message = auto_login_breeze(headless=True, task_name="Telegram manual login")
            if success:
                return {'success': True, 'message': message}
            return {'success': False, 'error': message}
        except Exception as e:
            logger.error(f"Error triggering Breeze login: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # ANALYTICS / PERFORMANCE
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_performance_summary(self, period: str = 'FY') -> dict:
        """Get performance analytics summary."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.trading.models import TakenTrade
            from django.db.models import Sum, Q, Avg, Max, Min

            # Build date filter
            today = date.today()
            if period == 'week':
                start_date = today - timedelta(days=today.weekday())
            elif period == 'month':
                start_date = today.replace(day=1)
            else:  # FY
                if today.month >= 4:
                    start_date = today.replace(month=4, day=1)
                else:
                    start_date = today.replace(year=today.year - 1, month=4, day=1)

            qs = TakenTrade.objects.filter(
                status='CLOSED',
                exit_time__date__gte=start_date,
            )

            total = qs.count()
            if total == 0:
                return {
                    'success': True,
                    'period': period,
                    'total_trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                }

            wins = qs.filter(outcome='PROFIT').count()
            losses = qs.filter(outcome='LOSS').count()

            agg = qs.aggregate(
                total_pnl=Sum('net_pnl'),
                avg_win=Avg('net_pnl', filter=Q(outcome='PROFIT')),
                avg_loss=Avg('net_pnl', filter=Q(outcome='LOSS')),
                best_trade=Max('net_pnl'),
                worst_trade=Min('net_pnl'),
            )

            # Strategy breakdown
            futures_qs = qs.filter(trade_type='FUTURES')
            options_qs = qs.filter(trade_type='OPTIONS')

            futures_pnl = futures_qs.aggregate(total=Sum('net_pnl'))['total'] or 0
            options_pnl = options_qs.aggregate(total=Sum('net_pnl'))['total'] or 0

            # Best/worst trade details
            best_trade_obj = qs.order_by('-net_pnl').first()
            worst_trade_obj = qs.order_by('net_pnl').first()

            return {
                'success': True,
                'period': period,
                'total_trades': total,
                'wins': wins,
                'losses': losses,
                'win_rate': round(wins / total * 100, 1) if total > 0 else 0,
                'total_pnl': float(agg['total_pnl'] or 0),
                'avg_win': float(agg['avg_win'] or 0),
                'avg_loss': float(agg['avg_loss'] or 0),
                'best_trade': float(agg['best_trade'] or 0),
                'worst_trade': float(agg['worst_trade'] or 0),
                'best_trade_name': best_trade_obj.instrument if best_trade_obj else '',
                'worst_trade_name': worst_trade_obj.instrument if worst_trade_obj else '',
                'futures_count': futures_qs.count(),
                'futures_pnl': float(futures_pnl),
                'options_count': options_qs.count(),
                'options_pnl': float(options_pnl),
            }
        except Exception as e:
            logger.error(f"Error fetching performance summary: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # MARKET SENTIMENT / NEWS
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_market_sentiment(self) -> dict:
        """Get market sentiment from analyzed news articles."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.data.models import NewsArticle
            today = date.today()

            articles = list(
                NewsArticle.objects
                .filter(published_at__date=today)
                .order_by('-published_at')[:10]
                .values('title', 'sentiment_score', 'published_at')
            )

            if not articles:
                return {
                    'success': True,
                    'overall_score': 0,
                    'overall_label': 'NO DATA',
                    'articles': [],
                    'blocking_news': False,
                }

            scores = [a['sentiment_score'] for a in articles if a.get('sentiment_score') is not None]
            avg_score = sum(scores) / len(scores) if scores else 0

            if avg_score > 0.3:
                label = 'BULLISH'
            elif avg_score < -0.3:
                label = 'BEARISH'
            else:
                label = 'NEUTRAL'

            return {
                'success': True,
                'overall_score': round(avg_score, 2),
                'overall_label': label,
                'articles': articles[:5],
                'blocking_news': avg_score < -0.6,
            }
        except Exception as e:
            logger.error(f"Error fetching market sentiment: {e}")
            return {'success': True, 'overall_score': 0, 'overall_label': 'N/A', 'articles': [], 'blocking_news': False}

    # =========================================================================
    # TASK SCHEDULE EDITING
    # =========================================================================

    @sync_to_async(thread_sensitive=False)
    def _get_task_schedule_detail(self, task_key: str) -> dict:
        """Get current schedule details for a task."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.core.models import CeleryTaskState
            from apps.core.task_config import TASK_DEFAULT_CONFIG

            config = TASK_DEFAULT_CONFIG.get(task_key, {})
            state = CeleryTaskState.objects.filter(task_key=task_key).first()

            sched_type = config.get('schedule_type', 'crontab')

            current_hour = config.get('default_hour', 0)
            current_minute = config.get('default_minute', 0)

            if state and state.use_custom_schedule:
                if state.custom_hour is not None:
                    current_hour = state.custom_hour
                if state.custom_minute is not None:
                    current_minute = state.custom_minute

            return {
                'success': True,
                'task_key': task_key,
                'display_name': config.get('display_name', task_key),
                'schedule_type': sched_type,
                'current_hour': current_hour,
                'current_minute': current_minute,
                'default_hour': config.get('default_hour', 0),
                'default_minute': config.get('default_minute', 0),
            }
        except Exception as e:
            logger.error(f"Error getting schedule for {task_key}: {e}")
            return {'success': False, 'error': str(e)}

    @sync_to_async(thread_sensitive=False)
    def _update_task_schedule(self, task_key: str, hour: int, minute: int) -> dict:
        """Update a task's schedule and restart beat."""
        from django.db import close_old_connections
        close_old_connections()

        try:
            from apps.core.models import CeleryTaskState
            from apps.core.task_config import TASK_DEFAULT_CONFIG

            config = TASK_DEFAULT_CONFIG.get(task_key, {})

            state, _ = CeleryTaskState.objects.get_or_create(
                task_key=task_key,
                defaults={
                    'display_name': config.get('display_name', task_key),
                    'is_enabled': True,
                }
            )
            state.custom_hour = hour
            state.custom_minute = minute
            state.use_custom_schedule = True
            state.save(update_fields=['custom_hour', 'custom_minute', 'use_custom_schedule'])

            # Restart beat
            from apps.core.views import ensure_celery_running
            ensure_celery_running()

            return {
                'success': True,
                'message': f'{config.get("display_name", task_key)} rescheduled to {hour:02d}:{minute:02d}',
            }
        except Exception as e:
            logger.error(f"Error updating schedule for {task_key}: {e}")
            return {'success': False, 'error': str(e)}
