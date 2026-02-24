"""
ICICI Futures Strategy (Enhanced)

Strategy: Directional futures trading based on ENHANCED multi-factor quantitative screening.
         Now incorporates 11 scoring components across technical, fundamental, and sentiment dimensions.

Account: ICICI Securities (Rs.1.2 Crores)
Target: Rs.6 Lakhs monthly (~5% on margin, 0.5% on exposure)
Risk Profile: Defined stop-loss, averaging allowed (max 2 attempts)

Key Rules:
- ONE POSITION PER ACCOUNT (enforced via morning_check)
- 50% margin usage for first trade
- 15-day minimum to expiry (skip if < 15 days)
- LLM validation required (70% minimum confidence)
- Sector alignment CRITICAL (ALL timeframes must align)
- Averaging allowed: Max 2 attempts, 1% loss trigger

ENHANCED Screening Process (300 pts scaled to 100) - Phase 2:
1. Hard Reject Filters (must pass ALL):
   - MWPL < 80% (not near ban)
   - Volatility < 60%
   - Piotroski >= 4 (financial health)
   - Promoter pledge < 30%
   - FII change > -2% (no exodus)
   - No blocking news
   - Analyst upside >= 8% (for LONG)

2. Multi-Factor Scoring (12 components):
   - OI & F&O Analysis (45 pts): Buildup + PCR + MWPL + Rollover
   - Technical Momentum (35 pts): RSI + MACD + MFI + ADX + ROC
   - Trend Confirmation (30 pts): DMA + Price Range + Breakouts + 52W Breakout
   - Volume Quality (25 pts): Surge + Delivery + VWAP + Delivery Trend
   - Institutional Flow (25 pts): FII + MF + Promoter changes
   - Fundamental Quality (20 pts): Piotroski + Profit Growth + ROE
   - Risk Adjustment (30 pts): Beta + Volatility + Valuation
   - News Sentiment (25 pts): Stock + Market + Sector news
   - Analyst Consensus (20 pts): Upside + Recommendations + Coverage
   - Research Reports (15 pts): LLM sentiment + Risk/Catalysts
   - Investor Calls (10 pts): Management tone + Trading signal
   - Momentum Acceleration (20 pts): Day-over-day + Week-over-week momentum trends

3. Sector Analysis -> ALL timeframes (3D, 7D, 21D) must align
4. LLM Validation -> Final gate (70% confidence minimum)
"""

import logging
from decimal import Decimal
from datetime import time
from typing import Dict, List, Tuple, Optional


from apps.strategies.core.base_strategy import BaseStrategy
from apps.strategies.core.result_types import StrategyConfig
from apps.strategies.shared.entry_filters import get_default_filters
from apps.strategies.filters.sector_filter import analyze_sector
from apps.data.analyzers import (
    OpenInterestAnalyzer,
    TrendlyneScoreAnalyzer,
    VolumeAnalyzer,
    DMAAnalyzer
)
from apps.llm.services.trade_validator import validate_trade
from apps.data.models import ContractStockData
from apps.trading.risk_calculator import FuturesRiskCalculator, SupportResistanceCalculator
from apps.strategies.analyzers.enhanced_futures_analyzer import (
    EnhancedFuturesAnalyzer,
    HardRejectError,
    analyze_stock_for_futures as enhanced_analyze_stock
)

logger = logging.getLogger(__name__)


