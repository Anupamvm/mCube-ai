"""
Risk & Profit Calculator for Trade Suggestions

Calculates:
1. Profit/Loss at different price points
2. Support and Resistance levels
3. Max profit potential
4. Breakeven levels
5. Risk/Reward ratios
6. Scenarios: 2%, 5%, 10% moves
"""

import logging
from decimal import Decimal
from typing import Dict, List, Tuple
from datetime import datetime, date

logger = logging.getLogger(__name__)


class OptionsRiskCalculator:
    """Calculate profit/loss scenarios for options trades"""

    @staticmethod
    def calculate_scenarios(
        current_price: Decimal,
        call_strike: int,
        put_strike: int,
        call_premium: Decimal,
        put_premium: Decimal,
        quantity: int,
        lot_size: int
    ) -> Dict:
        """
        Calculate profit/loss scenarios for short strangle

        For Short Strangle (selling options):
        - Max profit = Total premium collected
        - Max loss = Unlimited (but managed by SL)
        - Breakeven levels = Call strike + premium, Put strike - premium

        Args:
            current_price: Current spot price
            call_strike: Call strike price
            put_strike: Put strike price
            call_premium: Premium received for call
            put_premium: Premium received for put
            quantity: Total quantity (shares)
            lot_size: Lot size

        Returns:
            dict: Scenarios with profit/loss at various price points
        """

        total_premium = call_premium + put_premium
        max_profit = total_premium * quantity
        total_margin = Decimal('0')  # Will be updated externally

        # Breakeven levels
        call_breakeven = Decimal(str(call_strike)) + total_premium
        put_breakeven = Decimal(str(put_strike)) - total_premium

        # Profit/loss at specific percentage moves
        scenarios = []

        # Current price (0% move)
        scenarios.append({
            'move_pct': 0,
            'move_direction': 'NEUTRAL',
            'target_price': current_price,
            'profit_loss': max_profit,  # Max profit at current price
            'profit_loss_pct': (max_profit / total_margin * 100) if total_margin > 0 else 0,
            'description': 'Current price (max profit)'
        })

        # Upside scenarios
        for move_pct in [0.5, 1, 2, 5, 10]:
            target_price = current_price * (Decimal('1') + Decimal(str(move_pct)) / Decimal('100'))

            # For short call, loss increases as price goes up
            call_loss = (target_price - Decimal(str(call_strike))) * quantity if target_price > call_strike else Decimal('0')

            # For short put, we still have premium
            put_profit = put_premium * quantity

            # Total profit/loss
            total_pl = (total_premium * quantity) - call_loss

            scenarios.append({
                'move_pct': move_pct,
                'move_direction': 'UP',
                'target_price': target_price,
                'profit_loss': total_pl,
                'profit_loss_pct': (total_pl / total_margin * 100) if total_margin > 0 else 0,
                'description': f'Nifty up {move_pct}% to {target_price:.0f}'
            })

        # Downside scenarios
        for move_pct in [0.5, 1, 2, 5, 10]:
            target_price = current_price * (Decimal('1') - Decimal(str(move_pct)) / Decimal('100'))

            # For short call, we still have premium
            call_profit = call_premium * quantity

            # For short put, loss increases as price goes down
            put_loss = (Decimal(str(put_strike)) - target_price) * quantity if target_price < put_strike else Decimal('0')

            # Total profit/loss
            total_pl = (total_premium * quantity) - put_loss

            scenarios.append({
                'move_pct': -move_pct,
                'move_direction': 'DOWN',
                'target_price': target_price,
                'profit_loss': total_pl,
                'profit_loss_pct': (total_pl / total_margin * 100) if total_margin > 0 else 0,
                'description': f'Nifty down {move_pct}% to {target_price:.0f}'
            })

        return {
            'max_profit': max_profit,
            'max_loss': None,  # Unlimited for short strangle
            'call_breakeven': call_breakeven,
            'put_breakeven': put_breakeven,
            'profit_zone': {
                'lower': put_breakeven,
                'upper': call_breakeven,
                'description': f'Profitable range: {put_breakeven:.0f} to {call_breakeven:.0f}'
            },
            'loss_zone': {
                'description': 'Loss occurs beyond breakeven levels'
            },
            'scenarios': scenarios
        }

    @staticmethod
    def calculate_target_and_sl(
        current_price: Decimal,
        call_strike: int,
        put_strike: int,
        call_premium: Decimal,
        put_premium: Decimal,
        quantity: int
    ) -> Dict:
        """
        Calculate recommended target and stop-loss levels

        Target: 50-70% of max profit (conservative to moderate)
        SL: Typically at 1% move beyond breakeven

        Returns:
            dict: Target and SL recommendations
        """

        total_premium = call_premium + put_premium
        max_profit = total_premium * quantity

        # Conservative target: 50% of max profit
        conservative_target = (max_profit * Decimal('0.50')) / quantity

        # Moderate target: 70% of max profit
        moderate_target = (max_profit * Decimal('0.70')) / quantity

        # Aggressive target: 90% of max profit
        aggressive_target = (max_profit * Decimal('0.90')) / quantity

        # Stop-loss at breakeven + 1% buffer
        call_breakeven = Decimal(str(call_strike)) + total_premium
        put_breakeven = Decimal(str(put_strike)) - total_premium

        # SL would be triggered if price moves beyond either breakeven
        call_sl = call_breakeven + (call_breakeven * Decimal('0.01'))
        put_sl = put_breakeven - (put_breakeven * Decimal('0.01'))

        return {
            'targets': {
                'conservative': {
                    'value': conservative_target,
                    'profit': max_profit * Decimal('0.50'),
                    'description': '50% of max profit - safest exit'
                },
                'moderate': {
                    'value': moderate_target,
                    'profit': max_profit * Decimal('0.70'),
                    'description': '70% of max profit - balanced risk/reward'
                },
                'aggressive': {
                    'value': aggressive_target,
                    'profit': max_profit * Decimal('0.90'),
                    'description': '90% of max profit - high risk'
                }
            },
            'stop_loss': {
                'call_side': call_sl,
                'put_side': put_sl,
                'description': f'Trigger SL if Nifty breaks {put_sl:.0f} or {call_sl:.0f}'
            }
        }


