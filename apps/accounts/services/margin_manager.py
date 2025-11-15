"""
Margin Management Service

This service handles margin calculations and enforces the 50% margin usage rule.

CRITICAL BUSINESS RULE:
- Use only 50% of available margin for the first trade
- Reserve remaining 50% for:
  * Averaging opportunities (futures)
  * Emergency adjustments (strangles)
  * Unexpected margin calls
"""

import logging
from decimal import Decimal
from typing import Dict, Tuple

from apps.accounts.models import BrokerAccount

logger = logging.getLogger(__name__)


def calculate_usable_margin(account: BrokerAccount) -> Dict[str, Decimal]:
    """
    Calculate usable margin for new position entry

    CRITICAL: Use only 50% of available margin for first trade

    Rationale:
    - Reserve 50% buffer for averaging opportunities (futures)
    - Reserve 50% buffer for emergency adjustments (strangles)
    - Reserve 50% buffer for unexpected margin requirements
    - Never deploy 100% of capital to maintain flexibility

    Args:
        account: BrokerAccount instance

    Returns:
        dict: {
            'total_capital': Total allocated capital,
            'deployed_margin': Margin currently in use,
            'available_margin': Margin available for new positions,
            'usable_margin': 50% of available (for first trade),
            'reserved_margin': 50% of available (kept in reserve)
        }

    Example:
        >>> account = BrokerAccount.objects.get(broker='KOTAK')
        >>> margins = calculate_usable_margin(account)
        >>> print(f"Can use: {margins['usable_margin']}")
        Can use: 30000000.00  # 3 Crores (50% of 6Cr available)
    """

    # Get total allocated capital
    total_capital = account.allocated_capital

    # Calculate available capital (not deployed in positions)
    available_margin = account.get_available_capital()

    # Calculate deployed margin
    deployed_margin = total_capital - available_margin

    # Apply 50% rule: Use only half for first trade, reserve half
    usable_margin = available_margin * Decimal('0.50')
    reserved_margin = available_margin * Decimal('0.50')

    logger.info(
        f"Margin calculation for {account.account_name}:\n"
        f"  Total Capital:    ₹{total_capital:,.0f}\n"
        f"  Deployed:         ₹{deployed_margin:,.0f}\n"
        f"  Available:        ₹{available_margin:,.0f}\n"
        f"  Usable (50%):     ₹{usable_margin:,.0f}\n"
        f"  Reserved (50%):   ₹{reserved_margin:,.0f}"
    )

    return {
        'total_capital': total_capital,
        'deployed_margin': deployed_margin,
        'available_margin': available_margin,
        'usable_margin': usable_margin,
        'reserved_margin': reserved_margin,
    }


def check_margin_availability(
    account: BrokerAccount,
    required_margin: Decimal
) -> Tuple[bool, str]:
    """
    Check if sufficient margin is available for a trade

    Args:
        account: BrokerAccount instance
        required_margin: Margin required for the trade

    Returns:
        Tuple[bool, str]: (is_available, message)

    Example:
        >>> is_available, msg = check_margin_availability(account, Decimal('2000000'))
        >>> if not is_available:
        ...     print(msg)
        Insufficient margin. Required: ₹20,00,000, Usable: ₹18,00,000
    """

    margins = calculate_usable_margin(account)
    usable_margin = margins['usable_margin']

    if required_margin > usable_margin:
        message = (
            f"Insufficient margin. "
            f"Required: ₹{required_margin:,.0f}, "
            f"Usable: ₹{usable_margin:,.0f}"
        )
        logger.warning(message)
        return False, message

    # Check utilization percentage
    utilization_pct = (required_margin / usable_margin) * 100 if usable_margin > 0 else 0

    message = (
        f"Margin check passed. "
        f"Using ₹{required_margin:,.0f} ({utilization_pct:.1f}% of usable margin)"
    )
    logger.info(message)

    return True, message


