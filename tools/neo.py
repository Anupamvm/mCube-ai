"""
Kotak Neo API Wrapper

Comprehensive broker API with:
- Authentication & session management
- Margin checking
- Position fetching
- Order placement  
- Quote fetching
- Historical data
- Option chain

Usage:
    from tools.neo import NeoAPI
    
    api = NeoAPI()
    api.login()
    
    # Check margin
    margin = api.get_margin()
    
    # Place order
    order_id = api.place_order('NIFTY', 'BUY', 50, 'MARKET')
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd


class NeoAPI:
    """
    Comprehensive Kotak Neo API wrapper
    
    Handles all broker interactions including margin, positions, orders, and data fetching.
    """
    
    def __init__(self):
        """Initialize Neo API client"""
        self.neo = None
        self.session_active = False
        self._load_credentials()
    
    def _load_credentials(self):
        """Load Neo credentials from database"""
        try:
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.filter(service='kotakneo').first()
            
            if not creds:
                raise Exception("Kotak Neo credentials not found in database")
            
            self.consumer_key = creds.api_key
            self.consumer_secret = creds.api_secret
            self.mobile_number = creds.username
            self.password = creds.password
            self.mpin = creds.neo_password  # MPIN stored in neo_password field
            
        except Exception as e:
            print(f"Error loading Neo credentials: {e}")
            raise
    
    def login(self) -> bool:
        """
        Login to Kotak Neo and establish session
        
        Returns:
            bool: True if login successful
        """
        try:
            from neo_api_client import NeoAPI as KotakNeoAPI
            
            self.neo = KotakNeoAPI(
                consumer_key=self.consumer_key,
                consumer_secret=self.consumer_secret,
                environment='prod'
            )
            
            # Login
            response = self.neo.login(
                mobilenumber=self.mobile_number,
                password=self.password
            )
            
            if response:
                # Generate OTP (for first time)
                # otp_response = self.neo.session_2fa(OTP="123456")
                
                self.session_active = True
                print("✅ Neo login successful")
                return True
            else:
                print(f"❌ Neo login failed: {response}")
                return False
                
        except Exception as e:
            print(f"❌ Neo login error: {e}")
            return False
    
    def logout(self) -> bool:
        """Logout from Neo"""
        try:
            if self.neo:
                self.neo.logout()
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
                'cash': float
            }
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.neo.limits()
            
            if response and response.get('data'):
                data = response['data']
                
                # Neo returns margin data differently
                available = float(data.get('available_margin', 0) or data.get('net', 0))
                used = float(data.get('utilized_margin', 0) or 0)
                total = float(data.get('gross', 0) or 0)
                
                return {
                    'available_margin': available,
                    'used_margin': used,
                    'total_margin': total,
                    'cash': available,
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
            
            response = self.neo.positions()
            
            if response and response.get('data'):
                return response['data']
            
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
            
            # Calculate P&L
            if 'pnl' in df.columns:
                return float(df['pnl'].sum())
            elif 'mtom' in df.columns:
                return float(df['mtom'].sum())
            
            return 0.0
            
        except Exception as e:
            print(f"Error calculating P&L: {e}")
            return 0.0
    
    # ========== ORDERS ==========
    
    def place_order(
        self,
        symbol: str,
        action: str,  # 'B' (BUY) or 'S' (SELL)
        quantity: int,
        order_type: str = 'MKT',  # 'MKT' or 'L' (LIMIT)
        price: float = 0,
        exchange: str = 'NFO',
        product: str = 'NRML',  # 'NRML', 'MIS', 'CNC'
        instrument_token: str = ''
    ) -> Optional[str]:
        """
        Place an order
        
        Args:
            symbol: Trading symbol
            action: 'B' (BUY) or 'S' (SELL)
            quantity: Number of lots
            order_type: 'MKT' (MARKET) or 'L' (LIMIT)
            price: Limit price (for LIMIT orders)
            exchange: 'NSE' or 'NFO'
            product: 'NRML', 'MIS', 'CNC'
            instrument_token: Instrument token (required by Neo)
        
        Returns:
            str: Order ID if successful, None otherwise
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.neo.place_order(
                exchange_segment=exchange,
                product=product,
                price=str(price) if price > 0 else "0",
                order_type=order_type,
                quantity=str(quantity),
                validity="DAY",
                trading_symbol=symbol,
                transaction_type=action,
                amo="NO",
                disclosed_quantity="0",
                market_protection="0",
                pf="N",
                trigger_price="0",
                tag=None
            )
            
            if response and response.get('stat') == 'Ok':
                order_id = response.get('nOrdNo')
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
            
            response = self.neo.order_report()
            
            if response and response.get('data'):
                return response['data']
            
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
            
            response = self.neo.cancel_order(order_id=order_id)
            
            if response and response.get('stat') == 'Ok':
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
        instrument_token: str,
        exchange: str = 'NSE'
    ) -> Optional[Dict]:
        """
        Get current quote for a symbol
        
        Args:
            instrument_token: Instrument token
            exchange: 'NSE' or 'NFO'
        
        Returns:
            dict: Quote data
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.neo.quotes(
                instrument_tokens=[instrument_token],
                isIndex=False,
                session_token=None,
                sid=None
            )
            
            if response and response.get('data'):
                return response['data'][0]
            
            return None
            
        except Exception as e:
            print(f"Error fetching quote: {e}")
            return None
    
    def search_scrip(self, symbol: str, exchange: str = 'NSE') -> List[Dict]:
        """
        Search for scrip to get instrument token
        
        Args:
            symbol: Symbol to search
            exchange: Exchange segment
        
        Returns:
            list: List of matching scrips
        """
        try:
            if not self.session_active:
                self.login()
            
            response = self.neo.search_scrip(
                exchange_segment=exchange,
                symbol=symbol
            )
            
            if response and response.get('data'):
                return response['data']
            
            return []
            
        except Exception as e:
            print(f"Error searching scrip: {e}")
            return []
    
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


# ========== Helper Functions ==========

def get_neo_api() -> NeoAPI:
    """Get initialized Neo API instance"""
    api = NeoAPI()
    api.login()
    return api


def check_margin(required: float) -> bool:
    """Quick margin check"""
    api = get_neo_api()
    return api.check_margin_sufficient(required)


def isOpenPos() -> bool:
    """Quick check for open positions"""
    api = get_neo_api()
    return api.isOpenPos()