class ICICIFuturesStrategy(BaseStrategy):
    """
    Directional futures strategy with multi-factor screening.

    Unique Logic:
    - Multi-factor stock screening (OI + sector + technical)
    - LLM validation gate (70% confidence)
    - Averaging allowed (max 2 attempts)
    """

    def __init__(self, account, screened_candidate: Dict = None):
        """
        Initialize strategy with account and optional screened candidate.

        Args:
            account: BrokerAccount instance
            screened_candidate: Pre-screened candidate dict from screening process
        """
        self.candidate = screened_candidate or {}
        self.symbol = self.candidate.get('symbol', 'NIFTY')
        self.llm_result = None  # Will be populated during filter execution
        super().__init__(account)

    def get_config(self) -> StrategyConfig:
        """Return strategy configuration."""
        direction = self.candidate.get('direction', 'LONG')

        return StrategyConfig(
            name="ICICI Futures Strategy",
            strategy_type='FUTURES',
            direction=direction,
            entry_start_time=time(9, 15),
            entry_end_time=time(15, 0),
            min_days_to_expiry=15,
            margin_usage_pct=Decimal('0.50'),
            extra={
                'llm_confidence_threshold': Decimal('0.70'),
                'min_composite_score': 65,
            }
        )

    def get_entry_filters(self) -> List:
        """Return filters including LLM validation."""
        base_filters = get_default_filters()
        return base_filters + [self._llm_validation_filter]

    def _llm_validation_filter(self) -> Dict:
        """LLM validation as a filter step."""
        if not self.candidate:
            return {'passed': False, 'message': 'No candidate to validate'}

        try:
            self.llm_result = validate_trade(
                symbol=self.candidate.get('symbol', 'UNKNOWN'),
                direction=self.candidate.get('direction', 'LONG'),
                strategy_type='FUTURES'
            )

            confidence = self.llm_result.get('confidence', 0)
            passed = self.llm_result.get('approved', False) and confidence >= 0.70

            return {
                'passed': passed,
                'message': f"LLM confidence: {confidence*100:.1f}%",
                'details': self.llm_result
            }
        except Exception as e:
            logger.error(f"LLM validation error: {e}", exc_info=True)
            return {
                'passed': False,
                'message': f"LLM validation error: {str(e)}"
            }

    def calculate_entry_parameters(self, market_data: Dict) -> Dict:
        """
        Calculate entry parameters for futures trade.

        Uses enhanced entry params from EnhancedFuturesAnalyzer when available,
        which includes:
        - ATR-based stop-loss and targets
        - Support/resistance validated levels
        - Beta-based position sizing adjustments
        """
        if not self.candidate:
            raise ValueError("No screened candidate provided")

        direction = self.candidate.get('direction', 'LONG')

        # Check if enhanced entry_params are available from screening
        enhanced_params = self.candidate.get('entry_params', {})

        if enhanced_params and enhanced_params.get('entry_price'):
            # Use enhanced ATR-based parameters
            current_price = Decimal(str(enhanced_params.get('entry_price', 1000)))
            stop_loss = Decimal(str(enhanced_params.get('stop_loss', current_price * Decimal('0.98'))))
            target = Decimal(str(enhanced_params.get('target_1', current_price * Decimal('1.02'))))
            target_2 = Decimal(str(enhanced_params.get('target_2', current_price * Decimal('1.03'))))

            # Calculate percentages
            if direction == 'LONG':
                stop_loss_pct = (current_price - stop_loss) / current_price
                target_pct = (target - current_price) / current_price
            else:
                stop_loss_pct = (stop_loss - current_price) / current_price
                target_pct = (current_price - target) / current_price

            # Position sizing from enhanced analyzer
            position_sizing = enhanced_params.get('position_sizing', {})

            logger.info(
                f"Using enhanced entry params: ATR={enhanced_params.get('atr')}, "
                f"SL={stop_loss}, Target={target}, "
                f"Position Multiplier={position_sizing.get('final_multiplier', 1.0)}"
            )
        else:
            # Fallback to fixed percentages
            current_price = Decimal('1000')  # Placeholder
            stop_loss_pct = Decimal('0.005')  # 0.5% default SL
            target_pct = Decimal('0.01')      # 1.0% default target

            if direction == 'LONG':
                stop_loss = current_price * (Decimal('1') - stop_loss_pct)
                target = current_price * (Decimal('1') + target_pct)
            else:
                stop_loss = current_price * (Decimal('1') + stop_loss_pct)
                target = current_price * (Decimal('1') - target_pct)

            target_2 = None
            position_sizing = {}

            logger.info("Using fallback fixed percentage entry params")

        return {
            'symbol': self.candidate.get('symbol'),
            'direction': direction,
            'current_price': current_price,
            'stop_loss': stop_loss,
            'target': target,
            'target_2': target_2,
            'stop_loss_pct': stop_loss_pct,
            'target_pct': target_pct,
            'atr': enhanced_params.get('atr'),
            'risk': enhanced_params.get('risk'),
            'reward': enhanced_params.get('reward'),
            'risk_reward_ratio': enhanced_params.get('risk_reward_ratio'),
            'support_s1': enhanced_params.get('support_s1'),
            'resistance_r1': enhanced_params.get('resistance_r1'),
            'position_sizing': position_sizing,
            'composite_score': self.candidate.get('composite_score', 0),
            'scores': self.candidate.get('scores', {}),
            'details': self.candidate.get('details', {}),
            'oi_analysis': self.candidate.get('oi_analysis', {}),
            'sector_analysis': self.candidate.get('sector_analysis', {}),
            'technical_analysis': self.candidate.get('technical_analysis', {}),
            'expiry': market_data.get('expiry'),
            'days_to_expiry': market_data.get('days_to_expiry'),
            'llm_result': self.llm_result or {}
        }

    def build_position_details(self, entry_params: Dict, sizing: Dict) -> Dict:
        """Build position details for trade suggestion."""
        quantity = sizing['quantity']
        margin_used = sizing['margin_used']

        # Calculate risk/reward scenarios
        risk_scenarios = FuturesRiskCalculator.calculate_scenarios(
            current_price=entry_params['current_price'],
            direction=entry_params['direction'],
            quantity=quantity,
            stop_loss=entry_params['stop_loss'],
            target=entry_params['target']
        )

        # Support and Resistance
        volatility_range = entry_params['current_price'] * Decimal('0.02')
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=entry_params['current_price'],
            support_level=entry_params['current_price'] - volatility_range,
            resistance_level=entry_params['current_price'] + volatility_range
        )

        return {
            'instrument': entry_params['symbol'],
            'strategy': 'Directional Futures',
            'symbol': entry_params['symbol'],
            'direction': entry_params['direction'],
            'entry_price': str(entry_params['current_price']),
            'quantity': quantity,
            'lot_size': sizing['lot_size'],
            'stop_loss': str(entry_params['stop_loss']),
            'target': str(entry_params['target']),
            'margin_required': str(margin_used),
            'max_loss': str(risk_scenarios['max_loss']),
            'max_profit': str(risk_scenarios['max_profit']),
            'risk_reward_ratio': str(risk_scenarios['risk_reward_ratio']),
            'expected_profit': str(risk_scenarios['max_profit']),
            'expiry_date': str(entry_params['expiry']),
            'support_level': str(support_resistance['support']),
            'support_distance': str(support_resistance['support_distance']),
            'support_distance_pct': str(support_resistance['support_distance_pct']),
            'resistance_level': str(support_resistance['resistance']),
            'resistance_distance': str(support_resistance['resistance_distance']),
            'resistance_distance_pct': str(support_resistance['resistance_distance_pct']),
            'next_support': str(support_resistance['next_support']),
            'next_resistance': str(support_resistance['next_resistance']),
        }

    def build_algorithm_reasoning(self, entry_params: Dict, filters_result: Dict, sizing: Dict) -> Dict:
        """Build algorithm reasoning for trade suggestion."""
        quantity = sizing['quantity']

        # Calculate risk/reward scenarios
        risk_scenarios = FuturesRiskCalculator.calculate_scenarios(
            current_price=entry_params['current_price'],
            direction=entry_params['direction'],
            quantity=quantity,
            stop_loss=entry_params['stop_loss'],
            target=entry_params['target']
        )

        # Support and Resistance
        volatility_range = entry_params['current_price'] * Decimal('0.02')
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=entry_params['current_price'],
            support_level=entry_params['current_price'] - volatility_range,
            resistance_level=entry_params['current_price'] + volatility_range
        )

        llm_result = entry_params.get('llm_result', {})

        # Get enhanced 12-component scores if available
        scores = entry_params.get('scores', {})
        details = entry_params.get('details', {})
        enhanced_position_sizing = entry_params.get('position_sizing', {})

        return {
            'title': 'ICICI Futures Strategy (Phase 2 Enhanced)',
            'summary': '12-factor multi-dimensional scoring for directional trade',
            'scoring': {
                'composite_total': entry_params.get('composite_score', 0),
                'max_score': 100,
                'raw_score': sum(scores.values()) if scores else 0,
                'max_raw_score': 300,
                # 12-component breakdown
                'component_scores': {
                    'oi_fno': {'score': scores.get('oi_fno', 0), 'max': 45},
                    'technical_momentum': {'score': scores.get('technical_momentum', 0), 'max': 35},
                    'trend_confirmation': {'score': scores.get('trend_confirmation', 0), 'max': 30},
                    'volume_quality': {'score': scores.get('volume_quality', 0), 'max': 25},
                    'institutional_flow': {'score': scores.get('institutional_flow', 0), 'max': 25},
                    'fundamental_quality': {'score': scores.get('fundamental_quality', 0), 'max': 20},
                    'risk_adjustment': {'score': scores.get('risk_adjustment', 0), 'max': 30},
                    'news_sentiment': {'score': scores.get('news_sentiment', 0), 'max': 25},
                    'analyst_consensus': {'score': scores.get('analyst_consensus', 0), 'max': 20},
                    'research_reports': {'score': scores.get('research_reports', 0), 'max': 15},
                    'investor_calls': {'score': scores.get('investor_calls', 0), 'max': 10},
                    'momentum_acceleration': {'score': scores.get('momentum_acceleration', 0), 'max': 20},
                },
                # Legacy breakdown for backwards compatibility
                'composite_breakdown': {
                    'oi_analysis': entry_params.get('oi_analysis', {}),
                    'sector_analysis': entry_params.get('sector_analysis', {}),
                    'technical_analysis': entry_params.get('technical_analysis', {}),
                },
                # Phase 2 enhancements
                'phase2_details': {
                    '52w_status': details.get('trend_confirmation', {}).get('52w_status'),
                    'delivery_trend': details.get('volume_quality', {}).get('delivery_trend'),
                    'momentum_pattern': details.get('momentum_acceleration', {}).get('pattern'),
                }
            },
            'llm_validation': {
                'approved': llm_result.get('approved', False),
                'confidence': llm_result.get('confidence', 0),
                'reasoning': llm_result.get('reasoning', ''),
                'confidence_pct': f"{llm_result.get('confidence', 0)*100:.1f}%"
            },
            'filters': {
                'filters_passed': filters_result.get('filters_passed', []),
                'filters_failed': filters_result.get('filters_failed', []),
                'entry_time_valid': True,
                'hard_reject_checks': details.get('hard_reject_checks', {}),
            },
            'position_sizing': {
                'usable_margin': str(sizing['usable_margin']),
                'lot_size': sizing['lot_size'],
                'lots': sizing['lots'],
                'quantity': quantity,
                'margin_used': str(sizing['margin_used']),
                # Enhanced position sizing adjustments
                'beta_adjustment': enhanced_position_sizing.get('beta_adjustment', 1.0),
                'volatility_adjustment': enhanced_position_sizing.get('volatility_adjustment', 1.0),
                'score_adjustment': enhanced_position_sizing.get('score_adjustment', 1.0),
                'final_multiplier': enhanced_position_sizing.get('final_multiplier', 1.0),
                'adjustments_applied': enhanced_position_sizing.get('adjustments_applied', []),
            },
            'entry_analysis': {
                'atr': entry_params.get('atr'),
                'risk': entry_params.get('risk'),
                'reward': entry_params.get('reward'),
                'risk_reward_ratio': entry_params.get('risk_reward_ratio'),
                'support_s1': str(entry_params.get('support_s1')) if entry_params.get('support_s1') else None,
                'resistance_r1': str(entry_params.get('resistance_r1')) if entry_params.get('resistance_r1') else None,
            },
            'final_decision': {
                'recommendation': 'DIRECTIONAL_TRADE',
                'position_details': {
                    'symbol': entry_params['symbol'],
                    'direction': entry_params['direction'],
                    'entry_price': str(entry_params['current_price']),
                    'quantity': quantity,
                    'stop_loss': str(entry_params['stop_loss']),
                    'target': str(entry_params['target']),
                    'margin_required': str(sizing['margin_used']),
                    'max_loss': str(risk_scenarios['max_loss']),
                    'max_profit': str(risk_scenarios['max_profit']),
                    'risk_reward_ratio': str(risk_scenarios['risk_reward_ratio']),
                    'expiry_date': str(entry_params['expiry']),
                },
                'risk_reward': {
                    'max_profit': str(risk_scenarios['max_profit']),
                    'max_loss': str(risk_scenarios['max_loss']),
                    'risk_reward_ratio': str(risk_scenarios['risk_reward_ratio']),
                    'scenarios_count': len(risk_scenarios.get('scenarios', [])),
                },
                'support_resistance': {
                    'support_level': str(support_resistance['support']),
                    'resistance_level': str(support_resistance['resistance']),
                    'next_support': str(support_resistance['next_support']),
                    'next_resistance': str(support_resistance['next_resistance']),
                }
            }
        }


