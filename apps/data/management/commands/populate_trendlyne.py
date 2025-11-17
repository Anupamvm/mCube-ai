"""
Populate Trendlyne data - Complete workflow

This command performs the complete workflow to populate Trendlyne data:
1. Convert XLSX files to CSV format
2. Parse CSV files and populate database
3. Show status

Usage:
    python manage.py populate_trendlyne
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Complete workflow: Convert XLSX → Parse CSV → Populate Database'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('TRENDLYNE DATA POPULATION - FULL WORKFLOW'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

        # Step 0: Clear old data
        self.stdout.write(self.style.WARNING('[Step 1/4] Clearing old data from database...\n'))
        try:
            call_command('trendlyne_data_manager', '--clear-database')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Data cleanup failed: {e}'))
            return

        # Step 1: Convert XLSX to CSV
        self.stdout.write(self.style.WARNING('\n[Step 2/4] Converting XLSX files to CSV...\n'))
        try:
            call_command('convert_trendlyne_xlsx')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ XLSX conversion failed: {e}'))
            return

        # Step 2: Parse CSV and populate database
        self.stdout.write(self.style.WARNING('\n[Step 3/4] Parsing CSV and populating database...\n'))
        try:
            call_command('trendlyne_data_manager', '--parse-all')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Database population failed: {e}'))
            return

        # Step 3: Show status
        self.stdout.write(self.style.WARNING('\n[Step 4/4] Checking status...\n'))
        try:
            call_command('trendlyne_data_manager', '--status')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Status check failed: {e}'))
            return

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('✅ TRENDLYNE DATA POPULATION COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))
        self.stdout.write('\nYour database now contains:')
        self.stdout.write('  • Contract Data (F&O)')
        self.stdout.write('  • Stock Data (Comprehensive metrics)')
        self.stdout.write('\nUse these models in your code:')
        self.stdout.write('  - apps.data.models.ContractData')
        self.stdout.write('  - apps.data.models.TLStockData\n')
