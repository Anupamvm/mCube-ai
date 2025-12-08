"""
ICICI Breeze API Classes - High-Level API Wrappers

This module provides high-level API wrapper classes for Breeze integration.
"""

import logging
from typing import Dict, Optional

from apps.brokers.utils.common import parse_float as _parse_float

from .client import get_breeze_client
from .quotes import get_nifty_quote
from .margin import get_nfo_margin
from .data_fetcher import fetch_and_save_breeze_data
from .expiry import get_next_nifty_expiry
from .orders import place_futures_order_with_security_master, place_option_order_with_security_master

logger = logging.getLogger(__name__)


class BreezeAPI:
    """
    Simplified Breeze API wrapper for login and account queries.

    This class provides a simple interface for authentication and fetching
    account data (margin, positions) from ICICI Breeze.

    For order placement, use BreezeAPIClient instead.
    """

    def __init__(self):
        """Initialize Breeze API wrapper"""
        from apps.core.models import CredentialStore
        self.breeze = None
        self.session_token = None
        self._load_credentials()

    def _load_credentials(self):
        """Load Breeze credentials from database"""
        from apps.core.models import CredentialStore
        try:
            creds = CredentialStore.objects.filter(service='breeze').first()
            if creds:
                self.session_token = creds.session_token
        except Exception as e:
            logger.error(f"Error loading Breeze credentials: {e}")

    def login(self) -> bool:
        """
        Authenticate with Breeze API using stored session token.

        Returns:
            bool: True if login successful, False otherwise
        """
        from apps.brokers.exceptions import BreezeAuthenticationError
        try:
            self.breeze = get_breeze_client()
            logger.info("Breeze login successful")
            return True
        except BreezeAuthenticationError as e:
            logger.error(f"Breeze authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Breeze login error: {e}")
            return False

    def get_margin(self) -> dict:
        """
        Get NFO margin information.

        Returns:
            dict: Margin data with 'available_margin', 'used_margin', etc.
        """
        try:
            margin_data = get_nfo_margin()
            if margin_data:
                return {
                    'available_margin': _parse_float(margin_data.get('cash_limit', 0)),
                    'used_margin': _parse_float(margin_data.get('amount_allocated', 0)),
                    'raw_data': margin_data
                }
            return {'available_margin': 0, 'used_margin': 0}
        except Exception as e:
            logger.error(f"Error fetching margin: {e}")
            return {'available_margin': 0, 'used_margin': 0}

    def get_positions(self) -> list:
        """
        Get current broker positions.

        Returns:
            list: List of position dicts or position-like objects
        """
        try:
            _, positions = fetch_and_save_breeze_data()
            return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []


class BreezeAPIClient:
    """
    Client wrapper for ICICI Breeze API with order placement methods.

    Provides simplified methods for placing futures and options orders,
    handling the complexity of SecurityMaster lookups and Breeze API calls.

    This is the main client class for order placement and should be used in new code.
    """

    def __init__(self):
        """Initialize the Breeze API client"""
        self.breeze = get_breeze_client()

    def place_futures_order(
        self,
        symbol: str,
        direction: str,
        quantity: int,
        order_type: str = 'market',
        price: Optional[float] = None,
        expiry_date: Optional[str] = None
    ) -> Dict:
        """
        Place a futures order.

        Args:
            symbol: Stock symbol (e.g., 'NIFTY', 'SBIN')
            direction: 'buy' or 'sell'
            quantity: Number of shares/units
            order_type: 'market' or 'limit'
            price: Limit price (required for limit orders)
            expiry_date: Expiry date in 'DD-MMM-YYYY' format (auto-fetch if not provided)

        Returns:
            dict: {
                'success': bool,
                'order_id': str,
                'executed_price': float,
                'message': str,
                'error': str (if failed)
            }
        """
        try:
            # Use provided expiry or fetch next expiry
            if not expiry_date:
                expiry_date = get_next_nifty_expiry()

            # Calculate lot size and quantity
            # For now, assume quantity is in units (will be converted to lots)
            order_response = place_futures_order_with_security_master(
                symbol=symbol,
                expiry_date=expiry_date,
                action=direction.lower(),
                lots=quantity,
                order_type=order_type.lower(),
                price=float(price) if price else 0.0
            )

            if order_response.get('Status') == 200:
                return {
                    'success': True,
                    'order_id': order_response.get('Success', {}).get('order_id', 'UNKNOWN'),
                    'executed_price': price if price else 0.0,
                    'message': 'Order placed successfully'
                }
            else:
                error_msg = order_response.get('Error', 'Unknown error')
                return {
                    'success': False,
                    'message': f'Order placement failed: {error_msg}',
                    'error': error_msg
                }

        except Exception as e:
            logger.error(f"Error placing futures order: {e}")
            return {
                'success': False,
                'message': f'Order placement error: {str(e)}',
                'error': str(e)
            }

    def place_strangle_order(
        self,
        symbol: str,
        call_strike: float,
        put_strike: float,
        quantity: int,
        expiry: str
    ) -> Dict:
        """
        Place a strangle order (simultaneous call and put).

        Args:
            symbol: Underlying symbol (e.g., 'NIFTY')
            call_strike: Call strike price
            put_strike: Put strike price
            quantity: Quantity in lots
            expiry: Expiry date in 'DD-MMM-YYYY' format

        Returns:
            dict: Combined response from both orders
        """
        try:
            # Place call order
            call_response = place_option_order_with_security_master(
                symbol=symbol,
                expiry_date=expiry,
                strike_price=float(call_strike),
                option_type='CE',
                action='sell',  # Typically sell strangle (sell both call and put)
                lots=quantity,
                order_type='market'
            )

            if call_response.get('Status') != 200:
                return {
                    'success': False,
                    'message': f'Call order failed: {call_response.get("Error", "Unknown error")}',
                    'error': call_response.get('Error')
                }

            # Place put order
            put_response = place_option_order_with_security_master(
                symbol=symbol,
                expiry_date=expiry,
                strike_price=float(put_strike),
                option_type='PE',
                action='sell',  # Sell put
                lots=quantity,
                order_type='market'
            )

            if put_response.get('Status') != 200:
                return {
                    'success': False,
                    'message': f'Put order failed: {put_response.get("Error", "Unknown error")}',
                    'error': put_response.get('Error')
                }

            # Both successful
            call_order_id = call_response.get('Success', {}).get('order_id', 'UNKNOWN')
            put_order_id = put_response.get('Success', {}).get('order_id', 'UNKNOWN')

            return {
                'success': True,
                'order_id': f"{call_order_id},{put_order_id}",  # Combined order IDs
                'message': 'Strangle order placed successfully',
                'call_order_id': call_order_id,
                'put_order_id': put_order_id
            }

        except Exception as e:
            logger.error(f"Error placing strangle order: {e}")
            return {
                'success': False,
                'message': f'Strangle order error: {str(e)}',
                'error': str(e)
            }


def get_breeze_api():
    """
    Backward compatibility wrapper for legacy code.

    Returns a BreezeAPIClient instance for use with old code patterns.
    New code should use get_breeze_client() for direct Breeze API access
    or BreezeAPIClient() for order placement.

    Returns:
        BreezeAPIClient: Initialized Breeze API client
    """
    return BreezeAPIClient()
