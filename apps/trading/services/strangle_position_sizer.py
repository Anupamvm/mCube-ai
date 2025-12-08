"""
Nifty Strangle Position Sizer

Calculates position sizing for Nifty Strangle strategy with:
- Neo API margin fetching
- Averaging down logic (20%, 50%, 50%)
- Max profit/loss at Support/Resistance levels
- Max loss at 5% drop scenarios
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StranglePositionSizer:
    """
    Position sizing calculator specifically for Nifty Strangle strategy
    """

    # Averaging protocol from design doc
    AVERAGING_PROTOCOL = {
        'max_attempts': 3,
        'attempt_1_percent': Decimal('20'),  # 20% of current balance
        'attempt_2_percent': Decimal('50'),  # 50% of current balance
        'attempt_3_percent': Decimal('50'),  # 50% of current balance
        'trigger_percent': Decimal('1.0'),   # Trigger when position down 1%
    }

    # Risk management
    MAX_POSITION_PERCENT = Decimal('30')  # Max 30% of margin for initial position
    MIN_MARGIN_BUFFER = Decimal('0.15')   # Keep 15% margin buffer
    NIFTY_LOT_SIZE = Decimal('50')  # NIFTY lot size as Decimal for calculations

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
            # Use the WORKING NeoAPI class from tools/neo.py (same as the working margin endpoint)
            from tools.neo import NeoAPI

            logger.info("Fetching margin from Kotak Neo API using tools/neo.py...")

            # Initialize Neo API (handles session management automatically)
            neo = NeoAPI()

            # Use the working get_margin() method
            margin_data = neo.get_margin()

            if not margin_data:
                raise ValueError("Margin not found: Neo API returned empty response")

            logger.info(f"Neo margin fetched successfully using tools/neo.py:")
            logger.info(f"  Available Margin: ₹{margin_data['available_margin']:,.2f}")
            logger.info(f"  Used Margin: ₹{margin_data['used_margin']:,.2f}")
            logger.info(f"  Total Margin: ₹{margin_data['total_margin']:,.2f}")
            logger.info(f"  Collateral: ₹{margin_data['collateral']:,.2f}")

            # Convert to Decimal for calculations
            available_margin = Decimal(str(margin_data['available_margin']))
            used_margin = Decimal(str(margin_data['used_margin']))
            total_margin = Decimal(str(margin_data['total_margin']))
            collateral = Decimal(str(margin_data['collateral']))

            # Log warning if margin is zero or negative but still return the data
            if available_margin <= 0:
                logger.warning(f"Neo API returned zero or negative available margin: ₹{available_margin:,.2f}")
                logger.warning("Position sizing will recommend 0 lots due to insufficient margin")

            return {
                'available_margin': available_margin,
                'used_margin': used_margin,
                'total_margin': total_margin,
                'collateral': collateral,
                'source': 'neo_api',
                'fetched_at': datetime.now(),
                'margin_available': available_margin > 0  # Flag to indicate if margin is available
            }

        except Exception as e:
            logger.error(f"Error fetching Neo margin: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise ValueError(f"Margin not found: {str(e)}")

    def get_neo_margin_for_strangle(
        self,
        call_strike: int,
        put_strike: int,
        expiry_date: str = None
    ) -> Optional[Decimal]:
        """
        Get actual margin required from Neo API for the strangle position

        Args:
            call_strike: Call option strike
            put_strike: Put option strike
            expiry_date: Expiry date in format YYYY-MM-DD (defaults to current week)

        Returns:
            Decimal: Actual margin per lot from Neo API, or None if unavailable
        """
        try:
            from apps.core.models import CredentialStore
            from neo_api_client import NeoAPI

            neo_creds = CredentialStore.objects.filter(service='kotakneo').first()

            if not neo_creds or not neo_creds.session_token:
                logger.warning("Neo credentials not available for margin calculation")
                return None

            neo = NeoAPI(
                access_token=neo_creds.session_token,
                environment='prod'
            )

            # For Nifty options, we need to construct the trading symbol
            # Format: NIFTY[DDMMMYY][STRIKE][CE/PE]
            # Example: NIFTY05DEC2424000CE

            # If no expiry provided, use nearest weekly expiry (Thursday)
            if not expiry_date:
                from datetime import datetime, timedelta
                today = datetime.now()
                days_ahead = (3 - today.weekday()) % 7  # 3 = Thursday
                if days_ahead == 0 and today.hour >= 15:  # After 3:30 PM on Thursday
                    days_ahead = 7
                expiry = today + timedelta(days=days_ahead)
                expiry_str = expiry.strftime('%d%b%y').upper()
            else:
                from datetime import datetime
                expiry = datetime.strptime(expiry_date, '%Y-%m-%d')
                expiry_str = expiry.strftime('%d%b%y').upper()

            # Construct symbols
            call_symbol = f"NIFTY{expiry_str}{call_strike}CE"
            put_symbol = f"NIFTY{expiry_str}{put_strike}PE"

            # Neo margin calculator - requires scrip details
            # Try using span_calculator endpoint if available
            try:
                # Get scrip codes first
                call_quote = neo.quotes(
                    instrument_tokens=[
                        {"instrument_token": call_symbol, "exchange_segment": "nse_fo"}
                    ]
                )
                put_quote = neo.quotes(
                    instrument_tokens=[
                        {"instrument_token": put_symbol, "exchange_segment": "nse_fo"}
                    ]
                )

                if call_quote and put_quote:
                    # Calculate combined margin using Neo's basket margin API if available
                    # For now, return None to use estimate
                    logger.info(f"Got quotes for {call_symbol} and {put_symbol}")
                    # TODO: Implement actual margin calculation API call
                    return None

            except Exception as quote_error:
                logger.warning(f"Neo quote/margin API failed: {quote_error}")
                return None

        except Exception as e:
            logger.warning(f"Error fetching Neo margin for strangle: {e}")
            return None

    def calculate_strangle_position_size(
        self,
        call_strike: int,
        put_strike: int,
        call_premium: Decimal,
        put_premium: Decimal,
        spot_price: Decimal,
        support_levels: List[Decimal],
        resistance_levels: List[Decimal],
        vix: Optional[Decimal] = None
    ) -> Dict:
        """
        Calculate optimal position sizing for Nifty Strangle

        Args:
            call_strike: Call option strike
            put_strike: Put option strike
            call_premium: Call option premium
            put_premium: Put option premium
            spot_price: Current Nifty spot price
            support_levels: List of support levels (S1, S2, S3)
            resistance_levels: List of resistance levels (R1, R2, R3)
            vix: India VIX (optional)

        Returns:
            dict: Complete position sizing with averaging scenarios
        """
        try:
            # Get available margin from Neo
            margin_data = self.get_neo_margin()
            available_margin = margin_data['available_margin']

            total_premium = call_premium + put_premium

            logger.info("=" * 80)
            logger.info("POSITION SIZING CALCULATION - DETAILED BREAKDOWN")
            logger.info("=" * 80)
            logger.info(f"Strangle position sizing:")
            logger.info(f"  Strikes: CE {call_strike}, PE {put_strike}")
            logger.info(f"  Premiums: CE ₹{call_premium}, PE ₹{put_premium}, Total ₹{total_premium}")
            logger.info(f"  Spot: ₹{spot_price}, VIX: {vix}")
            logger.info("")
            logger.info("STEP 1: MARGIN FROM KOTAK NEO")
            logger.info(f"  Source: {margin_data['source']}")
            logger.info(f"  Available Margin: ₹{available_margin:,.2f}")
            logger.info(f"  Fetched at: {margin_data['fetched_at']}")

            # Calculate per-lot margin requirement
            # For selling strangles: SPAN + Exposure margin based on strike value
            # Margin = Higher strike × Lot size × SPAN factor
            # Based on actual observation: ~₹195K for 24000 strike = 16.28% of notional
            higher_strike = max(call_strike, put_strike)
            notional_value = Decimal(str(higher_strike)) * self.NIFTY_LOT_SIZE

            # Use 16% of notional value as margin (realistic for Nifty short strangles)
            margin_per_lot = notional_value * Decimal('0.16')

            total_premium_value = (call_premium + put_premium) * self.NIFTY_LOT_SIZE

            logger.info("")
            logger.info("STEP 2: MARGIN REQUIRED PER LOT")
            logger.info(f"  Higher Strike: ₹{higher_strike:,.0f}")
            logger.info(f"  Lot Size: {self.NIFTY_LOT_SIZE}")
            logger.info(f"  Notional Value: {higher_strike:,.0f} × {self.NIFTY_LOT_SIZE} = ₹{notional_value:,.2f}")
            logger.info(f"  SPAN Margin Factor: 16%")
            logger.info(f"  Margin per Lot: ₹{notional_value:,.2f} × 0.16 = ₹{margin_per_lot:,.2f}")
            logger.info(f"  Premium per Lot: (₹{call_premium} + ₹{put_premium}) × {self.NIFTY_LOT_SIZE} = ₹{total_premium_value:,.2f}")

            # Max loss per lot = unlimited for naked short strangle
            # But we'll use strike values as proxy
            max_loss_per_lot_ce = (Decimal(str(call_strike)) - call_premium) * self.NIFTY_LOT_SIZE
            max_loss_per_lot_pe = (Decimal(str(put_strike)) - put_premium) * self.NIFTY_LOT_SIZE

            # Premium collected per lot
            premium_per_lot = total_premium * self.NIFTY_LOT_SIZE

            logger.info(f"  Margin/Lot: ₹{margin_per_lot:,.2f}")
            logger.info(f"  Premium/Lot: ₹{premium_per_lot:,.2f}")

            # Calculate initial position size
            usable_margin = available_margin * (Decimal('1') - self.MIN_MARGIN_BUFFER)
            max_position_margin = available_margin * (self.MAX_POSITION_PERCENT / Decimal('100'))

            logger.info(f"  Margin Calculations:")
            logger.info(f"    Available Margin: ₹{available_margin:,.2f}")
            logger.info(f"    Usable (85%): ₹{usable_margin:,.2f}")
            logger.info(f"    Max Position (30%): ₹{max_position_margin:,.2f}")
            logger.info(f"    Margin per Lot: ₹{margin_per_lot:,.2f}")

            # Calculate lots using 50% margin utilization rule
            # Max lots = Available Margin / Margin per Lot
            # Recommended = Max lots / 2 (for 50% utilization)

            # Handle negative or zero available margin
            insufficient_margin = available_margin <= 0

            if insufficient_margin:
                max_lots_possible = 0
                recommended_lots = 0
                logger.warning("")
                logger.warning("STEP 3: LOT CALCULATION - INSUFFICIENT MARGIN")
                logger.warning(f"  Available Margin: ₹{available_margin:,.2f} (NEGATIVE/ZERO)")
                logger.warning(f"  Used Margin: ₹{margin_data.get('used_margin', 0):,.2f}")
                logger.warning(f"  Collateral: ₹{margin_data.get('collateral', 0):,.2f}")
                logger.warning(f"  ")
                logger.warning(f"  ⚠️  MARGIN EXHAUSTED - Account is over-leveraged")
                logger.warning(f"  ⚠️  Recommended Lots: 0 (cannot take new positions)")
                logger.warning(f"  ")
                logger.warning(f"  Action Required: Close existing positions or add funds")
            else:
                max_lots_possible = int(available_margin / margin_per_lot)
                # Use only 50% of available margin for initial position
                recommended_lots = max(1, int(max_lots_possible / 2))

                logger.info("")
                logger.info("STEP 3: LOT CALCULATION (50% MARGIN RULE)")
                logger.info(f"  Formula: (Available Margin ÷ Margin per Lot) ÷ 2")
                logger.info(f"  ")
                logger.info(f"  Available Margin: ₹{available_margin:,.2f}")
                logger.info(f"  Margin per Lot: ₹{margin_per_lot:,.2f}")
                logger.info(f"  ")
                logger.info(f"  Max Lots (100% margin): ₹{available_margin:,.2f} ÷ ₹{margin_per_lot:,.2f} = {max_lots_possible} lots")
                logger.info(f"  Recommended (50% rule): {max_lots_possible} ÷ 2 = {recommended_lots} lots")
                logger.info(f"  ")
                logger.info(f"  Margin to be used: {recommended_lots} × ₹{margin_per_lot:,.2f} = ₹{margin_per_lot * recommended_lots:,.2f}")
                logger.info(f"  Margin utilization: {float((margin_per_lot * recommended_lots / available_margin) * 100):.1f}%")

                if recommended_lots < 1 and available_margin > margin_per_lot:
                    logger.warning(f"Calculated 0 lots but have sufficient margin. Setting to 1 lot.")
                    recommended_lots = 1

            logger.info(f"    Final Recommended: {recommended_lots} lots")

            if recommended_lots == 0 and not insufficient_margin:
                logger.error(f"ZERO LOTS CALCULATED!")
                logger.error(f"  margin_per_lot: {margin_per_lot}")
                logger.error(f"  usable_margin: {usable_margin}")
                logger.error(f"  Ratio: {usable_margin / margin_per_lot if margin_per_lot > 0 else 'INFINITY'}")

            # Position sizing - same lots for both call and put
            call_lots = recommended_lots
            put_lots = recommended_lots
            total_quantity = recommended_lots * self.NIFTY_LOT_SIZE  # Per side

            # Margin and premium calculations
            total_margin_required = margin_per_lot * recommended_lots
            call_premium_collected = call_premium * self.NIFTY_LOT_SIZE * call_lots
            put_premium_collected = put_premium * self.NIFTY_LOT_SIZE * put_lots
            total_premium_collected = call_premium_collected + put_premium_collected

            # Calculate P&L at key levels (using recommended lots)
            pnl_analysis = self._calculate_pnl_at_levels(
                total_lots=recommended_lots,
                call_strike=call_strike,
                put_strike=put_strike,
                call_premium=call_premium,
                put_premium=put_premium,
                spot_price=spot_price,
                support_levels=support_levels,
                resistance_levels=resistance_levels
            )

            # Calculate averaging scenarios
            averaging_scenarios = self._calculate_averaging_scenarios(
                initial_lots=recommended_lots,
                margin_per_lot=margin_per_lot,
                premium_per_lot=premium_per_lot,
                available_margin=available_margin,
                call_premium=call_premium,
                put_premium=put_premium
            )

            # Calculate margin utilization percentage (handle zero/negative margin)
            if available_margin > 0:
                margin_utilization = float((total_margin_required / available_margin) * Decimal('100'))
            else:
                margin_utilization = 0.0  # No utilization when no margin available

            result = {
                'symbol': 'NIFTY',
                'strategy': 'SHORT_STRANGLE',
                'spot_price': float(spot_price),
                'vix': float(vix) if vix else None,

                # Strikes and Premiums
                'call_strike': call_strike,
                'put_strike': put_strike,
                'call_premium': float(call_premium),
                'put_premium': float(put_premium),
                'total_premium': float(total_premium),

                # Margin details from Neo API
                'margin_data': {
                    'available_margin': float(available_margin),
                    'used_margin': float(margin_data.get('used_margin', 0)),
                    'total_margin': float(margin_data.get('total_margin', 0)),
                    'collateral': float(margin_data.get('collateral', 0)),
                    'source': margin_data['source'],
                    'margin_per_lot': float(margin_per_lot),
                    'max_lots_possible': max_lots_possible,
                    'insufficient_margin': insufficient_margin,
                    'margin_warning': 'Account over-leveraged. Close positions or add funds.' if insufficient_margin else None,
                },

                # Position sizing
                'position': {
                    'call_lots': call_lots,
                    'put_lots': put_lots,
                    'lot_size': int(self.NIFTY_LOT_SIZE),
                    'call_quantity': call_lots * int(self.NIFTY_LOT_SIZE),
                    'put_quantity': put_lots * int(self.NIFTY_LOT_SIZE),
                    'total_margin_required': float(total_margin_required),
                    'call_premium_collected': float(call_premium_collected),
                    'put_premium_collected': float(put_premium_collected),
                    'total_premium_collected': float(total_premium_collected),
                    'max_profit': float(total_premium_collected),
                    'margin_utilization_percent': margin_utilization,
                },

                # P&L Analysis at key levels
                'pnl_analysis': pnl_analysis,

                # Backward compatibility - old structure
                'initial_position': {
                    'lots': recommended_lots,
                    'quantity': recommended_lots * int(self.NIFTY_LOT_SIZE),
                    'margin_required': float(total_margin_required),
                    'premium_collected': float(total_premium_collected),
                    'max_profit': float(total_premium_collected),
                },

                # Averaging scenarios with full data
                'averaging_scenarios': averaging_scenarios,

                'fetched_at': margin_data['fetched_at'].isoformat()
            }

            logger.info("")
            logger.info("STEP 4: FINAL POSITION")
            logger.info(f"  Call Lots: {call_lots} lots × {self.NIFTY_LOT_SIZE} qty = {call_lots * int(self.NIFTY_LOT_SIZE)} quantity")
            logger.info(f"  Put Lots: {put_lots} lots × {self.NIFTY_LOT_SIZE} qty = {put_lots * int(self.NIFTY_LOT_SIZE)} quantity")
            logger.info(f"  ")
            logger.info(f"  Call Premium: {call_lots} lots × ₹{call_premium} × {self.NIFTY_LOT_SIZE} = ₹{call_premium_collected:,.2f}")
            logger.info(f"  Put Premium: {put_lots} lots × ₹{put_premium} × {self.NIFTY_LOT_SIZE} = ₹{put_premium_collected:,.2f}")
            logger.info(f"  Total Premium Collected: ₹{total_premium_collected:,.2f}")
            logger.info(f"  ")
            logger.info(f"  Total Margin Required: ({call_lots} + {put_lots}) × ₹{margin_per_lot:,.2f} = ₹{total_margin_required:,.2f}")
            logger.info(f"  Margin Utilization: {margin_utilization:.1f}%")
            logger.info(f"  Max Profit: ₹{total_premium_collected:,.2f} (if both expire worthless)")
            logger.info("=" * 80)

            return result

        except Exception as e:
            logger.error(f"Error calculating strangle position size: {e}")
            raise

    def _calculate_averaging_scenarios(
        self,
        initial_lots: int,
        margin_per_lot: Decimal,
        premium_per_lot: Decimal,
        available_margin: Decimal,
        call_premium: Decimal,
        put_premium: Decimal
    ) -> Dict:
        """
        Calculate averaging down scenarios based on protocol:
        - Attempt 1: 20% of current balance
        - Attempt 2: 50% of current balance
        - Attempt 3: 50% of current balance
        """

        scenarios = {}

        # Current balance starts with available margin
        current_balance = available_margin
        cumulative_lots = initial_lots
        cumulative_margin = margin_per_lot * initial_lots

        # Averaging Attempt 1 (20% of balance)
        attempt_1_margin = current_balance * (self.AVERAGING_PROTOCOL['attempt_1_percent'] / Decimal('100'))
        attempt_1_lots = int(attempt_1_margin / margin_per_lot)
        attempt_1_lots = max(1, min(attempt_1_lots, initial_lots))  # At least 1, max = initial

        # Assume premiums reduce by 10% on averaging (market moved against us)
        attempt_1_call_premium = call_premium * Decimal('0.90')
        attempt_1_put_premium = put_premium * Decimal('0.90')
        attempt_1_premium = (attempt_1_call_premium + attempt_1_put_premium) * self.NIFTY_LOT_SIZE * attempt_1_lots

        scenarios['attempt_1'] = {
            'lots': attempt_1_lots,
            'quantity': attempt_1_lots * self.NIFTY_LOT_SIZE,
            'margin_required': float(margin_per_lot * attempt_1_lots),
            'premium_collected': float(attempt_1_premium),
            'trigger': f"Position down {self.AVERAGING_PROTOCOL['trigger_percent']}% from entry",
            'allocation': f"{self.AVERAGING_PROTOCOL['attempt_1_percent']}% of balance"
        }

        cumulative_lots += attempt_1_lots
        cumulative_margin += margin_per_lot * attempt_1_lots
        current_balance -= margin_per_lot * attempt_1_lots  # Reduce available balance

        scenarios['after_attempt_1'] = {
            'total_lots': cumulative_lots,
            'total_quantity': cumulative_lots * self.NIFTY_LOT_SIZE,
            'margin_required': float(cumulative_margin)
        }

        # Averaging Attempt 2 (50% of remaining balance)
        attempt_2_margin = current_balance * (self.AVERAGING_PROTOCOL['attempt_2_percent'] / Decimal('100'))
        attempt_2_lots = int(attempt_2_margin / margin_per_lot)
        attempt_2_lots = max(1, min(attempt_2_lots, int(cumulative_lots * 0.5)))

        attempt_2_call_premium = call_premium * Decimal('0.80')  # Further 10% reduction
        attempt_2_put_premium = put_premium * Decimal('0.80')
        attempt_2_premium = (attempt_2_call_premium + attempt_2_put_premium) * self.NIFTY_LOT_SIZE * attempt_2_lots

        scenarios['attempt_2'] = {
            'lots': attempt_2_lots,
            'quantity': attempt_2_lots * self.NIFTY_LOT_SIZE,
            'margin_required': float(margin_per_lot * attempt_2_lots),
            'premium_collected': float(attempt_2_premium),
            'trigger': f"Position down another {self.AVERAGING_PROTOCOL['trigger_percent']}%",
            'allocation': f"{self.AVERAGING_PROTOCOL['attempt_2_percent']}% of remaining balance"
        }

        cumulative_lots += attempt_2_lots
        cumulative_margin += margin_per_lot * attempt_2_lots
        current_balance -= margin_per_lot * attempt_2_lots

        scenarios['after_attempt_2'] = {
            'total_lots': cumulative_lots,
            'total_quantity': cumulative_lots * self.NIFTY_LOT_SIZE,
            'margin_required': float(cumulative_margin)
        }

        # Averaging Attempt 3 (50% of remaining balance)
        attempt_3_margin = current_balance * (self.AVERAGING_PROTOCOL['attempt_3_percent'] / Decimal('100'))
        attempt_3_lots = int(attempt_3_margin / margin_per_lot)
        attempt_3_lots = max(1, min(attempt_3_lots, int(cumulative_lots * 0.5)))

        attempt_3_call_premium = call_premium * Decimal('0.70')  # Further 10% reduction
        attempt_3_put_premium = put_premium * Decimal('0.70')
        attempt_3_premium = (attempt_3_call_premium + attempt_3_put_premium) * self.NIFTY_LOT_SIZE * attempt_3_lots

        scenarios['attempt_3'] = {
            'lots': attempt_3_lots,
            'quantity': attempt_3_lots * self.NIFTY_LOT_SIZE,
            'margin_required': float(margin_per_lot * attempt_3_lots),
            'premium_collected': float(attempt_3_premium),
            'trigger': f"Position down another {self.AVERAGING_PROTOCOL['trigger_percent']}%",
            'allocation': f"{self.AVERAGING_PROTOCOL['attempt_3_percent']}% of remaining balance"
        }

        cumulative_lots += attempt_3_lots
        cumulative_margin += margin_per_lot * attempt_3_lots

        scenarios['after_attempt_3'] = {
            'total_lots': cumulative_lots,
            'total_quantity': cumulative_lots * self.NIFTY_LOT_SIZE,
            'margin_required': float(cumulative_margin)
        }

        # Total after all averaging (including initial position premium)
        initial_premium = premium_per_lot * initial_lots
        total_premium = (
            float(initial_premium) +
            scenarios['attempt_1']['premium_collected'] +
            scenarios['attempt_2']['premium_collected'] +
            scenarios['attempt_3']['premium_collected']
        )

        scenarios['total_after_all_averaging'] = {
            'total_lots': cumulative_lots,
            'total_quantity': cumulative_lots * self.NIFTY_LOT_SIZE,
            'margin_required': float(cumulative_margin),
            'total_premium_collected': total_premium,
            'max_profit': total_premium,
        }

        return scenarios

    def _calculate_pnl_at_levels(
        self,
        total_lots: int,
        call_strike: int,
        put_strike: int,
        call_premium: Decimal,
        put_premium: Decimal,
        spot_price: Decimal,
        support_levels: List[Decimal],
        resistance_levels: List[Decimal]
    ) -> Dict:
        """
        Calculate P&L at various price levels:
        - At resistance levels (R1, R2, R3)
        - At support levels (S1, S2, S3)
        - At 5% drop from current spot
        - At 5% rise from current spot
        """

        total_premium_collected = (call_premium + put_premium) * self.NIFTY_LOT_SIZE * total_lots

        pnl = {}

        # Helper function to calculate P&L at a given price
        def calc_pnl_at_price(price: Decimal) -> Decimal:
            call_strike_decimal = Decimal(str(call_strike))
            put_strike_decimal = Decimal(str(put_strike))

            # Call option P&L: If price > call_strike, we lose (price - strike - premium)
            if price > call_strike_decimal:
                call_loss = (price - call_strike_decimal - call_premium) * self.NIFTY_LOT_SIZE * total_lots
            else:
                call_loss = Decimal('0')  # Call expires worthless, we keep premium

            # Put option P&L: If price < put_strike, we lose (strike - price - premium)
            if price < put_strike_decimal:
                put_loss = (put_strike_decimal - price - put_premium) * self.NIFTY_LOT_SIZE * total_lots
            else:
                put_loss = Decimal('0')  # Put expires worthless, we keep premium

            # Total P&L = Premium collected - losses
            total_pnl = total_premium_collected - call_loss - put_loss

            return total_pnl

        # Helper to calculate ROI percentage
        def calc_roi(pnl_value: Decimal, margin: Decimal) -> float:
            if margin == 0:
                return 0.0
            return float((pnl_value / margin) * Decimal('100'))

        # At resistance levels
        for i, resistance in enumerate(resistance_levels[:3], 1):
            pnl_value = calc_pnl_at_price(resistance)
            pnl[f'at_resistance_{i}'] = {
                'nifty_price': float(resistance),
                'pnl': float(pnl_value),
                'roi_percent': calc_roi(pnl_value, total_premium_collected),
                'description': f'R{i}'
            }

        # At support levels
        for i, support in enumerate(support_levels[:3], 1):
            pnl_value = calc_pnl_at_price(support)
            pnl[f'at_support_{i}'] = {
                'nifty_price': float(support),
                'pnl': float(pnl_value),
                'roi_percent': calc_roi(pnl_value, total_premium_collected),
                'description': f'S{i}'
            }

        # At 5% drop
        drop_5_percent = spot_price * Decimal('0.95')
        pnl_value_drop = calc_pnl_at_price(drop_5_percent)
        pnl['at_5_percent_drop'] = {
            'nifty_price': float(drop_5_percent),
            'pnl': float(pnl_value_drop),
            'roi_percent': calc_roi(pnl_value_drop, total_premium_collected),
            'description': '5% Drop'
        }

        # At 5% rise
        rise_5_percent = spot_price * Decimal('1.05')
        pnl_value_rise = calc_pnl_at_price(rise_5_percent)
        pnl['at_5_percent_rise'] = {
            'nifty_price': float(rise_5_percent),
            'pnl': float(pnl_value_rise),
            'roi_percent': calc_roi(pnl_value_rise, total_premium_collected),
            'description': '5% Rise'
        }

        # Max profit (both options expire worthless)
        pnl['max_profit'] = {
            'level': 'Between strikes',
            'pnl': float(total_premium_collected),
            'description': 'Max Profit (Both expire worthless)'
        }

        # Breakeven points
        upper_breakeven = Decimal(str(call_strike)) + (call_premium + put_premium)
        lower_breakeven = Decimal(str(put_strike)) - (call_premium + put_premium)

        pnl['breakeven_upper'] = {
            'nifty_price': float(upper_breakeven),
            'pnl': 0.0,
            'roi_percent': 0.0,
            'description': 'Upper Breakeven'
        }

        pnl['breakeven_lower'] = {
            'nifty_price': float(lower_breakeven),
            'pnl': 0.0,
            'roi_percent': 0.0,
            'description': 'Lower Breakeven'
        }

        return pnl