# ============================================================================
# SCREENING FUNCTIONS (UNIQUE TO THIS STRATEGY - KEPT AS STANDALONE)
# ============================================================================

def screen_futures_opportunities(
    min_volume_rank: int = 50,
    min_score: int = 65
) -> List[Dict]:
    """
    Screen for futures trading opportunities using multi-factor analysis.

    Screening Pipeline:
    1. Liquidity Filter (Top 50 by volume)
    2. OI Analysis (Long/Short buildup)
    3. Sector Analysis (ALL timeframes must align)
    4. Technical Analysis (Trendlyne scores, DMA, RSI)
    5. Composite Scoring (Min 65/100)

    Args:
        min_volume_rank: Minimum volume rank (default: 50 = top 50 stocks)
        min_score: Minimum composite score (default: 65)

    Returns:
        list: Sorted list of candidate dictionaries (highest score first)
    """
    logger.info("=" * 80)
    logger.info("FUTURES SCREENING - Multi-Factor Analysis")
    logger.info("=" * 80)
    logger.info(f"Filters: Top {min_volume_rank} stocks, Min Score: {min_score}/100")
    logger.info("")

    candidates = []

    # STEP 1: Liquidity Filter - Top 50 stocks by volume
    logger.info("STEP 1: Liquidity Filter")
    logger.info("-" * 80)

    stocks = ContractStockData.objects.filter(
        fno_total_oi__gt=0
    ).order_by('-fno_total_oi')[:min_volume_rank]

    logger.info(f"Found {stocks.count()} liquid F&O stocks")
    logger.info("")

    # STEP 2-5: Analyze each stock
    for stock in stocks:
        symbol = stock.nse_code

        try:
            logger.info(f"Analyzing: {symbol}")
            logger.info("-" * 40)

            # STEP 2: OI Analysis
            oi_score, oi_data = analyze_oi_for_stock(symbol)

            if oi_data['signal'] == 'NEUTRAL':
                logger.debug(f"  Skipped {symbol}: Neutral OI signal")
                continue

            # STEP 3: Sector Analysis (CRITICAL FILTER)
            sector_analysis = analyze_sector(symbol)

            direction = oi_data['signal']  # 'BULLISH' or 'BEARISH'

            # Check if sector allows the direction
            if direction == 'BULLISH' and not sector_analysis['allow_long']:
                logger.debug(f"  Skipped {symbol}: Sector doesn't support LONG")
                continue

            if direction == 'BEARISH' and not sector_analysis['allow_short']:
                logger.debug(f"  Skipped {symbol}: Sector doesn't support SHORT")
                continue

            # STEP 4: Technical Analysis
            technical_score, technical_data = analyze_technical_for_stock(symbol)

            # STEP 5: Composite Scoring
            composite_score = calculate_composite_score(
                oi_score=oi_score,
                sector_score=50 if sector_analysis['verdict'] in ['STRONG_BULLISH', 'STRONG_BEARISH'] else 0,
                technical_score=technical_score
            )

            if composite_score < min_score:
                logger.debug(f"  Skipped {symbol}: Score {composite_score}/100 below minimum")
                continue

            # Candidate passed all filters
            candidate = {
                'symbol': symbol,
                'direction': direction,
                'composite_score': composite_score,
                'oi_analysis': oi_data,
                'sector_analysis': sector_analysis,
                'technical_analysis': technical_data,
                'stock_data': stock
            }

            candidates.append(candidate)

            logger.info(f"  QUALIFIED: {symbol}")
            logger.info(f"     Direction: {direction}")
            logger.info(f"     Score: {composite_score}/100")
            logger.info(f"     OI: {oi_data['buildup_type']}")
            logger.info(f"     Sector: {sector_analysis['verdict']}")
            logger.info("")

        except Exception as e:
            logger.error(f"  Error analyzing {symbol}: {e}")
            continue

    # Sort by composite score (highest first)
    candidates.sort(key=lambda x: x['composite_score'], reverse=True)

    logger.info("=" * 80)
    logger.info(f"SCREENING COMPLETE: {len(candidates)} candidates qualified")
    logger.info("=" * 80)

    for i, candidate in enumerate(candidates[:5], 1):
        logger.info(
            f"{i}. {candidate['symbol']} - {candidate['direction']} - "
            f"Score: {candidate['composite_score']}/100"
        )

    logger.info("")

    return candidates