class FuturesRiskCalculator:
    """Calculate profit/loss scenarios for futures trades"""

    @staticmethod
    def calculate_scenarios(
        current_price: Decimal,
        direction: str,
        quantity: int,
        stop_loss: Decimal,
        target: Decimal
    ) -> Dict:
        """
        Calculate profit/loss scenarios for directional futures trades

        For LONG: Profit if price goes up, Loss if price goes down
        For SHORT: Profit if price goes down, Loss if price goes up

        Args:
            current_price: Current price of the contract
            direction: LONG or SHORT
            quantity: Number of contracts
            stop_loss: SL price level
            target: Target price level

        Returns:
            dict: Scenarios with profit/loss at various price points
        """

        max_profit = abs(target - current_price) * quantity
        max_loss = abs(current_price - stop_loss) * quantity

        scenarios = []

        # Current price
        scenarios.append({
            'move_pct': 0,
            'move_direction': 'NEUTRAL',
            'target_price': current_price,
            'profit_loss': Decimal('0'),
            'profit_loss_pct': Decimal('0'),
            'description': 'Current price'
        })

        if direction == 'LONG':
            # Upside scenarios (profitable for LONG)
            for move_pct in [0.5, 1, 2, 5, 10]:
                target_price = current_price * (Decimal('1') + Decimal(str(move_pct)) / Decimal('100'))
                profit = (target_price - current_price) * quantity
                profit_pct = (profit / (current_price * quantity) * 100)

                scenarios.append({
                    'move_pct': move_pct,
                    'move_direction': 'UP',
                    'target_price': target_price,
                    'profit_loss': profit,
                    'profit_loss_pct': profit_pct,
                    'description': f'Price up {move_pct}% to {target_price:.2f} = ₹{profit:,.0f} profit'
                })

            # Downside scenarios (loss for LONG)
            for move_pct in [0.5, 1, 2, 5, 10]:
                target_price = current_price * (Decimal('1') - Decimal(str(move_pct)) / Decimal('100'))
                loss = (current_price - target_price) * quantity
                loss_pct = (loss / (current_price * quantity) * 100)

                scenarios.append({
                    'move_pct': -move_pct,
                    'move_direction': 'DOWN',
                    'target_price': target_price,
                    'profit_loss': -loss,
                    'profit_loss_pct': -loss_pct,
                    'description': f'Price down {move_pct}% to {target_price:.2f} = ₹{loss:,.0f} loss'
                })

        else:  # SHORT
            # Downside scenarios (profitable for SHORT)
            for move_pct in [0.5, 1, 2, 5, 10]:
                target_price = current_price * (Decimal('1') - Decimal(str(move_pct)) / Decimal('100'))
                profit = (current_price - target_price) * quantity
                profit_pct = (profit / (current_price * quantity) * 100)

                scenarios.append({
                    'move_pct': -move_pct,
                    'move_direction': 'DOWN',
                    'target_price': target_price,
                    'profit_loss': profit,
                    'profit_loss_pct': profit_pct,
                    'description': f'Price down {move_pct}% to {target_price:.2f} = ₹{profit:,.0f} profit'
                })

            # Upside scenarios (loss for SHORT)
            for move_pct in [0.5, 1, 2, 5, 10]:
                target_price = current_price * (Decimal('1') + Decimal(str(move_pct)) / Decimal('100'))
                loss = (target_price - current_price) * quantity
                loss_pct = (loss / (current_price * quantity) * 100)

                scenarios.append({
                    'move_pct': move_pct,
                    'move_direction': 'UP',
                    'target_price': target_price,
                    'profit_loss': -loss,
                    'profit_loss_pct': -loss_pct,
                    'description': f'Price up {move_pct}% to {target_price:.2f} = ₹{loss:,.0f} loss'
                })

        return {
            'max_profit': max_profit,
            'max_loss': max_loss,
            'target_price': target,
            'stop_loss_price': stop_loss,
            'risk_reward_ratio': abs(max_profit / max_loss) if max_loss > 0 else 0,
            'scenarios': scenarios
        }


