"""
Trendlyne Data Manager Command

Manages complete lifecycle of Trendlyne data:
1. Download data from Trendlyne.com
2. Store raw files temporarily
3. Parse and populate database models
4. Clean up temporary files

Usage:
    # Download all Trendlyne data
    python manage.py trendlyne_data_manager --download-all

    # Parse and populate database
    python manage.py trendlyne_data_manager --parse-all

    # Clear all downloaded files
    python manage.py trendlyne_data_manager --clear-files

    # Clear all database data
    python manage.py trendlyne_data_manager --clear-database

    # Full cycle: Download -> Parse -> Populate -> Clean
    python manage.py trendlyne_data_manager --full-cycle
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction

from apps.data.models import (
    ContractData, ContractStockData, TLStockData,
    OptionChain, Event, MarketData, NewsArticle,
    InvestorCall, KnowledgeBase
)


class Command(BaseCommand):
    help = 'Manage Trendlyne data: download, parse, populate database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--download-all',
            action='store_true',
            help='Download all data from Trendlyne'
        )

        parser.add_argument(
            '--parse-all',
            action='store_true',
            help='Parse downloaded files and populate database'
        )

        parser.add_argument(
            '--clear-files',
            action='store_true',
            help='Clear all temporary downloaded files'
        )

        parser.add_argument(
            '--clear-database',
            action='store_true',
            help='Clear all data from database'
        )

        parser.add_argument(
            '--full-cycle',
            action='store_true',
            help='Full cycle: Download -> Parse -> Populate -> Clean'
        )

        parser.add_argument(
            '--status',
            action='store_true',
            help='Show status of files and database'
        )

    def handle(self, *args, **options):
        if options['full_cycle']:
            self.full_cycle()
        elif options['download_all']:
            self.download_all()
        elif options['parse_all']:
            self.parse_all()
        elif options['clear_files']:
            self.clear_files()
        elif options['clear_database']:
            self.clear_database()
        elif options['status']:
            self.show_status()
        else:
            self.stdout.write(self.style.WARNING('No action specified. Use --help for options.'))

    def get_download_dir(self):
        """Get or create download directory"""
        download_dir = Path(settings.BASE_DIR) / 'trendlyne_data'
        download_dir.mkdir(parents=True, exist_ok=True)
        return download_dir

    def full_cycle(self):
        """Complete workflow: Download -> Parse -> Populate -> Clean"""
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('TRENDLYNE DATA FULL CYCLE'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

        # Step 1: Clear previous files
        self.stdout.write(self.style.WARNING('\n[1/4] Clearing previous files...'))
        self.clear_files()

        # Step 2: Download new data
        self.stdout.write(self.style.WARNING('\n[2/4] Downloading data from Trendlyne...'))
        self.download_all()

        # Step 3: Parse and populate database
        self.stdout.write(self.style.WARNING('\n[3/4] Parsing files and populating database...'))
        self.parse_all()

        # Step 4: Clean up files
        self.stdout.write(self.style.WARNING('\n[4/4] Cleaning up temporary files...'))
        self.clear_files()

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('✅ FULL CYCLE COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

    def download_all(self):
        """Download all Trendlyne data using TrendlyneProvider"""
        try:
            from apps.data.providers.trendlyne import TrendlyneProvider

            download_dir = self.get_download_dir()
            self.stdout.write(f'\n📁 Download directory: {download_dir}')
            self.stdout.write('⬇️  Downloading all Trendlyne data...\n')

            with TrendlyneProvider(headless=True, download_dir=str(download_dir)) as provider:
                result = provider.fetch_all_data(download_dir=str(download_dir))

                if result.get('success'):
                    self.stdout.write(self.style.SUCCESS('✅ Download phase complete\n'))
                else:
                    error_msg = result.get('error', 'Unknown error')
                    self.stdout.write(self.style.ERROR(f'❌ Download failed: {error_msg}\n'))
                    raise CommandError(f'Download failed: {error_msg}')

        except ImportError as e:
            raise CommandError(f'Import error: {e}. Ensure TrendlyneProvider is available in apps.data.providers.trendlyne')
        except Exception as e:
            raise CommandError(f'Download failed: {e}')

    def parse_all(self):
        """Parse downloaded files and populate database"""
        try:
            download_dir = self.get_download_dir()

            # List of (model, parser_function, csv_filename)
            parsers = [
                (ContractData, self.parse_contract_data, 'contract_data.csv'),
                (ContractStockData, self.parse_contract_stock_data, 'contract_stock_data.csv'),
                (TLStockData, self.parse_stock_data, 'stock_data.csv'),
                (OptionChain, self.parse_option_chains, 'option_chains.csv'),
                (Event, self.parse_events, 'events.csv'),
                (NewsArticle, self.parse_news, 'news.csv'),
                (InvestorCall, self.parse_investor_calls, 'investor_calls.csv'),
                (KnowledgeBase, self.parse_knowledge_base, 'knowledge_base.csv'),
            ]

            self.stdout.write('\n📊 Parsing and populating database...\n')

            for model, parser_func, filename in parsers:
                filepath = download_dir / filename
                if filepath.exists():
                    try:
                        self.stdout.write(f'🔄 Parsing {model.__name__}...')
                        count = parser_func(filepath)
                        self.stdout.write(
                            self.style.SUCCESS(f'   ✅ {count} {model.__name__} records created')
                        )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'   ❌ Error parsing {model.__name__}: {e}')
                        )
                else:
                    self.stdout.write(self.style.WARNING(f'   ⚠️  File not found: {filename}'))

            self.stdout.write(self.style.SUCCESS('\n✅ Parse phase complete\n'))

        except Exception as e:
            raise CommandError(f'Parse failed: {e}')

    def _get_contract_csv_column(self, field_name, csv_columns):
        """
        Find matching CSV column for ContractData model field.
        Handles naming variations in contract_data.csv.
        """
        # Direct mappings for special cases
        special_mappings = {
            'cost_of_carry': 'cost_of_carry_coc',
            'traded_contracts_change_pct': 'traded_contracts_changepct_',
        }

        # Check special mappings first
        if field_name in special_mappings:
            csv_col = special_mappings[field_name]
            if csv_col in csv_columns:
                return csv_col

        # Try standard variations
        variations = [
            field_name,
            field_name + '_',
            field_name.replace('_change_pct', '_changepct_'),
        ]

        for variant in variations:
            if variant in csv_columns:
                return variant

        return None

    def parse_contract_data(self, filepath):
        """Parse contract data CSV with dynamic field mapping"""
        import pandas as pd
        import numpy as np

        self.stdout.write("Parsing contract data CSV...")
        ContractData.objects.all().delete()
        df = pd.read_csv(filepath)

        # Get all model field names and CSV columns
        model_fields = {f.name: f for f in ContractData._meta.fields}
        skip_fields = {'id', 'created_at', 'updated_at'}
        csv_columns = set(df.columns)

        self.stdout.write(f"Processing {len(df)} contracts with {len(df.columns)} CSV columns...")

        # Build field mapping once
        field_mapping = {}
        unmapped_fields = []
        for field_name in model_fields:
            if field_name in skip_fields:
                continue
            csv_col = self._get_contract_csv_column(field_name, csv_columns)
            if csv_col:
                field_mapping[field_name] = csv_col
            else:
                unmapped_fields.append(field_name)

        self.stdout.write(f"  Mapped {len(field_mapping)} fields, {len(unmapped_fields)} fields not in CSV")

        created_count = 0
        error_count = 0

        with transaction.atomic():
            for idx, row in df.iterrows():
                try:
                    # Build kwargs using pre-built mapping
                    kwargs = {}

                    for field_name, csv_col in field_mapping.items():
                        # Get value from CSV
                        value = row[csv_col]

                        # Handle NaN, None, and empty values
                        if pd.isna(value):
                            value = None
                        elif isinstance(value, str):
                            value = value.strip()
                            if value == '' or value.lower() in ['nan', 'null', 'none', '-', 'na', 'n/a']:
                                value = None
                        elif isinstance(value, (int, float)):
                            if np.isinf(value):
                                value = None

                        kwargs[field_name] = value

                    # Create the record with all mapped fields
                    ContractData.objects.create(**kwargs)
                    created_count += 1

                    if (idx + 1) % 1000 == 0:
                        self.stdout.write(f"  Processed {idx + 1}/{len(df)} contracts...")

                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        self.stdout.write(self.style.WARNING(
                            f"  Error on row {idx + 1}: {str(e)[:100]}"
                        ))

        self.stdout.write(self.style.SUCCESS(
            f"✅ Contract data import complete: {created_count} created, {error_count} errors"
        ))

        return created_count

    def parse_contract_stock_data(self, filepath):
        """Parse contract stock data CSV"""
        import pandas as pd

        ContractStockData.objects.all().delete()
        df = pd.read_csv(filepath)

        with transaction.atomic():
            for _, row in df.iterrows():
                ContractStockData.objects.create(
                    stock_name=row.get('stock_name'),
                    nse_code=row.get('nse_code'),
                    bse_code=row.get('bse_code', ''),
                    isin=row.get('isin', ''),
                    current_price=float(row.get('current_price', 0)),
                    industry_name=row.get('industry_name'),
                    annualized_volatility=float(row.get('annualized_volatility', 0)),
                    fno_total_oi=int(row.get('fno_total_oi', 0)),
                    fno_prev_day_total_oi=int(row.get('fno_prev_day_total_oi', 0)),
                    fno_total_put_oi=int(row.get('fno_total_put_oi', 0)),
                    fno_total_call_oi=int(row.get('fno_total_call_oi', 0)),
                    fno_prev_day_put_oi=int(row.get('fno_prev_day_put_oi', 0)),
                    fno_prev_day_call_oi=int(row.get('fno_prev_day_call_oi', 0)),
                    fno_total_put_vol=int(row.get('fno_total_put_vol', 0)),
                    fno_total_call_vol=int(row.get('fno_total_call_vol', 0)),
                    fno_prev_day_put_vol=int(row.get('fno_prev_day_put_vol', 0)),
                    fno_prev_day_call_vol=int(row.get('fno_prev_day_call_vol', 0)),
                    fno_mwpl=int(row.get('fno_mwpl', 0)),
                    fno_pcr_vol=float(row.get('fno_pcr_vol', 0)),
                    fno_pcr_vol_prev=float(row.get('fno_pcr_vol_prev', 0)),
                    fno_pcr_vol_change_pct=float(row.get('fno_pcr_vol_change_pct', 0)),
                    fno_pcr_oi=float(row.get('fno_pcr_oi', 0)),
                    fno_pcr_oi_prev=float(row.get('fno_pcr_oi_prev', 0)),
                    fno_pcr_oi_change_pct=float(row.get('fno_pcr_oi_change_pct', 0)),
                    fno_mwpl_pct=float(row.get('fno_mwpl_pct', 0)),
                    fno_mwpl_prev_pct=float(row.get('fno_mwpl_prev_pct', 0)),
                    fno_total_oi_change_pct=float(row.get('fno_total_oi_change_pct', 0)),
                    fno_put_oi_change_pct=float(row.get('fno_put_oi_change_pct', 0)),
                    fno_call_oi_change_pct=float(row.get('fno_call_oi_change_pct', 0)),
                    fno_put_vol_change_pct=float(row.get('fno_put_vol_change_pct', 0)),
                    fno_call_vol_change_pct=float(row.get('fno_call_vol_change_pct', 0)),
                    fno_rollover_cost=float(row.get('fno_rollover_cost', 0)),
                    fno_rollover_cost_pct=float(row.get('fno_rollover_cost_pct', 0)),
                    fno_rollover_pct=float(row.get('fno_rollover_pct', 0)),
                )

        return len(df)

    def _get_csv_column_for_field(self, field_name, csv_columns):
        """
        Find the matching CSV column for a model field name.
        Handles various naming conventions used by Trendlyne.
        """
        # Direct mappings for special cases
        special_mappings = {
            # SMA fields: CSV has day_sma50, model has day50_sma
            'day5_sma': 'day_sma5',
            'day30_sma': 'day_sma30',
            'day50_sma': 'day_sma50',
            'day100_sma': 'day_sma100',
            'day200_sma': 'day_sma200',

            # EMA fields: CSV has day_ema20, model has day20_ema
            'day12_ema': 'day_ema12',
            'day20_ema': 'day_ema20',
            'day50_ema': 'day_ema50',
            'day100_ema': 'day_ema100',

            # Time period fields: CSV uses abbreviations
            'one_year_low': '1yr_low',
            'one_year_high': '1yr_high',
            'one_year_change_pct': '1yr_change_pct_',
            'three_year_low': '3yr_low',
            'three_year_high': '3yr_high',
            'five_year_low': '5yr_low',
            'five_year_high': '5yr_high',
            'ten_year_low': '10yr_low',
            'ten_year_high': '10yr_high',

            # Volume fields: CSV has different naming
            'three_month_volume_avg': '3month_volume_avg',
            'six_month_volume_avg': '6month_volume_avg',

            # Consolidated volume fields
            'consolidated_eod_volume': 'consolidated_end_of_day_volume',
            'consolidated_prev_eod_volume': 'consolidated_previous_end_of_day_volume',
            'consolidated_5day_avg_eod_volume': 'consolidated_5day_average_end_of_day_volume',
            'consolidated_30day_avg_eod_volume': 'consolidated_30day_average_end_of_day_volume',

            # Pivot point fields: CSV uses "standard_" prefix
            'pivot_point': 'standard_pivot_point',
            'first_resistance_r1': 'standard_resistance_r1',
            'first_resistance_r1_to_price_diff_pct': 'standard_r1_to_price_diff_pct_',
            'second_resistance_r2': 'standard_resistance_r2',
            'second_resistance_r2_to_price_diff_pct': 'standard_r2_to_price_diff_pct_',
            'third_resistance_r3': 'standard_resistance_r3',
            'third_resistance_r3_to_price_diff_pct': 'standard_r3_to_price_diff_pct_',
            'first_support_s1': 'standard_resistance_s1',
            'first_support_s1_to_price_diff_pct': 'standard_s1_to_price_diff_pct_',
            'second_support_s2': 'standard_resistance_s2',
            'second_support_s2_to_price_diff_pct': 'standard_s2_to_price_diff_pct_',
            'third_support_s3': 'standard_resistance_s3',
            'third_support_s3_to_price_diff_pct': 'standard_s3_to_price_diff_pct_',

            # Percentage fields with trailing underscore variations
            'pctdays_traded_below_current_pe_price_to_earnings': 'pct_days_traded_below_current_pe_price_to_earnings',
            'pctdays_traded_below_current_price_to_book_value': 'pct_days_traded_below_current_price_to_book_value',
            'promoter_pledge_pct_qtr': 'promoter_holding_pledge_percentage_pct_qtr',
            'mf_holding_change_3month_pct': 'mf_holding_change_3monthpct_',
        }

        # Check special mappings first
        if field_name in special_mappings:
            csv_col = special_mappings[field_name]
            if csv_col in csv_columns:
                return csv_col

        # Try standard variations
        variations = [
            field_name,                                    # exact match
            field_name + '_',                              # with trailing underscore
            field_name.replace('_pct', '_pct_'),          # percentage fields
            field_name.replace('pctdays', 'pct_days'),    # pctdays variations
        ]

        for variant in variations:
            if variant in csv_columns:
                return variant

        return None

    def parse_stock_data(self, filepath):
        """Parse stock data CSV with comprehensive field mapping for ALL 163 fields"""
        import pandas as pd
        import numpy as np

        self.stdout.write("Parsing stock data CSV...")
        TLStockData.objects.all().delete()
        df = pd.read_csv(filepath)

        # Get all model field names and CSV columns
        model_fields = {f.name: f for f in TLStockData._meta.fields}
        skip_fields = {'id', 'created_at', 'updated_at'}
        csv_columns = set(df.columns)

        self.stdout.write(f"Processing {len(df)} stocks with {len(df.columns)} CSV columns...")

        # Build field mapping once
        field_mapping = {}
        unmapped_fields = []
        for field_name in model_fields:
            if field_name in skip_fields:
                continue
            csv_col = self._get_csv_column_for_field(field_name, csv_columns)
            if csv_col:
                field_mapping[field_name] = csv_col
            else:
                unmapped_fields.append(field_name)

        self.stdout.write(f"  Mapped {len(field_mapping)} fields, {len(unmapped_fields)} fields not in CSV")

        created_count = 0
        error_count = 0

        with transaction.atomic():
            for idx, row in df.iterrows():
                try:
                    # Build kwargs using pre-built mapping
                    kwargs = {}

                    for field_name, csv_col in field_mapping.items():
                        # Get value from CSV
                        value = row[csv_col]

                        # Handle NaN, None, and empty values
                        if pd.isna(value):
                            value = None
                        elif isinstance(value, str):
                            value = value.strip()
                            if value == '' or value.lower() in ['nan', 'null', 'none', '-', 'na', 'n/a']:
                                value = None
                            elif value == 'Export NA':  # Trendlyne specific
                                value = None
                        elif isinstance(value, (int, float)):
                            if np.isinf(value):
                                value = None

                        kwargs[field_name] = value

                    # Create the record with all mapped fields
                    TLStockData.objects.create(**kwargs)
                    created_count += 1

                    if (idx + 1) % 500 == 0:
                        self.stdout.write(f"  Processed {idx + 1}/{len(df)} stocks...")

                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        self.stdout.write(self.style.WARNING(
                            f"  Error on row {idx + 1} ({row.get('nsecode', 'unknown')}): {str(e)[:100]}"
                        ))

        self.stdout.write(self.style.SUCCESS(
            f"✅ Stock data import complete: {created_count} created, {error_count} errors"
        ))

        return created_count

    def parse_option_chains(self, filepath):
        """Parse option chains CSV"""
        import pandas as pd
        from datetime import datetime

        OptionChain.objects.all().delete()
        df = pd.read_csv(filepath)

        with transaction.atomic():
            for _, row in df.iterrows():
                # Parse expiry date with multiple format support
                expiry_str = row.get('expiry_date')
                try:
                    # Try DD-MMM-YYYY format first
                    expiry_date = datetime.strptime(str(expiry_str), '%d-%b-%Y').date()
                except:
                    try:
                        # Try YYYY-MM-DD format
                        expiry_date = datetime.strptime(str(expiry_str), '%Y-%m-%d').date()
                    except:
                        # Try other common formats
                        expiry_date = pd.to_datetime(expiry_str).date()

                OptionChain.objects.create(
                    underlying=row.get('underlying'),
                    expiry_date=expiry_date,
                    strike=float(row.get('strike', 0)),
                    option_type=row.get('option_type'),
                    ltp=float(row.get('ltp', 0)),
                    bid=float(row.get('bid', 0)) if row.get('bid') else None,
                    ask=float(row.get('ask', 0)) if row.get('ask') else None,
                    volume=int(row.get('volume', 0)),
                    oi=int(row.get('oi', 0)),
                    oi_change=int(row.get('oi_change', 0)),
                    iv=float(row.get('iv')) if row.get('iv') and str(row.get('iv')).strip() else None,
                    delta=float(row.get('delta')) if row.get('delta') and str(row.get('delta')).strip() else None,
                    gamma=float(row.get('gamma')) if row.get('gamma') and str(row.get('gamma')).strip() else None,
                    theta=float(row.get('theta')) if row.get('theta') and str(row.get('theta')).strip() else None,
                    vega=float(row.get('vega')) if row.get('vega') and str(row.get('vega')).strip() else None,
                )

        return len(df)

    def parse_events(self, filepath):
        """Parse events CSV"""
        import pandas as pd

        Event.objects.all().delete()
        df = pd.read_csv(filepath)

        with transaction.atomic():
            for _, row in df.iterrows():
                Event.objects.create(
                    event_date=row.get('event_date'),
                    event_time=row.get('event_time'),
                    title=row.get('title'),
                    description=row.get('description', ''),
                    importance=row.get('importance', 'MEDIUM'),
                    country=row.get('country', 'IN'),
                    category=row.get('category', ''),
                    actual=row.get('actual', ''),
                    forecast=row.get('forecast', ''),
                    previous=row.get('previous', ''),
                )

        return len(df)

    def parse_news(self, filepath):
        """Parse news CSV"""
        import pandas as pd
        from datetime import datetime
        from django.utils import timezone
        import uuid

        NewsArticle.objects.all().delete()
        df = pd.read_csv(filepath)

        with transaction.atomic():
            for idx, row in df.iterrows():
                try:
                    # Parse published date
                    published_str = row.get('published_date')
                    if published_str:
                        try:
                            published_at = pd.to_datetime(published_str)
                            # Make timezone aware
                            if published_at.tzinfo is None:
                                published_at = timezone.make_aware(published_at)
                        except:
                            published_at = timezone.now()
                    else:
                        published_at = timezone.now()

                    # Create unique URL if not provided
                    url = row.get('url', '')
                    if not url or pd.isna(url):
                        url = f"https://trendlyne.com/news/{str(uuid.uuid4())[:8]}"

                    NewsArticle.objects.create(
                        title=str(row.get('title', 'Untitled'))[:500],
                        content=str(row.get('content', '')),
                        source=str(row.get('source', 'Unknown'))[:100],
                        published_at=published_at,
                        url=url,
                        summary=str(row.get('content', ''))[:200],
                    )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Skipping news row {idx}: {e}'))

        return NewsArticle.objects.count()

    def parse_investor_calls(self, filepath):
        """Parse investor calls CSV"""
        import pandas as pd
        from datetime import datetime

        InvestorCall.objects.all().delete()
        df = pd.read_csv(filepath)

        with transaction.atomic():
            for idx, row in df.iterrows():
                try:
                    # Parse call date
                    date_str = row.get('date')
                    if date_str:
                        try:
                            call_date = pd.to_datetime(date_str).date()
                        except:
                            call_date = datetime.now().date()
                    else:
                        call_date = datetime.now().date()

                    company = str(row.get('company', 'Unknown'))[:100]
                    symbol = str(row.get('company', 'UNKNOWN')).upper()[:50]
                    title = str(row.get('title', 'Earnings Call'))[:100]
                    transcript = str(row.get('summary', ''))

                    InvestorCall.objects.create(
                        company=company,
                        symbol=symbol,
                        call_type='EARNINGS',
                        call_date=call_date,
                        quarter='',
                        transcript=transcript,
                        executive_summary=transcript[:500],
                    )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Skipping investor call row {idx}: {e}'))

        return InvestorCall.objects.count()

    def parse_knowledge_base(self, filepath):
        """Parse knowledge base CSV"""
        import pandas as pd
        import uuid

        KnowledgeBase.objects.all().delete()
        df = pd.read_csv(filepath, on_bad_lines='skip')

        with transaction.atomic():
            for idx, row in df.iterrows():
                try:
                    title = str(row.get('title', 'Untitled'))[:500]
                    content = str(row.get('content', ''))
                    category = str(row.get('category', 'General'))

                    # Generate unique embedding ID
                    embedding_id = f"kb_{str(uuid.uuid4())[:12]}"

                    KnowledgeBase.objects.create(
                        source_type='MANUAL',
                        source_id=idx + 1,
                        title=title,
                        content_chunk=content,
                        chunk_index=0,
                        metadata={'category': category},
                        embedding_id=embedding_id,
                    )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Skipping KB row {idx}: {e}'))

        return KnowledgeBase.objects.count()

    def clear_files(self):
        """Clear all downloaded files"""
        download_dir = self.get_download_dir()
        if download_dir.exists():
            try:
                shutil.rmtree(download_dir)
                self.stdout.write(self.style.SUCCESS(f'✅ Cleared files: {download_dir}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error clearing files: {e}'))
        else:
            self.stdout.write(self.style.WARNING(f'ℹ️  Directory does not exist: {download_dir}'))

    def clear_database(self):
        """Clear all data from database"""
        models = [
            ContractData, ContractStockData, TLStockData,
            OptionChain, Event, NewsArticle, InvestorCall, KnowledgeBase
        ]

        for model in models:
            count = model.objects.count()
            model.objects.all().delete()
            self.stdout.write(
                self.style.SUCCESS(f'✅ Deleted {count} {model.__name__} records')
            )

    def show_status(self):
        """Show current status of files and database"""
        download_dir = self.get_download_dir()

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('TRENDLYNE DATA STATUS'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

        # File status
        self.stdout.write('📁 Downloaded Files:\n')
        if download_dir.exists():
            files = list(download_dir.glob('*.csv'))
            if files:
                for file in files:
                    size = file.stat().st_size / (1024 * 1024)  # MB
                    self.stdout.write(f'  ✅ {file.name} ({size:.2f} MB)')
            else:
                self.stdout.write('  ⚠️  No files found')
        else:
            self.stdout.write('  ⚠️  Directory does not exist')

        # Database status
        self.stdout.write('\n💾 Database Records:\n')
        models = [
            ('Contract Data', ContractData),
            ('Contract Stock Data', ContractStockData),
            ('Stock Data', TLStockData),
            ('Option Chains', OptionChain),
            ('Events', Event),
            ('News Articles', NewsArticle),
            ('Investor Calls', InvestorCall),
            ('Knowledge Base', KnowledgeBase),
        ]

        for name, model in models:
            count = model.objects.count()
            status = '✅' if count > 0 else '⚠️'
            self.stdout.write(f'  {status} {name}: {count} records')

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70 + '\n'))
