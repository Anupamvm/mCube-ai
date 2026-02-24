"""
Analyst Report Aggregator Service

Aggregates analyst data and implements trade blocking rules:
- Rule 1: Block LONG trade if average target price upside < 8%
- Rule 2: Block if >= 10% of reports (min 2) recommend "Sell"

This service is used in the trade verification flow to check
analyst sentiment before allowing trades.
"""

import logging
from typing import Dict, List, Optional
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


class AnalystReportAggregator:
    """
    Aggregates analyst reports and price targets for trade verification.

    Implements blocking rules:
    1. Block LONG if avg target upside < 8%
    2. Block if >= 10% of reports (min 2) recommend Sell
    """

    # Trade blocking thresholds
    MIN_UPSIDE_PCT = 8.0  # Minimum upside to allow LONG trade
    SELL_RECOMMENDATION_PCT = 10.0  # Max percentage of sell recommendations allowed
    MIN_SELL_COUNT_TO_BLOCK = 2  # Minimum sell reports to trigger block

    # Data freshness threshold
    DATA_STALE_HOURS = 24  # Refetch if data is older than this

    def __init__(self):
        """Initialize aggregator"""

    def get_price_target(self, symbol: str, nse_code: str = None) -> Optional[Dict]:
        """
        Get latest price target data for a stock.

        Args:
            symbol: Stock symbol
            nse_code: NSE code (optional, defaults to symbol)

        Returns:
            Dict with price target data or None
        """
        from apps.data.models import AnalystPriceTarget

        nse_code = nse_code or symbol

        try:
            # Get most recent price target
            price_target = AnalystPriceTarget.objects.filter(
                nse_code__iexact=nse_code
            ).order_by('-fetch_timestamp').first()

            if not price_target:
                price_target = AnalystPriceTarget.objects.filter(
                    symbol__iexact=symbol
                ).order_by('-fetch_timestamp').first()

            if price_target:
                return {
                    'symbol': price_target.symbol,
                    'current_price': float(price_target.current_price) if price_target.current_price else None,
                    'avg_target_price': float(price_target.avg_target_price) if price_target.avg_target_price else None,
                    'upside_pct': float(price_target.upside_pct) if price_target.upside_pct else None,
                    'analyst_count': price_target.analyst_count,
                    'strong_buy_count': price_target.strong_buy_count,
                    'buy_count': price_target.buy_count,
                    'hold_count': price_target.hold_count,
                    'sell_count': price_target.sell_count,
                    'strong_sell_count': price_target.strong_sell_count,
                    'fetch_timestamp': price_target.fetch_timestamp,
                    'is_stale': self._is_data_stale(price_target.fetch_timestamp),
                }

            return None

        except Exception as e:
            logger.error(f"Error getting price target for {symbol}: {e}")
            return None

    def get_recent_reports(
        self,
        symbol: str,
        nse_code: str = None,
        months_back: int = 3
    ) -> List[Dict]:
        """
        Get recent analyst reports for a stock.

        Args:
            symbol: Stock symbol
            nse_code: NSE code (optional)
            months_back: Number of months to look back

        Returns:
            List of report dicts
        """
        from apps.data.models import AnalystReport

        nse_code = nse_code or symbol
        cutoff_date = timezone.now().date() - timedelta(days=months_back * 30)

        try:
            reports = AnalystReport.objects.filter(
                nse_code__iexact=nse_code,
                report_date__gte=cutoff_date
            ).order_by('-report_date')

            if not reports.exists():
                reports = AnalystReport.objects.filter(
                    symbol__iexact=symbol,
                    report_date__gte=cutoff_date
                ).order_by('-report_date')

            return [
                {
                    'id': r.id,
                    'symbol': r.symbol,
                    'report_date': r.report_date,
                    'author': r.author,
                    'target_price': float(r.target_price) if r.target_price else None,
                    'upside_pct': float(r.upside_pct) if r.upside_pct else None,
                    'recommendation_type': r.recommendation_type,
                    'llm_summary': r.llm_summary,
                    'sentiment_score': r.sentiment_score,
                    'trade_recommendation': r.trade_recommendation,
                    'risk_factors': r.risk_factors,
                    'catalysts': r.catalysts,
                    'llm_processed': r.llm_processed,
                }
                for r in reports
            ]

        except Exception as e:
            logger.error(f"Error getting reports for {symbol}: {e}")
            return []

    def _is_data_stale(self, fetch_timestamp) -> bool:
        """Check if data is stale (older than threshold)"""
        if not fetch_timestamp:
            return True
        stale_cutoff = timezone.now() - timedelta(hours=self.DATA_STALE_HOURS)
        return fetch_timestamp < stale_cutoff

    def _check_upside_rule(self, price_target: Dict, direction: str) -> Dict:
        """
        Check Rule 1: Block LONG if upside < 8%

        Args:
            price_target: Price target data dict
            direction: Trade direction ('LONG' or 'SHORT')

        Returns:
            Dict with rule check result
        """
        result = {
            'rule': 'UPSIDE_CHECK',
            'passed': True,
            'reason': None,
            'details': {}
        }

        # Only applies to LONG trades
        if direction.upper() != 'LONG':
            result['reason'] = 'Rule only applies to LONG trades'
            return result

        if not price_target:
            result['reason'] = 'No price target data available'
            return result

        upside_pct = price_target.get('upside_pct')
        if upside_pct is None:
            result['reason'] = 'Upside percentage not available'
            return result

        result['details'] = {
            'upside_pct': upside_pct,
            'threshold': self.MIN_UPSIDE_PCT,
            'avg_target_price': price_target.get('avg_target_price'),
            'current_price': price_target.get('current_price'),
            'analyst_count': price_target.get('analyst_count', 0),
        }

        if upside_pct < self.MIN_UPSIDE_PCT:
            result['passed'] = False
            result['reason'] = (
                f"Average analyst target upside ({upside_pct:.1f}%) is below "
                f"minimum threshold ({self.MIN_UPSIDE_PCT}%)"
            )
        else:
            result['reason'] = f"Target upside ({upside_pct:.1f}%) meets threshold"

        return result

    def _check_sell_recommendation_rule(self, price_target: Dict, reports: List[Dict]) -> Dict:
        """
        Check Rule 2: Block if >= 10% of recommendations are Sell (min 2)

        Args:
            price_target: Price target data dict
            reports: List of recent reports

        Returns:
            Dict with rule check result
        """
        result = {
            'rule': 'SELL_RECOMMENDATION_CHECK',
            'passed': True,
            'reason': None,
            'details': {}
        }

        # Count sell recommendations from price target
        sell_count = 0
        total_count = 0

        if price_target:
            sell_count = (
                price_target.get('sell_count', 0) +
                price_target.get('strong_sell_count', 0)
            )
            total_count = price_target.get('analyst_count', 0)

        # Also count from recent reports if available
        report_sell_count = sum(
            1 for r in reports
            if r.get('recommendation_type') in ['SELL', 'STRONG_SELL']
        )

        # Use the larger count
        if len(reports) > total_count:
            sell_count = report_sell_count
            total_count = len(reports)

        result['details'] = {
            'sell_count': sell_count,
            'total_count': total_count,
            'sell_pct': (sell_count / total_count * 100) if total_count > 0 else 0,
            'threshold_pct': self.SELL_RECOMMENDATION_PCT,
            'min_sell_to_block': self.MIN_SELL_COUNT_TO_BLOCK,
        }

        # Check rule: >= 10% sell AND at least 2 sell recommendations
        if total_count > 0:
            sell_pct = (sell_count / total_count) * 100
            result['details']['sell_pct'] = sell_pct

            if sell_count >= self.MIN_SELL_COUNT_TO_BLOCK and sell_pct >= self.SELL_RECOMMENDATION_PCT:
                result['passed'] = False
                result['reason'] = (
                    f"{sell_count} of {total_count} analysts ({sell_pct:.1f}%) recommend Sell - "
                    f"exceeds {self.SELL_RECOMMENDATION_PCT}% threshold"
                )
            else:
                result['reason'] = f"Sell recommendations ({sell_pct:.1f}%) within acceptable range"
        else:
            result['reason'] = "No analyst data available"

        return result

    def aggregate_for_trade(
        self,
        symbol: str,
        direction: str,
        current_price: float = None,
        nse_code: str = None,
        refresh_if_stale: bool = True
    ) -> Dict:
        """
        Aggregate analyst data and check trade blocking rules.

        Args:
            symbol: Stock symbol
            direction: Trade direction ('LONG' or 'SHORT')
            current_price: Current stock price (for context)
            nse_code: NSE code (optional)
            refresh_if_stale: Whether to trigger refresh if data is stale

        Returns:
            Dict with:
                - trade_allowed: bool
                - blocking_reasons: List of reasons if blocked
                - warnings: List of warnings (non-blocking)
                - price_target: Price target data
                - reports_summary: Summary of recent reports
                - top_blocking_reports: Reports that contribute to blocking
                - recommendation: Overall recommendation
        """
        nse_code = nse_code or symbol
        direction = direction.upper()

        result = {
            'trade_allowed': True,
            'blocking_reasons': [],
            'warnings': [],
            'price_target': None,
            'reports_summary': None,
            'top_blocking_reports': [],
            'recommendation': 'PROCEED',
            'rules_checked': [],
        }

        try:
            # Get price target data
            price_target = self.get_price_target(symbol, nse_code)
            result['price_target'] = price_target

            # Check if data is stale
            if price_target and price_target.get('is_stale'):
                result['warnings'].append(
                    f"Analyst data is more than {self.DATA_STALE_HOURS} hours old"
                )
                if refresh_if_stale:
                    # Trigger async refresh (don't block on it)
                    self._trigger_data_refresh(symbol, nse_code)

            # Get recent reports
            reports = self.get_recent_reports(symbol, nse_code)

            # Build reports summary
            if reports:
                bullish_count = sum(1 for r in reports if r.get('recommendation_type') in ['BUY', 'STRONG_BUY'])
                bearish_count = sum(1 for r in reports if r.get('recommendation_type') in ['SELL', 'STRONG_SELL'])
                hold_count = sum(1 for r in reports if r.get('recommendation_type') == 'HOLD')

                # Calculate average sentiment from LLM analysis
                sentiment_scores = [r['sentiment_score'] for r in reports if r.get('sentiment_score') is not None]
                avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0

                result['reports_summary'] = {
                    'total_reports': len(reports),
                    'bullish_count': bullish_count,
                    'bearish_count': bearish_count,
                    'hold_count': hold_count,
                    'avg_sentiment_score': round(avg_sentiment, 2),
                    'llm_processed_count': sum(1 for r in reports if r.get('llm_processed')),
                }

            # Check Rule 1: Upside threshold
            upside_result = self._check_upside_rule(price_target, direction)
            result['rules_checked'].append(upside_result)

            if not upside_result['passed']:
                result['trade_allowed'] = False
                result['blocking_reasons'].append(upside_result['reason'])

            # Check Rule 2: Sell recommendation percentage
            sell_result = self._check_sell_recommendation_rule(price_target, reports)
            result['rules_checked'].append(sell_result)

            if not sell_result['passed']:
                result['trade_allowed'] = False
                result['blocking_reasons'].append(sell_result['reason'])

            # Collect blocking reports (sell recommendations)
            blocking_reports = [
                r for r in reports
                if r.get('recommendation_type') in ['SELL', 'STRONG_SELL']
            ]
            result['top_blocking_reports'] = blocking_reports[:5]  # Top 5

            # Set overall recommendation
            if not result['trade_allowed']:
                result['recommendation'] = 'BLOCK'
            elif result['warnings']:
                result['recommendation'] = 'PROCEED_WITH_CAUTION'
            else:
                result['recommendation'] = 'PROCEED'

            # Log summary
            logger.info(
                f"Analyst verification for {symbol} {direction}: "
                f"allowed={result['trade_allowed']}, "
                f"blocking_reasons={len(result['blocking_reasons'])}, "
                f"reports={len(reports)}"
            )

            return result

        except Exception as e:
            logger.error(f"Error aggregating analyst data for {symbol}: {e}", exc_info=True)
            # Don't block on errors - return proceed with warning
            result['warnings'].append(f"Error checking analyst data: {str(e)}")
            result['recommendation'] = 'PROCEED_WITH_CAUTION'
            return result

    def _trigger_data_refresh(self, symbol: str, nse_code: str):
        """
        Trigger async refresh of analyst data.

        Args:
            symbol: Stock symbol
            nse_code: NSE code
        """
        try:
            from apps.data.tasks import fetch_analyst_reports_for_stock
            # Queue async task (don't wait for result)
            fetch_analyst_reports_for_stock.delay(symbol, nse_code)
            logger.info(f"Triggered async analyst data refresh for {symbol}")
        except Exception as e:
            logger.warning(f"Could not trigger async refresh for {symbol}: {e}")


# Global instance
_analyst_report_aggregator = None


def get_analyst_report_aggregator() -> AnalystReportAggregator:
    """Get or create global AnalystReportAggregator instance"""
    global _analyst_report_aggregator

    if _analyst_report_aggregator is None:
        _analyst_report_aggregator = AnalystReportAggregator()

    return _analyst_report_aggregator


def aggregate_analyst_data_for_trade(
    symbol: str,
    direction: str,
    current_price: float = None,
    nse_code: str = None
) -> Dict:
    """
    Convenience function to aggregate analyst data for trade verification.

    Args:
        symbol: Stock symbol
        direction: Trade direction ('LONG' or 'SHORT')
        current_price: Current stock price
        nse_code: NSE code

    Returns:
        Dict with trade_allowed, blocking_reasons, price_target, etc.
    """
    aggregator = get_analyst_report_aggregator()
    return aggregator.aggregate_for_trade(
        symbol=symbol,
        direction=direction,
        current_price=current_price,
        nse_code=nse_code
    )
