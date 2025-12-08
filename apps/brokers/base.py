"""
Base broker API interface for the mCube Trading System.

This module defines abstract base classes that all broker integrations must implement.
This ensures consistent interface across different brokers (Kotak Neo, ICICI Breeze, etc.)
and enables polymorphic usage of broker APIs.

Classes:
    BaseBrokerAPI: Abstract base class for all broker API wrappers
    BrokerOrderResult: Standard order result format
    BrokerPosition: Standard position data format
    BrokerMargin: Standard margin data format

Architecture:
    Each broker implementation (Neo, Breeze) should:
    1. Inherit from BaseBrokerAPI
    2. Implement all abstract methods
    3. Return data in standard formats (BrokerOrderResult, etc.)
    4. Handle broker-specific quirks internally

Example:
    >>> class MyBrokerAPI(BaseBrokerAPI):
    ...     def authenticate(self):
    ...         # Broker-specific auth logic
    ...         return True
    ...
    ...     def get_margin(self):
    ...         # Broker-specific margin fetching
    ...         return {'available_margin': 100000, ...}
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime


@dataclass
class BrokerOrderResult:
    """
    Standard format for order placement results across all brokers.

    This ensures consistent handling of order responses regardless of
    which broker API was used.

    Attributes:
        success: Whether order was placed successfully
        order_id: Broker's order ID (empty string if failed)
        message: Human-readable message
        error: Error message if failed (None if successful)
        broker: Broker name ('neo', 'breeze', etc.)
        raw_response: Original broker API response for debugging
        executed_price: Price at which order was executed (optional)
        quantity: Quantity ordered
        symbol: Trading symbol

    Example:
        >>> result = BrokerOrderResult(
        ...     success=True,
        ...     order_id='NEO123456',
        ...     message='Order placed successfully',
        ...     broker='neo',
        ...     quantity=50,
        ...     symbol='NIFTY25NOV24500CE'
        ... )
    """
    success: bool
    order_id: str
    message: str
    error: Optional[str] = None
    broker: str = ''
    raw_response: Optional[Dict] = None
    executed_price: Optional[float] = None
    quantity: Optional[int] = None
    symbol: Optional[str] = None


@dataclass
class BrokerPosition:
    """
    Standard format for position data across all brokers.

    Normalizes different broker API response formats into a consistent structure.

    Attributes:
        symbol: Trading symbol
        exchange: Exchange segment (NSE_FO, NFO, etc.)
        product: Product type (NRML, MIS, etc.)
        quantity: Net quantity (positive = long, negative = short)
        avg_price: Average execution price
        ltp: Last traded price
        unrealized_pnl: Unrealized profit/loss
        realized_pnl: Realized profit/loss
        buy_qty: Total buy quantity
        sell_qty: Total sell quantity
        buy_amount: Total buy amount
        sell_amount: Total sell amount

    Example:
        >>> position = BrokerPosition(
        ...     symbol='NIFTY25NOV24500CE',
        ...     exchange='NSE_FO',
        ...     quantity=50,
        ...     avg_price=Decimal('150.50'),
        ...     ltp=Decimal('155.00')
        ... )
    """
    symbol: str
    exchange: str
    product: str
    quantity: int
    avg_price: Decimal
    ltp: Decimal
    unrealized_pnl: Decimal = Decimal('0.00')
    realized_pnl: Decimal = Decimal('0.00')
    buy_qty: int = 0
    sell_qty: int = 0
    buy_amount: Decimal = Decimal('0.00')
    sell_amount: Decimal = Decimal('0.00')


@dataclass
class BrokerMargin:
    """
    Standard format for margin/funds data across all brokers.

    Different brokers use different terminology (cash_limit, available_margin,
    collateral, etc.). This class normalizes all into a standard format.

    Attributes:
        available_margin: Available margin for trading
        used_margin: Margin currently used by positions
        total_balance: Total account balance
        allocated_fno: Amount allocated to F&O segment
        collateral: Collateral value (pledged stocks, etc.)
        broker: Broker name
        fetched_at: Timestamp when data was fetched
        raw_data: Original broker response for reference

    Example:
        >>> margin = BrokerMargin(
        ...     available_margin=Decimal('500000.00'),
        ...     used_margin=Decimal('50000.00'),
        ...     broker='breeze'
        ... )
    """
    available_margin: Decimal
    used_margin: Decimal
    total_balance: Decimal = Decimal('0.00')
    allocated_fno: Decimal = Decimal('0.00')
    collateral: Decimal = Decimal('0.00')
    broker: str = ''
    fetched_at: Optional[datetime] = None
    raw_data: Optional[Dict] = None


class BaseBrokerAPI(ABC):
    """
    Abstract base class for all broker API implementations.

    All broker integrations (Kotak Neo, ICICI Breeze, etc.) must inherit
    from this class and implement all abstract methods. This ensures:
    1. Consistent interface across different brokers
    2. Type safety and code completion
    3. Easier testing with mock brokers
    4. Ability to switch brokers without changing client code

    Required Methods:
        - authenticate(): Authenticate with broker API
        - get_margin(): Fetch margin/funds data
        - get_positions(): Fetch current positions
        - place_order(): Place an order
        - get_client(): Get underlying broker client instance

    Optional Methods (can be overridden):
        - is_authenticated(): Check if currently authenticated
        - refresh_session(): Refresh authentication session
        - get_order_status(): Check status of an order
        - cancel_order(): Cancel a pending order

    Example Usage:
        >>> class KotakNeoAPI(BaseBrokerAPI):
        ...     def authenticate(self):
        ...         # Neo-specific authentication
        ...         return True
        ...
        ...     def get_margin(self):
        ...         # Neo-specific margin fetching
        ...         return BrokerMargin(...)
        >>>
        >>> # Client code works with any broker
        >>> broker = KotakNeoAPI()
        >>> if broker.authenticate():
        ...     margin = broker.get_margin()
        ...     print(f"Available: {margin.available_margin}")
    """

    def __init__(self):
        """Initialize broker API instance."""
        self._client = None
        self._authenticated = False

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with the broker API.

        This method should:
        1. Load credentials from database/config
        2. Perform authentication (login, 2FA, session token, etc.)
        3. Store authenticated client instance
        4. Set self._authenticated flag

        Returns:
            bool: True if authentication successful, False otherwise

        Raises:
            BrokerAuthenticationError: If credentials missing or auth fails

        Example:
            >>> broker = KotakNeoAPI()
            >>> if broker.authenticate():
            ...     print("Logged in successfully")
        """
        pass

    @abstractmethod
    def get_margin(self) -> BrokerMargin:
        """
        Fetch current margin/funds data from broker.

        Returns margin data in standardized format. Should handle
        different broker API response structures internally.

        Returns:
            BrokerMargin: Standardized margin data

        Raises:
            BrokerAPIError: If API call fails
            BrokerAuthenticationError: If session expired

        Example:
            >>> margin = broker.get_margin()
            >>> print(f"Available: ₹{margin.available_margin:,.2f}")
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[BrokerPosition]:
        """
        Fetch all current positions from broker.

        Returns list of positions in standardized format. Should:
        1. Fetch positions from broker API
        2. Calculate unrealized P&L
        3. Normalize to BrokerPosition format

        Returns:
            List[BrokerPosition]: List of all open positions

        Raises:
            BrokerAPIError: If API call fails

        Example:
            >>> positions = broker.get_positions()
            >>> for pos in positions:
            ...     print(f"{pos.symbol}: {pos.quantity} @ {pos.avg_price}")
        """
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str = 'market',
        price: float = 0.0,
        **kwargs
    ) -> BrokerOrderResult:
        """
        Place an order through the broker.

        Args:
            symbol: Trading symbol (broker-specific format)
            transaction_type: 'buy' or 'sell'
            quantity: Quantity to trade
            order_type: 'market' or 'limit'
            price: Limit price (for limit orders)
            **kwargs: Broker-specific additional parameters

        Returns:
            BrokerOrderResult: Standardized order result

        Raises:
            BrokerAPIError: If order placement fails

        Example:
            >>> result = broker.place_order(
            ...     symbol='NIFTY25NOV24500CE',
            ...     transaction_type='sell',
            ...     quantity=50,
            ...     order_type='market'
            ... )
            >>> if result.success:
            ...     print(f"Order ID: {result.order_id}")
        """
        pass

    @abstractmethod
    def get_client(self) -> Any:
        """
        Get the underlying broker API client instance.

        Returns raw broker client for advanced operations not covered
        by the base interface.

        Returns:
            Any: Broker-specific client instance (NeoAPI, BreezeConnect, etc.)

        Example:
            >>> neo_client = broker.get_client()
            >>> # Use Neo-specific methods
            >>> neo_client.quotes(...)
        """
        pass

    def is_authenticated(self) -> bool:
        """
        Check if currently authenticated with broker.

        Default implementation checks self._authenticated flag.
        Can be overridden for session validation with broker API.

        Returns:
            bool: True if authenticated, False otherwise

        Example:
            >>> if not broker.is_authenticated():
            ...     broker.authenticate()
        """
        return self._authenticated

    def refresh_session(self) -> bool:
        """
        Refresh authentication session with broker.

        Default implementation calls authenticate() again.
        Can be overridden for broker-specific session refresh logic.

        Returns:
            bool: True if refresh successful

        Example:
            >>> if not broker.refresh_session():
            ...     print("Session refresh failed")
        """
        return self.authenticate()

    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """
        Get status of a placed order.

        Optional method - not all operations require order status checking.
        Brokers can override if they support order status queries.

        Args:
            order_id: Order ID returned from place_order()

        Returns:
            Optional[Dict]: Order status data or None if not implemented

        Example:
            >>> status = broker.get_order_status('NEO123456')
            >>> if status:
            ...     print(f"Status: {status['order_status']}")
        """
        return None

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.

        Optional method - can be overridden by brokers that support
        order cancellation.

        Args:
            order_id: Order ID to cancel

        Returns:
            bool: True if cancellation successful

        Example:
            >>> if broker.cancel_order('NEO123456'):
            ...     print("Order cancelled")
        """
        return False

    def __repr__(self) -> str:
        """String representation of broker instance."""
        class_name = self.__class__.__name__
        auth_status = "authenticated" if self._authenticated else "not authenticated"
        return f"<{class_name} ({auth_status})>"
