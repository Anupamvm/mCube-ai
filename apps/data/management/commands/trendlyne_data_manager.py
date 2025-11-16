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
        """Download all Trendlyne data"""
        try:
            from apps.data.tools.trendlyne_downloader import (
                download_contract_data,
                download_contract_stock_data,
                download_stock_data,
                download_option_chains,
                download_events,
                download_news,
                download_investor_calls,
                download_knowledge_base
            )

            download_dir = self.get_download_dir()
            self.stdout.write(f'\n📁 Download directory: {download_dir}')

            datasets = [
                ('Contract Data', download_contract_data),
                ('Contract Stock Data', download_contract_stock_data),
                ('Stock Data', download_stock_data),
                ('Option Chains', download_option_chains),
                ('Events', download_events),
                ('News Articles', download_news),
                ('Investor Calls', download_investor_calls),
                ('Knowledge Base', download_knowledge_base),
            ]

            for dataset_name, download_func in datasets:
                try:
                    self.stdout.write(f'⬇️  Downloading {dataset_name}...')
                    result = download_func(str(download_dir))
                    if result:
                        self.stdout.write(self.style.SUCCESS(f'   ✅ {dataset_name} downloaded'))
                    else:
                        self.stdout.write(self.style.WARNING(f'   ⚠️  No data for {dataset_name}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'   ❌ {dataset_name} failed: {e}'))

            self.stdout.write(self.style.SUCCESS('\n✅ Download phase complete\n'))

        except ImportError as e:
            raise CommandError(f'Import error: {e}. Ensure trendlyne.py has required functions.')
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

    def parse_contract_data(self, filepath):
        """Parse contract data CSV and populate database"""
        import pandas as pd

        ContractData.objects.all().delete()  # Clear existing data
        df = pd.read_csv(filepath)

        with transaction.atomic():
            for _, row in df.iterrows():
                ContractData.objects.create(
                    symbol=row.get('symbol'),
                    option_type=row.get('option_type'),
                    strike_price=row.get('strike_price'),
                    price=float(row.get('price', 0)),
                    spot=float(row.get('spot', 0)),
                    expiry=row.get('expiry'),
                    last_updated=row.get('last_updated'),
                    build_up=row.get('build_up', ''),
                    lot_size=int(row.get('lot_size', 0)),
                    day_change=float(row.get('day_change', 0)),
                    pct_day_change=float(row.get('pct_day_change', 0)),
                    open_price=float(row.get('open_price', 0)),
                    high_price=float(row.get('high_price', 0)),
                    low_price=float(row.get('low_price', 0)),
                    prev_close_price=float(row.get('prev_close_price', 0)),
                    oi=int(row.get('oi', 0)),
                    pct_oi_change=float(row.get('pct_oi_change', 0)),
                    oi_change=int(row.get('oi_change', 0)),
                    prev_day_oi=int(row.get('prev_day_oi', 0)),
                    traded_contracts=int(row.get('traded_contracts', 0)),
                    traded_contracts_change_pct=float(row.get('traded_contracts_change_pct', 0)),
                    shares_traded=int(row.get('shares_traded', 0)),
                    pct_volume_shares_change=float(row.get('pct_volume_shares_change', 0)),
                    prev_day_vol=int(row.get('prev_day_vol', 0)),
                    basis=row.get('basis'),
                    cost_of_carry=row.get('cost_of_carry'),
                    iv=row.get('iv'),
                    prev_day_iv=row.get('prev_day_iv'),
                    pct_iv_change=row.get('pct_iv_change'),
                    delta=row.get('delta'),
                    vega=row.get('vega'),
                    gamma=row.get('gamma'),
                    theta=row.get('theta'),
                    rho=row.get('rho'),
                )

        return len(df)

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

    def parse_stock_data(self, filepath):
        """Parse stock data CSV"""
        import pandas as pd

        TLStockData.objects.all().delete()
        df = pd.read_csv(filepath)

        with transaction.atomic():
            for _, row in df.iterrows():
                TLStockData.objects.create(
                    stock_name=row.get('stock_name'),
                    nsecode=row.get('nsecode'),
                    bsecode=row.get('bsecode', ''),
                    isin=row.get('isin', ''),
                    industry_name=row.get('industry_name'),
                    sector_name=row.get('sector_name'),
                    current_price=row.get('current_price'),
                    market_capitalization=row.get('market_capitalization'),
                    trendlyne_durability_score=row.get('trendlyne_durability_score'),
                    trendlyne_valuation_score=row.get('trendlyne_valuation_score'),
                    trendlyne_momentum_score=row.get('trendlyne_momentum_score'),
                )

        return len(df)

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
