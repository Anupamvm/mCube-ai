"""
Test Telegram Integration

This command tests the Telegram notification system with mock data.

Usage:
    python manage.py test_telegram
    python manage.py test_telegram --send-all  # Send all test messages
"""

from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.positions.models import Position
from apps.alerts.services import (
    get_telegram_client,
    get_alert_manager,
    send_position_alert,
    send_risk_alert,
)


class Command(BaseCommand):
    help = 'Test Telegram notification integration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-all',
            action='store_true',
            help='Send all test notifications'
        )

    def handle(self, *args, **options):
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('TESTING TELEGRAM INTEGRATION'))
        self.stdout.write('=' * 80)
        self.stdout.write('')

        # Check if Telegram is configured
        telegram_client = get_telegram_client()

        if not telegram_client.is_enabled():
            self.stdout.write(
                self.style.ERROR('\nTelegram client not configured!')
            )
            self.stdout.write(
                self.style.WARNING('\nPlease set the following environment variables:')
            )
            self.stdout.write('  - TELEGRAM_BOT_TOKEN')
            self.stdout.write('  - TELEGRAM_CHAT_ID')
            self.stdout.write('')
            self.stdout.write('To get these values:')
            self.stdout.write('  1. Create a bot via @BotFather on Telegram')
            self.stdout.write('  2. Get your chat ID from @userinfobot')
            self.stdout.write('  3. Add them to your .env file')
            self.stdout.write('')
            return

        self.stdout.write(self.style.SUCCESS('✅ Telegram client configured'))
        self.stdout.write('')

        # Get or create test account
        test_account, created = BrokerAccount.objects.get_or_create(
            account_name='TEST_TELEGRAM',
            defaults={
                'broker': 'TEST',
                'account_type': 'PAPER',
                'allocated_capital': Decimal('1000000'),
                'max_daily_loss': Decimal('50000'),
                'max_weekly_loss': Decimal('100000'),
                'is_active': True
            }
        )

        if created:
            self.stdout.write(f'Created test account: {test_account.account_name}')
        else:
            self.stdout.write(f'Using existing test account: {test_account.account_name}')

        self.stdout.write('')

        # Test 1: Simple notification
        self.stdout.write(self.style.WARNING('TEST 1: Simple Notification'))
        self.stdout.write('-' * 80)

        success, response = telegram_client.send_priority_message(
            "This is a test notification from mCube Trading System!",
            priority='INFO'
        )

        if success:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Message sent: {response}'))
        else:
            self.stdout.write(self.style.ERROR(f'  ❌ Failed: {response}'))

        self.stdout.write('')

        if not options['send_all']:
            self.stdout.write(
                self.style.WARNING('\nTo send all test messages, run: python manage.py test_telegram --send-all')
            )
            return

        # Test 2: Position Entry Alert
        self.stdout.write(self.style.WARNING('TEST 2: Position Entry Alert'))
        self.stdout.write('-' * 80)

        position_data = {
            'account_name': test_account.account_name,
            'instrument': 'NIFTY24NOV2424000CE',
            'direction': 'NEUTRAL',
            'quantity': 10,
            'entry_price': 100.00,
            'current_price': 100.00,
            'stop_loss': 200.00,
            'target': 30.00,
            'unrealized_pnl': 0.00,
            'message': 'Test position entry notification'
        }

        success, response = telegram_client.send_position_alert(
            'POSITION_ENTERED',
            position_data
        )

        if success:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Position entry alert sent'))
        else:
            self.stdout.write(self.style.ERROR(f'  ❌ Failed: {response}'))

        self.stdout.write('')

        # Test 3: Stop-Loss Hit Alert
        self.stdout.write(self.style.WARNING('TEST 3: Stop-Loss Hit Alert'))
        self.stdout.write('-' * 80)

        sl_data = {
            'account_name': test_account.account_name,
            'instrument': 'NIFTY24NOV2424000CE',
            'direction': 'NEUTRAL',
            'quantity': 10,
            'entry_price': 100.00,
            'current_price': 210.00,
            'stop_loss': 200.00,
            'target': 30.00,
            'unrealized_pnl': -55000.00,
            'message': 'IMMEDIATE EXIT REQUIRED - Stop-loss breached!'
        }

        success, response = telegram_client.send_position_alert(
            'SL_HIT',
            sl_data
        )

        if success:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Stop-loss alert sent'))
        else:
            self.stdout.write(self.style.ERROR(f'  ❌ Failed: {response}'))

        self.stdout.write('')

        # Test 4: Target Hit Alert
        self.stdout.write(self.style.WARNING('TEST 4: Target Hit Alert'))
        self.stdout.write('-' * 80)

        target_data = {
            'account_name': test_account.account_name,
            'instrument': 'NIFTY24NOV2424000CE',
            'direction': 'NEUTRAL',
            'quantity': 10,
            'entry_price': 100.00,
            'current_price': 25.00,
            'stop_loss': 200.00,
            'target': 30.00,
            'unrealized_pnl': 37500.00,
            'message': 'Target achieved! Consider booking profits.'
        }

        success, response = telegram_client.send_position_alert(
            'TARGET_HIT',
            target_data
        )

        if success:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Target hit alert sent'))
        else:
            self.stdout.write(self.style.ERROR(f'  ❌ Failed: {response}'))

        self.stdout.write('')

        # Test 5: Risk Alert
        self.stdout.write(self.style.WARNING('TEST 5: Risk Management Alert'))
        self.stdout.write('-' * 80)

        risk_data = {
            'account_name': test_account.account_name,
            'action_required': 'WARNING',
            'trading_allowed': True,
            'active_circuit_breakers': 0,
            'warnings': [
                {
                    'type': 'DAILY_LOSS',
                    'utilization': 75.5
                }
            ],
            'message': 'Daily loss limit at 75.5%. Exercise caution.'
        }

        success, response = telegram_client.send_risk_alert(risk_data)

        if success:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Risk alert sent'))
        else:
            self.stdout.write(self.style.ERROR(f'  ❌ Failed: {response}'))

        self.stdout.write('')

        # Test 6: Circuit Breaker Alert
        self.stdout.write(self.style.WARNING('TEST 6: Circuit Breaker Alert'))
        self.stdout.write('-' * 80)

        circuit_breaker_data = {
            'account_name': test_account.account_name,
            'action_required': 'EMERGENCY_EXIT',
            'trading_allowed': False,
            'active_circuit_breakers': 1,
            'breached_limits': [
                {
                    'type': 'DAILY_LOSS',
                    'current': 55000,
                    'limit': 50000
                }
            ],
            'message': 'CIRCUIT BREAKER ACTIVATED! Daily loss limit exceeded. All trading stopped.'
        }

        success, response = telegram_client.send_risk_alert(circuit_breaker_data)

        if success:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Circuit breaker alert sent'))
        else:
            self.stdout.write(self.style.ERROR(f'  ❌ Failed: {response}'))

        self.stdout.write('')

        # Test 7: Daily Summary
        self.stdout.write(self.style.WARNING('TEST 7: Daily Trading Summary'))
        self.stdout.write('-' * 80)

        summary_data = {
            'date': date.today().strftime('%Y-%m-%d'),
            'total_pnl': 15750.00,
            'realized_pnl': 12000.00,
            'unrealized_pnl': 3750.00,
            'total_trades': 5,
            'winning_trades': 3,
            'losing_trades': 2,
            'win_rate': 60.0,
            'active_positions': 1,
            'capital_deployed': 250000,
            'margin_available': 750000,
            'max_drawdown': 2.5,
            'daily_loss_limit_used': 31.5
        }

        success, response = telegram_client.send_daily_summary(summary_data)

        if success:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Daily summary sent'))
        else:
            self.stdout.write(self.style.ERROR(f'  ❌ Failed: {response}'))

        self.stdout.write('')

        # Test 8: Using AlertManager
        self.stdout.write(self.style.WARNING('TEST 8: AlertManager Integration'))
        self.stdout.write('-' * 80)

        alert_manager = get_alert_manager()

        # Create a test system alert
        alert = alert_manager.create_system_alert(
            alert_type='SYSTEM_TEST',
            title='System Test Alert',
            message='This is a test alert created via AlertManager to verify database integration.',
            priority='INFO',
            send_telegram=True
        )

        if alert.telegram_sent:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Alert created and sent (ID: {alert.id})'))
            self.stdout.write(f'     - Delivery logs: {alert.logs.count()}')
        else:
            self.stdout.write(self.style.ERROR(f'  ❌ Alert created but failed to send (ID: {alert.id})'))

        self.stdout.write('')

        # Summary
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('TELEGRAM INTEGRATION TEST COMPLETE'))
        self.stdout.write('=' * 80)
        self.stdout.write('')
        self.stdout.write('Check your Telegram chat to verify all messages were received!')
        self.stdout.write('')
