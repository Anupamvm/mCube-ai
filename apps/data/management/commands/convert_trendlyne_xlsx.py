"""
Convert Trendlyne XLSX files to CSV format for database import

This command converts downloaded XLSX files from apps/data/tldata/ to CSV format
in trendlyne_data/ directory for processing by trendlyne_data_manager.

Usage:
    python manage.py convert_trendlyne_xlsx
"""

import os
import pandas as pd
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Convert Trendlyne XLSX files to CSV format'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('CONVERT TRENDLYNE XLSX TO CSV'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

        # Define directories
        source_dir = Path(settings.BASE_DIR) / 'apps' / 'data' / 'tldata'
        target_dir = Path(settings.BASE_DIR) / 'trendlyne_data'
        target_dir.mkdir(parents=True, exist_ok=True)

        # Convert FNO Data (Contract Data)
        self.convert_fno_data(source_dir, target_dir)

        # Convert Stock Data
        self.convert_stock_data(source_dir, target_dir)

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('✅ CONVERSION COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

    def convert_fno_data(self, source_dir, target_dir):
        """Convert FNO data XLSX to contract_data.csv"""
        self.stdout.write('📊 Converting FNO Data...')

        # Find the latest FNO data file
        fno_files = list(source_dir.glob('fno_data_*.xlsx'))
        if not fno_files:
            self.stdout.write(self.style.WARNING('  ⚠️  No FNO data files found'))
            return

        # Get the most recent file
        latest_file = max(fno_files, key=lambda x: x.stat().st_mtime)
        self.stdout.write(f'  📁 Reading {latest_file.name}')

        try:
            # Read XLSX
            df = pd.read_excel(latest_file, sheet_name=0)

            # Normalize column names
            df.columns = [
                col.lower()
                .replace(' ', '_')
                .replace('%', 'pct_')
                .replace('(', '')
                .replace(')', '')
                .replace('__', '_')
                for col in df.columns
            ]

            # Handle NaN values
            df = df.fillna(0)

            # Replace string 'nan' with empty strings
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].replace('nan', '')

            # Save as CSV
            csv_file = target_dir / 'contract_data.csv'
            df.to_csv(csv_file, index=False)

            self.stdout.write(
                self.style.SUCCESS(f'  ✅ Converted {len(df):,} rows to {csv_file.name}')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Error converting FNO data: {e}')
            )

    def convert_stock_data(self, source_dir, target_dir):
        """Convert Stock data XLSX to stock_data.csv"""
        self.stdout.write('\n📊 Converting Stock Data...')

        # Find the latest Stock data file
        stock_files = list(source_dir.glob('Stocks-data-IND-*.xlsx'))
        if not stock_files:
            self.stdout.write(self.style.WARNING('  ⚠️  No Stock data files found'))
            return

        # Get the most recent file
        latest_file = max(stock_files, key=lambda x: x.stat().st_mtime)
        self.stdout.write(f'  📁 Reading {latest_file.name}')

        try:
            # Read XLSX
            df = pd.read_excel(latest_file, sheet_name=0)

            # Normalize column names
            df.columns = [
                col.lower()
                .replace(' ', '_')
                .replace('%', 'pct_')
                .replace('(', '')
                .replace(')', '')
                .replace('__', '_')
                .replace('-', '_')
                for col in df.columns
            ]

            # Handle NaN values
            for col in df.columns:
                if df[col].dtype in ['float64', 'int64']:
                    df[col] = df[col].fillna(0)
                elif df[col].dtype == 'object':
                    df[col] = df[col].fillna('')
                    df[col] = df[col].replace('nan', '')

            # Save as CSV
            csv_file = target_dir / 'stock_data.csv'
            df.to_csv(csv_file, index=False)

            self.stdout.write(
                self.style.SUCCESS(f'  ✅ Converted {len(df):,} rows to {csv_file.name}')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Error converting Stock data: {e}')
            )