def screen_futures_opportunities_enhanced(
    min_volume_rank: int = 50,
    min_score: int = 65,
    directions: List[str] = None
) -> List[Dict]:
    """
    ENHANCED Screen for futures trading opportunities using 12-factor analysis (Phase 2).

    This is the new screening function that uses the EnhancedFuturesAnalyzer
    with comprehensive multi-factor scoring including:
    - Hard reject filters (MWPL, volatility, fundamentals, news, analysts)
    - 12 scoring components across technical, fundamental, and sentiment dimensions
    - 52W breakout detection, delivery trend analysis, momentum acceleration
    - Beta-based position sizing with risk adjustments

    Args:
        min_volume_rank: Minimum volume rank (default: 50 = top 50 stocks)
        min_score: Minimum composite score (default: 65)
        directions: List of directions to screen for (default: ['LONG', 'SHORT'])

    Returns:
        list: Sorted list of candidate dictionaries (highest score first)
    """
    if directions is None:
        directions = ['LONG', 'SHORT']

    logger.info("=" * 80)
    logger.info("ENHANCED FUTURES SCREENING - 12-Factor Multi-Dimensional Analysis (Phase 2)")
    logger.info("=" * 80)
    logger.info(f"Filters: Top {min_volume_rank} stocks, Min Score: {min_score}/100")
    logger.info(f"Directions: {directions}")
    logger.info("")

    candidates = []
    rejected = []

    # STEP 1: Liquidity Filter - Top stocks by OI
    logger.info("STEP 1: Liquidity Filter")
    logger.info("-" * 80)

    stocks = ContractStockData.objects.filter(
        fno_total_oi__gt=0
    ).order_by('-fno_total_oi')[:min_volume_rank]

    logger.info(f"Found {stocks.count()} liquid F&O stocks")
    logger.info("")

    # STEP 2: Analyze each stock with Enhanced Analyzer
    logger.info("STEP 2: Enhanced Multi-Factor Analysis")
    logger.info("-" * 80)

    for stock in stocks:
        symbol = stock.nse_code

        for direction in directions:
            try:
                logger.info(f"Analyzing: {symbol} ({direction})")

                # Use Enhanced Analyzer
                analyzer = EnhancedFuturesAnalyzer(symbol, direction)
                result = analyzer.analyze()

                if result['hard_reject']:
                    logger.info(f"  REJECTED: {result['reject_reason'][:60]}")
                    rejected.append({
                        'symbol': symbol,
                        'direction': direction,
                        'reason': result['reject_reason']
                    })
                    continue

                if result['composite_score'] < min_score:
                    logger.debug(f"  Score {result['composite_score']}/100 below minimum {min_score}")
                    continue

                # STEP 3: Sector Analysis (Critical Filter)
                sector_analysis = analyze_sector(symbol)

                # Check if sector allows the direction
                if direction == 'LONG' and not sector_analysis['allow_long']:
                    logger.debug(f"  Skipped: Sector doesn't support LONG")
                    continue

                if direction == 'SHORT' and not sector_analysis['allow_short']:
                    logger.debug(f"  Skipped: Sector doesn't support SHORT")
                    continue

                # Candidate passed all filters!
                candidate = {
                    'symbol': symbol,
                    'direction': direction,
                    'composite_score': result['composite_score'],
                    'raw_score': result.get('raw_score', 0),
                    'max_score': result.get('max_score', 300),
                    'recommendation': result['recommendation'],
                    'scores': result['scores'],
                    'details': result['details'],
                    'entry_params': result['entry_params'],
                    'sector_analysis': sector_analysis,
                    'stock_data': stock
                }

                candidates.append(candidate)

                logger.info(f"  QUALIFIED: {symbol} ({direction})")
                logger.info(f"     Score: {result['composite_score']}/100 ({result['recommendation']})")
                logger.info(f"     Top Scores: OI={result['scores'].get('oi_fno', 0)}/45, "
                          f"Tech={result['scores'].get('technical_momentum', 0)}/35, "
                          f"News={result['scores'].get('news_sentiment', 0)}/25")
                logger.info(f"     Sector: {sector_analysis['verdict']}")
                logger.info("")

            except HardRejectError as e:
                logger.info(f"  HARD REJECT: {str(e)[:60]}")
                rejected.append({
                    'symbol': symbol,
                    'direction': direction,
                    'reason': str(e)
                })
            except Exception as e:
                logger.error(f"  Error analyzing {symbol}: {e}")
                continue

    # Sort by composite score (highest first)
    candidates.sort(key=lambda x: x['composite_score'], reverse=True)

    logger.info("=" * 80)
    logger.info(f"ENHANCED SCREENING COMPLETE")
    logger.info(f"  Qualified: {len(candidates)} candidates")
    logger.info(f"  Rejected: {len(rejected)} stocks (hard reject filters)")
    logger.info("=" * 80)

    # Log top 5 candidates
    for i, candidate in enumerate(candidates[:5], 1):
        logger.info(
            f"{i}. {candidate['symbol']} - {candidate['direction']} - "
            f"Score: {candidate['composite_score']}/100 ({candidate['recommendation']})"
        )

    logger.info("")

    return candidates


