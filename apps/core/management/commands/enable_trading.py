"""
Management command to enable/disable automated trading
"""

from django.core.management.base import BaseCommand
from apps.core.models import NseFlag


class Command(BaseCommand):
    help = 'Enable or disable automated trading'

    def add_arguments(self, parser):
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Disable automated trading'
        )

    def handle(self, *args, **options):
        if options['disable']:
            NseFlag.set('autoTradingEnabled', 'false', 'Auto-trading disabled by user')
            self.stdout.write(self.style.WARNING('\n⚠️  Automated trading DISABLED\n'))
        else:
            NseFlag.set('autoTradingEnabled', 'true', 'Auto-trading enabled by user')
            self.stdout.write(self.style.SUCCESS('\n✅ Automated trading ENABLED\n'))

        # Show current status
        self.stdout.write('\nCurrent Configuration:')
        
        flags_to_show = [
            'autoTradingEnabled',
            'isDayTradable',
            'nseVix',
            'vixStatus',
            'openPositions',
            'stopLossLimit',
            'minDailyProfitTarget',
        ]

        for flag_name in flags_to_show:
            value = NseFlag.get(flag_name, 'Not set')
            self.stdout.write(f'  {flag_name}: {value}')

        self.stdout.write('')
