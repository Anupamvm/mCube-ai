"""
Enhanced Futures Analyzer

Comprehensive multi-factor analysis for Futures trading decisions.
Incorporates 12 scoring components across technical, fundamental, and sentiment dimensions.

Scoring Components (315 pts total, scaled to 100):
1. OI & F&O Analysis (45 pts)
2. Technical Momentum (35 pts)
3. Trend Confirmation (30 pts) - includes 52W breakout detection
4. Volume Quality (25 pts) - includes delivery trend analysis
5. Institutional Flow (25 pts)
6. Fundamental Quality (20 pts)
7. Risk Adjustment (30 pts)
8. News Sentiment (25 pts)
9. Analyst Consensus (20 pts)
10. Research Reports (15 pts)
11. Investor Calls (10 pts)
12. Momentum Acceleration (20 pts) - NEW Phase 2

Hard Reject Filters (must pass all):
- MWPL < 80%
- Volatility < 60%
- Piotroski >= 4
- Promoter pledge < 30%
- FII change > -2%
- No blocking news
- Analyst upside >= 8% (for LONG)

Phase 2 Enhancements:
- 52W breakout detection in trend confirmation
- Delivery trend analysis (accumulation/distribution patterns)
- Momentum acceleration scoring (day-over-day, week-over-week)
- Beta-based position sizing adjustments
"""

import logging
from typing import Dict
from datetime import timedelta
from django.utils import timezone
from apps.positions.services.sr_exit_engine import compute_initial_sl_target

logger = logging.getLogger(__name__)


class HardRejectError(Exception):
    """Raised when a hard reject filter fails"""


