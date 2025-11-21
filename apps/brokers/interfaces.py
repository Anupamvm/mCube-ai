"""
Broker API Interfaces

Defines abstract base classes for consistent broker integration.
Both ICICI Breeze and Kotak Neo implement these interfaces.

This allows switching between brokers by simply changing the broker type.

Example:
    # Switch broker easily
    broker = BrokerFactory.get_broker('breeze')  # or 'kotakneo'
    broker.login()
    margin = broker.get_available_margin()
    broker.place_order(symbol='RELIANCE', ...)
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarginData:
    """Standardized margin/funds data across brokers"""

    available_margin: float
    used_margin: float
    total_margin: float
    cash: float
    collateral: float = 0.0
    raw_data: Dict = None  # Raw broker response for debugging

    def __str__(self):
        from apps.core.utils import format_currency
        return (
            f"Available: {format_currency(self.available_margin)} | "
            f"Used: {format_currency(self.used_margin)} | "
            f"Total: {format_currency(self.total_margin)}"
        )


@dataclass
class Position:
    """Standardized position data across brokers"""

    symbol: str
    quantity: int
    average_price: float
    current_price: float
    pnl: float
    pnl_percentage: float
    exchange: str = 'NSE'
    product: str = 'NRML'
    raw_data: Dict = None  # Raw broker response

    def __str__(self):
        from apps.core.utils import format_currency
        return (
            f"{self.symbol} {self.quantity}qty @ {format_currency(self.average_price)} | "
            f"P&L: {format_currency(self.pnl)} ({self.pnl_percentage:.2f}%)"
        )


@dataclass
class Order:
    """Standardized order data across brokers"""

    order_id: str
    symbol: str
    quantity: int
    executed_quantity: int
    price: float
    order_type: str  # MARKET, LIMIT
    transaction_type: str  # BUY, SELL
    status: str  # PENDING, EXECUTED, REJECTED, CANCELLED
    timestamp: datetime
    raw_data: Dict = None

    def __str__(self):
        return (
            f"Order {self.order_id}: {self.transaction_type} {self.quantity} "
            f"{self.symbol} @ {self.price} - {self.status}"
        )


@dataclass
class Quote:
    """Standardized quote data across brokers"""

    symbol: str
    ltp: float  # Last Traded Price
    bid: float
    ask: float
    high: float
    low: float
    volume: int
    oi: Optional[int] = None  # Open Interest for F&O
    timestamp: Optional[datetime] = None
    raw_data: Dict = None

    def __str__(self):
        return f"{self.symbol}: {self.ltp} (H: {self.high}, L: {self.low}, V: {self.volume})"


class BrokerInterface(ABC):
    """
    Abstract base class for all broker implementations.

    Defines the contract that all broker integrations must follow.
    """

    @abstractmethod
    def login(self) -> bool:
        """
        Authenticate with the broker and establish session.

        Returns:
            bool: True if login successful, False otherwise
        """
        pass

    @abstractmethod
    def logout(self) -> bool:
        """Logout from the broker and close session"""
        pass

    # ===== Margin & Funds =====

    @abstractmethod
    def get_margin(self) -> MarginData:
        """Get current margin/funds information"""
        pass

    @abstractmethod
    def get_available_margin(self) -> float:
        """Get available margin as float"""
        pass

    @abstractmethod
    def check_margin_sufficient(self, required: float) -> bool:
        """Check if sufficient margin is available for a trade"""
        pass

    # ===== Positions =====

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Get all open positions"""
        pass

    @abstractmethod
    def has_open_positions(self) -> bool:
        """Check if any positions are open"""
        pass

    @abstractmethod
    def get_position_pnl(self) -> float:
        """Calculate total P&L from all positions"""
        pass

    # ===== Orders =====

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        action: str,  # 'B' or 'S'
        quantity: int,
        order_type: str = 'MKT',  # 'MKT' or 'L'
        price: float = 0.0,
        **kwargs
    ) -> Optional[str]:
        """
        Place an order on the exchange.

        Args:
            symbol: Trading symbol
            action: 'B' (BUY) or 'S' (SELL)
            quantity: Number of shares/lots
            order_type: 'MKT' (MARKET) or 'L' (LIMIT)
            price: Limit price (for limit orders)

        Returns:
            str: Order ID if successful, None otherwise
        """
        pass

    @abstractmethod
    def get_orders(self) -> List[Order]:
        """Get all orders for the day"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by ID"""
        pass

    # ===== Quotes & Data =====

    @abstractmethod
    def get_quote(self, symbol: str, **kwargs) -> Optional[Quote]:
        """Get current quote for a symbol"""
        pass

    @abstractmethod
    def search_symbol(self, symbol: str, **kwargs) -> List[Dict]:
        """Search for a symbol in broker's database"""
        pass

    # ===== Market Status =====

    @abstractmethod
    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        pass

    # ===== WebSocket (Optional) =====

    @abstractmethod
    def subscribe_live_feed(self, symbols: List[str], **kwargs) -> bool:
        """Subscribe to live price feed for symbols"""
        pass

    @abstractmethod
    def unsubscribe_live_feed(self, symbols: List[str]) -> bool:
        """Unsubscribe from live price feed"""
        pass


