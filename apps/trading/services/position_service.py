"""
Position Service - Shared position sizing logic for futures trading

This module centralizes position sizing calculations used across:
- Futures Algorithm (algorithm_views.py)
- Trade Verification (verification_views.py)
- Position Sizing API (api_views.py)

Key functions:
- calculate_position_sizing(): Complete position sizing with 50% margin rule
- calculate_stop_loss_target(): Stop loss and target price calculation
- calculate_risk_metrics(): Risk/reward calculations
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, Union

from .margin_service import get_available_margin, get_margin_per_lot, get_margin_summary

logger = logging.getLogger(__name__)

# Position sizing constants
DEFAULT_MARGIN_UTILIZATION = 0.5  # 50% rule - initial position uses 50% margin
DEFAULT_STOP_LOSS_PCT = 0.02  # 2% stop loss
DEFAULT_TARGET_PCT = 0.04  # 4% target


def calculate_stop_loss_target(
    entry_price: Union[float, Decimal],
    direction: str,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    target_pct: float = DEFAULT_TARGET_PCT
) -> Dict[str, Decimal]:
    """
    Calculate stop loss and target prices based on direction.

    Args:
        entry_price: Entry/futures price
        direction: Trade direction ('LONG', 'SHORT', or 'NEUTRAL')
        stop_loss_pct: Stop loss percentage (default 2%)
        target_pct: Target percentage (default 4%)

    Returns:
        dict: {
            'stop_loss': Decimal,
            'target': Decimal,
            'stop_loss_pct': float,
            'target_pct': float
        }

    Example:
        >>> result = calculate_stop_loss_target(2800.0, 'LONG')
        >>> print(f"SL: ₹{result['stop_loss']}, Target: ₹{result['target']}")
    """
    entry = Decimal(str(entry_price))

    if direction.upper() == 'LONG':
        # LONG: SL below, Target above
        stop_loss = entry * (1 - Decimal(str(stop_loss_pct)))
        target = entry * (1 + Decimal(str(target_pct)))
    elif direction.upper() == 'SHORT':
        # SHORT: SL above, Target below
        stop_loss = entry * (1 + Decimal(str(stop_loss_pct)))
        target = entry * (1 - Decimal(str(target_pct)))
    else:
        # NEUTRAL: Conservative targets
        stop_loss = entry * (1 - Decimal(str(stop_loss_pct)))
        target = entry * (1 + Decimal(str(stop_loss_pct)))  # Use SL % for both sides

    return {
        'stop_loss': stop_loss,
        'target': target,
        'stop_loss_pct': stop_loss_pct,
        'target_pct': target_pct
    }


def calculate_risk_metrics(
    entry_price: Union[float, Decimal],
    stop_loss: Union[float, Decimal],
    target: Union[float, Decimal],
    lot_size: int,
    num_lots: int
) -> Dict[str, Any]:
    """
    Calculate risk and reward metrics for a position.

    Args:
        entry_price: Entry/futures price
        stop_loss: Stop loss price
        target: Target price
        lot_size: Number of shares per lot
        num_lots: Number of lots in position

    Returns:
        dict: {
            'max_loss': Decimal,
            'max_profit': Decimal,
            'risk_reward_ratio': Decimal,
            'risk_per_lot': Decimal,
            'reward_per_lot': Decimal
        }
    """
    entry = Decimal(str(entry_price))
    sl = Decimal(str(stop_loss))
    tgt = Decimal(str(target))
    total_qty = lot_size * num_lots

    # Calculate per-lot risk/reward
    risk_per_share = abs(entry - sl)
    reward_per_share = abs(tgt - entry)

    risk_per_lot = risk_per_share * lot_size
    reward_per_lot = reward_per_share * lot_size

    # Calculate total risk/reward
    max_loss = risk_per_share * total_qty
    max_profit = reward_per_share * total_qty

    # Risk/reward ratio
    risk_reward_ratio = Decimal('0')
    if max_loss > 0:
        risk_reward_ratio = max_profit / max_loss

    return {
        'max_loss': max_loss,
        'max_profit': max_profit,
        'risk_reward_ratio': risk_reward_ratio,
        'risk_per_lot': risk_per_lot,
        'reward_per_lot': reward_per_lot
    }


def calculate_position_sizing(
    breeze,
    symbol: str,
    expiry: str,
    lot_size: int,
    futures_price: Union[float, Decimal],
    direction: str = 'LONG',
    available_margin: Optional[float] = None,
    margin_utilization_pct: float = DEFAULT_MARGIN_UTILIZATION,
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
    target_pct: float = DEFAULT_TARGET_PCT
) -> Dict[str, Any]:
    """
    Calculate comprehensive position sizing with 50% margin rule.

    The 50% rule reserves half of available margin for averaging down:
    - Initial position: 50% of available margin
    - Reserve 1 (33%): First averaging position
    - Reserve 2 (17%): Second averaging position

    Args:
        breeze: Breeze client instance
        symbol: Stock symbol (e.g., 'RELIANCE')
        expiry: Expiry date in Breeze format (e.g., '27-FEB-2025')
        lot_size: Number of shares per lot
        futures_price: Current futures price
        direction: Trade direction ('LONG' or 'SHORT')
        available_margin: Pre-fetched available margin (optional)
        margin_utilization_pct: Percentage of margin to use (default 50%)
        stop_loss_pct: Stop loss percentage (default 2%)
        target_pct: Target percentage (default 4%)

    Returns:
        dict: {
            'position': {
                'recommended_lots': int,
                'total_margin_required': float,
                'entry_value': float,
                'margin_utilization_percent': float
            },
            'margin_data': {
                'available_margin': float,
                'used_margin': float,
                'total_margin': float,
                'margin_per_lot': float,
                'max_lots_possible': int,
                'futures_price': float,
                'source': str
            },
            'risk_metrics': {
                'max_loss': float,
                'max_profit': float,
                'risk_reward_ratio': float
            },
            'stop_loss': float,
            'target': float,
            'direction': str
        }

    Example:
        >>> sizing = calculate_position_sizing(
        ...     breeze, 'RELIANCE', '27-FEB-2025', 250, 2800.0, 'LONG'
        ... )
        >>> print(f"Recommended: {sizing['position']['recommended_lots']} lots")
    """
    # Get margin summary
    margin_summary = get_margin_summary(
        breeze=breeze,
        symbol=symbol,
        expiry=expiry,
        lot_size=lot_size,
        direction=direction,
        futures_price=futures_price,
        available_margin=available_margin
    )

    available_margin = margin_summary['available_margin']
    margin_per_lot = margin_summary['margin_per_lot']
    max_lots_possible = margin_summary['max_lots_possible']

    # Apply margin utilization rule (50% by default)
    safe_margin = available_margin * margin_utilization_pct

    # Calculate recommended lots
    recommended_lots = max(1, int(safe_margin / margin_per_lot)) if margin_per_lot > 0 else 1

    # Calculate position metrics
    margin_required = margin_per_lot * recommended_lots
    futures_price_float = float(futures_price)
    entry_value = futures_price_float * lot_size * recommended_lots

    # Calculate margin utilization percentage
    margin_utilization = 0
    if available_margin > 0:
        margin_utilization = (margin_required / available_margin) * 100

    # Calculate stop loss and target
    sl_target = calculate_stop_loss_target(
        entry_price=futures_price,
        direction=direction,
        stop_loss_pct=stop_loss_pct,
        target_pct=target_pct
    )

    # Calculate risk metrics
    risk_metrics = calculate_risk_metrics(
        entry_price=futures_price,
        stop_loss=sl_target['stop_loss'],
        target=sl_target['target'],
        lot_size=lot_size,
        num_lots=recommended_lots
    )

    logger.info(f"Position sizing for {symbol}: {recommended_lots} lots "
               f"({margin_utilization_pct*100:.0f}% of ₹{available_margin:,.0f} = ₹{margin_required:,.0f}, "
               f"{margin_utilization:.1f}% utilization)")

    return {
        'position': {
            'recommended_lots': recommended_lots,
            'total_margin_required': float(margin_required),
            'entry_value': float(entry_value),
            'margin_utilization_percent': round(float(margin_utilization), 2)
        },
        'margin_data': {
            'available_margin': available_margin,
            'used_margin': float(margin_required),
            'total_margin': available_margin,
            'margin_per_lot': margin_per_lot,
            'max_lots_possible': max_lots_possible,
            'futures_price': futures_price_float,
            'source': margin_summary['source']
        },
        'risk_metrics': {
            'max_loss': float(risk_metrics['max_loss']),
            'max_profit': float(risk_metrics['max_profit']),
            'risk_reward_ratio': float(risk_metrics['risk_reward_ratio']),
            'risk_per_lot': float(risk_metrics['risk_per_lot']),
            'reward_per_lot': float(risk_metrics['reward_per_lot'])
        },
        'stop_loss': float(sl_target['stop_loss']),
        'target': float(sl_target['target']),
        'direction': direction
    }


def build_position_sizing_response(
    position_sizing: Dict[str, Any],
    lot_size: int,
    direction: str
) -> Dict[str, Any]:
    """
    Build a standardized position sizing response for API endpoints.

    This creates a consistent response format used by both
    algorithm_views.py and verification_views.py.

    Args:
        position_sizing: Result from calculate_position_sizing()
        lot_size: Number of shares per lot
        direction: Trade direction

    Returns:
        dict: Standardized position sizing response with all fields
              needed for UI display and trade execution
    """
    position = position_sizing['position']
    margin_data = position_sizing['margin_data']
    risk_metrics = position_sizing['risk_metrics']

    return {
        'position': position,
        'margin_data': margin_data,
        'stop_loss': position_sizing['stop_loss'],
        'target': position_sizing['target'],
        'direction': direction,
        'position_details': {
            'lot_size': lot_size,
            'recommended_lots': position['recommended_lots'],
            'entry_value': position['entry_value'],
            'risk_amount': risk_metrics['max_loss'],
            'reward_amount': risk_metrics['max_profit'],
            'risk_reward_ratio': round(risk_metrics['risk_reward_ratio'], 2),
            'margin_required': position['total_margin_required'],
            'margin_per_lot': margin_data['margin_per_lot'],
            'available_margin': margin_data['available_margin'],
            'margin_utilization_pct': position['margin_utilization_percent'],
            'max_lots_possible': margin_data['max_lots_possible'],
            'stop_loss': position_sizing['stop_loss'],
            'target': position_sizing['target']
        }
    }
