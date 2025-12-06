"""
Level 2 Deep-Dive Analysis Components

Comprehensive analyzers for fundamental, valuation, institutional, technical, and risk analysis
"""

import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)


class FinancialPerformanceAnalyzer:
    """Analyze financial performance metrics"""

    def analyze(self, stock_data, forecaster_data: Dict) -> Dict:
        """
        Comprehensive financial performance analysis

        Args:
            stock_data: TLStockData object
            forecaster_data: Forecaster CSV data

        Returns:
            dict: Financial analysis results
        """
        if not stock_data:
            return self._empty_analysis("No stock data available")

        analysis = {
            'profitability': self._analyze_profitability(stock_data),
            'revenue_analysis': self._analyze_revenue(stock_data),
            'earnings_quality': self._analyze_earnings(stock_data, forecaster_data),
            'cash_flow_analysis': self._analyze_cash_flow(stock_data),
            'balance_sheet_strength': self._analyze_balance_sheet(stock_data),
            'summary': None,
            'risk_factors': [],
            'opportunity_factors': []
        }

        # Generate summary
        analysis['summary'] = self._generate_summary(analysis)
        analysis['risk_factors'] = self._identify_risks(analysis)
        analysis['opportunity_factors'] = self._identify_opportunities(analysis)

        return analysis

    def _analyze_profitability(self, stock_data) -> Dict:
        """Analyze profitability metrics"""
        roe = stock_data.roe_annual_pct or 0
        sector_roe = stock_data.sector_return_on_equity_roe or roe
        roa = stock_data.roa_annual_pct or 0
        sector_roa = stock_data.sector_return_on_assets or roa
        margin = stock_data.operating_profit_margin_qtr_pct or 0
        margin_1yr_ago = stock_data.operating_profit_margin_qtr_1yr_ago_pct or margin

        return {
            'current_status': {
                'roe': round(roe, 2),
                'roe_vs_sector': round(roe - sector_roe, 2),
                'roe_interpretation': self._interpret_roe(roe, sector_roe),
                'roa': round(roa, 2),
                'roa_vs_sector': round(roa - sector_roa, 2),
                'operating_margin': round(margin, 2),
                'margin_trend': round(margin - margin_1yr_ago, 2),
                'margin_direction': 'IMPROVING' if margin > margin_1yr_ago else 'DECLINING'
            },
            'quality_score': self._calculate_profitability_score(roe, sector_roe, roa, sector_roa, margin, margin_1yr_ago),
            'trader_interpretation': self._profitability_trader_view(roe, sector_roe, margin, margin_1yr_ago)
        }

    def _analyze_revenue(self, stock_data) -> Dict:
        """Analyze revenue growth and quality"""
        qtr_yoy = stock_data.revenue_growth_qtr_yoy_pct or 0
        qtr_qoq = stock_data.revenue_qoq_growth_pct or 0
        annual_yoy = stock_data.revenue_growth_annual_yoy_pct or 0
        sector_qtr_yoy = stock_data.sector_revenue_growth_qtr_yoy_pct or qtr_yoy
        sector_annual = stock_data.sector_revenue_growth_annual_yoy_pct or annual_yoy

        return {
            'growth_metrics': {
                'qtr_yoy': round(qtr_yoy, 2),
                'qtr_qoq': round(qtr_qoq, 2),
                'annual_yoy': round(annual_yoy, 2),
                'ttm': stock_data.operating_revenue_ttm
            },
            'relative_performance': {
                'vs_sector_qtr': round(qtr_yoy - sector_qtr_yoy, 2),
                'vs_sector_annual': round(annual_yoy - sector_annual, 2),
                'outperforming_sector': qtr_yoy > sector_qtr_yoy
            },
            'momentum': 'ACCELERATING' if qtr_qoq > 0 and qtr_yoy > annual_yoy else 'STABLE' if qtr_yoy > 10 else 'DECELERATING',
            'quality_assessment': self._assess_revenue_quality(qtr_yoy, qtr_qoq, annual_yoy)
        }

    def _analyze_earnings(self, stock_data, forecaster_data) -> Dict:
        """Analyze earnings quality and surprises"""
        profit_qtr_yoy = stock_data.net_profit_qtr_growth_yoy_pct or 0
        profit_qtr_qoq = stock_data.net_profit_qoq_growth_pct or 0
        profit_annual = stock_data.net_profit_annual_yoy_growth_pct or 0
        sector_qtr = stock_data.sector_net_profit_growth_qtr_yoy_pct or profit_qtr_yoy
        eps_growth = stock_data.eps_ttm_growth_pct or 0

        # Check earnings surprises from forecaster data
        surprises = self._check_earnings_surprises(forecaster_data)

        return {
            'profit_growth': {
                'qtr_yoy': round(profit_qtr_yoy, 2),
                'qtr_qoq': round(profit_qtr_qoq, 2),
                'annual_yoy': round(profit_annual, 2)
            },
            'vs_sector': {
                'qtr': round(profit_qtr_yoy - sector_qtr, 2),
                'outperforming': profit_qtr_yoy > sector_qtr
            },
            'eps_analysis': {
                'basic_eps_ttm': stock_data.basic_eps_ttm,
                'eps_growth': round(eps_growth, 2)
            },
            'earnings_surprises': surprises,
            'quality_indicators': self._assess_earnings_quality(profit_qtr_yoy, eps_growth, surprises),
            'latest_result': stock_data.latest_financial_result,
            'result_date': stock_data.result_announced_date
        }

    def _analyze_cash_flow(self, stock_data) -> Dict:
        """Analyze cash flow strength"""
        ocf = stock_data.cash_from_operating_activity_annual or 0
        icf = stock_data.cash_from_investing_activity_annual or 0
        fcf_activity = stock_data.cash_from_financing_annual_activity or 0
        net_cf = stock_data.net_cash_flow_annual or 0

        # Calculate free cash flow (OCF - Capex, approximated)
        fcf = ocf + icf  # Simplified calculation

        return {
            'operating_cash': ocf,
            'investing_cash': icf,
            'financing_cash': fcf_activity,
            'net_cash_flow': net_cf,
            'free_cash_flow': fcf,
            'cash_generation': 'STRONG' if ocf > 0 and fcf > 0 else 'MODERATE' if ocf > 0 else 'WEAK',
            'interpretation': self._interpret_cash_flows(ocf, icf, fcf_activity, net_cf)
        }

    def _analyze_balance_sheet(self, stock_data) -> Dict:
        """Analyze balance sheet strength"""
        piotroski = stock_data.piotroski_score or 0

        return {
            'piotroski_score': piotroski,
            'piotroski_interpretation': self._interpret_piotroski(piotroski),
            'piotroski_grade': 'EXCELLENT' if piotroski >= 7 else 'GOOD' if piotroski >= 5 else 'WEAK'
        }

    def _interpret_roe(self, roe: float, sector_roe: float) -> str:
        """Interpret ROE"""
        if roe > sector_roe + 5:
            return "Significantly outperforming sector"
        elif roe > sector_roe:
            return "Outperforming sector"
        elif roe > 15:
            return "Healthy ROE"
        elif roe > 10:
            return "Moderate ROE"
        else:
            return "Weak ROE - caution advised"

    def _calculate_profitability_score(self, roe, sector_roe, roa, sector_roa, margin, margin_1yr_ago) -> int:
        """Calculate profitability quality score (0-100)"""
        score = 0

        # ROE scoring
        if roe > sector_roe + 5:
            score += 25
        elif roe > sector_roe:
            score += 15
        elif roe > 15:
            score += 10

        # ROA scoring
        if roa > sector_roa:
            score += 15

        # Margin scoring
        if margin > 20:
            score += 20
        elif margin > 10:
            score += 10

        # Margin trend
        if margin > margin_1yr_ago:
            score += 20
        elif margin > margin_1yr_ago * 0.95:
            score += 10

        return min(score, 100)

    def _profitability_trader_view(self, roe, sector_roe, margin, margin_1yr_ago) -> str:
        """Generate trader-friendly interpretation"""
        if roe > sector_roe and margin > margin_1yr_ago:
            return "🟢 STRONG: Company showing superior profitability with improving margins - bullish signal"
        elif roe > 15 and margin > 10:
            return "🟡 MODERATE: Decent profitability but watch for margin pressure"
        else:
            return "🔴 WEAK: Low profitability raises concerns about business quality"

    def _assess_revenue_quality(self, qtr_yoy, qtr_qoq, annual_yoy) -> str:
        """Assess revenue quality"""
        if qtr_yoy > 15 and qtr_qoq > 5:
            return "High quality - strong and accelerating growth"
        elif qtr_yoy > 10:
            return "Good quality - consistent growth"
        elif qtr_yoy > 0:
            return "Moderate quality - positive but slow growth"
        else:
            return "Poor quality - revenue decline"

    def _check_earnings_surprises(self, forecaster_data) -> Dict:
        """Check earnings surprise history"""
        surprises = {
            'eps_beats': [],
            'eps_misses': [],
            'revenue_beats': [],
            'revenue_misses': [],
            'consistency_score': 50  # Default
        }

        earnings_surprises = forecaster_data.get('earnings_surprises', {})

        # Count beats and misses
        beat_count = len([k for k in earnings_surprises.keys() if 'Beat' in k])
        miss_count = len([k for k in earnings_surprises.keys() if 'Missed' in k])

        if beat_count + miss_count > 0:
            surprises['consistency_score'] = int((beat_count / (beat_count + miss_count)) * 100)

        surprises['total_beats'] = beat_count
        surprises['total_misses'] = miss_count

        return surprises

    def _assess_earnings_quality(self, profit_growth, eps_growth, surprises) -> str:
        """Assess overall earnings quality"""
        if profit_growth > 20 and eps_growth > 15 and surprises.get('consistency_score', 0) > 70:
            return "Excellent - strong growth with consistent beats"
        elif profit_growth > 10 and eps_growth > 10:
            return "Good - healthy growth trajectory"
        elif profit_growth > 0:
            return "Fair - positive but modest growth"
        else:
            return "Poor - declining earnings"

    def _interpret_cash_flows(self, ocf, icf, fcf_activity, net_cf) -> str:
        """Interpret cash flow patterns"""
        if ocf > 0 and (ocf + icf) > 0:
            return "Strong - generating positive operational and free cash flow"
        elif ocf > 0:
            return "Moderate - positive operating cash but high capex"
        else:
            return "Weak - negative operating cash flow is concerning"

    def _interpret_piotroski(self, score: float) -> str:
        """Interpret Piotroski F-Score"""
        if score >= 7:
            return "Very Strong - Company shows high financial strength across multiple dimensions"
        elif score >= 5:
            return "Moderate - Company shows decent financial health"
        elif score >= 3:
            return "Weak - Company showing several red flags"
        else:
            return "Very Weak - Fundamental concerns across multiple areas"

    def _generate_summary(self, analysis: Dict) -> str:
        """Generate executive summary"""
        prof_score = analysis['profitability']['quality_score']
        revenue_momentum = analysis['revenue_analysis']['momentum']
        cash_gen = analysis['cash_flow_analysis']['cash_generation']
        piotroski_grade = analysis['balance_sheet_strength']['piotroski_grade']

        if prof_score > 70 and revenue_momentum == 'ACCELERATING' and cash_gen == 'STRONG':
            return "🟢 FUNDAMENTALLY STRONG: Company shows excellent financial health across all parameters"
        elif prof_score > 50 and cash_gen in ['STRONG', 'MODERATE']:
            return "🟡 FUNDAMENTALLY SOUND: Company shows good financial health with minor concerns"
        else:
            return "🔴 FUNDAMENTAL CONCERNS: Weak financial performance raises caution flags"

    def _identify_risks(self, analysis: Dict) -> List[str]:
        """Identify fundamental risk factors"""
        risks = []

        if analysis['profitability']['current_status']['margin_direction'] == 'DECLINING':
            risks.append("Declining operating margins may indicate pricing pressure or cost inflation")

        if analysis['revenue_analysis']['momentum'] == 'DECELERATING':
            risks.append("Decelerating revenue growth could signal market share loss or demand weakness")

        if analysis['cash_flow_analysis']['cash_generation'] == 'WEAK':
            risks.append("Weak cash generation may strain liquidity and limit growth investments")

        if analysis['balance_sheet_strength']['piotroski_score'] < 5:
            risks.append("Low Piotroski score indicates multiple fundamental weaknesses")

        if analysis['earnings_quality']['earnings_surprises'].get('total_misses', 0) > analysis['earnings_quality']['earnings_surprises'].get('total_beats', 0):
            risks.append("History of missing earnings estimates suggests execution challenges")

        return risks

    def _identify_opportunities(self, analysis: Dict) -> List[str]:
        """Identify opportunity factors"""
        opportunities = []

        if analysis['profitability']['current_status']['roe_vs_sector'] > 5:
            opportunities.append("Superior ROE vs sector indicates competitive advantage")

        if analysis['revenue_analysis']['momentum'] == 'ACCELERATING':
            opportunities.append("Accelerating revenue growth suggests strong demand environment")

        if analysis['cash_flow_analysis']['cash_generation'] == 'STRONG':
            opportunities.append("Strong cash generation provides flexibility for growth and returns")

        if analysis['balance_sheet_strength']['piotroski_score'] >= 7:
            opportunities.append("High Piotroski score indicates robust financial foundation")

        if analysis['profitability']['current_status']['margin_direction'] == 'IMPROVING':
            opportunities.append("Improving margins signal operational efficiency gains")

        return opportunities

    def _empty_analysis(self, reason: str) -> Dict:
        """Return empty analysis structure"""
        return {
            'error': reason,
            'profitability': {},
            'revenue_analysis': {},
            'earnings_quality': {},
            'cash_flow_analysis': {},
            'balance_sheet_strength': {},
            'summary': f"Analysis unavailable: {reason}",
            'risk_factors': [],
            'opportunity_factors': []
        }


