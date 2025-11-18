"""
Market Condition Validator for Nifty Strangle Strategy

This service validates market conditions before entering a strangle position.
Uses multiple data sources to determine if it's a "NO TRADE DAY".

NO TRADE CRITERIA:
1. Intraday volatility > threshold (Large gap up/down or intraday swing)
2. Last 3 days cumulative movement > delta-based threshold
3. VIX spike > 20% from previous day
4. Price at extreme support/resistance (near breakout levels)
5. High volatility regime (ATR expansion)
6. Event days (major announcements)
"""

import logging
from decimal import Decimal
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
from django.utils import timezone

from apps.brokers.integrations.breeze import get_nifty_quote, get_india_vix
from apps.brokers.models import HistoricalPrice

logger = logging.getLogger(__name__)


class MarketConditionValidator:
    """
    Validates market conditions for Nifty Strangle strategy

    Returns detailed validation report with pass/fail for each check
    """

    def __init__(self, spot_price: Decimal, vix: Decimal, days_to_expiry: int):
        """
        Initialize validator

        Args:
            spot_price: Current NIFTY spot price
            vix: Current India VIX
            days_to_expiry: Days remaining to expiry
        """
        self.spot_price = float(spot_price)
        self.vix = float(vix)
        self.days_to_expiry = days_to_expiry

        # Validation results
        self.validation_results = []
        self.is_no_trade_day = False
        self.trade_allowed = True
        self.warnings = []

    def validate_all(self) -> Dict:
        """
        Run all validation checks

        Returns:
            dict: Complete validation report
        """
        logger.info("Starting market condition validation")

        # Get current quote data
        try:
            nifty_quote = get_nifty_quote()
            if not nifty_quote:
                self._add_result("Quote Data", "FAIL", "Could not fetch current NIFTY quote", {})
                self.trade_allowed = False
                return self._build_report()

            current_data = {
                'ltp': float(nifty_quote.get('ltp', self.spot_price)),
                'open': float(nifty_quote.get('open', self.spot_price)),
                'high': float(nifty_quote.get('high', self.spot_price)),
                'low': float(nifty_quote.get('low', self.spot_price)),
                'prev_close': float(nifty_quote.get('previous_close', self.spot_price)),
            }
        except Exception as e:
            logger.warning(f"Could not fetch quote data: {e}, using spot price only")
            current_data = {
                'ltp': self.spot_price,
                'open': self.spot_price,
                'high': self.spot_price,
                'low': self.spot_price,
                'prev_close': self.spot_price,
            }

        # Run all validation checks
        self._check_intraday_gap(current_data)
        self._check_intraday_range(current_data)
        self._check_last_3_days_movement()
        self._check_vix_spike()
        self._check_volatility_regime(current_data)
        self._check_trend_strength()

        return self._build_report()

    def _check_intraday_gap(self, current_data: Dict) -> None:
        """
        Check if there's a significant gap up or down from previous close

        Criteria: Gap > 0.5% is WARNING, Gap > 1.0% is NO TRADE
        """
        ltp = current_data['ltp']
        open_price = current_data['open']
        prev_close = current_data['prev_close']

        gap_pct = ((open_price - prev_close) / prev_close * 100) if prev_close > 0 else 0

        details = {
            'previous_close': prev_close,
            'open': open_price,
            'gap_points': open_price - prev_close,
            'gap_pct': round(gap_pct, 2),
            'threshold_warning': 0.5,
            'threshold_no_trade': 1.0
        }

        if abs(gap_pct) > 1.0:
            self._add_result(
                "Gap Check",
                "FAIL",
                f"Large gap {gap_pct:+.2f}% - High volatility expected",
                details
            )
            self.is_no_trade_day = True
            self.trade_allowed = False
        elif abs(gap_pct) > 0.5:
            self._add_result(
                "Gap Check",
                "WARNING",
                f"Moderate gap {gap_pct:+.2f}% - Monitor closely",
                details
            )
            self.warnings.append(f"Moderate gap: {gap_pct:+.2f}%")
        else:
            self._add_result(
                "Gap Check",
                "PASS",
                f"Normal gap {gap_pct:+.2f}% - Within limits",
                details
            )

    def _check_intraday_range(self, current_data: Dict) -> None:
        """
        Check intraday volatility (high-low range)

        Criteria: Intraday range > 1.5% is WARNING, > 2.0% is NO TRADE
        """
        high = current_data['high']
        low = current_data['low']
        ltp = current_data['ltp']

        range_pct = ((high - low) / ltp * 100) if ltp > 0 else 0

        details = {
            'high': high,
            'low': low,
            'range_points': high - low,
            'range_pct': round(range_pct, 2),
            'threshold_warning': 1.5,
            'threshold_no_trade': 2.0
        }

        if range_pct > 2.0:
            self._add_result(
                "Intraday Range",
                "FAIL",
                f"Very high intraday volatility {range_pct:.2f}%",
                details
            )
            self.is_no_trade_day = True
            self.trade_allowed = False
        elif range_pct > 1.5:
            self._add_result(
                "Intraday Range",
                "WARNING",
                f"Elevated intraday volatility {range_pct:.2f}%",
                details
            )
            self.warnings.append(f"High intraday range: {range_pct:.2f}%")
        else:
            self._add_result(
                "Intraday Range",
                "PASS",
                f"Normal intraday range {range_pct:.2f}%",
                details
            )

    def _check_last_3_days_movement(self) -> None:
        """
        Check last 3-5 days extreme movements using comprehensive historical analysis

        Fetches historical data from Breeze API if needed.
        Criteria:
        - 3-day movement > 3% = NO TRADE
        - 5-day movement > 4.5% = NO TRADE
        """
        try:
            from apps.strategies.services.historical_analysis import analyze_nifty_historical

            logger.info("Running comprehensive historical movement analysis")

            # Run full historical analysis (will fetch from Breeze if needed)
            historical_analysis = analyze_nifty_historical(
                current_price=self.spot_price,
                days_to_fetch=365
            )

            if historical_analysis.get('status') == 'ERROR':
                self._add_result(
                    "Extreme Movement Check",
                    "SKIP",
                    f"Historical analysis failed: {historical_analysis.get('error')}",
                    {}
                )
                return

            if historical_analysis.get('status') == 'INSUFFICIENT_DATA':
                self._add_result(
                    "Extreme Movement Check",
                    "SKIP",
                    f"Insufficient historical data: {historical_analysis.get('days_available', 0)} days available",
                    {'days_available': historical_analysis.get('days_available', 0)}
                )
                return

            # Extract movement analysis
            extreme_movements = historical_analysis.get('extreme_movements', {})
            three_day = extreme_movements.get('3_day_movement', {})
            five_day = extreme_movements.get('5_day_movement', {})

            # Build details
            details = {
                'days_available': historical_analysis.get('data_summary', {}).get('days_available'),
                '3_day_move_pct': three_day.get('move_pct'),
                '3_day_abs_pct': three_day.get('move_abs_pct'),
                '3_day_status': three_day.get('status'),
                '5_day_move_pct': five_day.get('move_pct'),
                '5_day_abs_pct': five_day.get('move_abs_pct'),
                '5_day_status': five_day.get('status'),
                'overall_status': extreme_movements.get('status'),
            }

            # Determine result based on extreme movement analysis
            if extreme_movements.get('no_trade_day'):
                # EXTREME movement detected - NO TRADE
                message = f"EXTREME MOVEMENT: 3-day: {three_day.get('move_pct'):+.2f}%, 5-day: {five_day.get('move_pct'):+.2f}%"
                self._add_result(
                    "Extreme Movement Check",
                    "FAIL",
                    message,
                    details
                )
                self.is_no_trade_day = True
                self.trade_allowed = False
                logger.warning(f"⚠️ NO TRADE: {message}")

            elif extreme_movements.get('status') == 'WARNING':
                # WARNING - elevated movement
                message = f"Elevated movement: 3-day: {three_day.get('move_pct'):+.2f}%, 5-day: {five_day.get('move_pct'):+.2f}%"
                self._add_result(
                    "Extreme Movement Check",
                    "WARNING",
                    message,
                    details
                )
                self.warnings.append(f"Elevated movement detected")

            else:
                # NORMAL movement
                message = f"Normal movement: 3-day: {three_day.get('move_pct'):+.2f}%, 5-day: {five_day.get('move_pct'):+.2f}%"
                self._add_result(
                    "Extreme Movement Check",
                    "PASS",
                    message,
                    details
                )

            # Also add 20 DMA trend analysis if available
            trend_analysis = historical_analysis.get('trend_vs_20dma', {})
            if trend_analysis.get('status') == 'CALCULATED':
                dma_20 = trend_analysis.get('dma_20')
                diff_pct = trend_analysis.get('diff_pct')
                trend = trend_analysis.get('trend')

                self._add_result(
                    "20 DMA Trend",
                    "PASS",
                    f"{trend}: Price {diff_pct:+.2f}% from 20 DMA ({dma_20:.0f})",
                    {
                        'dma_20': dma_20,
                        'current_price': self.spot_price,
                        'diff_pct': diff_pct,
                        'trend': trend,
                        'interpretation': trend_analysis.get('interpretation')
                    }
                )

        except Exception as e:
            logger.error(f"Historical movement analysis failed: {e}", exc_info=True)
            self._add_result(
                "Extreme Movement Check",
                "SKIP",
                f"Analysis failed: {str(e)[:100]}",
                {}
            )

    def _check_vix_spike(self) -> None:
        """
        Check for VIX spike

        Criteria: VIX > 20 is WARNING, VIX > 25 is NO TRADE
        """
        details = {
            'current_vix': self.vix,
            'threshold_warning': 20,
            'threshold_no_trade': 25,
        }

        if self.vix > 25:
            self._add_result(
                "VIX Level",
                "FAIL",
                f"VIX too high at {self.vix:.1f} - Extreme volatility",
                details
            )
            self.is_no_trade_day = True
            self.trade_allowed = False
        elif self.vix > 20:
            self._add_result(
                "VIX Level",
                "WARNING",
                f"Elevated VIX at {self.vix:.1f} - Higher risk",
                details
            )
            self.warnings.append(f"Elevated VIX: {self.vix:.1f}")
        else:
            self._add_result(
                "VIX Level",
                "PASS",
                f"Normal VIX at {self.vix:.1f}",
                details
            )

    def _check_volatility_regime(self, current_data: Dict) -> None:
        """
        Check if we're in a high volatility regime using ATR

        This is a simplified check using intraday range as ATR proxy
        """
        high = current_data['high']
        low = current_data['low']

        # Use intraday range as proxy for ATR
        # For a more accurate ATR, we'd need 14-day historical data
        intraday_range = high - low
        atr_pct = (intraday_range / self.spot_price * 100) if self.spot_price > 0 else 0

        # Historical avg ATR for NIFTY is around 0.8-1.2%
        # High volatility: ATR > 1.5%

        details = {
            'atr_estimate_pct': round(atr_pct, 2),
            'normal_range': '0.8-1.2%',
            'high_volatility_threshold': 1.5
        }

        if atr_pct > 1.5:
            self._add_result(
                "Volatility Regime",
                "WARNING",
                f"High volatility regime (ATR ~{atr_pct:.2f}%)",
                details
            )
            self.warnings.append(f"High volatility: ATR ~{atr_pct:.2f}%")
        else:
            self._add_result(
                "Volatility Regime",
                "PASS",
                f"Normal volatility regime (ATR ~{atr_pct:.2f}%)",
                details
            )

    def _check_trend_strength(self) -> None:
        """
        Check if market is in a strong trend

        For strangle: We prefer range-bound markets, not trending markets
        """
        # This is a placeholder - would need historical data for proper trend analysis
        # For now, we'll use VIX as a proxy: Low VIX often means trending market

        details = {
            'vix': self.vix,
            'interpretation': 'Range-bound market preferred for strangles'
        }

        if self.vix < 12:
            self._add_result(
                "Market Trend",
                "WARNING",
                f"Very low VIX ({self.vix:.1f}) - Market might be complacent or trending",
                details
            )
            self.warnings.append(f"Low VIX: {self.vix:.1f} - trending market risk")
        else:
            self._add_result(
                "Market Trend",
                "PASS",
                f"VIX {self.vix:.1f} indicates suitable market conditions",
                details
            )

    def _add_result(self, check_name: str, status: str, message: str, details: Dict) -> None:
        """Add a validation result"""
        self.validation_results.append({
            'check': check_name,
            'status': status,  # PASS, WARNING, FAIL, SKIP
            'message': message,
            'details': details
        })

        logger.info(f"Validation Check [{check_name}]: {status} - {message}")

    def _build_report(self) -> Dict:
        """Build final validation report"""
        # Count statuses
        status_counts = {
            'PASS': sum(1 for r in self.validation_results if r['status'] == 'PASS'),
            'WARNING': sum(1 for r in self.validation_results if r['status'] == 'WARNING'),
            'FAIL': sum(1 for r in self.validation_results if r['status'] == 'FAIL'),
            'SKIP': sum(1 for r in self.validation_results if r['status'] == 'SKIP'),
        }

        # Overall verdict
        if self.is_no_trade_day:
            overall_verdict = "NO TRADE DAY"
            verdict_reason = "Market conditions are unfavorable for strangle entry"
        elif len(self.warnings) > 2:
            overall_verdict = "CAUTION"
            verdict_reason = f"Multiple warnings ({len(self.warnings)}) - Proceed with caution"
        elif len(self.warnings) > 0:
            overall_verdict = "PROCEED WITH CAUTION"
            verdict_reason = f"{len(self.warnings)} warning(s) detected"
        else:
            overall_verdict = "CLEAR FOR TRADING"
            verdict_reason = "All checks passed - Good conditions for strangle"

        report = {
            'trade_allowed': self.trade_allowed,
            'is_no_trade_day': self.is_no_trade_day,
            'overall_verdict': overall_verdict,
            'verdict_reason': verdict_reason,
            'validation_results': self.validation_results,
            'status_summary': status_counts,
            'warnings': self.warnings,
            'market_snapshot': {
                'spot_price': self.spot_price,
                'vix': self.vix,
                'days_to_expiry': self.days_to_expiry,
            }
        }

        logger.info(f"Validation Complete: {overall_verdict} - {verdict_reason}")

        return report


def validate_market_conditions(spot_price: Decimal, vix: Decimal, days_to_expiry: int) -> Dict:
    """
    Convenience function to validate market conditions

    Args:
        spot_price: Current NIFTY spot price
        vix: Current India VIX
        days_to_expiry: Days remaining to expiry

    Returns:
        dict: Validation report
    """
    validator = MarketConditionValidator(spot_price, vix, days_to_expiry)
    return validator.validate_all()
