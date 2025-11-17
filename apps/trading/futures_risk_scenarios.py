"""
Futures Risk Scenario Calculator

Calculates detailed risk scenarios including:
- 5% and 10% loss scenarios
- Target profit scenarios
- Stop loss levels
- Risk/Reward ratios
"""

import logging
from decimal import Decimal
from typing import Dict, List

logger = logging.getLogger(__name__)


class FuturesRiskScenarios:
    """
    Calculate comprehensive risk scenarios for futures trades
    """

    @staticmethod
    def calculate_comprehensive_scenarios(
        entry_price: Decimal,
        direction: str,
        quantity: int,
        lot_size: int = 1,
        default_sl_pct: Decimal = Decimal('0.5'),  # 0.5% default stop loss
        default_target_pct: Decimal = Decimal('1.0')  # 1.0% default target
    ) -> Dict:
        """
        Calculate comprehensive risk/reward scenarios

        Args:
            entry_price: Entry price for the trade
            direction: LONG or SHORT
            quantity: Number of lots
            lot_size: Size of each lot (default: 1 for testing)
            default_sl_pct: Default stop loss percentage
            default_target_pct: Default target percentage

        Returns:
            dict: Comprehensive risk scenarios
        """

        logger.info("=" * 80)
        logger.info("FUTURES RISK SCENARIO CALCULATION")
        logger.info("=" * 80)
        logger.info(f"Entry Price: ₹{entry_price:,.2f}")
        logger.info(f"Direction: {direction}")
        logger.info(f"Quantity: {quantity} lots x {lot_size} = {quantity * lot_size} units")
        logger.info("")

        total_units = quantity * lot_size

        # Calculate default stop loss and target
        if direction == 'LONG':
            default_sl = entry_price * (Decimal('1') - default_sl_pct / Decimal('100'))
            default_target = entry_price * (Decimal('1') + default_target_pct / Decimal('100'))
        else:  # SHORT
            default_sl = entry_price * (Decimal('1') + default_sl_pct / Decimal('100'))
            default_target = entry_price * (Decimal('1') - default_target_pct / Decimal('100'))

        # SCENARIO 1: 5% Loss
        loss_5pct_scenarios = FuturesRiskScenarios._calculate_loss_scenario(
            entry_price=entry_price,
            direction=direction,
            total_units=total_units,
            loss_pct=Decimal('5.0')
        )

        # SCENARIO 2: 10% Loss
        loss_10pct_scenarios = FuturesRiskScenarios._calculate_loss_scenario(
            entry_price=entry_price,
            direction=direction,
            total_units=total_units,
            loss_pct=Decimal('10.0')
        )

        # SCENARIO 3: Default Stop Loss
        default_sl_scenario = FuturesRiskScenarios._calculate_price_scenario(
            entry_price=entry_price,
            exit_price=default_sl,
            direction=direction,
            total_units=total_units,
            scenario_name=f"Default SL ({default_sl_pct}%)"
        )

        # SCENARIO 4: Default Target
        default_target_scenario = FuturesRiskScenarios._calculate_price_scenario(
            entry_price=entry_price,
            exit_price=default_target,
            direction=direction,
            total_units=total_units,
            scenario_name=f"Default Target ({default_target_pct}%)"
        )

        # SCENARIO 5: 1% Profit
        profit_1pct_scenarios = FuturesRiskScenarios._calculate_profit_scenario(
            entry_price=entry_price,
            direction=direction,
            total_units=total_units,
            profit_pct=Decimal('1.0')
        )

        # SCENARIO 6: 2% Profit
        profit_2pct_scenarios = FuturesRiskScenarios._calculate_profit_scenario(
            entry_price=entry_price,
            direction=direction,
            total_units=total_units,
            profit_pct=Decimal('2.0')
        )

        # Calculate risk/reward ratio
        sl_loss = abs(default_sl_scenario['pnl'])
        target_profit = abs(default_target_scenario['pnl'])
        risk_reward_ratio = target_profit / sl_loss if sl_loss > 0 else Decimal('0')

        # Compile all scenarios
        all_scenarios = {
            # Core metrics
            'entry_price': str(entry_price),
            'direction': direction,
            'quantity': quantity,
            'lot_size': lot_size,
            'total_units': total_units,
            'position_value': str(entry_price * total_units),

            # Stop loss and target
            'default_stop_loss': str(default_sl),
            'default_stop_loss_pct': str(default_sl_pct),
            'default_target': str(default_target),
            'default_target_pct': str(default_target_pct),

            # Risk/Reward
            'max_loss_at_sl': str(sl_loss),
            'max_profit_at_target': str(target_profit),
            'risk_reward_ratio': str(risk_reward_ratio),

            # Detailed scenarios
            'scenarios': {
                'loss_5pct': loss_5pct_scenarios,
                'loss_10pct': loss_10pct_scenarios,
                'default_sl': default_sl_scenario,
                'default_target': default_target_scenario,
                'profit_1pct': profit_1pct_scenarios,
                'profit_2pct': profit_2pct_scenarios,
            }
        }

        # Log summary
        logger.info("RISK SCENARIOS SUMMARY:")
        logger.info("-" * 80)
        logger.info(f"5% Loss: ₹{loss_5pct_scenarios['pnl']:,.0f} (Exit: ₹{loss_5pct_scenarios['exit_price']:,.2f})")
        logger.info(f"10% Loss: ₹{loss_10pct_scenarios['pnl']:,.0f} (Exit: ₹{loss_10pct_scenarios['exit_price']:,.2f})")
        logger.info(f"Default SL ({default_sl_pct}%): ₹{default_sl_scenario['pnl']:,.0f} (Exit: ₹{default_sl:,.2f})")
        logger.info(f"Default Target ({default_target_pct}%): ₹{default_target_scenario['pnl']:,.0f} (Exit: ₹{default_target:,.2f})")
        logger.info(f"Risk/Reward Ratio: {risk_reward_ratio:.2f}:1")
        logger.info("=" * 80)
        logger.info("")

        return all_scenarios

    @staticmethod
    def _calculate_loss_scenario(
        entry_price: Decimal,
        direction: str,
        total_units: int,
        loss_pct: Decimal
    ) -> Dict:
        """Calculate loss scenario at specific percentage"""

        if direction == 'LONG':
            # For LONG, loss occurs when price drops
            exit_price = entry_price * (Decimal('1') - loss_pct / Decimal('100'))
            pnl_per_unit = exit_price - entry_price
        else:  # SHORT
            # For SHORT, loss occurs when price rises
            exit_price = entry_price * (Decimal('1') + loss_pct / Decimal('100'))
            pnl_per_unit = entry_price - exit_price

        total_pnl = pnl_per_unit * total_units

        return {
            'scenario': f'{loss_pct}% Loss',
            'exit_price': exit_price,
            'pnl_per_unit': pnl_per_unit,
            'pnl': total_pnl,
            'pnl_pct': -loss_pct,  # Negative because it's a loss
        }

    @staticmethod
    def _calculate_profit_scenario(
        entry_price: Decimal,
        direction: str,
        total_units: int,
        profit_pct: Decimal
    ) -> Dict:
        """Calculate profit scenario at specific percentage"""

        if direction == 'LONG':
            # For LONG, profit occurs when price rises
            exit_price = entry_price * (Decimal('1') + profit_pct / Decimal('100'))
            pnl_per_unit = exit_price - entry_price
        else:  # SHORT
            # For SHORT, profit occurs when price drops
            exit_price = entry_price * (Decimal('1') - profit_pct / Decimal('100'))
            pnl_per_unit = entry_price - exit_price

        total_pnl = pnl_per_unit * total_units

        return {
            'scenario': f'{profit_pct}% Profit',
            'exit_price': exit_price,
            'pnl_per_unit': pnl_per_unit,
            'pnl': total_pnl,
            'pnl_pct': profit_pct,
        }

    @staticmethod
    def _calculate_price_scenario(
        entry_price: Decimal,
        exit_price: Decimal,
        direction: str,
        total_units: int,
        scenario_name: str
    ) -> Dict:
        """Calculate scenario at specific exit price"""

        if direction == 'LONG':
            pnl_per_unit = exit_price - entry_price
        else:  # SHORT
            pnl_per_unit = entry_price - exit_price

        total_pnl = pnl_per_unit * total_units
        pnl_pct = (pnl_per_unit / entry_price) * Decimal('100')

        return {
            'scenario': scenario_name,
            'exit_price': exit_price,
            'pnl_per_unit': pnl_per_unit,
            'pnl': total_pnl,
            'pnl_pct': pnl_pct,
        }

    @staticmethod
    def format_telegram_message(scenarios: Dict) -> str:
        """
        Format risk scenarios for Telegram display

        Args:
            scenarios: Risk scenarios dictionary

        Returns:
            str: Formatted message for Telegram (HTML)
        """

        entry_price = Decimal(scenarios['entry_price'])
        direction = scenarios['direction']
        quantity = scenarios['quantity']
        total_units = scenarios['total_units']

        # Extract scenarios
        loss_5 = scenarios['scenarios']['loss_5pct']
        loss_10 = scenarios['scenarios']['loss_10pct']
        default_sl = scenarios['scenarios']['default_sl']
        default_target = scenarios['scenarios']['default_target']

        message = (
            f"<b>📊 RISK/REWARD ANALYSIS</b>\n"
            f"{'=' * 40}\n\n"

            f"<b>Position Details:</b>\n"
            f"  Entry: ₹{entry_price:,.2f}\n"
            f"  Direction: {direction}\n"
            f"  Quantity: {quantity} lots ({total_units} units)\n"
            f"  Value: ₹{Decimal(scenarios['position_value']):,.0f}\n\n"

            f"<b>⚠️ LOSS SCENARIOS:</b>\n"
            f"  📉 <b>5% Loss:</b> ₹{abs(loss_5['pnl']):,.0f}\n"
            f"     Exit Price: ₹{loss_5['exit_price']:,.2f}\n\n"

            f"  📉 <b>10% Loss:</b> ₹{abs(loss_10['pnl']):,.0f}\n"
            f"     Exit Price: ₹{loss_10['exit_price']:,.2f}\n\n"

            f"  🛑 <b>Stop Loss ({scenarios['default_stop_loss_pct']}%):</b> ₹{abs(default_sl['pnl']):,.0f}\n"
            f"     Exit Price: ₹{default_sl['exit_price']:,.2f}\n\n"

            f"<b>💰 PROFIT SCENARIOS:</b>\n"
            f"  📈 <b>Target ({scenarios['default_target_pct']}%):</b> ₹{abs(default_target['pnl']):,.0f}\n"
            f"     Exit Price: ₹{default_target['exit_price']:,.2f}\n\n"

            f"<b>Risk/Reward Ratio:</b> {Decimal(scenarios['risk_reward_ratio']):.2f}:1\n"
        )

        return message
