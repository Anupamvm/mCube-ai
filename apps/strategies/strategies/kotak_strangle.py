"""
Kotak Strangle Strategy

Strategy: Sell out-of-the-money (OTM) Nifty weekly call and put options simultaneously
         to collect premium income while maintaining delta neutrality.

Account: Kotak Securities (Rs.6 Crores)
Target: Rs.6-8 Lakhs monthly (1.0-1.3% return)
Risk Profile: Market-neutral short strangle

Key Rules:
- ONE POSITION PER ACCOUNT (enforced via morning_check)
- 50% margin usage for first trade
- 1-day minimum to expiry (skip if < 1 day)
- Minimum 50% profit to exit EOD
- Delta monitoring (alert if |net_delta| > 300)
- Exit Thursday 3:15 PM (if >=50% profit) or Friday EOD (mandatory)

Enhanced Analysis (Phase 3):
- 10-factor scoring system (250 pts, scaled to 100)
- Hard reject filters (VIX range, blocking news, gap limits, FII outflow, events)
- Asymmetric strike adjustment based on sentiment
"""

import logging
from decimal import Decimal
from datetime import time, date
from typing import Dict, Tuple, Optional

from apps.strategies.core.base_strategy import BaseStrategy
from apps.strategies.core.result_types import StrategyConfig
from apps.strategies.shared.strike_calculator import calculate_strangle_strikes
from apps.strategies.shared.market_data import get_nifty_price, get_vix, get_option_premiums
from apps.trading.risk_calculator import OptionsRiskCalculator, SupportResistanceCalculator

logger = logging.getLogger(__name__)


