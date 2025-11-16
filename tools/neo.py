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

Implements BrokerInterface for consistency across broker integrations.

Usage:
    from tools.neo import NeoAPI

    api = NeoAPI()
    api.login()

    # Check margin
    margin = api.get_available_margin()

    # Place order
    order_id = api.place_order('NIFTY25NOV20000CE', 'B', 50, 'MARKET')

    # Using factory pattern
    from apps.brokers.interfaces import BrokerFactory
    broker = BrokerFactory.get_broker('kotakneo')
    broker.login()
    margin = broker.get_available_margin()
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import re
import logging

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


class NeoAPI(BrokerInterface if isinstance(BrokerInterface, type) else object):
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
            from apps.core.models import CredentialStore

            # Get fresh credentials to access session_token
            creds = CredentialStore.objects.filter(service='kotakneo').first()
            if not creds:
                raise Exception("Kotak Neo credentials not found in database")

            self.neo = KotakNeoAPI(
                consumer_key=self.consumer_key,
                consumer_secret=self.consumer_secret,
                environment='prod'
            )

            # Login with PAN (username field stores PAN)
            response = self.neo.login(
                pan=creds.username,
                password=creds.password
            )

            if response:
                # Complete 2FA with OTP/session token
                session_response = self.neo.session_2fa(OTP=creds.session_token)

                if session_response and session_response.get('data'):
                    self.session_active = True
                    print("✅ Neo login successful")
                    return True
                else:
                    print(f"❌ Neo 2FA failed: {session_response}")
                    return False
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

            # Call limits with segment/exchange/product parameters like working code
            response = self.neo.limits(segment="ALL", exchange="ALL", product="ALL")

            if response:
                # Response is a dict directly (not nested in 'data')
                # Map fields according to working code
                available = _parse_float(response.get('Collateral'))
                used = _parse_float(response.get('MarginUsed'))
                net = _parse_float(response.get('Net'))
                collateral_value = _parse_float(response.get('CollateralValue'))

                return {
                    'available_margin': available,
                    'used_margin': used,
                    'total_margin': net,
                    'cash': available,
                    'collateral': collateral_value,
                    'raw': response
                }

            return {}

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

            response = self.neo.positions()

            if not response or not response.get('data'):
                return []

            raw_positions = response.get('data', [])
            positions = []

            for p in raw_positions:
                # Parse quantities like working code
                buy_qty = int(p.get('cfBuyQty', 0)) + int(p.get('flBuyQty', 0))
                sell_qty = int(p.get('cfSellQty', 0)) + int(p.get('flSellQty', 0))
                net_q = buy_qty - sell_qty

                # Parse amounts
                buy_amt = _parse_float(p.get('cfBuyAmt', 0)) + _parse_float(p.get('buyAmt', 0))
                sell_amt = _parse_float(p.get('cfSellAmt', 0)) + _parse_float(p.get('sellAmt', 0))
                ltp = _parse_float(p.get('stkPrc', 0))

                # Calculate average price
                if net_q > 0 and buy_qty:
                    avg_price = buy_amt / buy_qty
                elif net_q < 0 and sell_qty:
                    avg_price = sell_amt / sell_qty
                else:
                    avg_price = 0.0

                # Calculate P&L
                realized_pnl = sell_amt - buy_amt
                unrealized_pnl = net_q * ltp

                # Create Position object if interface available
                try:
                    from apps.brokers.interfaces import Position as PositionClass
                    pos = PositionClass(
                        symbol=p.get('sym', p.get('trdSym', '')),
                        quantity=net_q,
                        average_price=avg_price,
                        current_price=ltp,
                        pnl=unrealized_pnl,
                        pnl_percentage=(unrealized_pnl / (buy_amt if buy_amt else 1)) * 100 if buy_amt else 0.0,
                        exchange=p.get('exSeg', ''),
                        product=p.get('prod', ''),
                        raw_data=p
                    )
                    positions.append(pos)
                except ImportError:
                    # Fallback to dict
                    positions.append({
                        'symbol': p.get('sym', p.get('trdSym', '')),
                        'quantity': net_q,
                        'average_price': avg_price,
                        'ltp': ltp,
                        'pnl': unrealized_pnl,
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

    def search_symbol(self, symbol: str, **kwargs) -> List[Dict]:
        """
        Search for a symbol in broker's database (interface implementation)

        Args:
            symbol: Symbol to search
            **kwargs: Additional parameters (exchange, etc.)

        Returns:
            list: Matching symbols
        """
        try:
            if not self.session_active:
                self.login()

            exchange = kwargs.get('exchange', 'NSE')
            return self.search_scrip(symbol=symbol, exchange=exchange)
        except Exception as e:
            print(f"Error searching symbol: {e}")
            return []

    def subscribe_live_feed(self, symbols: List[str], **kwargs) -> bool:
        """
        Subscribe to live price feed (interface implementation)

        Args:
            symbols: List of symbols (instrument tokens)
            **kwargs: Additional parameters

        Returns:
            bool: True if subscription successful
        """
        try:
            if not self.session_active:
                self.login()

            self.subscribe(symbols)
            return True
        except Exception as e:
            print(f"Error subscribing to live feed: {e}")
            return False

    def unsubscribe_live_feed(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from live price feed (interface implementation)

        Args:
            symbols: List of symbols (instrument tokens)

        Returns:
            bool: True if unsubscription successful
        """
        try:
            if not self.session_active:
                self.login()

            self.un_subscribe(symbols)
            return True
        except Exception as e:
            print(f"Error unsubscribing from live feed: {e}")
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