class EnhancedFuturesAnalyzer:
    """
    Comprehensive futures analyzer with multi-factor scoring.

    Usage:
        analyzer = EnhancedFuturesAnalyzer(symbol='RELIANCE', direction='LONG')
        result = analyzer.analyze()

        if result['hard_reject']:
            print(f"REJECTED: {result['reject_reason']}")
        elif result['composite_score'] >= 65:
            print(f"QUALIFIED: Score {result['composite_score']}/100")
    """

    # Hard reject thresholds
    MAX_MWPL_PCT = 80.0
    MAX_VOLATILITY_PCT = 60.0
    MIN_PIOTROSKI_SCORE = 4
    MAX_PROMOTER_PLEDGE_PCT = 30.0
    MIN_FII_CHANGE_PCT = -2.0
    MIN_ANALYST_UPSIDE_PCT = 8.0

    # Scoring weights (total 315 pts) - Phase 3 Enhanced
    WEIGHTS = {
        'oi_fno': 45,
        'technical_momentum': 35,
        'trend_confirmation': 30,        # +5 for 52W breakout detection
        'volume_quality': 25,            # +5 for delivery trend
        'institutional_flow': 25,
        'fundamental_quality': 20,
        'risk_adjustment': 30,
        'news_sentiment': 25,
        'analyst_consensus': 20,
        'research_reports': 15,
        'investor_calls': 10,
        'momentum_acceleration': 20,     # Phase 2
        'mtf_confluence': 15,            # Phase 3: Multi-Timeframe Confluence
    }
    TOTAL_WEIGHT = sum(WEIGHTS.values())  # 315

    # Position sizing adjustments based on beta
    BETA_POSITION_ADJUSTMENTS = {
        'very_high': {'threshold': 1.5, 'multiplier': 0.70},   # Reduce 30%
        'high': {'threshold': 1.2, 'multiplier': 0.85},        # Reduce 15%
        'normal': {'threshold': 1.0, 'multiplier': 1.00},      # Standard
        'low': {'threshold': 0.7, 'multiplier': 1.15},         # Increase 15%
        'very_low': {'threshold': 0.0, 'multiplier': 1.00},    # Standard (may lack movement)
    }

    def __init__(self, symbol: str, direction: str, expiry: str = None, regime: str = 'NORMAL'):
        """
        Initialize analyzer.

        Args:
            symbol: Stock symbol (NSE code)
            direction: Trade direction ('LONG' or 'SHORT')
            expiry: Optional expiry date for F&O contracts
            regime: Market regime (TRENDING, RANGING, VOLATILE, BREAKOUT, NORMAL)
        """
        self.symbol = symbol.upper()
        self.direction = direction.upper()
        self.expiry = expiry
        self.regime = regime

        # Data holders (lazy loaded)
        self._tl_stock_data = None
        self._contract_stock_data = None
        self._contract_data = None

        # Results
        self.hard_reject = False
        self.reject_reason = None
        self.scores = {}
        self.details = {}

    def _load_data(self):
        """Load all required data from models"""
        from apps.data.models import TLStockData, ContractStockData, ContractData

        # Load TLStockData
        self._tl_stock_data = TLStockData.objects.filter(
            nsecode=self.symbol
        ).first()

        # Load ContractStockData
        self._contract_stock_data = ContractStockData.objects.filter(
            nse_code=self.symbol
        ).first()

        # Load ContractData for specific expiry
        if self.expiry:
            self._contract_data = ContractData.objects.filter(
                symbol=self.symbol,
                expiry=self.expiry
            )

        if not self._tl_stock_data:
            logger.warning(f"No TLStockData found for {self.symbol}")
        if not self._contract_stock_data:
            logger.warning(f"No ContractStockData found for {self.symbol}")

    def analyze(self) -> Dict:
        """
        Run complete analysis.

        Returns:
            dict: {
                'symbol': str,
                'direction': str,
                'hard_reject': bool,
                'reject_reason': str or None,
                'composite_score': int (0-100),
                'scores': dict of component scores,
                'details': dict of analysis details,
                'recommendation': str,
                'entry_params': dict (if qualified)
            }
        """
        logger.info(f"=" * 80)
        logger.info(f"ENHANCED FUTURES ANALYSIS: {self.symbol} ({self.direction})")
        logger.info(f"=" * 80)

        # Load data
        self._load_data()

        # Check hard reject filters first
        try:
            self._check_hard_reject_filters()
        except HardRejectError as e:
            logger.warning(f"HARD REJECT: {self.symbol} - {str(e)}")
            return {
                'symbol': self.symbol,
                'direction': self.direction,
                'hard_reject': True,
                'reject_reason': str(e),
                'composite_score': 0,
                'scores': {},
                'details': self.details,
                'recommendation': 'REJECT',
                'entry_params': None
            }

        # Calculate all component scores
        self._calculate_all_scores()

        # Calculate composite score (scaled to 100)
        raw_score = sum(self.scores.values())
        composite_score = int((raw_score / self.TOTAL_WEIGHT) * 100)

        # Determine recommendation
        if composite_score >= 80:
            recommendation = 'STRONG_ENTRY'
        elif composite_score >= 65:
            recommendation = 'ENTRY'
        elif composite_score >= 50:
            recommendation = 'WEAK_ENTRY'
        else:
            recommendation = 'NO_ENTRY'

        # Calculate entry parameters if qualified
        entry_params = None
        if composite_score >= 65:
            entry_params = self._calculate_entry_params()

        logger.info(f"")
        logger.info(f"COMPOSITE SCORE: {composite_score}/100 (raw: {raw_score}/{self.TOTAL_WEIGHT})")
        logger.info(f"RECOMMENDATION: {recommendation}")
        logger.info(f"=" * 80)

        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'hard_reject': False,
            'reject_reason': None,
            'news_warning': self.details.get('news_warning'),
            'composite_score': composite_score,
            'raw_score': raw_score,
            'max_score': self.TOTAL_WEIGHT,
            'scores': self.scores,
            'details': self.details,
            'recommendation': recommendation,
            'entry_params': entry_params,
            'regime': self.regime,
        }

    # =========================================================================
    # HARD REJECT FILTERS
    # =========================================================================

    def _check_hard_reject_filters(self):
        """
        Check all hard reject filters.
        Raises HardRejectError if any filter fails.
        """
        logger.info("Checking Hard Reject Filters...")
        logger.info("-" * 40)

        self.details['hard_reject_checks'] = {}

        # 1. MWPL Check
        self._check_mwpl()

        # 2. Volatility Check
        self._check_volatility()

        # 3. Piotroski Score Check
        self._check_piotroski()

        # 4. Promoter Pledge Check
        self._check_promoter_pledge()

        # 5. FII Holding Change Check
        self._check_fii_change()

        # 6. News Sentiment Check
        self._check_blocking_news()

        # 7. Analyst Upside Check (for LONG only)
        if self.direction == 'LONG':
            self._check_analyst_upside()

        logger.info("All hard reject filters PASSED")
        logger.info("")

    def _check_mwpl(self):
        """Check MWPL (Market Wide Position Limit)"""
        if not self._contract_stock_data:
            self.details['hard_reject_checks']['mwpl'] = {
                'passed': True,
                'reason': 'No F&O data available',
                'value': None,
                'threshold': self.MAX_MWPL_PCT
            }
            return

        mwpl_pct = self._contract_stock_data.fno_mwpl_pct or 0
        passed = mwpl_pct < self.MAX_MWPL_PCT

        self.details['hard_reject_checks']['mwpl'] = {
            'passed': passed,
            'value': mwpl_pct,
            'threshold': self.MAX_MWPL_PCT,
            'reason': f"MWPL at {mwpl_pct:.1f}%"
        }

        if not passed:
            raise HardRejectError(
                f"MWPL too high: {mwpl_pct:.1f}% (max {self.MAX_MWPL_PCT}%) - near ban risk"
            )

        logger.info(f"  MWPL: {mwpl_pct:.1f}% < {self.MAX_MWPL_PCT}% - PASS")

    def _check_volatility(self):
        """Check annualized volatility"""
        if not self._contract_stock_data:
            self.details['hard_reject_checks']['volatility'] = {
                'passed': True,
                'reason': 'No volatility data available',
                'value': None,
                'threshold': self.MAX_VOLATILITY_PCT
            }
            return

        volatility = self._contract_stock_data.annualized_volatility or 0
        passed = volatility < self.MAX_VOLATILITY_PCT

        self.details['hard_reject_checks']['volatility'] = {
            'passed': passed,
            'value': volatility,
            'threshold': self.MAX_VOLATILITY_PCT,
            'reason': f"Volatility at {volatility:.1f}%"
        }

        if not passed:
            raise HardRejectError(
                f"Volatility too high: {volatility:.1f}% (max {self.MAX_VOLATILITY_PCT}%)"
            )

        logger.info(f"  Volatility: {volatility:.1f}% < {self.MAX_VOLATILITY_PCT}% - PASS")

    def _check_piotroski(self):
        """Check Piotroski F-Score"""
        if not self._tl_stock_data:
            self.details['hard_reject_checks']['piotroski'] = {
                'passed': True,
                'reason': 'No Piotroski data available',
                'value': None,
                'threshold': self.MIN_PIOTROSKI_SCORE
            }
            return

        piotroski = self._tl_stock_data.piotroski_score
        if piotroski is None:
            self.details['hard_reject_checks']['piotroski'] = {
                'passed': True,
                'reason': 'Piotroski score not available',
                'value': None,
                'threshold': self.MIN_PIOTROSKI_SCORE
            }
            return

        passed = piotroski >= self.MIN_PIOTROSKI_SCORE

        self.details['hard_reject_checks']['piotroski'] = {
            'passed': passed,
            'value': piotroski,
            'threshold': self.MIN_PIOTROSKI_SCORE,
            'reason': f"Piotroski score: {piotroski}"
        }

        if not passed:
            raise HardRejectError(
                f"Piotroski score too low: {piotroski} (min {self.MIN_PIOTROSKI_SCORE}) - weak fundamentals"
            )

        logger.info(f"  Piotroski: {piotroski} >= {self.MIN_PIOTROSKI_SCORE} - PASS")

    def _check_promoter_pledge(self):
        """Check promoter pledge percentage"""
        if not self._tl_stock_data:
            self.details['hard_reject_checks']['promoter_pledge'] = {
                'passed': True,
                'reason': 'No pledge data available',
                'value': None,
                'threshold': self.MAX_PROMOTER_PLEDGE_PCT
            }
            return

        pledge_pct = self._tl_stock_data.promoter_pledge_pct_qtr or 0
        passed = pledge_pct < self.MAX_PROMOTER_PLEDGE_PCT

        self.details['hard_reject_checks']['promoter_pledge'] = {
            'passed': passed,
            'value': pledge_pct,
            'threshold': self.MAX_PROMOTER_PLEDGE_PCT,
            'reason': f"Promoter pledge: {pledge_pct:.1f}%"
        }

        if not passed:
            raise HardRejectError(
                f"Promoter pledge too high: {pledge_pct:.1f}% (max {self.MAX_PROMOTER_PLEDGE_PCT}%) - financial stress risk"
            )

        logger.info(f"  Promoter Pledge: {pledge_pct:.1f}% < {self.MAX_PROMOTER_PLEDGE_PCT}% - PASS")

    def _check_fii_change(self):
        """Check FII holding change QoQ"""
        if not self._tl_stock_data:
            self.details['hard_reject_checks']['fii_change'] = {
                'passed': True,
                'reason': 'No FII data available',
                'value': None,
                'threshold': self.MIN_FII_CHANGE_PCT
            }
            return

        fii_change = self._tl_stock_data.fii_holding_change_qoq_pct
        if fii_change is None:
            self.details['hard_reject_checks']['fii_change'] = {
                'passed': True,
                'reason': 'FII change data not available',
                'value': None,
                'threshold': self.MIN_FII_CHANGE_PCT
            }
            return

        passed = fii_change > self.MIN_FII_CHANGE_PCT

        self.details['hard_reject_checks']['fii_change'] = {
            'passed': passed,
            'value': fii_change,
            'threshold': self.MIN_FII_CHANGE_PCT,
            'reason': f"FII change QoQ: {fii_change:+.2f}%"
        }

        if not passed:
            raise HardRejectError(
                f"FII exodus: {fii_change:+.2f}% (min {self.MIN_FII_CHANGE_PCT}%) - institutional selling"
            )

        logger.info(f"  FII Change: {fii_change:+.2f}% > {self.MIN_FII_CHANGE_PCT}% - PASS")

    def _check_blocking_news(self):
        """Check for blocking news articles (soft warning, does not reject)"""
        try:
            from apps.strategies.filters.news_sentiment import check_market_news_sentiment

            news_result = check_market_news_sentiment(max_hours_old=4)
            passed = news_result.get('passed', True)

            self.details['hard_reject_checks']['blocking_news'] = {
                'passed': passed,
                'value': news_result.get('details', {}).get('average_sentiment', 0),
                'articles_analyzed': news_result.get('details', {}).get('articles_analyzed', 0),
                'blocking_articles': len(news_result.get('details', {}).get('blocking_articles', [])),
                'reason': news_result.get('message', 'News check completed')
            }

            if not passed:
                # Check if hard-block is configured (default: soft warning only)
                try:
                    from apps.core.models import TradingCoreConfig
                    config = TradingCoreConfig.get_instance()
                    avg_sentiment = news_result.get('details', {}).get('average_sentiment', 0)
                    if config.news_hard_block_enabled and avg_sentiment < config.news_hard_block_threshold:
                        raise HardRejectError(
                            f"News hard block: market sentiment {avg_sentiment:.2f} "
                            f"< threshold {config.news_hard_block_threshold:.2f}"
                        )
                except HardRejectError:
                    raise
                except Exception:
                    pass  # Fail-open if config lookup errors
                # Default: soft warning — proceed
                self.details['news_warning'] = news_result.get('message', 'Negative market sentiment')
                logger.warning(f"  Market News: {news_result.get('message', '')[:60]} - WARNING (proceeding)")
            else:
                logger.info(f"  Market News: {news_result.get('message', 'OK')[:50]} - PASS")

        except ImportError:
            self.details['hard_reject_checks']['blocking_news'] = {
                'passed': True,
                'reason': 'News sentiment service not available'
            }
            logger.info("  Market News: Service not available - SKIP")
        except Exception as e:
            # Fail-open for news check
            self.details['hard_reject_checks']['blocking_news'] = {
                'passed': True,
                'reason': f'News check error (fail-open): {str(e)}'
            }
            logger.warning(f"  Market News: Error ({str(e)[:30]}) - SKIP (fail-open)")

    def _check_analyst_upside(self):
        """Check analyst consensus upside (LONG only)"""
        try:
            from apps.llm.services.analyst_report_aggregator import aggregate_analyst_data_for_trade

            analyst_result = aggregate_analyst_data_for_trade(
                symbol=self.symbol,
                direction=self.direction,
                nse_code=self.symbol
            )

            passed = analyst_result.get('trade_allowed', True)
            price_target = analyst_result.get('price_target', {})
            upside_pct = price_target.get('upside_pct') if price_target else None

            self.details['hard_reject_checks']['analyst_upside'] = {
                'passed': passed,
                'value': upside_pct,
                'threshold': self.MIN_ANALYST_UPSIDE_PCT,
                'blocking_reasons': analyst_result.get('blocking_reasons', []),
                'reason': analyst_result.get('blocking_reasons', ['Check passed'])[0] if not passed else 'Analyst consensus OK'
            }

            # Store full analyst data for scoring
            self.details['analyst_data'] = analyst_result

            if not passed:
                reasons = analyst_result.get('blocking_reasons', ['Analyst check failed'])
                raise HardRejectError(f"Analyst block: {reasons[0]}")

            logger.info(f"  Analyst Upside: {upside_pct:.1f}% >= {self.MIN_ANALYST_UPSIDE_PCT}% - PASS" if upside_pct else "  Analyst: No data - SKIP")

        except ImportError:
            self.details['hard_reject_checks']['analyst_upside'] = {
                'passed': True,
                'reason': 'Analyst service not available'
            }
            logger.info("  Analyst Upside: Service not available - SKIP")
        except HardRejectError:
            raise
        except Exception as e:
            # Fail-open for analyst check
            self.details['hard_reject_checks']['analyst_upside'] = {
                'passed': True,
                'reason': f'Analyst check error (fail-open): {str(e)}'
            }
            logger.warning(f"  Analyst Upside: Error ({str(e)[:30]}) - SKIP (fail-open)")

    # =========================================================================
    # SCORING COMPONENTS
    # =========================================================================

    def _calculate_all_scores(self):
        """Calculate all component scores (Phase 2 Enhanced)"""
        logger.info("Calculating Component Scores (Phase 2 Enhanced)...")
        logger.info("-" * 40)

        # 1. OI & F&O Analysis (45 pts)
        self.scores['oi_fno'] = self._score_oi_fno()

        # 2. Technical Momentum (35 pts)
        self.scores['technical_momentum'] = self._score_technical_momentum()

        # 3. Trend Confirmation (30 pts) - Enhanced with 52W breakout
        self.scores['trend_confirmation'] = self._score_trend_confirmation()

        # 4. Volume Quality (25 pts) - Enhanced with delivery trend
        self.scores['volume_quality'] = self._score_volume_quality()

        # 5. Institutional Flow (25 pts)
        self.scores['institutional_flow'] = self._score_institutional_flow()

        # 6. Fundamental Quality (20 pts)
        self.scores['fundamental_quality'] = self._score_fundamental_quality()

        # 7. Risk Adjustment (30 pts)
        self.scores['risk_adjustment'] = self._score_risk_adjustment()

        # 8. News Sentiment (25 pts)
        self.scores['news_sentiment'] = self._score_news_sentiment()

        # 9. Analyst Consensus (20 pts)
        self.scores['analyst_consensus'] = self._score_analyst_consensus()

        # 10. Research Reports (15 pts)
        self.scores['research_reports'] = self._score_research_reports()

        # 11. Investor Calls (10 pts)
        self.scores['investor_calls'] = self._score_investor_calls()

        # 12. Momentum Acceleration (20 pts) - Phase 2
        self.scores['momentum_acceleration'] = self._score_momentum_acceleration()

        # 13. Multi-Timeframe Confluence (15 pts) - Phase 3
        self.scores['mtf_confluence'] = self._score_mtf_confluence()

        # Log scores
        logger.info("")
        logger.info("SCORE BREAKDOWN:")
        for component, score in self.scores.items():
            max_score = self.WEIGHTS[component]
            pct = (score / max_score * 100) if max_score > 0 else 0
            detail = self.details.get(component, {})
            gap_tag = ' [DATA GAP]' if (
                score == 0
                and isinstance(detail, dict)
                and detail.get('reason', '').lower().startswith('no ')
            ) else ''
            logger.info(f"  {component}: {score}/{max_score} ({pct:.0f}%){gap_tag}")

        # Warn when data gaps deflate the composite (score=0 because data was missing, not bad)
        data_gaps = []
        gap_pts = 0
        for component, score in self.scores.items():
            if score == 0:
                detail = self.details.get(component, {})
                reason = detail.get('reason', '') if isinstance(detail, dict) else ''
                if reason.lower().startswith('no '):
                    data_gaps.append(f"{component}({self.WEIGHTS[component]}pts)")
                    gap_pts += self.WEIGHTS[component]
        if data_gaps:
            logger.warning(
                f"[{self.symbol}] DATA GAPS — {gap_pts}/{self.TOTAL_WEIGHT}pts from missing data: "
                + ", ".join(data_gaps)
            )

    def _score_oi_fno(self) -> int:
        """
        Score OI & F&O Analysis (max 45 pts)
        - OI Buildup: 20 pts
        - PCR Analysis: 10 pts
        - MWPL Position: 5 pts
        - Rollover: 10 pts
        """
        score = 0
        details = {}

        if not self._contract_stock_data:
            self.details['oi_fno'] = {'score': 0, 'reason': 'No F&O data'}
            return 0

        csd = self._contract_stock_data

        # OI Buildup Analysis (20 pts)
        oi_change = csd.fno_total_oi_change_pct or 0
        price_change = self._tl_stock_data.day_change_pct if self._tl_stock_data else 0

        # Determine buildup type
        if price_change > 0 and oi_change > 0:
            buildup = 'LONG_BUILDUP'
            buildup_score = 20 if self.direction == 'LONG' else 5
        elif price_change < 0 and oi_change > 0:
            buildup = 'SHORT_BUILDUP'
            buildup_score = 20 if self.direction == 'SHORT' else 5
        elif price_change > 0 and oi_change < 0:
            buildup = 'SHORT_COVERING'
            buildup_score = 10 if self.direction == 'LONG' else 10
        elif price_change < 0 and oi_change < 0:
            buildup = 'LONG_UNWINDING'
            buildup_score = 10 if self.direction == 'SHORT' else 5
        else:
            buildup = 'NEUTRAL'
            buildup_score = 5

        score += buildup_score
        details['buildup'] = {'type': buildup, 'oi_change': oi_change, 'price_change': price_change, 'score': buildup_score}

        # PCR Analysis (10 pts)
        pcr = csd.fno_pcr_oi or 1.0
        if self.direction == 'LONG':
            # High PCR = bearish, actually bullish for LONG (put sellers)
            if pcr > 1.2:
                pcr_score = 10
            elif pcr > 1.0:
                pcr_score = 7
            elif pcr > 0.8:
                pcr_score = 5
            else:
                pcr_score = 2
        else:  # SHORT
            # Low PCR = bullish, bad for SHORT
            if pcr < 0.8:
                pcr_score = 10
            elif pcr < 1.0:
                pcr_score = 7
            elif pcr < 1.2:
                pcr_score = 5
            else:
                pcr_score = 2

        score += pcr_score
        details['pcr'] = {'value': pcr, 'score': pcr_score}

        # MWPL Position (5 pts) - Lower is better
        mwpl_pct = csd.fno_mwpl_pct or 0
        if mwpl_pct < 30:
            mwpl_score = 5
        elif mwpl_pct < 50:
            mwpl_score = 4
        elif mwpl_pct < 70:
            mwpl_score = 2
        else:
            mwpl_score = 0

        score += mwpl_score
        details['mwpl'] = {'value': mwpl_pct, 'score': mwpl_score}

        # Rollover Analysis (10 pts)
        rollover_pct = csd.fno_rollover_pct or 0
        rollover_cost = csd.fno_rollover_cost_pct or 0

        # High rollover = position continuation
        if rollover_pct > 70:
            rollover_score = 7
        elif rollover_pct > 50:
            rollover_score = 5
        else:
            rollover_score = 2

        # Rollover cost indicates sentiment
        if self.direction == 'LONG' and rollover_cost > 0:
            rollover_score += 3  # Premium = bullish
        elif self.direction == 'SHORT' and rollover_cost < 0:
            rollover_score += 3  # Discount = bearish

        rollover_score = min(rollover_score, 10)
        score += rollover_score
        details['rollover'] = {'pct': rollover_pct, 'cost': rollover_cost, 'score': rollover_score}

        self.details['oi_fno'] = details
        logger.info(f"  OI & F&O: {score}/45 (buildup={buildup}, PCR={pcr:.2f})")

        return min(score, 45)

    def _score_technical_momentum(self) -> int:
        """
        Score Technical Momentum (max 35 pts)
        - RSI: 5 pts
        - MACD: 10 pts
        - MFI: 5 pts
        - ADX: 10 pts
        - ROC: 5 pts
        """
        score = 0
        details = {}

        if not self._tl_stock_data:
            self.details['technical_momentum'] = {'score': 0, 'reason': 'No data'}
            return 0

        tl = self._tl_stock_data

        # RSI (5 pts)
        rsi = tl.day_rsi
        if rsi:
            if self.direction == 'LONG':
                if 30 <= rsi <= 50:
                    rsi_score = 5  # Oversold recovery zone
                elif 50 < rsi <= 70:
                    rsi_score = 4  # Bullish momentum
                elif rsi < 30:
                    rsi_score = 3  # Very oversold
                else:
                    rsi_score = 1  # Overbought
            else:  # SHORT
                if 50 <= rsi <= 70:
                    rsi_score = 5  # Overbought reversal zone
                elif rsi > 70:
                    rsi_score = 4  # Very overbought
                elif 30 < rsi < 50:
                    rsi_score = 2
                else:
                    rsi_score = 1  # Oversold
            score += rsi_score
            details['rsi'] = {'value': rsi, 'score': rsi_score}

        # MACD (10 pts)
        macd = tl.day_macd
        macd_signal = tl.day_macd_signal_line
        if macd is not None and macd_signal is not None:
            if self.direction == 'LONG':
                if macd > 0 and macd > macd_signal:
                    macd_score = 10  # Bullish and above signal
                elif macd > macd_signal:
                    macd_score = 7  # Bullish crossover
                elif macd > 0:
                    macd_score = 4  # Above zero but below signal
                else:
                    macd_score = 1
            else:  # SHORT
                if macd < 0 and macd < macd_signal:
                    macd_score = 10  # Bearish and below signal
                elif macd < macd_signal:
                    macd_score = 7  # Bearish crossover
                elif macd < 0:
                    macd_score = 4
                else:
                    macd_score = 1
            score += macd_score
            details['macd'] = {'value': macd, 'signal': macd_signal, 'score': macd_score}

        # MFI (5 pts)
        mfi = tl.day_mfi
        if mfi:
            if self.direction == 'LONG':
                if mfi > 60:
                    mfi_score = 5  # Strong money inflow
                elif mfi > 50:
                    mfi_score = 4
                elif mfi > 40:
                    mfi_score = 2
                else:
                    mfi_score = 0  # Money outflow
            else:  # SHORT
                if mfi < 40:
                    mfi_score = 5  # Money outflow
                elif mfi < 50:
                    mfi_score = 4
                elif mfi < 60:
                    mfi_score = 2
                else:
                    mfi_score = 0
            score += mfi_score
            details['mfi'] = {'value': mfi, 'score': mfi_score}

        # ADX (10 pts) - Trend strength
        adx = tl.day_adx
        if adx:
            if adx > 40:
                adx_score = 10  # Very strong trend
            elif adx > 25:
                adx_score = 7  # Strong trend
            elif adx > 20:
                adx_score = 4  # Moderate trend
            else:
                adx_score = 2  # Weak/no trend
            score += adx_score
            details['adx'] = {'value': adx, 'score': adx_score}

        # ROC (5 pts) - Rate of Change
        roc21 = tl.day_roc21
        if roc21:
            if self.direction == 'LONG':
                if roc21 > 5:
                    roc_score = 5
                elif roc21 > 0:
                    roc_score = 3
                else:
                    roc_score = 1
            else:  # SHORT
                if roc21 < -5:
                    roc_score = 5
                elif roc21 < 0:
                    roc_score = 3
                else:
                    roc_score = 1
            score += roc_score
            details['roc21'] = {'value': roc21, 'score': roc_score}

        self.details['technical_momentum'] = details
        logger.info(f"  Technical Momentum: {score}/35")

        return min(score, 35)

    def _score_trend_confirmation(self) -> int:
        """
        Score Trend Confirmation (max 30 pts) - Phase 2 Enhanced
        - DMA Position: 10 pts
        - Price Range Position: 10 pts
        - Breakout Detection: 5 pts
        - 52W Breakout Detection: 5 pts (NEW Phase 2)
        """
        score = 0
        details = {}

        if not self._tl_stock_data:
            self.details['trend_confirmation'] = {'score': 0, 'reason': 'No data'}
            return 0

        tl = self._tl_stock_data
        price = tl.current_price or 0

        # DMA Position (10 pts)
        dmas = [
            tl.day5_sma, tl.day30_sma, tl.day50_sma,
            tl.day100_sma, tl.day200_sma
        ]
        valid_dmas = [d for d in dmas if d is not None]

        if valid_dmas and price:
            above_count = sum(1 for d in valid_dmas if price > d)
            total_dmas = len(valid_dmas)

            if self.direction == 'LONG':
                dma_ratio = above_count / total_dmas
                if dma_ratio >= 0.8:
                    dma_score = 10  # Above most DMAs
                elif dma_ratio >= 0.6:
                    dma_score = 7
                elif dma_ratio >= 0.4:
                    dma_score = 4
                else:
                    dma_score = 1
            else:  # SHORT
                below_ratio = 1 - (above_count / total_dmas)
                if below_ratio >= 0.8:
                    dma_score = 10  # Below most DMAs
                elif below_ratio >= 0.6:
                    dma_score = 7
                elif below_ratio >= 0.4:
                    dma_score = 4
                else:
                    dma_score = 1

            # Golden/Death cross bonus
            if tl.day50_sma and tl.day200_sma:
                if tl.day50_sma > tl.day200_sma and self.direction == 'LONG':
                    dma_score = min(dma_score + 2, 10)  # Golden cross bonus
                elif tl.day50_sma < tl.day200_sma and self.direction == 'SHORT':
                    dma_score = min(dma_score + 2, 10)  # Death cross bonus

            score += dma_score
            details['dma'] = {'above_count': above_count, 'total': total_dmas, 'score': dma_score}

        # Price Range Position (10 pts)
        one_year_high = tl.one_year_high
        one_year_low = tl.one_year_low

        if one_year_high and one_year_low and price:
            range_size = one_year_high - one_year_low
            if range_size > 0:
                position_in_range = (price - one_year_low) / range_size

                if self.direction == 'LONG':
                    # Near 52W high is strength for LONG
                    if position_in_range > 0.9:
                        range_score = 10  # Near 52W high
                    elif position_in_range > 0.7:
                        range_score = 7
                    elif position_in_range > 0.5:
                        range_score = 5
                    else:
                        range_score = 2  # Near 52W low - weak
                else:  # SHORT
                    # Near 52W low is strength for SHORT
                    if position_in_range < 0.1:
                        range_score = 10  # Near 52W low
                    elif position_in_range < 0.3:
                        range_score = 7
                    elif position_in_range < 0.5:
                        range_score = 5
                    else:
                        range_score = 2

                score += range_score
                details['price_range'] = {'position': position_in_range, 'score': range_score}

        # Breakout Detection (5 pts) — enhanced with volume confirmation & fake breakout penalty
        week_high = tl.week_high
        week_low = tl.week_low
        month_high = tl.month_high
        month_low = tl.month_low
        day_high = tl.day_high
        day_low = tl.day_low

        breakout_score = 0
        breakout_details = {}
        if self.direction == 'LONG':
            if day_high and week_high and day_high >= week_high:
                breakout_score += 2  # Weekly breakout
            if day_high and month_high and day_high >= month_high:
                breakout_score += 3  # Monthly breakout
            # Fake breakout penalty: broke resistance but closed below
            if day_high and week_high and day_high >= week_high and price and price < week_high:
                breakout_score = max(0, breakout_score - 3)
                breakout_details['fake_breakout'] = True
        else:  # SHORT
            if day_low and week_low and day_low <= week_low:
                breakout_score += 2  # Weekly breakdown
            if day_low and month_low and day_low <= month_low:
                breakout_score += 3  # Monthly breakdown
            # Fake breakdown penalty: broke support but closed above
            if day_low and week_low and day_low <= week_low and price and price > week_low:
                breakout_score = max(0, breakout_score - 3)
                breakout_details['fake_breakout'] = True

        # Breakout volume confirmation
        vol = tl.day_volume
        avg_vol = tl.month_volume_avg
        if vol and avg_vol and avg_vol > 0:
            vol_ratio = vol / avg_vol
            if vol_ratio > 2.0:
                breakout_score = min(breakout_score + 5, 5)  # Strong volume = full marks
                breakout_details['volume_confirmation'] = 'STRONG'
            elif vol_ratio > 1.5:
                breakout_score = min(breakout_score + 2, 5)
                breakout_details['volume_confirmation'] = 'MODERATE'
            breakout_details['volume_ratio'] = round(vol_ratio, 2)

        # Breakout proximity: within 2% = fresh, > 5% past = extended
        if one_year_high and price and self.direction == 'LONG':
            dist_from_high = (one_year_high - price) / one_year_high * 100 if one_year_high > 0 else 100
            if dist_from_high <= 2:
                breakout_score = min(breakout_score + 3, 5)
                breakout_details['proximity'] = 'FRESH'
            elif dist_from_high > 5:
                breakout_details['proximity'] = 'EXTENDED'

        breakout_score = min(breakout_score, 5)
        score += breakout_score
        breakout_details['score'] = breakout_score
        details['breakout'] = breakout_details

        # 52W Breakout Detection (5 pts) - NEW Phase 2
        fifty_two_week_score = 0
        if one_year_high and one_year_low and price:
            # Calculate proximity to 52W high/low
            high_distance_pct = ((one_year_high - price) / one_year_high * 100) if one_year_high > 0 else 100
            low_distance_pct = ((price - one_year_low) / one_year_low * 100) if one_year_low > 0 else 100

            if self.direction == 'LONG':
                # Near 52W high = bullish momentum
                if high_distance_pct <= 2:
                    fifty_two_week_score = 5  # Within 2% of 52W high - breakout potential
                    details['52w_status'] = '52W_HIGH_BREAKOUT'
                elif high_distance_pct <= 5:
                    fifty_two_week_score = 4  # Within 5% of 52W high
                    details['52w_status'] = 'NEAR_52W_HIGH'
                elif high_distance_pct <= 10:
                    fifty_two_week_score = 3
                    details['52w_status'] = 'APPROACHING_52W_HIGH'
                else:
                    fifty_two_week_score = 1
                    details['52w_status'] = 'FAR_FROM_52W_HIGH'
            else:  # SHORT
                # Near 52W low = bearish momentum
                if low_distance_pct <= 5:
                    fifty_two_week_score = 5  # Within 5% of 52W low - breakdown
                    details['52w_status'] = '52W_LOW_BREAKDOWN'
                elif low_distance_pct <= 10:
                    fifty_two_week_score = 4
                    details['52w_status'] = 'NEAR_52W_LOW'
                elif low_distance_pct <= 20:
                    fifty_two_week_score = 3
                    details['52w_status'] = 'APPROACHING_52W_LOW'
                else:
                    fifty_two_week_score = 1
                    details['52w_status'] = 'FAR_FROM_52W_LOW'

            details['52w_high'] = one_year_high
            details['52w_low'] = one_year_low
            details['52w_high_distance_pct'] = round(high_distance_pct, 2)
            details['52w_low_distance_pct'] = round(low_distance_pct, 2)

        score += fifty_two_week_score
        details['52w_breakout'] = {'score': fifty_two_week_score}

        self.details['trend_confirmation'] = details
        logger.info(f"  Trend Confirmation: {score}/30")

        return min(score, 30)

    def _score_volume_quality(self) -> int:
        """
        Score Volume Quality (max 25 pts) - Phase 2 Enhanced
        - Volume Surge: 10 pts
        - Delivery %: 5 pts
        - VWAP Position: 5 pts
        - Delivery Trend: 5 pts (NEW Phase 2)
        """
        score = 0
        details = {}

        if not self._tl_stock_data:
            self.details['volume_quality'] = {'score': 0, 'reason': 'No data'}
            return 0

        tl = self._tl_stock_data

        # Volume Surge (10 pts)
        volume_multiple = tl.day_volume_multiple_of_week
        if volume_multiple:
            if volume_multiple > 3:
                surge_score = 10  # Major surge
            elif volume_multiple > 2:
                surge_score = 7  # Significant surge
            elif volume_multiple > 1.5:
                surge_score = 5  # Moderate surge
            elif volume_multiple > 1:
                surge_score = 3  # Above average
            else:
                surge_score = 1  # Below average
            score += surge_score
            details['volume_surge'] = {'multiple': volume_multiple, 'score': surge_score}
        else:
            # Fallback to manual calculation
            day_vol = tl.day_volume or 0
            week_avg = tl.week_volume_avg or 1
            if week_avg > 0:
                manual_multiple = day_vol / week_avg
                if manual_multiple > 2:
                    surge_score = 7
                elif manual_multiple > 1.5:
                    surge_score = 5
                else:
                    surge_score = 2
                score += surge_score
                details['volume_surge'] = {'multiple': manual_multiple, 'score': surge_score}

        # Delivery % (5 pts)
        delivery_pct = tl.delivery_volume_pct_eod
        if delivery_pct:
            if delivery_pct > 70:
                delivery_score = 5  # Very strong hands
            elif delivery_pct > 50:
                delivery_score = 4  # Strong hands
            elif delivery_pct > 35:
                delivery_score = 2  # Moderate
            else:
                delivery_score = 0  # Speculation
            score += delivery_score
            details['delivery'] = {'pct': delivery_pct, 'score': delivery_score}

        # VWAP Position (5 pts)
        vwap = tl.vwap_day
        price = tl.current_price
        if vwap and price:
            if self.direction == 'LONG':
                if price > vwap:
                    vwap_score = 5  # Above VWAP - bullish
                elif price > vwap * 0.99:
                    vwap_score = 3  # Near VWAP
                else:
                    vwap_score = 1  # Below VWAP
            else:  # SHORT
                if price < vwap:
                    vwap_score = 5  # Below VWAP - bearish
                elif price < vwap * 1.01:
                    vwap_score = 3  # Near VWAP
                else:
                    vwap_score = 1  # Above VWAP
            score += vwap_score
            details['vwap'] = {'vwap': vwap, 'price': price, 'score': vwap_score}

        # Delivery Trend Analysis (5 pts) - NEW Phase 2
        delivery_trend_score = 0
        delivery_pct_eod = tl.delivery_volume_pct_eod
        delivery_pct_prev = tl.delivery_volume_pct_prev_eod
        delivery_avg_week = tl.delivery_volume_avg_week
        delivery_avg_month = tl.delivery_volume_avg_month
        price_change = tl.day_change_pct or 0

        if delivery_pct_eod:
            # Analyze delivery trend
            delivery_increasing = False
            delivery_above_avg = False

            # Compare with previous day
            if delivery_pct_prev and delivery_pct_eod > delivery_pct_prev:
                delivery_increasing = True

            # Compare with weekly average
            if delivery_avg_week and delivery_pct_eod > delivery_avg_week:
                delivery_above_avg = True

            # Interpret based on price movement and direction
            if self.direction == 'LONG':
                # For LONG: Rising delivery + Rising price = Accumulation
                if delivery_increasing and price_change > 0:
                    delivery_trend_score = 5  # Strong accumulation
                    details['delivery_trend'] = 'ACCUMULATION'
                elif delivery_above_avg and price_change > 0:
                    delivery_trend_score = 4  # Moderate accumulation
                    details['delivery_trend'] = 'MODERATE_ACCUMULATION'
                elif delivery_increasing:
                    delivery_trend_score = 3  # Increasing delivery
                    details['delivery_trend'] = 'DELIVERY_INCREASING'
                elif delivery_above_avg:
                    delivery_trend_score = 2  # Above average
                    details['delivery_trend'] = 'ABOVE_AVG_DELIVERY'
                else:
                    delivery_trend_score = 1
                    details['delivery_trend'] = 'NORMAL'
            else:  # SHORT
                # For SHORT: Rising delivery + Falling price = Distribution
                if delivery_increasing and price_change < 0:
                    delivery_trend_score = 5  # Strong distribution
                    details['delivery_trend'] = 'DISTRIBUTION'
                elif delivery_above_avg and price_change < 0:
                    delivery_trend_score = 4  # Moderate distribution
                    details['delivery_trend'] = 'MODERATE_DISTRIBUTION'
                elif delivery_increasing:
                    delivery_trend_score = 3
                    details['delivery_trend'] = 'DELIVERY_INCREASING'
                elif delivery_above_avg:
                    delivery_trend_score = 2
                    details['delivery_trend'] = 'ABOVE_AVG_DELIVERY'
                else:
                    delivery_trend_score = 1
                    details['delivery_trend'] = 'NORMAL'

            details['delivery_trend_details'] = {
                'eod': delivery_pct_eod,
                'prev_eod': delivery_pct_prev,
                'week_avg': delivery_avg_week,
                'month_avg': delivery_avg_month,
                'price_change': price_change,
                'increasing': delivery_increasing,
                'above_avg': delivery_above_avg,
                'score': delivery_trend_score
            }

        score += delivery_trend_score

        self.details['volume_quality'] = details
        logger.info(f"  Volume Quality: {score}/25")

        return min(score, 25)

    def _score_institutional_flow(self) -> int:
        """
        Score Institutional Flow (max 25 pts)
        - FII Change: 10 pts
        - MF Change: 5 pts
        - Promoter Change: 5 pts
        - Total Institutional: 5 pts
        """
        score = 0
        details = {}

        if not self._tl_stock_data:
            self.details['institutional_flow'] = {'score': 0, 'reason': 'No data'}
            return 0

        tl = self._tl_stock_data

        # FII Change (10 pts)
        fii_change = tl.fii_holding_change_qoq_pct
        if fii_change is not None:
            if fii_change > 1:
                fii_score = 10  # Strong accumulation
            elif fii_change > 0.5:
                fii_score = 7
            elif fii_change > 0:
                fii_score = 5
            elif fii_change > -0.5:
                fii_score = 3
            else:
                fii_score = 0  # FII selling
            score += fii_score
            details['fii'] = {'change': fii_change, 'score': fii_score}

        # MF Change (5 pts)
        mf_change = tl.mf_holding_change_qoq_pct
        if mf_change is not None:
            if mf_change > 0.5:
                mf_score = 5
            elif mf_change > 0:
                mf_score = 3
            elif mf_change > -0.5:
                mf_score = 2
            else:
                mf_score = 0
            score += mf_score
            details['mf'] = {'change': mf_change, 'score': mf_score}

        # Promoter Change (5 pts)
        promoter_change = tl.promoter_holding_change_qoq_pct
        if promoter_change is not None:
            if promoter_change > 0:
                promoter_score = 5  # Promoter buying
            elif promoter_change > -0.5:
                promoter_score = 3  # Stable
            else:
                promoter_score = 0  # Promoter selling
            score += promoter_score
            details['promoter'] = {'change': promoter_change, 'score': promoter_score}

        # Total Institutional (5 pts)
        inst_change = tl.institutional_holding_change_qoq_pct
        if inst_change is not None:
            if inst_change > 1:
                inst_score = 5
            elif inst_change > 0:
                inst_score = 3
            else:
                inst_score = 1
            score += inst_score
            details['institutional'] = {'change': inst_change, 'score': inst_score}

        self.details['institutional_flow'] = details
        logger.info(f"  Institutional Flow: {score}/25")

        return min(score, 25)

    def _score_fundamental_quality(self) -> int:
        """
        Score Fundamental Quality (max 20 pts)
        - Piotroski Score: 10 pts
        - Profit Growth: 5 pts
        - ROE: 5 pts
        """
        score = 0
        details = {}

        if not self._tl_stock_data:
            self.details['fundamental_quality'] = {'score': 0, 'reason': 'No data'}
            return 0

        tl = self._tl_stock_data

        # Piotroski Score (10 pts)
        piotroski = tl.piotroski_score
        if piotroski is not None:
            if piotroski >= 7:
                piotroski_score = 10  # Financially strong
            elif piotroski >= 5:
                piotroski_score = 6
            elif piotroski >= 4:
                piotroski_score = 3
            else:
                piotroski_score = 0
            score += piotroski_score
            details['piotroski'] = {'value': piotroski, 'score': piotroski_score}

        # Profit Growth (5 pts)
        profit_growth = tl.net_profit_qtr_growth_yoy_pct
        if profit_growth is not None:
            if profit_growth > 20:
                growth_score = 5
            elif profit_growth > 10:
                growth_score = 4
            elif profit_growth > 0:
                growth_score = 2
            else:
                growth_score = 0
            score += growth_score
            details['profit_growth'] = {'value': profit_growth, 'score': growth_score}

        # ROE (5 pts)
        roe = tl.roe_annual_pct
        if roe is not None:
            if roe > 20:
                roe_score = 5
            elif roe > 15:
                roe_score = 4
            elif roe > 10:
                roe_score = 2
            else:
                roe_score = 0
            score += roe_score
            details['roe'] = {'value': roe, 'score': roe_score}

        self.details['fundamental_quality'] = details
        logger.info(f"  Fundamental Quality: {score}/20")

        return min(score, 20)

    def _score_risk_adjustment(self) -> int:
        """
        Score Risk Adjustment (max 30 pts)
        - Beta: 10 pts
        - Volatility: 10 pts
        - Valuation: 10 pts
        """
        score = 0
        details = {}

        if not self._tl_stock_data:
            self.details['risk_adjustment'] = {'score': 0, 'reason': 'No data'}
            return 0

        tl = self._tl_stock_data

        # Beta (10 pts) - Moderate beta is ideal
        beta = tl.beta_1year
        if beta is not None:
            if 0.8 <= beta <= 1.2:
                beta_score = 10  # Ideal beta range
            elif 0.6 <= beta <= 1.5:
                beta_score = 7  # Acceptable
            elif beta < 0.6:
                beta_score = 4  # Low beta - may lack movement
            else:
                beta_score = 3  # High beta - risky
            score += beta_score
            details['beta'] = {'value': beta, 'score': beta_score}

        # Volatility (10 pts) - Lower is better
        if self._contract_stock_data:
            volatility = self._contract_stock_data.annualized_volatility or 0
            if volatility < 25:
                vol_score = 10  # Low volatility
            elif volatility < 35:
                vol_score = 7
            elif volatility < 45:
                vol_score = 5
            else:
                vol_score = 2  # High volatility
            score += vol_score
            details['volatility'] = {'value': volatility, 'score': vol_score}

        # Valuation (10 pts)
        pe_ttm = tl.pe_ttm_price_to_earnings
        pe_5yr = tl.pe_5yr_average
        if pe_ttm is not None and pe_5yr is not None and pe_5yr > 0:
            pe_ratio = pe_ttm / pe_5yr
            if self.direction == 'LONG':
                if pe_ratio < 0.8:
                    val_score = 10  # Undervalued
                elif pe_ratio < 1.0:
                    val_score = 7
                elif pe_ratio < 1.2:
                    val_score = 5
                else:
                    val_score = 2  # Overvalued
            else:  # SHORT
                if pe_ratio > 1.5:
                    val_score = 10  # Overvalued - good for short
                elif pe_ratio > 1.2:
                    val_score = 7
                else:
                    val_score = 3
            score += val_score
            details['valuation'] = {'pe_ttm': pe_ttm, 'pe_5yr': pe_5yr, 'ratio': pe_ratio, 'score': val_score}

        self.details['risk_adjustment'] = details
        logger.info(f"  Risk Adjustment: {score}/30")

        return min(score, 30)

    def _score_news_sentiment(self) -> int:
        """
        Score News Sentiment (max 25 pts)
        - Stock News: 15 pts
        - Market News: 5 pts
        - Sector News: 5 pts
        """
        score = 0
        details = {}

        try:
            from apps.data.models import NewsArticle

            # Get stock-specific news from last 24 hours (single query)
            cutoff = timezone.now() - timedelta(hours=24)
            now = timezone.now()
            stock_news = list(NewsArticle.objects.filter(
                symbols_mentioned__contains=[self.symbol],
                published_at__gte=cutoff
            ).order_by('-published_at')[:10])

            if stock_news:
                # Freshness-weighted + source-quality-weighted average sentiment
                # OPINION/GENERAL articles are capped at ±0.3 (low-value commentary)
                OPINION_TYPES = {'OPINION', 'GENERAL'}
                weighted_sum, total_weight = 0.0, 0.0
                article_count = 0
                for n in stock_news:
                    if n.sentiment_score is None:
                        continue
                    sentiment = n.sentiment_score
                    # Cap low-value event types so they can't dominate the signal
                    if getattr(n, 'event_type', '') in OPINION_TYPES:
                        sentiment = max(-0.3, min(0.3, sentiment))
                    hours_old = max(0, (now - n.published_at).total_seconds() / 3600)
                    freshness = max(0.3, 1.0 - (hours_old / 24) * 0.7)  # 1.0→0.3 over 24h
                    quality = getattr(n, 'source_quality_score', None) or 0.6
                    w = freshness * quality
                    weighted_sum += sentiment * w
                    total_weight += w
                    article_count += 1

                if total_weight > 0:
                    avg_sentiment = weighted_sum / total_weight

                    if self.direction == 'LONG':
                        if avg_sentiment > 0.5:
                            stock_score = 15
                        elif avg_sentiment > 0.2:
                            stock_score = 10
                        elif avg_sentiment > 0:
                            stock_score = 7
                        elif avg_sentiment > -0.3:
                            stock_score = 3
                        else:
                            stock_score = 0
                    else:  # SHORT
                        if avg_sentiment < -0.5:
                            stock_score = 15
                        elif avg_sentiment < -0.2:
                            stock_score = 10
                        elif avg_sentiment < 0:
                            stock_score = 7
                        else:
                            stock_score = 3

                    score += stock_score
                    details['stock_news'] = {
                        'count': article_count,
                        'avg_sentiment': round(avg_sentiment, 3),
                        'score': stock_score
                    }
                else:
                    # Articles exist but none have been LLM-analyzed yet — neutral fallback
                    score += 7
                    details['stock_news'] = {'count': len(stock_news), 'score': 7, 'reason': 'No sentiment data yet'}
            else:
                # No news found — neutral fallback
                score += 7
                details['stock_news'] = {'count': 0, 'score': 7, 'reason': 'No recent news'}

            # Market news sentiment (from hard reject check if available)
            market_check = self.details.get('hard_reject_checks', {}).get('blocking_news', {})
            market_sentiment = market_check.get('value', 0)

            if self.direction == 'LONG':
                if market_sentiment > 0.2:
                    market_score = 5
                elif market_sentiment > 0:
                    market_score = 3
                else:
                    market_score = 1
            else:
                if market_sentiment < -0.2:
                    market_score = 5
                elif market_sentiment < 0:
                    market_score = 3
                else:
                    market_score = 1

            score += market_score
            details['market_news'] = {'sentiment': market_sentiment, 'score': market_score}

            # Sector news — real implementation
            sector_score, sector_details = self._score_sector_news_component()
            score += sector_score
            details['sector_news'] = sector_details

        except Exception as e:
            logger.warning(f"News sentiment scoring error: {e}")
            score = 12  # Default neutral score
            details['error'] = str(e)

        self.details['news_sentiment'] = details
        logger.info(f"  News Sentiment: {score}/25")

        return min(score, 25)

    def _score_sector_news_component(self):
        """
        Score sector news (0-5 pts).

        Fetches or uses pre-fetched INDUSTRY articles for this stock's sector.
        Falls back to neutral 3 pts if sector is unknown or fetch fails.
        Returns (score, details_dict).
        """
        default_result = (3, {'score': 3, 'reason': 'No sector data'})
        try:
            sector_name = None
            if self._tl_stock_data:
                sector_name = getattr(self._tl_stock_data, 'sector_name', None)
            if not sector_name:
                return default_result

            from apps.data.models import NewsArticle
            cutoff = timezone.now() - timedelta(hours=24)
            sector_articles = list(NewsArticle.objects.filter(
                news_type='INDUSTRY',
                sectors_mentioned__contains=[sector_name],
                published_at__gte=cutoff
            ).order_by('-published_at')[:10])

            # If too few cached articles, fetch fresh from GNews and store for future runs.
            # Newly stored articles have no LLM sentiment yet so are NOT scored this run.
            if len(sector_articles) < 3:
                try:
                    from apps.data.services.gnews_client import get_gnews_client
                    gnews = get_gnews_client()
                    result = gnews.fetch_industry_news(
                        industry=sector_name, max_results=5
                    )
                    for art in result.get('articles', []):
                        url = art.get('url', '')
                        if url and NewsArticle.objects.filter(url=url).exists():
                            continue
                        NewsArticle.objects.create(
                            title=art.get('title', ''),
                            content=art.get('content') or art.get('description', ''),
                            source=art.get('source', {}).get('name', 'GNews'),
                            url=url,
                            published_at=timezone.now(),
                            news_type='INDUSTRY',
                            sectors_mentioned=[sector_name],
                        )
                        # Not appended to sector_articles — no sentiment score yet
                except Exception as _fe:
                    logger.debug(f"Sector news fetch failed for {sector_name}: {_fe}")

            if not sector_articles:
                return default_result

            # Weighted average (freshness + quality)
            now = timezone.now()
            weighted_sum, total_weight = 0.0, 0.0
            for n in sector_articles:
                if n.sentiment_score is None:
                    continue
                hours_old = max(0, (now - n.published_at).total_seconds() / 3600)
                freshness = max(0.3, 1.0 - (hours_old / 24) * 0.7)
                quality = getattr(n, 'source_quality_score', None) or 0.6
                w = freshness * quality
                weighted_sum += n.sentiment_score * w
                total_weight += w

            if total_weight == 0:
                return default_result

            avg = weighted_sum / total_weight
            if avg > 0.2:
                sector_score = 5
            elif avg > 0:
                sector_score = 3
            elif avg > -0.2:
                sector_score = 2
            else:
                sector_score = 1

            return (sector_score, {
                'score': sector_score,
                'sector': sector_name,
                'count': len(sector_articles),
                'avg_sentiment': round(avg, 3),
            })

        except Exception as e:
            logger.warning(f"Sector news scoring error: {e}")
            return default_result

    def _score_analyst_consensus(self) -> int:
        """
        Score Analyst Consensus (max 20 pts)
        - Upside %: 10 pts
        - Recommendation Ratio: 5 pts
        - Coverage: 5 pts
        """
        score = 0
        details = {}

        # Use data from hard reject check if available
        analyst_data = self.details.get('analyst_data', {})
        price_target = analyst_data.get('price_target', {})

        if not price_target:
            try:
                from apps.llm.services.analyst_report_aggregator import get_analyst_report_aggregator
                aggregator = get_analyst_report_aggregator()
                price_target = aggregator.get_price_target(self.symbol)
            except:
                pass

        if price_target:
            # Upside % (10 pts)
            upside = price_target.get('upside_pct')
            if upside is not None:
                if self.direction == 'LONG':
                    if upside > 20:
                        upside_score = 10
                    elif upside > 15:
                        upside_score = 8
                    elif upside > 10:
                        upside_score = 6
                    elif upside > 5:
                        upside_score = 4
                    else:
                        upside_score = 2
                else:  # SHORT
                    if upside < 0:
                        upside_score = 10  # Negative upside = downside
                    elif upside < 5:
                        upside_score = 6
                    else:
                        upside_score = 2
                score += upside_score
                details['upside'] = {'value': upside, 'score': upside_score}

            # Recommendation Ratio (5 pts)
            buy_count = (price_target.get('strong_buy_count', 0) +
                        price_target.get('buy_count', 0))
            sell_count = (price_target.get('sell_count', 0) +
                         price_target.get('strong_sell_count', 0))
            total = price_target.get('analyst_count', 0)

            if total > 0:
                buy_pct = (buy_count / total) * 100
                sell_pct = (sell_count / total) * 100

                if self.direction == 'LONG':
                    if buy_pct > 70:
                        rec_score = 5
                    elif buy_pct > 50:
                        rec_score = 3
                    else:
                        rec_score = 1
                else:  # SHORT
                    if sell_pct > 30:
                        rec_score = 5
                    elif sell_pct > 20:
                        rec_score = 3
                    else:
                        rec_score = 1

                score += rec_score
                details['recommendation'] = {'buy_pct': buy_pct, 'sell_pct': sell_pct, 'score': rec_score}

            # Coverage (5 pts)
            analyst_count = price_target.get('analyst_count', 0)
            if analyst_count >= 10:
                coverage_score = 5
            elif analyst_count >= 5:
                coverage_score = 3
            elif analyst_count >= 2:
                coverage_score = 2
            else:
                coverage_score = 0
            score += coverage_score
            details['coverage'] = {'count': analyst_count, 'score': coverage_score}
        else:
            score = 10  # Default neutral
            details['reason'] = 'No analyst data available'

        self.details['analyst_consensus'] = details
        logger.info(f"  Analyst Consensus: {score}/20")

        return min(score, 20)

    def _score_research_reports(self) -> int:
        """
        Score Research Reports (max 15 pts)
        - Report Sentiment: 10 pts
        - Risk/Catalysts: 5 pts

        Also generates 5-point summaries for the latest 3 reports.
        """
        score = 0
        details = {}

        try:
            from apps.data.models import AnalystReport

            # Get recent reports (last 3 months)
            cutoff = timezone.now().date() - timedelta(days=90)
            reports = AnalystReport.objects.filter(
                nse_code=self.symbol,
                report_date__gte=cutoff,
                llm_processed=True
            ).order_by('-report_date')[:10]

            if reports.exists():
                reports_list = list(reports)

                # Average sentiment from LLM analysis
                sentiments = [r.sentiment_score for r in reports_list if r.sentiment_score is not None]
                if sentiments:
                    avg_sentiment = sum(sentiments) / len(sentiments)

                    if self.direction == 'LONG':
                        if avg_sentiment > 0.5:
                            sentiment_score = 10
                        elif avg_sentiment > 0.2:
                            sentiment_score = 7
                        elif avg_sentiment > 0:
                            sentiment_score = 5
                        else:
                            sentiment_score = 2
                    else:  # SHORT
                        if avg_sentiment < -0.5:
                            sentiment_score = 10
                        elif avg_sentiment < -0.2:
                            sentiment_score = 7
                        elif avg_sentiment < 0:
                            sentiment_score = 5
                        else:
                            sentiment_score = 2

                    score += sentiment_score
                    details['sentiment'] = {'avg': avg_sentiment, 'count': len(sentiments), 'score': sentiment_score}

                # Risk/Catalysts (5 pts)
                has_catalysts = any(r.catalysts for r in reports_list if r.catalysts)
                has_risks = any(r.risk_factors for r in reports_list if r.risk_factors)

                if self.direction == 'LONG':
                    if has_catalysts and not has_risks:
                        rc_score = 5
                    elif has_catalysts:
                        rc_score = 3
                    else:
                        rc_score = 1
                else:  # SHORT
                    if has_risks and not has_catalysts:
                        rc_score = 5
                    elif has_risks:
                        rc_score = 3
                    else:
                        rc_score = 1

                score += rc_score
                details['risk_catalysts'] = {'has_catalysts': has_catalysts, 'has_risks': has_risks, 'score': rc_score}

                # Generate 5-point summaries for latest 3 reports (shared with Verify Trade)
                details['report_summaries'] = self._get_report_summaries(reports_list[:3])
            else:
                score = 7  # Default neutral
                details['reason'] = 'No recent reports'
                details['report_summaries'] = []

        except Exception as e:
            logger.warning(f"Research reports scoring error: {e}")
            score = 7
            details['error'] = str(e)
            details['report_summaries'] = []

        self.details['research_reports'] = details
        logger.info(f"  Research Reports: {score}/15")

        return min(score, 15)

    def _get_report_summaries(self, reports: list, max_reports: int = 3) -> list:
        """
        Get 5-point summaries for analyst reports.

        Uses the shared get_quick_summaries_for_reports function from
        analyst_report_analyzer to avoid code duplication with Verify Trade.

        Args:
            reports: List of AnalystReport model instances
            max_reports: Maximum reports to summarize (default: 3)

        Returns:
            List of dicts with report info and 5-point summaries
        """
        try:
            from apps.llm.services.analyst_report_analyzer import get_quick_summaries_for_reports

            summaries = get_quick_summaries_for_reports(
                reports=reports,
                symbol=self.symbol,
                max_reports=max_reports
            )
            logger.info(f"  Generated {len([s for s in summaries if s.get('success')])} report summaries")
            return summaries
        except Exception as e:
            logger.warning(f"Could not generate report summaries: {e}")
            return []

    def _score_investor_calls(self) -> int:
        """
        Score Investor Calls (max 10 pts)
        - Management Tone: 5 pts
        - Trading Signal: 5 pts
        """
        score = 0
        details = {}

        try:
            from apps.data.models import InvestorCall

            # Get recent calls (last 90 days)
            cutoff = timezone.now().date() - timedelta(days=90)
            calls = InvestorCall.objects.filter(
                symbol=self.symbol,
                call_date__gte=cutoff,
                processed=True
            ).order_by('-call_date')[:3]

            if calls.exists():
                latest_call = calls.first()

                # Management Tone (5 pts)
                tone = latest_call.management_tone
                if tone:
                    if self.direction == 'LONG':
                        if tone == 'POSITIVE':
                            tone_score = 5
                        elif tone == 'NEUTRAL':
                            tone_score = 3
                        else:
                            tone_score = 1
                    else:  # SHORT
                        if tone == 'NEGATIVE':
                            tone_score = 5
                        elif tone == 'NEUTRAL':
                            tone_score = 3
                        else:
                            tone_score = 1
                    score += tone_score
                    details['tone'] = {'value': tone, 'score': tone_score}

                # Trading Signal (5 pts)
                signal = latest_call.trading_signal
                confidence = latest_call.confidence_score or 0
                if signal:
                    aligned = (
                        (self.direction == 'LONG' and signal == 'BULLISH') or
                        (self.direction == 'SHORT' and signal == 'BEARISH')
                    )
                    if aligned and confidence > 0.7:
                        signal_score = 5
                    elif aligned:
                        signal_score = 3
                    else:
                        signal_score = 1
                    score += signal_score
                    details['signal'] = {'value': signal, 'confidence': confidence, 'score': signal_score}
            else:
                score = 5  # Default neutral
                details['reason'] = 'No recent calls'

        except Exception as e:
            logger.warning(f"Investor calls scoring error: {e}")
            score = 5
            details['error'] = str(e)

        self.details['investor_calls'] = details
        logger.info(f"  Investor Calls: {score}/10")

        return min(score, 10)

    def _score_momentum_acceleration(self) -> int:
        """
        Score Momentum Acceleration (max 20 pts) - NEW Phase 2

        Compares current momentum with previous day and previous week:
        - Accelerating momentum (current > prev_day > prev_week): Bonus points
        - Decelerating momentum (current < prev_day < prev_week): Reduced points
        - Consistent direction alignment with trade direction: Additional points

        Scoring breakdown:
        - Acceleration Pattern: 10 pts
        - Consistency: 5 pts
        - Direction Alignment: 5 pts
        """
        score = 0
        details = {}

        if not self._tl_stock_data:
            self.details['momentum_acceleration'] = {'score': 0, 'reason': 'No data'}
            return 0

        tl = self._tl_stock_data

        # Get momentum scores
        current_momentum = tl.trendlyne_momentum_score
        prev_day_momentum = tl.prev_day_trendlyne_momentum_score
        prev_week_momentum = tl.prev_week_trendlyne_momentum_score

        # Store raw values in details
        details['current_momentum'] = current_momentum
        details['prev_day_momentum'] = prev_day_momentum
        details['prev_week_momentum'] = prev_week_momentum

        # If no momentum data, return neutral score
        if current_momentum is None:
            score = 10  # Default neutral
            details['reason'] = 'No momentum data available'
            self.details['momentum_acceleration'] = details
            logger.info(f"  Momentum Acceleration: {score}/20 (no data)")
            return score

        # Acceleration Pattern Analysis (10 pts)
        acceleration_score = 0
        pattern = 'UNKNOWN'

        if prev_day_momentum is not None and prev_week_momentum is not None:
            # Calculate changes
            day_change = current_momentum - prev_day_momentum
            week_change = current_momentum - prev_week_momentum

            details['day_change'] = round(day_change, 2)
            details['week_change'] = round(week_change, 2)

            # Determine pattern
            if current_momentum > prev_day_momentum > prev_week_momentum:
                # Strong accelerating momentum
                pattern = 'STRONG_ACCELERATION'
                acceleration_score = 10
            elif current_momentum > prev_day_momentum and current_momentum > prev_week_momentum:
                # Moderate acceleration
                pattern = 'MODERATE_ACCELERATION'
                acceleration_score = 8
            elif current_momentum > prev_week_momentum and day_change > 0:
                # Mild acceleration
                pattern = 'MILD_ACCELERATION'
                acceleration_score = 6
            elif current_momentum < prev_day_momentum < prev_week_momentum:
                # Strong deceleration
                pattern = 'STRONG_DECELERATION'
                acceleration_score = 2
            elif current_momentum < prev_day_momentum and current_momentum < prev_week_momentum:
                # Moderate deceleration
                pattern = 'MODERATE_DECELERATION'
                acceleration_score = 3
            elif abs(day_change) < 5 and abs(week_change) < 10:
                # Stable momentum
                pattern = 'STABLE'
                acceleration_score = 5
            else:
                # Mixed signals
                pattern = 'MIXED'
                acceleration_score = 4

            details['pattern'] = pattern
        elif prev_day_momentum is not None:
            # Only day comparison available
            day_change = current_momentum - prev_day_momentum
            details['day_change'] = round(day_change, 2)

            if day_change > 5:
                pattern = 'DAY_IMPROVING'
                acceleration_score = 6
            elif day_change > 0:
                pattern = 'DAY_SLIGHTLY_IMPROVING'
                acceleration_score = 5
            elif day_change > -5:
                pattern = 'DAY_STABLE'
                acceleration_score = 4
            else:
                pattern = 'DAY_DECLINING'
                acceleration_score = 3
            details['pattern'] = pattern
        else:
            # Only current momentum available — D-1 data missing from Trendlyne import
            acceleration_score = 5  # Neutral
            pattern = 'CURRENT_ONLY'
            details['pattern'] = pattern
            logger.warning(
                f"[{self.symbol}] Momentum acceleration: prev_day data missing — "
                f"using CURRENT_ONLY fallback (5/10 acceleration pts)"
            )

        score += acceleration_score
        details['acceleration_score'] = acceleration_score

        # Consistency Score (5 pts) - Are all momentum readings in same direction?
        consistency_score = 0
        if prev_day_momentum is not None and prev_week_momentum is not None:
            all_positive = current_momentum > 50 and prev_day_momentum > 50 and prev_week_momentum > 50
            all_negative = current_momentum < 50 and prev_day_momentum < 50 and prev_week_momentum < 50
            mostly_positive = sum(1 for m in [current_momentum, prev_day_momentum, prev_week_momentum] if m > 50) >= 2
            mostly_negative = sum(1 for m in [current_momentum, prev_day_momentum, prev_week_momentum] if m < 50) >= 2

            if all_positive or all_negative:
                consistency_score = 5  # Very consistent
                details['consistency'] = 'VERY_CONSISTENT'
            elif mostly_positive or mostly_negative:
                consistency_score = 3  # Mostly consistent
                details['consistency'] = 'MOSTLY_CONSISTENT'
            else:
                consistency_score = 1  # Inconsistent
                details['consistency'] = 'INCONSISTENT'
        else:
            consistency_score = 2  # Unknown
            details['consistency'] = 'UNKNOWN'

        score += consistency_score
        details['consistency_score'] = consistency_score

        # Direction Alignment Score (5 pts) - Does momentum support trade direction?
        alignment_score = 0
        if self.direction == 'LONG':
            # For LONG: Higher momentum is better
            if current_momentum >= 70:
                alignment_score = 5  # Strong bullish momentum
                details['alignment'] = 'STRONG_BULLISH'
            elif current_momentum >= 60:
                alignment_score = 4
                details['alignment'] = 'BULLISH'
            elif current_momentum >= 50:
                alignment_score = 3
                details['alignment'] = 'NEUTRAL_BULLISH'
            elif current_momentum >= 40:
                alignment_score = 2
                details['alignment'] = 'WEAK'
            else:
                alignment_score = 1  # Momentum against direction
                details['alignment'] = 'AGAINST'
        else:  # SHORT
            # For SHORT: Lower momentum is better
            if current_momentum <= 30:
                alignment_score = 5  # Strong bearish momentum
                details['alignment'] = 'STRONG_BEARISH'
            elif current_momentum <= 40:
                alignment_score = 4
                details['alignment'] = 'BEARISH'
            elif current_momentum <= 50:
                alignment_score = 3
                details['alignment'] = 'NEUTRAL_BEARISH'
            elif current_momentum <= 60:
                alignment_score = 2
                details['alignment'] = 'WEAK'
            else:
                alignment_score = 1  # Momentum against direction
                details['alignment'] = 'AGAINST'

        score += alignment_score
        details['alignment_score'] = alignment_score

        self.details['momentum_acceleration'] = details
        logger.info(
            f"  Momentum Acceleration: {score}/20 "
            f"(pattern={pattern}, momentum={current_momentum})"
        )

        return min(score, 20)

    def _score_mtf_confluence(self) -> int:
        """
        Score Multi-Timeframe Confluence (max 15 pts) - Phase 3

        Checks alignment of daily trend with weekly/monthly trends.
        - Weekly trend matches daily: +5
        - Monthly trend matches: +5
        - Divergence penalty: daily LONG but weekly bearish = -5
        """
        score = 0
        details = {}

        if not self._tl_stock_data:
            self.details['mtf_confluence'] = {'score': 0, 'reason': 'No data'}
            return 0

        tl = self._tl_stock_data
        price = tl.current_price or 0

        # Determine weekly trend from 5-day and 30-day SMAs
        sma5 = tl.day5_sma
        sma30 = tl.day30_sma
        sma50 = tl.day50_sma
        sma200 = tl.day200_sma

        # Weekly trend: price vs 30-day SMA
        weekly_bullish = None
        if price and sma30:
            weekly_bullish = price > sma30
            details['weekly_trend'] = 'BULLISH' if weekly_bullish else 'BEARISH'

        # Monthly trend: 50-day SMA slope (approximated by 50 vs 200 SMA)
        monthly_bullish = None
        if sma50 and sma200:
            monthly_bullish = sma50 > sma200
            details['monthly_trend'] = 'BULLISH' if monthly_bullish else 'BEARISH'

        # Scoring
        if self.direction == 'LONG':
            if weekly_bullish is True:
                score += 5
                details['weekly_alignment'] = 'ALIGNED'
            elif weekly_bullish is False:
                score -= 5  # Divergence penalty
                details['weekly_alignment'] = 'DIVERGENT'

            if monthly_bullish is True:
                score += 5
                details['monthly_alignment'] = 'ALIGNED'
            elif monthly_bullish is False:
                score -= 5
                details['monthly_alignment'] = 'DIVERGENT'
        else:  # SHORT
            if weekly_bullish is False:
                score += 5
                details['weekly_alignment'] = 'ALIGNED'
            elif weekly_bullish is True:
                score -= 5
                details['weekly_alignment'] = 'DIVERGENT'

            if monthly_bullish is False:
                score += 5
                details['monthly_alignment'] = 'ALIGNED'
            elif monthly_bullish is True:
                score -= 5
                details['monthly_alignment'] = 'DIVERGENT'

        # Short-term confirmation bonus: 5-day SMA alignment
        if sma5 and sma30:
            short_aligned = (sma5 > sma30) if self.direction == 'LONG' else (sma5 < sma30)
            if short_aligned:
                score += 5
                details['short_term'] = 'CONFIRMED'
            else:
                details['short_term'] = 'NEUTRAL'

        score = max(0, min(score, 15))
        details['score'] = score

        self.details['mtf_confluence'] = details
        logger.info(f"  MTF Confluence: {score}/15")

        return score

    # =========================================================================
    # ENTRY PARAMETERS & POSITION SIZING
    # =========================================================================

    def _calculate_entry_params(self) -> Dict:
        """Calculate entry parameters using adaptive SL/Target engine."""
        if not self._tl_stock_data:
            return {}

        tl = self._tl_stock_data
        price = tl.current_price or 0
        atr = tl.day_atr

        # Get volatility for Tier 3 fallback
        volatility_pct = None
        if self._contract_stock_data:
            volatility_pct = self._contract_stock_data.annualized_volatility

        # Composite score for context
        composite_score = sum(self.scores.values())
        scaled_score = int((composite_score / self.TOTAL_WEIGHT) * 100) if self.TOTAL_WEIGHT > 0 else 0

        # Use adaptive SL/target engine (3-tier: SR → ATR → Volatility)
        from apps.strategies.services.adaptive_sl_target import compute_adaptive_sl_target
        sl_result = compute_adaptive_sl_target(
            symbol=self.symbol,
            price=float(price),
            direction=self.direction,
            atr=float(atr) if atr else None,
            volatility_pct=float(volatility_pct) if volatility_pct else None,
            composite_score=scaled_score,
            regime=self.regime,
            support_s1=float(tl.first_support_s1) if tl.first_support_s1 else None,
            resistance_r1=float(tl.first_resistance_r1) if tl.first_resistance_r1 else None,
        )

        stop_loss = sl_result['stop_loss']
        target_1 = sl_result['target_1']
        target_2 = sl_result['target_2']

        # Calculate position sizing
        position_sizing = self._calculate_position_sizing(float(price), stop_loss)

        return {
            'entry_price': float(price),
            'stop_loss': round(stop_loss, 2),
            'target_1': round(target_1, 2),
            'target_2': round(target_2, 2),
            'atr': atr,
            'risk': sl_result['risk'],
            'reward': sl_result['reward'],
            'risk_reward_ratio': sl_result['risk_reward_ratio'],
            'sl_type': sl_result['sl_type'],
            'regime': sl_result['regime'],
            'rr_rejected': sl_result.get('rr_rejected', False),
            'support_s1': float(tl.first_support_s1) if tl.first_support_s1 else None,
            'resistance_r1': float(tl.first_resistance_r1) if tl.first_resistance_r1 else None,
            'position_sizing': position_sizing,
        }

    def _calculate_position_sizing(self, entry_price: float, stop_loss: float) -> Dict:
        """
        Calculate position sizing based on risk parameters.

        Factors considered:
        1. Beta - Higher beta = smaller position
        2. Volatility - Higher volatility = smaller position
        3. Composite Score - Higher score = can use larger position
        4. Risk per trade - Fixed at 2% of capital

        Returns position multiplier and recommended lot sizing.
        """
        BASE_RISK_PCT = 0.02  # 2% risk per trade
        DEFAULT_CAPITAL = 500000  # Default capital for calculations

        sizing = {
            'base_multiplier': 1.0,
            'beta_adjustment': 1.0,
            'volatility_adjustment': 1.0,
            'score_adjustment': 1.0,
            'final_multiplier': 1.0,
            'risk_per_trade_pct': BASE_RISK_PCT * 100,
            'recommended_lots': 1,
            'adjustments_applied': [],
        }

        # 1. Beta Adjustment
        beta = None
        if self._tl_stock_data:
            beta = self._tl_stock_data.beta_1year

        if beta is not None:
            if beta >= 1.5:
                sizing['beta_adjustment'] = 0.70  # Reduce 30% for very high beta
                sizing['adjustments_applied'].append(f"High beta ({beta:.2f}): -30%")
            elif beta >= 1.2:
                sizing['beta_adjustment'] = 0.85  # Reduce 15% for high beta
                sizing['adjustments_applied'].append(f"Elevated beta ({beta:.2f}): -15%")
            elif beta <= 0.7:
                sizing['beta_adjustment'] = 1.00  # Keep standard for low beta (less movement)
                sizing['adjustments_applied'].append(f"Low beta ({beta:.2f}): standard")
            else:
                sizing['beta_adjustment'] = 1.00  # Normal beta range
            sizing['beta'] = beta

        # 2. Volatility Adjustment
        volatility = None
        if self._contract_stock_data:
            volatility = self._contract_stock_data.annualized_volatility

        if volatility is not None:
            if volatility >= 50:
                sizing['volatility_adjustment'] = 0.70  # High volatility
                sizing['adjustments_applied'].append(f"High volatility ({volatility:.1f}%): -30%")
            elif volatility >= 40:
                sizing['volatility_adjustment'] = 0.85
                sizing['adjustments_applied'].append(f"Elevated volatility ({volatility:.1f}%): -15%")
            elif volatility >= 30:
                sizing['volatility_adjustment'] = 0.95
                sizing['adjustments_applied'].append(f"Moderate volatility ({volatility:.1f}%): -5%")
            elif volatility < 20:
                sizing['volatility_adjustment'] = 1.10  # Low volatility - can size up
                sizing['adjustments_applied'].append(f"Low volatility ({volatility:.1f}%): +10%")
            else:
                sizing['volatility_adjustment'] = 1.00
            sizing['volatility'] = volatility

        # 3. Composite Score Adjustment
        composite_score = sum(self.scores.values()) / self.TOTAL_WEIGHT * 100 if self.scores else 50

        if composite_score >= 80:
            sizing['score_adjustment'] = 1.20  # Strong conviction
            sizing['adjustments_applied'].append(f"High score ({composite_score:.0f}): +20%")
        elif composite_score >= 70:
            sizing['score_adjustment'] = 1.10
            sizing['adjustments_applied'].append(f"Good score ({composite_score:.0f}): +10%")
        elif composite_score >= 60:
            sizing['score_adjustment'] = 1.00  # Standard
        elif composite_score >= 50:
            sizing['score_adjustment'] = 0.90
            sizing['adjustments_applied'].append(f"Lower score ({composite_score:.0f}): -10%")
        else:
            sizing['score_adjustment'] = 0.75
            sizing['adjustments_applied'].append(f"Weak score ({composite_score:.0f}): -25%")

        sizing['composite_score'] = composite_score

        # Calculate final multiplier (cap between 0.5 and 1.5)
        final_multiplier = (
            sizing['beta_adjustment'] *
            sizing['volatility_adjustment'] *
            sizing['score_adjustment']
        )
        sizing['final_multiplier'] = round(max(0.5, min(1.5, final_multiplier)), 2)

        # Calculate recommended lots based on risk
        risk_per_share = abs(entry_price - stop_loss) if entry_price and stop_loss else entry_price * 0.02
        if risk_per_share > 0:
            # Risk amount = Capital * Risk % * Position Multiplier
            risk_amount = DEFAULT_CAPITAL * BASE_RISK_PCT * sizing['final_multiplier']
            max_shares = int(risk_amount / risk_per_share)

            # Get lot size from ContractData (futures contract), fallback to 1
            lot_size = 1
            if self._contract_data is not None:
                futures_contract = self._contract_data.filter(option_type='FUT').first()
                if futures_contract and futures_contract.lot_size:
                    lot_size = futures_contract.lot_size

            sizing['lot_size'] = lot_size
            sizing['max_shares_by_risk'] = max_shares
            sizing['recommended_lots'] = max(1, int(max_shares / lot_size)) if lot_size > 0 else 1
            sizing['position_value'] = round(sizing['recommended_lots'] * lot_size * entry_price, 2)

        logger.info(
            f"  Position Sizing: {sizing['final_multiplier']}x multiplier, "
            f"{sizing['recommended_lots']} lots recommended"
        )

        return sizing


# Convenience function
def analyze_stock_for_futures(symbol: str, direction: str, expiry: str = None) -> Dict:
    """
    Analyze a stock for futures trading.

    Args:
        symbol: Stock symbol
        direction: 'LONG' or 'SHORT'
        expiry: Optional expiry date

    Returns:
        Analysis result dict
    """
    analyzer = EnhancedFuturesAnalyzer(symbol, direction, expiry)
    return analyzer.analyze()
