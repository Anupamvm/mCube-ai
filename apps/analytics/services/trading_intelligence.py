"""
Trading Intelligence Service - Smart Analysis & Conclusions

Analyzes trading data like a data scientist and trader to provide:
- Statistical edge identification
- Market regime analysis
- Behavioral insights
- Risk-adjusted recommendations
- Actionable trading conclusions

Think like a quant + discretionary trader hybrid.
"""

import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
import statistics

from django.db.models import Sum, Count, Avg, Max, Min, F, Q, StdDev, Variance
from django.db.models.functions import ExtractWeekDay, ExtractHour, ExtractMonth, TruncMonth, TruncWeek
from django.utils import timezone

logger = logging.getLogger(__name__)


class TradingIntelligenceService:
    """
    Smart trading analysis engine that combines:
    - Statistical analysis (data scientist perspective)
    - Market intuition (trader perspective)
    - Risk management (portfolio manager perspective)
    """

    def __init__(self, broker: str = None):
        self.broker = broker
        self._cache = {}

    def get_smart_suggestions(self) -> Dict[str, Any]:
        """
        Generate comprehensive smart trading suggestions and conclusions.

        Returns a structured analysis with:
        - Executive summary
        - Statistical insights
        - Behavioral patterns
        - Risk assessment
        - Actionable recommendations
        """
        try:
            # Gather all analysis components
            overview = self._get_performance_overview()
            edge_analysis = self._analyze_statistical_edge()
            time_patterns = self._analyze_time_patterns()
            symbol_insights = self._analyze_symbol_performance()
            risk_analysis = self._analyze_risk_metrics()
            behavioral_patterns = self._analyze_behavioral_patterns()
            market_regime = self._analyze_market_conditions()
            streak_analysis = self._analyze_streaks_and_momentum()

            # Generate conclusions and recommendations
            conclusions = self._generate_conclusions(
                overview, edge_analysis, time_patterns, symbol_insights,
                risk_analysis, behavioral_patterns, market_regime, streak_analysis
            )

            # Prioritize actionable items
            action_items = self._prioritize_actions(conclusions)

            return {
                'timestamp': timezone.now().isoformat(),
                'executive_summary': self._create_executive_summary(overview, conclusions),
                'performance_overview': overview,
                'statistical_edge': edge_analysis,
                'time_patterns': time_patterns,
                'symbol_insights': symbol_insights,
                'risk_analysis': risk_analysis,
                'behavioral_patterns': behavioral_patterns,
                'market_regime': market_regime,
                'streak_analysis': streak_analysis,
                'conclusions': conclusions,
                'action_items': action_items,
                'confidence_score': self._calculate_confidence_score(overview),
            }
        except Exception as e:
            logger.error(f"Error generating smart suggestions: {e}", exc_info=True)
            return {'error': str(e)}

    def _get_base_queryset(self):
        """Get base queryset for contract P&L data."""
        from apps.brokers.models import BrokerContractPnL
        qs = BrokerContractPnL.objects.all()
        if self.broker:
            qs = qs.filter(broker=self.broker)
        return qs

    def _get_performance_overview(self) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics."""
        qs = self._get_base_queryset()

        stats = qs.aggregate(
            total_trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            gross_pnl=Sum('gross_pnl'),
            total_charges=Sum('total_charges'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
            losers=Count('id', filter=Q(net_pnl__lt=0)),
            breakeven=Count('id', filter=Q(net_pnl=0)),
            total_profit=Sum('net_pnl', filter=Q(net_pnl__gt=0)),
            total_loss=Sum('net_pnl', filter=Q(net_pnl__lt=0)),
            avg_profit=Avg('net_pnl', filter=Q(net_pnl__gt=0)),
            avg_loss=Avg('net_pnl', filter=Q(net_pnl__lt=0)),
            max_profit=Max('net_pnl'),
            max_loss=Min('net_pnl'),
            pnl_stddev=StdDev('net_pnl'),
        )

        total_trades = stats['total_trades'] or 0
        winners = stats['winners'] or 0
        losers = stats['losers'] or 0
        total_profit = float(stats['total_profit'] or 0)
        total_loss = abs(float(stats['total_loss'] or 0))
        avg_profit = float(stats['avg_profit'] or 0)
        avg_loss = abs(float(stats['avg_loss'] or 0))

        # Core metrics
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else float('inf')
        risk_reward = (avg_profit / avg_loss) if avg_loss > 0 else float('inf')

        # Expected value per trade
        expectancy = (win_rate/100 * avg_profit) - ((100-win_rate)/100 * avg_loss)

        # Kelly Criterion for optimal position sizing
        if profit_factor > 0 and profit_factor != float('inf'):
            kelly_pct = (win_rate/100) - ((1 - win_rate/100) / (risk_reward if risk_reward > 0 else 1))
            kelly_pct = max(0, min(kelly_pct * 100, 100))  # Cap at 100%
        else:
            kelly_pct = 0

        # Charges impact
        charges_pct = (float(stats['total_charges'] or 0) / float(stats['gross_pnl'] or 1)) * 100 if stats['gross_pnl'] else 0

        return {
            'total_trades': total_trades,
            'total_pnl': float(stats['total_pnl'] or 0),
            'gross_pnl': float(stats['gross_pnl'] or 0),
            'total_charges': float(stats['total_charges'] or 0),
            'charges_impact_pct': round(charges_pct, 2),
            'winners': winners,
            'losers': losers,
            'breakeven': stats['breakeven'] or 0,
            'win_rate': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else None,
            'avg_profit': round(avg_profit, 2),
            'avg_loss': round(avg_loss, 2),
            'risk_reward': round(risk_reward, 2) if risk_reward != float('inf') else None,
            'expectancy': round(expectancy, 2),
            'max_profit': float(stats['max_profit'] or 0),
            'max_loss': float(stats['max_loss'] or 0),
            'pnl_volatility': float(stats['pnl_stddev'] or 0),
            'kelly_criterion_pct': round(kelly_pct, 2),
        }

    def _analyze_statistical_edge(self) -> Dict[str, Any]:
        """
        Analyze statistical edge with significance testing.
        Key question: Is our edge statistically significant or just luck?
        """
        qs = self._get_base_queryset()
        pnl_values = list(qs.values_list('net_pnl', flat=True))
        pnl_values = [float(p) for p in pnl_values if p is not None]

        if len(pnl_values) < 10:
            return {'insufficient_data': True, 'min_required': 10, 'current': len(pnl_values)}

        # Basic statistics
        mean_pnl = statistics.mean(pnl_values)
        median_pnl = statistics.median(pnl_values)
        stdev_pnl = statistics.stdev(pnl_values) if len(pnl_values) > 1 else 0

        # T-test: Is mean significantly different from 0?
        n = len(pnl_values)
        if stdev_pnl > 0:
            t_statistic = mean_pnl / (stdev_pnl / (n ** 0.5))
            import math
            z = abs(t_statistic)
            p_value = 2 * (1 - 0.5 * (1 + math.erf(z / (2 ** 0.5))))
        else:
            t_statistic = 0
            p_value = 1.0

        # Sharpe-like ratio (annualized assuming 250 trading days)
        if stdev_pnl > 0:
            sharpe_daily = mean_pnl / stdev_pnl
            sharpe_annualized = sharpe_daily * (250 ** 0.5)
        else:
            sharpe_daily = 0
            sharpe_annualized = 0

        # Sortino ratio (only downside deviation)
        negative_returns = [p for p in pnl_values if p < 0]
        if negative_returns and len(negative_returns) > 1:
            downside_dev = statistics.stdev(negative_returns)
            sortino = mean_pnl / downside_dev if downside_dev > 0 else 0
        else:
            downside_dev = 0
            sortino = 0

        # Skewness and Kurtosis
        if stdev_pnl > 0 and n > 2:
            skewness = sum(((x - mean_pnl) / stdev_pnl) ** 3 for x in pnl_values) / n
            kurtosis = sum(((x - mean_pnl) / stdev_pnl) ** 4 for x in pnl_values) / n - 3
        else:
            skewness = 0
            kurtosis = 0

        # Win rate confidence interval
        wins = sum(1 for p in pnl_values if p > 0)
        win_rate = wins / n
        z_95 = 1.96
        margin = z_95 * ((win_rate * (1 - win_rate) / n) ** 0.5)
        win_rate_ci = (max(0, win_rate - margin), min(1, win_rate + margin))

        is_significant = p_value < 0.05 and mean_pnl > 0
        edge_quality = self._categorize_edge(sharpe_annualized, p_value, win_rate)

        return {
            'sample_size': n,
            'mean_pnl': round(mean_pnl, 2),
            'median_pnl': round(median_pnl, 2),
            'std_dev': round(stdev_pnl, 2),
            't_statistic': round(t_statistic, 3),
            'p_value': round(p_value, 4),
            'is_statistically_significant': is_significant,
            'confidence_level': round((1 - p_value) * 100, 1),
            'sharpe_ratio_daily': round(sharpe_daily, 3),
            'sharpe_ratio_annualized': round(sharpe_annualized, 3),
            'sortino_ratio': round(sortino, 3),
            'downside_deviation': round(downside_dev, 2),
            'skewness': round(skewness, 3),
            'kurtosis': round(kurtosis, 3),
            'win_rate_95_ci': (round(win_rate_ci[0] * 100, 1), round(win_rate_ci[1] * 100, 1)),
            'edge_quality': edge_quality,
            'interpretation': self._interpret_edge(edge_quality, is_significant, mean_pnl, sharpe_annualized),
        }

    def _categorize_edge(self, sharpe: float, p_value: float, win_rate: float) -> str:
        """Categorize edge quality."""
        if p_value > 0.1:
            return 'NO_EDGE'
        elif p_value > 0.05:
            return 'WEAK_EDGE'
        elif sharpe < 0.5:
            return 'MARGINAL_EDGE'
        elif sharpe < 1.0:
            return 'MODERATE_EDGE'
        elif sharpe < 2.0:
            return 'GOOD_EDGE'
        else:
            return 'EXCELLENT_EDGE'

    def _interpret_edge(self, quality: str, significant: bool, mean_pnl: float, sharpe: float) -> str:
        """Generate human-readable edge interpretation."""
        interpretations = {
            'NO_EDGE': "Your results could be due to random chance. Need more data or strategy refinement.",
            'WEAK_EDGE': "There's a hint of edge, but not statistically reliable yet. Continue monitoring.",
            'MARGINAL_EDGE': "Small but real edge detected. Focus on consistency and reducing variance.",
            'MODERATE_EDGE': "Solid edge! Your strategy shows reliable outperformance. Optimize position sizing.",
            'GOOD_EDGE': "Strong edge confirmed. Consider scaling up with proper risk management.",
            'EXCELLENT_EDGE': "Exceptional performance. Verify this isn't due to survivorship bias or overfitting.",
        }
        return interpretations.get(quality, "Unable to assess edge quality.")

    def _analyze_time_patterns(self) -> Dict[str, Any]:
        """Analyze when you trade best - monthly patterns."""
        qs = self._get_base_queryset()

        monthly_data = qs.filter(expiry_date__isnull=False).annotate(
            month=ExtractMonth('expiry_date')
        ).values('month').annotate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
            avg_pnl=Avg('net_pnl'),
        ).order_by('month')

        month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        monthly_analysis = []
        best_month = None
        worst_month = None
        best_pnl = float('-inf')
        worst_pnl = float('inf')

        for m in monthly_data:
            month_num = m['month']
            if not month_num:
                continue
            trades = m['trades'] or 0
            pnl = float(m['total_pnl'] or 0)
            winners = m['winners'] or 0
            win_rate = (winners / trades * 100) if trades > 0 else 0

            month_info = {
                'month': month_names[month_num],
                'month_num': month_num,
                'trades': trades,
                'total_pnl': round(pnl, 2),
                'win_rate': round(win_rate, 1),
                'avg_pnl': round(float(m['avg_pnl'] or 0), 2),
            }
            monthly_analysis.append(month_info)

            if pnl > best_pnl:
                best_pnl = pnl
                best_month = month_names[month_num]
            if pnl < worst_pnl:
                worst_pnl = pnl
                worst_month = month_names[month_num]

        expiry_analysis = self._analyze_expiry_patterns()

        return {
            'monthly_performance': monthly_analysis,
            'best_month': {'month': best_month, 'pnl': round(best_pnl, 2)} if best_month else None,
            'worst_month': {'month': worst_month, 'pnl': round(worst_pnl, 2)} if worst_month else None,
            'expiry_patterns': expiry_analysis,
            'recommendations': self._generate_time_recommendations(monthly_analysis, expiry_analysis),
        }

    def _analyze_expiry_patterns(self) -> Dict[str, Any]:
        """Analyze performance around expiry dates."""
        qs = self._get_base_queryset()

        weekly_expiries = qs.filter(segment='OPTIONS').aggregate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
        )

        weekly_trades = weekly_expiries['trades'] or 0

        return {
            'options_expiry': {
                'trades': weekly_trades,
                'total_pnl': float(weekly_expiries['total_pnl'] or 0),
                'win_rate': round((weekly_expiries['winners'] or 0) / weekly_trades * 100, 1) if weekly_trades > 0 else 0,
            },
        }

    def _generate_time_recommendations(self, monthly: List, expiry: Dict) -> List[str]:
        """Generate time-based trading recommendations."""
        recommendations = []

        if monthly:
            profitable_months = [m for m in monthly if m['total_pnl'] > 0]
            losing_months = [m for m in monthly if m['total_pnl'] < 0]

            if len(losing_months) > len(profitable_months):
                recommendations.append(
                    f"More losing months ({len(losing_months)}) than winning ({len(profitable_months)}). "
                    "Consider reducing position size during historically weak months."
                )

            if profitable_months:
                best = sorted(profitable_months, key=lambda x: x['total_pnl'], reverse=True)[:2]
                recommendations.append(
                    f"Strongest months: {', '.join(m['month'] for m in best)}. Consider being more aggressive."
                )

            if losing_months:
                worst = sorted(losing_months, key=lambda x: x['total_pnl'])[:2]
                recommendations.append(
                    f"Weakest months: {', '.join(m['month'] for m in worst)}. Consider reducing exposure."
                )

        return recommendations

    def _analyze_symbol_performance(self) -> Dict[str, Any]:
        """Analyze performance by underlying symbol."""
        qs = self._get_base_queryset()

        symbol_stats = qs.values('symbol').annotate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
            avg_pnl=Avg('net_pnl'),
            max_profit=Max('net_pnl'),
            max_loss=Min('net_pnl'),
        ).filter(trades__gte=3).order_by('-total_pnl')

        symbols = []
        profitable_symbols = []
        losing_symbols = []

        for s in symbol_stats:
            trades = s['trades']
            pnl = float(s['total_pnl'] or 0)
            winners = s['winners'] or 0
            win_rate = (winners / trades * 100) if trades > 0 else 0

            symbol_info = {
                'symbol': s['symbol'],
                'trades': trades,
                'total_pnl': round(pnl, 2),
                'win_rate': round(win_rate, 1),
                'avg_pnl': round(float(s['avg_pnl'] or 0), 2),
                'max_profit': round(float(s['max_profit'] or 0), 2),
                'max_loss': round(float(s['max_loss'] or 0), 2),
            }
            symbols.append(symbol_info)

            if pnl > 0:
                profitable_symbols.append(symbol_info)
            else:
                losing_symbols.append(symbol_info)

        total_pnl = sum(s['total_pnl'] for s in symbols)
        if symbols and total_pnl != 0:
            top_symbol_contribution = (symbols[0]['total_pnl'] / abs(total_pnl)) * 100 if symbols else 0
        else:
            top_symbol_contribution = 0

        return {
            'all_symbols': symbols[:20],
            'best_performers': profitable_symbols[:5],
            'worst_performers': losing_symbols[-5:] if losing_symbols else [],
            'concentration_risk': {
                'top_symbol': symbols[0]['symbol'] if symbols else None,
                'top_contribution_pct': round(abs(top_symbol_contribution), 1),
                'is_concentrated': abs(top_symbol_contribution) > 50,
            },
            'recommendations': self._generate_symbol_recommendations(symbols, profitable_symbols, losing_symbols),
        }

    def _generate_symbol_recommendations(self, all_symbols: List, profitable: List, losing: List) -> List[str]:
        """Generate symbol-specific recommendations."""
        recommendations = []

        if profitable:
            best = profitable[0]
            recommendations.append(
                f"Your edge is strongest in {best['symbol']} "
                f"({best['win_rate']}% win rate, avg P&L: Rs.{best['avg_pnl']:,.0f}). "
                "Consider focusing more here."
            )

        if losing and len(losing) >= 2:
            worst = [s['symbol'] for s in losing[-2:]]
            recommendations.append(
                f"Consider avoiding or reducing size in {', '.join(worst)} - consistently losing."
            )

        if all_symbols and len(all_symbols) < 3:
            recommendations.append(
                "Low diversification detected. Trading only 1-2 symbols increases concentration risk."
            )

        return recommendations

    def _analyze_risk_metrics(self) -> Dict[str, Any]:
        """Comprehensive risk analysis."""
        qs = self._get_base_queryset()
        pnl_values = [float(p) for p in qs.values_list('net_pnl', flat=True) if p is not None]

        if not pnl_values:
            return {'insufficient_data': True}

        # Calculate running drawdown
        cumulative = []
        running_sum = 0
        peak = 0
        max_drawdown = 0
        current_drawdown = 0
        drawdown_periods = []
        in_drawdown = False
        drawdown_start_idx = 0

        for i, pnl in enumerate(pnl_values):
            running_sum += pnl
            cumulative.append(running_sum)

            if running_sum > peak:
                if in_drawdown:
                    drawdown_periods.append(i - drawdown_start_idx)
                    in_drawdown = False
                peak = running_sum
            else:
                if not in_drawdown:
                    drawdown_start_idx = i
                    in_drawdown = True
                current_dd = peak - running_sum
                if current_dd > max_drawdown:
                    max_drawdown = current_dd

        if in_drawdown:
            drawdown_periods.append(len(pnl_values) - drawdown_start_idx)

        current_drawdown = peak - running_sum if running_sum < peak else 0

        # Value at Risk (VaR) - 95th percentile
        sorted_pnl = sorted(pnl_values)
        var_index = int(len(sorted_pnl) * 0.05)
        var_95 = sorted_pnl[var_index] if var_index < len(sorted_pnl) else sorted_pnl[0]

        # Conditional VaR (Expected Shortfall)
        cvar_values = sorted_pnl[:var_index + 1] if var_index > 0 else sorted_pnl[:1]
        cvar_95 = statistics.mean(cvar_values) if cvar_values else var_95

        # Loss statistics
        losses = [p for p in pnl_values if p < 0]
        loss_stats = {}
        if losses:
            loss_stats = {
                'count': len(losses),
                'total': round(sum(losses), 2),
                'average': round(statistics.mean(losses), 2),
                'worst': round(min(losses), 2),
                'median': round(statistics.median(losses), 2),
            }

        # Consecutive losses
        max_consecutive_losses = 0
        current_consecutive = 0
        for pnl in pnl_values:
            if pnl < 0:
                current_consecutive += 1
                max_consecutive_losses = max(max_consecutive_losses, current_consecutive)
            else:
                current_consecutive = 0

        total_pnl = sum(pnl_values)
        calmar_ratio = total_pnl / max_drawdown if max_drawdown > 0 else 0

        return {
            'max_drawdown': round(max_drawdown, 2),
            'current_drawdown': round(current_drawdown, 2),
            'in_drawdown': current_drawdown > 0,
            'peak_equity': round(peak, 2),
            'current_equity': round(running_sum, 2),
            'var_95': round(var_95, 2),
            'cvar_95': round(cvar_95, 2),
            'calmar_ratio': round(calmar_ratio, 3),
            'max_consecutive_losses': max_consecutive_losses,
            'avg_drawdown_duration': round(statistics.mean(drawdown_periods), 1) if drawdown_periods else 0,
            'loss_statistics': loss_stats,
            'risk_level': self._assess_risk_level(max_drawdown, max_consecutive_losses, current_drawdown),
            'recommendations': self._generate_risk_recommendations(max_drawdown, current_drawdown, max_consecutive_losses, var_95),
        }

    def _assess_risk_level(self, max_dd: float, max_consec: int, current_dd: float) -> str:
        """Assess overall risk level."""
        if current_dd > max_dd * 0.8:
            return 'CRITICAL'
        elif max_consec >= 5 or max_dd > 100000:
            return 'HIGH'
        elif max_consec >= 3 or max_dd > 50000:
            return 'MODERATE'
        else:
            return 'LOW'

    def _generate_risk_recommendations(self, max_dd: float, current_dd: float, max_consec: int, var: float) -> List[str]:
        """Generate risk management recommendations."""
        recommendations = []

        if current_dd > 0:
            recommendations.append(
                f"Currently in drawdown of Rs.{current_dd:,.0f}. "
                "Consider reducing position sizes until recovery."
            )

        if max_consec >= 4:
            recommendations.append(
                f"Had {max_consec} consecutive losses at worst. "
                "Implement a 'pause rule' after 3 consecutive losses."
            )

        recommendations.append(
            f"95% VaR is Rs.{abs(var):,.0f}. "
            "This is your expected worst-case single trade loss at 95% confidence."
        )

        if max_dd > 50000:
            recommendations.append(
                f"Max drawdown of Rs.{max_dd:,.0f} is significant. "
                "Review position sizing - consider using Kelly Criterion at 1/2 or 1/4 for safety."
            )

        return recommendations

    def _analyze_behavioral_patterns(self) -> Dict[str, Any]:
        """Analyze trading behavior patterns."""
        qs = self._get_base_queryset()

        segment_stats = qs.values('segment').annotate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
            total_charges=Sum('total_charges'),
        )

        segments = {}
        for s in segment_stats:
            trades = s['trades'] or 0
            pnl = float(s['total_pnl'] or 0)
            winners = s['winners'] or 0
            charges = float(s['total_charges'] or 0)

            segments[s['segment']] = {
                'trades': trades,
                'total_pnl': round(pnl, 2),
                'win_rate': round((winners / trades * 100), 1) if trades > 0 else 0,
                'avg_pnl': round(pnl / trades, 2) if trades > 0 else 0,
                'total_charges': round(charges, 2),
            }

        option_stats = qs.filter(segment='OPTIONS').values('option_type').annotate(
            trades=Count('id'),
            total_pnl=Sum('net_pnl'),
            winners=Count('id', filter=Q(net_pnl__gt=0)),
        )

        options = {}
        for o in option_stats:
            if o['option_type']:
                trades = o['trades'] or 0
                pnl = float(o['total_pnl'] or 0)
                winners = o['winners'] or 0
                options[o['option_type']] = {
                    'trades': trades,
                    'total_pnl': round(pnl, 2),
                    'win_rate': round((winners / trades * 100), 1) if trades > 0 else 0,
                }

        weekly_trades = qs.filter(expiry_date__isnull=False).annotate(
            week=TruncWeek('expiry_date')
        ).values('week').annotate(
            trades=Count('id')
        )

        trade_counts = [w['trades'] for w in weekly_trades if w['trades']]
        avg_weekly_trades = statistics.mean(trade_counts) if trade_counts else 0

        return {
            'segment_performance': segments,
            'option_type_performance': options,
            'trading_frequency': {
                'avg_trades_per_week': round(avg_weekly_trades, 1),
                'total_weeks_traded': len(trade_counts),
                'most_active_week_trades': max(trade_counts) if trade_counts else 0,
            },
            'recommendations': self._generate_behavioral_recommendations(segments, options),
        }

    def _generate_behavioral_recommendations(self, segments: Dict, options: Dict) -> List[str]:
        """Generate behavioral recommendations."""
        recommendations = []

        if 'OPTIONS' in segments and 'FUTURES' in segments:
            opt_pnl = segments['OPTIONS']['total_pnl']
            fut_pnl = segments['FUTURES']['total_pnl']

            if opt_pnl > fut_pnl and opt_pnl > 0:
                recommendations.append(
                    "Options trading is more profitable. Consider allocating more capital to options strategies."
                )
            elif fut_pnl > opt_pnl and fut_pnl > 0:
                recommendations.append(
                    "Futures trading outperforms options. Your directional calls are working better."
                )

        if 'CE' in options and 'PE' in options:
            ce_pnl = options['CE']['total_pnl']
            pe_pnl = options['PE']['total_pnl']

            if ce_pnl > pe_pnl and ce_pnl > 0:
                recommendations.append(
                    f"Call options (CE) are profitable while puts (PE) are {'losing' if pe_pnl < 0 else 'underperforming'}. "
                    "Possible bullish bias in strategy."
                )
            elif pe_pnl > ce_pnl and pe_pnl > 0:
                recommendations.append(
                    "Put options (PE) outperform calls. Consider hedging positions more frequently."
                )

        return recommendations

    def _analyze_market_conditions(self) -> Dict[str, Any]:
        """Analyze performance in different market conditions."""
        return {
            'note': 'Market condition analysis requires VIX/trend correlation data',
            'framework': {
                'high_vix_performance': 'Track trades when VIX > 18',
                'low_vix_performance': 'Track trades when VIX < 14',
                'trending_market': 'Track trades in strong trend days',
                'range_bound_market': 'Track trades in sideways markets',
            },
            'recommendations': [
                "Keep a trading journal noting market conditions for each trade.",
                "Tag trades with VIX level and market trend for future analysis.",
            ]
        }

    def _analyze_streaks_and_momentum(self) -> Dict[str, Any]:
        """Analyze winning/losing streaks and trading momentum."""
        qs = self._get_base_queryset().order_by('expiry_date', 'id')
        pnl_values = list(qs.values_list('net_pnl', flat=True))
        pnl_values = [float(p) for p in pnl_values if p is not None]

        if not pnl_values:
            return {'insufficient_data': True}

        win_streaks = []
        loss_streaks = []
        current_streak = 0
        current_type = None

        for pnl in pnl_values:
            is_win = pnl > 0

            if current_type is None:
                current_type = 'win' if is_win else 'loss'
                current_streak = 1
            elif (is_win and current_type == 'win') or (not is_win and current_type == 'loss'):
                current_streak += 1
            else:
                if current_type == 'win':
                    win_streaks.append(current_streak)
                else:
                    loss_streaks.append(current_streak)
                current_type = 'win' if is_win else 'loss'
                current_streak = 1

        if current_type == 'win':
            win_streaks.append(current_streak)
        else:
            loss_streaks.append(current_streak)

        recent = pnl_values[-10:] if len(pnl_values) >= 10 else pnl_values
        recent_wins = sum(1 for p in recent if p > 0)
        recent_pnl = sum(recent)

        return {
            'current_streak': {
                'type': current_type,
                'length': current_streak,
            },
            'max_win_streak': max(win_streaks) if win_streaks else 0,
            'max_loss_streak': max(loss_streaks) if loss_streaks else 0,
            'avg_win_streak': round(statistics.mean(win_streaks), 1) if win_streaks else 0,
            'avg_loss_streak': round(statistics.mean(loss_streaks), 1) if loss_streaks else 0,
            'recent_momentum': {
                'trades': len(recent),
                'wins': recent_wins,
                'losses': len(recent) - recent_wins,
                'pnl': round(recent_pnl, 2),
                'trend': 'HOT' if recent_wins >= 7 else ('COLD' if recent_wins <= 3 else 'NEUTRAL'),
            },
            'recommendations': self._generate_momentum_recommendations(current_type, current_streak, recent_wins, len(recent)),
        }

    def _generate_momentum_recommendations(self, streak_type: str, streak_len: int, recent_wins: int, total_recent: int) -> List[str]:
        """Generate momentum-based recommendations."""
        recommendations = []

        if streak_type == 'loss' and streak_len >= 3:
            recommendations.append(
                f"On a {streak_len}-trade losing streak. Consider taking a break or reducing size by 50%."
            )
        elif streak_type == 'win' and streak_len >= 4:
            recommendations.append(
                f"On a {streak_len}-trade winning streak! Stay disciplined - don't increase size due to overconfidence."
            )

        if total_recent >= 5:
            win_pct = (recent_wins / total_recent) * 100
            if win_pct >= 70:
                recommendations.append(
                    f"Running hot ({recent_wins}/{total_recent} recent wins). Great execution - maintain discipline."
                )
            elif win_pct <= 30:
                recommendations.append(
                    f"Cold streak ({recent_wins}/{total_recent} recent wins). Review setups and consider paper trading."
                )

        return recommendations

    def _generate_conclusions(self, overview, edge, time, symbols, risk, behavior, market, streaks) -> List[Dict]:
        """Generate prioritized trading conclusions."""
        conclusions = []

        # 1. Edge Assessment
        if edge and not edge.get('insufficient_data'):
            if edge.get('is_statistically_significant'):
                conclusions.append({
                    'type': 'POSITIVE',
                    'category': 'EDGE',
                    'title': 'Statistical Edge Confirmed',
                    'message': f"Your strategy has a statistically significant edge (p={edge['p_value']:.3f}). "
                               f"Annualized Sharpe: {edge['sharpe_ratio_annualized']:.2f}",
                    'priority': 1,
                })
            else:
                conclusions.append({
                    'type': 'WARNING',
                    'category': 'EDGE',
                    'title': 'Edge Not Yet Proven',
                    'message': f"Results could be random (p={edge['p_value']:.3f}). "
                               "Need more trades or strategy refinement.",
                    'priority': 2,
                })

        # 2. Win Rate Assessment
        if overview.get('win_rate'):
            wr = overview['win_rate']
            if wr >= 55:
                conclusions.append({
                    'type': 'POSITIVE',
                    'category': 'PERFORMANCE',
                    'title': f'Solid Win Rate: {wr}%',
                    'message': f"Above average win rate. Combined with {overview.get('risk_reward', 'N/A')} R:R, "
                               f"your expectancy is Rs.{overview.get('expectancy', 0):,.0f} per trade.",
                    'priority': 2,
                })
            elif wr < 40:
                conclusions.append({
                    'type': 'WARNING',
                    'category': 'PERFORMANCE',
                    'title': f'Low Win Rate: {wr}%',
                    'message': "Win rate below 40% requires exceptional risk:reward to be profitable. "
                               "Review entry criteria.",
                    'priority': 1,
                })

        # 3. Risk Assessment
        if risk and not risk.get('insufficient_data'):
            if risk.get('in_drawdown') and risk['current_drawdown'] > 20000:
                conclusions.append({
                    'type': 'ALERT',
                    'category': 'RISK',
                    'title': 'Significant Drawdown in Progress',
                    'message': f"Currently down Rs.{risk['current_drawdown']:,.0f} from peak. "
                               "Consider reducing exposure until recovery.",
                    'priority': 1,
                })

            if risk.get('max_consecutive_losses', 0) >= 4:
                conclusions.append({
                    'type': 'WARNING',
                    'category': 'RISK',
                    'title': f"History of Losing Streaks ({risk['max_consecutive_losses']} max)",
                    'message': "Implement a circuit breaker rule: pause after 3 consecutive losses.",
                    'priority': 2,
                })

        # 4. Symbol Concentration
        if symbols and symbols.get('concentration_risk', {}).get('is_concentrated'):
            conclusions.append({
                'type': 'WARNING',
                'category': 'DIVERSIFICATION',
                'title': 'High Concentration Risk',
                'message': f"{symbols['concentration_risk']['top_symbol']} accounts for "
                           f"{symbols['concentration_risk']['top_contribution_pct']}% of P&L. Diversify.",
                'priority': 2,
            })

        # 5. Behavioral Insights
        if behavior and behavior.get('segment_performance'):
            segs = behavior['segment_performance']
            if 'OPTIONS' in segs and segs['OPTIONS']['total_pnl'] < 0 and segs['OPTIONS']['trades'] > 10:
                conclusions.append({
                    'type': 'ALERT',
                    'category': 'STRATEGY',
                    'title': 'Options Trading Underperforming',
                    'message': f"Options segment has net loss of Rs.{abs(segs['OPTIONS']['total_pnl']):,.0f}. "
                               "Review option selling strategies and premium collection approach.",
                    'priority': 2,
                })

        # 6. Charges Impact
        if overview.get('charges_impact_pct', 0) > 10:
            conclusions.append({
                'type': 'WARNING',
                'category': 'COSTS',
                'title': f'High Transaction Costs ({overview["charges_impact_pct"]}%)',
                'message': "Charges are eating into profits. Consider larger position sizes or fewer trades.",
                'priority': 3,
            })

        # 7. Recent Momentum
        if streaks and streaks.get('recent_momentum'):
            momentum = streaks['recent_momentum']
            if momentum['trend'] == 'HOT':
                conclusions.append({
                    'type': 'POSITIVE',
                    'category': 'MOMENTUM',
                    'title': 'Currently Running Hot',
                    'message': f"{momentum['wins']}/{momentum['trades']} recent trades profitable. "
                               "Stay disciplined, don't increase size.",
                    'priority': 3,
                })
            elif momentum['trend'] == 'COLD':
                conclusions.append({
                    'type': 'ALERT',
                    'category': 'MOMENTUM',
                    'title': 'Cold Streak in Progress',
                    'message': f"Only {momentum['wins']}/{momentum['trades']} recent wins. "
                               "Consider reducing size or taking a break.",
                    'priority': 1,
                })

        conclusions.sort(key=lambda x: x['priority'])
        return conclusions

    def _prioritize_actions(self, conclusions: List[Dict]) -> List[Dict]:
        """Convert conclusions into prioritized action items."""
        actions = []

        for c in conclusions:
            if c['type'] == 'ALERT':
                action = {
                    'urgency': 'IMMEDIATE',
                    'action': c['message'],
                    'category': c['category'],
                }
            elif c['type'] == 'WARNING':
                action = {
                    'urgency': 'SOON',
                    'action': c['message'],
                    'category': c['category'],
                }
            elif c['type'] == 'POSITIVE':
                action = {
                    'urgency': 'MAINTAIN',
                    'action': c['message'],
                    'category': c['category'],
                }
            else:
                continue

            actions.append(action)

        return actions

    def _create_executive_summary(self, overview: Dict, conclusions: List) -> Dict:
        """Create executive summary for quick consumption."""
        score = 50

        if overview.get('win_rate', 0) >= 50:
            score += 10
        if overview.get('profit_factor', 0) and overview['profit_factor'] >= 1.5:
            score += 15
        if overview.get('total_pnl', 0) > 0:
            score += 10
        if overview.get('expectancy', 0) > 0:
            score += 10

        alerts = sum(1 for c in conclusions if c['type'] == 'ALERT')
        warnings = sum(1 for c in conclusions if c['type'] == 'WARNING')
        score -= alerts * 15
        score -= warnings * 5

        score = max(0, min(100, score))

        if score >= 80:
            grade = 'A'
            summary = "Excellent trading performance. Maintain discipline and current strategy."
        elif score >= 65:
            grade = 'B'
            summary = "Good performance with room for improvement. Address warnings."
        elif score >= 50:
            grade = 'C'
            summary = "Average performance. Review strategy and risk management."
        elif score >= 35:
            grade = 'D'
            summary = "Below average. Significant improvements needed."
        else:
            grade = 'F'
            summary = "Critical issues detected. Consider pausing live trading."

        return {
            'health_score': score,
            'grade': grade,
            'summary': summary,
            'total_pnl': overview.get('total_pnl', 0),
            'win_rate': overview.get('win_rate', 0),
            'profit_factor': overview.get('profit_factor'),
            'total_trades': overview.get('total_trades', 0),
            'alerts_count': alerts,
            'warnings_count': warnings,
        }

    def _calculate_confidence_score(self, overview: Dict) -> float:
        """Calculate confidence in analysis based on sample size."""
        trades = overview.get('total_trades', 0)

        if trades < 10:
            return 20.0
        elif trades < 30:
            return 40.0
        elif trades < 50:
            return 60.0
        elif trades < 100:
            return 75.0
        elif trades < 200:
            return 85.0
        else:
            return 95.0


def get_trading_intelligence(broker: str = None) -> Dict[str, Any]:
    """
    Convenience function to get smart trading suggestions.

    Args:
        broker: Optional broker filter ('KOTAK' or 'ICICI')

    Returns:
        Dict with comprehensive trading analysis and recommendations
    """
    service = TradingIntelligenceService(broker=broker)
    return service.get_smart_suggestions()