class ValuationDeepDive:
    """Comprehensive valuation analysis"""

    def analyze(self, stock_data) -> Dict:
        """
        Perform deep valuation analysis

        Args:
            stock_data: TLStockData object

        Returns:
            dict: Valuation analysis
        """
        if not stock_data:
            return self._empty_analysis("No stock data available")

        analysis = {
            'absolute_valuation': self._analyze_absolute_valuation(stock_data),
            'relative_valuation': self._analyze_relative_valuation(stock_data),
            'valuation_summary': None
        }

        analysis['valuation_summary'] = self._generate_valuation_summary(analysis)

        return analysis

    def _analyze_absolute_valuation(self, stock_data) -> Dict:
        """Analyze absolute valuation metrics"""
        current_pe = stock_data.pe_ttm_price_to_earnings or 0
        forward_pe = stock_data.forecaster_estimates_1y_forward_pe or current_pe
        pe_3yr = stock_data.pe_3yr_average or current_pe
        pe_5yr = stock_data.pe_5yr_average or current_pe
        pe_percentile = stock_data.pctdays_traded_below_current_pe_price_to_earnings or 50

        peg = stock_data.peg_ttm_pe_to_growth or 0
        forward_peg = stock_data.forecaster_estimates_1y_forward_peg or peg

        pb = stock_data.price_to_book_value or 0
        pb_percentile = stock_data.pctdays_traded_below_current_price_to_book_value or 50

        return {
            'pe_analysis': {
                'current_pe': round(current_pe, 2),
                'forward_pe': round(forward_pe, 2),
                'historical_context': {
                    '3yr_avg': round(pe_3yr, 2),
                    '5yr_avg': round(pe_5yr, 2),
                    'current_vs_3yr_pct': round(((current_pe / pe_3yr) - 1) * 100, 2) if pe_3yr > 0 else 0,
                    'percentile': round(pe_percentile, 2),
                    'interpretation': self._interpret_pe_percentile(pe_percentile)
                },
                'valuation_signal': self._pe_signal(current_pe, pe_3yr, pe_percentile)
            },
            'peg_analysis': {
                'current_peg': round(peg, 2),
                'forward_peg': round(forward_peg, 2),
                'interpretation': 'UNDERVALUED' if peg < 1 and peg > 0 else 'FAIRLY_VALUED' if peg < 1.5 else 'OVERVALUED'
            },
            'price_to_book': {
                'current': round(pb, 2),
                'percentile': round(pb_percentile, 2),
                'interpretation': self._interpret_pb_ratio(pb, pb_percentile)
            }
        }

    def _analyze_relative_valuation(self, stock_data) -> Dict:
        """Analyze relative valuation vs sector/industry"""
        current_pe = stock_data.pe_ttm_price_to_earnings or 0
        sector_pe = stock_data.sector_pe_ttm or current_pe
        industry_pe = stock_data.industry_pe_ttm or current_pe

        current_peg = stock_data.peg_ttm_pe_to_growth or 0
        sector_peg = stock_data.sector_peg_ttm or current_peg
        industry_peg = stock_data.industry_peg_ttm or current_peg

        current_pb = stock_data.price_to_book_value or 0
        sector_pb = stock_data.sector_price_to_book_ttm or current_pb
        industry_pb = stock_data.industry_price_to_book_ttm or current_pb

        return {
            'vs_sector': {
                'pe_premium_discount': round(((current_pe / sector_pe) - 1) * 100, 2) if sector_pe > 0 else 0,
                'peg_premium_discount': round(((current_peg / sector_peg) - 1) * 100, 2) if sector_peg > 0 else 0,
                'pb_premium_discount': round(((current_pb / sector_pb) - 1) * 100, 2) if sector_pb > 0 else 0,
                'trading_at': 'PREMIUM' if current_pe > sector_pe else 'DISCOUNT'
            },
            'vs_industry': {
                'pe_ratio': round(current_pe / industry_pe, 2) if industry_pe > 0 else 1,
                'peg_ratio': round(current_peg / industry_peg, 2) if industry_peg > 0 else 1,
                'pb_ratio': round(current_pb / industry_pb, 2) if industry_pb > 0 else 1
            },
            'assessment': self._assess_relative_valuation(current_pe, sector_pe, current_peg, sector_peg)
        }

    def _interpret_pe_percentile(self, percentile: float) -> str:
        """Interpret P/E percentile"""
        if percentile < 25:
            return "Trading in bottom quartile of historical range - potential value opportunity"
        elif percentile < 50:
            return "Trading below historical median - reasonable valuation"
        elif percentile < 75:
            return "Trading above historical median - getting expensive"
        else:
            return "Trading in top quartile - expensive by historical standards"

    def _pe_signal(self, current_pe, avg_pe, percentile) -> str:
        """Generate P/E valuation signal"""
        if current_pe < avg_pe * 0.9 and percentile < 30:
            return "🟢 ATTRACTIVE - Trading at significant discount to historical average"
        elif current_pe < avg_pe and percentile < 50:
            return "🟡 FAIR - Reasonable valuation relative to history"
        elif current_pe > avg_pe * 1.2 and percentile > 70:
            return "🔴 EXPENSIVE - Trading at premium to historical average"
        else:
            return "🟡 NEUTRAL - Around historical average"

    def _interpret_pb_ratio(self, pb: float, percentile: float) -> str:
        """Interpret P/B ratio"""
        if pb < 2 and percentile < 30:
            return "Attractive P/B with favorable historical positioning"
        elif pb < 3:
            return "Reasonable P/B valuation"
        elif pb < 5:
            return "Elevated P/B - premium valuation"
        else:
            return "Very high P/B - significant premium to book value"

    def _assess_relative_valuation(self, current_pe, sector_pe, current_peg, sector_peg) -> str:
        """Assess relative valuation"""
        pe_premium = ((current_pe / sector_pe) - 1) * 100 if sector_pe > 0 else 0
        peg_premium = ((current_peg / sector_peg) - 1) * 100 if sector_peg > 0 else 0

        if pe_premium < -10 and peg_premium < 0:
            return "Trading at significant discount to sector - potential value play"
        elif pe_premium < 0:
            return "Trading at discount to sector - reasonable relative valuation"
        elif pe_premium < 20:
            return "Trading at modest premium to sector - may be justified by superior fundamentals"
        else:
            return "Trading at significant premium to sector - verify if justified"

    def _generate_valuation_summary(self, analysis: Dict) -> Dict:
        """Generate valuation summary"""
        pe_signal = analysis['absolute_valuation']['pe_analysis']['valuation_signal']
        peg_interpretation = analysis['absolute_valuation']['peg_analysis']['interpretation']
        relative_assessment = analysis['relative_valuation']['assessment']

        # Determine overall valuation
        if '🟢' in pe_signal and peg_interpretation == 'UNDERVALUED':
            overall = "UNDERVALUED - Attractive entry point from valuation perspective"
        elif '🔴' in pe_signal or peg_interpretation == 'OVERVALUED':
            overall = "OVERVALUED - Exercise caution, valuation appears stretched"
        else:
            overall = "FAIRLY VALUED - Valuation in reasonable range"

        return {
            'overall_assessment': overall,
            'key_insights': [pe_signal, f"PEG: {peg_interpretation}", relative_assessment]
        }

    def _empty_analysis(self, reason: str) -> Dict:
        """Return empty analysis"""
        return {
            'error': reason,
            'absolute_valuation': {},
            'relative_valuation': {},
            'valuation_summary': {'overall_assessment': f"Analysis unavailable: {reason}", 'key_insights': []}
        }


