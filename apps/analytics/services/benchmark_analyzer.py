"""
Benchmark Analyzer Service for mCube Trading System

Provides benchmark comparison and alpha/beta calculations:
- Fetch benchmark data (Nifty/BankNifty) from Breeze API
- Calculate portfolio beta vs benchmark
- Calculate alpha (excess return)
- Performance comparison vs benchmark
"""

import logging
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import numpy as np
from django.db import transaction
from django.db.models import Avg, Sum
from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.analytics.models import (
    BenchmarkData,
    PortfolioBeta,
    DailyEquityCurve,
)

logger = logging.getLogger(__name__)


class BenchmarkAnalyzer:
    """
    Service for benchmark comparison and alpha/beta calculations.
    """

    # Risk-free rate (Indian T-bill rate)
    RISK_FREE_RATE = Decimal('0.065')  # 6.5% annual

    # Trading days per year
    TRADING_DAYS_PER_YEAR = 252

    # Period to days mapping
    PERIOD_DAYS = {
        '30D': 30,
        '60D': 60,
        '90D': 90,
        '180D': 180,
        '1Y': 365,
        'ALL': None,  # All available data
    }

    def fetch_benchmark_data(
        self,
        benchmark: str,
        from_date: date,
        to_date: date,
    ) -> int:
        """
        Fetch and store benchmark OHLC data from Breeze API.

        Args:
            benchmark: One of NIFTY50, BANKNIFTY, NIFTYIT
            from_date: Start date
            to_date: End date

        Returns:
            int: Number of records created/updated
        """
        try:
            from apps.brokers.integrations.breeze import get_breeze_client

            client = get_breeze_client()
            if not client:
                logger.warning("Breeze client not available")
                return 0

            # Map benchmark to Breeze stock code
            stock_code_map = {
                'NIFTY50': 'NIFTY',
                'BANKNIFTY': 'BANKNIFTY',
                'NIFTYIT': 'NIFTYIT',
            }

            stock_code = stock_code_map.get(benchmark, 'NIFTY')

            # Fetch historical data
            historical_data = client.get_historical_data_v2(
                interval='1day',
                from_date=from_date.strftime('%Y-%m-%dT07:00:00.000Z'),
                to_date=to_date.strftime('%Y-%m-%dT07:00:00.000Z'),
                stock_code=stock_code,
                exchange_code='NSE',
                product_type='cash',
            )

            if not historical_data or 'Success' not in historical_data:
                logger.warning(f"No historical data returned for {benchmark}")
                return 0

            records = historical_data.get('Success', [])
            created_count = 0
            prev_close = None

            for record in records:
                try:
                    record_date = datetime.strptime(
                        record['datetime'].split('T')[0],
                        '%Y-%m-%d'
                    ).date()

                    open_price = Decimal(str(record['open']))
                    high_price = Decimal(str(record['high']))
                    low_price = Decimal(str(record['low']))
                    close_price = Decimal(str(record['close']))
                    volume = record.get('volume')

                    # Calculate daily return
                    daily_return = None
                    if prev_close and prev_close > 0:
                        daily_return = ((close_price - prev_close) / prev_close) * 100

                    # Store/update record
                    BenchmarkData.objects.update_or_create(
                        benchmark=benchmark,
                        date=record_date,
                        defaults={
                            'open': open_price,
                            'high': high_price,
                            'low': low_price,
                            'close': close_price,
                            'volume': volume,
                            'daily_return_pct': daily_return,
                        }
                    )

                    prev_close = close_price
                    created_count += 1

                except Exception as e:
                    logger.error(f"Error processing record: {e}")
                    continue

            # Update cumulative returns from FY start
            self._update_cumulative_returns(benchmark)

            logger.info(f"Fetched {created_count} benchmark records for {benchmark}")
            return created_count

        except ImportError:
            logger.warning("Breeze client not available")
            return 0
        except Exception as e:
            logger.error(f"Error fetching benchmark data: {e}", exc_info=True)
            return 0

    def _update_cumulative_returns(self, benchmark: str):
        """Update cumulative returns from FY start for benchmark."""
        try:
            # Get current FY start
            today = date.today()
            if today.month >= 4:
                fy_start = date(today.year, 4, 1)
            else:
                fy_start = date(today.year - 1, 4, 1)

            # Get data from FY start
            records = BenchmarkData.objects.filter(
                benchmark=benchmark,
                date__gte=fy_start,
            ).order_by('date')

            if not records.exists():
                return

            # Get first close as base
            first_record = records.first()
            base_close = first_record.close

            # Calculate cumulative return for each date
            for record in records:
                if base_close and base_close > 0:
                    cumulative_return = ((record.close - base_close) / base_close) * 100
                    record.cumulative_return_pct = cumulative_return
                    record.save(update_fields=['cumulative_return_pct'])

        except Exception as e:
            logger.error(f"Error updating cumulative returns: {e}")

    @transaction.atomic
    def calculate_beta(
        self,
        account: BrokerAccount,
        benchmark: str = 'NIFTY50',
        period_days: int = 90,
    ) -> Optional[PortfolioBeta]:
        """
        Calculate portfolio beta vs benchmark.

        Beta measures portfolio volatility relative to market.
        Beta > 1: More volatile than market
        Beta < 1: Less volatile than market
        Beta = 1: Same as market

        Args:
            account: The broker account
            benchmark: Benchmark to compare against
            period_days: Number of days to use for calculation

        Returns:
            PortfolioBeta: The calculated beta record
        """
        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=period_days)

            # Get portfolio daily returns
            equity_curves = DailyEquityCurve.objects.filter(
                account=account,
                date__gte=start_date,
                date__lte=end_date,
            ).order_by('date')

            # Get benchmark daily returns
            benchmark_data = BenchmarkData.objects.filter(
                benchmark=benchmark,
                date__gte=start_date,
                date__lte=end_date,
            ).order_by('date')

            if equity_curves.count() < 20 or benchmark_data.count() < 20:
                logger.warning(f"Insufficient data for beta calculation ({equity_curves.count()} portfolio, {benchmark_data.count()} benchmark)")
                return None

            # Build aligned returns series
            portfolio_returns = {}
            benchmark_returns = {}

            for curve in equity_curves:
                if curve.opening_capital and curve.opening_capital > 0:
                    ret = float(curve.total_pnl / curve.opening_capital)
                    portfolio_returns[curve.date] = ret

            for data in benchmark_data:
                if data.daily_return_pct is not None:
                    benchmark_returns[data.date] = float(data.daily_return_pct) / 100

            # Align dates
            common_dates = set(portfolio_returns.keys()) & set(benchmark_returns.keys())

            if len(common_dates) < 20:
                logger.warning(f"Only {len(common_dates)} common dates for beta calculation")
                return None

            sorted_dates = sorted(common_dates)
            port_rets = [portfolio_returns[d] for d in sorted_dates]
            bench_rets = [benchmark_returns[d] for d in sorted_dates]

            # Calculate beta using regression
            port_arr = np.array(port_rets)
            bench_arr = np.array(bench_rets)

            # Beta = Cov(portfolio, benchmark) / Var(benchmark)
            covariance = np.cov(port_arr, bench_arr)[0, 1]
            variance = np.var(bench_arr, ddof=1)

            if variance == 0:
                logger.warning("Zero variance in benchmark returns")
                return None

            beta = covariance / variance

            # Calculate correlation
            correlation = np.corrcoef(port_arr, bench_arr)[0, 1]
            r_squared = correlation ** 2

            # Calculate returns for the period
            portfolio_return = sum(port_rets) * 100
            benchmark_return = sum(bench_rets) * 100

            # Calculate alpha using CAPM
            # Alpha = Portfolio Return - (Risk-free rate + Beta * (Market Return - Risk-free rate))
            daily_rf = float(self.RISK_FREE_RATE) / self.TRADING_DAYS_PER_YEAR
            annualized_rf = float(self.RISK_FREE_RATE) * 100

            period_rf = annualized_rf * (period_days / 365)
            alpha = portfolio_return - (period_rf + beta * (benchmark_return - period_rf))

            excess_return = portfolio_return - benchmark_return

            # Determine period type
            period_type = self._days_to_period_type(period_days)

            # Create/update beta record
            beta_record, created = PortfolioBeta.objects.update_or_create(
                account=account,
                benchmark=benchmark,
                period_type=period_type,
                calculation_date=end_date,
                defaults={
                    'beta': Decimal(str(round(beta, 4))),
                    'alpha': Decimal(str(round(alpha, 4))),
                    'r_squared': Decimal(str(round(r_squared, 4))),
                    'correlation': Decimal(str(round(correlation, 4))),
                    'portfolio_return': Decimal(str(round(portfolio_return, 4))),
                    'benchmark_return': Decimal(str(round(benchmark_return, 4))),
                    'excess_return': Decimal(str(round(excess_return, 4))),
                    'risk_free_rate': self.RISK_FREE_RATE,
                }
            )

            logger.info(
                f"Calculated beta for {account.account_name} vs {benchmark}: "
                f"β={beta:.2f}, α={alpha:.2f}%"
            )

            return beta_record

        except Exception as e:
            logger.error(f"Error calculating beta: {e}", exc_info=True)
            return None

    def calculate_alpha(
        self,
        portfolio_return: float,
        benchmark_return: float,
        beta: float,
        period_days: int = 365,
    ) -> float:
        """
        Calculate alpha (excess return adjusted for risk).

        Uses CAPM: Alpha = Portfolio Return - (Rf + Beta * (Market Return - Rf))

        Args:
            portfolio_return: Portfolio return percentage
            benchmark_return: Benchmark return percentage
            beta: Portfolio beta
            period_days: Period length for annualization

        Returns:
            float: Alpha as percentage
        """
        try:
            # Annualized risk-free rate adjusted for period
            period_rf = float(self.RISK_FREE_RATE) * 100 * (period_days / 365)

            # CAPM expected return
            expected_return = period_rf + beta * (benchmark_return - period_rf)

            # Alpha = Actual - Expected
            alpha = portfolio_return - expected_return

            return round(alpha, 4)

        except Exception as e:
            logger.error(f"Error calculating alpha: {e}")
            return 0.0

    def get_performance_vs_benchmark(
        self,
        account: BrokerAccount,
        benchmark: str = 'NIFTY50',
        period_type: str = 'FY',
    ) -> Dict:
        """
        Get comprehensive performance comparison vs benchmark.

        Args:
            account: The broker account
            benchmark: Benchmark to compare against
            period_type: Period for comparison

        Returns:
            Dict with comparison metrics
        """
        try:
            # Determine date range
            today = date.today()

            if period_type == 'FY':
                if today.month >= 4:
                    start_date = date(today.year, 4, 1)
                else:
                    start_date = date(today.year - 1, 4, 1)
                end_date = today
            elif period_type == 'YTD':
                start_date = date(today.year, 1, 1)
                end_date = today
            elif period_type == '1M':
                start_date = today - timedelta(days=30)
                end_date = today
            elif period_type == '3M':
                start_date = today - timedelta(days=90)
                end_date = today
            elif period_type == '6M':
                start_date = today - timedelta(days=180)
                end_date = today
            elif period_type == '1Y':
                start_date = today - timedelta(days=365)
                end_date = today
            else:
                # Default to FY
                if today.month >= 4:
                    start_date = date(today.year, 4, 1)
                else:
                    start_date = date(today.year - 1, 4, 1)
                end_date = today

            # Get portfolio equity curve
            equity_curves = DailyEquityCurve.objects.filter(
                account=account,
                date__gte=start_date,
                date__lte=end_date,
            ).order_by('date')

            # Get benchmark data
            benchmark_data = BenchmarkData.objects.filter(
                benchmark=benchmark,
                date__gte=start_date,
                date__lte=end_date,
            ).order_by('date')

            if not equity_curves.exists() or not benchmark_data.exists():
                return {'error': 'Insufficient data'}

            # Portfolio metrics
            first_equity = equity_curves.first()
            last_equity = equity_curves.last()

            portfolio_start = float(first_equity.opening_capital)
            portfolio_end = float(last_equity.closing_capital)
            portfolio_return = ((portfolio_end - portfolio_start) / portfolio_start) * 100 if portfolio_start > 0 else 0

            # Benchmark metrics
            first_bench = benchmark_data.first()
            last_bench = benchmark_data.last()

            benchmark_start = float(first_bench.close)
            benchmark_end = float(last_bench.close)
            benchmark_return = ((benchmark_end - benchmark_start) / benchmark_start) * 100

            # Excess return
            excess_return = portfolio_return - benchmark_return

            # Get beta if available
            beta_record = PortfolioBeta.objects.filter(
                account=account,
                benchmark=benchmark,
            ).order_by('-calculation_date').first()

            # Build daily series for chart
            portfolio_series = []
            benchmark_series = []

            # Normalize both to 100 at start
            for curve in equity_curves:
                normalized = (float(curve.closing_capital) / portfolio_start) * 100
                portfolio_series.append({
                    'date': curve.date.isoformat(),
                    'value': round(normalized, 2),
                })

            for data in benchmark_data:
                normalized = (float(data.close) / benchmark_start) * 100
                benchmark_series.append({
                    'date': data.date.isoformat(),
                    'value': round(normalized, 2),
                })

            return {
                'period': period_type,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'benchmark': benchmark,

                # Returns
                'portfolio_return': round(portfolio_return, 2),
                'benchmark_return': round(benchmark_return, 2),
                'excess_return': round(excess_return, 2),

                # Starting values
                'portfolio_start': portfolio_start,
                'benchmark_start': benchmark_start,

                # Ending values
                'portfolio_end': portfolio_end,
                'benchmark_end': benchmark_end,

                # Beta/Alpha (if available)
                'beta': float(beta_record.beta) if beta_record else None,
                'alpha': float(beta_record.alpha) if beta_record else None,
                'correlation': float(beta_record.correlation) if beta_record else None,

                # Chart data
                'portfolio_series': portfolio_series,
                'benchmark_series': benchmark_series,

                # Outperformance indicator
                'outperformed': portfolio_return > benchmark_return,
            }

        except Exception as e:
            logger.error(f"Error getting benchmark comparison: {e}", exc_info=True)
            return {'error': str(e)}

    def _days_to_period_type(self, days: int) -> str:
        """Convert days to period type string."""
        if days <= 30:
            return '30D'
        elif days <= 60:
            return '60D'
        elif days <= 90:
            return '90D'
        elif days <= 180:
            return '180D'
        elif days <= 365:
            return '1Y'
        else:
            return 'ALL'


# Singleton instance
_analyzer = None


def get_analyzer() -> BenchmarkAnalyzer:
    """Get singleton BenchmarkAnalyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = BenchmarkAnalyzer()
    return _analyzer
