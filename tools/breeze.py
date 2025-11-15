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

Usage:
    from tools.breeze import BreezeAPI
    
    api = BreezeAPI()
    api.login()
    
    # Check margin
    margin = api.get_margin()
    
    # Place order
    order_id = api.place_order('NIFTY', 'BUY', 50, 'MARKET')
"""

from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
import pandas as pd


class BreezeAPI:
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
            
            self.breeze = BreezeConnect(api_key=self.api_key)
            
            response = self.breeze.generate_session(
                api_secret=self.api_secret,
                session_token=self.session_token
            )
            
            if response and response.get('Status') == 200:
                self.session_active = True
                print("✅ Breeze login successful")
                return True
            else:
                print(f"❌ Breeze login failed: {response}")
                return False
                
        except Exception as e:
            print(f"❌ Breeze login error: {e}")
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
        Get available margin/funds
        
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
            
            response = self.breeze.get_funds()
            
            if response and response.get('Success'):
                data = response['Success'][0]
                
                return {
                    'available_margin': float(data.get('available_margin', 0)),
                    'used_margin': float(data.get('used_margin', 0)),
                    'total_margin': float(data.get('total_margin', 0)),
                    'cash': float(data.get('cash', 0)),
                    'collateral': float(data.get('collateral', 0)),
                    'raw': data
                }
            
            return {}
            
        except Exception as e:
            print(f"Error fetching margin: {e}")
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
    
    def get_positions(self) -> List[Dict]:
        """
        Get all open positions
        
        Returns:
            list: List of position dicts
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.breeze.get_portfolio_positions()
            
            if response and response.get('Success'):
                return response['Success']
            
            return []
            
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return []
    
    def isOpenPos(self) -> bool:
        """
        Check if any open positions exist
        
        Returns:
            bool: True if open positions exist
        """
        positions = self.get_positions()
        return len(positions) > 0
    
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
