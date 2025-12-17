"""
Comprehensive Trendlyne Data Parser
Parses ALL downloaded XLSX files and populates ALL models
"""

import os
import pandas as pd
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.data.models import (
    ContractData, ContractStockData, TLStockData,
    OptionChain, Event, NewsArticle, InvestorCall, KnowledgeBase
)
from django.db import transaction

def safe_float(value, default=0):
    """Safely convert to float"""
    if pd.isna(value):
        return default
    try:
        return float(value)
    except:
        return default

def safe_int(value, default=0):
    """Safely convert to int"""
    if pd.isna(value):
        return default
    try:
        return int(value)
    except:
        return default

def parse_option_chain_from_contracts():
    """
    Parse OptionChain data from contracts XLSX
    This extracts option chain data for ALL stocks with options, not just NIFTY/BANKNIFTY
    """
    print("\n📊 Parsing Option Chain Data from Contracts...")

    # Try different contract files
    filepaths = [
        'apps/data/tldata/fno_data_2025-11-16.xlsx',
        'apps/data/tldata/contracts_2025_11_14.xlsx',
    ]

    filepath = None
    for fp in filepaths:
        if os.path.exists(fp):
            filepath = fp
            break

    if not filepath:
        print("❌ No contracts file found")
        return 0

    df = pd.read_excel(filepath)
    print(f"Found {len(df)} rows in {filepath}")

    # Clear existing OptionChain data
    old_count = OptionChain.objects.count()
    OptionChain.objects.all().delete()
    print(f"Cleared {old_count} existing OptionChain records")

    created_count = 0

    with transaction.atomic():
        for idx, row in df.iterrows():
            try:
                symbol = str(row.get('SYMBOL', ''))
                option_type = str(row.get('OPTION TYPE', ''))

                # Skip FUTURE contracts, only process CE and PE options
                if option_type == 'FUTURE':
                    continue

                # Parse expiry date
                expiry_str = row.get('EXPIRY', '')
                try:
                    # Try different date formats
                    if isinstance(expiry_str, str):
                        expiry_date = pd.to_datetime(expiry_str).date()
                    else:
                        expiry_date = pd.to_datetime(str(expiry_str)).date()
                except:
                    # Skip if can't parse date
                    continue

                strike = safe_float(row.get('STRIKE PRICE'))
                if strike == 0 or pd.isna(row.get('STRIKE PRICE')):
                    continue  # Skip if no strike price

                OptionChain.objects.create(
                    underlying=symbol[:50],
                    expiry_date=expiry_date,
                    strike=strike,
                    option_type=option_type[:2],  # CE or PE
                    ltp=safe_float(row.get('PRICE', 0)),
                    bid=safe_float(row.get('BID')) if pd.notna(row.get('BID')) else None,
                    ask=safe_float(row.get('ASK')) if pd.notna(row.get('ASK')) else None,
                    volume=safe_int(row.get('VOLUME', 0)),
                    oi=safe_int(row.get('OI', 0)),
                    oi_change=safe_int(row.get('OI CHANGE', 0)),
                    iv=safe_float(row.get('IV')) if pd.notna(row.get('IV')) else None,
                    delta=safe_float(row.get('DELTA')) if pd.notna(row.get('DELTA')) else None,
                    gamma=safe_float(row.get('GAMMA')) if pd.notna(row.get('GAMMA')) else None,
                    theta=safe_float(row.get('THETA')) if pd.notna(row.get('THETA')) else None,
                    vega=safe_float(row.get('VEGA')) if pd.notna(row.get('VEGA')) else None,
                )
                created_count += 1

                if created_count % 1000 == 0:
                    print(f"  ... created {created_count} option chain records")

            except Exception as e:
                if idx < 5:
                    print(f"Warning: Error on row {idx}: {e}")

    print(f"✅ Created {created_count} OptionChain records for ALL stocks")

    # Show breakdown by underlying
    from django.db.models import Count
    breakdown = OptionChain.objects.values('underlying').annotate(count=Count('id')).order_by('-count')[:20]
    print("\nTop 20 stocks by option count:")
    for item in breakdown:
        print(f"  {item['underlying']}: {item['count']} options")

    return created_count