def analyze_stock_for_futures_enhanced(stock_symbol: str, direction: str = None) -> Dict:
    """
    ENHANCED Analyze a specific stock for futures trading (Phase 2).

    Uses the new EnhancedFuturesAnalyzer with 12-factor scoring including:
    - 52W breakout detection
    - Delivery trend analysis (accumulation/distribution)
    - Momentum acceleration scoring
    - Beta-based position sizing with risk adjustments

    If direction is not specified, analyzes both LONG and SHORT and returns the better one.

    Args:
        stock_symbol: Stock symbol to analyze
        direction: Optional direction ('LONG' or 'SHORT'). If None, analyzes both.

    Returns:
        dict: Comprehensive analysis results with position sizing recommendations
    """
    if direction:
        # Analyze specific direction
        result = enhanced_analyze_stock(stock_symbol, direction)

        # Add sector analysis
        sector_analysis = analyze_sector(stock_symbol)
        result['sector_analysis'] = sector_analysis

        # Check sector alignment
        if direction == 'LONG' and not sector_analysis['allow_long']:
            result['sector_warning'] = 'Sector does not support LONG positions'
        elif direction == 'SHORT' and not sector_analysis['allow_short']:
            result['sector_warning'] = 'Sector does not support SHORT positions'

        return result
    else:
        # Analyze both directions and return the better one
        long_result = enhanced_analyze_stock(stock_symbol, 'LONG')
        short_result = enhanced_analyze_stock(stock_symbol, 'SHORT')

        # Add sector analysis
        sector_analysis = analyze_sector(stock_symbol)

        # Determine which direction is better
        long_score = long_result['composite_score'] if not long_result['hard_reject'] else 0
        short_score = short_result['composite_score'] if not short_result['hard_reject'] else 0

        # Apply sector filter
        if not sector_analysis['allow_long']:
            long_score = 0
        if not sector_analysis['allow_short']:
            short_score = 0

        if long_score >= short_score and long_score > 0:
            best_result = long_result
            best_direction = 'LONG'
        elif short_score > 0:
            best_result = short_result
            best_direction = 'SHORT'
        else:
            # Neither direction is viable
            return {
                'symbol': stock_symbol,
                'direction': 'NEUTRAL',
                'hard_reject': True,
                'reject_reason': 'Neither LONG nor SHORT viable after sector filter',
                'composite_score': 0,
                'long_analysis': long_result,
                'short_analysis': short_result,
                'sector_analysis': sector_analysis
            }

        best_result['sector_analysis'] = sector_analysis
        best_result['alternative_direction'] = {
            'direction': 'SHORT' if best_direction == 'LONG' else 'LONG',
            'score': short_score if best_direction == 'LONG' else long_score,
            'viable': (short_score if best_direction == 'LONG' else long_score) >= 65
        }

        return best_result


