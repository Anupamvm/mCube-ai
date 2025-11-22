"""
Level 2 Deep-Dive Analysis Components - Part 2

Institutional behavior, technical analysis, and risk assessment
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class InstitutionalBehaviorAnalyzer:
    """Analyze institutional and smart money behavior"""

    def analyze(self, stock_data, contract_stock_data) -> Dict:
        """
        Analyze institutional behavior patterns

        Args:
            stock_data: TLStockData object
            contract_stock_data: ContractStockData object

        Returns:
            dict: Institutional behavior analysis
        """
        if not stock_data:
            return self._empty_analysis("No stock data available")

        analysis = {
            'promoter_analysis': self._analyze_promoter(stock_data),
            'fii_activity': self._analyze_fii(stock_data),
            'mutual_fund_activity': self._analyze_mf(stock_data),
            'combined_institutional': self._analyze_combined_institutional(stock_data),
            'fo_positioning': self._analyze_fo_positioning(contract_stock_data) if contract_stock_data else {},
            'summary': None
        }

        analysis['summary'] = self._generate_summary(analysis)

        return analysis

    def _analyze_promoter(self, stock_data) -> Dict:
        """Analyze promoter holding patterns"""
        current_holding = stock_data.promoter_holding_latest_pct or 0
        qoq_change = stock_data.promoter_holding_change_qoq_pct or 0
        yr1_change = stock_data.promoter_holding_change_4qtr_pct or 0
        yr2_change = stock_data.promoter_holding_change_8qtr_pct or 0

        pledge = stock_data.promoter_pledge_pct_qtr or 0
        pledge_change = stock_data.promoter_pledge_change_qoq_pct or 0

        return {
            'current_holding': round(current_holding, 2),
            'trend_analysis': {
                'qoq_change': round(qoq_change, 2),
                '1yr_change': round(yr1_change, 2),
                '2yr_change': round(yr2_change, 2),
                'trend': self._determine_trend([qoq_change, yr1_change, yr2_change])
            },
            'pledge_analysis': {
                'current_pledge': round(pledge, 2),
                'pledge_change': round(pledge_change, 2),
                'risk_level': self._assess_pledge_risk(pledge)
            },
            'interpretation': self._interpret_promoter_behavior(qoq_change, yr1_change, pledge),
            'confidence_signal': self._calculate_promoter_confidence(qoq_change, yr1_change, pledge)
        }

    def _analyze_fii(self, stock_data) -> Dict:
        """Analyze FII activity"""
        current_holding = stock_data.fii_holding_current_qtr_pct or 0
        qoq_change = stock_data.fii_holding_change_qoq_pct or 0
        yr1_change = stock_data.fii_holding_change_4qtr_pct or 0
        yr2_change = stock_data.fii_holding_change_8qtr_pct or 0

        return {
            'current_holding': round(current_holding, 2),
            'flow_analysis': {
                'qoq': round(qoq_change, 2),
                '1yr': round(yr1_change, 2),
                '2yr': round(yr2_change, 2),
                'momentum': self._calculate_momentum([qoq_change, yr1_change, yr2_change])
            },
            'interpretation': self._interpret_fii_behavior(qoq_change, yr1_change),
            'signal_strength': self._calculate_signal_strength(qoq_change, yr1_change)
        }

    def _analyze_mf(self, stock_data) -> Dict:
        """Analyze mutual fund activity"""
        current_holding = stock_data.mf_holding_current_qtr_pct or 0
        m1_change = stock_data.mf_holding_change_1month_pct or 0
        m2_change = stock_data.mf_holding_change_2month_pct or 0
        m3_change = stock_data.mf_holding_change_3month_pct or 0
        qoq_change = stock_data.mf_holding_change_qoq_pct or 0

        return {
            'current_holding': round(current_holding, 2),
            'recent_activity': {
                '1_month': round(m1_change, 2),
                '2_month': round(m2_change, 2),
                '3_month': round(m3_change, 2),
                'qoq': round(qoq_change, 2)
            },
            'trend': self._determine_trend([m1_change, m2_change, m3_change, qoq_change]),
            'accumulation_phase': self._identify_accumulation_distribution([m1_change, m2_change, m3_change])
        }

    def _analyze_combined_institutional(self, stock_data) -> Dict:
        """Analyze combined institutional behavior"""
        total_holding = stock_data.institutional_holding_current_qtr_pct or 0
        qoq_change = stock_data.institutional_holding_change_qoq_pct or 0

        fii_change = stock_data.fii_holding_change_qoq_pct or 0
        mf_change = stock_data.mf_holding_change_qoq_pct or 0

        return {
            'total_holding': round(total_holding, 2),
            'combined_trend': self._analyze_combined_trend(fii_change, mf_change),
            'smart_money_signal': self._calculate_smart_money_indicator(fii_change, mf_change, qoq_change)
        }

    def _analyze_fo_positioning(self, contract_stock_data) -> Dict:
        """Analyze F&O positioning"""
        if not contract_stock_data:
            return {}

        pcr_oi = contract_stock_data.fno_pcr_oi or 0
        pcr_oi_change = contract_stock_data.fno_pcr_oi_change_pct or 0
        pcr_vol = contract_stock_data.fno_pcr_vol or 0
        pcr_vol_change = contract_stock_data.fno_pcr_vol_change_pct or 0

        total_oi = contract_stock_data.fno_total_oi or 0
        oi_change = contract_stock_data.fno_total_oi_change_pct or 0
        call_oi_change = contract_stock_data.fno_call_oi_change_pct or 0
        put_oi_change = contract_stock_data.fno_put_oi_change_pct or 0

        mwpl = contract_stock_data.fno_mwpl_pct or 0
        rollover_cost = contract_stock_data.fno_rollover_cost_pct or 0
        rollover_pct = contract_stock_data.fno_rollover_pct or 0

        return {
            'pcr_analysis': {
                'oi_pcr': round(pcr_oi, 3),
                'oi_pcr_change': round(pcr_oi_change, 2),
                'volume_pcr': round(pcr_vol, 3),
                'volume_pcr_change': round(pcr_vol_change, 2),
                'interpretation': self._interpret_pcr(pcr_oi, pcr_vol)
            },
            'open_interest': {
                'total_oi': total_oi,
                'oi_change': round(oi_change, 2),
                'call_oi_change': round(call_oi_change, 2),
                'put_oi_change': round(put_oi_change, 2),
                'buildup': self._identify_oi_buildup(oi_change, call_oi_change, put_oi_change)
            },
            'mwpl_analysis': {
                'current': round(mwpl, 2),
                'risk': 'HIGH' if mwpl > 80 else 'MODERATE' if mwpl > 60 else 'NORMAL'
            },
            'rollover': {
                'cost_pct': round(rollover_cost, 2),
                'rollover_pct': round(rollover_pct, 2),
                'interpretation': self._interpret_rollover(rollover_cost, rollover_pct)
            }
        }

    def _determine_trend(self, changes: List[float]) -> str:
        """Determine overall trend from changes"""
        positive = sum(1 for x in changes if x > 0)
        if positive >= len(changes) * 0.7:
            return 'INCREASING'
        elif positive <= len(changes) * 0.3:
            return 'DECREASING'
        else:
            return 'STABLE'

    def _calculate_momentum(self, changes: List[float]) -> str:
        """Calculate momentum from changes"""
        if len(changes) < 2:
            return 'NEUTRAL'

        # Check if recent change is stronger
        if changes[0] > changes[-1]:
            return 'ACCELERATING'
        elif changes[0] < changes[-1]:
            return 'DECELERATING'
        else:
            return 'STABLE'

    def _assess_pledge_risk(self, pledge: float) -> str:
        """Assess pledging risk"""
        if pledge == 0:
            return 'NONE'
        elif pledge < 20:
            return 'LOW'
        elif pledge < 50:
            return 'MODERATE'
        else:
            return 'HIGH - Significant concern'

    def _interpret_promoter_behavior(self, qoq_change: float, yr1_change: float, pledge: float) -> str:
        """Interpret promoter behavior"""
        if qoq_change > 0 and yr1_change > 0 and pledge < 20:
            return "🟢 BULLISH: Promoters increasing stake with low pledging - shows strong confidence"
        elif qoq_change < 0 or yr1_change < -2:
            return "🔴 BEARISH: Promoters reducing stake - potential red flag"
        elif pledge > 50:
            return "🔴 RISKY: High promoter pledging raises concerns"
        else:
            return "🟡 NEUTRAL: Stable promoter holding pattern"

    def _calculate_promoter_confidence(self, qoq_change: float, yr1_change: float, pledge: float) -> str:
        """Calculate promoter confidence level"""
        score = 0
        if qoq_change > 0:
            score += 30
        if yr1_change > 0:
            score += 30
        if pledge < 20:
            score += 40

        if score >= 70:
            return 'HIGH'
        elif score >= 40:
            return 'MODERATE'
        else:
            return 'LOW'

    def _interpret_fii_behavior(self, qoq_change: float, yr1_change: float) -> str:
        """Interpret FII behavior"""
        if qoq_change > 1 and yr1_change > 2:
            return "🟢 STRONG BUYING: Consistent FII accumulation - positive signal"
        elif qoq_change > 0:
            return "🟡 MODERATE BUYING: FII showing interest"
        elif qoq_change < -1 and yr1_change < -2:
            return "🔴 STRONG SELLING: FII exiting - caution advised"
        elif qoq_change < 0:
            return "🟡 MODERATE SELLING: FII reducing positions"
        else:
            return "🟡 NEUTRAL: No significant FII activity"

    def _calculate_signal_strength(self, qoq_change: float, yr1_change: float) -> str:
        """Calculate signal strength"""
        if abs(qoq_change) > 2 or abs(yr1_change) > 4:
            return 'STRONG'
        elif abs(qoq_change) > 0.5 or abs(yr1_change) > 1:
            return 'MODERATE'
        else:
            return 'WEAK'

    def _identify_accumulation_distribution(self, changes: List[float]) -> str:
        """Identify accumulation or distribution phase"""
        avg_change = sum(changes) / len(changes) if changes else 0

        if avg_change > 0.5:
            return 'ACCUMULATION'
        elif avg_change < -0.5:
            return 'DISTRIBUTION'
        else:
            return 'NEUTRAL'

    def _analyze_combined_trend(self, fii_change: float, mf_change: float) -> str:
        """Analyze combined institutional trend"""
        if fii_change > 0 and mf_change > 0:
            return 'BROAD BUYING - Both FII and MF accumulating'
        elif fii_change < 0 and mf_change < 0:
            return 'BROAD SELLING - Both FII and MF reducing'
        elif fii_change > 0 and mf_change < 0:
            return 'MIXED - FII buying, MF selling'
        elif fii_change < 0 and mf_change > 0:
            return 'MIXED - MF buying, FII selling'
        else:
            return 'NEUTRAL - No significant activity'

    def _calculate_smart_money_indicator(self, fii_change: float, mf_change: float, total_change: float) -> str:
        """Calculate smart money indicator"""
        if fii_change > 1 and mf_change > 1 and total_change > 2:
            return "🟢 STRONG BUY: Smart money aggressively accumulating"
        elif fii_change > 0 and mf_change > 0:
            return "🟡 BUY: Smart money showing interest"
        elif fii_change < -1 and mf_change < -1:
            return "🔴 STRONG SELL: Smart money exiting"
        elif fii_change < 0 and mf_change < 0:
            return "🟡 SELL: Smart money reducing exposure"
        else:
            return "⚪ NEUTRAL: Mixed signals"

    def _interpret_pcr(self, pcr_oi: float, pcr_vol: float) -> str:
        """Interpret Put-Call Ratio"""
        if pcr_oi > 1.2 or pcr_vol > 1.2:
            return "High put activity - Bearish sentiment (Contrarian Bullish)"
        elif pcr_oi < 0.8 or pcr_vol < 0.8:
            return "High call activity - Bullish sentiment (Contrarian Bearish)"
        else:
            return "Balanced put-call ratio - Neutral sentiment"

    def _identify_oi_buildup(self, oi_change: float, call_change: float, put_change: float) -> str:
        """Identify OI buildup pattern"""
        if call_change > 10 and oi_change > 10:
            return "LONG BUILDUP - Price rising with OI increase (Bullish)"
        elif put_change > 10 and oi_change > 10:
            return "SHORT BUILDUP - Price falling with OI increase (Bearish)"
        elif call_change < -10:
            return "LONG UNWINDING - Call positions being closed"
        elif put_change < -10:
            return "SHORT COVERING - Put positions being closed"
        else:
            return "NEUTRAL - No clear buildup pattern"

    def _interpret_rollover(self, rollover_cost: float, rollover_pct: float) -> str:
        """Interpret rollover data"""
        if rollover_pct > 70 and abs(rollover_cost) < 1:
            return "High rollover at low cost - Bullish continuation expected"
        elif rollover_pct < 50:
            return "Low rollover - Possible position unwinding"
        elif abs(rollover_cost) > 2:
            return "High rollover cost - Expensive to carry positions"
        else:
            return "Normal rollover activity"

    def _generate_summary(self, analysis: Dict) -> str:
        """Generate institutional behavior summary"""
        promoter_conf = analysis['promoter_analysis'].get('confidence_signal', 'MODERATE')
        fii_interp = analysis['fii_activity'].get('interpretation', '')
        mf_phase = analysis['mutual_fund_activity'].get('accumulation_phase', 'NEUTRAL')
        smart_money = analysis['combined_institutional'].get('smart_money_signal', '')

        if promoter_conf == 'HIGH' and '🟢' in smart_money:
            return "🟢 STRONG INSTITUTIONAL SUPPORT: All institutional indicators bullish"
        elif promoter_conf == 'LOW' or '🔴' in smart_money:
            return "🔴 INSTITUTIONAL CONCERNS: Weak institutional support raises red flags"
        else:
            return "🟡 MIXED INSTITUTIONAL SIGNALS: Monitor for clearer trend"

    def _empty_analysis(self, reason: str) -> Dict:
        """Return empty analysis"""
        return {
            'error': reason,
            'promoter_analysis': {},
            'fii_activity': {},
            'mutual_fund_activity': {},
            'combined_institutional': {},
            'fo_positioning': {},
            'summary': f"Analysis unavailable: {reason}"
        }


class TechnicalDeepDive:
    """Deep technical analysis"""

    def analyze(self, stock_data) -> Dict:
        """
        Perform comprehensive technical analysis

        Args:
            stock_data: TLStockData object

        Returns:
            dict: Technical analysis
        """
        if not stock_data:
            return self._empty_analysis("No stock data available")

        analysis = {
            'trend_analysis': self._analyze_trends(stock_data),
            'momentum_indicators': self._analyze_momentum(stock_data),
            'volatility_analysis': self._analyze_volatility(stock_data),
            'price_action': self._analyze_price_action(stock_data),
            'volume_analysis': self._analyze_volume(stock_data),
            'summary': None
        }

        analysis['summary'] = self._generate_summary(analysis)

        return analysis

    def _analyze_trends(self, stock_data) -> Dict:
        """Analyze trend using moving averages and support/resistance"""
        current_price = stock_data.current_price or 0

        # Moving averages
        sma_5 = stock_data.day5_sma or 0
        sma_30 = stock_data.day30_sma or 0
        sma_50 = stock_data.day50_sma or 0
        sma_100 = stock_data.day100_sma or 0
        sma_200 = stock_data.day200_sma or 0

        # Check alignment
        above_sma_count = sum([
            current_price > sma_5 if sma_5 > 0 else False,
            current_price > sma_30 if sma_30 > 0 else False,
            current_price > sma_50 if sma_50 > 0 else False,
            current_price > sma_100 if sma_100 > 0 else False,
            current_price > sma_200 if sma_200 > 0 else False
        ])

        # Support/Resistance
        pivot = stock_data.pivot_point or current_price
        s1 = stock_data.first_support_s1 or 0
        r1 = stock_data.first_resistance_r1 or 0

        return {
            'moving_averages': {
                'sma_5': round(sma_5, 2),
                'sma_30': round(sma_30, 2),
                'sma_50': round(sma_50, 2),
                'sma_100': round(sma_100, 2),
                'sma_200': round(sma_200, 2),
                'above_sma_count': above_sma_count,
                'alignment': 'BULLISH' if above_sma_count >= 4 else 'BEARISH' if above_sma_count <= 1 else 'NEUTRAL'
            },
            'support_resistance': {
                'pivot': round(pivot, 2),
                's1': round(s1, 2),
                'r1': round(r1, 2),
                's1_distance_pct': round(stock_data.first_support_s1_to_price_diff_pct or 0, 2),
                'r1_distance_pct': round(stock_data.first_resistance_r1_to_price_diff_pct or 0, 2),
                'position': self._determine_price_position(current_price, s1, r1, pivot)
            },
            'primary_trend': self._determine_primary_trend(above_sma_count, current_price, sma_200)
        }

    def _analyze_momentum(self, stock_data) -> Dict:
        """Analyze momentum indicators"""
        rsi = stock_data.day_rsi or 50
        macd = stock_data.day_macd or 0
        macd_signal = stock_data.day_macd_signal_line or 0
        mfi = stock_data.day_mfi or 50
        adx = stock_data.day_adx or 0
        roc21 = stock_data.day_roc21 or 0

        return {
            'rsi': {
                'value': round(rsi, 2),
                'zone': 'OVERBOUGHT' if rsi > 70 else 'OVERSOLD' if rsi < 30 else 'NEUTRAL',
                'signal': self._interpret_rsi(rsi)
            },
            'macd': {
                'macd': round(macd, 4),
                'signal': round(macd_signal, 4),
                'histogram': round(macd - macd_signal, 4),
                'crossover': 'BULLISH' if macd > macd_signal else 'BEARISH'
            },
            'mfi': {
                'value': round(mfi, 2),
                'interpretation': 'OVERBOUGHT' if mfi > 80 else 'OVERSOLD' if mfi < 20 else 'NEUTRAL'
            },
            'adx': {
                'value': round(adx, 2),
                'trend_strength': 'STRONG' if adx > 25 else 'WEAK'
            },
            'roc': {
                '21_day': round(roc21, 2),
                'momentum': 'POSITIVE' if roc21 > 0 else 'NEGATIVE'
            }
        }

    def _analyze_volatility(self, stock_data) -> Dict:
        """Analyze volatility metrics"""
        atr = stock_data.day_atr or 0
        beta_1m = stock_data.beta_1month or 1
        beta_3m = stock_data.beta_3month or 1
        beta_1y = stock_data.beta_1year or 1

        return {
            'atr': round(atr, 2),
            'beta_analysis': {
                '1m': round(beta_1m, 2),
                '3m': round(beta_3m, 2),
                '1y': round(beta_1y, 2),
                'stability': self._assess_beta_stability([beta_1m, beta_3m, beta_1y]),
                'market_correlation': 'HIGH' if beta_1y > 1.2 else 'LOW' if beta_1y < 0.8 else 'MODERATE'
            }
        }

    def _analyze_price_action(self, stock_data) -> Dict:
        """Analyze price action across timeframes"""
        return {
            'performance': {
                'day': round(stock_data.day_change_pct or 0, 2),
                'week': round(stock_data.week_change_pct or 0, 2),
                'month': round(stock_data.month_change_pct or 0, 2),
                'quarter': round(stock_data.qtr_change_pct or 0, 2),
                'year': round(stock_data.one_year_change_pct or 0, 2)
            },
            'ranges': {
                'day_range': f"{stock_data.day_low} - {stock_data.day_high}",
                'week_range': f"{stock_data.week_low} - {stock_data.week_high}",
                'year_range': f"{stock_data.one_year_low} - {stock_data.one_year_high}"
            },
            'trend_consistency': self._check_trend_consistency(stock_data)
        }

    def _analyze_volume(self, stock_data) -> Dict:
        """Analyze volume patterns"""
        day_vol = stock_data.day_volume or 0
        week_avg = stock_data.week_volume_avg or day_vol
        month_avg = stock_data.month_volume_avg or day_vol

        delivery_pct = stock_data.delivery_volume_pct_eod or 0
        vwap = stock_data.vwap_day or stock_data.current_price or 0
        current_price = stock_data.current_price or 0

        return {
            'current_volume': day_vol,
            'relative_volume': {
                'vs_week_avg': round(day_vol / week_avg, 2) if week_avg > 0 else 0,
                'vs_month_avg': round(day_vol / month_avg, 2) if month_avg > 0 else 0
            },
            'delivery_analysis': {
                'delivery_pct': round(delivery_pct, 2),
                'interpretation': self._interpret_delivery(delivery_pct)
            },
            'vwap': {
                'value': round(vwap, 2),
                'position': 'ABOVE' if current_price > vwap else 'BELOW',
                'signal': '🟢 Bullish' if current_price > vwap else '🔴 Bearish'
            }
        }

    def _determine_price_position(self, price: float, s1: float, r1: float, pivot: float) -> str:
        """Determine price position relative to levels"""
        if price > r1:
            return "ABOVE_RESISTANCE"
        elif price > pivot:
            return "ABOVE_PIVOT"
        elif price > s1:
            return "ABOVE_SUPPORT"
        else:
            return "BELOW_SUPPORT"

    def _determine_primary_trend(self, above_sma_count: int, price: float, sma_200: float) -> str:
        """Determine primary trend"""
        if above_sma_count >= 4 and price > sma_200:
            return "STRONG UPTREND"
        elif above_sma_count >= 3:
            return "UPTREND"
        elif above_sma_count <= 1 and price < sma_200:
            return "STRONG DOWNTREND"
        elif above_sma_count <= 2:
            return "DOWNTREND"
        else:
            return "SIDEWAYS"

    def _interpret_rsi(self, rsi: float) -> str:
        """Interpret RSI"""
        if rsi > 70:
            return "🔴 Overbought - potential reversal or consolidation"
        elif rsi > 60:
            return "🟡 Strong but not extreme"
        elif rsi < 30:
            return "🟢 Oversold - potential bounce opportunity"
        elif rsi < 40:
            return "🟡 Weak but not extreme"
        else:
            return "⚪ Neutral zone"

    def _assess_beta_stability(self, betas: List[float]) -> str:
        """Assess beta stability"""
        if not betas:
            return "UNKNOWN"

        avg_beta = sum(betas) / len(betas)
        variance = sum((b - avg_beta) ** 2 for b in betas) / len(betas)

        if variance < 0.05:
            return "STABLE"
        elif variance < 0.15:
            return "MODERATE"
        else:
            return "VOLATILE"

    def _check_trend_consistency(self, stock_data) -> str:
        """Check if trends are consistent across timeframes"""
        day = stock_data.day_change_pct or 0
        week = stock_data.week_change_pct or 0
        month = stock_data.month_change_pct or 0

        all_positive = day > 0 and week > 0 and month > 0
        all_negative = day < 0 and week < 0 and month < 0

        if all_positive:
            return "CONSISTENTLY BULLISH across all timeframes"
        elif all_negative:
            return "CONSISTENTLY BEARISH across all timeframes"
        else:
            return "MIXED signals across timeframes"

    def _interpret_delivery(self, delivery_pct: float) -> str:
        """Interpret delivery percentage"""
        if delivery_pct > 60:
            return "Very high delivery - strong investor interest"
        elif delivery_pct > 40:
            return "Good delivery - healthy investor participation"
        elif delivery_pct > 25:
            return "Moderate delivery - normal trading"
        else:
            return "Low delivery - speculative trading"

    def _generate_summary(self, analysis: Dict) -> str:
        """Generate technical summary"""
        trend = analysis['trend_analysis']['primary_trend']
        ma_alignment = analysis['trend_analysis']['moving_averages']['alignment']
        rsi_zone = analysis['momentum_indicators']['rsi']['zone']

        if 'UPTREND' in trend and ma_alignment == 'BULLISH' and rsi_zone != 'OVERBOUGHT':
            return "🟢 TECHNICALLY STRONG: Bullish trend with positive momentum"
        elif 'DOWNTREND' in trend and ma_alignment == 'BEARISH':
            return "🔴 TECHNICALLY WEAK: Bearish trend with negative momentum"
        else:
            return "🟡 TECHNICALLY NEUTRAL: Mixed technical signals"

    def _empty_analysis(self, reason: str) -> Dict:
        """Return empty analysis"""
        return {
            'error': reason,
            'trend_analysis': {},
            'momentum_indicators': {},
            'volatility_analysis': {},
            'price_action': {},
            'volume_analysis': {},
            'summary': f"Analysis unavailable: {reason}"
        }


class RiskAssessment:
    """Comprehensive risk assessment"""

    def analyze(self, stock_data, all_analysis: Dict) -> Dict:
        """
        Perform risk assessment

        Args:
            stock_data: TLStockData object
            all_analysis: Dict containing all other analysis results

        Returns:
            dict: Risk analysis
        """
        if not stock_data:
            return self._empty_analysis("No stock data available")

        risk_analysis = {
            'market_risk': self._assess_market_risk(stock_data),
            'fundamental_risks': self._assess_fundamental_risks(all_analysis.get('fundamental', {})),
            'technical_risks': self._assess_technical_risks(all_analysis.get('technical', {})),
            'overall_risk_score': 0,
            'risk_grade': 'MODERATE'
        }

        # Calculate overall risk
        risk_analysis['overall_risk_score'] = self._calculate_overall_risk(risk_analysis)
        risk_analysis['risk_grade'] = self._grade_risk(risk_analysis['overall_risk_score'])

        return risk_analysis

    def _assess_market_risk(self, stock_data) -> Dict:
        """Assess market-related risks"""
        beta_1y = stock_data.beta_1year or 1
        atr = stock_data.day_atr or 0

        return {
            'beta_risk': 'HIGH' if beta_1y > 1.5 else 'LOW' if beta_1y < 0.7 else 'MODERATE',
            'volatility_risk': 'HIGH' if atr > 50 else 'LOW' if atr < 20 else 'MODERATE',
            'beta_value': round(beta_1y, 2),
            'atr_value': round(atr, 2)
        }

    def _assess_fundamental_risks(self, fundamental_analysis: Dict) -> List[str]:
        """Extract fundamental risks"""
        return fundamental_analysis.get('risk_factors', [])

    def _assess_technical_risks(self, technical_analysis: Dict) -> List[str]:
        """Assess technical risks"""
        risks = []

        momentum = technical_analysis.get('momentum_indicators', {})
        rsi = momentum.get('rsi', {})

        if rsi.get('zone') == 'OVERBOUGHT':
            risks.append("RSI in overbought territory - pullback risk")

        trend = technical_analysis.get('trend_analysis', {})
        if trend.get('primary_trend', '').startswith('STRONG DOWN'):
            risks.append("Strong downtrend - risk of further decline")

        return risks

    def _calculate_overall_risk(self, risk_analysis: Dict) -> int:
        """Calculate overall risk score (0-100, higher = riskier)"""
        score = 50  # Start at moderate

        # Market risk factors
        market = risk_analysis['market_risk']
        if market['beta_risk'] == 'HIGH':
            score += 15
        if market['volatility_risk'] == 'HIGH':
            score += 15

        # Fundamental risks
        fundamental_risks = len(risk_analysis['fundamental_risks'])
        score += min(fundamental_risks * 5, 20)

        # Technical risks
        technical_risks = len(risk_analysis['technical_risks'])
        score += min(technical_risks * 5, 10)

        return min(max(score, 0), 100)

    def _grade_risk(self, risk_score: int) -> str:
        """Grade overall risk"""
        if risk_score < 40:
            return 'LOW'
        elif risk_score < 60:
            return 'MODERATE'
        elif risk_score < 75:
            return 'HIGH'
        else:
            return 'VERY HIGH'

    def _empty_analysis(self, reason: str) -> Dict:
        """Return empty analysis"""
        return {
            'error': reason,
            'market_risk': {},
            'fundamental_risks': [],
            'technical_risks': [],
            'overall_risk_score': 50,
            'risk_grade': 'UNKNOWN'
        }
