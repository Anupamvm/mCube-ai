"""
Trendlyne Data Fetcher Service

A service that fetches Trendlyne data with real-time logging support.
Used by the SSE endpoint to stream logs to the frontend.
"""

import os
import time
import threading
import queue
from datetime import datetime
from typing import Callable, Optional, Dict, Any
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.data.models import ContractData, ContractStockData


class TrendlyneLogCallback:
    """Manages log callbacks for real-time streaming"""

    def __init__(self):
        self.log_queue = queue.Queue()
        self.is_running = True

    def log(self, message: str, level: str = "info"):
        """Add a log message to the queue"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put({
            "timestamp": timestamp,
            "level": level,
            "message": message
        })

    def info(self, message: str):
        self.log(message, "info")

    def success(self, message: str):
        self.log(message, "success")

    def warning(self, message: str):
        self.log(message, "warning")

    def error(self, message: str):
        self.log(message, "error")

    def get_logs(self, timeout: float = 0.5):
        """Get all available logs from the queue"""
        logs = []
        try:
            while True:
                log = self.log_queue.get(timeout=timeout)
                logs.append(log)
        except queue.Empty:
            pass
        return logs

    def stop(self):
        self.is_running = False


class TrendlyneDataFetcher:
    """
    Fetches Trendlyne data with real-time logging support.

    Usage:
        callback = TrendlyneLogCallback()
        fetcher = TrendlyneDataFetcher(callback)

        # Run in a thread
        thread = threading.Thread(target=fetcher.fetch_fno_data)
        thread.start()

        # Stream logs
        while thread.is_alive():
            logs = callback.get_logs()
            for log in logs:
                yield log
    """

    def __init__(self, log_callback: Optional[TrendlyneLogCallback] = None):
        self.log_callback = log_callback or TrendlyneLogCallback()
        # Use trendlyne_data directory for downloads
        self.download_dir = Path(settings.BASE_DIR) / 'trendlyne_data'
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.result = {"success": False, "error": None, "data": None}

    def log(self, message: str, level: str = "info"):
        """Log a message"""
        if self.log_callback:
            self.log_callback.log(message, level)

    def fetch_fno_data(self) -> Dict[str, Any]:
        """
        Complete workflow to fetch ALL Trendlyne data:
        1. Initialize browser & Login
        2. Download F&O contracts data
        3. Download Market Snapshot (Stock data)
        4. Fetch Forecaster data (21 screeners)
        5. Parse and save all to database
        6. Cleanup
        """
        try:
            self.log("Starting Trendlyne FULL data fetch...", "info")
            self.log("=" * 60, "info")

            # Step 1: Initialize
            self.log("[1/6] Initializing browser...", "info")
            from apps.data.providers.trendlyne import TrendlyneProvider

            provider = TrendlyneProvider(
                headless=True,
                download_dir=str(self.download_dir)
            )

            self.log("Browser initialized successfully", "success")

            # Step 2: Login
            self.log("[2/6] Logging into Trendlyne...", "info")
            provider.init_driver(download_dir=str(self.download_dir))

            self.log("Navigating to Trendlyne homepage...", "info")

            try:
                if provider.login():
                    self.log("Login successful!", "success")
                else:
                    self.log("Login failed - check credentials", "error")
                    self.result = {"success": False, "error": "Login failed"}
                    provider.cleanup()
                    return self.result
            except Exception as e:
                self.log(f"Login error: {str(e)}", "error")
                self.result = {"success": False, "error": f"Login error: {str(e)}"}
                provider.cleanup()
                return self.result

            # Track results
            results_summary = {
                "fno_contracts": 0,
                "stock_data": 0,
                "forecaster_screeners": 0
            }

            # ============ PART A: F&O Contracts Data ============
            self.log("[3/6] Downloading F&O contracts data...", "info")
            self.log(f"Download directory: {self.download_dir}", "info")

            try:
                fno_result = provider.fetch_fno_data(download_dir=str(self.download_dir))

                if fno_result.get('success'):
                    self.log(f"F&O data downloaded: {fno_result.get('filename')}", "success")

                    # Parse and save F&O data
                    self.log("Parsing F&O contracts...", "info")
                    fno_records = self._parse_and_save_fno_data(fno_result.get('path'))
                    results_summary["fno_contracts"] = fno_records
                    self.log(f"Saved {fno_records} F&O contract records", "success")
                else:
                    self.log(f"F&O download failed: {fno_result.get('error')}", "warning")

            except Exception as e:
                self.log(f"F&O fetch error: {str(e)}", "warning")

            # ============ PART B: Market Snapshot (Stock Data) ============
            self.log("[4/6] Downloading Market Snapshot (Stock data)...", "info")

            try:
                # First check if we already have a stock data file downloaded
                import os
                stock_file_path = None
                all_files = os.listdir(str(self.download_dir))
                stock_files = [f for f in all_files if f.startswith("Stocks-data") and (f.endswith(".xlsx") or f.endswith(".csv"))]

                if stock_files:
                    # Use the most recent stock data file
                    stock_files.sort(key=lambda x: os.path.getctime(os.path.join(str(self.download_dir), x)), reverse=True)
                    stock_file_path = os.path.join(str(self.download_dir), stock_files[0])
                    self.log(f"Found existing stock data file: {stock_files[0]}", "info")

                if not stock_file_path:
                    # Try to download via provider
                    snapshot_result = provider.fetch_market_snapshot(download_dir=str(self.download_dir))
                    self.log(f"Market Snapshot result: {snapshot_result}", "info")

                    if snapshot_result.get('success'):
                        stock_file_path = snapshot_result.get('path')
                        self.log(f"Market Snapshot downloaded: {snapshot_result.get('filename')}", "success")
                    else:
                        self.log(f"Market Snapshot download failed: {snapshot_result.get('error')}", "warning")
                        # Check again for any stock files that may have been downloaded
                        all_files = os.listdir(str(self.download_dir))
                        stock_files = [f for f in all_files if f.startswith("Stocks-data") and (f.endswith(".xlsx") or f.endswith(".csv"))]
                        if stock_files:
                            stock_files.sort(key=lambda x: os.path.getctime(os.path.join(str(self.download_dir), x)), reverse=True)
                            stock_file_path = os.path.join(str(self.download_dir), stock_files[0])
                            self.log(f"Found stock data file after download attempt: {stock_files[0]}", "info")

                if stock_file_path:
                    self.log(f"Processing stock data from: {stock_file_path}", "info")
                    # Parse and save stock data
                    self.log("Parsing stock data...", "info")
                    stock_records = self._parse_and_save_stock_data(stock_file_path)
                    results_summary["stock_data"] = stock_records
                    self.log(f"Saved {stock_records} stock records to TLStockData", "success")
                else:
                    self.log("No stock data file found - stock data will not be updated", "warning")

            except Exception as e:
                self.log(f"Market Snapshot fetch error: {str(e)}", "error")
                import traceback
                self.log(f"Traceback: {traceback.format_exc()[:500]}", "error")

            # ============ PART C: Forecaster Data (21 screeners) ============
            self.log("[5/6] Fetching Forecaster data (21 screeners)...", "info")

            try:
                forecaster_dir = str(self.download_dir / 'forecaster')
                forecaster_result = provider.fetch_forecaster_data(output_dir=forecaster_dir)

                success_count = sum(1 for r in forecaster_result.values() if r.get('success'))
                total_count = len(forecaster_result)
                results_summary["forecaster_screeners"] = success_count

                self.log(f"Forecaster: {success_count}/{total_count} screeners fetched", "success")

                # Log individual screener results
                for label, result in forecaster_result.items():
                    if result.get('success'):
                        self.log(f"  ✓ {label}: {result.get('rows', 0)} rows", "info")
                    else:
                        self.log(f"  ✗ {label}: {result.get('error', 'Unknown error')}", "warning")

            except Exception as e:
                self.log(f"Forecaster fetch error: {str(e)}", "warning")

            # Step 6: Cleanup
            self.log("[6/6] Cleaning up...", "info")
            provider.cleanup()
            self.log("Browser closed", "info")

            # Cleanup old files
            self._cleanup_files()

            self.log("=" * 60, "info")
            self.log("TRENDLYNE DATA FETCH SUMMARY:", "success")
            self.log(f"  F&O Contracts: {results_summary['fno_contracts']} records", "info")
            self.log(f"  Stock Data: {results_summary['stock_data']} records", "info")
            self.log(f"  Forecaster Screeners: {results_summary['forecaster_screeners']}/21", "info")
            self.log("=" * 60, "info")
            self.log("Trendlyne data fetch completed!", "success")

            self.result = {
                "success": True,
                "data": results_summary
            }
            return self.result

        except Exception as e:
            self.log(f"Unexpected error: {str(e)}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            self.result = {"success": False, "error": str(e)}
            return self.result
        finally:
            self.log_callback.stop()

    def _parse_and_save_fno_data(self, filepath: str) -> int:
        """Parse F&O Excel/CSV file and save to database"""
        import pandas as pd
        import numpy as np

        # Determine file type and read accordingly
        if filepath.endswith('.xlsx'):
            self.log(f"Reading Excel file: {filepath}", "info")
            df = pd.read_excel(filepath)
        else:
            self.log(f"Reading CSV file: {filepath}", "info")
            df = pd.read_csv(filepath)

        self.log(f"Found {len(df)} contracts in file", "info")
        self.log(f"Columns in file: {list(df.columns)[:10]}...", "info")

        # Column mapping from Excel headers to model fields
        column_mapping = {
            'SYMBOL': 'symbol',
            'OPTION TYPE': 'option_type',
            'STRIKE PRICE': 'strike_price',
            'PRICE': 'price',
            'SPOT': 'spot',
            'EXPIRY': 'expiry',
            'LAST UPDATED': 'last_updated',
            'BUILD UP': 'build_up',
            'LOT SIZE': 'lot_size',
            'DAY CHANGE': 'day_change',
            '%DAY CHANGE': 'pct_day_change',
            'OPEN PRICE': 'open_price',
            'HIGH PRICE': 'high_price',
            'LOW PRICE': 'low_price',
            'PREV CLOSE PRICE': 'prev_close_price',
            'OI': 'oi',
            '%OI CHANGE': 'pct_oi_change',
            'OI CHANGE': 'oi_change',
            'PREV DAY OI': 'prev_day_oi',
            'TRADED CONTRACTS': 'traded_contracts',
            'TRADED CONTRACTS CHANGE%': 'traded_contracts_change_pct',
            'SHARES TRADED': 'shares_traded',
            '%VOLUME SHARES CHANGE': 'pct_volume_shares_change',
            'PREV DAY VOL': 'prev_day_vol',
            'BASIS': 'basis',
            'COST OF CARRY (CoC)': 'cost_of_carry',
            'IV': 'iv',
            'PREV DAY IV': 'prev_day_iv',
            '%IV CHANGE': 'pct_iv_change',
            'DELTA': 'delta',
            'VEGA': 'vega',
            'GAMMA': 'gamma',
            'THETA': 'theta',
            'RHO': 'rho',
        }

        # Rename columns to match model fields
        df = df.rename(columns=column_mapping)

        # Convert expiry to string format (YYYY-MM-DD)
        if 'expiry' in df.columns:
            df['expiry'] = pd.to_datetime(df['expiry']).dt.strftime('%Y-%m-%d')

        # Convert last_updated to string
        if 'last_updated' in df.columns:
            df['last_updated'] = df['last_updated'].astype(str)

        # Clear existing data
        self.log("Clearing existing contract data...", "info")
        ContractData.objects.all().delete()

        created_count = 0
        error_count = 0

        self.log("Importing contracts to database...", "info")

        # Get model field names
        model_fields = {f.name for f in ContractData._meta.fields}
        skip_fields = {'id', 'created_at', 'updated_at'}

        with transaction.atomic():
            for idx, row in df.iterrows():
                try:
                    kwargs = {}

                    for col in df.columns:
                        if col in skip_fields or col not in model_fields:
                            continue

                        value = row[col]

                        # Handle NaN/None values
                        if pd.isna(value):
                            value = None
                        elif isinstance(value, str):
                            value = value.strip()
                            if value == '' or value.lower() in ['nan', 'null', 'none', '-', 'na', 'n/a']:
                                value = None
                        elif isinstance(value, (int, float)):
                            if np.isinf(value):
                                value = None

                        kwargs[col] = value

                    # Ensure required fields have default values
                    if kwargs.get('build_up') is None:
                        kwargs['build_up'] = ''

                    ContractData.objects.create(**kwargs)
                    created_count += 1

                    if (idx + 1) % 1000 == 0:
                        self.log(f"Processed {idx + 1}/{len(df)} contracts...", "info")

                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        self.log(f"Error on row {idx + 1}: {str(e)[:100]}", "warning")

        self.log(f"Import complete: {created_count} created, {error_count} errors", "info")
        return created_count

    def _parse_and_save_stock_data(self, filepath: str) -> int:
        """Parse Market Snapshot Excel/CSV file and save to TLStockData model"""
        import pandas as pd
        import numpy as np
        from apps.data.models import TLStockData

        # Determine file type and read accordingly
        if filepath.endswith('.xlsx'):
            self.log(f"Reading Excel file: {filepath}", "info")
            df = pd.read_excel(filepath)
        else:
            self.log(f"Reading CSV file: {filepath}", "info")
            df = pd.read_csv(filepath)

        self.log(f"Found {len(df)} stocks in file", "info")
        self.log(f"Columns in file ({len(df.columns)}): {list(df.columns)[:10]}...", "info")

        # Comprehensive column mapping from Excel headers to model fields
        column_mapping = {
            'Stock Name': 'stock_name',
            'NSEcode': 'nsecode',
            'BSEcode': 'bsecode',
            'ISIN': 'isin',
            'Industry Name': 'industry_name',
            'sector_name': 'sector_name',
            'Current Price': 'current_price',
            'Market Capitalization': 'market_capitalization',
            # Trendlyne Scores
            'Trendlyne Durability Score': 'trendlyne_durability_score',
            'Trendlyne Valuation Score': 'trendlyne_valuation_score',
            'Trendlyne Momentum Score': 'trendlyne_momentum_score',
            'DVM_classification_text': 'dvm_classification_text',
            'Prev Day Trendlyne Durability Score': 'prev_day_trendlyne_durability_score',
            'Prev Day Trendlyne Valuation Score': 'prev_day_trendlyne_valuation_score',
            'Prev Day Trendlyne Momentum Score': 'prev_day_trendlyne_momentum_score',
            'Prev Week Trendlyne Durability Score': 'prev_week_trendlyne_durability_score',
            'Prev Week Trendlyne Valuation Score': 'prev_week_trendlyne_valuation_score',
            'Prev Week Trendlyne Momentum Score': 'prev_week_trendlyne_momentum_score',
            'Prev Month Trendlyne Durability Score': 'prev_month_trendlyne_durability_score',
            'Prev Month Trendlyne Valuation Score': 'prev_month_trendlyne_valuation_score',
            'Prev Month Trendlyne Momentum Score': 'prev_month_trendlyne_momentum_score',
            'Normalized Momentum Score': 'normalized_momentum_score',
            # Financial Metrics - Quarterly
            'Operating Revenue Qtr': 'operating_revenue_qtr',
            'Net Profit Qtr': 'net_profit_qtr',
            'Revenue QoQ Growth %': 'revenue_qoq_growth_pct',
            'Revenue Growth Qtr YoY %': 'revenue_growth_qtr_yoy_pct',
            'Net Profit Qtr Growth YoY %': 'net_profit_qtr_growth_yoy_pct',
            'Net Profit QoQ Growth %': 'net_profit_qoq_growth_pct',
            'Operating Profit Margin Qtr %': 'operating_profit_margin_qtr_pct',
            'Operating Profit Margin Qtr 4Qtr ago %': 'operating_profit_margin_qtr_1yr_ago_pct',
            # Sector comparisons
            'Sector Revenue Growth Qtr YoY %': 'sector_revenue_growth_qtr_yoy_pct',
            'Sector Net Profit Growth Qtr YoY %': 'sector_net_profit_growth_qtr_yoy_pct',
            'Sector Revenue Growth Qtr QoQ %': 'sector_revenue_growth_qtr_qoq_pct',
            'Sector Net Profit Growth Qtr QoQ %': 'sector_net_profit_growth_qtr_qoq_pct',
            # Financial Metrics - TTM & Annual
            'Operating Revenue TTM': 'operating_revenue_ttm',
            'Net profit TTM': 'net_profit_ttm',
            'Operating Revenue Annual': 'operating_revenue_annual',
            'Net Profit Annual': 'net_profit_annual',
            'Revenue Growth Annual YoY %': 'revenue_growth_annual_yoy_pct',
            'Net Profit Annual YoY Growth %': 'net_profit_annual_yoy_growth_pct',
            'Sector Revenue Growth Annual YoY %': 'sector_revenue_growth_annual_yoy_pct',
            # Cash Flow
            'Cash from Financing Annual Activity': 'cash_from_financing_annual_activity',
            'Cash from Investing Activity Annual': 'cash_from_investing_activity_annual',
            'Cash from Operating Activity Annual': 'cash_from_operating_activity_annual',
            'Net Cash Flow Annual': 'net_cash_flow_annual',
            # Latest Results
            'Latest financial result': 'latest_financial_result',
            'Result Announced Date': 'result_announced_date',
            # Valuation - P/E
            'PE TTM Price to Earnings': 'pe_ttm_price_to_earnings',
            'Forecaster Estimates 1Y forward PE': 'forecaster_estimates_1y_forward_pe',
            'PE 3Yr Average': 'pe_3yr_average',
            'PE 5Yr Average': 'pe_5yr_average',
            '%Days traded below current PE Price to Earnings': 'pctdays_traded_below_current_pe_price_to_earnings',
            'Sector PE TTM': 'sector_pe_ttm',
            'Industry PE TTM': 'industry_pe_ttm',
            # Valuation - PEG
            'PEG TTM PE to Growth': 'peg_ttm_pe_to_growth',
            'Forecaster Estimates 1Y forward PEG': 'forecaster_estimates_1y_forward_peg',
            'Sector PEG TTM': 'sector_peg_ttm',
            'Industry PEG TTM': 'industry_peg_ttm',
            # Valuation - Price to Book
            'Price to Book Value Adjusted': 'price_to_book_value',
            '%Days traded below current Price to Book Value': 'pctdays_traded_below_current_price_to_book_value',
            'Sector Price to Book TTM': 'sector_price_to_book_ttm',
            'Industry Price to Book TTM': 'industry_price_to_book_ttm',
            # EPS
            'Basic EPS TTM': 'basic_eps_ttm',
            'EPS TTM Growth %': 'eps_ttm_growth_pct',
            # Returns & Quality
            'ROE Annual %': 'roe_annual_pct',
            'Sector Return on Equity ROE': 'sector_return_on_equity_roe',
            'Industry Return on Equity ROE': 'industry_return_on_equity_roe',
            'RoA Annual %': 'roa_annual_pct',
            'Sector Return on Assets': 'sector_return_on_assets',
            'Industry Return on Assets': 'industry_return_on_assets',
            'Piotroski Score': 'piotroski_score',
            # Technical Indicators
            'Day MFI': 'day_mfi',
            'Day RSI': 'day_rsi',
            'Day MACD': 'day_macd',
            'Day MACD Signal Line': 'day_macd_signal_line',
            'Day ATR': 'day_atr',
            'Day ADX': 'day_adx',
            'Day ROC21': 'day_roc21',
            'Day ROC125': 'day_roc125',
            # Moving Averages - SMA
            'Day SMA5': 'day5_sma',
            'Day SMA30': 'day30_sma',
            'Day SMA50': 'day50_sma',
            'Day SMA100': 'day100_sma',
            'Day SMA200': 'day200_sma',
            # Moving Averages - EMA
            'Day EMA12': 'day12_ema',
            'Day EMA20': 'day20_ema',
            'Day EMA50': 'day50_ema',
            'Day EMA100': 'day100_ema',
            # Beta
            'Beta 1Month': 'beta_1month',
            'Beta 3Month': 'beta_3month',
            'Beta 1Year': 'beta_1year',
            'Beta 3Year': 'beta_3year',
            # Support & Resistance
            'Standard Pivot point': 'pivot_point',
            'Standard resistance R1': 'first_resistance_r1',
            'Standard R1 to Price Diff %': 'first_resistance_r1_to_price_diff_pct',
            'Standard resistance R2': 'second_resistance_r2',
            'Standard R2 to Price Diff %': 'second_resistance_r2_to_price_diff_pct',
            'Standard resistance R3': 'third_resistance_r3',
            'Standard R3 to Price Diff %': 'third_resistance_r3_to_price_diff_pct',
            'Standard resistance S1': 'first_support_s1',
            'Standard S1 to Price Diff %': 'first_support_s1_to_price_diff_pct',
            'Standard resistance S2': 'second_support_s2',
            'Standard S2 to Price Diff %': 'second_support_s2_to_price_diff_pct',
            'Standard resistance S3': 'third_support_s3',
            'Standard S3 to Price Diff %': 'third_support_s3_to_price_diff_pct',
            # Price Ranges & Changes
            'Day Low': 'day_low',
            'Day High': 'day_high',
            'Day change %': 'day_change_pct',
            'Week Low': 'week_low',
            'Week High': 'week_high',
            'Week change %': 'week_change_pct',
            'Month Low': 'month_low',
            'Month High': 'month_high',
            'Month Change %': 'month_change_pct',
            'Qtr Low': 'qtr_low',
            'Qtr High': 'qtr_high',
            'Qtr Change %': 'qtr_change_pct',
            '1Yr Low': 'one_year_low',
            '1Yr High': 'one_year_high',
            '1Yr change %': 'one_year_change_pct',
            '3Yr Low': 'three_year_low',
            '3Yr High': 'three_year_high',
            'three_year_changeP': 'three_year_changep',
            '5Yr Low': 'five_year_low',
            '5Yr High': 'five_year_high',
            'five_year_changeP': 'five_year_changep',
            '10Yr Low': 'ten_year_low',
            '10Yr High': 'ten_year_high',
            'ten_year_changeP': 'ten_year_changep',
            # Volume Data
            'Day Volume': 'day_volume',
            'Week Volume Avg': 'week_volume_avg',
            'Month Volume Avg': 'month_volume_avg',
            '3Month Volume Avg': 'three_month_volume_avg',
            '6Month Volume Avg': 'six_month_volume_avg',
            'Consolidated end of day volume': 'consolidated_eod_volume',
            'Consolidated previous end of day volume': 'consolidated_prev_eod_volume',
            'Consolidated 5day average end of day volume': 'consolidated_5day_avg_eod_volume',
            'Consolidated 30day average end of day volume': 'consolidated_30day_avg_eod_volume',
            'Day volume multiple of week': 'day_volume_multiple_of_week',
            'vol_day_times_vol_week_str': 'vol_day_times_vol_week_str',
            'Consolidated day Volume': 'consolidated_day_volume',
            'VWAP Day': 'vwap_day',
            # Delivery Data  - note: missing some in model, we'll skip those
            # 'Delivery Volume % end of day': 'delivery_volume_pct_eod',
            # Holdings - Promoter
            'Promoter holding latest %': 'promoter_holding_latest_pct',
            'Promoter holding change QoQ %': 'promoter_holding_change_qoq_pct',
            'Promoter holding change 4Qtr %': 'promoter_holding_change_4qtr_pct',
            'Promoter holding change 8Qtr %': 'promoter_holding_change_8qtr_pct',
            'Promoter holding pledge percentage % Qtr': 'promoter_pledge_pct_qtr',
            'Promoter pledge change QoQ %': 'promoter_pledge_change_qoq_pct',
            # Holdings - Mutual Funds
            'MF holding current Qtr %': 'mf_holding_current_qtr_pct',
            'MF holding change QoQ %': 'mf_holding_change_qoq_pct',
            'MF holding change 1Month %': 'mf_holding_change_1month_pct',
            'MF holding change 2Month %': 'mf_holding_change_2month_pct',
            'MF holding change 3Month%': 'mf_holding_change_3month_pct',
            'MF holding change 4Qtr %': 'mf_holding_change_4qtr_pct',
            'MF holding change 8Qtr %': 'mf_holding_change_8qtr_pct',
            # Holdings - FII
            'FII holding current Qtr %': 'fii_holding_current_qtr_pct',
            'FII holding change QoQ %': 'fii_holding_change_qoq_pct',
            'FII holding change 4Qtr %': 'fii_holding_change_4qtr_pct',
            'FII holding change 8Qtr %': 'fii_holding_change_8qtr_pct',
            # Holdings - Institutional
            'Institutional holding current Qtr %': 'institutional_holding_current_qtr_pct',
            'Institutional holding change QoQ %': 'institutional_holding_change_qoq_pct',
            'Institutional holding change 4Qtr %': 'institutional_holding_change_4qtr_pct',
            'Institutional holding change 8Qtr %': 'institutional_holding_change_8qtr_pct',
        }

        # Rename columns to model field names
        df = df.rename(columns=column_mapping)

        self.log(f"Mapped columns: {list(df.columns)[:10]}...", "info")

        # Clear existing data
        self.log("Clearing existing stock data...", "info")
        TLStockData.objects.all().delete()

        # Get model field names
        model_fields = {f.name for f in TLStockData._meta.fields}
        skip_fields = {'id', 'created_at', 'updated_at'}

        created_count = 0
        error_count = 0

        self.log("Importing stock data to database...", "info")

        # List of NA indicators to convert to None
        na_indicators = {'nan', 'null', 'none', '-', 'na', 'n/a', 'export na', '#n/a', '#value!', '#div/0!', '#ref!', ''}

        with transaction.atomic():
            for idx, row in df.iterrows():
                try:
                    kwargs = {}

                    for col in df.columns:
                        if col in skip_fields or col not in model_fields:
                            continue

                        value = row[col]

                        # Handle NaN/None values and invalid strings
                        if pd.isna(value):
                            value = None
                        elif isinstance(value, str):
                            value = value.strip()
                            # Handle various NA indicators including "Export NA" from Trendlyne
                            if value.lower() in na_indicators:
                                value = None
                        elif isinstance(value, (int, float)):
                            if np.isinf(value):
                                value = None

                        kwargs[col] = value

                    # Need at least nsecode or stock_name
                    if not kwargs.get('nsecode') and not kwargs.get('stock_name'):
                        continue

                    TLStockData.objects.create(**kwargs)
                    created_count += 1

                    if (idx + 1) % 500 == 0:
                        self.log(f"Processed {idx + 1}/{len(df)} stocks...", "info")

                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        self.log(f"Error on row {idx + 1}: {str(e)[:150]}", "warning")

        self.log(f"Stock import complete: {created_count} created, {error_count} errors", "info")
        return created_count

    def _cleanup_files(self):
        """Clean up old downloaded files (keep recent ones)"""
        try:
            # Only clean up files older than 7 days to save space
            # but keep recent downloads for debugging
            import time
            cutoff_time = time.time() - (7 * 24 * 60 * 60)  # 7 days ago

            if self.download_dir.exists():
                for f in self.download_dir.iterdir():
                    if f.is_file() and f.stat().st_mtime < cutoff_time:
                        f.unlink()
                        self.log(f"Cleaned up old file: {f.name}", "info")
        except Exception as e:
            self.log(f"Warning: Could not clean up files: {e}", "warning")


# Global storage for active fetch sessions
_active_sessions: Dict[str, TrendlyneLogCallback] = {}


def start_trendlyne_fetch(session_id: str) -> TrendlyneLogCallback:
    """
    Start a new Trendlyne fetch session in a background thread.
    Returns the log callback for streaming.
    """
    callback = TrendlyneLogCallback()
    _active_sessions[session_id] = callback

    fetcher = TrendlyneDataFetcher(callback)

    # Run in background thread
    thread = threading.Thread(target=fetcher.fetch_fno_data, daemon=True)
    thread.start()

    return callback


def get_active_session(session_id: str) -> Optional[TrendlyneLogCallback]:
    """Get an active fetch session by ID"""
    return _active_sessions.get(session_id)


def cleanup_session(session_id: str):
    """Clean up a completed session"""
    if session_id in _active_sessions:
        del _active_sessions[session_id]
