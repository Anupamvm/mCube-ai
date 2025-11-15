"""
Alert Manager Service

This service handles creating and dispatching alerts across multiple channels.

Features:
- Create alerts for different event types
- Dispatch to Telegram, Email, SMS
- Track delivery status
- Retry failed deliveries
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.utils import timezone

from apps.alerts.models import Alert, AlertLog
from apps.alerts.services.telegram_client import get_telegram_client
from apps.accounts.models import BrokerAccount
from apps.positions.models import Position

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Manages alert creation and delivery across multiple channels

    Supported Alert Types:
        - POSITION_ENTERED
        - POSITION_CLOSED
        - SL_HIT
        - TARGET_HIT
        - DELTA_ALERT
        - CIRCUIT_BREAKER
        - RISK_WARNING
        - DAILY_LOSS_LIMIT
        - WEEKLY_LOSS_LIMIT
        - EXPIRY_WARNING
        - SYSTEM_ERROR
    """

    def __init__(self):
        """Initialize alert manager"""
        self.telegram_client = get_telegram_client()

    def create_position_alert(
        self,
        position: Position,
        alert_type: str,
        priority: str = 'MEDIUM',
        message: str = '',
        send_telegram: bool = True,
        metadata: Optional[Dict] = None
    ) -> Alert:
        """
        Create and send position-related alert

        Args:
            position: Position instance
            alert_type: Type of alert
            priority: Alert priority (CRITICAL, HIGH, MEDIUM, LOW, INFO)
            message: Custom message
            send_telegram: Send via Telegram
            metadata: Additional metadata

        Returns:
            Alert: Created alert instance
        """
        # Build title
        title = self._build_position_alert_title(position, alert_type)

        # Build message if not provided
        if not message:
            message = self._build_position_alert_message(position, alert_type)

        # Create alert
        alert = Alert.objects.create(
            account=position.account,
            position=position,
            priority=priority,
            alert_type=alert_type,
            title=title,
            message=message,
            send_telegram=send_telegram,
            metadata=metadata or {}
        )

        logger.info(f"Alert created: {alert_type} for position {position.instrument}")

        # Dispatch to channels
        if send_telegram:
            self._send_via_telegram(alert, position)

        return alert

    def create_risk_alert(
        self,
        account: BrokerAccount,
        alert_type: str,
        priority: str = 'HIGH',
        message: str = '',
        risk_data: Optional[Dict] = None,
        send_telegram: bool = True
    ) -> Alert:
        """
        Create and send risk management alert

        Args:
            account: BrokerAccount instance
            alert_type: Type of alert
            priority: Alert priority
            message: Custom message
            risk_data: Risk metrics data
            send_telegram: Send via Telegram

        Returns:
            Alert: Created alert instance
        """
        # Build title
        title = self._build_risk_alert_title(account, alert_type)

        # Build message if not provided
        if not message:
            message = self._build_risk_alert_message(account, alert_type, risk_data)

        # Create alert
        alert = Alert.objects.create(
            account=account,
            priority=priority,
            alert_type=alert_type,
            title=title,
            message=message,
            send_telegram=send_telegram,
            requires_action=(priority == 'CRITICAL'),
            metadata=risk_data or {}
        )

        logger.info(f"Risk alert created: {alert_type} for {account.account_name}")

        # Dispatch to channels
        if send_telegram:
            self._send_risk_via_telegram(alert, account, risk_data)

        return alert

    def create_daily_summary_alert(
        self,
        account: BrokerAccount,
        summary_data: Dict,
        send_telegram: bool = True
    ) -> Alert:
        """
        Create daily summary alert

        Args:
            account: BrokerAccount instance
            summary_data: Daily summary statistics
            send_telegram: Send via Telegram

        Returns:
            Alert: Created alert instance
        """
        title = f"Daily Summary - {account.account_name} - {summary_data.get('date', 'N/A')}"
        message = self._build_daily_summary_message(summary_data)

        alert = Alert.objects.create(
            account=account,
            priority='INFO',
            alert_type='DAILY_SUMMARY',
            title=title,
            message=message,
            send_telegram=send_telegram,
            metadata=summary_data
        )

        logger.info(f"Daily summary alert created for {account.account_name}")

        # Dispatch to channels
        if send_telegram:
            self._send_daily_summary_via_telegram(alert, summary_data)

        return alert

    def create_system_alert(
        self,
        alert_type: str,
        title: str,
        message: str,
        priority: str = 'HIGH',
        send_telegram: bool = True,
        metadata: Optional[Dict] = None
    ) -> Alert:
        """
        Create system-level alert

        Args:
            alert_type: Type of alert
            title: Alert title
            message: Alert message
            priority: Alert priority
            send_telegram: Send via Telegram
            metadata: Additional metadata

        Returns:
            Alert: Created alert instance
        """
        alert = Alert.objects.create(
            priority=priority,
            alert_type=alert_type,
            title=title,
            message=message,
            send_telegram=send_telegram,
            metadata=metadata or {}
        )

        logger.info(f"System alert created: {alert_type}")

        # Dispatch to channels
        if send_telegram:
            self._send_system_via_telegram(alert)

        return alert

    def retry_failed_alerts(self, max_retries: int = 3) -> Tuple[int, int]:
        """
        Retry sending failed alerts

        Args:
            max_retries: Maximum retry attempts

        Returns:
            Tuple[int, int]: (retried_count, success_count)
        """
        # Get alerts that failed telegram delivery
        failed_alerts = Alert.objects.filter(
            send_telegram=True,
            telegram_sent=False,
            created_at__gte=timezone.now() - timezone.timedelta(hours=24)
        )

        retried = 0
        success = 0

        for alert in failed_alerts:
            # Check retry count
            retry_count = AlertLog.objects.filter(
                alert=alert,
                channel='telegram',
                status='FAILED'
            ).count()

            if retry_count >= max_retries:
                logger.warning(f"Alert {alert.id} exceeded max retries ({max_retries})")
                continue

            # Retry sending
            if alert.position:
                success_sent = self._send_via_telegram(alert, alert.position)
            else:
                success_sent = self._send_system_via_telegram(alert)

            retried += 1
            if success_sent:
                success += 1

        logger.info(f"Retry complete: {retried} retried, {success} successful")
        return retried, success

    # Private helper methods

    def _send_via_telegram(self, alert: Alert, position: Position) -> bool:
        """Send position alert via Telegram"""
        try:
            # Prepare position data
            position_data = {
                'account_name': position.account.account_name,
                'instrument': position.instrument,
                'direction': position.direction,
                'quantity': position.quantity,
                'entry_price': float(position.entry_price),
                'current_price': float(position.current_price),
                'stop_loss': float(position.stop_loss),
                'target': float(position.target),
                'unrealized_pnl': float(position.unrealized_pnl),
                'message': alert.message
            }

            if position.status == 'CLOSED':
                position_data['exit_price'] = float(position.exit_price)
                position_data['realized_pnl'] = float(position.realized_pnl)

            # Send via Telegram
            success, response = self.telegram_client.send_position_alert(
                alert.alert_type,
                position_data
            )

            # Log result
            AlertLog.objects.create(
                alert=alert,
                channel='telegram',
                status='SUCCESS' if success else 'FAILED',
                response=response[:500] if response else '',
                error_message='' if success else response
            )

            if success:
                alert.mark_sent('telegram')
                logger.info(f"Telegram alert sent for position {position.instrument}")
            else:
                logger.error(f"Failed to send Telegram alert: {response}")

            return success

        except Exception as e:
            error_msg = f"Error sending Telegram alert: {str(e)}"
            logger.error(error_msg, exc_info=True)

            AlertLog.objects.create(
                alert=alert,
                channel='telegram',
                status='FAILED',
                error_message=error_msg
            )

            return False

    def _send_risk_via_telegram(
        self,
        alert: Alert,
        account: BrokerAccount,
        risk_data: Optional[Dict]
    ) -> bool:
        """Send risk alert via Telegram"""
        try:
            # Prepare risk data
            telegram_data = {
                'account_name': account.account_name,
                'action_required': risk_data.get('action_required', 'NONE') if risk_data else 'NONE',
                'trading_allowed': risk_data.get('trading_allowed', True) if risk_data else True,
                'active_circuit_breakers': risk_data.get('active_circuit_breakers', 0) if risk_data else 0,
                'message': alert.message
            }

            if risk_data:
                if 'breached_limits' in risk_data:
                    telegram_data['breached_limits'] = risk_data['breached_limits']
                if 'warnings' in risk_data:
                    telegram_data['warnings'] = risk_data['warnings']

            # Send via Telegram
            success, response = self.telegram_client.send_risk_alert(telegram_data)

            # Log result
            AlertLog.objects.create(
                alert=alert,
                channel='telegram',
                status='SUCCESS' if success else 'FAILED',
                response=response[:500] if response else '',
                error_message='' if success else response
            )

            if success:
                alert.mark_sent('telegram')
                logger.info(f"Telegram risk alert sent for {account.account_name}")
            else:
                logger.error(f"Failed to send Telegram risk alert: {response}")

            return success

        except Exception as e:
            error_msg = f"Error sending Telegram risk alert: {str(e)}"
            logger.error(error_msg, exc_info=True)

            AlertLog.objects.create(
                alert=alert,
                channel='telegram',
                status='FAILED',
                error_message=error_msg
            )

            return False

    def _send_daily_summary_via_telegram(
        self,
        alert: Alert,
        summary_data: Dict
    ) -> bool:
        """Send daily summary via Telegram"""
        try:
            success, response = self.telegram_client.send_daily_summary(summary_data)

            # Log result
            AlertLog.objects.create(
                alert=alert,
                channel='telegram',
                status='SUCCESS' if success else 'FAILED',
                response=response[:500] if response else '',
                error_message='' if success else response
            )

            if success:
                alert.mark_sent('telegram')
                logger.info("Telegram daily summary sent")
            else:
                logger.error(f"Failed to send Telegram daily summary: {response}")

            return success

        except Exception as e:
            error_msg = f"Error sending Telegram daily summary: {str(e)}"
            logger.error(error_msg, exc_info=True)

            AlertLog.objects.create(
                alert=alert,
                channel='telegram',
                status='FAILED',
                error_message=error_msg
            )

            return False

    def _send_system_via_telegram(self, alert: Alert) -> bool:
        """Send system alert via Telegram"""
        try:
            message = f"<b>{alert.title}</b>\n\n{alert.message}"

            success, response = self.telegram_client.send_priority_message(
                message,
                alert.priority
            )

            # Log result
            AlertLog.objects.create(
                alert=alert,
                channel='telegram',
                status='SUCCESS' if success else 'FAILED',
                response=response[:500] if response else '',
                error_message='' if success else response
            )

            if success:
                alert.mark_sent('telegram')
                logger.info(f"Telegram system alert sent: {alert.alert_type}")
            else:
                logger.error(f"Failed to send Telegram system alert: {response}")

            return success

        except Exception as e:
            error_msg = f"Error sending Telegram system alert: {str(e)}"
            logger.error(error_msg, exc_info=True)

            AlertLog.objects.create(
                alert=alert,
                channel='telegram',
                status='FAILED',
                error_message=error_msg
            )

            return False

    def _build_position_alert_title(self, position: Position, alert_type: str) -> str:
        """Build alert title for position"""
        title_map = {
            'POSITION_ENTERED': 'Position Entered',
            'POSITION_CLOSED': 'Position Closed',
            'SL_HIT': 'Stop-Loss Hit',
            'TARGET_HIT': 'Target Hit',
            'DELTA_ALERT': 'Delta Alert',
            'AVERAGING_DONE': 'Position Averaged',
        }

        title = title_map.get(alert_type, alert_type)
        return f"{title} - {position.instrument}"

    def _build_position_alert_message(self, position: Position, alert_type: str) -> str:
        """Build alert message for position"""
        if alert_type == 'POSITION_ENTERED':
            return (
                f"New {position.direction} position entered in {position.instrument}. "
                f"Quantity: {position.quantity} lots at Rs.{position.entry_price:,.2f}. "
                f"SL: Rs.{position.stop_loss:,.2f}, Target: Rs.{position.target:,.2f}"
            )
        elif alert_type == 'POSITION_CLOSED':
            pnl_text = "Profit" if position.realized_pnl >= 0 else "Loss"
            return (
                f"Position closed in {position.instrument}. "
                f"Exit: Rs.{position.exit_price:,.2f}. "
                f"{pnl_text}: Rs.{abs(position.realized_pnl):,.2f}"
            )
        elif alert_type == 'SL_HIT':
            return (
                f"Stop-loss hit for {position.instrument}. "
                f"Current: Rs.{position.current_price:,.2f}, SL: Rs.{position.stop_loss:,.2f}. "
                f"IMMEDIATE EXIT REQUIRED."
            )
        elif alert_type == 'TARGET_HIT':
            return (
                f"Target hit for {position.instrument}. "
                f"Current: Rs.{position.current_price:,.2f}, Target: Rs.{position.target:,.2f}. "
                f"Consider exiting."
            )
        else:
            return f"{alert_type} for {position.instrument}"

    def _build_risk_alert_title(self, account: BrokerAccount, alert_type: str) -> str:
        """Build alert title for risk alert"""
        title_map = {
            'CIRCUIT_BREAKER': 'CIRCUIT BREAKER ACTIVATED',
            'DAILY_LOSS_LIMIT': 'Daily Loss Limit Warning',
            'WEEKLY_LOSS_LIMIT': 'Weekly Loss Limit Warning',
            'RISK_WARNING': 'Risk Warning',
        }

        title = title_map.get(alert_type, alert_type)
        return f"{title} - {account.account_name}"

    def _build_risk_alert_message(
        self,
        account: BrokerAccount,
        alert_type: str,
        risk_data: Optional[Dict]
    ) -> str:
        """Build alert message for risk alert"""
        if not risk_data:
            return f"{alert_type} for {account.account_name}"

        message = risk_data.get('message', '')

        if alert_type == 'CIRCUIT_BREAKER':
            message += "\n\nAll trading stopped. Manual intervention required."

        return message

    def _build_daily_summary_message(self, summary_data: Dict) -> str:
        """Build daily summary message"""
        total_pnl = summary_data.get('total_pnl', 0)
        pnl_text = "Profit" if total_pnl >= 0 else "Loss"

        message = f"Daily {pnl_text}: Rs.{abs(total_pnl):,.2f}\n"
        message += f"Trades: {summary_data.get('total_trades', 0)}\n"
        message += f"Win Rate: {summary_data.get('win_rate', 0):.1f}%"

        return message


# Global instance
_alert_manager = None


def get_alert_manager() -> AlertManager:
    """Get or create global AlertManager instance"""
    global _alert_manager

    if _alert_manager is None:
        _alert_manager = AlertManager()

    return _alert_manager


# Convenience functions

def send_position_alert(
    position: Position,
    alert_type: str,
    priority: str = 'MEDIUM',
    message: str = ''
) -> Alert:
    """
    Send position alert (convenience function)

    Args:
        position: Position instance
        alert_type: Type of alert
        priority: Alert priority
        message: Custom message

    Returns:
        Alert: Created alert
    """
    manager = get_alert_manager()
    return manager.create_position_alert(position, alert_type, priority, message)


def send_risk_alert(
    account: BrokerAccount,
    alert_type: str,
    priority: str = 'HIGH',
    risk_data: Optional[Dict] = None
) -> Alert:
    """
    Send risk alert (convenience function)

    Args:
        account: BrokerAccount instance
        alert_type: Type of alert
        priority: Alert priority
        risk_data: Risk metrics

    Returns:
        Alert: Created alert
    """
    manager = get_alert_manager()
    return manager.create_risk_alert(account, alert_type, priority, risk_data=risk_data)
