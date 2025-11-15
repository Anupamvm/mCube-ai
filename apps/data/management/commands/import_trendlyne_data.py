"""
Management command to import Trendlyne CSV data into database
"""

from django.core.management.base import BaseCommand
from apps.data.importers import TrendlyneDataImporter, ContractStockDataImporter


class Command(BaseCommand):
    help = 'Import Trendlyne CSV data into database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['market_snapshot', 'fno', 'forecaster', 'all'],
            default='all',
            help='Type of data to import'
        )
        parser.add_argument(
            '--file',
            type=str,
            help='Specific file path (optional)'
        )

    def handle(self, *args, **options):
        importer = TrendlyneDataImporter()
        data_type = options['type']
        file_path = options.get('file')

        self.stdout.write(self.style.SUCCESS('Starting Trendlyne data import...'))

        if data_type in ['market_snapshot', 'all']:
            self.stdout.write('Importing market snapshot data...')
            result = importer.import_market_snapshot(file_path)
            self.stdout.write(self.style.SUCCESS(
                f"Market Snapshot: Created={result.get('created', 0)}, "
                f"Updated={result.get('updated', 0)}, "
                f"Errors={result.get('errors', 0)}"
            ))

        if data_type in ['fno', 'all']:
            self.stdout.write('Importing F&O data...')
            result = importer.import_fno_data(file_path)
            self.stdout.write(self.style.SUCCESS(
                f"F&O Data: Created={result.get('created', 0)}, "
                f"Updated={result.get('updated', 0)}, "
                f"Errors={result.get('errors', 0)}"
            ))

            # Calculate aggregated stock-level data
            self.stdout.write('Calculating stock-level F&O metrics...')
            stock_importer = ContractStockDataImporter()
            result = stock_importer.calculate_and_save_stock_fno_data()
            self.stdout.write(self.style.SUCCESS(
                f"Stock F&O Data: Created={result.get('created', 0)}, "
                f"Updated={result.get('updated', 0)}"
            ))

        if data_type in ['forecaster', 'all']:
            self.stdout.write('Importing forecaster data...')
            results = importer.import_forecaster_data()
            for file, result in results.items():
                if 'error' in result:
                    self.stdout.write(self.style.ERROR(f"{file}: {result['error']}"))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f"{file}: Updated={result.get('updated', 0)}"
                    ))

        self.stdout.write(self.style.SUCCESS('\nData import completed!'))