class KotakStrangleStrategy(BaseStrategy):
    """
    Short Strangle strategy for Kotak account.

    Unique Logic:
    - VIX-adjusted strike selection
    - Delta monitoring (alert if |net_delta| > 300)
    - Exit Thursday 3:15 PM (if >=50% profit) or Friday EOD

    Enhanced Analysis (Phase 3):
    - 10-factor multi-factor scoring
    - Hard reject filters
    - Asymmetric delta adjustments
    """

    # Minimum enhanced analysis score to proceed with entry
    MIN_ENHANCED_SCORE = 50

    def get_config(self) -> StrategyConfig:
        """Return strategy configuration."""
        return StrategyConfig(
            name="Kotak Strangle Strategy",
            strategy_type='OPTIONS',
            direction='NEUTRAL',
            entry_start_time=time(9, 0),
            entry_end_time=time(11, 30),
            min_days_to_expiry=1,
            margin_usage_pct=Decimal('0.50'),
            extra={
                'delta_alert_threshold': 300,
                'profit_target_pct': Decimal('0.50'),
            }
        )

    def run_enhanced_analysis(self) -> Optional[Dict]:
        """
        Run enhanced multi-factor analysis for strangle entry.

        Implements 10-factor scoring with hard reject filters.

        Returns:
            Dict with:
                - hard_reject: bool
                - reject_reason: str or None
                - composite_score: int (0-100)
                - recommendation: str
                - entry_bias: str ('SYMMETRIC', 'WIDEN_CALL', 'WIDEN_PUT')
                - delta_adjustments: dict
                - scores: dict of component scores
                - details: dict of analysis details
        """
        from apps.strategies.analyzers.enhanced_strangle_analyzer import EnhancedStrangleAnalyzer

        logger.info("Running Enhanced Strangle Analysis...")

        # Get market data
        spot_price = get_nifty_price()
        vix = get_vix()
        days_to_expiry = self._get_days_to_expiry()

        # Initialize analyzer
        analyzer = EnhancedStrangleAnalyzer(spot_price, vix, days_to_expiry)

        # Gather comprehensive market data
        market_data = self._gather_enhanced_market_data(spot_price, vix)
        analyzer.set_market_data(market_data)

        # Run analysis
        result = analyzer.analyze()

        # Store enhanced analysis for use in entry parameters and reasoning
        self._enhanced_analysis_result = result

        return result

    def _get_days_to_expiry(self) -> int:
        """Get days to the nearest weekly expiry."""
        from apps.core.services.expiry_selector import get_next_weekly_expiry

        try:
            next_expiry = get_next_weekly_expiry('NIFTY')
            return (next_expiry - date.today()).days
        except Exception:
            return 3  # Default

    def _gather_enhanced_market_data(self, spot_price: Decimal, vix: Decimal) -> Dict:
        """
        Gather comprehensive market data for enhanced analysis.

        Returns:
            Dict with all data needed for EnhancedStrangleAnalyzer
        """
        market_data = {}

        # 1. News sentiment
        try:
            from apps.strategies.services.strangle_news_analyzer import get_market_sentiment_for_strangle
            market_data['news_sentiment'] = get_market_sentiment_for_strangle(hours_back=4)
        except Exception as e:
            logger.warning(f"Failed to get news sentiment: {e}")
            market_data['news_sentiment'] = None

        # 2. FII/DII data
        try:
            from apps.data.services.fii_dii_service import get_fii_dii_data
            market_data['fii_dii_data'] = get_fii_dii_data()
        except Exception as e:
            logger.warning(f"Failed to get FII/DII data: {e}")
            market_data['fii_dii_data'] = None

        # 3. Option chain data (PCR, OI patterns)
        try:
            from apps.brokers.services.option_chain_service import get_nifty_option_chain_summary
            market_data['option_chain'] = get_nifty_option_chain_summary()
        except Exception as e:
            logger.warning(f"Failed to get option chain data: {e}")
            market_data['option_chain'] = None

        # 4. Market breadth
        try:
            from apps.data.services.market_breadth_service import get_market_breadth
            market_data['market_breadth'] = get_market_breadth()
        except Exception as e:
            logger.warning(f"Failed to get market breadth: {e}")
            market_data['market_breadth'] = None

        # 5. Economic events
        try:
            from apps.strategies.filters.event_calendar import get_upcoming_events
            market_data['economic_events'] = get_upcoming_events(days_ahead=7)
        except Exception as e:
            logger.warning(f"Failed to get economic events: {e}")
            market_data['economic_events'] = None

        # 6. Global markets
        try:
            from apps.strategies.models import SGXNiftyData, MarketOpeningState
            from datetime import date as date_module

            sgx_data = SGXNiftyData.objects.filter(trading_date=date_module.today()).first()
            market_state = MarketOpeningState.objects.filter(trading_date=date_module.today()).first()

            market_data['global_markets'] = {
                'sgx_change': float(sgx_data.sgx_change_percent) if sgx_data and sgx_data.sgx_change_percent else None,
                'nasdaq_change': float(sgx_data.us_nasdaq_change) if sgx_data and hasattr(sgx_data, 'us_nasdaq_change') and sgx_data.us_nasdaq_change else None,
                'dow_change': float(sgx_data.us_dow_change) if sgx_data and hasattr(sgx_data, 'us_dow_change') and sgx_data.us_dow_change else None,
                'gift_change': float(market_state.gap_percent) if market_state and market_state.gap_percent else None,
            }
        except Exception as e:
            logger.warning(f"Failed to get global markets data: {e}")
            market_data['global_markets'] = None

        # 7. Price data
        try:
            from apps.strategies.models import MarketOpeningState
            from datetime import date as date_module

            market_state = MarketOpeningState.objects.filter(trading_date=date_module.today()).first()

            if market_state:
                market_data['prev_close'] = market_state.prev_close
                market_data['open_price'] = market_state.nifty_open
                market_data['price_915'] = market_state.nifty_9_15_price
                market_data['price_930'] = market_state.nifty_9_30_price
            else:
                market_data['prev_close'] = spot_price
                market_data['open_price'] = spot_price
                market_data['price_915'] = spot_price
                market_data['price_930'] = spot_price
        except Exception as e:
            logger.warning(f"Failed to get price data: {e}")

        # 8. Technical indicators (DMAs)
        try:
            from apps.data.services.technical_service import get_nifty_dmas
            dmas = get_nifty_dmas()
            market_data['dma_5'] = dmas.get('dma_5')
            market_data['dma_20'] = dmas.get('dma_20')
            market_data['dma_50'] = dmas.get('dma_50')
            market_data['dma_200'] = dmas.get('dma_200')
        except Exception as e:
            logger.warning(f"Failed to get DMA data: {e}")

        # 9. Recent Nifty Momentum (1D, 3D, 5D change) - IMPORTANT
        try:
            from apps.strategies.shared.market_data import get_nifty_change, get_consecutive_red_days
            market_data['nifty_1d_change'] = get_nifty_change(days=1)
            market_data['nifty_3d_change'] = get_nifty_change(days=3)
            market_data['nifty_5d_change'] = get_nifty_change(days=5)

            if market_data['nifty_1d_change'] is not None:
                logger.info(f"Nifty momentum: 1D={market_data['nifty_1d_change']:+.2f}%")
            if market_data['nifty_3d_change'] is not None:
                logger.info(f"Nifty momentum: 3D={market_data['nifty_3d_change']:+.2f}%")
            if market_data['nifty_5d_change'] is not None:
                logger.info(f"Nifty 5D Filter: {market_data['nifty_5d_change']:+.2f}%")
        except Exception as e:
            logger.warning(f"Failed to get Nifty momentum data: {e}")
            market_data['nifty_1d_change'] = None
            market_data['nifty_3d_change'] = None
            market_data['nifty_5d_change'] = None

        # 10. Consecutive Red Days (for PUT widening)
        try:
            from apps.strategies.shared.market_data import get_consecutive_red_days
            market_data['consecutive_red_days'] = get_consecutive_red_days()
            if market_data['consecutive_red_days'] > 0:
                logger.info(f"Consecutive red days: {market_data['consecutive_red_days']}")
        except Exception as e:
            logger.warning(f"Failed to get consecutive red days: {e}")
            market_data['consecutive_red_days'] = 0

        # 11. Is Friday (for strike tightening)
        from datetime import date as date_module
        market_data['is_friday'] = date_module.today().weekday() == 4  # 4 = Friday
        if market_data['is_friday']:
            logger.info("Friday detected - will apply tighter strikes")

        return market_data

    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """
        Calculate strikes and premiums for strangle with enhanced adjustments.

        Strike Calculation Flow:
        1. calculate_strangle_strikes() → Base strikes (VIX + delta adjustments)
        2. adjust_strikes_for_sr()      → Move away from S/R levels
        3. adjust_strikes_for_premium() → Adjust to target 3-3.5 INR
        4. check_strike_liquidity()     → Warning if OI < 100K
        """
        from apps.strategies.shared.strike_calculator import (
            adjust_strikes_for_sr,
            adjust_strikes_for_premium
        )
        from apps.strategies.shared.market_data import check_strike_liquidity

        spot_price = market_data.get('spot_price') or get_nifty_price()
        vix = market_data.get('vix') or get_vix()

        # Get enhanced analysis delta adjustments if available
        delta_adjustments = None
        if hasattr(self, '_enhanced_analysis_result') and self._enhanced_analysis_result:
            delta_adjustments = self._enhanced_analysis_result.get('delta_adjustments')

        # Step 1: Calculate base strikes using VIX + delta adjustments
        logger.info("=" * 60)
        logger.info("STEP 1: Base Strike Calculation (VIX + Delta)")
        strikes = calculate_strangle_strikes(
            spot_price=spot_price,
            days_to_expiry=market_data['days_to_expiry'],
            vix=vix,
            delta_adjustments=delta_adjustments
        )

        call_strike = strikes['call_strike']
        put_strike = strikes['put_strike']

        # Track all adjustments for audit trail
        adjustment_log = {
            'step1_base': {'call': call_strike, 'put': put_strike},
            'step2_sr': None,
            'step3_premium': None,
            'step4_liquidity': None
        }

        # Step 2: Adjust for S/R proximity
        logger.info("=" * 60)
        logger.info("STEP 2: S/R Proximity Adjustment")
        try:
            sr_result = adjust_strikes_for_sr(
                call_strike=call_strike,
                put_strike=put_strike,
                spot_price=spot_price
            )
            call_strike = sr_result['call_strike']
            put_strike = sr_result['put_strike']
            adjustment_log['step2_sr'] = {
                'call_adjusted': sr_result['call_adjusted'],
                'put_adjusted': sr_result['put_adjusted'],
                'call': call_strike,
                'put': put_strike,
                'call_reason': sr_result.get('call_adjustment_reason'),
                'put_reason': sr_result.get('put_adjustment_reason')
            }
        except Exception as e:
            logger.warning(f"S/R adjustment skipped: {e}")
            adjustment_log['step2_sr'] = {'error': str(e)}

        # Step 3: Adjust for premium target (3-3.5 INR)
        logger.info("=" * 60)
        logger.info("STEP 3: Premium-Based Adjustment (target: 3-3.5 INR)")
        try:
            premium_result = adjust_strikes_for_premium(
                call_strike=call_strike,
                put_strike=put_strike,
                expiry_date=market_data['expiry']
            )
            call_strike = premium_result['call_strike']
            put_strike = premium_result['put_strike']
            adjustment_log['step3_premium'] = {
                'call': call_strike,
                'put': put_strike,
                'call_premium': float(premium_result['call_premium']) if premium_result['call_premium'] else None,
                'put_premium': float(premium_result['put_premium']) if premium_result['put_premium'] else None,
                'call_iterations': premium_result['call_iterations'],
                'put_iterations': premium_result['put_iterations'],
                'call_status': premium_result['call_status'],
                'put_status': premium_result['put_status'],
                'warnings': premium_result['warnings']
            }

            # Log warnings
            for warning in premium_result['warnings']:
                logger.warning(f"Premium adjustment warning: {warning}")

        except Exception as e:
            logger.warning(f"Premium adjustment skipped: {e}")
            adjustment_log['step3_premium'] = {'error': str(e)}

        # Step 4: Check liquidity (warning only, don't block)
        logger.info("=" * 60)
        logger.info("STEP 4: Liquidity Check (OI >= 100,000)")
        try:
            call_liquidity = check_strike_liquidity(call_strike, 'CE', market_data['expiry'])
            put_liquidity = check_strike_liquidity(put_strike, 'PE', market_data['expiry'])
            adjustment_log['step4_liquidity'] = {
                'call': call_liquidity,
                'put': put_liquidity
            }

            if call_liquidity.get('warning'):
                logger.warning(call_liquidity['warning'])
            if put_liquidity.get('warning'):
                logger.warning(put_liquidity['warning'])

        except Exception as e:
            logger.warning(f"Liquidity check skipped: {e}")
            adjustment_log['step4_liquidity'] = {'error': str(e)}

        # Update strikes dict with final values
        strikes['call_strike'] = call_strike
        strikes['put_strike'] = put_strike

        # Get final option premiums
        call_premium, put_premium = get_option_premiums(
            call_strike,
            put_strike,
            market_data['expiry']
        )

        logger.info("=" * 60)
        logger.info(f"FINAL STRIKES: Call={call_strike}, Put={put_strike}")
        logger.info(f"FINAL PREMIUMS: Call={call_premium}, Put={put_premium}")
        logger.info("=" * 60)

        result = {
            'spot_price': spot_price,
            'vix': vix,
            'strikes': strikes,
            'call_premium': call_premium,
            'put_premium': put_premium,
            'total_premium': call_premium + put_premium,
            'expiry': market_data['expiry'],
            'days_to_expiry': market_data['days_to_expiry'],
            'adjustment_log': adjustment_log  # Full audit trail
        }

        # Include enhanced analysis in result if available
        if hasattr(self, '_enhanced_analysis_result') and self._enhanced_analysis_result:
            result['enhanced_analysis'] = {
                'composite_score': self._enhanced_analysis_result.get('composite_score'),
                'recommendation': self._enhanced_analysis_result.get('recommendation'),
                'entry_bias': self._enhanced_analysis_result.get('entry_bias'),
                'delta_adjustments': delta_adjustments,
                'scores': self._enhanced_analysis_result.get('scores', {}),
                'hard_reject': self._enhanced_analysis_result.get('hard_reject', False),
                'reject_reason': self._enhanced_analysis_result.get('reject_reason'),
                'details': self._enhanced_analysis_result.get('details', {}),
            }

        return result

    def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
        """Build position details for trade suggestion."""
        strikes = entry_params['strikes']
        quantity = sizing['quantity']
        lot_size = sizing['lot_size']
        premium_collected = entry_params['total_premium'] * quantity
        margin_used = sizing['margin_used']

        # Calculate stop-loss and target
        # For strangle: SL = 100% loss (premium becomes zero), Target = 70% profit
        stop_loss = Decimal('0')  # Premium goes to zero
        target = premium_collected * Decimal('0.70')  # 70% profit on premium

        # Calculate risk/reward scenarios
        risk_scenarios = OptionsRiskCalculator.calculate_scenarios(
            current_price=entry_params['spot_price'],
            call_strike=strikes['call_strike'],
            put_strike=strikes['put_strike'],
            call_premium=entry_params['call_premium'],
            put_premium=entry_params['put_premium'],
            quantity=quantity,
            lot_size=lot_size
        )

        # Support and Resistance
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=entry_params['spot_price'],
            support_level=entry_params['spot_price'] * Decimal('0.99'),  # 1% below
            resistance_level=entry_params['spot_price'] * Decimal('1.01')  # 1% above
        )

        return {
            'instrument': 'NIFTY',
            'strategy': 'Short Strangle',
            'call_strike': strikes['call_strike'],
            'put_strike': strikes['put_strike'],
            'quantity': quantity,
            'lot_size': lot_size,
            'entry_price': None,  # Will be fetched from market at execution
            'premium_collected': str(premium_collected),
            'margin_required': str(margin_used),
            'stop_loss': str(stop_loss),
            'target': str(target),
            'expiry_date': str(entry_params['expiry']),
            # Risk metrics
            'max_profit': str(risk_scenarios['max_profit']),
            'max_profit_pct': str((risk_scenarios['max_profit'] / margin_used * 100) if margin_used > 0 else 0),
            'profitable_range': {
                'lower': str(risk_scenarios['profit_zone']['lower']),
                'upper': str(risk_scenarios['profit_zone']['upper']),
            },
            'support_level': str(support_resistance['support']),
            'support_distance': str(support_resistance['support_distance']),
            'support_distance_pct': str(support_resistance['support_distance_pct']),
            'resistance_level': str(support_resistance['resistance']),
            'resistance_distance': str(support_resistance['resistance_distance']),
            'resistance_distance_pct': str(support_resistance['resistance_distance_pct']),
        }

    def build_algorithm_reasoning(self, entry_params: Dict, filters_result: Dict, sizing: Dict) -> Dict:
        """Build algorithm reasoning for trade suggestion."""
        strikes = entry_params['strikes']
        quantity = sizing['quantity']
        lot_size = sizing['lot_size']
        premium_collected = entry_params['total_premium'] * quantity

        # Calculate risk/reward scenarios for reasoning
        risk_scenarios = OptionsRiskCalculator.calculate_scenarios(
            current_price=entry_params['spot_price'],
            call_strike=strikes['call_strike'],
            put_strike=strikes['put_strike'],
            call_premium=entry_params['call_premium'],
            put_premium=entry_params['put_premium'],
            quantity=quantity,
            lot_size=lot_size
        )

        # Support and Resistance for reasoning
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=entry_params['spot_price'],
            support_level=entry_params['spot_price'] * Decimal('0.99'),
            resistance_level=entry_params['spot_price'] * Decimal('1.01')
        )

        # Build enhanced analysis section if available
        enhanced_analysis_section = None
        if hasattr(self, '_enhanced_analysis_result') and self._enhanced_analysis_result:
            ea = self._enhanced_analysis_result
            enhanced_analysis_section = {
                'composite_score': ea.get('composite_score'),
                'recommendation': ea.get('recommendation'),
                'entry_bias': ea.get('entry_bias'),
                'component_scores': ea.get('scores', {}),
                'delta_adjustments': ea.get('delta_adjustments'),
                'details': ea.get('details', {}),  # Include filter details
                'hard_reject': ea.get('hard_reject', False),
                'reject_reason': ea.get('reject_reason'),
                'score_breakdown': self._format_score_breakdown(ea.get('scores', {})),
            }

        # Get adjustment log from entry_params
        adjustment_log = entry_params.get('adjustment_log', {})

        reasoning = {
            'title': 'Kotak Strangle Strategy (Enhanced Analysis)',
            'summary': 'Short Strangle position with multi-factor scoring',
            'calculations': {
                'spot_price': str(entry_params['spot_price']),
                'vix': str(entry_params['vix']),
                'days_to_expiry': entry_params['days_to_expiry'],
                'strike_distance': str(strikes['strike_distance']),
                'adjusted_delta': str(strikes['adjusted_delta']),
                'adjustment_reason': strikes['adjustment_reason'],
                'call_premium': str(entry_params['call_premium']),
                'put_premium': str(entry_params['put_premium']),
                'total_premium': str(entry_params['total_premium']),
                'premium_collected': str(premium_collected),
            },
            'filters': {
                'filters_passed': filters_result.get('filters_passed', []),
                'filters_failed': filters_result.get('filters_failed', []),
                'entry_time_valid': True,
            },
            'position_sizing': {
                'usable_margin': str(sizing['usable_margin']),
                'lot_size': lot_size,
                'lots': sizing['lots'],
                'quantity': quantity,
                'margin_used': str(sizing['margin_used']),
            },
            'final_decision': {
                'recommendation': 'SELL_STRANGLE',
                'position_details': {
                    'instrument': 'NIFTY',
                    'strategy': 'Short Strangle',
                    'call_strike': strikes['call_strike'],
                    'put_strike': strikes['put_strike'],
                    'total_quantity': quantity,
                    'quantity_per_lot': lot_size,
                    'premium_collected': str(premium_collected),
                    'margin_used': str(sizing['margin_used']),
                    'expiry_date': str(entry_params['expiry']),
                },
                'risk_reward': {
                    'max_profit': str(risk_scenarios['max_profit']),
                    'profitable_range': risk_scenarios['profit_zone'],
                    'breakeven_call': str(risk_scenarios['call_breakeven']),
                    'breakeven_put': str(risk_scenarios['put_breakeven']),
                    'scenarios_count': len(risk_scenarios['scenarios']),
                },
                'support_resistance': {
                    'support_level': str(support_resistance['support']),
                    'resistance_level': str(support_resistance['resistance']),
                    'next_support': str(support_resistance['next_support']),
                    'next_resistance': str(support_resistance['next_resistance']),
                }
            }
        }

        # Add enhanced analysis if available
        if enhanced_analysis_section:
            reasoning['enhanced_analysis'] = enhanced_analysis_section

        # Add adjustment log for audit trail
        if adjustment_log:
            reasoning['adjustment_log'] = adjustment_log

        return reasoning

    def _format_score_breakdown(self, scores: Dict) -> str:
        """Format score breakdown as readable string."""
        from apps.strategies.analyzers.enhanced_strangle_analyzer import EnhancedStrangleAnalyzer

        weights = EnhancedStrangleAnalyzer.WEIGHTS
        lines = []

        for component, score in scores.items():
            max_score = weights.get(component, 0)
            pct = int((score / max_score) * 100) if max_score > 0 else 0
            lines.append(f"{component}: {score}/{max_score} ({pct}%)")

        return " | ".join(lines)


