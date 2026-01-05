"""
Broken Iron Condor Position Sizer

Calculates position sizing for Broken Iron Condor strategy (3 legs):
- Sell Call (naked)
- Sell Put
- Buy Put (insurance) - reduces margin and caps put-side loss

Key difference from strangle: Insurance put reduces margin requirement
"""

import logging
from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class IronCondorPositionSizer:
    """
    Position sizing calculator for Broken Iron Condor strategy (3 legs)
    """

    # Risk management
    MAX_POSITION_PERCENT = Decimal('50')  # Max 50% of margin for initial position
    MIN_MARGIN_BUFFER = Decimal('0.15')   # Keep 15% margin buffer
    NIFTY_LOT_SIZE = Decimal('75')        # NIFTY lot size (updated from 50 to 75)

    def __init__(self, user):
        self.user = user

    def get_neo_margin(self) -> Dict:
        """
        Get available margin from Neo API using existing authentication mechanism

        Returns:
            dict: {
                'available_margin': Decimal,
                'used_margin': Decimal,
                'total_margin': Decimal,
                'collateral': Decimal,
                'source': 'neo_api'
            }

        Raises:
            ValueError: If Neo API fails or credentials not configured
        """
        try:
            # Use the WORKING NeoAPI class from tools/neo.py
            from tools.neo import NeoAPI

            logger.info("Fetching margin from Kotak Neo API for Iron Condor...")

            # Initialize Neo API (handles session management automatically)
            neo = NeoAPI()

            # Use the working get_margin() method
            margin_data = neo.get_margin()

            if not margin_data:
                raise ValueError("Margin not found: Neo API returned empty response")

            logger.info(f"Neo margin fetched for Iron Condor:")
            logger.info(f"  Available Margin: ₹{margin_data['available_margin']:,.2f}")
            logger.info(f"  Used Margin: ₹{margin_data['used_margin']:,.2f}")

            # Convert to Decimal for calculations
            available_margin = Decimal(str(margin_data['available_margin']))
            used_margin = Decimal(str(margin_data['used_margin']))
            total_margin = Decimal(str(margin_data['total_margin']))
            collateral = Decimal(str(margin_data['collateral']))

            if available_margin <= 0:
                logger.warning(f"Neo API returned zero or negative available margin: ₹{available_margin:,.2f}")

            return {
                'available_margin': available_margin,
                'used_margin': used_margin,
                'total_margin': total_margin,
                'collateral': collateral,
                'source': 'neo_api',
                'fetched_at': datetime.now(),
                'margin_available': available_margin > 0
            }

        except Exception as e:
            logger.error(f"Error fetching Neo margin: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise ValueError(f"Margin not found: {str(e)}")

    def calculate_iron_condor_position_size(
        self,
        call_strike: int,
        put_strike: int,
        insurance_strike: int,
        call_premium: Decimal,
        put_premium: Decimal,
        insurance_premium: Decimal,
        spot_price: Decimal,
        vix: Optional[Decimal] = None
    ) -> Dict:
        """
        Calculate optimal position sizing for Broken Iron Condor (3 legs)

        Args:
            call_strike: Call option strike (sold)
            put_strike: Put option strike (sold)
            insurance_strike: Insurance put option strike (bought)
            call_premium: Call option premium
            put_premium: Put option premium
            insurance_premium: Insurance put option premium
            spot_price: Current Nifty spot price
            vix: India VIX (optional)

        Returns:
            dict: Complete position sizing with margin analysis
        """
        try:
            # Get available margin from Neo
            margin_data = self.get_neo_margin()
            available_margin = margin_data['available_margin']

            # Net premium collected
            net_premium = call_premium + put_premium - insurance_premium

            logger.info("=" * 80)
            logger.info("IRON CONDOR POSITION SIZING - DETAILED BREAKDOWN")
            logger.info("=" * 80)
            logger.info(f"Position Details:")
            logger.info(f"  Sell Call: {call_strike} CE @ ₹{call_premium}")
            logger.info(f"  Sell Put: {put_strike} PE @ ₹{put_premium}")
            logger.info(f"  Buy Insurance: {insurance_strike} PE @ ₹{insurance_premium}")
            logger.info(f"  Net Premium: ₹{net_premium} per share")
            logger.info(f"  Spot: ₹{spot_price}, VIX: {vix}")

            # Calculate margin per lot for 3-leg position
            # For Iron Condor: margin is reduced because insurance put caps risk on put side
            higher_strike = max(call_strike, put_strike)
            notional_value = Decimal(str(higher_strike)) * self.NIFTY_LOT_SIZE

            # Base margin for short strangle (16% of notional)
            base_margin_per_lot = notional_value * Decimal('0.16')

            # Insurance put reduces margin (hedge benefit)
            # The spread width determines the max loss on put side
            spread_width = put_strike - insurance_strike
            # Insurance credit: approximately 50% of spread risk is offset
            insurance_credit = Decimal(str(spread_width)) * self.NIFTY_LOT_SIZE * Decimal('0.08')

            # Net margin per lot (reduced due to insurance)
            margin_per_lot = base_margin_per_lot - insurance_credit
            margin_per_lot = max(margin_per_lot, Decimal('50000'))  # Floor at 50K per lot

            logger.info("")
            logger.info("STEP 1: MARGIN CALCULATION")
            logger.info(f"  Available Margin: ₹{available_margin:,.2f}")
            logger.info(f"  Base Margin (16% of notional): ₹{base_margin_per_lot:,.2f}")
            logger.info(f"  Insurance Credit (spread hedge): -₹{insurance_credit:,.2f}")
            logger.info(f"  Net Margin per Lot: ₹{margin_per_lot:,.2f}")

            # Calculate lots using 50% margin utilization rule
            insufficient_margin = available_margin <= 0

            if insufficient_margin:
                max_lots_possible = 0
                recommended_lots = 0
                logger.warning("INSUFFICIENT MARGIN - Cannot take position")
            else:
                max_lots_possible = int(available_margin / margin_per_lot)
                # Use only 50% of available margin for initial position
                recommended_lots = max(1, int(max_lots_possible / 2))

                logger.info("")
                logger.info("STEP 2: LOT CALCULATION (50% MARGIN RULE)")
                logger.info(f"  Max Lots (100% margin): {max_lots_possible} lots")
                logger.info(f"  Recommended (50% rule): {recommended_lots} lots")

            # Calculate position values
            quantity = recommended_lots * int(self.NIFTY_LOT_SIZE)
            total_margin_required = float(margin_per_lot * recommended_lots)

            # Premium calculations
            call_premium_collected = float(call_premium * self.NIFTY_LOT_SIZE * recommended_lots)
            put_premium_collected = float(put_premium * self.NIFTY_LOT_SIZE * recommended_lots)
            insurance_premium_paid = float(insurance_premium * self.NIFTY_LOT_SIZE * recommended_lots)
            net_premium_collected = call_premium_collected + put_premium_collected - insurance_premium_paid

            # Max profit = Net premium collected (if all expire worthless between strikes)
            max_profit = net_premium_collected

            # Max loss on put side = (spread_width - net_premium) x quantity
            # Spread width = put_strike - insurance_strike
            max_loss_put_side = float(
                (Decimal(str(spread_width)) - net_premium) * self.NIFTY_LOT_SIZE * recommended_lots
            )
            max_loss_put_side = max(0, max_loss_put_side)  # Can't be negative

            # Max loss on call side = unlimited (no insurance on call)
            # For display, show theoretical loss at +5% move
            call_5pct_loss = float(
                (spot_price * Decimal('0.05') - call_premium) * self.NIFTY_LOT_SIZE * recommended_lots
            )

            # Breakeven points
            upper_breakeven = float(Decimal(str(call_strike)) + net_premium)
            lower_breakeven = float(Decimal(str(put_strike)) - net_premium)

            # Margin utilization
            if available_margin > 0:
                margin_utilization = float((margin_per_lot * recommended_lots / available_margin) * 100)
            else:
                margin_utilization = 0.0

            logger.info("")
            logger.info("STEP 3: FINAL POSITION SUMMARY")
            logger.info(f"  Lots: {recommended_lots}")
            logger.info(f"  Quantity: {quantity}")
            logger.info(f"  Net Premium: ₹{net_premium_collected:,.2f}")
            logger.info(f"  Max Profit: ₹{max_profit:,.2f}")
            logger.info(f"  Max Loss (Put Side): ₹{max_loss_put_side:,.2f}")
            logger.info(f"  Total Margin: ₹{total_margin_required:,.2f}")
            logger.info(f"  Margin Utilization: {margin_utilization:.1f}%")
            logger.info("=" * 80)

            result = {
                'symbol': 'NIFTY',
                'strategy': 'BROKEN_IRON_CONDOR',
                'spot_price': float(spot_price),
                'vix': float(vix) if vix else None,

                # Strikes
                'call_strike': call_strike,
                'put_strike': put_strike,
                'insurance_strike': insurance_strike,
                'spread_width': spread_width,

                # Premiums
                'call_premium': float(call_premium),
                'put_premium': float(put_premium),
                'insurance_premium': float(insurance_premium),
                'net_premium_per_share': float(net_premium),

                # Margin details
                'available_margin': float(available_margin),
                'used_margin': float(margin_data.get('used_margin', 0)),
                'margin_per_lot': float(margin_per_lot),
                'base_margin_per_lot': float(base_margin_per_lot),
                'insurance_credit_per_lot': float(insurance_credit),
                'total_margin_required': total_margin_required,
                'margin_utilization_percent': margin_utilization,
                'insufficient_margin': insufficient_margin,

                # Position sizing
                'max_lots_possible': max_lots_possible,
                'recommended_lots': recommended_lots,
                'position': {
                    'lots': recommended_lots,
                    'lot_size': int(self.NIFTY_LOT_SIZE),
                    'quantity': quantity,
                },

                # P&L metrics
                'call_premium_collected': call_premium_collected,
                'put_premium_collected': put_premium_collected,
                'insurance_premium_paid': insurance_premium_paid,
                'net_premium_collected': net_premium_collected,
                'max_profit': max_profit,
                'max_loss_put_side': max_loss_put_side,
                'max_loss_call_side': 'Unlimited (use stop loss)',
                'call_5pct_loss': call_5pct_loss,

                # Breakevens
                'breakeven_upper': upper_breakeven,
                'breakeven_lower': lower_breakeven,

                'fetched_at': margin_data['fetched_at'].isoformat()
            }

            return result

        except Exception as e:
            logger.error(f"Error calculating Iron Condor position size: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
