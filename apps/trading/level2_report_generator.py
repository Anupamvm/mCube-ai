"""
Level 2 Deep-Dive Report Generator

Generates comprehensive analysis reports for trader decision-making
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from apps.trading.data_aggregator import TrendlyneDataAggregator
from apps.trading.level2_analyzers import FinancialPerformanceAnalyzer, ValuationDeepDive
from apps.trading.level2_analyzers_part2 import (
    InstitutionalBehaviorAnalyzer,
    TechnicalDeepDive,
    RiskAssessment
)

logger = logging.getLogger(__name__)


class Level2ReportGenerator:
    """
    Generate comprehensive Level 2 deep-dive analysis reports

    This class orchestrates all Level 2 analyzers and produces
    actionable trading reports.
    """

    def __init__(self, symbol: str, expiry_date: str, level1_results: Dict):
        """
        Initialize report generator

        Args:
            symbol: Stock symbol
            expiry_date: Futures expiry date
            level1_results: Level 1 analysis results
        """
        self.symbol = symbol
        self.expiry_date = expiry_date
        self.level1_results = level1_results
        self.aggregator = TrendlyneDataAggregator(symbol)

    def generate_report(self) -> Dict:
        """
        Generate comprehensive Level 2 deep-dive report

        Returns:
            dict: Complete analysis report
        """
        logger.info(f"Generating Level 2 deep-dive report for {self.symbol}")

        # Fetch all data
        data = self.aggregator.fetch_all_data()

        # Run all analyses
        fundamental = FinancialPerformanceAnalyzer().analyze(
            data['fundamentals'],
            data['forecaster']
        )

        valuation = ValuationDeepDive().analyze(data['fundamentals'])

        institutional = InstitutionalBehaviorAnalyzer().analyze(
            data['fundamentals'],
            data['contract_stock']
        )

        technical = TechnicalDeepDive().analyze(data['fundamentals'])

        risk = RiskAssessment().analyze(
            data['fundamentals'],
            {
                'fundamental': fundamental,
                'technical': technical
            }
        )

        # Generate comprehensive report
        report = {
            'metadata': {
                'symbol': self.symbol,
                'expiry_date': self.expiry_date,
                'analysis_timestamp': datetime.now().isoformat(),
                'level1_score': self.level1_results.get('composite_score', 0),
                'level1_direction': self.level1_results.get('direction', 'NEUTRAL'),
                'level1_verdict': self.level1_results.get('verdict', 'UNKNOWN'),
                'data_completeness': data['data_completeness']
            },

            'executive_summary': self.generate_executive_summary(
                fundamental, valuation, institutional, technical, risk
            ),

            'detailed_analysis': {
                'fundamental_analysis': fundamental,
                'valuation_analysis': valuation,
                'institutional_behavior': institutional,
                'technical_analysis': technical,
                'risk_assessment': risk
            },

            'trading_recommendation': self.generate_trading_recommendation(
                fundamental, valuation, institutional, technical, risk, data['fundamentals']
            ),

            'decision_matrix': self.create_decision_matrix(
                fundamental, valuation, institutional, technical, risk
            )
        }

        logger.info(f"✅ Level 2 report generated for {self.symbol}")

        return report

    def generate_executive_summary(
        self,
        fundamental: Dict,
        valuation: Dict,
        institutional: Dict,
        technical: Dict,
        risk: Dict
    ) -> Dict:
        """
        Generate executive summary

        Args:
            fundamental: Fundamental analysis
            valuation: Valuation analysis
            institutional: Institutional analysis
            technical: Technical analysis
            risk: Risk assessment

        Returns:
            dict: Executive summary
        """
        # Calculate conviction score
        conviction_score = self.calculate_conviction_score(
            fundamental, valuation, institutional, technical, risk
        )

        # Identify top strengths
        strengths = self.identify_top_strengths(
            fundamental, valuation, institutional, technical
        )

        # Identify top concerns
        concerns = self.identify_top_concerns(
            fundamental, valuation, institutional, technical, risk
        )

        # Create verdict
        verdict = self.create_verdict(conviction_score, strengths, concerns)

        # Identify critical levels
        critical_levels = self.identify_critical_levels(technical)

        return {
            'one_line_verdict': verdict,
            'conviction_score': conviction_score,
            'key_strengths': strengths[:5],  # Top 5
            'key_concerns': concerns[:5],  # Top 5
            'recommended_action': self.recommend_action(conviction_score),
            'critical_levels': critical_levels
        }

    def calculate_conviction_score(
        self,
        fundamental: Dict,
        valuation: Dict,
        institutional: Dict,
        technical: Dict,
        risk: Dict
    ) -> int:
        """
        Calculate overall conviction score (0-100)

        Args:
            fundamental: Fundamental analysis
            valuation: Valuation analysis
            institutional: Institutional analysis
            technical: Technical analysis
            risk: Risk assessment

        Returns:
            int: Conviction score
        """
        score = 50  # Start at neutral

        # Fundamental contribution (max 25 points)
        prof_score = fundamental.get('profitability', {}).get('quality_score', 50)
        score += int((prof_score - 50) / 4)

        # Valuation contribution (max 15 points)
        val_summary = valuation.get('valuation_summary', {}).get('overall_assessment', '')
        if 'UNDERVALUED' in val_summary:
            score += 15
        elif 'FAIRLY' in val_summary:
            score += 7
        elif 'OVERVALUED' in val_summary:
            score -= 10

        # Institutional contribution (max 15 points)
        inst_summary = institutional.get('summary', '')
        if '🟢' in inst_summary:
            score += 15
        elif '🔴' in inst_summary:
            score -= 10
        else:
            score += 5

        # Technical contribution (max 15 points)
        tech_summary = technical.get('summary', '')
        if '🟢' in tech_summary:
            score += 15
        elif '🔴' in tech_summary:
            score -= 10
        else:
            score += 5

        # Risk adjustment (can reduce up to 20 points)
        risk_score = risk.get('overall_risk_score', 50)
        risk_adjustment = -int((risk_score - 50) / 2.5)
        score += risk_adjustment

        return max(min(score, 100), 0)

    def identify_top_strengths(
        self,
        fundamental: Dict,
        valuation: Dict,
        institutional: Dict,
        technical: Dict
    ) -> List[str]:
        """Identify top strengths"""
        strengths = []

        # Fundamental strengths
        opportunities = fundamental.get('opportunity_factors', [])
        strengths.extend(opportunities[:3])

        # Valuation strengths
        val_assessment = valuation.get('valuation_summary', {}).get('overall_assessment', '')
        if 'UNDERVALUED' in val_assessment:
            strengths.append("Stock trading at attractive valuation levels")

        # Institutional strengths
        inst_summary = institutional.get('summary', '')
        if '🟢' in inst_summary:
            strengths.append("Strong institutional support and accumulation")

        # Technical strengths
        trend = technical.get('trend_analysis', {}).get('primary_trend', '')
        if 'UPTREND' in trend:
            strengths.append(f"Technical trend: {trend}")

        return strengths

    def identify_top_concerns(
        self,
        fundamental: Dict,
        valuation: Dict,
        institutional: Dict,
        technical: Dict,
        risk: Dict
    ) -> List[str]:
        """Identify top concerns"""
        concerns = []

        # Fundamental concerns
        risks = fundamental.get('risk_factors', [])
        concerns.extend(risks[:3])

        # Valuation concerns
        val_assessment = valuation.get('valuation_summary', {}).get('overall_assessment', '')
        if 'OVERVALUED' in val_assessment:
            concerns.append("Stock appears overvalued - valuation stretched")

        # Institutional concerns
        inst_summary = institutional.get('summary', '')
        if '🔴' in inst_summary:
            concerns.append("Weak institutional support - smart money exiting")

        # Technical concerns
        tech_risks = risk.get('technical_risks', [])
        concerns.extend(tech_risks[:2])

        # Overall risk
        if risk.get('risk_grade') in ['HIGH', 'VERY HIGH']:
            concerns.append(f"Overall risk assessment: {risk.get('risk_grade')}")

        return concerns

    def create_verdict(self, conviction_score: int, strengths: List[str], concerns: List[str]) -> str:
        """Create one-line verdict"""
        if conviction_score >= 75:
            return f"🟢 HIGH CONVICTION BUY - Score: {conviction_score}/100 - Strong opportunity with multiple positive factors"
        elif conviction_score >= 60:
            return f"🟡 MODERATE BUY - Score: {conviction_score}/100 - Good opportunity with manageable risks"
        elif conviction_score >= 50:
            return f"🟡 NEUTRAL/HOLD - Score: {conviction_score}/100 - Mixed signals, wait for clearer trend"
        elif conviction_score >= 35:
            return f"🟠 WEAK/AVOID - Score: {conviction_score}/100 - Several concerns outweigh positives"
        else:
            return f"🔴 AVOID/SHORT - Score: {conviction_score}/100 - Multiple red flags suggest staying away"

    def recommend_action(self, conviction_score: int) -> str:
        """Recommend trading action"""
        if conviction_score >= 75:
            return "EXECUTE TRADE - High conviction, proceed with recommended position size"
        elif conviction_score >= 60:
            return "EXECUTE WITH CAUTION - Moderate conviction, consider reduced position size"
        elif conviction_score >= 50:
            return "MONITOR - Keep on watchlist, wait for improved setup"
        else:
            return "AVOID - Look for better opportunities elsewhere"

    def identify_critical_levels(self, technical: Dict) -> Dict:
        """Identify critical price levels"""
        sr = technical.get('trend_analysis', {}).get('support_resistance', {})

        return {
            'immediate_support': sr.get('s1', 0),
            'immediate_resistance': sr.get('r1', 0),
            'pivot': sr.get('pivot', 0),
            'current_position': sr.get('position', 'UNKNOWN')
        }

    def generate_trading_recommendation(
        self,
        fundamental: Dict,
        valuation: Dict,
        institutional: Dict,
        technical: Dict,
        risk: Dict,
        stock_data
    ) -> Dict:
        """
        Generate specific trading recommendations

        Returns:
            dict: Trading recommendations
        """
        current_price = stock_data.current_price if stock_data else 0
        conviction = self.calculate_conviction_score(fundamental, valuation, institutional, technical, risk)

        # Support and resistance
        sr = technical.get('trend_analysis', {}).get('support_resistance', {})
        s1 = sr.get('s1', current_price * 0.98)
        r1 = sr.get('r1', current_price * 1.02)

        # Position sizing based on conviction and risk
        base_lots = 1
        risk_grade = risk.get('risk_grade', 'MODERATE')

        if conviction >= 75 and risk_grade in ['LOW', 'MODERATE']:
            position_multiplier = 1.5
        elif conviction >= 60:
            position_multiplier = 1.0
        elif conviction >= 50:
            position_multiplier = 0.5
        else:
            position_multiplier = 0.0

        recommended_lots = int(base_lots * position_multiplier)

        # Calculate stop loss
        atr = technical.get('volatility_analysis', {}).get('atr', current_price * 0.02)
        stop_loss = max(s1, current_price - (2 * atr))

        # Calculate targets
        target1 = r1
        target2 = r1 + (r1 - current_price)

        return {
            'entry_strategy': self._create_entry_strategy(conviction, current_price),
            'position_sizing': {
                'recommended_lots': recommended_lots,
                'rationale': self._position_sizing_rationale(conviction, risk_grade)
            },
            'stop_loss': {
                'level': round(stop_loss, 2),
                'percentage': round(((current_price - stop_loss) / current_price) * 100, 2),
                'method': 'Support + ATR based'
            },
            'profit_targets': [
                {
                    'target': round(target1, 2),
                    'percentage': round(((target1 - current_price) / current_price) * 100, 2),
                    'level': 'R1',
                    'action': 'Book 50% profit'
                },
                {
                    'target': round(target2, 2),
                    'percentage': round(((target2 - current_price) / current_price) * 100, 2),
                    'level': 'Extended R2',
                    'action': 'Book remaining 50%'
                }
            ],
            'time_horizon': self._recommend_holding_period(technical, conviction),
            'key_monitorables': self._identify_key_monitorables(fundamental, institutional, risk)
        }

    def _create_entry_strategy(self, conviction: int, current_price: float) -> str:
        """Create entry strategy"""
        if conviction >= 75:
            return f"Enter at market price (~₹{current_price:.2f}) - High conviction setup"
        elif conviction >= 60:
            return f"Enter on minor dips near ₹{current_price * 0.99:.2f} or at market"
        elif conviction >= 50:
            return f"Wait for pullback to ₹{current_price * 0.97:.2f} before entering"
        else:
            return "Avoid entry - insufficient conviction"

    def _position_sizing_rationale(self, conviction: int, risk_grade: str) -> str:
        """Explain position sizing"""
        if conviction >= 75 and risk_grade in ['LOW', 'MODERATE']:
            return "Increased size justified by high conviction and manageable risk"
        elif conviction >= 60:
            return "Standard position size - balanced risk-reward"
        elif conviction >= 50:
            return "Reduced size due to moderate conviction"
        else:
            return "Zero position - avoid this trade"

    def _recommend_holding_period(self, technical: Dict, conviction: int) -> str:
        """Recommend holding period"""
        trend = technical.get('trend_analysis', {}).get('primary_trend', '')

        if 'STRONG UPTREND' in trend and conviction >= 70:
            return "3-7 days (swing trade) - strong trend supports longer hold"
        elif conviction >= 60:
            return "2-5 days - medium-term trade"
        else:
            return "1-3 days - short-term only"

    def _identify_key_monitorables(self, fundamental: Dict, institutional: Dict, risk: Dict) -> List[str]:
        """Identify what to monitor"""
        monitorables = [
            "Stop loss breach",
            "Target achievement",
            "Change in FII/DII holdings",
            "Upcoming earnings/results",
            "Sector trend changes"
        ]

        # Add specific monitorables based on risks
        if risk.get('overall_risk_score', 50) > 70:
            monitorables.append("Elevated risk - monitor volatility closely")

        return monitorables

    def create_decision_matrix(
        self,
        fundamental: Dict,
        valuation: Dict,
        institutional: Dict,
        technical: Dict,
        risk: Dict
    ) -> Dict:
        """
        Create decision matrix with bullish/bearish factors

        Returns:
            dict: Decision matrix
        """
        bullish_factors = []
        bearish_factors = []

        # Fundamental factors
        if fundamental.get('profitability', {}).get('quality_score', 0) > 70:
            bullish_factors.append("Strong profitability metrics")
        elif fundamental.get('profitability', {}).get('quality_score', 0) < 40:
            bearish_factors.append("Weak profitability")

        # Revenue momentum
        momentum = fundamental.get('revenue_analysis', {}).get('momentum', '')
        if momentum == 'ACCELERATING':
            bullish_factors.append("Accelerating revenue growth")
        elif momentum == 'DECELERATING':
            bearish_factors.append("Decelerating revenue growth")

        # Valuation
        val_assessment = valuation.get('valuation_summary', {}).get('overall_assessment', '')
        if 'UNDERVALUED' in val_assessment:
            bullish_factors.append("Attractive valuation - trading below fair value")
        elif 'OVERVALUED' in val_assessment:
            bearish_factors.append("Stretched valuation - trading above fair value")

        # Institutional
        inst_summary = institutional.get('summary', '')
        if '🟢' in inst_summary:
            bullish_factors.append("Strong institutional accumulation")
        elif '🔴' in inst_summary:
            bearish_factors.append("Institutional selling pressure")

        # Technical
        tech_summary = technical.get('summary', '')
        if '🟢' in tech_summary:
            bullish_factors.append("Positive technical setup with bullish trend")
        elif '🔴' in tech_summary:
            bearish_factors.append("Negative technical setup with bearish trend")

        # Risk factors
        all_risks = fundamental.get('risk_factors', []) + risk.get('technical_risks', [])
        bearish_factors.extend(all_risks[:3])

        # Opportunities
        opportunities = fundamental.get('opportunity_factors', [])
        bullish_factors.extend(opportunities[:3])

        return {
            'bullish_factors': bullish_factors,
            'bearish_factors': bearish_factors,
            'key_risks': all_risks[:5],
            'catalysts': self._identify_potential_catalysts(fundamental, institutional)
        }

    def _identify_potential_catalysts(self, fundamental: Dict, institutional: Dict) -> List[str]:
        """Identify potential catalysts"""
        catalysts = []

        # Upcoming results
        latest_result = fundamental.get('earnings_quality', {}).get('latest_result', '')
        if latest_result:
            catalysts.append(f"Next results expected around {latest_result}")

        # Institutional activity
        fii_signal = institutional.get('fii_activity', {}).get('signal_strength', '')
        if fii_signal == 'STRONG':
            catalysts.append("Strong FII activity could drive momentum")

        # General catalysts
        catalysts.append("Sector rotation or market sentiment shift")
        catalysts.append("Better than expected quarterly results")

        return catalysts