# ============================================================================
# BACKWARD COMPATIBILITY FUNCTIONS
# ============================================================================

def execute_kotak_strangle_entry(account) -> Dict:
    """
    Complete entry workflow for Kotak Strangle Strategy.

    This is the backward-compatible wrapper function that maintains the
    original function signature for existing code that imports and calls it.

    Workflow:
        1. Morning position check (ONE POSITION RULE)
        2. Entry timing validation (9:00 AM - 11:30 AM)
        3. Run entry filters (ALL must pass)
        4. Expiry selection (1-day rule)
        5. Calculate strikes (VIX-based delta adjustment)
        6. Validate premiums (min/max checks)
        7. Calculate position size (50% margin rule)
        8. Risk limit checks
        9. Create trade suggestion

    Args:
        account: BrokerAccount instance (Kotak)

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'suggestion': TradeSuggestion or None,
            'details': dict
        }
    """
    strategy = KotakStrangleStrategy(account)
    result = strategy.execute_entry()
    return result.to_dict()


# Keep original helper functions for backward compatibility
# These are deprecated - use shared utilities instead

def calculate_strikes(spot_price: Decimal, days_to_expiry: int, vix: Decimal) -> Dict:
    """
    Calculate OTM call and put strikes for short strangle.

    DEPRECATED: Use apps.strategies.shared.strike_calculator.calculate_strangle_strikes instead.
    """
    return calculate_strangle_strikes(spot_price, days_to_expiry, vix)


def run_entry_filters() -> Tuple[bool, list, list]:
    """
    Execute ALL entry filters for strangle strategy.

    DEPRECATED: Use apps.strategies.shared.entry_filters.run_filters instead.
    """
    from apps.strategies.shared.entry_filters import get_default_filters, run_filters

    filters = get_default_filters()
    all_passed, details = run_filters(filters, logger)

    return all_passed, details.get('filters_passed', []), details.get('filters_failed', [])


def get_current_nifty_price() -> Decimal:
    """
    Get current Nifty spot price.

    DEPRECATED: Use apps.strategies.shared.market_data.get_nifty_price instead.
    """
    return get_nifty_price()


def get_option_premiums_wrapper(call_strike: int, put_strike: int, expiry_date) -> Tuple[Decimal, Decimal]:
    """
    Get option premiums for given strikes.

    DEPRECATED: Use apps.strategies.shared.market_data.get_option_premiums instead.
    """
    return get_option_premiums(call_strike, put_strike, expiry_date)