# ============================================================================
# LEGACY SCREENING FUNCTIONS (KEPT FOR BACKWARD COMPATIBILITY)
# ============================================================================

def analyze_oi_for_stock(symbol: str) -> Tuple[int, Dict]:
    """
    Analyze Open Interest for a stock.

    Returns:
        tuple: (oi_score: int (0-40), oi_data: dict)
    """
    oi_analyzer = OpenInterestAnalyzer()

    # Get current expiry (placeholder)
    expiry = '2024-11-28'

    # Analyze OI buildup
    oi_buildup = oi_analyzer.analyze_oi_buildup(symbol, expiry)

    if 'error' in oi_buildup:
        return 0, {'signal': 'NEUTRAL', 'buildup_type': 'UNKNOWN'}

    # Get PCR ratio
    pcr_data = oi_analyzer.get_pcr_ratio(symbol)

    # Determine signal from buildup + PCR
    buildup_type = oi_buildup['buildup_type']
    buildup_sentiment = oi_buildup['sentiment']

    # PCR interpretation
    if pcr_data:
        pcr_signal = pcr_data['interpretation']
    else:
        pcr_signal = 'NEUTRAL'

    # Combined signal (buildup takes priority)
    if buildup_sentiment in ['BULLISH', 'BEARISH']:
        signal = buildup_sentiment
    else:
        signal = pcr_signal if pcr_signal != 'NEUTRAL' else 'NEUTRAL'

    # Calculate score (0-40)
    score = 0

    # OI buildup strength (0-25)
    oi_change = abs(oi_buildup.get('oi_change_pct', 0))
    if oi_change > 10:
        score += 25
    elif oi_change > 5:
        score += 15
    elif oi_change > 0:
        score += 5

    # PCR alignment (0-15)
    if pcr_signal == buildup_sentiment:
        score += 15  # Both agree
    elif pcr_signal != 'NEUTRAL':
        score += 5   # PCR has opinion but doesn't agree

    return score, {
        'signal': signal,
        'buildup_type': buildup_type,
        'buildup_sentiment': buildup_sentiment,
        'price_change_pct': oi_buildup.get('price_change_pct', 0),
        'oi_change_pct': oi_buildup.get('oi_change_pct', 0),
        'pcr': pcr_data.get('pcr_oi', 0) if pcr_data else 0,
        'pcr_signal': pcr_signal
    }


