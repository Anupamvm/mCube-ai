"""
Position Sizing Calculator with Margin Fetching

Calculates optimal position sizes, margin requirements, and averaging down strategies
for futures trading using ICICI Breeze API for real-time margin data.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Comprehensive position sizing calculator for futures trading

    Features:
    - Fetches real-time margin requirements from ICICI Breeze
    - Calculates optimal lot sizes based on available capital
    - Provides averaging down strategies with entry levels
    - Risk management with stop loss and target calculations
    """

    def __init__(self, breeze_client=None):
        """
        Initialize position sizer

        Args:
            breeze_client: ICICI Breeze API client instance
        """
        self.breeze = breeze_client

    def fetch_margin_requirement(self, stock_code: str, expiry: str,
                                 quantity: int, direction: str = 'LONG',
                                 futures_price: float = 0) -> Dict:
        """
        Estimate margin requirement for futures contracts

        Breeze API doesn't provide per-contract margin calculation, so we estimate:
        - SPAN Margin: ~10-12% of contract value
        - Exposure Margin: ~3-5% of contract value
        - Total: ~15% of contract value

        Args:
            stock_code: NSE stock code (e.g., 'RELIANCE')
            expiry: Expiry date in DD-MMM-YYYY format (e.g., '28-NOV-2024')
            quantity: Number of contracts (lot size)
            direction: 'LONG' or 'SHORT'
            futures_price: Current futures price (for estimation)

        Returns:
            dict: {
                'success': bool,
                'total_margin': float,
                'span_margin': float,
                'exposure_margin': float,
                'margin_per_lot': float,
                'error': str (if failed)
            }
        """
        try:
            if not self.breeze:
                return {
                    'success': False,
                    'error': 'Breeze client not initialized'
                }

            logger.info(f"Estimating margin for {stock_code} {expiry} - {quantity} units - {direction}")

            # Estimate margin as percentage of contract value
            # Typical futures margins: SPAN ~10%, Exposure ~5%
            contract_value = futures_price * quantity

            # Conservative estimates
            span_margin = contract_value * 0.12  # 12% SPAN
            exposure_margin = contract_value * 0.05  # 5% Exposure
            total_margin = span_margin + exposure_margin  # ~17% total

            margin_per_lot = total_margin

            logger.info(f"Estimated margin for {stock_code}: ₹{margin_per_lot:,.0f} (17% of contract value ₹{contract_value:,.0f})")

            return {
                'success': True,
                'total_margin': total_margin,
                'span_margin': span_margin,
                'exposure_margin': exposure_margin,
                'margin_per_lot': margin_per_lot,
                'method': 'estimated',
                'estimation_percent': 17.0
            }

        except Exception as e:
            logger.error(f"Error estimating margin: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def calculate_position_size(self,
                                available_capital: float,
                                futures_price: float,
                                lot_size: int,
                                margin_per_lot: float,
                                risk_percent: float = 2.0,
                                max_lots: int = 10) -> Dict:
        """
        Calculate optimal position size based on available capital and risk tolerance

        Args:
            available_capital: Available trading capital in ₹
            futures_price: Current futures price
            lot_size: Contract lot size
            margin_per_lot: Margin required per lot
            risk_percent: Maximum risk per trade as % of capital (default 2%)
            max_lots: Maximum lots to trade (safety limit)

        Returns:
            dict: Position sizing recommendations
        """
        try:
            # Calculate maximum affordable lots based on margin
            max_affordable_lots = int(available_capital / margin_per_lot) if margin_per_lot > 0 else 0

            # Calculate risk-based lot size (risk 2% of capital per trade)
            risk_amount = available_capital * (risk_percent / 100)

            # Assume 2% stop loss per lot
            risk_per_lot = futures_price * lot_size * 0.02
            risk_based_lots = int(risk_amount / risk_per_lot) if risk_per_lot > 0 else 0

            # Take the minimum of: affordable, risk-based, and max_lots
            recommended_lots = min(max_affordable_lots, risk_based_lots, max_lots)
            recommended_lots = max(1, recommended_lots)  # At least 1 lot

            # Calculate position details
            total_margin_required = margin_per_lot * recommended_lots
            position_value = futures_price * lot_size * recommended_lots

            # Capital utilization
            capital_used_pct = (total_margin_required / available_capital * 100) if available_capital > 0 else 0
            remaining_capital = available_capital - total_margin_required

            return {
                'recommended_lots': recommended_lots,
                'max_affordable_lots': max_affordable_lots,
                'risk_based_lots': risk_based_lots,
                'total_margin_required': total_margin_required,
                'position_value': position_value,
                'capital_used_percent': round(capital_used_pct, 2),
                'remaining_capital': remaining_capital,
                'lot_details': {
                    'futures_price': futures_price,
                    'lot_size': lot_size,
                    'margin_per_lot': margin_per_lot,
                    'value_per_lot': futures_price * lot_size
                }
            }

        except Exception as e:
            logger.error(f"Error calculating position size: {e}", exc_info=True)
            return {
                'error': str(e),
                'recommended_lots': 1  # Safe default
            }

    def generate_averaging_strategy(self,
                                     entry_price: float,
                                     direction: str,
                                     lot_size: int,
                                     initial_lots: int,
                                     available_capital: float,
                                     margin_per_lot: float,
                                     num_levels: int = 3) -> Dict:
        """
        Generate averaging down/up strategy with multiple entry levels

        Args:
            entry_price: Initial entry price
            direction: 'LONG' or 'SHORT'
            lot_size: Contract lot size
            initial_lots: Number of lots for initial entry
            available_capital: Total available capital
            margin_per_lot: Margin required per lot
            num_levels: Number of averaging levels (default 3)

        Returns:
            dict: Averaging strategy with entry levels, quantities, and targets
        """
        try:
            levels = []

            if direction == 'LONG':
                # For LONG: Average down at lower prices
                price_drops = [0, 2, 4, 6][:num_levels + 1]  # 0%, 2%, 4%, 6%

                cumulative_lots = 0
                cumulative_cost = 0

                for i, drop_pct in enumerate(price_drops):
                    level_price = entry_price * (1 - drop_pct / 100)

                    # First level uses initial lots, subsequent levels add more
                    if i == 0:
                        level_lots = initial_lots
                    else:
                        # Add 50% more lots at each level (pyramid strategy)
                        level_lots = int(initial_lots * 0.5)

                    # Check if we have enough margin
                    required_margin = margin_per_lot * level_lots
                    if cumulative_lots > 0:
                        # Check remaining capital after previous levels
                        used_margin = margin_per_lot * cumulative_lots
                        if required_margin > (available_capital - used_margin):
                            level_lots = int((available_capital - used_margin) / margin_per_lot)
                            if level_lots <= 0:
                                break  # No more capital

                    cumulative_lots += level_lots
                    cumulative_cost += level_price * lot_size * level_lots

                    average_price = cumulative_cost / (lot_size * cumulative_lots) if cumulative_lots > 0 else level_price

                    # Calculate targets (2%, 4%, 6% profit from average)
                    target_1 = average_price * 1.02
                    target_2 = average_price * 1.04
                    target_3 = average_price * 1.06

                    # Stop loss: 3% below average
                    stop_loss = average_price * 0.97

                    levels.append({
                        'level': i + 1,
                        'trigger_price': round(level_price, 2),
                        'trigger_drop_pct': drop_pct,
                        'lots': level_lots,
                        'quantity': level_lots * lot_size,
                        'value': round(level_price * lot_size * level_lots, 2),
                        'margin_required': round(margin_per_lot * level_lots, 2),
                        'cumulative_lots': cumulative_lots,
                        'cumulative_quantity': cumulative_lots * lot_size,
                        'average_price': round(average_price, 2),
                        'targets': {
                            't1': round(target_1, 2),
                            't2': round(target_2, 2),
                            't3': round(target_3, 2)
                        },
                        'stop_loss': round(stop_loss, 2),
                        'action': 'BUY'
                    })

            else:  # SHORT
                # For SHORT: Average up at higher prices
                price_rises = [0, 2, 4, 6][:num_levels + 1]  # 0%, 2%, 4%, 6%

                cumulative_lots = 0
                cumulative_cost = 0

                for i, rise_pct in enumerate(price_rises):
                    level_price = entry_price * (1 + rise_pct / 100)

                    if i == 0:
                        level_lots = initial_lots
                    else:
                        level_lots = int(initial_lots * 0.5)

                    required_margin = margin_per_lot * level_lots
                    if cumulative_lots > 0:
                        used_margin = margin_per_lot * cumulative_lots
                        if required_margin > (available_capital - used_margin):
                            level_lots = int((available_capital - used_margin) / margin_per_lot)
                            if level_lots <= 0:
                                break

                    cumulative_lots += level_lots
                    cumulative_cost += level_price * lot_size * level_lots

                    average_price = cumulative_cost / (lot_size * cumulative_lots) if cumulative_lots > 0 else level_price

                    # Targets for SHORT (prices going down)
                    target_1 = average_price * 0.98
                    target_2 = average_price * 0.96
                    target_3 = average_price * 0.94

                    # Stop loss: 3% above average
                    stop_loss = average_price * 1.03

                    levels.append({
                        'level': i + 1,
                        'trigger_price': round(level_price, 2),
                        'trigger_rise_pct': rise_pct,
                        'lots': level_lots,
                        'quantity': level_lots * lot_size,
                        'value': round(level_price * lot_size * level_lots, 2),
                        'margin_required': round(margin_per_lot * level_lots, 2),
                        'cumulative_lots': cumulative_lots,
                        'cumulative_quantity': cumulative_lots * lot_size,
                        'average_price': round(average_price, 2),
                        'targets': {
                            't1': round(target_1, 2),
                            't2': round(target_2, 2),
                            't3': round(target_3, 2)
                        },
                        'stop_loss': round(stop_loss, 2),
                        'action': 'SELL'
                    })

            # Calculate total capital required for full strategy
            total_margin = sum(level['margin_required'] for level in levels)
            total_value = sum(level['value'] for level in levels)

            return {
                'success': True,
                'direction': direction,
                'strategy_type': 'AVERAGING_DOWN' if direction == 'LONG' else 'AVERAGING_UP',
                'levels': levels,
                'summary': {
                    'total_levels': len(levels),
                    'total_lots': cumulative_lots,
                    'total_quantity': cumulative_lots * lot_size,
                    'total_margin_required': round(total_margin, 2),
                    'total_position_value': round(total_value, 2),
                    'capital_available': available_capital,
                    'capital_remaining': round(available_capital - total_margin, 2),
                    'final_average_price': levels[-1]['average_price'] if levels else entry_price
                }
            }

        except Exception as e:
            logger.error(f"Error generating averaging strategy: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def calculate_comprehensive_position(self,
                                          stock_symbol: str,
                                          expiry: str,
                                          futures_price: float,
                                          lot_size: int,
                                          direction: str,
                                          available_capital: float,
                                          risk_percent: float = 2.0) -> Dict:
        """
        Complete position sizing calculation with margin, position size, and averaging strategy

        Args:
            stock_symbol: Stock symbol
            expiry: Expiry date
            futures_price: Current futures price
            lot_size: Contract lot size
            direction: 'LONG' or 'SHORT'
            available_capital: Available capital
            risk_percent: Risk per trade as % (default 2%)

        Returns:
            dict: Complete position sizing data including margin, position, and averaging
        """
        try:
            # Step 1: Fetch margin requirement
            quantity = lot_size  # Get margin for 1 lot first
            margin_data = self.fetch_margin_requirement(stock_symbol, expiry, quantity, direction)

            if not margin_data.get('success'):
                # Fallback: Estimate margin as 10-15% of position value
                estimated_margin = futures_price * lot_size * 0.12
                margin_per_lot = estimated_margin
                logger.warning(f"Using estimated margin: ₹{margin_per_lot:,.0f} per lot")
            else:
                margin_per_lot = margin_data.get('margin_per_lot', 0)

            # Step 2: Calculate optimal position size
            position_calc = self.calculate_position_size(
                available_capital=available_capital,
                futures_price=futures_price,
                lot_size=lot_size,
                margin_per_lot=margin_per_lot,
                risk_percent=risk_percent
            )

            recommended_lots = position_calc.get('recommended_lots', 1)

            # Step 3: Generate averaging strategy
            averaging_strategy = self.generate_averaging_strategy(
                entry_price=futures_price,
                direction=direction,
                lot_size=lot_size,
                initial_lots=recommended_lots,
                available_capital=available_capital,
                margin_per_lot=margin_per_lot,
                num_levels=3
            )

            return {
                'success': True,
                'symbol': stock_symbol,
                'expiry': expiry,
                'direction': direction,
                'current_price': futures_price,
                'lot_size': lot_size,
                'margin_data': margin_data,
                'position_sizing': position_calc,
                'averaging_strategy': averaging_strategy,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in comprehensive position calculation: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
