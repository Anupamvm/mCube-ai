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
import threading
import time
from requests.exceptions import ConnectionError, Timeout, ReadTimeout

logger = logging.getLogger(__name__)

# Process-level singleton: avoids repeated session_init() API calls
_cached_instance = None
_cache_lock = threading.Lock()

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
    
    AUTH_ERROR_KEYWORDS = ['unauthorized', 'invalid token', 'session', 'auth', '401']

    def __init__(self):
        """Initialize Neo API client"""
        self.neo = None
        self.session_active = False
        self.last_error = None
        self._load_credentials()
    
    def _load_credentials(self):
        """Load Neo credentials from database (v2 API)"""
        try:
            from apps.core.models import CredentialStore
            creds = CredentialStore.objects.filter(service='kotakneo').first()

            if not creds:
                raise Exception("Kotak Neo credentials not found in database")

            self.consumer_key = creds.api_key
            raw_mobile = creds.mobile_number or creds.username
            # v2 API requires +91 country code prefix for mobile number
            if raw_mobile and not raw_mobile.startswith('+'):
                self.mobile_number = f'+91{raw_mobile}'
            else:
                self.mobile_number = raw_mobile
            self.mpin = creds.neo_password  # MPIN stored in neo_password field
            self.ucc = creds.ucc
            self.totp_secret = creds.totp_secret

        except Exception as e:
            logger.error(f"Error loading Neo credentials: {e}")
            raise
    
    def try_restore_session(self) -> bool:
        """
        Try to restore a previously saved session from the database.

        Creates a fresh v2 NeoAPI client (no network calls on init),
        then injects saved edit_token/edit_sid/serverId/base_url/data_center.

        Returns:
            bool: True if session was successfully restored
        """
        from apps.brokers.utils.auth_manager import restore_neo_session

        saved = restore_neo_session()
        if not saved:
            return False

        edit_token, edit_sid, server_id, base_url, data_center = saved

        try:
            from neo_api_client import NeoAPI as KotakNeoAPI

            # v2: no consumer_secret, no session_init() — zero network calls
            self.neo = KotakNeoAPI(
                consumer_key=self.consumer_key,
                environment='prod'
            )

            # v2 requires base_url for all API calls (quotes, orders, etc.)
            # Without it, get_url_details() returns None and all calls fail.
            if not base_url:
                logger.warning("Session restore skipped — base_url missing (incomplete session)")
                return False

            # Inject saved session values into the client configuration
            self.neo.configuration.edit_token = edit_token
            self.neo.configuration.edit_sid = edit_sid
            self.neo.configuration.base_url = base_url
            # Always set serverId explicitly: '' produces ?sId= in URLs (handled by server),
            # while leaving it as None produces ?sId=None (causes routing failures).
            self.neo.configuration.serverId = server_id or ''
            if data_center:
                self.neo.configuration.data_center = data_center

            self.session_active = True
            self.last_error = None
            return True

        except Exception as e:
            logger.warning(f"Session restore failed during client init: {e}")
            return False

    MAX_LOGIN_ATTEMPTS = 3
    LOGIN_RETRY_DELAY_SECONDS = 10  # Wait between retries (TOTP codes valid for 30s)

    def _has_error(self, response: dict) -> bool:
        """Check if an API response contains an error (handles both 'error' and 'Error' keys)."""
        if not response:
            return True
        return 'error' in response or 'Error' in response

    def _get_error_msg(self, response: dict) -> str:
        """Extract error message from API response."""
        if not response:
            return 'No response'
        return response.get('error', response.get('Error', 'Unknown'))

    def login(self, manual: bool = False, force_fresh: bool = False) -> bool:
        """
        Login to Kotak Neo v2 with auto-login using TOTP + MPIN.

        Neo uses automated TOTP + MPIN (no manual OTP required), so we retry
        up to 3 times within a single login session to handle TOTP timing
        edge cases and transient network issues.

        Flow:
        1. Try restoring saved session (no login needed) — skipped if force_fresh=True
        2. Check daily auto-login limit
        3. Retry up to 3 times:
           a. Generate fresh TOTP from stored secret
           b. Call totp_login() with mobile_number + UCC + TOTP
           c. Call totp_validate() with MPIN
        4. Only mark as failed after all retries exhausted

        Args:
            manual: If True, bypass trading window and daily limit (UI-triggered)
            force_fresh: If True, skip try_restore_session() and force full TOTP+MPIN login.
                         Use this when a restored session is known to be API-unauthorized.

        Returns:
            bool: True if login successful
        """
        import time

        # Try restoring a saved session first (avoids login+2FA entirely).
        # Skipped when force_fresh=True — the caller knows the restored token is stale.
        if not force_fresh and self.try_restore_session():
            logger.info("Session restored from database — skipping login/2FA")
            return True

        if force_fresh:
            logger.info("force_fresh=True — skipping session restore, doing fresh TOTP+MPIN login")

        from apps.brokers.utils.auth_manager import (
            can_attempt_auto_login, mark_auto_login_started,
            mark_auto_login_success, mark_auto_login_failed,
        )

        # Check daily limit (manual=True bypasses window + daily cap)
        can_login, reason = can_attempt_auto_login('kotakneo', manual=manual)
        if not can_login:
            self.last_error = f"Auto-login blocked: {reason}"
            logger.warning(f"Neo login blocked: {reason}")
            return False

        from neo_api_client import NeoAPI as KotakNeoAPI

        if not self.mpin:
            self.last_error = "MPIN not configured — cannot auto-login"
            logger.error(self.last_error)
            self._notify_neo_login_failed(self.last_error)
            return False

        if not self.totp_secret:
            self.last_error = "TOTP secret not configured — cannot auto-login"
            logger.error(self.last_error)
            self._notify_neo_login_failed(self.last_error)
            return False

        if not self.ucc:
            self.last_error = "UCC not configured — cannot auto-login"
            logger.error(self.last_error)
            self._notify_neo_login_failed(self.last_error)
            return False

        mark_auto_login_started('kotakneo')

        import pyotp
        last_error = None

        for attempt in range(1, self.MAX_LOGIN_ATTEMPTS + 1):
            try:
                # Fresh client each attempt to avoid stale state
                self.neo = KotakNeoAPI(
                    consumer_key=self.consumer_key,
                    environment='prod'
                )

                # Generate fresh TOTP for each attempt (handles 30s window edge cases)
                totp = pyotp.TOTP(self.totp_secret)
                totp_code = totp.now()

                # Step 1: TOTP login (generates view token)
                logger.info(f"Neo login attempt {attempt}/{self.MAX_LOGIN_ATTEMPTS} — TOTP for UCC: {self.ucc}")
                response = self.neo.totp_login(
                    mobile_number=self.mobile_number,
                    ucc=self.ucc,
                    totp=totp_code
                )

                if self._has_error(response):
                    last_error = f"TOTP login error: {self._get_error_msg(response)}"
                    logger.warning(f"Neo attempt {attempt} TOTP login failed: {last_error}")
                    if attempt < self.MAX_LOGIN_ATTEMPTS:
                        logger.info(f"Retrying in {self.LOGIN_RETRY_DELAY_SECONDS}s...")
                        time.sleep(self.LOGIN_RETRY_DELAY_SECONDS)
                    continue

                # Step 2: Validate with MPIN
                logger.info(f"Attempt {attempt}: TOTP login succeeded — validating with MPIN")
                session_response = self.neo.totp_validate(mpin=self.mpin)

                if self._has_error(session_response) or not session_response.get('data'):
                    last_error = f"MPIN validation failed: {self._get_error_msg(session_response) if self._has_error(session_response) else session_response}"
                    logger.warning(f"Neo attempt {attempt} MPIN validation failed: {last_error}")
                    if attempt < self.MAX_LOGIN_ATTEMPTS:
                        logger.info(f"Retrying in {self.LOGIN_RETRY_DELAY_SECONDS}s...")
                        time.sleep(self.LOGIN_RETRY_DELAY_SECONDS)
                    continue

                # === Login succeeded ===
                self.session_active = True
                self.last_error = None

                data = session_response.get('data', {})
                server_id = data.get('hsServerId', '') or ''
                # Normalize serverId to '' when None to avoid ?sId=None in API URLs
                if self.neo.configuration.serverId is None:
                    self.neo.configuration.serverId = server_id  # '' if not provided
                base_url = getattr(self.neo.configuration, 'base_url', None) or data.get('baseUrl', '')
                data_center = getattr(self.neo.configuration, 'data_center', None) or data.get('dataCenter', '')
                logger.info(f"Neo login successful on attempt {attempt} - serverId: {server_id}, base_url: {base_url}, dataCenter: {data_center}")
                if not base_url:
                    logger.warning("Neo login succeeded but base_url is empty — API calls may fail")

                # Persist session for reuse
                try:
                    from apps.brokers.utils.auth_manager import save_neo_session
                    save_neo_session(
                        edit_token=self.neo.configuration.edit_token,
                        edit_sid=self.neo.configuration.edit_sid,
                        server_id=getattr(self.neo.configuration, 'serverId', '') or '',
                        base_url=base_url,
                        data_center=data_center,
                    )
                except Exception as save_err:
                    logger.warning(f"Failed to persist Neo session (non-fatal): {save_err}")

                mark_auto_login_success('kotakneo')
                if attempt > 1:
                    self._notify_neo_login_success(f" (succeeded on attempt {attempt}/{self.MAX_LOGIN_ATTEMPTS})")
                else:
                    self._notify_neo_login_success()
                return True

            except Exception as e:
                last_error = self._format_exception(e)
                logger.error(f"Neo login attempt {attempt} error: {last_error}", exc_info=True)
                if attempt < self.MAX_LOGIN_ATTEMPTS:
                    logger.info(f"Retrying in {self.LOGIN_RETRY_DELAY_SECONDS}s...")
                    time.sleep(self.LOGIN_RETRY_DELAY_SECONDS)

        # All attempts exhausted
        self.last_error = last_error
        self.session_active = False
        mark_auto_login_failed('kotakneo')
        self._notify_neo_login_failed(f"{last_error} (failed all {self.MAX_LOGIN_ATTEMPTS} attempts)")
        return False

    def _notify_neo_login_failed(self, reason: str):
        """Send Telegram notification that Neo auto-login failed."""
        self._send_telegram(
            f"Kotak Neo Auto-Login Failed\n\n"
            f"Reason: {reason}\n\n"
            f"Please login manually via the web UI."
        )

    def _notify_neo_login_success(self, suffix: str = ''):
        """Send Telegram notification that Neo auto-login succeeded."""
        self._send_telegram(
            f"Kotak Neo Login Successful{suffix}\n\n"
            f"Session established and saved."
        )

    def _send_telegram(self, message: str):
        """Send a Telegram notification (convenience wrapper)."""
        try:
            from apps.alerts.services.notification_service import notify
            notify('SYSTEM_STATUS',
                title='Kotak Neo Login',
                context=[message],
                collapsible=False,
            )
        except Exception as e:
            logger.warning(f"Failed to send Telegram notification: {e}")

    def _format_exception(self, e: Exception) -> str:
        """Format exception message, handling broken __str__ methods."""
        try:
            msg = str(e)
            if msg:
                return msg
        except Exception:
            pass

        # Try common exception attributes
        for attr in ['reason', 'message', 'msg', 'args']:
            val = getattr(e, attr, None)
            if val:
                if isinstance(val, tuple) and val:
                    return str(val[0])
                return str(val)

        return f"{type(e).__name__}: Unknown error"

    def _is_auth_error(self, exception: Exception) -> bool:
        """Check if an exception indicates an authentication/session error."""
        error_str = self._format_exception(exception).lower()
        return any(kw in error_str for kw in self.AUTH_ERROR_KEYWORDS)

    def _handle_auth_error(self, source: str = ''):
        """Clear saved session, invalidate cache, so next call triggers fresh login."""
        global _cached_instance
        if source:
            logger.warning(f"Auth error in {source}, clearing saved session")
        self.session_active = False
        _cached_instance = None  # Invalidate process cache
        try:
            from apps.brokers.utils.auth_manager import clear_neo_session
            clear_neo_session()
        except Exception as e:
            logger.warning(f"Failed to clear saved Neo session: {e}")

    def get_last_error(self) -> Optional[str]:
        """Get the last error message from login or API calls."""
        return self.last_error
    
    def logout(self) -> bool:
        """Logout from Neo"""
        try:
            if self.neo:
                self.neo.logout()
                self.session_active = False
            return True
        except Exception as e:
            logger.error(f"Error during logout: {e}")
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
                    'available_margin': net,              # Use Net field (actual available funds for new positions)
                    'used_margin': used,
                    'total_margin': net,
                    'cash': net,                          # Use Net for cash too
                    'collateral': available,              # Store Collateral separately for reference
                    'collateral_value': collateral_value,
                    'raw': response
                }

            return {}

        except Exception as e:
            if self._is_auth_error(e):
                self._handle_auth_error('get_margin')
            logger.exception(f"Error fetching margin: {e}")
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
            if self._is_auth_error(e):
                self._handle_auth_error('get_positions')
            logger.exception(f"Error fetching positions: {e}")
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
            logger.error(f"Error calculating P&L: {e}")
            return 0.0
    
    # ========== ORDERS ==========
    
    # Transient errors that warrant a retry
    _RETRYABLE_EXCEPTIONS = (ConnectionError, Timeout, ReadTimeout, OSError)

    def place_order(
        self,
        symbol: str,
        action: str,  # 'B' (BUY) or 'S' (SELL)
        quantity: int,
        order_type: str = 'MKT',  # 'MKT' or 'L' (LIMIT)
        price: float = 0,
        exchange: str = 'NFO',
        product: str = 'NRML',  # 'NRML', 'MIS', 'CNC'
        instrument_token: str = '',
        is_exit: bool = False,
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        Place an order with automatic retry for transient failures.

        Args:
            symbol: Trading symbol
            action: 'B' (BUY) or 'S' (SELL)
            quantity: Number of lots
            order_type: 'MKT' (MARKET) or 'L' (LIMIT)
            price: Limit price (for LIMIT orders)
            exchange: 'NSE' or 'NFO'
            product: 'NRML', 'MIS', 'CNC'
            instrument_token: Instrument token (required by Neo)
            is_exit: If True, sends URGENT alert on exhausted retries
            max_retries: Number of retry attempts (default 3)

        Returns:
            str: Order ID if successful, None otherwise
        """
        last_error = None

        for attempt in range(1, max_retries + 1):
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
                    if attempt > 1:
                        logger.info(f"Order placed on attempt {attempt}: {order_id}")
                    else:
                        logger.info(f"Order placed: {order_id}")
                    return order_id
                else:
                    # Deterministic failure (margin, invalid symbol, etc.) — don't retry
                    logger.error(f"Order rejected by broker: {response}")
                    last_error = f"Broker rejected: {response}"
                    break

            except Exception as e:
                last_error = str(e)

                if self._is_auth_error(e):
                    # Auth error: clear session, re-login, and retry once
                    self._handle_auth_error('place_order')
                    logger.warning(f"Auth error on attempt {attempt}, re-authenticating: {e}")
                    try:
                        self.login()
                    except Exception as login_err:
                        logger.error(f"Re-login failed: {login_err}")
                    # Continue to next attempt (will use fresh session)
                    if attempt < max_retries:
                        time.sleep(1)
                    continue

                if isinstance(e, self._RETRYABLE_EXCEPTIONS) or self._is_transient_error(e):
                    backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    logger.warning(
                        f"Transient error on attempt {attempt}/{max_retries}, "
                        f"retrying in {backoff}s: {e}"
                    )
                    if attempt < max_retries:
                        time.sleep(backoff)
                    continue

                # Non-transient, non-auth error — don't retry
                logger.error(f"Order placement error (non-retryable): {e}")
                break

        # All retries exhausted or broke out
        logger.error(
            f"Order FAILED after {attempt} attempt(s): {symbol} {action} qty={quantity} | {last_error}"
        )

        if is_exit:
            self._send_urgent_order_failure_alert(
                symbol=symbol, action=action, quantity=quantity,
                order_type=order_type, price=price, exchange=exchange,
                product=product, error=last_error,
            )

        return None

    def _is_transient_error(self, exception: Exception) -> bool:
        """Check if an error is likely transient (server-side, network)."""
        error_str = self._format_exception(exception).lower()
        transient_keywords = ['timeout', 'connection', 'temporary', '500', '502', '503', '504', 'rate limit']
        return any(kw in error_str for kw in transient_keywords)

    def _send_urgent_order_failure_alert(self, **order_details):
        """Send URGENT Telegram alert when an exit order fails after all retries."""
        try:
            from apps.alerts.services.notification_service import notify
            notify(
                'CRITICAL_ERROR',
                title='EXIT ORDER FAILED — Manual Action Required',
                priority='CRITICAL',
                metrics={
                    'Symbol': order_details.get('symbol', '?'),
                    'Action': 'BUY' if order_details.get('action') == 'B' else 'SELL',
                    'Quantity': str(order_details.get('quantity', '?')),
                    'Type': order_details.get('order_type', '?'),
                },
                context=[
                    f"Exit order failed after all retries",
                    f"Error: {order_details.get('error', 'Unknown')}",
                    "⚠️ Position is still OPEN — close manually via broker portal",
                ],
            )
        except Exception as alert_err:
            logger.critical(
                f"CRITICAL: Exit order failed AND alert failed: {alert_err} | "
                f"Order: {order_details}"
            )

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
            if self._is_auth_error(e):
                self._handle_auth_error('get_orders')
            logger.error(f"Error fetching orders: {e}")
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
                logger.info(f"Order {order_id} cancelled")
                return True
            else:
                logger.error(f"Cancel failed: {response}")
                return False

        except Exception as e:
            if self._is_auth_error(e):
                self._handle_auth_error('cancel_order')
            logger.error(f"Cancel error: {e}")
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

            # Map exchange to v2 exchange_segment format
            exchange_map = {'NSE': 'nse_cm', 'NFO': 'nse_fo', 'BSE': 'bse_cm', 'BFO': 'bse_fo'}
            exchange_segment = exchange_map.get(exchange.upper(), 'nse_cm')

            # v2: instrument_tokens is a list of dicts with exchange_segment + instrument_token
            response = self.neo.quotes(
                instrument_tokens=[{
                    "exchange_segment": exchange_segment,
                    "instrument_token": instrument_token
                }],
                quote_type="ltp"
            )

            # v2 returns a list directly, or a dict with 'fault'/'error' on failure
            if isinstance(response, list) and response:
                return response[0]
            elif isinstance(response, dict) and response.get('data'):
                # Fallback for any future format changes
                return response['data'][0] if isinstance(response['data'], list) else response['data']

            return None
            
        except Exception as e:
            if self._is_auth_error(e):
                self._handle_auth_error('get_quote')
            logger.error(f"Error fetching quote: {e}")
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

            # v2 returns a list directly, not {'data': [...]}
            if isinstance(response, list):
                return response
            elif isinstance(response, dict) and response.get('data'):
                # Fallback for any future format changes
                return response['data']

            return []
            
        except Exception as e:
            if self._is_auth_error(e):
                self._handle_auth_error('search_scrip')
            logger.error(f"Error searching scrip: {e}")
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
            logger.error(f"Error checking market status: {e}")
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
            if self._is_auth_error(e):
                self._handle_auth_error('search_symbol')
            logger.error(f"Error searching symbol: {e}")
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
            if self._is_auth_error(e):
                self._handle_auth_error('subscribe_live_feed')
            logger.error(f"Error subscribing to live feed: {e}")
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
            if self._is_auth_error(e):
                self._handle_auth_error('unsubscribe_live_feed')
            logger.error(f"Error unsubscribing from live feed: {e}")
            return False


# ========== Helper Functions ==========

def get_neo_api() -> NeoAPI:
    """
    Get authenticated Neo API instance, cached per-process.

    First call creates the instance and logs in (restores session or full login).
    Subsequent calls return the same instance — no repeated session_init() or login.
    If the cached session becomes invalid, creates a fresh one.
    """
    global _cached_instance

    with _cache_lock:
        if _cached_instance and _cached_instance.session_active:
            return _cached_instance

        api = NeoAPI()
        api.login()
        if api.session_active:
            _cached_instance = api
        return api


def check_margin(required: float) -> bool:
    """Quick margin check"""
    api = get_neo_api()
    return api.check_margin_sufficient(required)


def isOpenPos() -> bool:
    """Quick check for open positions"""
    api = get_neo_api()
    return api.isOpenPos()