def analyze_technical_for_stock(symbol: str) -> Tuple[int, Dict]:
    """
    Analyze technical indicators for a stock.

    Returns:
        tuple: (technical_score: int (0-35), technical_data: dict)
    """
    score = 0
    technical_data = {}

    # Trendlyne Scores (0-15)
    try:
        trendlyne_analyzer = TrendlyneScoreAnalyzer()
        tl_scores = trendlyne_analyzer.get_stock_scores(symbol)

        if tl_scores:
            overall_rating = tl_scores.get('overall_rating', 'HOLD')

            if overall_rating == 'STRONG_BUY':
                score += 15
            elif overall_rating == 'BUY':
                score += 10
            elif overall_rating == 'HOLD':
                score += 5

            technical_data['trendlyne_rating'] = overall_rating
            technical_data['trendlyne_scores'] = tl_scores
    except:
        pass

    # DMA Analysis (0-10)
    try:
        dma_analyzer = DMAAnalyzer()
        dma_analysis = dma_analyzer.get_dma_signals(symbol)

        if dma_analysis:
            if dma_analysis.get('golden_cross', False):
                score += 10
            elif dma_analysis.get('above_all_dmas', False):
                score += 5

            technical_data['dma_analysis'] = dma_analysis
    except:
        pass

    # Volume Analysis (0-10)
    try:
        volume_analyzer = VolumeAnalyzer()
        volume_analysis = volume_analyzer.detect_breakouts(symbol)

        if volume_analysis:
            if volume_analysis.get('volume_breakout', False):
                score += 10
            elif volume_analysis.get('delivery_pct', 0) > 60:
                score += 5

            technical_data['volume_analysis'] = volume_analysis
    except:
        pass

    return score, technical_data


def calculate_composite_score(
    oi_score: int,
    sector_score: int,
    technical_score: int
) -> int:
    """
    Calculate composite score from individual components.

    Weighting:
    - OI Analysis: 40% (0-40 points)
    - Sector Analysis: 25% (0-25 points) - Binary: 0 if mixed, 25 if aligned
    - Technical Analysis: 35% (0-35 points)

    Total: 100 points

    Args:
        oi_score: OI analysis score (0-40)
        sector_score: Sector analysis score (0 or 50, will be normalized to 0 or 25)
        technical_score: Technical analysis score (0-35)

    Returns:
        int: Composite score (0-100)
    """
    # Normalize sector score (convert 50 -> 25, 0 -> 0)
    normalized_sector_score = min(sector_score, 25)

    composite = oi_score + normalized_sector_score + technical_score

    return int(composite)


def analyze_stock_for_futures(stock_symbol: str, use_enhanced: bool = True) -> Optional[Dict]:
    """
    Analyze a specific stock for futures trading.

    Used for manual verification of trade ideas.

    Args:
        stock_symbol: Stock symbol to analyze
        use_enhanced: If True, uses the new 11-factor EnhancedFuturesAnalyzer.
                     If False, uses the legacy analyzer for backward compatibility.

    Returns:
        dict: Analysis results with all metrics, or None if unable to analyze
    """
    # Use enhanced analyzer by default
    if use_enhanced:
        try:
            return analyze_stock_for_futures_enhanced(stock_symbol)
        except Exception as e:
            logger.warning(f"Enhanced analyzer failed, falling back to legacy: {e}")
            # Fall through to legacy analyzer

    # Legacy analyzer (backward compatibility)
    try:
        logger.info(f"Analyzing {stock_symbol} for futures trading (legacy)")

        # Get stock data
        stock = ContractStockData.objects.filter(nse_code=stock_symbol).first()
        if not stock:
            stock = ContractStockData.objects.filter(stock_name__icontains=stock_symbol).first()

        if not stock:
            logger.warning(f"{stock_symbol} not found in database")
            return None

        # Run OI analysis
        oi_score, oi_details = analyze_oi_for_stock(stock_symbol)

        # Sector analysis
        sector_analysis = analyze_sector(stock_symbol)
        sector_score = 50 if sector_analysis['verdict'] in ['STRONG_BULLISH', 'STRONG_BEARISH'] else 0

        # Technical analysis
        tech_score, tech_details = analyze_technical_for_stock(stock_symbol)

        # Composite score
        composite_score = calculate_composite_score(oi_score, sector_score, tech_score)

        # Determine direction
        signal = oi_details.get('signal', 'NEUTRAL')
        direction = 'LONG' if signal == 'BULLISH' else 'SHORT' if signal == 'BEARISH' else 'NEUTRAL'

        # Calculate entry, SL, target
        current_price = float(stock.current_price or 0)

        if direction == 'LONG':
            entry_price = current_price
            stop_loss = current_price * 0.98  # 2% below
            target = current_price * 1.04     # 4% above
        elif direction == 'SHORT':
            entry_price = current_price
            stop_loss = current_price * 1.02  # 2% above
            target = current_price * 0.96     # 4% below
        else:
            entry_price = current_price
            stop_loss = current_price * 0.95
            target = current_price * 1.05

        return {
            'symbol': stock_symbol,
            'direction': direction,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'target': target,
            'composite_score': composite_score,
            'oi_score': oi_score,
            'sector_score': sector_score,
            'tech_score': tech_score,
            'oi_analysis': oi_details.get('buildup_type', 'Unknown'),
            'sector_analysis': sector_analysis.get('verdict', 'Unknown'),
            'technical_setup': tech_details.get('trendlyne_rating', 'Unknown'),
            'reasoning': f"{direction} setup with {composite_score}/100 score"
        }

    except Exception as e:
        logger.error(f"Error analyzing {stock_symbol}: {e}", exc_info=True)
        return None