class BrokerFactory:
    """Factory for creating broker instances"""

    _brokers: Dict[str, type] = {}

    @classmethod
    def register(cls, broker_name: str, broker_class: type):
        """Register a broker implementation"""
        cls._brokers[broker_name.lower()] = broker_class

    @classmethod
    def get_broker(cls, broker_name: str) -> BrokerInterface:
        """
        Get a broker instance by name.

        Args:
            broker_name: 'breeze' or 'kotakneo'

        Returns:
            BrokerInterface instance

        Raises:
            ValueError: If broker is not registered
        """
        broker_class = cls._brokers.get(broker_name.lower())
        if not broker_class:
            available = ', '.join(cls._brokers.keys())
            raise ValueError(
                f"Broker '{broker_name}' not found. "
                f"Available: {available}"
            )

        return broker_class()

    @classmethod
    def list_brokers(cls) -> List[str]:
        """List all registered brokers"""
        return list(cls._brokers.keys())


# Register implementations when imported
def register_brokers():
    """Register all available broker implementations"""
    try:
        from apps.brokers.integrations.breeze import BreezeAPIClient
        BrokerFactory.register('breeze', BreezeAPIClient)
    except ImportError:
        pass

    try:
        from tools.neo import NeoAPI
        BrokerFactory.register('kotakneo', NeoAPI)
    except ImportError:
        pass


# Auto-register on import
register_brokers()


# ===== Comparison Utilities =====

def compare_margins(brokers: List[str]) -> Dict[str, MarginData]:
    """
    Get margin comparison across multiple brokers.

    Args:
        brokers: List of broker names

    Returns:
        Dict mapping broker name to margin data
    """
    comparison = {}

    for broker_name in brokers:
        try:
            broker = BrokerFactory.get_broker(broker_name)
            if broker.login():
                comparison[broker_name] = broker.get_margin()
                broker.logout()
        except Exception as e:
            print(f"Error getting margin for {broker_name}: {e}")

    return comparison


def best_broker_for_trade(symbol: str, quantity: int, required_margin: float) -> Optional[str]:
    """
    Determine which broker has sufficient margin for a trade.

    Args:
        symbol: Trading symbol
        quantity: Trade quantity
        required_margin: Required margin for the trade

    Returns:
        Broker name with best available margin, or None
    """
    margins = compare_margins(['breeze', 'kotakneo'])
    suitable = {
        name: margin for name, margin in margins.items()
        if margin.available_margin >= required_margin
    }

    if not suitable:
        return None

    # Return broker with most available margin
    return max(suitable.items(), key=lambda x: x[1].available_margin)[0]


class BrokerError(Exception):
    """Base exception for broker-related errors"""
    pass


class BrokerAuthError(BrokerError):
    """Raised when authentication fails"""
    pass


class BrokerConnectionError(BrokerError):
    """Raised when connection to broker fails"""
    pass


class InsufficientMarginError(BrokerError):
    """Raised when margin is insufficient for trade"""
    pass


class InvalidOrderError(BrokerError):
    """Raised when order parameters are invalid"""
    pass
