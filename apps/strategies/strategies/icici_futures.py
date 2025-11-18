"""
ICICI Futures Strategy

Strategy: Directional futures trading based on multi-factor quantitative screening
         (OI analysis + sector strength + technical indicators) validated by LLM.

Account: ICICI Securities (₹1.2 Crores)
Target: ₹6 Lakhs monthly (~5% on margin, 0.5% on exposure)
Risk Profile: Defined stop-loss, averaging allowed (max 2 attempts)

Key Rules:
- ONE POSITION PER ACCOUNT (enforced via morning_check)
- 50% margin usage for first trade
- 15-day minimum to expiry (skip if < 15 days)
- LLM validation required (70% minimum confidence)
- Sector alignment CRITICAL (ALL timeframes must align)
- Averaging allowed: Max 2 attempts, 1% loss trigger

Screening Process:
1. Liquidity Filter → Top 50 stocks by volume
2. OI Analysis → Primary signal (Long/Short buildup, PCR)
3. Sector Analysis → ALL timeframes (3D, 7D, 21D) must align
4. Technical Analysis → Support/resistance, RSI, trend
5. Composite Scoring → Minimum 65/100
6. LLM Validation → Final gate (70% confidence minimum)
"""

import logging
import json
from decimal import Decimal
from datetime import datetime, time, date
from typing import Dict, List, Tuple, Optional

from django.utils import timezone

from apps.positions.services.position_manager import morning_check, create_position
from apps.core.services.expiry_selector import select_expiry_for_futures
from apps.accounts.services.margin_manager import calculate_usable_margin
from apps.risk.services.risk_manager import check_risk_limits
from apps.strategies.filters.sector_filter import analyze_sector
from apps.data.analyzers import (
    OpenInterestAnalyzer,
    TrendlyneScoreAnalyzer,
    VolumeAnalyzer,
    DMAAnalyzer,
    TechnicalIndicatorAnalyzer
)
from apps.llm.services.trade_validator import validate_trade
from apps.data.models import ContractStockData, ContractData
from apps.positions.models import Position
from apps.accounts.models import BrokerAccount
from apps.trading.services import TradeSuggestionService, FuturesSuggestionFormatter
from apps.trading.risk_calculator import FuturesRiskCalculator, SupportResistanceCalculator

logger = logging.getLogger(__name__)


