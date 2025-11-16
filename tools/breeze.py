"""
ICICI Breeze API Wrapper

Comprehensive broker API with:
- Authentication & session management
- Margin checking
- Position fetching
- Order placement
- Quote fetching
- Historical data
- Option chain

Implements BrokerInterface for consistency across broker integrations.

Usage:
    from tools.breeze import BreezeAPI

    api = BreezeAPI()
    api.login()

    # Check margin
    margin = api.get_available_margin()

    # Place order
    order_id = api.place_order('NIFTY', 'B', 50, 'MKT')

    # Using factory pattern
    from apps.brokers.interfaces import BrokerFactory
    broker = BrokerFactory.get_broker('breeze')
    broker.login()
    margin = broker.get_available_margin()
"""

from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta, timezone as dt_timezone
import pandas as pd
import re
import logging
import json
import hashlib
import requests

try:
    from apps.brokers.interfaces import BrokerInterface, MarginData, Position, Order, Quote
except ImportError:
    # Fallback if interface is not available
    BrokerInterface = object
    MarginData = dict
    Position = dict
    Order = dict
    Quote = dict


def _parse_float(val):
    """
    Extract numeric content from val and return as float.
    Falls back to 0.0 if parsing fails.
    - strips commas and percent signs
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return 0.0
    s = s.replace(',', '')
    if s.endswith('%'):
        s = s[:-1]
    m = re.search(r'-?\d+\.?\d*', s)
    if not m:
        logging.warning(f"Float parse: no numeric data in '{val}', defaulting to 0.0")
        return 0.0
    try:
        return float(m.group())
    except ValueError:
        logging.warning(f"Float parse: invalid conversion for '{val}', defaulting to 0.0")
        return 0.0


class BreezeAPI(BrokerInterface if isinstance(BrokerInterface, type) else object):
    """
    Comprehensive ICICI Breeze API wrapper
    
    Handles all broker interactions including margin, positions, orders, and data fetching.
    """
    
    def __init__(self):
        """Initialize Breeze API client"""
        self.breeze = None
        self.session_active = False
        self._load_credentials()
    
    def _load_credentials(self):
        """Load Breeze credentials from database"""
        try:
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.filter(service='breeze').first()
            
            if not creds:
                raise Exception("Breeze credentials not found in database")
            
            self.api_key = creds.api_key
            self.api_secret = creds.api_secret
            self.session_token = creds.session_token
            
        except Exception as e:
            print(f"Error loading Breeze credentials: {e}")
            raise
    
    def login(self) -> bool:
        """
        Login to Breeze and establish session

        Returns:
            bool: True if login successful
        """
        try:
            from breeze_connect import BreezeConnect

            # Validate session_token exists
            if not self.session_token or self.session_token.strip() == '':
                print("❌ Breeze login failed: Session token is required")
                return False

            self.breeze = BreezeConnect(api_key=self.api_key)

            # Call generate_session - old working code doesn't check response
            # Just calling it is enough, it throws exception on failure
            self.breeze.generate_session(
                api_secret=self.api_secret,
                session_token=self.session_token
            )

            # If we reach here without exception, login succeeded
            self.session_active = True
            print("✅ Breeze login successful")
            return True

        except Exception as e:
            print(f"❌ Breeze login error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def logout(self) -> bool:
        """Logout from Breeze"""
        try:
            if self.breeze:
                self.breeze = None
                self.session_active = False
            return True
        except Exception as e:
            print(f"Error during logout: {e}")
            return False
    
    # ========== MARGIN & FUNDS ==========
    
    def get_margin(self) -> Dict:
        """
        Get available margin/funds using both funds API and margin API

        Returns:
            dict: {
                'available_margin': float,
                'used_margin': float,
                'total_margin': float,
                'cash': float,
                'collateral': float
            }
        """
        try:
            if not self.session_active:
                self.login()

            # Get funds data
            funds_resp = self.breeze.get_funds()
            funds = funds_resp.get('Success', {}) if funds_resp else {}

            # Get margin data using direct API call with checksums (like working code)
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.filter(service='breeze').first()
            if not creds:
                raise Exception("Breeze credentials not found")

            appkey = creds.api_key
            secret_key = creds.api_secret
            session_key = creds.session_token

            # Get customer details for REST token
            cd_url = "https://api.icicidirect.com/breezeapi/api/v1/customerdetails"
            cd_payload = json.dumps({"SessionToken": session_key, "AppKey": appkey})
            cd_headers = {'Content-Type': 'application/json'}
            cd_resp = requests.get(cd_url, headers=cd_headers, data=cd_payload)
            rest_token = cd_resp.json().get('Success', {}).get('session_token')

            # Get margin data with checksum
            margin_url = "https://api.icicidirect.com/breezeapi/api/v1/margin"
            time_stamp = datetime.now(dt_timezone.utc).isoformat()[:19] + '.000Z'
            payload = json.dumps({"exchange_code": "NFO"}, separators=(',', ':'))
            checksum = hashlib.sha256((time_stamp + payload + secret_key).encode()).hexdigest()

            headers = {
                'Content-Type': 'application/json',
                'X-Checksum': 'token ' + checksum,
                'X-Timestamp': time_stamp,
                'X-AppKey': appkey,
                'X-SessionToken': rest_token,
            }

            margin_resp = requests.get(margin_url, headers=headers, data=payload)
            margins = margin_resp.json().get('Success', {})

            # Parse and combine data like working code
            available_margin = _parse_float(margins.get('cash_limit'))
            used_margin = _parse_float(margins.get('amount_allocated'))
            total_bank_balance = _parse_float(funds.get('total_bank_balance')) if isinstance(funds, dict) else 0.0
            allocated_fno = _parse_float(funds.get('allocated_fno')) if isinstance(funds, dict) else 0.0

            return {
                'available_margin': available_margin,
                'used_margin': used_margin,
                'total_margin': total_bank_balance,
                'cash': available_margin,
                'collateral': allocated_fno,
                'raw_funds': funds,
                'raw_margin': margins
            }

        except Exception as e:
            print(f"Error fetching margin: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def get_available_margin(self) -> float:
        """
        Get available margin as simple float
        
        Returns:
            float: Available margin in rupees
        """
        margin_data = self.get_margin()
        return margin_data.get('available_margin', 0.0)
    
    def check_margin_sufficient(self, required_margin: float) -> bool:
        """
        Check if sufficient margin available
        
        Args:
            required_margin: Required margin amount
        
        Returns:
            bool: True if sufficient margin available
        """
        available = self.get_available_margin()
        return available >= required_margin
    
    # ========== POSITIONS ==========
    
    def get_positions(self) -> List[Position]:
        """
        Get all open positions

        Returns:
            list: List of Position objects
        """
        try:
            if not self.session_active:
                self.login()

            response = self.breeze.get_portfolio_positions()

            if not response or not response.get('Success'):
                return []

            raw_positions = response.get('Success', [])
            positions = []

            for p in raw_positions:
                # Parse like working code
                quantity = int(p.get('quantity') or 0)
                avg_price_val = _parse_float(p.get('average_price'))
                ltp_val = _parse_float(p.get('ltp') or p.get('price'))

                # Calculate buy/sell quantities
                buy_qty = quantity if quantity > 0 else 0
                sell_qty = abs(quantity) if quantity < 0 else 0
                buy_amt = buy_qty * avg_price_val
                sell_amt = sell_qty * avg_price_val

                # Get P&L
                unrealized = _parse_float(p.get('pnl'))

                # Build symbol from available fields
                symbol = p.get('stock_code') or f"{p.get('underlying', '')} {p.get('strike_price', '')} {p.get('right', '')}".strip()

                # Create Position object if interface available
                try:
                    from apps.brokers.interfaces import Position as PositionClass
                    pos = PositionClass(
                        symbol=symbol,
                        quantity=quantity,
                        average_price=avg_price_val,
                        current_price=ltp_val,
                        pnl=unrealized,
                        pnl_percentage=(unrealized / (buy_amt if buy_amt else 1)) * 100 if buy_amt else 0.0,
                        exchange=p.get('segment', 'NFO'),
                        product=p.get('product_type', 'NRML'),
                        raw_data=p
                    )
                    positions.append(pos)
                except ImportError:
                    # Fallback to dict
                    positions.append({
                        'symbol': symbol,
                        'quantity': quantity,
                        'average_price': avg_price_val,
                        'ltp': ltp_val,
                        'pnl': unrealized,
                        'buy_qty': buy_qty,
                        'sell_qty': sell_qty,
                        'raw': p
                    })

            return positions

        except Exception as e:
            print(f"Error fetching positions: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def isOpenPos(self) -> bool:
        """
        Check if any open positions exist

        Returns:
            bool: True if open positions exist
        """
        positions = self.get_positions()
        return len(positions) > 0

    def has_open_positions(self) -> bool:
        """
        Check if any open positions exist (interface implementation)

        Returns:
            bool: True if open positions exist
        """
        return self.isOpenPos()
    
    def get_position_pnl(self) -> float:
        """
        Calculate total P&L from all positions
        
        Returns:
            float: Total P&L
        """
        try:
            positions = self.get_positions()
            
            if not positions:
                return 0.0
            
            df = pd.DataFrame(positions)
            
            # Filter for NIFTY or relevant symbol
            if 'symbol' in df.columns:
                df = df[df['symbol'].str.contains('NIFTY', na=False)]
            
            # Calculate P&L
            if 'pnl' in df.columns:
                return float(df['pnl'].sum())
            elif 'unrealized_profit' in df.columns:
                return float(df['unrealized_profit'].sum())
            
            return 0.0
            
        except Exception as e:
            print(f"Error calculating P&L: {e}")
            return 0.0
    
    # ========== ORDERS ==========
    
    def place_order(
        self,
        symbol: str,
        action: str,  # 'BUY' or 'SELL'
        quantity: int,
        order_type: str = 'MARKET',  # 'MARKET' or 'LIMIT'
        price: float = 0,
        exchange: str = 'NFO',
        product: str = 'INTRADAY',
        expiry: str = '',
        strike_price: str = '',
        right: str = ''  # 'CALL' or 'PUT' for options
    ) -> Optional[str]:
        """
        Place an order
        
        Args:
            symbol: Stock/index symbol (e.g., 'NIFTY')
            action: 'BUY' or 'SELL'
            quantity: Number of lots
            order_type: 'MARKET' or 'LIMIT'
            price: Limit price (for LIMIT orders)
            exchange: 'NSE' or 'NFO'
            product: 'INTRADAY', 'DELIVERY', 'MARGIN'
            expiry: Expiry date for F&O (DD-MMM-YYYY)
            strike_price: Strike price for options
            right: 'CALL' or 'PUT' for options
        
        Returns:
            str: Order ID if successful, None otherwise
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.breeze.place_order(
                stock_code=symbol,
                exchange_code=exchange,
                product=product,
                action=action,
                order_type=order_type,
                quantity=str(quantity),
                price=str(price) if price > 0 else '',
                expiry_date=expiry,
                strike_price=strike_price,
                right=right
            )
            
            if response and response.get('Success'):
                order_id = response['Success'].get('order_id')
                print(f"✅ Order placed: {order_id}")
                return order_id
            else:
                print(f"❌ Order failed: {response}")
                return None
                
        except Exception as e:
            print(f"❌ Order placement error: {e}")
            return None
    
    def get_orders(self) -> List[Dict]:
        """
        Get all orders for the day
        
        Returns:
            list: List of order dicts
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.breeze.get_order_list()
            
            if response and response.get('Success'):
                return response['Success']
            
            return []
            
        except Exception as e:
            print(f"Error fetching orders: {e}")
            return []
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            bool: True if cancelled successfully
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.breeze.cancel_order(order_id=order_id)
            
            if response and response.get('Success'):
                print(f"✅ Order {order_id} cancelled")
                return True
            else:
                print(f"❌ Cancel failed: {response}")
                return False
                
        except Exception as e:
            print(f"❌ Cancel error: {e}")
            return False
    
    # ========== QUOTES & DATA ==========
    
    def get_quote(
        self,
        symbol: str,
        exchange: str = 'NSE',
        expiry: str = '',
        strike: str = '',
        right: str = ''
    ) -> Optional[Dict]:
        """
        Get current quote for a symbol
        
        Args:
            symbol: Stock/index symbol
            exchange: 'NSE' or 'NFO'
            expiry: Expiry date for F&O
            strike: Strike price for options
            right: 'CALL' or 'PUT' for options
        
        Returns:
            dict: Quote data
        """
        try:
            if not self.session_active:
                self.login()
            
            product_type = 'cash' if exchange == 'NSE' else 'futures'
            if right:
                product_type = 'options'
            
            response = self.breeze.get_quotes(
                stock_code=symbol,
                exchange_code=exchange,
                expiry_date=expiry,
                product_type=product_type,
                right=right,
                strike_price=strike
            )
            
            if response and response.get('Success'):
                return response['Success'][0]
            
            return None
            
        except Exception as e:
            print(f"Error fetching quote: {e}")
            return None
    
    def get_option_chain(
        self,
        symbol: str,
        expiry: str
    ) -> List[Dict]:
        """
        Get complete option chain
        
        Args:
            symbol: Underlying symbol (e.g., 'NIFTY')
            expiry: Expiry date (DD-MMM-YYYY)
        
        Returns:
            list: Option chain data
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.breeze.get_option_chain_quotes(
                stock_code=symbol,
                exchange_code='NFO',
                expiry_date=expiry,
                product_type='options',
                right='',
                strike_price=''
            )
            
            if response and response.get('Success'):
                return response['Success']
            
            return []
            
        except Exception as e:
            print(f"Error fetching option chain: {e}")
            return []
    
    def get_historical_data(
        self,
        symbol: str,
        interval: str = '1day',
        from_date: str = '',
        to_date: str = '',
        exchange: str = 'NSE'
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data
        
        Args:
            symbol: Stock/index symbol
            interval: '1minute', '5minute', '30minute', '1day'
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            exchange: 'NSE' or 'NFO'
        
        Returns:
            DataFrame: OHLCV data
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.breeze.get_historical_data(
                interval=interval,
                from_date=from_date,
                to_date=to_date,
                stock_code=symbol,
                exchange_code=exchange
            )
            
            if response and response.get('Success'):
                df = pd.DataFrame(response['Success'])
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            print(f"Error fetching historical data: {e}")
            return pd.DataFrame()
    
    # ========== MARKET STATUS ==========
    
    def is_market_open(self) -> bool:
        """
        Check if market is currently open

        Returns:
            bool: True if market is open
        """
        try:
            now = datetime.now()

            # Check if it's a weekday
            if now.weekday() >= 5:  # Saturday or Sunday
                return False

            # Check market hours (9:15 AM to 3:30 PM)
            market_open = now.replace(hour=9, minute=15, second=0)
            market_close = now.replace(hour=15, minute=30, second=0)

            return market_open <= now <= market_close

        except Exception as e:
            print(f"Error checking market status: {e}")
            return False

    def search_symbol(self, symbol: str, **kwargs) -> List[Dict]:
        """
        Search for a symbol in broker's database (interface implementation)

        Args:
            symbol: Symbol to search

        Returns:
            list: Matching symbols
        """
        try:
            if not self.session_active:
                self.login()

            # Breeze doesn't have direct search, but we can attempt quotes
            quote = self.get_quote(symbol)
            if quote:
                return [quote]
            return []
        except Exception as e:
            print(f"Error searching symbol: {e}")
            return []

    def subscribe_live_feed(self, symbols: List[str], **kwargs) -> bool:
        """
        Subscribe to live price feed (interface implementation)

        Args:
            symbols: List of symbols to subscribe

        Returns:
            bool: True if subscription successful
        """
        # Breeze WebSocket support would be implemented here
        print("Live feed subscription not yet implemented for Breeze")
        return False

    def unsubscribe_live_feed(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from live price feed (interface implementation)

        Args:
            symbols: List of symbols to unsubscribe

        Returns:
            bool: True if unsubscription successful
        """
        print("Live feed unsubscription not yet implemented for Breeze")
        return False
    
    # ========== UTILITIES ==========
    
    def get_current_expiry(self) -> str:
        """
        Get current month F&O expiry (last Thursday)
        
        Returns:
            str: Expiry date in DD-MMM-YYYY format
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


# ========== Helper Functions ==========

def get_breeze_api() -> BreezeAPI:
    """Get initialized Breeze API instance"""
    api = BreezeAPI()
    api.login()
    return api


def check_margin(required: float) -> bool:
    """Quick margin check"""
    api = get_breeze_api()
    return api.check_margin_sufficient(required)


def isOpenPos() -> bool:
    """Quick check for open positions"""
    api = get_breeze_api()
    return api.isOpenPos()
