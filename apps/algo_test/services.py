"""
Algorithm Testing Services

Calculation and analysis services for algorithm testing
"""

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class OptionsAlgorithmCalculator:
    """
    Options (Kotak Strangle) Algorithm Calculator
    Replicates the exact logic from kotak_strangle.py
    """

    # Configuration
    BASE_DELTA_PCT = Decimal('0.50')  # 0.50%
    VIX_ADJUSTMENT_LOW = Decimal('1.00')  # VIX < 15
    VIX_ADJUSTMENT_MID = Decimal('1.10')  # VIX 15-18
    VIX_ADJUSTMENT_HIGH = Decimal('1.20')  # VIX > 18
    ENTRY_WINDOW_START = 9  # 9:00 AM
    ENTRY_WINDOW_END = 11  # 11:30 AM (exclusive at 11:30)
    MIN_MARGIN_USAGE_PCT = Decimal('50')  # Use only 50% of margin
    MAX_DELTA_THRESHOLD = 300
    MIN_PROFIT_PCT_FOR_EOD_EXIT = Decimal('50')  # 50% profit required

    @staticmethod
    def get_vix_adjusted_delta(vix: Decimal) -> Decimal:
        """Calculate VIX-adjusted delta percentage"""
        if vix < Decimal('15'):
            adjustment = OptionsAlgorithmCalculator.VIX_ADJUSTMENT_LOW
        elif vix <= Decimal('18'):
            adjustment = OptionsAlgorithmCalculator.VIX_ADJUSTMENT_MID
        else:
            adjustment = OptionsAlgorithmCalculator.VIX_ADJUSTMENT_HIGH

        adjusted = OptionsAlgorithmCalculator.BASE_DELTA_PCT * adjustment
        return adjusted

    @staticmethod
    def calculate_strike_distance(
        spot_price: Decimal,
        adjusted_delta: Decimal,
        days_to_expiry: int
    ) -> Decimal:
        """
        Calculate strike distance using the formula:
        strike_distance = spot_price × adjusted_delta × days_to_expiry
        """
        distance = spot_price * (adjusted_delta / Decimal('100')) * Decimal(days_to_expiry)
        return distance

    @staticmethod
    def round_strike(strike: Decimal, round_to: int = 100) -> int:
        """Round strike to nearest round_to value (default 100)"""
        return int((strike / round_to).to_integral_value() * round_to)

    @staticmethod
    def calculate_strikes(
        spot_price: Decimal,
        vix: Decimal,
        days_to_expiry: int
    ) -> Tuple[int, int, Decimal]:
        """
        Calculate call and put strikes for strangle

        Returns:
            (call_strike, put_strike, adjusted_delta)
        """
        adjusted_delta = OptionsAlgorithmCalculator.get_vix_adjusted_delta(vix)
        strike_distance = OptionsAlgorithmCalculator.calculate_strike_distance(
            spot_price, adjusted_delta, days_to_expiry
        )

        call_strike = OptionsAlgorithmCalculator.round_strike(spot_price + strike_distance)
        put_strike = OptionsAlgorithmCalculator.round_strike(spot_price - strike_distance)

        return call_strike, put_strike, adjusted_delta

    @staticmethod
    def check_one_position_rule(active_positions: int) -> Tuple[bool, str]:
        """Check if ONE POSITION RULE is satisfied"""
        if active_positions > 0:
            return False, f"Active position exists. ONE POSITION RULE: max 1 position"
        return True, "No active positions. Can proceed."

    @staticmethod
    def check_entry_timing(current_time: datetime) -> Tuple[bool, str]:
        """Check if current time is within entry window (9:00-11:30 AM)"""
        hour = current_time.hour
        minute = current_time.minute

        entry_start_minutes = OptionsAlgorithmCalculator.ENTRY_WINDOW_START * 60
        entry_end_minutes = 11 * 60 + 30  # 11:30 AM

        current_minutes = hour * 60 + minute

        if entry_start_minutes <= current_minutes < entry_end_minutes:
            return True, f"Within entry window: {current_time.strftime('%H:%M')}"
        return False, f"Outside entry window (9:00-11:30 AM). Current: {current_time.strftime('%H:%M')}"

    @staticmethod
    def check_global_markets_stability(
        sgx_nifty_change: Decimal,
        nasdaq_change: Decimal,
        dow_change: Decimal,
        nifty_1d_change: Decimal,
        nifty_3d_change: Decimal
    ) -> Tuple[bool, Dict]:
        """Check global market stability thresholds"""
        SGX_THRESHOLD = Decimal('0.5')
        US_THRESHOLD = Decimal('1.0')
        NIFTY_1D_THRESHOLD = Decimal('1.0')
        NIFTY_3D_THRESHOLD = Decimal('2.0')

        results = {
            'sgx_nifty': {
                'value': float(sgx_nifty_change),
                'threshold': float(SGX_THRESHOLD),
                'pass': abs(sgx_nifty_change) <= SGX_THRESHOLD
            },
            'nasdaq': {
                'value': float(nasdaq_change),
                'threshold': float(US_THRESHOLD),
                'pass': abs(nasdaq_change) <= US_THRESHOLD
            },
            'dow': {
                'value': float(dow_change),
                'threshold': float(US_THRESHOLD),
                'pass': abs(dow_change) <= US_THRESHOLD
            },
            'nifty_1d': {
                'value': float(nifty_1d_change),
                'threshold': float(NIFTY_1D_THRESHOLD),
                'pass': abs(nifty_1d_change) <= NIFTY_1D_THRESHOLD
            },
            'nifty_3d': {
                'value': float(nifty_3d_change),
                'threshold': float(NIFTY_3D_THRESHOLD),
                'pass': abs(nifty_3d_change) <= NIFTY_3D_THRESHOLD
            }
        }

        all_pass = all(r['pass'] for r in results.values())
        return all_pass, results

    @staticmethod
    def check_economic_events(days_ahead: int = 5) -> Tuple[bool, List[str]]:
        """
        Check for major economic events in the next N days
        Returns True if NO major events found
        """
        # In production, this would query a calendar API
        # For now, return true (no blocking events)
        return True, ["No major events in next 5 days"]

    @staticmethod
    def check_market_regime(
        vix: Decimal,
        price_vs_bb: str = 'middle'  # 'upper', 'middle', 'lower'
    ) -> Tuple[bool, Dict]:
        """
        Check market regime (VIX, Bollinger Bands)
        VIX max threshold: 20
        Price should not be at extremes (upper/lower BB)
        """
        VIX_MAX = Decimal('20')

        vix_pass = vix <= VIX_MAX
        bb_pass = price_vs_bb == 'middle'

        results = {
            'vix': {
                'value': float(vix),
                'threshold': float(VIX_MAX),
                'pass': vix_pass
            },
            'bollinger_bands': {
                'position': price_vs_bb,
                'pass': bb_pass
            }
        }

        all_pass = vix_pass and bb_pass
        return all_pass, results

    @staticmethod
    def check_margin_availability(
        available_margin: Decimal,
        margin_required: Decimal
    ) -> Tuple[bool, Dict]:
        """Check if sufficient margin available (50% rule)"""
        usable_margin = available_margin * (OptionsAlgorithmCalculator.MIN_MARGIN_USAGE_PCT / Decimal('100'))

        has_margin = usable_margin >= margin_required

        results = {
            'available_margin': float(available_margin),
            'usable_margin': float(usable_margin),
            'margin_required': float(margin_required),
            'margin_buffer': float(usable_margin - margin_required) if has_margin else float(margin_required - usable_margin),
            'pass': has_margin
        }

        return has_margin, results

    @staticmethod
    def calculate_margin_requirement(
        call_premium: Decimal,
        put_premium: Decimal,
        lot_size: int = 50
    ) -> Decimal:
        """Calculate margin requirement for strangle"""
        # Margin is typically 10-15% of notional value
        # For simplicity, use 15% of premium collected
        premium_per_lot = (call_premium + put_premium) * lot_size
        margin_requirement = premium_per_lot * Decimal('0.15')
        return margin_requirement

    @staticmethod
    def run_full_analysis(
        nifty_spot: Decimal,
        vix: Decimal,
        days_to_expiry: int,
        available_margin: Decimal,
        active_positions: int,
        current_time: datetime,
        sgx_nifty_change: Decimal,
        nasdaq_change: Decimal,
        dow_change: Decimal,
        nifty_1d_change: Decimal,
        nifty_3d_change: Decimal,
        call_premium: Decimal = None,
        put_premium: Decimal = None,
        price_vs_bb: str = 'middle'
    ) -> Dict:
        """
        Run complete options algorithm analysis
        Returns comprehensive results with all filter checks
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'inputs': {
                'nifty_spot': float(nifty_spot),
                'vix': float(vix),
                'days_to_expiry': days_to_expiry,
                'available_margin': float(available_margin),
                'active_positions': active_positions,
            },
            'calculations': {},
            'filters': {},
            'final_decision': {}
        }

        # Step 1: Calculate strikes
        try:
            call_strike, put_strike, adjusted_delta = OptionsAlgorithmCalculator.calculate_strikes(
                nifty_spot, vix, days_to_expiry
            )
            results['calculations']['vix_adjusted_delta'] = float(adjusted_delta)
            results['calculations']['strike_distance'] = float(
                OptionsAlgorithmCalculator.calculate_strike_distance(nifty_spot, adjusted_delta, days_to_expiry)
            )
            results['calculations']['call_strike'] = call_strike
            results['calculations']['put_strike'] = put_strike

            # Default premium values if not provided
            if call_premium is None:
                call_premium = nifty_spot * Decimal('0.003')  # 0.3% of spot
            if put_premium is None:
                put_premium = nifty_spot * Decimal('0.0035')  # 0.35% of spot

            results['calculations']['call_premium'] = float(call_premium)
            results['calculations']['put_premium'] = float(put_premium)
            results['calculations']['premium_collected'] = float(call_premium + put_premium)

        except Exception as e:
            results['final_decision']['status'] = 'ERROR'
            results['final_decision']['error'] = str(e)
            return results

        # Step 2: Run all filters
        all_filters_pass = True

        # Filter 1: ONE POSITION RULE
        filter_pass, filter_msg = OptionsAlgorithmCalculator.check_one_position_rule(active_positions)
        results['filters']['one_position_rule'] = {
            'pass': filter_pass,
            'message': filter_msg
        }
        all_filters_pass = all_filters_pass and filter_pass

        # Filter 2: ENTRY TIMING
        filter_pass, filter_msg = OptionsAlgorithmCalculator.check_entry_timing(current_time)
        results['filters']['entry_timing'] = {
            'pass': filter_pass,
            'message': filter_msg
        }
        all_filters_pass = all_filters_pass and filter_pass

        # Filter 3: GLOBAL MARKETS STABILITY
        filter_pass, filter_detail = OptionsAlgorithmCalculator.check_global_markets_stability(
            sgx_nifty_change, nasdaq_change, dow_change, nifty_1d_change, nifty_3d_change
        )
        results['filters']['global_markets'] = {
            'pass': filter_pass,
            'details': filter_detail
        }
        all_filters_pass = all_filters_pass and filter_pass

        # Filter 4: ECONOMIC EVENTS
        filter_pass, events = OptionsAlgorithmCalculator.check_economic_events()
        results['filters']['economic_events'] = {
            'pass': filter_pass,
            'events': events
        }
        all_filters_pass = all_filters_pass and filter_pass

        # Filter 5: MARKET REGIME
        filter_pass, filter_detail = OptionsAlgorithmCalculator.check_market_regime(vix, price_vs_bb)
        results['filters']['market_regime'] = {
            'pass': filter_pass,
            'details': filter_detail
        }
        all_filters_pass = all_filters_pass and filter_pass

        # Filter 6: MARGIN AVAILABILITY
        margin_req = OptionsAlgorithmCalculator.calculate_margin_requirement(call_premium, put_premium)
        filter_pass, filter_detail = OptionsAlgorithmCalculator.check_margin_availability(
            available_margin, margin_req
        )
        results['filters']['margin_availability'] = {
            'pass': filter_pass,
            'details': filter_detail
        }
        all_filters_pass = all_filters_pass and filter_pass

        # Step 3: Final decision
        if all_filters_pass:
            results['final_decision']['decision'] = 'EXECUTE STRANGLE'
            results['final_decision']['status'] = 'ENTRY_APPROVED'
            results['final_decision']['position_details'] = {
                'instrument': 'NIFTY',
                'strategy': 'Short Strangle',
                'call_strike': call_strike,
                'put_strike': put_strike,
                'quantity_per_lot': 50,
                'lots': 1,
                'total_quantity': 50,
                'premium_collected': float(call_premium + put_premium),
                'margin_used': float(margin_req),
                'stop_loss': float((call_premium + put_premium) * Decimal('1.20')),
                'target': float((call_premium + put_premium) / Decimal('2')),
                'risk_reward_ratio': f"1:{float((call_premium + put_premium) / Decimal('2')) / float(margin_req):.2f}"
            }
        else:
            failed_filters = [k for k, v in results['filters'].items() if not v['pass']]
            results['final_decision']['decision'] = 'REJECT ENTRY'
            results['final_decision']['status'] = 'ENTRY_REJECTED'
            results['final_decision']['reason'] = f"Failed filters: {', '.join(failed_filters)}"

        return results


class FuturesAlgorithmCalculator:
    """
    Futures (ICICI) Algorithm Calculator
    Scoring and validation for futures positions
    """

    # Score weights
    OI_SCORE_WEIGHT = Decimal('40')  # 0-40 points
    SECTOR_SCORE_WEIGHT = Decimal('25')  # 0 or 25 points
    TECHNICAL_SCORE_WEIGHT = Decimal('35')  # 0-35 points
    MIN_COMPOSITE_SCORE = Decimal('65')
    MIN_LLM_CONFIDENCE = Decimal('70')

    @staticmethod
    def calculate_oi_score(
        price_change_pct: Decimal,
        oi_change_pct: Decimal,
        pcr_ratio: Decimal
    ) -> Tuple[Decimal, Dict]:
        """
        Calculate OI Analysis score (0-40 points)
        """
        buildup_score = Decimal('0')
        buildup_type = None

        # OI Buildup pattern detection
        price_up = price_change_pct > Decimal('0')
        oi_up = oi_change_pct > Decimal('0')

        if price_up and oi_up:
            buildup_type = 'LONG_BUILDUP'
            buildup_score = Decimal('25')
        elif not price_up and oi_up:
            buildup_type = 'SHORT_BUILDUP'
            buildup_score = Decimal('25')
        elif not price_up and not oi_up:
            buildup_type = 'LONG_UNWINDING'
            buildup_score = Decimal('0')
        elif price_up and not oi_up:
            buildup_type = 'SHORT_COVERING'
            buildup_score = Decimal('15')

        # PCR Analysis
        pcr_score = Decimal('0')
        pcr_signal = None

        if pcr_ratio > Decimal('1.2'):
            pcr_signal = 'BULLISH'
            pcr_score = Decimal('15')
        elif pcr_ratio < Decimal('0.8'):
            pcr_signal = 'BEARISH'
            pcr_score = Decimal('5')
        else:
            pcr_signal = 'NEUTRAL'
            pcr_score = Decimal('10')

        total_score = min(buildup_score + pcr_score, FuturesAlgorithmCalculator.OI_SCORE_WEIGHT)

        details = {
            'buildup_pattern': buildup_type,
            'buildup_score': float(buildup_score),
            'price_change_pct': float(price_change_pct),
            'oi_change_pct': float(oi_change_pct),
            'pcr_ratio': float(pcr_ratio),
            'pcr_signal': pcr_signal,
            'pcr_score': float(pcr_score),
            'total_score': float(total_score)
        }

        return total_score, details

    @staticmethod
    def calculate_sector_score(
        sector_3d_change: Decimal,
        sector_7d_change: Decimal,
        sector_21d_change: Decimal,
        direction: str = 'LONG'
    ) -> Tuple[Decimal, Dict]:
        """
        Calculate Sector Analysis score (0 or 25 points)
        CRITICAL: All timeframes must align with direction
        """
        all_positive = (
            sector_3d_change > Decimal('0') and
            sector_7d_change > Decimal('0') and
            sector_21d_change > Decimal('0')
        )

        all_negative = (
            sector_3d_change < Decimal('0') and
            sector_7d_change < Decimal('0') and
            sector_21d_change < Decimal('0')
        )

        score = Decimal('0')
        verdict = None

        if direction == 'LONG':
            if all_positive:
                score = FuturesAlgorithmCalculator.SECTOR_SCORE_WEIGHT
                verdict = 'APPROVED_FOR_LONG'
            else:
                verdict = 'BLOCKED_MIXED_SIGNALS'
        elif direction == 'SHORT':
            if all_negative:
                score = FuturesAlgorithmCalculator.SECTOR_SCORE_WEIGHT
                verdict = 'APPROVED_FOR_SHORT'
            else:
                verdict = 'BLOCKED_MIXED_SIGNALS'

        details = {
            '3d_change': float(sector_3d_change),
            '7d_change': float(sector_7d_change),
            '21d_change': float(sector_21d_change),
            'all_positive': all_positive,
            'all_negative': all_negative,
            'verdict': verdict,
            'score': float(score)
        }

        return score, details

    @staticmethod
    def calculate_technical_score(
        trendlyne_score: Decimal,
        dma_score: Decimal,
        volume_score: Decimal
    ) -> Tuple[Decimal, Dict]:
        """
        Calculate Technical Analysis score (0-35 points)
        """
        # Trendlyne: 0-15
        trendlyne_contribution = (trendlyne_score / Decimal('15')) * Decimal('12')

        # DMA: 0-10
        dma_contribution = (dma_score / Decimal('10')) * Decimal('8')

        # Volume: 0-10
        volume_contribution = (volume_score / Decimal('10')) * Decimal('9')

        total_score = min(
            trendlyne_contribution + dma_contribution + volume_contribution,
            FuturesAlgorithmCalculator.TECHNICAL_SCORE_WEIGHT
        )

        details = {
            'trendlyne_score': float(trendlyne_score),
            'trendlyne_contribution': float(trendlyne_contribution),
            'dma_score': float(dma_score),
            'dma_contribution': float(dma_contribution),
            'volume_score': float(volume_score),
            'volume_contribution': float(volume_contribution),
            'total_score': float(total_score)
        }

        return total_score, details

    @staticmethod
    def run_full_analysis(
        symbol: str,
        direction: str,
        current_price: Decimal,
        previous_price: Decimal,
        current_oi: int,
        previous_oi: int,
        pcr_ratio: Decimal,
        sector_3d_change: Decimal,
        sector_7d_change: Decimal,
        sector_21d_change: Decimal,
        trendlyne_score: Decimal,
        dma_score: Decimal,
        volume_score: Decimal,
        llm_confidence: Decimal = None,
        available_margin: Decimal = None
    ) -> Dict:
        """
        Run complete futures algorithm analysis
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'direction': direction,
            'inputs': {
                'current_price': float(current_price),
                'previous_price': float(previous_price),
                'current_oi': current_oi,
                'previous_oi': previous_oi
            },
            'scoring': {},
            'final_decision': {}
        }

        # Calculate price and OI changes
        price_change = current_price - previous_price
        price_change_pct = (price_change / previous_price) * Decimal('100')

        oi_change = current_oi - previous_oi
        oi_change_pct = (oi_change / previous_oi) * Decimal('100') if previous_oi > 0 else Decimal('0')

        # Factor 1: OI Analysis
        oi_score, oi_details = FuturesAlgorithmCalculator.calculate_oi_score(
            price_change_pct, oi_change_pct, pcr_ratio
        )
        results['scoring']['oi_analysis'] = {
            'score': float(oi_score),
            'weight': float(FuturesAlgorithmCalculator.OI_SCORE_WEIGHT),
            'details': oi_details
        }

        # Factor 2: Sector Analysis
        sector_score, sector_details = FuturesAlgorithmCalculator.calculate_sector_score(
            sector_3d_change, sector_7d_change, sector_21d_change, direction
        )
        results['scoring']['sector_analysis'] = {
            'score': float(sector_score),
            'weight': float(FuturesAlgorithmCalculator.SECTOR_SCORE_WEIGHT),
            'details': sector_details
        }

        # Factor 3: Technical Analysis
        technical_score, technical_details = FuturesAlgorithmCalculator.calculate_technical_score(
            trendlyne_score, dma_score, volume_score
        )
        results['scoring']['technical_analysis'] = {
            'score': float(technical_score),
            'weight': float(FuturesAlgorithmCalculator.TECHNICAL_SCORE_WEIGHT),
            'details': technical_details
        }

        # Calculate composite score
        composite_score = oi_score + sector_score + technical_score

        results['scoring']['composite'] = {
            'total': float(composite_score),
            'minimum_required': float(FuturesAlgorithmCalculator.MIN_COMPOSITE_SCORE),
            'qualified': composite_score >= FuturesAlgorithmCalculator.MIN_COMPOSITE_SCORE
        }

        # LLM Validation
        llm_approved = False
        if llm_confidence is not None:
            llm_approved = llm_confidence >= FuturesAlgorithmCalculator.MIN_LLM_CONFIDENCE
            results['llm_validation'] = {
                'confidence': float(llm_confidence),
                'minimum_required': float(FuturesAlgorithmCalculator.MIN_LLM_CONFIDENCE),
                'approved': llm_approved
            }
        else:
            results['llm_validation'] = {
                'confidence': 0,
                'minimum_required': float(FuturesAlgorithmCalculator.MIN_LLM_CONFIDENCE),
                'approved': False,
                'note': 'LLM confidence not provided'
            }

        # Final Decision
        if composite_score >= FuturesAlgorithmCalculator.MIN_COMPOSITE_SCORE and llm_approved:
            results['final_decision']['decision'] = f"EXECUTE {direction}"
            results['final_decision']['status'] = 'APPROVED'

            if available_margin:
                # Position sizing
                margin_per_lot = Decimal('35000')  # Example
                available_for_trading = available_margin * Decimal('0.50')  # 50% rule
                max_lots = int(available_for_trading / margin_per_lot)

                results['final_decision']['position_details'] = {
                    'symbol': symbol,
                    'direction': direction,
                    'max_lots': max_lots,
                    'suggested_lots': min(max_lots, 7),  # Default suggestion
                    'margin_available': float(available_margin),
                    'margin_for_trading': float(available_for_trading)
                }

        else:
            reasons = []
            if composite_score < FuturesAlgorithmCalculator.MIN_COMPOSITE_SCORE:
                reasons.append(f"Composite score {float(composite_score):.0f} < minimum {float(FuturesAlgorithmCalculator.MIN_COMPOSITE_SCORE):.0f}")
            if not llm_approved:
                reasons.append(f"LLM confidence insufficient")

            results['final_decision']['decision'] = 'BLOCK TRADE'
            results['final_decision']['status'] = 'REJECTED'
            results['final_decision']['reasons'] = reasons

        return results