def calculate_position_size(
    account: BrokerAccount,
    instrument_price: Decimal,
    lot_size: int,
    margin_per_lot: Decimal
) -> Dict[str, any]:
    """
    Calculate optimal position size based on available margin

    Uses the 50% margin rule to determine maximum lots

    Args:
        account: BrokerAccount instance
        instrument_price: Current price of the instrument
        lot_size: Lot size for the instrument
        margin_per_lot: Margin required per lot

    Returns:
        dict: {
            'max_lots': Maximum lots that can be traded,
            'max_quantity': Maximum quantity (max_lots * lot_size),
            'total_margin_required': Total margin for max lots,
            'total_value': Total position value,
            'remaining_margin': Margin remaining after this trade
        }

    Example:
        >>> size = calculate_position_size(
        ...     account=kotak_account,
        ...     instrument_price=Decimal('100'),
        ...     lot_size=50,
        ...     margin_per_lot=Decimal('50000')
        ... )
        >>> print(f"Can trade {size['max_lots']} lots")
        Can trade 60 lots
    """

    margins = calculate_usable_margin(account)
    usable_margin = margins['usable_margin']

    # Calculate how many lots can be traded with usable margin
    if margin_per_lot > 0:
        max_lots = int(usable_margin / margin_per_lot)
    else:
        max_lots = 0
        logger.error("Margin per lot is zero or negative")

    max_quantity = max_lots * lot_size
    total_margin_required = max_lots * margin_per_lot
    total_value = max_quantity * instrument_price
    remaining_margin = usable_margin - total_margin_required

    logger.info(
        f"Position sizing for {account.account_name}:\n"
        f"  Usable Margin:         ₹{usable_margin:,.0f}\n"
        f"  Margin per Lot:        ₹{margin_per_lot:,.0f}\n"
        f"  Max Lots:              {max_lots}\n"
        f"  Max Quantity:          {max_quantity}\n"
        f"  Total Margin Required: ₹{total_margin_required:,.0f}\n"
        f"  Total Position Value:  ₹{total_value:,.0f}\n"
        f"  Remaining Margin:      ₹{remaining_margin:,.0f}"
    )

    return {
        'max_lots': max_lots,
        'max_quantity': max_quantity,
        'total_margin_required': total_margin_required,
        'total_value': total_value,
        'remaining_margin': remaining_margin,
    }


def get_margin_utilization(account: BrokerAccount) -> Dict[str, Decimal]:
    """
    Get current margin utilization statistics

    Args:
        account: BrokerAccount instance

    Returns:
        dict: {
            'total_capital': Total allocated capital,
            'deployed_margin': Currently deployed margin,
            'available_margin': Available margin,
            'utilization_pct': Percentage of total capital utilized,
            'available_pct': Percentage of capital still available
        }
    """

    margins = calculate_usable_margin(account)

    total_capital = margins['total_capital']
    deployed_margin = margins['deployed_margin']
    available_margin = margins['available_margin']

    utilization_pct = (deployed_margin / total_capital * 100) if total_capital > 0 else Decimal('0')
    available_pct = (available_margin / total_capital * 100) if total_capital > 0 else Decimal('0')

    return {
        'total_capital': total_capital,
        'deployed_margin': deployed_margin,
        'available_margin': available_margin,
        'utilization_pct': utilization_pct,
        'available_pct': available_pct,
    }


def validate_margin_for_averaging(
    account: BrokerAccount,
    current_position_margin: Decimal,
    averaging_attempt: int
) -> Tuple[bool, str, Decimal]:
    """
    Validate if margin is available for averaging

    Averaging Rules:
    - 1st average: Use 20% of current available balance
    - 2nd average: Use 50% of current available balance
    - Max 2 averaging attempts

    Args:
        account: BrokerAccount instance
        current_position_margin: Margin used by current position
        averaging_attempt: Which averaging attempt (1 or 2)

    Returns:
        Tuple[bool, str, Decimal]: (is_valid, message, margin_for_averaging)
    """

    if averaging_attempt > 2:
        return False, "Maximum 2 averaging attempts allowed", Decimal('0')

    margins = calculate_usable_margin(account)
    available_margin = margins['available_margin']

    # Determine averaging percentage based on attempt number
    if averaging_attempt == 1:
        averaging_pct = Decimal('0.20')  # 20% for first average
        attempt_label = "1st"
    else:  # averaging_attempt == 2
        averaging_pct = Decimal('0.50')  # 50% for second average
        attempt_label = "2nd"

    margin_for_averaging = available_margin * averaging_pct

    if margin_for_averaging <= 0:
        message = f"No margin available for {attempt_label} averaging"
        logger.warning(message)
        return False, message, Decimal('0')

    message = (
        f"Margin available for {attempt_label} averaging: "
        f"₹{margin_for_averaging:,.0f} ({averaging_pct * 100:.0f}% of available)"
    )
    logger.info(message)

    return True, message, margin_for_averaging
