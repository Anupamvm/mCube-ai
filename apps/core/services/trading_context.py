"""
Trading Context Service

Provides a unified context for Celery tasks and web app views.
Consolidates common operations to ensure web app and tasks use the SAME APIs.

USAGE:
    from apps.core.services.trading_context import TradingContext

    # In a Celery task:
    ctx = TradingContext()
    if not ctx.is_trading_allowed():
        return {'success': False, 'reason': ctx.skip_reason}

    kotak_account = ctx.get_kotak_account()
    icici_account = ctx.get_icici_account()
    config = ctx.config  # TradingCoreConfig instance

This eliminates duplicate code across:
- apps/strategies/tasks.py
- apps/positions/tasks.py
- apps/trading/views.py
- apps/core/views.py
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Optional, Dict
from django.utils import timezone
from django.db.models import QuerySet

logger = logging.getLogger(__name__)


class TradingContext:
    """
    Unified context for trading operations.

    Provides:
    - Account retrieval (Kotak, ICICI)
    - Trading day validation (holidays, weekends, setup)
    - Config access (TradingCoreConfig)
    - Position queries
    - Notification helpers
    """

    def __init__(self, task_name: str = None, task_logger=None):
        """
        Initialize trading context.

        Args:
            task_name: Name of the calling task (for logging)
            task_logger: TaskLogger instance (optional)
        """
        self.task_name = task_name or 'unknown'
        self.task_logger = task_logger
        self._config = None
        self._kotak_account = None
        self._icici_account = None
        self._trading_day_setup = None
        self._skip_reason = None
        self.today = date.today()
        self.now = timezone.now()

    # =========================================================================
    # CONFIGURATION ACCESS
    # =========================================================================

    @property
    def config(self):
        """
        Get TradingCoreConfig instance (lazy-loaded, cached).

        Returns:
            TradingCoreConfig: The singleton config instance
        """
        if self._config is None:
            from apps.core.models import TradingCoreConfig
            self._config = TradingCoreConfig.get_instance()
        return self._config

    @property
    def skip_reason(self) -> Optional[str]:
        """Get the reason why trading was skipped (if applicable)."""
        return self._skip_reason

    # =========================================================================
    # ACCOUNT RETRIEVAL
    # =========================================================================

    def get_kotak_account(self):
        """
        Get active Kotak Neo account.

        Returns:
            BrokerAccount or None: Active Kotak account
        """
        if self._kotak_account is None:
            from apps.accounts.models import BrokerAccount
            self._kotak_account = BrokerAccount.objects.filter(
                broker='KOTAK',
                is_active=True
            ).first()
        return self._kotak_account

    def get_icici_account(self):
        """
        Get active ICICI Breeze account.

        Returns:
            BrokerAccount or None: Active ICICI account
        """
        if self._icici_account is None:
            from apps.accounts.models import BrokerAccount
            self._icici_account = BrokerAccount.objects.filter(
                broker='ICICI',
                is_active=True
            ).first()
        return self._icici_account

    def get_account(self, broker: str):
        """
        Get active account by broker name.

        Args:
            broker: 'KOTAK' or 'ICICI'

        Returns:
            BrokerAccount or None
        """
        if broker.upper() == 'KOTAK':
            return self.get_kotak_account()
        elif broker.upper() == 'ICICI':
            return self.get_icici_account()
        else:
            from apps.accounts.models import BrokerAccount
            return BrokerAccount.objects.filter(
                broker=broker.upper(),
                is_active=True
            ).first()

    # =========================================================================
    # TRADING DAY VALIDATION
    # =========================================================================

    def is_trading_allowed(self, check_futures: bool = False, check_options: bool = False) -> bool:
        """
        Check if trading is allowed today.

        Validates:
        1. Not a weekend (Saturday/Sunday)
        2. Not a market holiday (NseFlag.is_holiday)
        3. TradingDaySetup.is_tradable (if exists)
        4. TradingCoreConfig futures/options enabled (if check_* is True)

        Args:
            check_futures: Also check if futures trading enabled
            check_options: Also check if options trading enabled

        Returns:
            bool: True if trading allowed
        """
        from apps.core.models import NseFlag

        # Check weekend
        if self.today.weekday() >= 5:
            self._skip_reason = f"Weekend ({self.today.strftime('%A')})"
            self._log('skipped', self._skip_reason)
            return False

        # Check market holiday
        if NseFlag.get_bool('is_holiday', default=False):
            self._skip_reason = "Market holiday"
            self._log('skipped', self._skip_reason)
            return False

        # Check TradingDaySetup
        setup = self.get_trading_day_setup()
        if setup and not setup.is_tradable:
            self._skip_reason = setup.tradable_reason or "Day not tradable"
            self._log('skipped', self._skip_reason)
            return False

        # Check config-level trading flags
        if check_futures and not self.config.is_futures_enabled():
            self._skip_reason = "Futures trading disabled in Core Config"
            self._log('skipped', self._skip_reason)
            return False

        if check_options and not self.config.is_options_enabled():
            self._skip_reason = "Options trading disabled in Core Config"
            self._log('skipped', self._skip_reason)
            return False

        return True

    def get_trading_day_setup(self):
        """
        Get TradingDaySetup for today (lazy-loaded, cached).

        Returns:
            TradingDaySetup or None
        """
        if self._trading_day_setup is None:
            from apps.strategies.models import TradingDaySetup
            try:
                self._trading_day_setup = TradingDaySetup.objects.get(
                    trading_date=self.today
                )
            except TradingDaySetup.DoesNotExist:
                self._trading_day_setup = None
        return self._trading_day_setup

    def is_market_hours(self, start_hour: int = 9, start_minute: int = 15,
                        end_hour: int = 15, end_minute: int = 30) -> bool:
        """
        Check if current time is within market hours.

        Args:
            start_hour: Market open hour (default 9)
            start_minute: Market open minute (default 15)
            end_hour: Market close hour (default 15)
            end_minute: Market close minute (default 30)

        Returns:
            bool: True if within market hours
        """
        now = self.now
        market_open = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        market_close = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        return market_open <= now <= market_close

    def is_within_time_window(self, start_hour: int, start_minute: int,
                               end_hour: int, end_minute: int) -> bool:
        """
        Check if current time is within a specific window.

        Args:
            start_hour: Window start hour
            start_minute: Window start minute
            end_hour: Window end hour
            end_minute: Window end minute

        Returns:
            bool: True if within window
        """
        now = self.now
        window_start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        window_end = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        return window_start <= now <= window_end

    # =========================================================================
    # POSITION QUERIES
    # =========================================================================

    def get_active_positions(self, account=None, strategy_type: str = None) -> QuerySet:
        """
        Get active positions with optional filters.

        Args:
            account: BrokerAccount to filter by (optional)
            strategy_type: Strategy type to filter by (optional)

        Returns:
            QuerySet: Active positions
        """
        from apps.positions.models import Position

        qs = Position.objects.filter(status='ACTIVE')

        if account:
            qs = qs.filter(account=account)

        if strategy_type:
            qs = qs.filter(strategy_type=strategy_type)

        return qs

    def get_active_options_positions(self) -> QuerySet:
        """
        Get all active options (strangle/iron condor) positions.

        Returns:
            QuerySet: Active options positions
        """
        return self.get_active_positions().filter(
            strategy_type__in=['WEEKLY_NIFTY_STRANGLE', 'IRON_CONDOR', 'BROKEN_IRON_CONDOR']
        )

    def get_active_futures_positions(self) -> QuerySet:
        """
        Get all active futures positions.

        Returns:
            QuerySet: Active futures positions
        """
        return self.get_active_positions().filter(
            strategy_type__in=['LLM_VALIDATED_FUTURES', 'FUTURES']
        )

    def has_active_position(self, account) -> bool:
        """
        Check if account has any active position (ONE POSITION RULE).

        Args:
            account: BrokerAccount to check

        Returns:
            bool: True if account has active position
        """
        from apps.positions.models import Position
        return Position.get_active_position(account) is not None

    # =========================================================================
    # POSITION SIZING HELPERS
    # =========================================================================

    def get_lots_for_trade(self, trade_type: str,
                           available_margin: Decimal = None,
                           margin_per_lot: Decimal = None) -> int:
        """
        Get number of lots based on position sizing mode.

        Delegates to TradingCoreConfig.get_lots_for_trade().

        Args:
            trade_type: 'OPTIONS' or 'FUTURES'
            available_margin: Available margin (for AUTO mode)
            margin_per_lot: Margin per lot (for AUTO mode)

        Returns:
            int: Number of lots
        """
        return self.config.get_lots_for_trade(
            trade_type=trade_type,
            available_margin=available_margin,
            margin_per_lot=margin_per_lot
        )

    def requires_confirmation(self, action_type: str) -> bool:
        """
        Check if action requires user confirmation.

        Delegates to TradingCoreConfig.requires_confirmation().

        Args:
            action_type: 'ENTRY', 'EXIT', 'AVERAGING', etc.

        Returns:
            bool: True if confirmation required
        """
        return self.config.requires_confirmation(action_type)

    def is_simulated(self) -> bool:
        """Check if system is in simulated (paper trade) mode."""
        return self.config.is_simulated()

    def is_autonomous(self) -> bool:
        """Check if system is in autonomous mode."""
        return self.config.is_autonomous()

    # =========================================================================
    # NOTIFICATION HELPERS
    # =========================================================================

    def notify(self, message: str, notification_type: str = 'INFO'):
        """
        Send Telegram notification.

        Args:
            message: Message text
            notification_type: 'SUCCESS', 'INFO', 'WARNING', 'ERROR'
        """
        from apps.alerts.services.telegram_client import send_telegram_notification
        send_telegram_notification(message, notification_type=notification_type)

    def notify_success(self, message: str):
        """Send success notification."""
        self.notify(message, notification_type='SUCCESS')

    def notify_error(self, message: str):
        """Send error notification."""
        self.notify(message, notification_type='ERROR')

    def notify_warning(self, message: str):
        """Send warning notification."""
        self.notify(message, notification_type='WARNING')

    # =========================================================================
    # RESULT BUILDERS
    # =========================================================================

    def skip_result(self, reason: str = None) -> Dict:
        """
        Build a standard skip result.

        Args:
            reason: Skip reason (uses self.skip_reason if not provided)

        Returns:
            dict: {'success': True, 'skipped': True, 'reason': str}
        """
        return {
            'success': True,
            'skipped': True,
            'reason': reason or self._skip_reason or 'Unknown'
        }

    def error_result(self, error: str) -> Dict:
        """
        Build a standard error result.

        Args:
            error: Error message

        Returns:
            dict: {'success': False, 'error': str}
        """
        return {'success': False, 'error': str(error)}

    def success_result(self, **kwargs) -> Dict:
        """
        Build a standard success result.

        Args:
            **kwargs: Additional result fields

        Returns:
            dict: {'success': True, ...kwargs}
        """
        return {'success': True, **kwargs}

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _log(self, level: str, message: str, **kwargs):
        """Log message using task_logger if available, else standard logger."""
        if self.task_logger:
            log_method = getattr(self.task_logger, level, self.task_logger.info)
            log_method(level, message, context=kwargs if kwargs else None)
        else:
            log_level = logging.INFO if level in ['info', 'skipped'] else logging.WARNING
            logger.log(log_level, f"[{self.task_name}] {message}")


# Convenience function for quick context creation
def get_trading_context(task_name: str = None, task_logger=None) -> TradingContext:
    """
    Get a TradingContext instance.

    Args:
        task_name: Name of the calling task
        task_logger: TaskLogger instance

    Returns:
        TradingContext: Configured context
    """
    return TradingContext(task_name=task_name, task_logger=task_logger)
