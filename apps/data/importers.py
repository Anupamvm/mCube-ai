"""
Data import utilities for Trendlyne CSV files

Handles importing scraped data into Django models
"""

import os
import pandas as pd
from datetime import datetime
from django.conf import settings
from django.db import transaction
from decimal import Decimal

from .models import TLStockData, ContractData, ContractStockData


class TrendlyneDataImporter:
    """Import Trendlyne CSV data into Django models"""

    def __init__(self):
        self.base_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')
        self.forecaster_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'trendlynedata')

    @transaction.atomic
    def import_market_snapshot(self, csv_path=None):
        """
        Import market snapshot CSV into TLStockData model

        Args:
            csv_path: Path to CSV file. If None, uses latest file.

        Returns:
            dict: Import statistics
        """
        if csv_path is None:
            # Find latest market snapshot file
            files = [f for f in os.listdir(self.base_dir) if f.startswith('market_snapshot_')]
            if not files:
                return {"error": "No market snapshot files found"}
            files.sort(reverse=True)
            csv_path = os.path.join(self.base_dir, files[0])

        df = pd.read_csv(csv_path)

        created_count = 0
        updated_count = 0
        error_count = 0

        for _, row in df.iterrows():
            try:
                nsecode = row.get('NSE Code', row.get('Stock Code', None))
                if pd.isna(nsecode):
                    error_count += 1
                    continue

                stock_data, created = TLStockData.objects.update_or_create(
                    nsecode=nsecode,
                    defaults=self._map_market_snapshot_row(row)
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                print(f"Error importing row: {e}")
                error_count += 1

        return {
            "created": created_count,
            "updated": updated_count,
            "errors": error_count,
            "total": len(df)
        }

    def _map_market_snapshot_row(self, row):
        """Map CSV row to TLStockData model fields"""
        return {
            'stock_name': self._safe_get(row, 'Stock Name', 'Company'),
            'bsecode': self._safe_get(row, 'BSE Code'),
            'isin': self._safe_get(row, 'ISIN'),
            'current_price': self._safe_float(row, 'LTP', 'Current Price', 'Price'),
            'market_capitalization': self._safe_int(row, 'Market Cap'),
            'sector_name': self._safe_get(row, 'Sector'),
            'industry_name': self._safe_get(row, 'Industry'),

            # Trendlyne Scores
            'trendlyne_durability_score': self._safe_float(row, 'Durability Score', 'Quality Score'),
            'trendlyne_valuation_score': self._safe_float(row, 'Valuation Score'),
            'trendlyne_momentum_score': self._safe_float(row, 'Momentum Score'),

            # Price changes
            'day_change_pct': self._safe_float(row, 'Day Change %', '1D %'),
            'week_change_pct': self._safe_float(row, 'Week Change %', '1W %'),
            'month_change_pct': self._safe_float(row, 'Month Change %', '1M %'),

            # Volume
            'day_volume': self._safe_int(row, 'Volume', 'Day Volume'),

            # Valuation
            'pe_ttm_price_to_earnings': self._safe_float(row, 'PE', 'P/E', 'PE TTM'),
            'price_to_book_value': self._safe_float(row, 'P/B', 'PB', 'Price to Book'),

            # Returns
            'roe_annual_pct': self._safe_float(row, 'ROE', 'ROE %'),
            'roa_annual_pct': self._safe_float(row, 'ROA', 'ROA %'),
        }

    @transaction.atomic
    def import_fno_data(self, csv_path=None):
        """
        Import F&O contracts CSV into ContractData model

        Args:
            csv_path: Path to CSV file. If None, uses latest file.

        Returns:
            dict: Import statistics
        """
        if csv_path is None:
            files = [f for f in os.listdir(self.base_dir) if f.startswith('fno_data_')]
            if not files:
                return {"error": "No F&O data files found"}
            files.sort(reverse=True)
            csv_path = os.path.join(self.base_dir, files[0])

        df = pd.read_csv(csv_path)

        created_count = 0
        updated_count = 0
        error_count = 0

        for _, row in df.iterrows():
            try:
                contract_data = self._map_fno_row(row)

                # Create unique identifier for contract
                contract, created = ContractData.objects.update_or_create(
                    symbol=contract_data['symbol'],
                    option_type=contract_data['option_type'],
                    strike_price=contract_data['strike_price'],
                    expiry=contract_data['expiry'],
                    defaults=contract_data
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                print(f"Error importing F&O row: {e}")
                error_count += 1

        return {
            "created": created_count,
            "updated": updated_count,
            "errors": error_count,
            "total": len(df)
        }

    def _map_fno_row(self, row):
        """Map F&O CSV row to ContractData model fields"""
        return {
            'symbol': self._safe_get(row, 'Symbol', 'Stock'),
            'option_type': self._safe_get(row, 'Type', 'Option Type', 'Instrument'),
            'strike_price': self._safe_float(row, 'Strike', 'Strike Price'),
            'price': self._safe_float(row, 'LTP', 'Price', 'Close'),
            'spot': self._safe_float(row, 'Spot', 'Underlying Price'),
            'expiry': self._safe_get(row, 'Expiry', 'Expiry Date'),
            'last_updated': self._safe_get(row, 'Last Updated', 'Date'),
            'build_up': self._safe_get(row, 'Build Up', ''),
            'lot_size': self._safe_int(row, 'Lot Size', 1),

            # Price metrics
            'day_change': self._safe_float(row, 'Change', 'Day Change'),
            'pct_day_change': self._safe_float(row, '% Change', 'Change %'),
            'open_price': self._safe_float(row, 'Open'),
            'high_price': self._safe_float(row, 'High'),
            'low_price': self._safe_float(row, 'Low'),
            'prev_close_price': self._safe_float(row, 'Prev Close', 'Previous Close'),

            # OI metrics
            'oi': self._safe_int(row, 'OI', 'Open Interest'),
            'pct_oi_change': self._safe_float(row, 'OI Change %', '% OI Change'),
            'oi_change': self._safe_int(row, 'OI Change'),
            'prev_day_oi': self._safe_int(row, 'Prev OI', 'Previous OI'),

            # Volume metrics
            'traded_contracts': self._safe_int(row, 'Volume', 'Traded Contracts'),
            'traded_contracts_change_pct': self._safe_float(row, 'Volume Change %'),
            'shares_traded': self._safe_int(row, 'Shares Traded', 'Qty'),
            'pct_volume_shares_change': self._safe_float(row, 'Shares Change %'),
            'prev_day_vol': self._safe_int(row, 'Prev Volume'),

            # Futures specific
            'basis': self._safe_float(row, 'Basis'),
            'cost_of_carry': self._safe_float(row, 'Cost of Carry'),

            # Options Greeks
            'iv': self._safe_float(row, 'IV', 'Implied Volatility'),
            'prev_day_iv': self._safe_float(row, 'Prev IV'),
            'pct_iv_change': self._safe_float(row, 'IV Change %'),
            'delta': self._safe_float(row, 'Delta'),
            'vega': self._safe_float(row, 'Vega'),
            'gamma': self._safe_float(row, 'Gamma'),
            'theta': self._safe_float(row, 'Theta'),
            'rho': self._safe_float(row, 'Rho'),
        }

    @transaction.atomic
    def import_forecaster_data(self, category=None):
        """
        Import analyst consensus CSV files

        Args:
            category: Specific category to import (e.g., 'High_Bullishness')
                     If None, imports all available categories

        Returns:
            dict: Import statistics per category
        """
        if not os.path.exists(self.forecaster_dir):
            return {"error": "Forecaster directory not found"}

        results = {}

        files = [f for f in os.listdir(self.forecaster_dir) if f.startswith('trendlyne_') and f.endswith('.csv')]

        if category:
            files = [f for f in files if category in f]

        for file in files:
            file_path = os.path.join(self.forecaster_dir, file)
            try:
                result = self._import_forecaster_file(file_path)
                results[file] = result
            except Exception as e:
                results[file] = {"error": str(e)}

        return results

    def _import_forecaster_file(self, file_path):
        """Import a single forecaster CSV file"""
        df = pd.read_csv(file_path)

        updated_count = 0

        # This data is used to enrich existing TLStockData records
        for _, row in df.iterrows():
            try:
                stock_name = self._safe_get(row, 'Stock', 'Company', 'Stock Name')

                # Try to find stock by name
                stock = TLStockData.objects.filter(stock_name__icontains=stock_name).first()

                if stock:
                    # Update with additional data from forecaster
                    updated_fields = {}

                    # Add any additional fields from the forecaster data
                    # This will vary based on the specific forecaster category
                    for col in df.columns:
                        if col.lower() not in ['stock', 'company', 'stock name']:
                            value = self._safe_float(row, col)
                            if value is not None:
                                # Store in a metadata field or specific field if mapped
                                pass

                    if updated_fields:
                        for field, value in updated_fields.items():
                            setattr(stock, field, value)
                        stock.save()
                        updated_count += 1

            except Exception as e:
                print(f"Error processing forecaster row: {e}")
                continue

        return {"updated": updated_count, "total": len(df)}

    # Helper methods
    def _safe_get(self, row, *keys, default=None):
        """Safely get value from row with multiple possible keys"""
        for key in keys:
            if key in row and not pd.isna(row[key]):
                value = row[key]
                if isinstance(value, str):
                    value = value.strip()
                    if value == '' or value.lower() in ['na', 'n/a', '-', 'nan']:
                        continue
                return value
        return default

    def _safe_float(self, row, *keys):
        """Safely convert to float"""
        value = self._safe_get(row, *keys)
        if value is None:
            return None
        try:
            # Remove commas and convert
            if isinstance(value, str):
                value = value.replace(',', '').replace('%', '')
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, row, *keys, default=None):
        """Safely convert to int"""
        value = self._safe_float(row, *keys)
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default


class ContractStockDataImporter:
    """Import stock-level F&O aggregated data"""

    def __init__(self):
        self.base_dir = os.path.join(settings.BASE_DIR, 'apps', 'data', 'tldata')

    @transaction.atomic
    def calculate_and_save_stock_fno_data(self):
        """
        Calculate stock-level F&O metrics from ContractData
        and save to ContractStockData
        """
        from django.db.models import Sum, Avg, Count

        stocks = ContractData.objects.values_list('symbol', flat=True).distinct()

        created_count = 0
        updated_count = 0

        for symbol in stocks:
            try:
                contracts = ContractData.objects.filter(symbol=symbol)

                # Get stock info
                tl_stock = TLStockData.objects.filter(nsecode=symbol).first()

                # Calculate aggregated metrics
                call_contracts = contracts.filter(option_type__in=['CE', 'CALL'])
                put_contracts = contracts.filter(option_type__in=['PE', 'PUT'])

                total_call_oi = call_contracts.aggregate(Sum('oi'))['oi__sum'] or 0
                total_put_oi = put_contracts.aggregate(Sum('oi'))['oi__sum'] or 0
                total_call_vol = call_contracts.aggregate(Sum('traded_contracts'))['traded_contracts__sum'] or 0
                total_put_vol = put_contracts.aggregate(Sum('traded_contracts'))['traded_contracts__sum'] or 0

                # Calculate PCR
                pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
                pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0

                # Get average IV for volatility
                avg_iv = contracts.filter(iv__isnull=False).aggregate(Avg('iv'))['iv__avg'] or 0

                stock_data, created = ContractStockData.objects.update_or_create(
                    nse_code=symbol,
                    defaults={
                        'stock_name': tl_stock.stock_name if tl_stock else symbol,
                        'current_price': tl_stock.current_price if tl_stock else 0,
                        'industry_name': tl_stock.industry_name if tl_stock else '',
                        'annualized_volatility': avg_iv * 100,

                        'fno_total_oi': total_call_oi + total_put_oi,
                        'fno_total_call_oi': total_call_oi,
                        'fno_total_put_oi': total_put_oi,
                        'fno_total_call_vol': total_call_vol,
                        'fno_total_put_vol': total_put_vol,

                        'fno_pcr_oi': pcr_oi,
                        'fno_pcr_vol': pcr_vol,

                        # Placeholder for other fields - update with actual calculations
                        'fno_prev_day_total_oi': 0,
                        'fno_prev_day_call_oi': 0,
                        'fno_prev_day_put_oi': 0,
                        'fno_prev_day_call_vol': 0,
                        'fno_prev_day_put_vol': 0,
                        'fno_pcr_oi_prev': 0,
                        'fno_pcr_vol_prev': 0,
                        'fno_pcr_oi_change_pct': 0,
                        'fno_pcr_vol_change_pct': 0,
                        'fno_mwpl': 0,
                        'fno_mwpl_pct': 0,
                        'fno_mwpl_prev_pct': 0,
                        'fno_total_oi_change_pct': 0,
                        'fno_put_oi_change_pct': 0,
                        'fno_call_oi_change_pct': 0,
                        'fno_put_vol_change_pct': 0,
                        'fno_call_vol_change_pct': 0,
                        'fno_rollover_cost': 0,
                        'fno_rollover_cost_pct': 0,
                        'fno_rollover_pct': 0,
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                print(f"Error calculating stock F&O data for {symbol}: {e}")
                continue

        return {
            "created": created_count,
            "updated": updated_count,
            "total": len(stocks)
        }
