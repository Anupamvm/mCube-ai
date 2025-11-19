"""
Position Sizing Service

Calculates optimal lot sizes for futures and options trades based on:
- Available margin (from Breeze for futures, Neo for options)
- Averaging down scenarios (3x margin requirement)
- Risk management rules
- Max profit/loss calculations
"""

import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Position sizing calculator for futures and options trades
    """

    # Risk management constants
    MAX_POSITION_PERCENT = 25  # Max % of available margin per position
    AVERAGING_DOWN_MULTIPLIER = 3  # Reserve 3x margin for averaging down
    MIN_MARGIN_BUFFER = 0.20  # Keep 20% margin buffer

    def __init__(self, user):
        self.user = user

    def get_breeze_margin(self) -> Dict:
        """
        Get available margin from Breeze API for futures trading

        Returns:
            dict: {
                'available_margin': Decimal,
                'used_margin': Decimal,
                'total_margin': Decimal,
                'source': 'breeze'
            }
        """
        try:
            from apps.brokers.integrations.breeze import get_breeze_client

            breeze = get_breeze_client()

            # Get funds
            funds_resp = breeze.get_funds()
            logger.info(f"Breeze funds response: {funds_resp}")

            if funds_resp and funds_resp.get("Status") == 200 and funds_resp.get("Success"):
                funds = funds_resp["Success"]

                # Extract margin details
                available_margin = Decimal(str(funds.get('availablemargin', 0) or 0))
                used_margin = Decimal(str(funds.get('usedmargin', 0) or 0))
                total_margin = Decimal(str(funds.get('totalmargin', 0) or 0))

                logger.info(f"Breeze margin - Available: ₹{available_margin:,.2f}, Used: ₹{used_margin:,.2f}")

                return {
                    'available_margin': available_margin,
                    'used_margin': used_margin,
                    'total_margin': total_margin,
                    'source': 'breeze',
                    'fetched_at': datetime.now()
                }
            else:
                logger.error(f"Failed to fetch Breeze funds: {funds_resp}")
                raise ValueError(f"Breeze API error: {funds_resp.get('Error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Error fetching Breeze margin: {e}")
            raise

    def get_neo_margin(self) -> Dict:
        """
        Get available margin from Neo API for options trading

        Returns:
            dict: {
                'available_margin': Decimal,
                'used_margin': Decimal,
                'total_margin': Decimal,
                'source': 'neo'
            }
        """
        try:
            # TODO: Implement Neo API margin fetch
            # For now, use placeholder
            logger.warning("Neo margin API not yet implemented, using placeholder")

            return {
                'available_margin': Decimal('100000'),  # Placeholder
                'used_margin': Decimal('0'),
                'total_margin': Decimal('100000'),
                'source': 'neo',
                'fetched_at': datetime.now()
            }

        except Exception as e:
            logger.error(f"Error fetching Neo margin: {e}")
            raise

    def calculate_futures_position_size(
        self,
        symbol: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        target: Decimal,
        lot_size: int,
        direction: str = 'LONG'
    ) -> Dict:
        """
        Calculate optimal futures position size considering averaging down

        Args:
            symbol: Stock symbol
            entry_price: Entry price
            stop_loss: Stop loss price
            target: Target price
            lot_size: Contract lot size
            direction: 'LONG' or 'SHORT'

        Returns:
            dict: Position sizing details with lot calculations
        """
        try:
            # Get available margin from Breeze
            margin_data = self.get_breeze_margin()
            available_margin = margin_data['available_margin']

            # Calculate per-lot margin requirement (conservative estimate)
            # Futures margin = ~20% of contract value for most stocks
            contract_value = entry_price * lot_size
            margin_per_lot = contract_value * Decimal('0.20')  # 20% margin

            logger.info(f"Futures position sizing for {symbol}:")
            logger.info(f"  Entry: ₹{entry_price}, Lot Size: {lot_size}")
            logger.info(f"  Contract Value: ₹{contract_value:,.2f}")
            logger.info(f"  Estimated Margin/Lot: ₹{margin_per_lot:,.2f}")
            logger.info(f"  Available Margin: ₹{available_margin:,.2f}")

            # Calculate risk per lot
            if direction == 'LONG':
                risk_per_lot = (entry_price - stop_loss) * lot_size
                profit_per_lot = (target - entry_price) * lot_size
            else:  # SHORT
                risk_per_lot = (stop_loss - entry_price) * lot_size
                profit_per_lot = (entry_price - target) * lot_size

            # Calculate max lots considering:
            # 1. Available margin
            # 2. Averaging down requirement (3x margin)
            # 3. Max position % limit
            # 4. Margin buffer

            # Step 1: Max lots from available margin
            usable_margin = available_margin * (1 - self.MIN_MARGIN_BUFFER)  # Keep 20% buffer
            max_lots_from_margin = int(usable_margin / margin_per_lot)

            # Step 2: Apply max position % limit
            max_position_margin = available_margin * (self.MAX_POSITION_PERCENT / 100)
            max_lots_from_limit = int(max_position_margin / margin_per_lot)

            # Step 3: Consider averaging down (need 3x margin for full position)
            # If we average down, we'll need 3 lots total (initial + 2 averages)
            # So divide available margin by (3 * margin_per_lot)
            max_lots_with_averaging = int(usable_margin / (self.AVERAGING_DOWN_MULTIPLIER * margin_per_lot))

            # Take the minimum of all constraints
            recommended_lots = min(
                max_lots_from_margin,
                max_lots_from_limit,
                max_lots_with_averaging,
                10  # Hard cap at 10 lots for safety
            )

            # Ensure at least 1 lot if we have any margin
            if recommended_lots < 1 and available_margin > margin_per_lot:
                recommended_lots = 1

            # Calculate scenarios
            # Scenario 1: Single position (no averaging)
            single_margin_required = margin_per_lot * recommended_lots
            single_max_loss = risk_per_lot * recommended_lots
            single_max_profit = profit_per_lot * recommended_lots

            # Scenario 2: With averaging down (3 entries)
            # Assume we average at: entry, entry-5%, entry-10%
            avg_entry_1 = entry_price
            avg_entry_2 = entry_price * Decimal('0.95')
            avg_entry_3 = entry_price * Decimal('0.90')
            avg_entry_price = (avg_entry_1 + avg_entry_2 + avg_entry_3) / 3

            averaging_total_lots = recommended_lots * self.AVERAGING_DOWN_MULTIPLIER
            averaging_margin_required = margin_per_lot * averaging_total_lots

            if direction == 'LONG':
                averaging_max_loss = (avg_entry_price - stop_loss) * lot_size * averaging_total_lots
                averaging_max_profit = (target - avg_entry_price) * lot_size * averaging_total_lots
            else:
                averaging_max_loss = (stop_loss - avg_entry_price) * lot_size * averaging_total_lots
                averaging_max_profit = (avg_entry_price - target) * lot_size * averaging_total_lots

            result = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': float(entry_price),
                'stop_loss': float(stop_loss),
                'target': float(target),
                'lot_size': lot_size,

                # Margin details
                'available_margin': float(available_margin),
                'margin_per_lot': float(margin_per_lot),
                'contract_value': float(contract_value),

                # Single position scenario
                'recommended_lots': recommended_lots,
                'total_quantity': recommended_lots * lot_size,
                'margin_required': float(single_margin_required),
                'max_loss': float(single_max_loss),
                'max_profit': float(single_max_profit),
                'risk_reward_ratio': float(single_max_profit / single_max_loss) if single_max_loss > 0 else 0,

                # Averaging down scenario
                'averaging_down': {
                    'total_lots': averaging_total_lots,
                    'total_quantity': averaging_total_lots * lot_size,
                    'entry_1': float(avg_entry_1),
                    'entry_2': float(avg_entry_2),
                    'entry_3': float(avg_entry_3),
                    'average_entry': float(avg_entry_price),
                    'margin_required': float(averaging_margin_required),
                    'max_loss': float(averaging_max_loss),
                    'max_profit': float(averaging_max_profit),
                    'risk_reward_ratio': float(averaging_max_profit / averaging_max_loss) if averaging_max_loss > 0 else 0,
                },

                # Constraints applied
                'constraints': {
                    'max_lots_from_margin': max_lots_from_margin,
                    'max_lots_from_limit': max_lots_from_limit,
                    'max_lots_with_averaging': max_lots_with_averaging,
                    'applied_constraint': self._get_applied_constraint(
                        recommended_lots,
                        max_lots_from_margin,
                        max_lots_from_limit,
                        max_lots_with_averaging
                    )
                },

                'fetched_at': margin_data['fetched_at'].isoformat()
            }

            logger.info(f"Position sizing complete:")
            logger.info(f"  Recommended: {recommended_lots} lots ({recommended_lots * lot_size} qty)")
            logger.info(f"  Single Position: Loss ₹{single_max_loss:,.2f}, Profit ₹{single_max_profit:,.2f}")
            logger.info(f"  With Averaging: Loss ₹{averaging_max_loss:,.2f}, Profit ₹{averaging_max_profit:,.2f}")

            return result

        except Exception as e:
            logger.error(f"Error calculating futures position size: {e}")
            raise

    def calculate_options_position_size(
        self,
        symbol: str,
        strike: int,
        option_type: str,
        premium: Decimal,
        lot_size: int,
        stop_loss_premium: Decimal,
        target_premium: Decimal,
        strategy: str = 'BUY'
    ) -> Dict:
        """
        Calculate optimal options position size

        Args:
            symbol: Underlying symbol (e.g., 'NIFTY')
            strike: Strike price
            option_type: 'CE' or 'PE'
            premium: Option premium
            lot_size: Contract lot size
            stop_loss_premium: Stop loss premium
            target_premium: Target premium
            strategy: 'BUY' or 'SELL'

        Returns:
            dict: Position sizing details
        """
        try:
            # Get available margin from Neo
            margin_data = self.get_neo_margin()
            available_margin = margin_data['available_margin']

            # Calculate per-lot requirements
            if strategy == 'BUY':
                # For buying options, margin = premium paid
                margin_per_lot = premium * lot_size
                max_loss_per_lot = premium * lot_size  # Max loss = premium paid
                max_profit_per_lot = (target_premium - premium) * lot_size
            else:  # SELL
                # For selling options, margin = SPAN + Exposure (typically 20-30% of strike)
                margin_per_lot = strike * lot_size * Decimal('0.25')  # Conservative 25%
                max_loss_per_lot = (stop_loss_premium - premium) * lot_size
                max_profit_per_lot = premium * lot_size  # Max profit = premium received

            logger.info(f"Options position sizing for {symbol} {strike} {option_type}:")
            logger.info(f"  Premium: ₹{premium}, Lot Size: {lot_size}")
            logger.info(f"  Margin/Lot: ₹{margin_per_lot:,.2f}")
            logger.info(f"  Available Margin: ₹{available_margin:,.2f}")

            # Calculate max lots
            usable_margin = available_margin * (1 - self.MIN_MARGIN_BUFFER)
            max_lots_from_margin = int(usable_margin / margin_per_lot)

            max_position_margin = available_margin * (self.MAX_POSITION_PERCENT / 100)
            max_lots_from_limit = int(max_position_margin / margin_per_lot)

            recommended_lots = min(
                max_lots_from_margin,
                max_lots_from_limit,
                20  # Hard cap at 20 lots for options
            )

            if recommended_lots < 1 and available_margin > margin_per_lot:
                recommended_lots = 1

            # Calculate totals
            total_margin = margin_per_lot * recommended_lots
            total_max_loss = max_loss_per_lot * recommended_lots
            total_max_profit = max_profit_per_lot * recommended_lots

            result = {
                'symbol': symbol,
                'strike': strike,
                'option_type': option_type,
                'premium': float(premium),
                'lot_size': lot_size,
                'strategy': strategy,

                # Margin details
                'available_margin': float(available_margin),
                'margin_per_lot': float(margin_per_lot),

                # Position sizing
                'recommended_lots': recommended_lots,
                'total_quantity': recommended_lots * lot_size,
                'margin_required': float(total_margin),
                'max_loss': float(total_max_loss),
                'max_profit': float(total_max_profit),
                'risk_reward_ratio': float(total_max_profit / total_max_loss) if total_max_loss > 0 else 0,

                # Stop loss and target
                'stop_loss_premium': float(stop_loss_premium),
                'target_premium': float(target_premium),

                'fetched_at': margin_data['fetched_at'].isoformat()
            }

            logger.info(f"Options position sizing complete:")
            logger.info(f"  Recommended: {recommended_lots} lots ({recommended_lots * lot_size} qty)")
            logger.info(f"  Max Loss: ₹{total_max_loss:,.2f}, Max Profit: ₹{total_max_profit:,.2f}")

            return result

        except Exception as e:
            logger.error(f"Error calculating options position size: {e}")
            raise

    def _get_applied_constraint(self, recommended, from_margin, from_limit, with_averaging):
        """Determine which constraint was applied"""
        if recommended == from_margin:
            return 'available_margin'
        elif recommended == from_limit:
            return 'max_position_percent'
        elif recommended == with_averaging:
            return 'averaging_down_requirement'
        else:
            return 'hard_cap'