class SupportResistanceCalculator:
    """Calculate support and resistance levels"""

    @staticmethod
    def calculate_from_recent_data(
        current_price: Decimal,
        high_52w: Decimal,
        low_52w: Decimal,
        high_6m: Decimal,
        low_6m: Decimal,
        high_3m: Decimal,
        low_3m: Decimal
    ) -> Dict:
        """
        Calculate support and resistance from price history

        Pivot Point Calculation:
        R1 = (2 * Pivot) - Low
        S1 = (2 * Pivot) - High
        Pivot = (High + Low) / 2

        Args:
            current_price: Current price
            high_52w, low_52w: 52-week highs/lows
            high_6m, low_6m: 6-month highs/lows
            high_3m, low_3m: 3-month highs/lows

        Returns:
            dict: Support and resistance levels
        """

        # Immediate resistance (3-month high)
        immediate_resistance = high_3m
        immediate_support = low_3m

        # Intermediate resistance (6-month high)
        intermediate_resistance = high_6m
        intermediate_support = low_6m

        # Long-term resistance (52-week high)
        long_term_resistance = high_52w
        long_term_support = low_52w

        # Pivot points from 3-month data
        pivot_3m = (high_3m + low_3m) / Decimal('2')
        r1_3m = (Decimal('2') * pivot_3m) - low_3m
        s1_3m = (Decimal('2') * pivot_3m) - high_3m

        return {
            'immediate': {
                'resistance': immediate_resistance,
                'support': immediate_support,
                'distance_to_resistance': immediate_resistance - current_price,
                'distance_to_support': current_price - immediate_support,
                'timeframe': '3-month'
            },
            'intermediate': {
                'resistance': intermediate_resistance,
                'support': intermediate_support,
                'distance_to_resistance': intermediate_resistance - current_price,
                'distance_to_support': current_price - intermediate_support,
                'timeframe': '6-month'
            },
            'long_term': {
                'resistance': long_term_resistance,
                'support': long_term_support,
                'distance_to_resistance': long_term_resistance - current_price,
                'distance_to_support': current_price - long_term_support,
                'timeframe': '52-week'
            },
            'pivot_points': {
                'pivot': pivot_3m,
                'r1': r1_3m,
                's1': s1_3m
            }
        }

    @staticmethod
    def calculate_from_bollinger_bands(
        current_price: Decimal,
        sma_20: Decimal,
        upper_band: Decimal,
        lower_band: Decimal,
        sma_50: Decimal,
        sma_200: Decimal
    ) -> Dict:
        """
        Calculate support/resistance from Bollinger Bands and moving averages

        Args:
            current_price: Current price
            sma_20: 20-period simple moving average
            upper_band: Upper Bollinger Band
            lower_band: Lower Bollinger Band
            sma_50: 50-period SMA
            sma_200: 200-period SMA

        Returns:
            dict: Support/resistance levels
        """

        return {
            'bollinger_bands': {
                'upper': upper_band,
                'middle': sma_20,
                'lower': lower_band,
                'current_position': 'overbought' if current_price > upper_band else (
                    'oversold' if current_price < lower_band else 'neutral'
                )
            },
            'moving_averages': {
                'sma_20': sma_20,
                'sma_50': sma_50,
                'sma_200': sma_200,
                'trend': 'uptrend' if sma_20 > sma_50 > sma_200 else (
                    'downtrend' if sma_20 < sma_50 < sma_200 else 'mixed'
                )
            },
            'nearest_support': min(lower_band, sma_20, sma_50),
            'nearest_resistance': max(upper_band, sma_20, sma_50)
        }

    @staticmethod
    def calculate_next_levels(
        current_price: Decimal,
        support_level: Decimal,
        resistance_level: Decimal
    ) -> Dict:
        """
        Calculate next support and resistance levels based on current levels

        Uses Fibonacci extensions to calculate next levels

        Args:
            current_price: Current price
            support_level: Nearest support
            resistance_level: Nearest resistance

        Returns:
            dict: Next levels
        """

        range_val = resistance_level - support_level

        # Fibonacci levels
        next_support = support_level - (range_val * Decimal('0.618'))
        next_resistance = resistance_level + (range_val * Decimal('0.618'))

        return {
            'current_price': current_price,
            'support': support_level,
            'support_distance': current_price - support_level,
            'support_distance_pct': ((current_price - support_level) / current_price * 100),
            'resistance': resistance_level,
            'resistance_distance': resistance_level - current_price,
            'resistance_distance_pct': ((resistance_level - current_price) / current_price * 100),
            'next_support': next_support,
            'next_support_distance_pct': ((current_price - next_support) / current_price * 100),
            'next_resistance': next_resistance,
            'next_resistance_distance_pct': ((next_resistance - current_price) / current_price * 100),
            'range': range_val,
            'breakout_potential': {
                'upside': next_resistance - current_price,
                'downside': current_price - next_support
            }
        }
