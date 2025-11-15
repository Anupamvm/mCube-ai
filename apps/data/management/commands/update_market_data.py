"""
Management command to update live market data from broker APIs
"""

from django.core.management.base import BaseCommand
from apps.data.broker_integration import MarketDataUpdater


class Command(BaseCommand):
    help = 'Update live market data from broker APIs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--broker',
            type=str,
            default='breeze',
            choices=['breeze', 'kotak_neo'],
            help='Broker to fetch data from'
        )
        parser.add_argument(
            '--type',
            type=str,
            default='all',
            choices=['stocks', 'fno', 'all'],
            help='Type of data to update'
        )
        parser.add_argument(
            '--symbols',
            type=str,
            nargs='+',
            help='Specific symbols to update (space-separated)'
        )
        parser.add_argument(
            '--expiry',
            type=str,
            help='F&O expiry date (DD-MMM-YYYY)'
        )

    def handle(self, *args, **options):
        broker = options['broker']
        data_type = options['type']
        symbols = options.get('symbols')
        expiry = options.get('expiry')

        self.stdout.write(self.style.SUCCESS(
            f'\nUpdating market data from {broker.upper()}...\n'
        ))

        try:
            updater = MarketDataUpdater(broker=broker)

            if data_type in ['stocks', 'all']:
                self.stdout.write('Updating stock data...')

                if symbols:
                    stats = updater.update_stock_universe(symbols)
                else:
                    stats = updater.update_nifty50_stocks()

                self.stdout.write(self.style.SUCCESS(
                    f"Stocks: {stats['updated']}/{stats['total']} updated, "
                    f"{stats['failed']} failed"
                ))

            if data_type in ['fno', 'all']:
                self.stdout.write('\nUpdating F&O data...')

                if symbols:
                    stats = updater.update_fno_universe(symbols, expiry)
                else:
                    stats = updater.update_fno_stocks(expiry)

                self.stdout.write(self.style.SUCCESS(
                    f"F&O: {stats['futures_updated']} futures, "
                    f"{stats['options_updated']} options updated, "
                    f"{stats['failed']} failed"
                ))

                # Calculate derived metrics
                self.stdout.write('\nCalculating derived metrics...')
                updater.calculate_and_update_derived_metrics('NIFTY', expiry or updater._get_current_expiry())

            self.stdout.write(self.style.SUCCESS('\n✅ Market data update completed!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error: {str(e)}'))
