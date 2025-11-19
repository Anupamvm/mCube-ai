"""
Psychological Level Analysis for Strike Selection

Psychological levels are round numbers where market participants tend to
place heavy support/resistance. Options near these levels are riskier.

Key Psychological Levels:
- Major: 25,000, 26,000, 27,000 (1000s)
- Intermediate: 25,500, 26,500 (500s)
- Minor: 25,100, 25,200, 25,300, etc. (100s)

Strategy:
If calculated strike is within danger zone of psychological level:
- CALL strikes: Move UP one strike (safer - further OTM)
- PUT strikes: Move DOWN one strike (safer - further OTM)

This protects against unexpected support/resistance at round numbers.
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class PsychologicalLevelAnalyzer:
    """
    Analyzes strikes for proximity to psychological levels
    and recommends adjustments
    """

    # Danger zone distances (in points)
    # Only flag strikes that are AT or VERY CLOSE to psychological levels
    # One strike interval (50 points) away is considered safe
    MAJOR_LEVEL_DANGER_ZONE = 25  # Within 25 points of major level (1000s like 25000, 26000, 27000)
    INTERMEDIATE_LEVEL_DANGER_ZONE = 25  # Within 25 points of 500s (like 25500, 26500)
    MINOR_LEVEL_DANGER_ZONE = 25   # Within 25 points of 100s (like 24800, 24900, 25100)

    def __init__(self, spot_price: float, strike_interval: int = 50):
        """
        Initialize analyzer

        Args:
            spot_price: Current spot price
            strike_interval: Strike price interval (default: 50 for NIFTY)
        """
        self.spot_price = spot_price
        self.strike_interval = strike_interval
        self.analysis_results = []

    def analyze_strike(self, strike: int, option_type: str) -> Dict:
        """
        Analyze a strike for psychological level proximity

        Args:
            strike: Strike price to analyze
            option_type: 'CE' or 'PE'

        Returns:
            dict: Analysis result with adjustment recommendation
        """
        # Find nearest psychological levels
        levels = self._find_psychological_levels(strike)

        # Check if strike is in danger zone
        danger_analysis = self._check_danger_zone(strike, levels)

        # Recommend adjustment if needed
        recommendation = self._get_recommendation(
            strike, option_type, danger_analysis
        )

        result = {
            'strike': strike,
            'option_type': option_type,
            'nearest_levels': levels,
            'danger_analysis': danger_analysis,
            'recommendation': recommendation,
            'should_adjust': recommendation['adjust'],
            'adjusted_strike': recommendation['new_strike'] if recommendation['adjust'] else strike,
        }

        self.analysis_results.append(result)
        return result

    def _find_psychological_levels(self, strike: int) -> Dict:
        """
        Find nearest psychological levels to a strike

        Returns:
            dict: Nearest major, intermediate, and minor levels
        """
        # Major levels (1000s): 25000, 26000, 27000
        nearest_major_below = (strike // 1000) * 1000
        nearest_major_above = nearest_major_below + 1000

        # Intermediate levels (500s): 25500, 26500
        if strike % 1000 < 500:
            nearest_intermediate_below = (strike // 1000) * 1000
            nearest_intermediate_above = nearest_intermediate_below + 500
        else:
            nearest_intermediate_below = (strike // 1000) * 1000 + 500
            nearest_intermediate_above = nearest_intermediate_below + 500

        # Minor levels (100s): 25100, 25200, 25300
        nearest_minor_below = (strike // 100) * 100
        nearest_minor_above = nearest_minor_below + 100

        return {
            'major': {
                'below': nearest_major_below,
                'above': nearest_major_above,
                'distance_below': abs(strike - nearest_major_below),
                'distance_above': abs(nearest_major_above - strike),
            },
            'intermediate': {
                'below': nearest_intermediate_below,
                'above': nearest_intermediate_above,
                'distance_below': abs(strike - nearest_intermediate_below),
                'distance_above': abs(nearest_intermediate_above - strike),
            },
            'minor': {
                'below': nearest_minor_below,
                'above': nearest_minor_above,
                'distance_below': abs(strike - nearest_minor_below),
                'distance_above': abs(nearest_minor_above - strike),
            }
        }

    def _check_danger_zone(self, strike: int, levels: Dict) -> Dict:
        """
        Check if strike is EXACTLY at a psychological level (500 or 1000 multiples)

        Changed logic: Only flag if strike is EXACTLY at a round number,
        not based on proximity/danger zones.

        Returns:
            dict: Danger zone analysis
        """
        dangers = []

        # Check if EXACTLY at 1000 multiple (25000, 26000, 27000)
        if strike % 1000 == 0:
            dangers.append({
                'level': strike,
                'type': 'MAJOR',
                'position': 'EXACT',
                'distance': 0,
                'severity': 'HIGH'
            })
            logger.info(f"Strike {strike} is EXACTLY at 1000 multiple")

        # Check if EXACTLY at 500 multiple (but not 1000) - like 25500, 26500
        elif strike % 500 == 0:
            dangers.append({
                'level': strike,
                'type': 'INTERMEDIATE',
                'position': 'EXACT',
                'distance': 0,
                'severity': 'MEDIUM'
            })
            logger.info(f"Strike {strike} is EXACTLY at 500 multiple")

        # No need to check 100s - those are too granular for NIFTY options
        # (NIFTY strikes are in 50-point intervals, so 100s don't matter)

        return {
            'in_danger_zone': len(dangers) > 0,
            'dangers': dangers,
            'highest_severity': self._get_highest_severity(dangers) if dangers else None,
        }

    def _get_highest_severity(self, dangers: List[Dict]) -> str:
        """Get highest severity from danger list"""
        if any(d['severity'] == 'HIGH' for d in dangers):
            return 'HIGH'
        elif any(d['severity'] == 'MEDIUM' for d in dangers):
            return 'MEDIUM'
        else:
            return 'LOW'

    def _get_recommendation(self, strike: int, option_type: str, danger_analysis: Dict) -> Dict:
        """
        Get adjustment recommendation based on danger analysis

        Logic:
        - CALL strikes near psychological level: Move UP (further OTM)
        - PUT strikes near psychological level: Move DOWN (further OTM)
        - Adjust for ALL severity levels (HIGH, MEDIUM, LOW) to be conservative
        """
        if not danger_analysis['in_danger_zone']:
            return {
                'adjust': False,
                'reason': 'Strike is safe - not near any psychological level',
                'new_strike': strike,
            }

        # IMPORTANT: We adjust for ALL severities to be very conservative
        # Round numbers act as magnets for price action

        # Get the most critical danger
        critical_danger = next(
            (d for d in danger_analysis['dangers'] if d['severity'] == danger_analysis['highest_severity']),
            danger_analysis['dangers'][0]
        )

        # Determine adjustment direction
        if option_type == 'CE':
            # CALL option: Move UP (increase strike)
            new_strike = strike + self.strike_interval
            direction = 'UP'
            reason = f"CALL strike too close to {critical_danger['type']} level {critical_danger['level']} ({critical_danger['distance']} points). Moving UP to {new_strike} for safety."
        else:  # PE
            # PUT option: Move DOWN (decrease strike)
            new_strike = strike - self.strike_interval
            direction = 'DOWN'
            reason = f"PUT strike too close to {critical_danger['type']} level {critical_danger['level']} ({critical_danger['distance']} points). Moving DOWN to {new_strike} for safety."

        logger.info(f"Psychological level adjustment: {option_type} {strike} → {new_strike} ({reason})")

        return {
            'adjust': True,
            'direction': direction,
            'reason': reason,
            'critical_level': critical_danger['level'],
            'level_type': critical_danger['type'],
            'new_strike': new_strike,
        }

    def analyze_strangle(self, call_strike: int, put_strike: int) -> Dict:
        """
        Analyze both strikes of a strangle for psychological levels

        Args:
            call_strike: Call strike to analyze
            put_strike: Put strike to analyze

        Returns:
            dict: Complete analysis with recommendations
        """
        logger.info(f"Analyzing strangle for psychological levels: CE {call_strike}, PE {put_strike}")

        # Analyze call strike
        call_analysis = self.analyze_strike(call_strike, 'CE')

        # Analyze put strike
        put_analysis = self.analyze_strike(put_strike, 'PE')

        # Build summary
        adjustments_made = []
        if call_analysis['should_adjust']:
            adjustments_made.append(f"CALL: {call_strike} → {call_analysis['adjusted_strike']}")
        if put_analysis['should_adjust']:
            adjustments_made.append(f"PUT: {put_strike} → {put_analysis['adjusted_strike']}")

        summary = {
            'original_call': call_strike,
            'original_put': put_strike,
            'adjusted_call': call_analysis['adjusted_strike'],
            'adjusted_put': put_analysis['adjusted_strike'],
            'call_analysis': call_analysis,
            'put_analysis': put_analysis,
            'any_adjustments': call_analysis['should_adjust'] or put_analysis['should_adjust'],
            'adjustments_made': adjustments_made,
            'safety_verdict': self._get_safety_verdict(call_analysis, put_analysis),
        }

        # Log summary
        if summary['any_adjustments']:
            logger.warning(f"⚠️ Psychological level adjustments needed: {', '.join(adjustments_made)}")
        else:
            logger.info("✓ Strikes are safe from psychological levels")

        return summary

    def _get_safety_verdict(self, call_analysis: Dict, put_analysis: Dict) -> str:
        """Get overall safety verdict"""
        if not call_analysis['should_adjust'] and not put_analysis['should_adjust']:
            return "SAFE: Both strikes clear of psychological levels"

        if call_analysis['should_adjust'] and put_analysis['should_adjust']:
            return "BOTH ADJUSTED: Both strikes moved away from psychological levels for safety"

        if call_analysis['should_adjust']:
            return f"CALL ADJUSTED: Call strike moved to safer level"

        return f"PUT ADJUSTED: Put strike moved to safer level"


def check_psychological_levels(call_strike: int, put_strike: int, spot_price: float) -> Dict:
    """
    Convenience function to check strikes for psychological levels

    Args:
        call_strike: Call strike price
        put_strike: Put strike price
        spot_price: Current spot price

    Returns:
        dict: Complete analysis with adjusted strikes
    """
    analyzer = PsychologicalLevelAnalyzer(spot_price)
    return analyzer.analyze_strangle(call_strike, put_strike)
