"""
Quick script to parse existing Trendlyne XLSX files and populate database

Run this to populate your database with the real downloaded data:
    python parse_trendlyne_xlsx.py
"""

import os
import pandas as pd
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.data.models import ContractData, ContractStockData, TLStockData
from django.db import transaction

def parse_fno_data():
    """Parse F&O XLSX file"""
    print("📊 Parsing F&O Data...")

    filepath = 'apps/data/tldata/fno_data_2025-11-16.xlsx'
    if not os.path.exists(filepath):
        # Try contracts file
        filepath = 'apps/data/tldata/contracts_2025_11_14.xlsx'

    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return 0

    df = pd.read_excel(filepath)
    print(f"Found {len(df)} rows in {filepath}")

    # Clear existing data
    ContractData.objects.all().delete()
    print("Cleared existing ContractData")

    # Column mapping (adjust based on actual XLSX columns)
    created_count = 0

    with transaction.atomic():
        for idx, row in df.iterrows():
            try:
                ContractData.objects.create(
                    symbol=str(row.get('SYMBOL', ''))[:50],
                    option_type=str(row.get('OPTION TYPE', 'FUTURE'))[:10],
                    strike_price=float(row.get('STRIKE PRICE')) if pd.notna(row.get('STRIKE PRICE')) else None,
                    price=float(row.get('PRICE', 0)) if pd.notna(row.get('PRICE')) else 0,
                    spot=float(row.get('SPOT', 0)) if pd.notna(row.get('SPOT')) else 0,
                    expiry=str(row.get('EXPIRY', ''))[:50],
                    last_updated=str(row.get('LAST UPDATED', ''))[:50],
                    build_up=str(row.get('BUILD UP', ''))[:100],
                    lot_size=int(row.get('LOT SIZE', 1)) if pd.notna(row.get('LOT SIZE')) else 1,

                    # Price metrics (required)
                    day_change=float(row.get('DAY CHANGE', 0)) if pd.notna(row.get('DAY CHANGE')) else 0,
                    pct_day_change=float(row.get('% DAY CHANGE', 0)) if pd.notna(row.get('% DAY CHANGE')) else 0,
                    open_price=float(row.get('OPEN', 0)) if pd.notna(row.get('OPEN')) else 0,
                    high_price=float(row.get('HIGH', 0)) if pd.notna(row.get('HIGH')) else 0,
                    low_price=float(row.get('LOW', 0)) if pd.notna(row.get('LOW')) else 0,
                    prev_close_price=float(row.get('PREV. CLOSE', 0)) if pd.notna(row.get('PREV. CLOSE')) else 0,

                    # OI metrics (required)
                    oi=int(row.get('OI', 0)) if pd.notna(row.get('OI')) else 0,
                    pct_oi_change=float(row.get('% OI CHANGE', 0)) if pd.notna(row.get('% OI CHANGE')) else 0,
                    oi_change=int(row.get('OI CHANGE', 0)) if pd.notna(row.get('OI CHANGE')) else 0,
                    prev_day_oi=int(row.get('PREV DAY OI', 0)) if pd.notna(row.get('PREV DAY OI')) else 0,

                    # Volume metrics (required)
                    traded_contracts=int(row.get('TRADED CONTRACTS', 0)) if pd.notna(row.get('TRADED CONTRACTS')) else 0,
                    traded_contracts_change_pct=float(row.get('TRADED CONTRACTS CHANGE %', 0)) if pd.notna(row.get('TRADED CONTRACTS CHANGE %')) else 0,
                    shares_traded=int(row.get('SHARES TRADED', 0)) if pd.notna(row.get('SHARES TRADED')) else 0,
                    pct_volume_shares_change=float(row.get('% VOLUME SHARES CHANGE', 0)) if pd.notna(row.get('% VOLUME SHARES CHANGE')) else 0,
                    prev_day_vol=int(row.get('PREV DAY VOL', 0)) if pd.notna(row.get('PREV DAY VOL')) else 0,

                    # Greeks (optional)
                    iv=float(row.get('IV')) if pd.notna(row.get('IV')) else None,
                    delta=float(row.get('DELTA')) if pd.notna(row.get('DELTA')) else None,
                    gamma=float(row.get('GAMMA')) if pd.notna(row.get('GAMMA')) else None,
                    theta=float(row.get('THETA')) if pd.notna(row.get('THETA')) else None,
                    vega=float(row.get('VEGA')) if pd.notna(row.get('VEGA')) else None,
                    rho=float(row.get('RHO')) if pd.notna(row.get('RHO')) else None,
                )
                created_count += 1

                if created_count % 1000 == 0:
                    print(f"  ... created {created_count} records")

            except Exception as e:
                if idx < 5:  # Only show first few errors
                    print(f"Warning: Error on row {idx}: {e}")

    print(f"✅ Created {created_count} ContractData records")
    return created_count


def parse_market_snapshot():
    """Parse Market Snapshot XLSX file"""
    print("\n📊 Parsing Market Snapshot...")

    filepath = 'apps/data/tldata/market_snapshot_2025-11-16.xlsx'
    if not os.path.exists(filepath):
        # Try Stocks-data file
        filepath = 'apps/data/tldata/Stocks-data-IND-14-Nov-2025.xlsx'

    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return 0

    df = pd.read_excel(filepath)
    print(f"Found {len(df)} rows in {filepath}")

    # Clear existing data
    TLStockData.objects.all().delete()
    print("Cleared existing TLStockData")

    created_count = 0

    with transaction.atomic():
        for idx, row in df.iterrows():
            try:
                # Get stock name - try different column names
                stock_name = row.get('Stock Name') or row.get('STOCK') or row.get('Stock') or ''
                nsecode = row.get('NSEcode') or row.get('NSE CODE') or row.get('NSE') or ''

                # Skip if no NSE code (required unique field)
                if not nsecode or pd.isna(nsecode) or str(nsecode).strip() == '':
                    continue

                # Use update_or_create to handle duplicates
                obj, created = TLStockData.objects.update_or_create(
                    nsecode=str(nsecode)[:50],
                    defaults={
                        'stock_name': str(stock_name)[:200],
                        'bsecode': str(row.get('BSEcode', ''))[:50],
                        'isin': str(row.get('ISIN', ''))[:50],
                        'industry_name': str(row.get('Industry Name', ''))[:100],
                        'sector_name': str(row.get('sector_name', ''))[:100],
                        'current_price': float(row.get('Current Price', 0)) if pd.notna(row.get('Current Price')) else None,
                        'market_capitalization': float(row.get('Market Capitalization', 0)) if pd.notna(row.get('Market Capitalization')) else None,
                        'trendlyne_durability_score': float(row.get('Trendlyne Durability Score', 0)) if pd.notna(row.get('Trendlyne Durability Score')) else None,
                        'trendlyne_valuation_score': float(row.get('Trendlyne Valuation Score', 0)) if pd.notna(row.get('Trendlyne Valuation Score')) else None,
                        'trendlyne_momentum_score': float(row.get('Trendlyne Momentum Score', 0)) if pd.notna(row.get('Trendlyne Momentum Score')) else None,
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


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("TRENDLYNE XLSX DATA PARSER")
    print("=" * 70 + "\n")

    total = 0
    total += parse_fno_data()
    total += parse_market_snapshot()

    print("\n" + "=" * 70)
    print(f"✅ TOTAL: {total} records populated across all models")
    print("=" * 70 + "\n")