# ============================================================================
# COMPARISON & UTILITY FUNCTIONS
# ============================================================================

def compare_screening_methods(symbol: str) -> Dict:
    """
    Compare legacy vs enhanced screening for a specific stock.

    Useful for validating the new enhanced analyzer against the legacy system.

    Args:
        symbol: Stock symbol to compare

    Returns:
        dict: Comparison results with both analyses
    """
    logger.info(f"Comparing screening methods for {symbol}")
    logger.info("=" * 80)

    # Legacy analysis
    legacy_result = analyze_stock_for_futures(symbol, use_enhanced=False)

    # Enhanced analysis
    enhanced_result = analyze_stock_for_futures_enhanced(symbol)

    comparison = {
        'symbol': symbol,
        'legacy': {
            'direction': legacy_result.get('direction') if legacy_result else 'N/A',
            'composite_score': legacy_result.get('composite_score', 0) if legacy_result else 0,
            'reasoning': legacy_result.get('reasoning', '') if legacy_result else 'Failed'
        },
        'enhanced': {
            'direction': enhanced_result.get('direction', 'N/A'),
            'composite_score': enhanced_result.get('composite_score', 0),
            'recommendation': enhanced_result.get('recommendation', 'N/A'),
            'hard_reject': enhanced_result.get('hard_reject', False),
            'reject_reason': enhanced_result.get('reject_reason', None),
            'scores': enhanced_result.get('scores', {}),
        },
        'improvement': {
            'new_components': [
                'news_sentiment',
                'analyst_consensus',
                'research_reports',
                'investor_calls',
                'institutional_flow',
                'fundamental_quality',
                'risk_adjustment'
            ],
            'hard_reject_filters': [
                'MWPL < 80%',
                'Volatility < 60%',
                'Piotroski >= 4',
                'Promoter pledge < 30%',
                'FII change > -2%',
                'No blocking news',
                'Analyst upside >= 8%'
            ]
        }
    }

    logger.info("COMPARISON RESULTS:")
    logger.info(f"  Legacy Score: {comparison['legacy']['composite_score']}/100")
    logger.info(f"  Enhanced Score: {comparison['enhanced']['composite_score']}/100")
    logger.info(f"  Enhanced Direction: {comparison['enhanced']['direction']}")
    logger.info(f"  Hard Reject: {comparison['enhanced']['hard_reject']}")
    logger.info("=" * 80)

    return comparison


def get_screening_summary(candidates: List[Dict]) -> Dict:
    """
    Generate a summary of screening results.

    Args:
        candidates: List of candidate dicts from screen_futures_opportunities_enhanced

    Returns:
        dict: Summary statistics
    """
    if not candidates:
        return {
            'total_candidates': 0,
            'by_direction': {'LONG': 0, 'SHORT': 0},
            'by_recommendation': {},
            'avg_score': 0,
            'top_candidates': []
        }

    long_count = sum(1 for c in candidates if c['direction'] == 'LONG')
    short_count = sum(1 for c in candidates if c['direction'] == 'SHORT')

    rec_counts = {}
    for c in candidates:
        rec = c.get('recommendation', 'UNKNOWN')
        rec_counts[rec] = rec_counts.get(rec, 0) + 1

    avg_score = sum(c['composite_score'] for c in candidates) / len(candidates)

    return {
        'total_candidates': len(candidates),
        'by_direction': {'LONG': long_count, 'SHORT': short_count},
        'by_recommendation': rec_counts,
        'avg_score': round(avg_score, 1),
        'top_candidates': [
            {
                'symbol': c['symbol'],
                'direction': c['direction'],
                'score': c['composite_score'],
                'recommendation': c['recommendation']
            }
            for c in candidates[:5]
        ]
    }


# ============================================================================
# BACKWARD COMPATIBILITY FUNCTIONS
# ============================================================================

def execute_icici_futures_entry(
    account,
    symbol: str,
    direction: str,
    oi_analysis: Dict,
    sector_analysis: Dict,
    technical_analysis: Dict,
    composite_score: int
) -> Dict:
    """
    Complete entry workflow for ICICI Futures Strategy.

    This is the backward-compatible wrapper function.

    Args:
        account: BrokerAccount instance (ICICI)
        symbol: Stock symbol
        direction: 'LONG' or 'SHORT'
        oi_analysis: OI analysis results
        sector_analysis: Sector analysis results
        technical_analysis: Technical analysis results
        composite_score: Composite score

    Returns:
        dict: {
            'success': bool,
            'message': str,
            'suggestion': TradeSuggestion or None,
            'details': dict
        }
    """
    # Build candidate from parameters
    candidate = {
        'symbol': symbol,
        'direction': direction,
        'composite_score': composite_score,
        'oi_analysis': oi_analysis,
        'sector_analysis': sector_analysis,
        'technical_analysis': technical_analysis,
    }

    strategy = ICICIFuturesStrategy(account, candidate)
    result = strategy.execute_entry()
    return result.to_dict()