def screen_futures_opportunities(
    min_volume_rank: int = 50,
    min_score: int = 65
) -> List[Dict]:
    """
    Screen for futures trading opportunities using multi-factor analysis

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

    # Get stocks with F&O data, sorted by volume
    # Using fno_total_oi > 0 to identify stocks with F&O data
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
                logger.debug(f"  ❌ Skipped {symbol}: Neutral OI signal")
                continue

            # STEP 3: Sector Analysis (CRITICAL FILTER)
            sector_analysis = analyze_sector(symbol)

            direction = oi_data['signal']  # 'BULLISH' or 'BEARISH'

            # Check if sector allows the direction
            if direction == 'BULLISH' and not sector_analysis['allow_long']:
                logger.debug(
                    f"  ❌ Skipped {symbol}: Sector doesn't support LONG "
                    f"({sector_analysis['verdict']})"
                )
                continue

            if direction == 'BEARISH' and not sector_analysis['allow_short']:
                logger.debug(
                    f"  ❌ Skipped {symbol}: Sector doesn't support SHORT "
                    f"({sector_analysis['verdict']})"
                )
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
                logger.debug(f"  ❌ Skipped {symbol}: Score {composite_score}/100 below minimum")
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

            logger.info(f"  ✅ QUALIFIED: {symbol}")
            logger.info(f"     Direction: {direction}")
            logger.info(f"     Score: {composite_score}/100")
            logger.info(f"     OI: {oi_data['buildup_type']}")
            logger.info(f"     Sector: {sector_analysis['verdict']}")
            logger.info("")

        except Exception as e:
            logger.error(f"  ❌ Error analyzing {symbol}: {e}")
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


def analyze_oi_for_stock(symbol: str) -> Tuple[int, Dict]:
    """
    Analyze Open Interest for a stock

    Returns:
        tuple: (oi_score: int (0-40), oi_data: dict)
    """

    oi_analyzer = OpenInterestAnalyzer()

    # Get current expiry
    # TODO: Fetch actual expiry from contract data
    expiry = '2024-11-28'  # Placeholder

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
    Analyze technical indicators for a stock

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
            # Check for golden cross (bullish) or death cross (bearish)
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
    Calculate composite score from individual components

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

    # Normalize sector score (convert 50 → 25, 0 → 0)
    normalized_sector_score = min(sector_score, 25)

    composite = oi_score + normalized_sector_score + technical_score

    return int(composite)


def execute_icici_futures_entry(
    account: BrokerAccount,
    symbol: str,
    direction: str,
    oi_analysis: Dict,
    sector_analysis: Dict,
    technical_analysis: Dict,
    composite_score: int
) -> Dict:
    """
    Complete entry workflow for ICICI Futures Strategy

    Workflow:
        1. Morning position check (ONE POSITION RULE)
        2. Entry timing validation
        3. Expiry selection (15-day rule)
        4. LLM validation (70% confidence minimum)
        5. Calculate position size (50% margin + risk-based)
        6. Risk limit checks
        7. Place order (paper trading or real)

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
            'position': Position or None,
            'details': dict
        }
    """

    logger.info("=" * 100)
    logger.info("ICICI FUTURES STRATEGY - ENTRY EVALUATION")
    logger.info("=" * 100)
    logger.info(f"Account: {account.broker} - {account.account_name}")
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Direction: {direction}")
    logger.info(f"Composite Score: {composite_score}/100")
    logger.info(f"Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    # STEP 1: Morning Check (ONE POSITION RULE)
    logger.info("STEP 1: Morning Position Check (ONE POSITION RULE)")
    logger.info("-" * 80)

    morning_check_result = morning_check(account)

    if not morning_check_result['allow_new_entry']:
        logger.warning(f"❌ {morning_check_result['message']}")
        logger.info("=" * 100)
        return {
            'success': False,
            'message': morning_check_result['message'],
            'position': None,
            'details': morning_check_result
        }

    logger.info(f"✅ {morning_check_result['message']}")
    logger.info("")

    # STEP 2: Entry Timing Validation
    logger.info("STEP 2: Entry Timing Validation")
    logger.info("-" * 80)

    current_time = timezone.now().time()
    entry_start = time(9, 15)   # 9:15 AM
    entry_end = time(15, 0)     # 3:00 PM

    if not (entry_start <= current_time <= entry_end):
        msg = f"❌ Entry time window closed (allowed: 09:15-15:00, current: {current_time.strftime('%H:%M')})"
        logger.warning(msg)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'current_time': current_time.strftime('%H:%M')}
        }

    logger.info(f"✅ Entry timing valid (current: {current_time.strftime('%H:%M')})")
    logger.info("")

    # STEP 3: Expiry Selection (15-day rule)
    logger.info("STEP 3: Expiry Selection (15-day minimum rule)")
    logger.info("-" * 80)

    try:
        selected_expiry, expiry_details = select_expiry_for_futures(symbol=symbol, min_days=15)
        days_to_expiry = (selected_expiry - date.today()).days

        logger.info(f"✅ Selected Expiry: {selected_expiry} ({days_to_expiry} days)")
        logger.info(f"   Details: {expiry_details}")
        logger.info("")
    except Exception as e:
        msg = f"❌ Expiry selection failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'error': str(e)}
        }

    # STEP 4: LLM Validation (70% confidence minimum)
    logger.info("STEP 4: LLM Trade Validation (70% confidence minimum)")
    logger.info("-" * 80)

    try:
        # Prepare context for LLM
        llm_context = {
            'symbol': symbol,
            'direction': direction,
            'composite_score': composite_score,
            'oi_buildup': oi_analysis['buildup_type'],
            'sector_verdict': sector_analysis['verdict'],
            'sector_performance': sector_analysis['performance']
        }

        llm_result = validate_trade(
            symbol=symbol,
            direction=direction,
            strategy_type='FUTURES'
        )

        logger.info(f"LLM Validation Result:")
        logger.info(f"  Approved: {llm_result.get('approved', False)}")
        logger.info(f"  Confidence: {llm_result.get('confidence', 0)*100:.1f}%")
        logger.info(f"  Reasoning: {llm_result.get('reasoning', 'N/A')}")
        logger.info("")

        if not llm_result.get('approved', False):
            msg = f"❌ LLM validation failed: {llm_result.get('reasoning', 'Not approved')}"
            logger.warning(msg)
            logger.info("=" * 100)
            return {
                'success': False,
                'message': msg,
                'position': None,
                'details': llm_result
            }

        if llm_result.get('confidence', 0) < 0.70:
            msg = f"❌ LLM confidence {llm_result.get('confidence', 0)*100:.1f}% below 70% threshold"
            logger.warning(msg)
            logger.info("=" * 100)
            return {
                'success': False,
                'message': msg,
                'position': None,
                'details': llm_result
            }

        logger.info(f"✅ LLM validation passed (confidence: {llm_result.get('confidence', 0)*100:.1f}%)")
        logger.info("")

    except Exception as e:
        msg = f"❌ LLM validation error: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'error': str(e)}
        }

    # STEP 5: Position Sizing (50% margin + risk-based)
    logger.info("STEP 5: Position Sizing (50% margin + risk-based)")
    logger.info("-" * 80)

    try:
        usable_margin = calculate_usable_margin(account)

        # Get current price
        # TODO: Fetch actual futures price from broker
        current_price = Decimal('1000')  # Placeholder

        # Calculate stop-loss and target
        stop_loss_pct = Decimal('0.005')  # 0.5% default SL
        target_pct = Decimal('0.01')      # 1.0% default target

        if direction == 'LONG':
            stop_loss = current_price * (Decimal('1') - stop_loss_pct)
            target = current_price * (Decimal('1') + target_pct)
        else:  # SHORT
            stop_loss = current_price * (Decimal('1') + stop_loss_pct)
            target = current_price * (Decimal('1') - target_pct)

        # Calculate position size based on risk
        # Risk per trade: ₹60,000 (from design doc)
        max_risk_per_trade = Decimal('60000')
        risk_per_unit = abs(current_price - stop_loss)
        max_quantity = int(max_risk_per_trade / risk_per_unit) if risk_per_unit > 0 else 0

        # Futures lot size
        # TODO: Fetch from contract data
        lot_size = 1  # Placeholder

        # Calculate lots based on margin and risk
        margin_per_lot = Decimal('100000')  # Placeholder
        max_lots_by_margin = int(usable_margin / margin_per_lot)
        max_lots_by_risk = max(1, max_quantity // lot_size)

        # Use minimum of both
        lots = min(max_lots_by_margin, max_lots_by_risk, 10)  # Max 10 lots safety cap

        if lots < 1:
            msg = f"❌ Insufficient margin or risk capacity"
            logger.warning(msg)
            logger.info("=" * 100)
            return {
                'success': False,
                'message': msg,
                'position': None,
                'details': {
                    'usable_margin': usable_margin,
                    'margin_required': margin_per_lot
                }
            }

        quantity = lots * lot_size
        margin_used = margin_per_lot * lots

        logger.info(f"Usable Margin (50%): ₹{usable_margin:,.0f}")
        logger.info(f"Current Price: ₹{current_price:,.2f}")
        logger.info(f"Stop-Loss: ₹{stop_loss:,.2f} ({stop_loss_pct*100:.1f}%)")
        logger.info(f"Target: ₹{target:,.2f} ({target_pct*100:.1f}%)")
        logger.info(f"Lots: {lots}")
        logger.info(f"Quantity: {quantity}")
        logger.info(f"Margin Used: ₹{margin_used:,.0f}")
        logger.info(f"✅ Position sizing complete")
        logger.info("")
    except Exception as e:
        msg = f"❌ Position sizing failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'error': str(e)}
        }

    # STEP 6: Risk Limit Checks
    logger.info("STEP 6: Risk Limit Validation")
    logger.info("-" * 80)

    try:
        risk_check = check_risk_limits(account)

        if risk_check['action_required'] != 'NONE':
            msg = f"❌ Risk limits breached: {risk_check['message']}"
            logger.warning(msg)
            logger.info("=" * 100)
            return {
                'success': False,
                'message': msg,
                'position': None,
                'details': risk_check
            }

        logger.info(f"✅ All risk limits satisfied")
        logger.info("")
    except Exception as e:
        msg = f"❌ Risk check failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'position': None,
            'details': {'error': str(e)}
        }

    # STEP 7: Create Trade Suggestion
    logger.info("STEP 7: Trade Suggestion Creation")
    logger.info("-" * 80)

    try:
        # Prepare algorithm reasoning (complete analysis details)
        algorithm_reasoning = {
            'title': 'ICICI Futures Strategy',
            'summary': 'Multi-factor scoring for directional trade',
            'scoring': {
                'oi_score': oi_analysis.get('oi_score', 0),
                'sector_score': sector_analysis.get('score', 0),
                'technical_score': 0,  # Would be calculated in analyze_technical
                'composite_total': composite_score,
                'composite_breakdown': {
                    'oi_analysis': {
                        'signal': oi_analysis.get('signal'),
                        'buildup_type': oi_analysis.get('buildup_type'),
                        'buildup_sentiment': oi_analysis.get('buildup_sentiment'),
                        'price_change_pct': oi_analysis.get('price_change_pct'),
                        'oi_change_pct': oi_analysis.get('oi_change_pct'),
                        'pcr': oi_analysis.get('pcr'),
                    },
                    'sector_analysis': {
                        'verdict': sector_analysis.get('verdict'),
                        'performance': sector_analysis.get('performance'),
                        'allow_long': sector_analysis.get('allow_long'),
                        'allow_short': sector_analysis.get('allow_short'),
                    },
                    'technical_analysis': technical_analysis
                }
            },
            'llm_validation': {
                'approved': llm_result.get('approved', False),
                'confidence': llm_result.get('confidence', 0),
                'reasoning': llm_result.get('reasoning', ''),
                'confidence_pct': f"{llm_result.get('confidence', 0)*100:.1f}%"
            },
            'position_parameters': {
                'entry_time_valid': True,
                'position_count_check': morning_check_result['message'],
                'days_to_expiry': days_to_expiry,
            },
            'final_decision': {
                'recommendation': 'DIRECTIONAL_TRADE',
                'position_details': {
                    'symbol': symbol,
                    'direction': direction,
                    'entry_price': str(current_price),
                    'quantity': quantity,
                    'stop_loss': str(stop_loss),
                    'target': str(target),
                    'margin_required': str(margin_used),
                    'max_loss': str(risk_scenarios['max_loss']),
                    'max_profit': str(risk_scenarios['max_profit']),
                    'risk_reward_ratio': str(risk_scenarios['risk_reward_ratio']),
                    'expected_profit': str(risk_scenarios['max_profit']),
                    'expiry_date': str(selected_expiry),
                },
                'risk_reward': {
                    'max_profit': str(risk_scenarios['max_profit']),
                    'max_loss': str(risk_scenarios['max_loss']),
                    'risk_reward_ratio': str(risk_scenarios['risk_reward_ratio']),
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

        # Calculate risk/reward scenarios
        risk_scenarios = FuturesRiskCalculator.calculate_scenarios(
            current_price=current_price,
            direction=direction,
            quantity=quantity,
            stop_loss=stop_loss,
            target=target
        )

        # Support and Resistance (TODO: Fetch actual price data from Trendlyne/broker)
        # For now, using placeholder data based on recent volatility
        volatility_range = current_price * Decimal('0.02')  # 2% volatility range
        support_resistance = SupportResistanceCalculator.calculate_next_levels(
            current_price=current_price,
            support_level=current_price - volatility_range,
            resistance_level=current_price + volatility_range
        )

        # Prepare position details with risk metrics
        position_details = {
            'symbol': symbol,
            'direction': direction,
            'entry_price': str(current_price),
            'quantity': quantity,
            'lot_size': lot_size,
            'stop_loss': str(stop_loss),
            'target': str(target),
            'margin_required': str(margin_used),
            'max_loss': str(risk_scenarios['max_loss']),
            'max_profit': str(risk_scenarios['max_profit']),
            'risk_reward_ratio': str(risk_scenarios['risk_reward_ratio']),
            'expected_profit': str(risk_scenarios['max_profit']),
            'expiry_date': str(selected_expiry),
            # Support and Resistance
            'support_level': str(support_resistance['support']),
            'support_distance': str(support_resistance['support_distance']),
            'support_distance_pct': str(support_resistance['support_distance_pct']),
            'resistance_level': str(support_resistance['resistance']),
            'resistance_distance': str(support_resistance['resistance_distance']),
            'resistance_distance_pct': str(support_resistance['resistance_distance_pct']),
            'next_support': str(support_resistance['next_support']),
            'next_resistance': str(support_resistance['next_resistance']),
        }

        # Create trade suggestion
        suggestion = TradeSuggestionService.create_suggestion(
            user=account.user,
            strategy='icici_futures',
            suggestion_type='FUTURES',
            instrument=symbol,
            direction=direction,
            algorithm_reasoning=algorithm_reasoning,
            position_details=position_details
        )

        logger.info(f"✅ Trade suggestion created successfully: {suggestion.id}")
        logger.info(f"   Status: {suggestion.get_status_display()}")
        logger.info(f"   Auto-Trade: {suggestion.is_auto_trade}")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Direction: {direction}")
        logger.info(f"   Entry Price: ₹{current_price:,.2f}")
        logger.info(f"   Margin Used: ₹{margin_used:,.0f}")
        logger.info("")
        logger.info("=" * 100)

        return {
            'success': True,
            'message': f'Trade suggestion #{suggestion.id} created (Status: {suggestion.get_status_display()})',
            'suggestion': suggestion,
            'details': {
                'symbol': symbol,
                'direction': direction,
                'composite_score': composite_score,
                'llm_confidence': llm_result.get('confidence', 0),
                'expiry': selected_expiry,
                'margin_used': margin_used,
                'suggestion_status': suggestion.get_status_display(),
                'is_auto_trade': suggestion.is_auto_trade,
            }
        }

    except Exception as e:
        msg = f"❌ Trade suggestion creation failed: {str(e)}"
        logger.error(msg, exc_info=True)
        logger.info("=" * 100)
        return {
            'success': False,
            'message': msg,
            'suggestion': None,
            'details': {'error': str(e)}
        }


def analyze_stock_for_futures(stock_symbol: str) -> Optional[Dict]:
    """
    Analyze a specific stock for futures trading

    Used for manual verification of trade ideas

    Args:
        stock_symbol: Stock symbol to analyze

    Returns:
        dict: Analysis results with all metrics, or None if unable to analyze
    """
    try:
        logger.info(f"Analyzing {stock_symbol} for futures trading")

        # Get stock data - use nse_code field
        stock = ContractStockData.objects.filter(nse_code=stock_symbol).first()
        if not stock:
            # Try with stock_name as fallback
            stock = ContractStockData.objects.filter(stock_name__icontains=stock_symbol).first()

        if not stock:
            logger.warning(f"{stock_symbol} not found in database")
            return None

        # Initialize analyzers
        oi_analyzer = OpenInterestAnalyzer()
        trendlyne_analyzer = TrendlyneScoreAnalyzer()
        volume_analyzer = VolumeAnalyzer()
        dma_analyzer = DMAAnalyzer()
        technical_analyzer = TechnicalIndicatorAnalyzer()

        # Run OI analysis
        oi_score, oi_details = analyze_oi(stock_symbol, oi_analyzer)

        # Sector analysis
        sector_score, sector_details = analyze_sector_alignment(stock)

        # Technical analysis
        tech_score, tech_details = analyze_technical(
            stock_symbol,
            trendlyne_analyzer,
            dma_analyzer,
            technical_analyzer
        )

        # Volume analysis
        volume_score = min(50, volume_analyzer.get_volume_rank(stock_symbol))

        # Composite score
        composite_score = oi_score + sector_score + tech_score

        # Determine direction
        signal = oi_details.get('signal', 'NEUTRAL')
        direction = 'LONG' if signal == 'BULLISH' else 'SHORT' if signal == 'BEARISH' else 'NEUTRAL'

        # Calculate entry, SL, target
        current_price = float(stock.current_price or 0)

        # Support/Resistance calculator
        sr_calculator = SupportResistanceCalculator()
        support, resistance = sr_calculator.calculate_levels(
            stock_symbol,
            current_price
        )

        if direction == 'LONG':
            entry_price = current_price
            stop_loss = support * 0.98  # 2% below support
            target = resistance * 1.02  # 2% above resistance
        elif direction == 'SHORT':
            entry_price = current_price
            stop_loss = resistance * 1.02  # 2% above resistance
            target = support * 0.98  # 2% below support
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
            'volume_rank': volume_score,
            'oi_analysis': oi_details.get('buildup_type', 'Unknown'),
            'sector_analysis': sector_details.get('alignment', 'Unknown'),
            'technical_setup': tech_details.get('summary', 'Unknown'),
            'reasoning': f"{direction} setup with {composite_score}/100 score"
        }

    except Exception as e:
        logger.error(f"Error analyzing {stock_symbol}: {e}", exc_info=True)
        return None