def calculate_support_resistance(symbol: str) -> Dict:
    """
    Calculate support and resistance levels using pivot points and historical data

    Args:
        symbol: Stock code/symbol

    Returns:
        dict: Support and resistance levels
            {
                'success': bool,
                'support_levels': List[float],
                'resistance_levels': List[float],
                'pivot_point': float
            }
    """
    try:
        from apps.brokers.models import HistoricalPrice

        # Get last 30 days of historical data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        # Fetch historical prices
        prices = HistoricalPrice.objects.filter(
            stock_code=symbol,
            product_type='cash',
            datetime__gte=start_date,
            datetime__lte=end_date
        ).order_by('-datetime')[:30]

        if not prices.exists():
            logger.warning(f"No historical price data found for {symbol}")
            return {
                'success': False,
                'message': f'No historical data available for {symbol}',
                'support_levels': [],
                'resistance_levels': []
            }

        # Get high, low, close from most recent data
        latest = prices.first()
        high = float(latest.high or 0)
        low = float(latest.low or 0)
        close = float(latest.close or 0)

        if high == 0 or low == 0 or close == 0:
            return {
                'success': False,
                'message': 'Invalid price data',
                'support_levels': [],
                'resistance_levels': []
            }

        # Calculate pivot point (standard method)
        pivot = (high + low + close) / 3

        # Calculate support and resistance levels
        # R1 = 2*PP - Low
        # R2 = PP + (High - Low)
        # R3 = High + 2*(PP - Low)
        # S1 = 2*PP - High
        # S2 = PP - (High - Low)
        # S3 = Low - 2*(High - PP)

        r1 = 2 * pivot - low
        r2 = pivot + (high - low)
        r3 = high + 2 * (pivot - low)

        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        s3 = low - 2 * (high - pivot)

        # Also identify swing highs and lows from last 30 days
        swing_highs = []
        swing_lows = []

        price_list = list(prices)
        for i in range(1, len(price_list) - 1):
            current_high = float(price_list[i].high or 0)
            current_low = float(price_list[i].low or 0)
            prev_high = float(price_list[i-1].high or 0)
            next_high = float(price_list[i+1].high or 0)
            prev_low = float(price_list[i-1].low or 0)
            next_low = float(price_list[i+1].low or 0)

            # Swing high: higher than both neighbors
            if current_high > prev_high and current_high > next_high:
                swing_highs.append(current_high)

            # Swing low: lower than both neighbors
            if current_low < prev_low and current_low < next_low:
                swing_lows.append(current_low)

        # Combine and deduplicate resistance levels
        resistance_levels = sorted(list(set([r1, r2, r3] + swing_highs)))
        # Keep only levels above current price
        resistance_levels = [r for r in resistance_levels if r > close][:5]

        # Combine and deduplicate support levels
        support_levels = sorted(list(set([s1, s2, s3] + swing_lows)), reverse=True)
        # Keep only levels below current price
        support_levels = [s for s in support_levels if s < close][:5]

        return {
            'success': True,
            'support_levels': [round(s, 2) for s in support_levels],
            'resistance_levels': [round(r, 2) for r in resistance_levels],
            'pivot_point': round(pivot, 2),
            'current_price': round(close, 2)
        }

    except Exception as e:
        logger.error(f"Error calculating support/resistance for {symbol}: {e}", exc_info=True)
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'support_levels': [],
            'resistance_levels': []
        }


