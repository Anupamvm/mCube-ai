"""
Paper Trading Broker — Simulates order execution without real broker API calls.

SAFETY: This module intentionally has ZERO imports from tools.neo, kotak-neo-api,
or ICICI Breeze SDK.  It fetches market data only via the data layer (ContractData
/ market data services) and can never trigger a real broker order.
"""

import logging
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional

import pytz

from django.db.models import Sum

from apps.brokers.interfaces import (
    BrokerInterface,
    MarginData,
    Order,
    Position as BrokerPosition,
    Quote,
)

logger = logging.getLogger('paper_trading')
IST = pytz.timezone('Asia/Kolkata')


class PaperBroker(BrokerInterface):
    """
    Paper (simulated) broker implementing BrokerInterface.

    All order placement is simulated using real-time LTP from the market data
    layer.  Fills are recorded in the ``PaperOrder`` model for auditing.
    """

    def __init__(self, account):
        """
        Args:
            account: BrokerAccount instance with ``is_paper_trading=True``.
        """
        assert account.is_paper_trading, (
            "PaperBroker can only be used with paper trading accounts"
        )
        self.account = account

    # ===== Authentication (no-op) =====

    def login(self) -> bool:
        logger.info("[PAPER] Login — no-op (always connected)")
        return True

    def logout(self) -> bool:
        logger.info("[PAPER] Logout — no-op")
        return True

    # ===== Margin & Funds =====

    def get_margin(self) -> MarginData:
        from apps.core.models import TradingCoreConfig
        config = TradingCoreConfig.get_instance()
        total = float(config.paper_initial_capital)
        used = self._get_used_margin()
        available = total - used
        return MarginData(
            available_margin=max(available, 0),
            used_margin=used,
            total_margin=total,
            cash=max(available, 0),
            collateral=0.0,
            raw_data={'source': 'paper_broker'},
        )

    def get_available_margin(self) -> float:
        return self.get_margin().available_margin

    def check_margin_sufficient(self, required: float) -> bool:
        return self.get_available_margin() >= required

    def _get_used_margin(self) -> float:
        """Sum margin_used from all open paper positions for this account."""
        from apps.positions.models import Position
        agg = (
            Position.all_objects
            .filter(account=self.account, is_paper=True, status='OPEN')
            .aggregate(total=Sum('margin_used'))
        )
        return float(agg['total'] or 0)

    # ===== Positions =====

    def get_positions(self) -> List[BrokerPosition]:
        from apps.positions.models import Position
        positions = Position.all_objects.filter(
            account=self.account, is_paper=True, status='OPEN',
        )
        result = []
        for pos in positions:
            result.append(BrokerPosition(
                symbol=pos.instrument,
                quantity=pos.quantity,
                average_price=float(pos.entry_price),
                current_price=float(pos.current_price),
                pnl=float(pos.unrealized_pnl),
                pnl_percentage=(
                    float(pos.unrealized_pnl / pos.entry_value * 100)
                    if pos.entry_value else 0.0
                ),
                exchange='NFO',
                product='NRML',
                raw_data={'paper': True, 'position_id': pos.id},
            ))
        return result

    def has_open_positions(self) -> bool:
        from apps.positions.models import Position
        return Position.all_objects.filter(
            account=self.account, is_paper=True, status='OPEN',
        ).exists()

    def get_position_pnl(self) -> float:
        from apps.positions.models import Position
        agg = (
            Position.all_objects
            .filter(account=self.account, is_paper=True, status='OPEN')
            .aggregate(total=Sum('unrealized_pnl'))
        )
        return float(agg['total'] or 0)

    # ===== Orders =====

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = 'MKT',
        price: float = 0.0,
        **kwargs,
    ) -> Optional[str]:
        """
        Simulate an order fill.

        1. Fetch real-time LTP from market data service.
        2. Apply configurable slippage.
        3. Check margin (for entry orders).
        4. Create PaperOrder audit record.
        5. Return UUID-based order ID.
        """
        from apps.brokers.models import PaperOrder
        from apps.core.models import TradingCoreConfig

        config = TradingCoreConfig.get_instance()
        slippage_pct = float(config.paper_slippage_pct)

        # Fetch LTP
        ltp = self._fetch_ltp(symbol)
        if ltp is None or ltp <= 0:
            logger.warning(f"[PAPER] Cannot fetch LTP for {symbol} — order rejected")
            PaperOrder.objects.create(
                order_id=str(uuid.uuid4())[:20],
                account=self.account,
                symbol=symbol,
                action=action,
                quantity=quantity,
                order_type=order_type,
                requested_price=Decimal(str(price)),
                fill_price=Decimal('0'),
                ltp_at_fill=Decimal('0'),
                status='REJECTED',
                rejection_reason='Could not fetch LTP',
            )
            return None

        ltp_decimal = Decimal(str(ltp))

        # Apply slippage (adverse direction)
        if action.upper() in ('B', 'BUY'):
            fill_price = ltp_decimal * (1 + Decimal(str(slippage_pct)))
        else:
            fill_price = ltp_decimal * (1 - Decimal(str(slippage_pct)))
        fill_price = fill_price.quantize(Decimal('0.01'))
        slippage_amount = abs(fill_price - ltp_decimal)

        # For LIMIT orders: check if price is favorable
        if order_type.upper() in ('L', 'LIMIT') and price > 0:
            if action.upper() in ('B', 'BUY') and ltp > price:
                logger.info(f"[PAPER] LIMIT BUY rejected: LTP {ltp} > limit {price}")
                PaperOrder.objects.create(
                    order_id=str(uuid.uuid4())[:20],
                    account=self.account,
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    order_type=order_type,
                    requested_price=Decimal(str(price)),
                    fill_price=Decimal('0'),
                    ltp_at_fill=ltp_decimal,
                    status='REJECTED',
                    rejection_reason=f'Limit price {price} below LTP {ltp}',
                )
                return None
            elif action.upper() in ('S', 'SELL') and ltp < price:
                logger.info(f"[PAPER] LIMIT SELL rejected: LTP {ltp} < limit {price}")
                PaperOrder.objects.create(
                    order_id=str(uuid.uuid4())[:20],
                    account=self.account,
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    order_type=order_type,
                    requested_price=Decimal(str(price)),
                    fill_price=Decimal('0'),
                    ltp_at_fill=ltp_decimal,
                    status='REJECTED',
                    rejection_reason=f'Limit price {price} above LTP {ltp}',
                )
                return None

        # Margin check (skip for exit orders)
        is_exit = kwargs.get('is_exit', False)
        if not is_exit:
            required_margin = float(fill_price) * quantity
            if not self.check_margin_sufficient(required_margin):
                logger.warning(
                    f"[PAPER] Insufficient margin: need {required_margin:.2f}, "
                    f"have {self.get_available_margin():.2f}"
                )
                PaperOrder.objects.create(
                    order_id=str(uuid.uuid4())[:20],
                    account=self.account,
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    order_type=order_type,
                    requested_price=Decimal(str(price)),
                    fill_price=Decimal('0'),
                    ltp_at_fill=ltp_decimal,
                    status='REJECTED',
                    rejection_reason=(
                        f'Insufficient margin: need {required_margin:.2f}, '
                        f'have {self.get_available_margin():.2f}'
                    ),
                )
                return None

        # Generate order ID
        order_id = f"PAPER-{uuid.uuid4().hex[:12].upper()}"

        # Create audit record
        PaperOrder.objects.create(
            order_id=order_id,
            account=self.account,
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type=order_type,
            requested_price=Decimal(str(price)),
            fill_price=fill_price,
            slippage_applied=slippage_amount,
            ltp_at_fill=ltp_decimal,
            status='FILLED',
            metadata={
                'is_exit': is_exit,
                'slippage_pct': slippage_pct,
                'kwargs': {k: str(v) for k, v in kwargs.items()},
            },
        )

        logger.info(
            f"[PAPER] Order filled: {order_id} | {action} {quantity} {symbol} "
            f"@ {fill_price} (LTP: {ltp_decimal}, slippage: {slippage_amount})"
        )
        return order_id

    def get_orders(self) -> List[Order]:
        from apps.brokers.models import PaperOrder
        today = date.today()
        paper_orders = PaperOrder.objects.filter(
            account=self.account, created_at__date=today,
        )
        result = []
        for po in paper_orders:
            result.append(Order(
                order_id=po.order_id,
                symbol=po.symbol,
                quantity=po.quantity,
                executed_quantity=po.quantity if po.status == 'FILLED' else 0,
                price=float(po.fill_price),
                order_type=po.order_type,
                transaction_type='BUY' if po.action in ('B', 'BUY') else 'SELL',
                status=po.status,
                timestamp=po.created_at,
                raw_data={'paper': True},
            ))
        return result

    def cancel_order(self, order_id: str) -> bool:
        from apps.brokers.models import PaperOrder
        try:
            po = PaperOrder.objects.get(order_id=order_id)
            if po.status == 'FILLED':
                logger.warning(f"[PAPER] Cannot cancel filled order {order_id}")
                return False
            po.status = 'CANCELLED'
            po.save(update_fields=['status'])
            logger.info(f"[PAPER] Order {order_id} cancelled")
            return True
        except PaperOrder.DoesNotExist:
            logger.warning(f"[PAPER] Order {order_id} not found for cancellation")
            return False

    # ===== Quotes & Data =====

    def get_quote(self, symbol: str, **kwargs) -> Optional[Quote]:
        ltp = self._fetch_ltp(symbol)
        if ltp is None:
            return None
        return Quote(
            symbol=symbol,
            ltp=ltp,
            bid=ltp * 0.9999,   # Approximate
            ask=ltp * 1.0001,
            high=ltp,
            low=ltp,
            volume=0,
            raw_data={'source': 'paper_broker'},
        )

    def search_symbol(self, symbol: str, **kwargs) -> List[Dict]:
        # Delegate to existing contract data
        from apps.data.models import ContractData
        contracts = ContractData.objects.filter(
            symbol__icontains=symbol,
        )[:10]
        return [
            {'symbol': c.symbol, 'name': c.symbol}
            for c in contracts
        ]

    # ===== Market Status =====

    def is_market_open(self) -> bool:
        now = datetime.now(IST)
        if now.weekday() >= 5:  # Sat/Sun
            return False
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close

    # ===== WebSocket (no-op) =====

    def subscribe_live_feed(self, symbols: List[str], **kwargs) -> bool:
        return True

    def unsubscribe_live_feed(self, symbols: List[str]) -> bool:
        return True

    # ===== Internal Helpers =====

    def _fetch_ltp(self, symbol: str) -> Optional[float]:
        """
        Fetch LTP from market data layer (NOT from broker API).

        Tries multiple sources in order:
        1. ContractData model (if recently updated)
        2. get_ltp_from_neo (which uses Breeze market data, not broker orders)
        """
        try:
            # Try ContractData first (already-fetched market data)
            from apps.data.models import ContractData
            contract = ContractData.objects.filter(
                trading_symbol=symbol,
            ).first()
            if contract and contract.price:
                ltp = float(contract.price)
                if ltp > 0:
                    return ltp
        except Exception:
            pass

        try:
            # Fallback to Neo quotes (fetches from Breeze market data feed)
            from apps.brokers.integrations.neo.quotes import get_ltp_from_neo
            ltp = get_ltp_from_neo(symbol)
            if ltp and ltp > 0:
                return ltp
        except Exception as e:
            logger.warning(f"[PAPER] LTP fetch failed for {symbol}: {e}")

        return None
