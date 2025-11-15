"""
Broker API Integration for Real-Time Market Data

Fetches live data from broker APIs and updates Django models:
- Current prices
- Live volume and OI
- Real-time Greeks
- Delivery data

Supports:
- ICICI Breeze
- Kotak Neo
- (Add more as needed)
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone

from .models import TLStockData, ContractData, ContractStockData


class BreezeDataFetcher:
    """Fetch real-time data from ICICI Breeze API"""

    def __init__(self):
        from apps.core.models import CredentialStore

        # Get Breeze credentials
        creds = CredentialStore.objects.filter(service='breeze').first()
        if not creds:
            raise Exception("Breeze credentials not found")

        # Initialize Breeze
        from breeze_connect import BreezeConnect
        self.breeze = BreezeConnect(api_key=creds.api_key)
        self.breeze.generate_session(
            api_secret=creds.api_secret,
            session_token=creds.session_token
        )

    def fetch_stock_quote(self, symbol: str, exchange: str = 'NSE') -> Optional[Dict]:
        """
        Fetch current stock quote

        Returns:
            dict with: price, volume, change, etc.
        """
        try:
            quote = self.breeze.get_quotes(
                stock_code=symbol,
                exchange_code=exchange,
                expiry_date="",
                product_type="cash",
                right="",
                strike_price=""
            )

            if quote and quote.get('Success'):
                data = quote['Success'][0]
                return {
                    'symbol': symbol,
                    'current_price': float(data.get('ltp', 0)),
                    'day_volume': int(data.get('volume', 0)),
                    'day_high': float(data.get('high', 0)),
                    'day_low': float(data.get('low', 0)),
                    'day_change_pct': float(data.get('ltpc', 0)),
                    'prev_close': float(data.get('prev_close', 0)),
                    'total_buy_quantity': int(data.get('total_buy_qty', 0)),
                    'total_sell_quantity': int(data.get('total_sell_qty', 0)),
                }

            return None

        except Exception as e:
            print(f"Error fetching quote for {symbol}: {e}")
            return None

    def fetch_futures_quote(self, symbol: str, expiry: str) -> Optional[Dict]:
        """Fetch futures contract quote"""
        try:
            quote = self.breeze.get_quotes(
                stock_code=symbol,
                exchange_code='NFO',
                expiry_date=expiry,
                product_type='futures',
                right='',
                strike_price=''
            )

            if quote and quote.get('Success'):
                data = quote['Success'][0]
                return {
                    'symbol': symbol,
                    'expiry': expiry,
                    'price': float(data.get('ltp', 0)),
                    'oi': int(data.get('open_interest', 0)),
                    'oi_change': int(data.get('oi_change', 0)),
                    'volume': int(data.get('volume', 0)),
                    'day_change': float(data.get('change', 0)),
                    'pct_day_change': float(data.get('ltpc', 0)),
                    'open_price': float(data.get('open', 0)),
                    'high_price': float(data.get('high', 0)),
                    'low_price': float(data.get('low', 0)),
                    'prev_close_price': float(data.get('prev_close', 0)),
                }

            return None

        except Exception as e:
            print(f"Error fetching futures quote for {symbol}: {e}")
            return None

    def fetch_option_chain(self, symbol: str, expiry: str) -> List[Dict]:
        """
        Fetch complete option chain for a symbol

        Returns list of dicts with CE and PE data
        """
        try:
            # Fetch option chain
            chain = self.breeze.get_option_chain_quotes(
                stock_code=symbol,
                exchange_code='NFO',
                expiry_date=expiry,
                product_type='options',
                right='',
                strike_price=''
            )

            if not chain or not chain.get('Success'):
                return []

            options_data = []

            for option in chain['Success']:
                options_data.append({
                    'symbol': symbol,
                    'expiry': expiry,
                    'strike_price': float(option.get('strike_price', 0)),
                    'option_type': option.get('right', ''),
                    'price': float(option.get('ltp', 0)),
                    'oi': int(option.get('open_interest', 0)),
                    'oi_change': int(option.get('oi_change', 0)),
                    'volume': int(option.get('volume', 0)),
                    'iv': float(option.get('iv', 0)) if option.get('iv') else None,
                    'delta': float(option.get('delta', 0)) if option.get('delta') else None,
                    'gamma': float(option.get('gamma', 0)) if option.get('gamma') else None,
                    'theta': float(option.get('theta', 0)) if option.get('theta') else None,
                    'vega': float(option.get('vega', 0)) if option.get('vega') else None,
                    'day_change': float(option.get('change', 0)),
                    'pct_day_change': float(option.get('ltpc', 0)),
                })

            return options_data

        except Exception as e:
            print(f"Error fetching option chain for {symbol}: {e}")
            return []

    @transaction.atomic
    def update_stock_data(self, symbol: str) -> bool:
        """
        Fetch live data and update TLStockData model

        Updates:
        - Current price
        - Day volume
        - Day high/low
        - Day change %
        """
        quote = self.fetch_stock_quote(symbol)
        if not quote:
            return False

        try:
            stock, created = TLStockData.objects.update_or_create(
                nsecode=symbol,
                defaults={
                    'current_price': quote['current_price'],
                    'day_volume': quote['day_volume'],
                    'day_high': quote['day_high'],
                    'day_low': quote['day_low'],
                    'day_change_pct': quote['day_change_pct'],
                }
            )

            return True

        except Exception as e:
            print(f"Error updating stock data for {symbol}: {e}")
            return False

    @transaction.atomic
    def update_futures_data(self, symbol: str, expiry: str) -> bool:
        """Update futures contract data"""
        quote = self.fetch_futures_quote(symbol, expiry)
        if not quote:
            return False

        try:
            contract, created = ContractData.objects.update_or_create(
                symbol=symbol,
                expiry=expiry,
                option_type='FUT',
                strike_price=0,
                defaults={
                    'price': quote['price'],
                    'oi': quote['oi'],
                    'oi_change': quote['oi_change'],
                    'traded_contracts': quote['volume'],
                    'day_change': quote['day_change'],
                    'pct_day_change': quote['pct_day_change'],
                    'open_price': quote['open_price'],
                    'high_price': quote['high_price'],
                    'low_price': quote['low_price'],
                    'prev_close_price': quote['prev_close_price'],
                    'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
            )

            return True

        except Exception as e:
            print(f"Error updating futures data for {symbol}: {e}")
            return False

    @transaction.atomic
    def update_option_chain_data(self, symbol: str, expiry: str) -> int:
        """
        Update option chain data

        Returns: Number of contracts updated
        """
        options = self.fetch_option_chain(symbol, expiry)
        if not options:
            return 0

        updated_count = 0

        for option_data in options:
            try:
                contract, created = ContractData.objects.update_or_create(
                    symbol=option_data['symbol'],
                    expiry=option_data['expiry'],
                    strike_price=option_data['strike_price'],
                    option_type=option_data['option_type'],
                    defaults={
                        'price': option_data['price'],
                        'oi': option_data['oi'],
                        'oi_change': option_data['oi_change'],
                        'traded_contracts': option_data['volume'],
                        'iv': option_data['iv'],
                        'delta': option_data['delta'],
                        'gamma': option_data['gamma'],
                        'theta': option_data['theta'],
                        'vega': option_data['vega'],
                        'day_change': option_data['day_change'],
                        'pct_day_change': option_data['pct_day_change'],
                        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    }
                )

                updated_count += 1

            except Exception as e:
                print(f"Error updating option data: {e}")
                continue

        return updated_count


class MarketDataUpdater:
    """
    Main class to update all market data from broker APIs

    Orchestrates fetching data from broker APIs and updating Django models
    """

    def __init__(self, broker: str = 'breeze'):
        """
        Initialize with specific broker

        Args:
            broker: 'breeze' or 'kotak_neo'
        """
        self.broker = broker

        if broker == 'breeze':
            self.fetcher = BreezeDataFetcher()
        else:
            raise ValueError(f"Broker {broker} not supported yet")

    def update_stock_universe(self, symbols: List[str]) -> Dict:
        """
        Update data for multiple stocks

        Args:
            symbols: List of NSE codes

        Returns:
            dict with update statistics
        """
        stats = {
            'total': len(symbols),
            'updated': 0,
            'failed': 0
        }

        for symbol in symbols:
            success = self.fetcher.update_stock_data(symbol)
            if success:
                stats['updated'] += 1
            else:
                stats['failed'] += 1

        return stats

    def update_fno_universe(self, symbols: List[str], expiry: str) -> Dict:
        """
        Update F&O data for multiple symbols

        Args:
            symbols: List of F&O symbols
            expiry: Expiry date (e.g., '28-NOV-2024')

        Returns:
            dict with update statistics
        """
        stats = {
            'total': len(symbols),
            'futures_updated': 0,
            'options_updated': 0,
            'failed': 0
        }

        for symbol in symbols:
            # Update futures
            futures_success = self.fetcher.update_futures_data(symbol, expiry)
            if futures_success:
                stats['futures_updated'] += 1

            # Update options
            options_count = self.fetcher.update_option_chain_data(symbol, expiry)
            if options_count > 0:
                stats['options_updated'] += options_count
            else:
                stats['failed'] += 1

        return stats

    def update_nifty50_stocks(self) -> Dict:
        """Update data for all Nifty 50 stocks"""
        nifty50_symbols = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
            'HINDUNILVR', 'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK',
            'BAJFINANCE', 'LT', 'ASIANPAINT', 'AXISBANK', 'MARUTI',
            'SUNPHARMA', 'TITAN', 'ULTRACEMCO', 'NESTLEIND', 'WIPRO',
            'HCLTECH', 'TECHM', 'NTPC', 'TATAMOTORS', 'POWERGRID',
            'ONGC', 'ADANIENT', 'JSWSTEEL', 'TATASTEEL', 'COALINDIA',
            'INDUSINDBK', 'M&M', 'BAJAJFINSV', 'DRREDDY', 'CIPLA',
            'GRASIM', 'EICHERMOT', 'HINDALCO', 'APOLLOHOSP', 'HEROMOTOCO',
            'DIVISLAB', 'TATACONSUM', 'ADANIPORTS', 'BRITANNIA', 'SHREECEM',
            'SBILIFE', 'BAJAJ-AUTO', 'BPCL', 'HDFCLIFE', 'LTIM'
        ]

        return self.update_stock_universe(nifty50_symbols)

    def update_fno_stocks(self, expiry: str = None) -> Dict:
        """
        Update F&O data for liquid stocks

        Args:
            expiry: Expiry date. If None, uses current month expiry
        """
        if expiry is None:
            # Auto-calculate current month expiry (last Thursday)
            expiry = self._get_current_expiry()

        fno_symbols = [
            'NIFTY', 'BANKNIFTY', 'FINNIFTY',  # Indices
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
            'ITC', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'BAJFINANCE',
        ]

        return self.update_fno_universe(fno_symbols, expiry)

    def _get_current_expiry(self) -> str:
        """
        Calculate current month expiry (last Thursday)

        Returns:
            str: Expiry date in format 'DD-MMM-YYYY'
        """
        from calendar import monthrange

        today = datetime.now()
        year = today.year
        month = today.month

        # Get last day of current month
        last_day = monthrange(year, month)[1]

        # Find last Thursday
        for day in range(last_day, 0, -1):
            date = datetime(year, month, day)
            if date.weekday() == 3:  # Thursday
                return date.strftime('%d-%b-%Y').upper()

        return today.strftime('%d-%b-%Y').upper()

    @transaction.atomic
    def calculate_and_update_derived_metrics(self, symbol: str, expiry: str):
        """
        Calculate derived metrics from raw data

        Calculates:
        - PCR ratio
        - Max pain
        - Total OI
        - Volume ratios
        """
        from apps.data.importers import ContractStockDataImporter

        # Calculate stock-level F&O metrics
        importer = ContractStockDataImporter()
        result = importer.calculate_and_save_stock_fno_data()

        return result


class ScheduledDataUpdater:
    """
    Scheduled updates for continuous data refresh

    Use this with Celery for automated updates
    """

    @staticmethod
    def update_pre_market_data():
        """Update data before market opens (8:30 AM)"""
        updater = MarketDataUpdater(broker='breeze')

        # Update Nifty 50 stocks
        stats = updater.update_nifty50_stocks()
        print(f"Pre-market update: {stats}")

        return stats

    @staticmethod
    def update_live_fno_data():
        """Update F&O data during market hours (every 5 minutes)"""
        updater = MarketDataUpdater(broker='breeze')

        # Update F&O data
        stats = updater.update_fno_stocks()
        print(f"Live F&O update: {stats}")

        # Calculate derived metrics
        updater.calculate_and_update_derived_metrics('NIFTY', updater._get_current_expiry())

        return stats

    @staticmethod
    def update_post_market_data():
        """Update data after market closes (3:30 PM)"""
        updater = MarketDataUpdater(broker='breeze')

        # Full update of all stocks
        stats = updater.update_nifty50_stocks()
        fno_stats = updater.update_fno_stocks()

        stats.update(fno_stats)
        print(f"Post-market update: {stats}")

        return stats