def analyze_sector_strength(symbol: str) -> Dict:
    """
    Analyze sector strength for a given stock

    Args:
        symbol: Stock code/symbol

    Returns:
        dict: Sector strength analysis
            {
                'success': bool,
                'score': int (0-100),
                'status': str ('STRONG', 'NEUTRAL', 'WEAK'),
                'sector': str,
                'details': dict
            }
    """
    try:
        from apps.data.models import TLStockData

        # Try to find stock data (TLStockData uses 'nsecode' field)
        stock_data = TLStockData.objects.filter(nsecode=symbol).first()

        if not stock_data:
            logger.warning(f"No TLStockData found for {symbol}")
            return {
                'success': False,
                'message': f'No stock data found for {symbol}',
                'score': 50,
                'status': 'NEUTRAL'
            }

        # Calculate sector strength score based on available metrics
        score = 50  # Default neutral

        # Check sector performance metrics
        sector_pe = stock_data.sector_pe_ttm or 0
        sector_roe = stock_data.sector_return_on_equity_roe or 0
        sector_revenue_growth = stock_data.sector_revenue_growth_qtr_yoy_pct or 0
        sector_profit_growth = stock_data.sector_net_profit_growth_qtr_yoy_pct or 0

        # Stock vs sector metrics
        stock_pe = stock_data.pe_ttm_price_to_earnings or 0
        stock_roe = stock_data.roe_annual_pct or 0
        stock_revenue_growth = stock_data.revenue_growth_qtr_yoy_pct or 0
        stock_profit_growth = stock_data.net_profit_qtr_growth_yoy_pct or 0

        # Sector health indicators
        if sector_revenue_growth > 15:
            score += 15
        elif sector_revenue_growth > 10:
            score += 10
        elif sector_revenue_growth > 5:
            score += 5
        elif sector_revenue_growth < 0:
            score -= 10

        if sector_profit_growth > 15:
            score += 15
        elif sector_profit_growth > 10:
            score += 10
        elif sector_profit_growth > 5:
            score += 5
        elif sector_profit_growth < 0:
            score -= 10

        if sector_roe > 20:
            score += 10
        elif sector_roe > 15:
            score += 5

        # Stock performance relative to sector
        if stock_revenue_growth > sector_revenue_growth:
            score += 10

        if stock_profit_growth > sector_profit_growth:
            score += 10

        # Cap score at 0-100
        score = max(0, min(100, score))

        # Determine status
        if score >= 70:
            status = 'STRONG'
        elif score >= 40:
            status = 'NEUTRAL'
        else:
            status = 'WEAK'

        return {
            'success': True,
            'score': score,
            'status': status,
            'sector': stock_data.sector_name or 'Unknown',
            'details': {
                'sector_revenue_growth': round(sector_revenue_growth, 2),
                'sector_profit_growth': round(sector_profit_growth, 2),
                'sector_roe': round(sector_roe, 2),
                'stock_vs_sector_revenue': round(stock_revenue_growth - sector_revenue_growth, 2),
                'stock_vs_sector_profit': round(stock_profit_growth - sector_profit_growth, 2),
                'outperforming_sector': stock_revenue_growth > sector_revenue_growth and stock_profit_growth > sector_profit_growth
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing sector strength for {symbol}: {e}", exc_info=True)
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'score': 50,
            'status': 'NEUTRAL'
        }
