"""
Returns Calculator Service for mCube Trading System

Calculates various return metrics and risk-adjusted performance measures:
- Daily equity curve updates
- Period returns (daily, weekly, monthly, FY)
- Sharpe ratio, Sortino ratio, Calmar ratio
- Maximum drawdown
- CAGR (Compound Annual Growth Rate)
"""

import logging
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import numpy as np
from django.db import transaction
from django.db.models import Avg, Sum, Count, Min, Max, Q
from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.analytics.models import DailyEquityCurve, AccountReturns, DailyPnL, BenchmarkData
from apps.positions.models import Position
from apps.trading.models import TakenTrade

logger = logging.getLogger(__name__)


class ReturnsCalculator:
    """
    Service for calculating returns and performance metrics.
    """

    # Risk-free rate for Sharpe/Sortino calculations (Indian T-bill rate)
    RISK_FREE_RATE = Decimal('0.065')  # 6.5% annual

    # Trading days per year (for annualization)
    TRADING_DAYS_PER_YEAR = 252

    def calculate_daily_equity(
        self,
        account: BrokerAccount,
        target_date: date,
    ) -> Optional[DailyEquityCurve]:
        """
        Calculate and store daily equity curve for an account.

        Args:
            account: The broker account
            target_date: Date to calculate for

        Returns:
            DailyEquityCurve: The created/updated record
        """
        try:
            # Get previous day's closing capital (or initial capital)
            prev_curve = DailyEquityCurve.objects.filter(
                account=account,
                date__lt=target_date,
            ).order_by('-date').first()

            if prev_curve:
                opening_capital = prev_curve.closing_capital
                peak_capital = prev_curve.peak_capital or prev_curve.closing_capital
                cumulative_pnl = prev_curve.cumulative_pnl
            else:
                opening_capital = account.allocated_capital
                peak_capital = opening_capital
                cumulative_pnl = Decimal('0.00')

            # Get positions closed on this date
            closed_positions = Position.objects.filter(
                account=account,
                status='CLOSED',
                exit_timestamp__date=target_date,
            )

            # Calculate realized P&L
            realized_pnl = closed_positions.aggregate(
                total=Sum('realized_pnl')
            )['total'] or Decimal('0.00')

            # Get open positions for unrealized P&L
            open_positions = Position.objects.filter(
                account=account,
                status__in=['OPEN', 'ACTIVE'],
            )

            unrealized_pnl = open_positions.aggregate(
                total=Sum('unrealized_pnl')
            )['total'] or Decimal('0.00')

            # Calculate totals
            total_pnl = realized_pnl + unrealized_pnl
            closing_capital = opening_capital + total_pnl
            cumulative_pnl = cumulative_pnl + realized_pnl

            # Update peak and drawdown
            if closing_capital > peak_capital:
                peak_capital = closing_capital
                current_drawdown = Decimal('0.00')
                drawdown_pct = Decimal('0.00')
            else:
                current_drawdown = peak_capital - closing_capital
                drawdown_pct = (current_drawdown / peak_capital * 100) if peak_capital > 0 else Decimal('0.00')

            # Calculate cumulative return
            initial_capital = account.allocated_capital
            cumulative_return_pct = Decimal('0.00')
            if initial_capital and initial_capital > 0:
                cumulative_return_pct = (cumulative_pnl / initial_capital) * 100

            # Get benchmark data
            nifty_data = BenchmarkData.objects.filter(
                benchmark='NIFTY50',
                date=target_date,
            ).first()

            nifty_close = nifty_data.close if nifty_data else None
            nifty_return = nifty_data.daily_return_pct if nifty_data else None

            # Calculate alpha
            alpha = None
            if nifty_return is not None and opening_capital > 0:
                daily_return = (total_pnl / opening_capital) * 100
                alpha = daily_return - nifty_return

            # Trade counts
            trades_taken = Position.objects.filter(
                account=account,
                entry_timestamp__date=target_date,
            ).count()

            trades_closed = closed_positions.count()
            winning_trades = closed_positions.filter(realized_pnl__gt=0).count()
            losing_trades = closed_positions.filter(realized_pnl__lt=0).count()

            # Create or update equity curve
            equity_curve, created = DailyEquityCurve.objects.update_or_create(
                account=account,
                date=target_date,
                defaults={
                    'opening_capital': opening_capital,
                    'closing_capital': closing_capital,
                    'realized_pnl': realized_pnl,
                    'unrealized_pnl': unrealized_pnl,
                    'total_pnl': total_pnl,
                    'cumulative_pnl': cumulative_pnl,
                    'cumulative_return_pct': cumulative_return_pct,
                    'peak_capital': peak_capital,
                    'current_drawdown': current_drawdown,
                    'drawdown_pct': drawdown_pct,
                    'nifty_close': nifty_close,
                    'nifty_return_pct': nifty_return,
                    'alpha': alpha,
                    'trades_taken': trades_taken,
                    'trades_closed': trades_closed,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                }
            )

            logger.info(
                f"{'Created' if created else 'Updated'} equity curve for "
                f"{account.account_name} on {target_date}: Rs.{closing_capital:,.2f}"
            )

            return equity_curve

        except Exception as e:
            logger.error(
                f"Error calculating daily equity for {account.account_name} on {target_date}: {e}",
                exc_info=True
            )
            return None

    @transaction.atomic
    def calculate_period_returns(
        self,
        account: BrokerAccount,
        period_type: str,
        start_date: date,
        end_date: date,
    ) -> Optional[AccountReturns]:
        """
        Calculate returns for a specific period.

        Args:
            account: The broker account
            period_type: One of DAILY, WEEKLY, MONTHLY, QUARTERLY, FY, ALL_TIME
            start_date: Period start date
            end_date: Period end date

        Returns:
            AccountReturns: The calculated returns record
        """
        try:
            # Get equity curves for the period
            curves = DailyEquityCurve.objects.filter(
                account=account,
                date__gte=start_date,
                date__lte=end_date,
            ).order_by('date')

            if not curves.exists():
                logger.warning(f"No equity data for {account.account_name} from {start_date} to {end_date}")
                return None

            # Get starting and ending capital
            first_curve = curves.first()
            last_curve = curves.last()

            starting_capital = first_curve.opening_capital
            ending_capital = last_curve.closing_capital

            # Calculate returns
            absolute_return = ending_capital - starting_capital
            percentage_return = Decimal('0.00')
            if starting_capital > 0:
                percentage_return = (absolute_return / starting_capital) * 100

            # Annualized return (CAGR)
            days = (end_date - start_date).days or 1
            annualized_return = self.calculate_cagr(
                float(starting_capital),
                float(ending_capital),
                days / 365.0
            )

            # Get daily returns for volatility and Sharpe
            daily_returns = []
            for curve in curves:
                if curve.opening_capital and curve.opening_capital > 0:
                    daily_ret = float((curve.total_pnl / curve.opening_capital))
                    daily_returns.append(daily_ret)

            # Calculate risk metrics
            volatility = self.calculate_volatility(daily_returns)
            sharpe = self.calculate_sharpe_ratio(daily_returns)
            sortino = self.calculate_sortino_ratio(daily_returns)

            # Maximum drawdown
            equity_series = [float(c.closing_capital) for c in curves]
            max_dd, max_dd_pct = self.calculate_max_drawdown(equity_series)

            # Calmar ratio
            calmar = None
            if max_dd_pct and max_dd_pct != 0:
                calmar = Decimal(str(annualized_return)) / Decimal(str(abs(max_dd_pct)))

            # Get trades in period
            trades = TakenTrade.objects.filter(
                account=account,
                closed_at__date__gte=start_date,
                closed_at__date__lte=end_date,
                status='CLOSED',
            )

            total_trades = trades.count()
            winning_trades = trades.filter(outcome='PROFIT').count()
            losing_trades = trades.filter(outcome='LOSS').count()

            win_rate = Decimal('0.00')
            if total_trades > 0:
                win_rate = Decimal(winning_trades) / Decimal(total_trades) * 100

            # Average win/loss
            avg_win = trades.filter(outcome='PROFIT').aggregate(
                avg=Avg('net_pnl')
            )['avg']
            avg_loss = trades.filter(outcome='LOSS').aggregate(
                avg=Avg('net_pnl')
            )['avg']

            # Profit factor
            gross_profit = trades.filter(net_pnl__gt=0).aggregate(
                total=Sum('net_pnl')
            )['total'] or Decimal('0.00')
            gross_loss = abs(trades.filter(net_pnl__lt=0).aggregate(
                total=Sum('net_pnl')
            )['total'] or Decimal('0.00'))

            profit_factor = None
            if gross_loss > 0:
                profit_factor = gross_profit / gross_loss

            # Total charges
            total_charges = trades.aggregate(total=Sum('charges'))['total'] or Decimal('0.00')

            # Strategy breakdown
            strategy_returns = self._calculate_strategy_returns(trades)

            # Generate period label
            period_label = self._generate_period_label(period_type, start_date, end_date)

            # Average capital
            avg_capital = curves.aggregate(avg=Avg('closing_capital'))['avg']

            # Create or update returns record
            returns, created = AccountReturns.objects.update_or_create(
                account=account,
                period_type=period_type,
                period_start=start_date,
                period_end=end_date,
                defaults={
                    'period_label': period_label,
                    'starting_capital': starting_capital,
                    'ending_capital': ending_capital,
                    'avg_capital': avg_capital,
                    'absolute_return': absolute_return,
                    'percentage_return': percentage_return,
                    'annualized_return': Decimal(str(annualized_return)) if annualized_return else None,
                    'max_drawdown': Decimal(str(max_dd)),
                    'max_drawdown_pct': Decimal(str(max_dd_pct)),
                    'volatility': Decimal(str(volatility)) if volatility else None,
                    'sharpe_ratio': Decimal(str(sharpe)) if sharpe else None,
                    'sortino_ratio': Decimal(str(sortino)) if sortino else None,
                    'calmar_ratio': calmar,
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'win_rate': win_rate,
                    'profit_factor': profit_factor,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'total_charges': total_charges,
                    'strategy_returns': strategy_returns,
                }
            )

            logger.info(
                f"Calculated {period_type} returns for {account.account_name}: "
                f"{percentage_return:.2f}% ({period_label})"
            )

            return returns

        except Exception as e:
            logger.error(f"Error calculating period returns: {e}", exc_info=True)
            return None

    def calculate_sharpe_ratio(
        self,
        returns: List[float],
        annualize: bool = True,
    ) -> Optional[float]:
        """
        Calculate Sharpe ratio from returns series.

        Args:
            returns: List of daily returns (as decimals, e.g., 0.01 for 1%)
            annualize: Whether to annualize the ratio

        Returns:
            float: Sharpe ratio, or None if insufficient data
        """
        if len(returns) < 2:
            return None

        try:
            returns_arr = np.array(returns)
            mean_return = np.mean(returns_arr)
            std_return = np.std(returns_arr, ddof=1)

            if std_return == 0:
                return None

            # Daily risk-free rate
            daily_rf = float(self.RISK_FREE_RATE) / self.TRADING_DAYS_PER_YEAR

            sharpe = (mean_return - daily_rf) / std_return

            if annualize:
                sharpe *= math.sqrt(self.TRADING_DAYS_PER_YEAR)

            return round(sharpe, 4)

        except Exception as e:
            logger.error(f"Error calculating Sharpe ratio: {e}")
            return None

    def calculate_sortino_ratio(
        self,
        returns: List[float],
        annualize: bool = True,
    ) -> Optional[float]:
        """
        Calculate Sortino ratio from returns series.
        Uses downside deviation instead of total standard deviation.

        Args:
            returns: List of daily returns (as decimals)
            annualize: Whether to annualize the ratio

        Returns:
            float: Sortino ratio, or None if insufficient data
        """
        if len(returns) < 2:
            return None

        try:
            returns_arr = np.array(returns)
            mean_return = np.mean(returns_arr)

            # Daily risk-free rate
            daily_rf = float(self.RISK_FREE_RATE) / self.TRADING_DAYS_PER_YEAR

            # Downside returns (only negative returns)
            downside_returns = returns_arr[returns_arr < daily_rf]

            if len(downside_returns) == 0:
                return None

            # Downside deviation
            downside_deviation = np.std(downside_returns, ddof=1)

            if downside_deviation == 0:
                return None

            sortino = (mean_return - daily_rf) / downside_deviation

            if annualize:
                sortino *= math.sqrt(self.TRADING_DAYS_PER_YEAR)

            return round(sortino, 4)

        except Exception as e:
            logger.error(f"Error calculating Sortino ratio: {e}")
            return None

    def calculate_max_drawdown(
        self,
        equity_series: List[float],
    ) -> Tuple[float, float]:
        """
        Calculate maximum drawdown from equity series.

        Args:
            equity_series: List of equity values over time

        Returns:
            Tuple: (max_drawdown_absolute, max_drawdown_percentage)
        """
        if len(equity_series) < 2:
            return 0.0, 0.0

        try:
            equity_arr = np.array(equity_series)

            # Running maximum
            running_max = np.maximum.accumulate(equity_arr)

            # Drawdown at each point
            drawdowns = running_max - equity_arr
            drawdown_pcts = drawdowns / running_max * 100

            max_dd = float(np.max(drawdowns))
            max_dd_pct = float(np.max(drawdown_pcts))

            return round(max_dd, 2), round(max_dd_pct, 4)

        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return 0.0, 0.0

    def calculate_volatility(
        self,
        returns: List[float],
        annualize: bool = True,
    ) -> Optional[float]:
        """
        Calculate volatility (standard deviation) of returns.

        Args:
            returns: List of daily returns (as decimals)
            annualize: Whether to annualize

        Returns:
            float: Volatility, or None if insufficient data
        """
        if len(returns) < 2:
            return None

        try:
            std = np.std(returns, ddof=1)

            if annualize:
                std *= math.sqrt(self.TRADING_DAYS_PER_YEAR)

            return round(float(std) * 100, 4)  # Convert to percentage

        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")
            return None

    def calculate_cagr(
        self,
        start_value: float,
        end_value: float,
        years: float,
    ) -> Optional[float]:
        """
        Calculate Compound Annual Growth Rate.

        Args:
            start_value: Starting value
            end_value: Ending value
            years: Number of years

        Returns:
            float: CAGR as percentage, or None if invalid
        """
        if start_value <= 0 or years <= 0:
            return None

        try:
            cagr = (pow(end_value / start_value, 1 / years) - 1) * 100
            return round(cagr, 4)

        except Exception as e:
            logger.error(f"Error calculating CAGR: {e}")
            return None

    def aggregate_all_accounts(
        self,
        user,
        period_type: str,
        start_date: date,
        end_date: date,
    ) -> Dict:
        """
        Aggregate returns across all accounts for a user.

        Args:
            user: The user
            period_type: Period type
            start_date: Start date
            end_date: End date

        Returns:
            Dict with aggregated metrics
        """
        try:
            accounts = BrokerAccount.objects.filter(
                is_active=True,
            )

            total_starting = Decimal('0.00')
            total_ending = Decimal('0.00')
            all_daily_returns = []
            all_equity_values = []
            total_trades = 0
            total_wins = 0

            for account in accounts:
                returns = AccountReturns.objects.filter(
                    account=account,
                    period_type=period_type,
                    period_start=start_date,
                    period_end=end_date,
                ).first()

                if returns:
                    total_starting += returns.starting_capital
                    total_ending += returns.ending_capital
                    total_trades += returns.total_trades
                    total_wins += returns.winning_trades

                # Get daily returns for the period
                curves = DailyEquityCurve.objects.filter(
                    account=account,
                    date__gte=start_date,
                    date__lte=end_date,
                ).order_by('date')

                for curve in curves:
                    if curve.opening_capital and curve.opening_capital > 0:
                        daily_ret = float(curve.total_pnl / curve.opening_capital)
                        all_daily_returns.append(daily_ret)
                    all_equity_values.append(float(curve.closing_capital))

            # Calculate aggregated metrics
            absolute_return = total_ending - total_starting
            pct_return = Decimal('0.00')
            if total_starting > 0:
                pct_return = (absolute_return / total_starting) * 100

            sharpe = self.calculate_sharpe_ratio(all_daily_returns)
            sortino = self.calculate_sortino_ratio(all_daily_returns)
            max_dd, max_dd_pct = self.calculate_max_drawdown(all_equity_values)

            win_rate = Decimal('0.00')
            if total_trades > 0:
                win_rate = Decimal(total_wins) / Decimal(total_trades) * 100

            return {
                'starting_capital': float(total_starting),
                'ending_capital': float(total_ending),
                'absolute_return': float(absolute_return),
                'percentage_return': float(pct_return),
                'sharpe_ratio': sharpe,
                'sortino_ratio': sortino,
                'max_drawdown': max_dd,
                'max_drawdown_pct': max_dd_pct,
                'total_trades': total_trades,
                'winning_trades': total_wins,
                'win_rate': float(win_rate),
            }

        except Exception as e:
            logger.error(f"Error aggregating returns: {e}", exc_info=True)
            return {}

    def _calculate_strategy_returns(self, trades) -> Dict:
        """Calculate returns breakdown by strategy."""
        strategy_data = {}

        for strategy, _ in TakenTrade.STRATEGY_CHOICES:
            strategy_trades = trades.filter(strategy=strategy)

            if not strategy_trades.exists():
                continue

            total = strategy_trades.count()
            wins = strategy_trades.filter(outcome='PROFIT').count()
            pnl = strategy_trades.aggregate(total=Sum('net_pnl'))['total'] or Decimal('0.00')

            strategy_data[strategy] = {
                'total_trades': total,
                'winning_trades': wins,
                'win_rate': float(Decimal(wins) / Decimal(total) * 100) if total > 0 else 0,
                'total_pnl': float(pnl),
            }

        return strategy_data

    def _generate_period_label(
        self,
        period_type: str,
        start_date: date,
        end_date: date,
    ) -> str:
        """Generate display label for period."""
        if period_type == 'DAILY':
            return start_date.strftime('%Y-%m-%d')
        elif period_type == 'WEEKLY':
            return f"Week {start_date.strftime('%Y-W%W')}"
        elif period_type == 'MONTHLY':
            return start_date.strftime('%b %Y')
        elif period_type == 'QUARTERLY':
            quarter = (start_date.month - 1) // 3 + 1
            return f"Q{quarter} {start_date.year}"
        elif period_type == 'FY':
            fy_year = start_date.year if start_date.month >= 4 else start_date.year - 1
            return f"FY{fy_year}-{str(fy_year + 1)[-2:]}"
        elif period_type == 'YTD':
            return f"YTD {end_date.year}"
        else:
            return f"{start_date} to {end_date}"


# Singleton instance
_calculator = None


def get_calculator() -> ReturnsCalculator:
    """Get singleton ReturnsCalculator instance."""
    global _calculator
    if _calculator is None:
        _calculator = ReturnsCalculator()
    return _calculator