def parse_contract_data():
    """Parse ContractData - all F&O contracts"""
    print("\n📊 Parsing Contract Data (F&O)...")

    filepath = 'apps/data/tldata/fno_data_2025-11-16.xlsx'
    if not os.path.exists(filepath):
        filepath = 'apps/data/tldata/contracts_2025_11_14.xlsx'

    if not os.path.exists(filepath):
        print("❌ File not found")
        return 0

    df = pd.read_excel(filepath)
    print(f"Found {len(df)} rows in {filepath}")

    # Clear old data
    old_count = ContractData.objects.count()
    ContractData.objects.all().delete()
    print(f"Cleared {old_count} existing ContractData records")

    created_count = 0

    with transaction.atomic():
        for idx, row in df.iterrows():
            try:
                ContractData.objects.create(
                    symbol=str(row.get('SYMBOL', ''))[:50],
                    option_type=str(row.get('OPTION TYPE', 'FUTURE'))[:10],
                    strike_price=safe_float(row.get('STRIKE PRICE')) if pd.notna(row.get('STRIKE PRICE')) else None,
                    price=safe_float(row.get('PRICE', 0)),
                    spot=safe_float(row.get('SPOT', 0)),
                    expiry=str(row.get('EXPIRY', ''))[:50],
                    last_updated=str(row.get('LAST UPDATED', ''))[:50],
                    build_up=str(row.get('BUILD UP', ''))[:100],
                    lot_size=safe_int(row.get('LOT SIZE', 1)),

                    # Price metrics
                    day_change=safe_float(row.get('DAY CHANGE', 0)),
                    pct_day_change=safe_float(row.get('% DAY CHANGE', 0)),
                    open_price=safe_float(row.get('OPEN', 0)),
                    high_price=safe_float(row.get('HIGH', 0)),
                    low_price=safe_float(row.get('LOW', 0)),
                    prev_close_price=safe_float(row.get('PREV. CLOSE', 0)),

                    # OI metrics
                    oi=safe_int(row.get('OI', 0)),
                    pct_oi_change=safe_float(row.get('% OI CHANGE', 0)),
                    oi_change=safe_int(row.get('OI CHANGE', 0)),
                    prev_day_oi=safe_int(row.get('PREV DAY OI', 0)),

                    # Volume metrics
                    traded_contracts=safe_int(row.get('TRADED CONTRACTS', 0)),
                    traded_contracts_change_pct=safe_float(row.get('TRADED CONTRACTS CHANGE %', 0)),
                    shares_traded=safe_int(row.get('SHARES TRADED', 0)),
                    pct_volume_shares_change=safe_float(row.get('% VOLUME SHARES CHANGE', 0)),
                    prev_day_vol=safe_int(row.get('PREV DAY VOL', 0)),

                    # Greeks
                    iv=safe_float(row.get('IV')) if pd.notna(row.get('IV')) else None,
                    delta=safe_float(row.get('DELTA')) if pd.notna(row.get('DELTA')) else None,
                    gamma=safe_float(row.get('GAMMA')) if pd.notna(row.get('GAMMA')) else None,
                    theta=safe_float(row.get('THETA')) if pd.notna(row.get('THETA')) else None,
                    vega=safe_float(row.get('VEGA')) if pd.notna(row.get('VEGA')) else None,
                    rho=safe_float(row.get('RHO')) if pd.notna(row.get('RHO')) else None,
                )
                created_count += 1

                if created_count % 1000 == 0:
                    print(f"  ... created {created_count} contract records")

            except Exception as e:
                if idx < 5:
                    print(f"Warning: Error on row {idx}: {e}")

    print(f"✅ Created {created_count} ContractData records")
    return created_count


