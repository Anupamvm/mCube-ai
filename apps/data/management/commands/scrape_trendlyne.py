"""
Django management command to scrape Trendlyne data

Usage:
    python manage.py scrape_trendlyne
"""

from django.core.management.base import BaseCommand
from apps.data.tools.trendlyne import get_all_trendlyne_data
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scrape all data from Trendlyne (F&O, Market Snapshot, Forecaster)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dir',
            type=str,
            help='Custom download directory (default: apps/data/tldata/)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting Trendlyne data scraping...'))
        self.stdout.write(self.style.WARNING('This may take several minutes.'))

        download_dir = options.get('dir')

        try:
            results = get_all_trendlyne_data(download_dir=download_dir)

            # Display results
            self.stdout.write(self.style.SUCCESS('\n=== Trendlyne Scraping Results ==='))

            if results['login']:
                self.stdout.write(self.style.SUCCESS('✓ Login: Success'))
            else:
                self.stdout.write(self.style.ERROR('✗ Login: Failed'))

            if results['fno_data']:
                self.stdout.write(self.style.SUCCESS(f'✓ F&O Data: {results["fno_data"]}'))
            else:
                self.stdout.write(self.style.WARNING('✗ F&O Data: Failed'))

            if results['market_snapshot']:
                self.stdout.write(self.style.SUCCESS(f'✓ Market Snapshot: {results["market_snapshot"]}'))
            else:
                self.stdout.write(self.style.WARNING('✗ Market Snapshot: Failed'))

            self.stdout.write(self.style.SUCCESS(f'✓ Forecaster Pages: {results["forecaster_pages"]}/21'))

            if results['errors']:
                self.stdout.write(self.style.ERROR(f'\nErrors encountered:'))
                for error in results['errors']:
                    self.stdout.write(self.style.ERROR(f'  - {error}'))
            else:
                self.stdout.write(self.style.SUCCESS('\n✅ All data scraped successfully!'))

            self.stdout.write('')
            self.stdout.write('Next steps:')
            self.stdout.write('  1. Run: python manage.py import_trendlyne_data')
            self.stdout.write('  2. Check data in Django admin')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            logger.exception('Trendlyne scraping failed')
            raise