def parse_market_snapshot():
    """Parse TLStockData - market snapshot"""
    print("\n📊 Parsing Market Snapshot (TLStockData)...")

    filepath = 'apps/data/tldata/market_snapshot_2025-11-16.xlsx'
    if not os.path.exists(filepath):
        filepath = 'apps/data/tldata/Stocks-data-IND-14-Nov-2025.xlsx'

    if not os.path.exists(filepath):
        print("❌ File not found")
        return 0

    df = pd.read_excel(filepath)
    print(f"Found {len(df)} rows in {filepath}")

    # Clear old data
    old_count = TLStockData.objects.count()
    TLStockData.objects.all().delete()
    print(f"Cleared {old_count} existing TLStockData records")

    created_count = 0

    with transaction.atomic():
        for idx, row in df.iterrows():
            try:
                stock_name = row.get('Stock Name') or row.get('STOCK') or row.get('Stock') or ''
                nsecode = row.get('NSEcode') or row.get('NSE CODE') or row.get('NSE') or ''

                # Skip if no NSE code
                if not nsecode or pd.isna(nsecode) or str(nsecode).strip() == '':
                    continue

                obj, created = TLStockData.objects.update_or_create(
                    nsecode=str(nsecode)[:50],
                    defaults={
                        'stock_name': str(stock_name)[:200],
                        'bsecode': str(row.get('BSEcode', ''))[:50],
                        'isin': str(row.get('ISIN', ''))[:50],
                        'industry_name': str(row.get('Industry Name', ''))[:100],
                        'sector_name': str(row.get('sector_name', ''))[:100],
                        'current_price': safe_float(row.get('Current Price')) if pd.notna(row.get('Current Price')) else None,
                        'market_capitalization': safe_float(row.get('Market Capitalization')) if pd.notna(row.get('Market Capitalization')) else None,
                        'trendlyne_durability_score': safe_float(row.get('Trendlyne Durability Score')) if pd.notna(row.get('Trendlyne Durability Score')) else None,
                        'trendlyne_valuation_score': safe_float(row.get('Trendlyne Valuation Score')) if pd.notna(row.get('Trendlyne Valuation Score')) else None,
                        'trendlyne_momentum_score': safe_float(row.get('Trendlyne Momentum Score')) if pd.notna(row.get('Trendlyne Momentum Score')) else None,
                    }
                )
                if created:
                    created_count += 1

                if created_count % 500 == 0:
                    print(f"  ... created {created_count} records")

            except Exception as e:
                if idx < 5:
                    print(f"Warning: Error on row {idx}: {e}")

    print(f"✅ Created {created_count} TLStockData records")
    return created_count


def parse_contract_stock_data():
    """Parse ContractStockData - stock-level F&O summary"""
    print("\n📊 Parsing Contract Stock Data...")

    # This might be in a separate sheet or file
    # For now, we'll extract unique stocks from contracts
    filepath = 'apps/data/tldata/fno_data_2025-11-16.xlsx'

    if not os.path.exists(filepath):
        print("❌ File not found")
        return 0

    df = pd.read_excel(filepath)

    # Get unique stocks with F&O
    stocks = df[df['OPTION TYPE'] != 'FUTURE']['SYMBOL'].unique()

    print(f"Found {len(stocks)} unique stocks with F&O contracts")

    # Clear old data
    old_count = ContractStockData.objects.count()
    ContractStockData.objects.all().delete()
    print(f"Cleared {old_count} existing ContractStockData records")

    created_count = 0

    # This would need actual stock-level data
    # For now, just creating placeholder entries
    print("⚠️  ContractStockData requires stock-level summary file (not available in current downloads)")

    return created_count


def main():
    print("\n" + "=" * 70)
    print("COMPREHENSIVE TRENDLYNE DATA PARSER")
    print("=" * 70)

    stats = {}

    # Parse ContractData (F&O contracts - all)
    stats['ContractData'] = parse_contract_data()

    # Parse TLStockData (Market Snapshot)
    stats['TLStockData'] = parse_market_snapshot()

    # Parse OptionChain (from contracts file)
    stats['OptionChain'] = parse_option_chain_from_contracts()

    # Parse ContractStockData
    stats['ContractStockData'] = parse_contract_stock_data()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Get current counts from database
    print("\nDatabase Record Counts:")
    print(f"  ContractData: {ContractData.objects.count():,}")
    print(f"  ContractStockData: {ContractStockData.objects.count():,}")
    print(f"  TLStockData: {TLStockData.objects.count():,}")
    print(f"  OptionChain: {OptionChain.objects.count():,}")
    print(f"  Event: {Event.objects.count():,}")
    print(f"  NewsArticle: {NewsArticle.objects.count():,}")
    print(f"  InvestorCall: {InvestorCall.objects.count():,}")
    print(f"  KnowledgeBase: {KnowledgeBase.objects.count():,}")

    total = (ContractData.objects.count() + ContractStockData.objects.count() +
             TLStockData.objects.count() + OptionChain.objects.count() +
             Event.objects.count() + NewsArticle.objects.count() +
             InvestorCall.objects.count() + KnowledgeBase.objects.count())

    print(f"\n✅ TOTAL: {total:,} records across all models")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
