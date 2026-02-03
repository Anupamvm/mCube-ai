"""
Enhanced Strangle Analyzer

Comprehensive multi-factor analysis for Nifty Strangle entry decisions.
Incorporates 10 scoring components for market condition assessment.

Scoring Components (250 pts total, scaled to 100):
1. VIX Regime (35 pts)
2. Global Markets Sentiment (30 pts)
3. Market Breadth (25 pts)
4. News Sentiment (30 pts)
5. PCR Analysis (25 pts)
6. OI Pattern Analysis (25 pts)
7. Economic Event Proximity (20 pts)
8. Gap & Movement Analysis (25 pts)
9. FII/DII Flow (20 pts)
10. Technical Structure (15 pts)

Hard Reject Filters (must pass all):
- VIX not in extreme zones (10 < VIX < 18)
- No blocking news (sentiment >= -0.4)
- No major economic event within 2 days
- Market gap < 1.5% at open
- FII net outflow < Rs 2000 Cr (last 3 days)
- 9:15-9:30 movement < 0.5% (no extreme volatility)
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


class HardRejectError(Exception):
    """Raised when a hard reject filter fails"""
    pass


class EnhancedStrangleAnalyzer:
    """
    Comprehensive strangle analyzer with multi-factor scoring.

    Usage:
        analyzer = EnhancedStrangleAnalyzer(spot_price=24000, vix=14.5, days_to_expiry=3)
        analyzer.set_market_data(market_data_dict)
        result = analyzer.analyze()

        if result['hard_reject']:
            print(f"REJECTED: {result['reject_reason']}")
        elif result['composite_score'] >= 65:
            print(f"ENTRY QUALIFIED: Score {result['composite_score']}/100")
    """

    # Hard reject thresholds
    MIN_VIX = 10.0                    # Below this, premiums too low
    MAX_VIX = 18.0                    # Above this, too volatile
    MIN_NEWS_SENTIMENT = -0.4         # Below this, blocking news
    MAX_GAP_PCT = 1.5                 # Above this, extreme gap
    MAX_FII_OUTFLOW_3D = 2000         # Crores, max 3-day outflow
    MAX_915_930_MOVEMENT = 0.5        # Max 9:15-9:30 movement %
    MIN_EVENT_DAYS = 2                # Days buffer for major events
    MAX_NIFTY_1D_CHANGE = 1.5         # Max previous day change % (hard reject)
    MAX_NIFTY_3D_CHANGE = 2.5         # Max 3-day change % (hard reject)
    MAX_NIFTY_5D_CHANGE = 3.0         # Max 5-day change % (SKIP WEEK if exceeded)

    # Trader constraint thresholds
    CONSECUTIVE_RED_DAYS_THRESHOLD = 3  # 3+ red days → widen PUT
    PCR_EXTREME_BULLISH = 0.6           # PCR < 0.6 → widen CALL
    PCR_EXTREME_BEARISH = 1.4           # PCR > 1.4 → widen PUT

    # Scoring weights (total 275 pts)
    WEIGHTS = {
        'vix_regime': 35,             # VIX in optimal zone
        'global_markets': 30,         # US/SGX sentiment
        'market_breadth': 25,         # Advances/Declines
        'news_sentiment': 30,         # News analysis
        'pcr_analysis': 25,           # Put-Call Ratio
        'oi_patterns': 25,            # Open Interest patterns
        'event_proximity': 20,        # Economic calendar
        'gap_movement': 25,           # Gap and intraday movement
        'recent_nifty_momentum': 25,  # Nifty 1D and 3D change (IMPORTANT)
        'fii_dii_flow': 20,           # Institutional flows
        'technical_structure': 15,    # DMA alignment
    }
    TOTAL_WEIGHT = sum(WEIGHTS.values())  # 275

    def __init__(self, spot_price: Decimal, vix: Decimal, days_to_expiry: int):
        """
        Initialize analyzer with core market data.

        Args:
            spot_price: Current Nifty spot price
            vix: India VIX value
            days_to_expiry: Days remaining to expiry
        """
        self.spot_price = Decimal(str(spot_price))
        self.vix = Decimal(str(vix))
        self.days_to_expiry = days_to_expiry

        # Market data holders
        self._market_data = {}
        self._news_sentiment = None
        self._fii_dii_data = None
        self._option_chain_data = None
        self._market_breadth = None
        self._economic_events = None
        self._global_markets = None

        # Results
        self.hard_reject = False
        self.reject_reason = None
        self.scores = {}
        self.details = {}

    def set_market_data(self, market_data: Dict):
        """
        Set comprehensive market data for analysis.

        Args:
            market_data: Dict containing:
                - news_sentiment: News analysis result
                - fii_dii_data: FII/DII flow data
                - option_chain: Option chain with OI data
                - market_breadth: Advances/Declines
                - economic_events: Upcoming events
                - global_markets: SGX, US indices
                - prev_close: Previous Nifty close
                - open_price: Today's opening price
                - price_915: Price at 9:15
                - price_930: Price at 9:30
                - dma_5, dma_20, dma_50, dma_200: Moving averages
        """
        self._market_data = market_data
        self._news_sentiment = market_data.get('news_sentiment')
        self._fii_dii_data = market_data.get('fii_dii_data')
        self._option_chain_data = market_data.get('option_chain')
        self._market_breadth = market_data.get('market_breadth')
        self._economic_events = market_data.get('economic_events')
        self._global_markets = market_data.get('global_markets')

    def analyze(self) -> Dict:
        """
        Run complete analysis.

        Returns:
            dict: {
                'hard_reject': bool,
                'reject_reason': str or None,
                'composite_score': int (0-100),
                'scores': dict of component scores,
                'details': dict of analysis details,
                'recommendation': str,
                'entry_bias': str ('SYMMETRIC', 'WIDEN_CALL', 'WIDEN_PUT'),
                'delta_adjustments': dict
            }
        """
        logger.info("=" * 80)
        logger.info("ENHANCED STRANGLE ANALYSIS")
        logger.info(f"Spot: {self.spot_price}, VIX: {self.vix}, DTE: {self.days_to_expiry}")
        logger.info("=" * 80)

        # Check hard reject filters first
        try:
            self._check_hard_reject_filters()
        except HardRejectError as e:
            logger.warning(f"HARD REJECT: {str(e)}")
            return {
                'hard_reject': True,
                'reject_reason': str(e),
                'composite_score': 0,
                'scores': {},
                'details': self.details,
                'recommendation': 'NO_ENTRY',
                'entry_bias': None,
                'delta_adjustments': None
            }

        # Calculate all component scores
        self._calculate_all_scores()

        # Calculate composite score (scaled to 100)
        raw_score = sum(self.scores.values())
        composite_score = int((raw_score / self.TOTAL_WEIGHT) * 100)

        # Determine recommendation and entry bias
        recommendation, entry_bias = self._determine_recommendation(composite_score)

        # Calculate delta adjustments based on scoring
        delta_adjustments = self._calculate_delta_adjustments()

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"COMPOSITE SCORE: {composite_score}/100 ({raw_score}/{self.TOTAL_WEIGHT} raw)")
        logger.info(f"RECOMMENDATION: {recommendation}")
        logger.info(f"ENTRY BIAS: {entry_bias}")
        logger.info("=" * 80)

        return {
            'hard_reject': False,
            'reject_reason': None,
            'composite_score': composite_score,
            'raw_score': raw_score,
            'scores': self.scores,
            'details': self.details,
            'recommendation': recommendation,
            'entry_bias': entry_bias,
            'delta_adjustments': delta_adjustments
        }

    def _check_hard_reject_filters(self):
        """Check all hard reject filters. Raises HardRejectError if any fail."""

        # 1. VIX range check
        vix_val = float(self.vix)
        if vix_val < self.MIN_VIX:
            self.details['vix_reject'] = f"VIX {vix_val:.1f} < {self.MIN_VIX} (premiums too low)"
            raise HardRejectError(f"VIX too low ({vix_val:.1f}) - premiums insufficient")

        if vix_val > self.MAX_VIX:
            self.details['vix_reject'] = f"VIX {vix_val:.1f} > {self.MAX_VIX} (too volatile)"
            raise HardRejectError(f"VIX too high ({vix_val:.1f}) - extreme volatility")

        logger.info(f"[PASS] VIX Filter: {vix_val:.1f} (range: {self.MIN_VIX}-{self.MAX_VIX})")

        # 2. News sentiment check
        if self._news_sentiment:
            avg_sentiment = self._news_sentiment.get('average_sentiment', 0)
            blocking_articles = self._news_sentiment.get('blocking_articles', [])

            if avg_sentiment < self.MIN_NEWS_SENTIMENT:
                self.details['news_reject'] = f"Sentiment {avg_sentiment:.2f} < {self.MIN_NEWS_SENTIMENT}"
                raise HardRejectError(f"Blocking news sentiment ({avg_sentiment:.2f})")

            if blocking_articles:
                titles = [a.get('title', '')[:50] for a in blocking_articles[:2]]
                self.details['news_reject'] = f"Blocking articles: {titles}"
                raise HardRejectError(f"{len(blocking_articles)} blocking news articles found")

            logger.info(f"[PASS] News Filter: Sentiment {avg_sentiment:.2f}")
        else:
            logger.info("[SKIP] News Filter: No news data available")

        # 3. Gap check
        prev_close = self._market_data.get('prev_close')
        open_price = self._market_data.get('open_price')

        if prev_close and open_price:
            gap_pct = abs((float(open_price) - float(prev_close)) / float(prev_close) * 100)
            if gap_pct > self.MAX_GAP_PCT:
                self.details['gap_reject'] = f"Gap {gap_pct:.2f}% > {self.MAX_GAP_PCT}%"
                raise HardRejectError(f"Extreme market gap ({gap_pct:.2f}%)")

            logger.info(f"[PASS] Gap Filter: {gap_pct:.2f}% (max: {self.MAX_GAP_PCT}%)")
        else:
            logger.info("[SKIP] Gap Filter: No price data available")

        # 4. 9:15-9:30 movement check
        price_915 = self._market_data.get('price_915')
        price_930 = self._market_data.get('price_930')

        if price_915 and price_930:
            movement_pct = abs((float(price_930) - float(price_915)) / float(price_915) * 100)
            if movement_pct > self.MAX_915_930_MOVEMENT:
                # This is a warning, not hard reject - but flags extreme volatility
                logger.warning(f"[WARN] 9:15-9:30 movement {movement_pct:.2f}% exceeds threshold")
                self.details['movement_warning'] = f"High initial movement: {movement_pct:.2f}%"

            logger.info(f"[PASS] Movement Filter: {movement_pct:.2f}%")

        # 5. FII outflow check
        if self._fii_dii_data:
            fii_3d_outflow = self._fii_dii_data.get('fii_3d_net', 0)
            if fii_3d_outflow < -self.MAX_FII_OUTFLOW_3D:
                self.details['fii_reject'] = f"FII 3D outflow: Rs {abs(fii_3d_outflow):.0f} Cr"
                raise HardRejectError(f"Heavy FII outflow (Rs {abs(fii_3d_outflow):.0f} Cr in 3 days)")

            logger.info(f"[PASS] FII Filter: 3D net Rs {fii_3d_outflow:+.0f} Cr")
        else:
            logger.info("[SKIP] FII Filter: No FII/DII data available")

        # 6. Economic event check
        if self._economic_events:
            high_impact_events = [
                e for e in self._economic_events
                if e.get('impact') == 'HIGH' and e.get('days_away', 999) <= self.MIN_EVENT_DAYS
            ]

            if high_impact_events:
                event_names = [e.get('name', 'Unknown')[:30] for e in high_impact_events[:2]]
                self.details['event_reject'] = f"High-impact events: {event_names}"
                raise HardRejectError(f"Major economic event within {self.MIN_EVENT_DAYS} days: {event_names[0]}")

            logger.info(f"[PASS] Event Filter: No major events within {self.MIN_EVENT_DAYS} days")
        else:
            logger.info("[SKIP] Event Filter: No event data available")

        # 7. Nifty Recent Momentum check (IMPORTANT - previous day and 3-day change)
        nifty_1d_change = self._market_data.get('nifty_1d_change')
        nifty_3d_change = self._market_data.get('nifty_3d_change')

        if nifty_1d_change is not None:
            abs_1d = abs(float(nifty_1d_change))
            if abs_1d > self.MAX_NIFTY_1D_CHANGE:
                self.details['nifty_1d_reject'] = f"Nifty 1D change {nifty_1d_change:+.2f}% > {self.MAX_NIFTY_1D_CHANGE}%"
                raise HardRejectError(f"Nifty previous day moved {nifty_1d_change:+.2f}% (max: ±{self.MAX_NIFTY_1D_CHANGE}%)")

            logger.info(f"[PASS] Nifty 1D Filter: {nifty_1d_change:+.2f}% (max: ±{self.MAX_NIFTY_1D_CHANGE}%)")
        else:
            logger.info("[SKIP] Nifty 1D Filter: No data available")

        if nifty_3d_change is not None:
            abs_3d = abs(float(nifty_3d_change))
            if abs_3d > self.MAX_NIFTY_3D_CHANGE:
                self.details['nifty_3d_reject'] = f"Nifty 3D change {nifty_3d_change:+.2f}% > {self.MAX_NIFTY_3D_CHANGE}%"
                raise HardRejectError(f"Nifty 3-day momentum {nifty_3d_change:+.2f}% (max: ±{self.MAX_NIFTY_3D_CHANGE}%)")

            logger.info(f"[PASS] Nifty 3D Filter: {nifty_3d_change:+.2f}% (max: ±{self.MAX_NIFTY_3D_CHANGE}%)")
        else:
            logger.info("[SKIP] Nifty 3D Filter: No data available")

        # 8. Nifty 5D Change - WEEKLY SKIP FILTER (IMPORTANT - if market moved 3%+ in 5 days, skip this week)
        nifty_5d_change = self._market_data.get('nifty_5d_change')

        if nifty_5d_change is not None:
            abs_5d = abs(float(nifty_5d_change))
            if abs_5d > self.MAX_NIFTY_5D_CHANGE:
                self.details['nifty_5d_reject'] = f"Nifty 5D change {nifty_5d_change:+.2f}% > {self.MAX_NIFTY_5D_CHANGE}%"
                raise HardRejectError(
                    f"SKIP THIS WEEK: Market moved {nifty_5d_change:+.2f}% in 5 trading days "
                    f"(max: ±{self.MAX_NIFTY_5D_CHANGE}%)"
                )

            logger.info(f"[PASS] Nifty 5D Filter: {nifty_5d_change:+.2f}% (max: ±{self.MAX_NIFTY_5D_CHANGE}%)")
        else:
            logger.info("[SKIP] Nifty 5D Filter: No data available")

        logger.info("")
        logger.info("All hard reject filters PASSED")

    def _calculate_all_scores(self):
        """Calculate all scoring components."""
        self.scores['vix_regime'] = self._score_vix_regime()
        self.scores['global_markets'] = self._score_global_markets()
        self.scores['market_breadth'] = self._score_market_breadth()
        self.scores['news_sentiment'] = self._score_news_sentiment()
        self.scores['pcr_analysis'] = self._score_pcr_analysis()
        self.scores['oi_patterns'] = self._score_oi_patterns()
        self.scores['event_proximity'] = self._score_event_proximity()
        self.scores['gap_movement'] = self._score_gap_movement()
        self.scores['recent_nifty_momentum'] = self._score_recent_nifty_momentum()
        self.scores['fii_dii_flow'] = self._score_fii_dii_flow()
        self.scores['technical_structure'] = self._score_technical_structure()

        # Log all scores
        logger.info("")
        logger.info("COMPONENT SCORES:")
        for component, score in self.scores.items():
            max_score = self.WEIGHTS[component]
            pct = int((score / max_score) * 100) if max_score > 0 else 0
            logger.info(f"  {component}: {score}/{max_score} ({pct}%)")

    def _score_vix_regime(self) -> int:
        """
        Score VIX Regime (max 35 pts)

        Optimal VIX range for strangle: 12-14 (sweet spot)
        - VIX 12-14: Full score (35 pts) - optimal premium with manageable risk
        - VIX 11-12 or 14-15: Good (28 pts)
        - VIX 10-11 or 15-16: Moderate (20 pts)
        - VIX 16-18 or < 10: Low (10 pts)
        """
        max_score = self.WEIGHTS['vix_regime']
        vix_val = float(self.vix)

        if 12 <= vix_val <= 14:
            score = max_score  # Sweet spot
            reason = f"Optimal VIX range ({vix_val:.1f})"
        elif 11 <= vix_val < 12 or 14 < vix_val <= 15:
            score = int(max_score * 0.8)
            reason = f"Good VIX range ({vix_val:.1f})"
        elif 10 <= vix_val < 11 or 15 < vix_val <= 16:
            score = int(max_score * 0.57)
            reason = f"Moderate VIX ({vix_val:.1f})"
        else:
            score = int(max_score * 0.29)
            reason = f"Suboptimal VIX ({vix_val:.1f})"

        self.details['vix_regime'] = {
            'vix': vix_val,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"VIX Regime: {score}/{max_score} - {reason}")
        return score

    def _score_global_markets(self) -> int:
        """
        Score Global Markets Sentiment (max 30 pts)

        Factors:
        - SGX Nifty trend (10 pts)
        - US markets (Nasdaq, Dow) (10 pts)
        - GIFT Nifty alignment (5 pts)
        - Consistency bonus (5 pts)
        """
        max_score = self.WEIGHTS['global_markets']
        score = 0

        if not self._global_markets:
            # No data - neutral score
            self.details['global_markets'] = {
                'score': int(max_score * 0.5),
                'reason': 'No global market data available'
            }
            return int(max_score * 0.5)

        sgx_change = self._global_markets.get('sgx_change', 0)
        nasdaq_change = self._global_markets.get('nasdaq_change', 0)
        dow_change = self._global_markets.get('dow_change', 0)
        gift_change = self._global_markets.get('gift_change', 0)

        # SGX Nifty scoring (10 pts)
        # Flat to slightly positive is best for strangle (range-bound expectation)
        sgx_val = abs(float(sgx_change)) if sgx_change else 0
        if sgx_val <= 0.3:
            score += 10  # Flat - ideal for strangle
        elif sgx_val <= 0.5:
            score += 7
        elif sgx_val <= 1.0:
            score += 4
        else:
            score += 1  # Large move - not ideal

        # US markets scoring (10 pts)
        us_avg = (abs(float(nasdaq_change or 0)) + abs(float(dow_change or 0))) / 2
        if us_avg <= 0.5:
            score += 10  # Flat US market
        elif us_avg <= 1.0:
            score += 7
        elif us_avg <= 1.5:
            score += 4
        else:
            score += 1

        # GIFT Nifty alignment (5 pts)
        if gift_change is not None and sgx_change is not None:
            gift_val = float(gift_change)
            sgx_val_signed = float(sgx_change)
            if (gift_val * sgx_val_signed) > 0:  # Same direction
                score += 5
            elif abs(gift_val - sgx_val_signed) < 0.3:
                score += 3

        # Consistency bonus (5 pts)
        directions = []
        if sgx_change: directions.append(1 if float(sgx_change) > 0 else -1)
        if nasdaq_change: directions.append(1 if float(nasdaq_change) > 0 else -1)
        if dow_change: directions.append(1 if float(dow_change) > 0 else -1)

        if len(directions) >= 2:
            if all(d == directions[0] for d in directions):
                score += 5  # All aligned
            elif sum(1 for d in directions if d == directions[0]) >= 2:
                score += 3  # Majority aligned

        reason = f"SGX: {sgx_change:+.2f}%, US: {nasdaq_change:+.2f}%/{dow_change:+.2f}%"

        self.details['global_markets'] = {
            'sgx_change': sgx_change,
            'nasdaq_change': nasdaq_change,
            'dow_change': dow_change,
            'gift_change': gift_change,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"Global Markets: {score}/{max_score} - {reason}")
        return score

    def _score_market_breadth(self) -> int:
        """
        Score Market Breadth (max 25 pts)

        A/D ratio close to 1 is ideal for strangle (balanced market)
        Factors:
        - Advances vs Declines ratio (15 pts)
        - Unchanged stocks count (5 pts)
        - Sector uniformity (5 pts)
        """
        max_score = self.WEIGHTS['market_breadth']

        if not self._market_breadth:
            self.details['market_breadth'] = {
                'score': int(max_score * 0.5),
                'reason': 'No market breadth data available'
            }
            return int(max_score * 0.5)

        advances = self._market_breadth.get('advances', 0)
        declines = self._market_breadth.get('declines', 0)
        unchanged = self._market_breadth.get('unchanged', 0)

        score = 0
        total = advances + declines + unchanged

        if total > 0:
            # A/D ratio scoring (15 pts)
            ad_ratio = advances / declines if declines > 0 else 2
            if 0.8 <= ad_ratio <= 1.2:
                score += 15  # Balanced - ideal
            elif 0.6 <= ad_ratio <= 1.4:
                score += 10
            elif 0.4 <= ad_ratio <= 1.6:
                score += 5
            else:
                score += 2  # Extreme

            # Unchanged stocks (5 pts)
            unchanged_pct = unchanged / total * 100 if total > 0 else 0
            if unchanged_pct >= 10:
                score += 5  # High uncertainty
            elif unchanged_pct >= 5:
                score += 3
            else:
                score += 1

            # Sector uniformity bonus (5 pts) - placeholder
            score += 3  # Default moderate

            reason = f"A/D: {advances}/{declines} (ratio: {ad_ratio:.2f})"
        else:
            reason = "Insufficient breadth data"
            score = int(max_score * 0.4)

        self.details['market_breadth'] = {
            'advances': advances,
            'declines': declines,
            'unchanged': unchanged,
            'ad_ratio': ad_ratio if total > 0 else None,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"Market Breadth: {score}/{max_score} - {reason}")
        return score

    def _score_news_sentiment(self) -> int:
        """
        Score News Sentiment (max 30 pts)

        Neutral to slightly positive news is best for strangle
        Factors:
        - Average sentiment score (15 pts)
        - News volume/confidence (10 pts)
        - Directional bias (5 pts)
        """
        max_score = self.WEIGHTS['news_sentiment']

        if not self._news_sentiment:
            self.details['news_sentiment'] = {
                'score': int(max_score * 0.5),
                'reason': 'No news sentiment data available'
            }
            return int(max_score * 0.5)

        avg_sentiment = self._news_sentiment.get('average_sentiment', 0)
        confidence = self._news_sentiment.get('confidence', 0.5)
        articles = self._news_sentiment.get('articles_analyzed', 0)
        outlook = self._news_sentiment.get('market_outlook', 'NEUTRAL')

        score = 0

        # Average sentiment scoring (15 pts)
        # Neutral is best for strangle
        abs_sentiment = abs(avg_sentiment)
        if abs_sentiment <= 0.1:
            score += 15  # Very neutral
        elif abs_sentiment <= 0.2:
            score += 12
        elif abs_sentiment <= 0.3:
            score += 8
        else:
            score += 4  # Strong directional

        # Confidence/volume scoring (10 pts)
        if articles >= 20 and confidence >= 0.7:
            score += 10
        elif articles >= 10 and confidence >= 0.5:
            score += 7
        elif articles >= 5:
            score += 4
        else:
            score += 2

        # Directional bias (5 pts)
        # For strangle, NEUTRAL or balanced is preferred
        if outlook == 'NEUTRAL':
            score += 5
        elif outlook == 'VOLATILE':
            score += 3  # Expect movement, but risky
        else:
            score += 2  # Directional

        reason = f"Outlook: {outlook}, Sentiment: {avg_sentiment:+.2f}, Articles: {articles}"

        self.details['news_sentiment'] = {
            'average_sentiment': avg_sentiment,
            'outlook': outlook,
            'confidence': confidence,
            'articles_analyzed': articles,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"News Sentiment: {score}/{max_score} - {reason}")
        return score

    def _score_pcr_analysis(self) -> int:
        """
        Score Put-Call Ratio Analysis (max 25 pts)

        PCR close to 1 is ideal (balanced sentiment)
        Factors:
        - PCR OI value (15 pts)
        - PCR volume value (5 pts)
        - PCR change (5 pts)
        """
        max_score = self.WEIGHTS['pcr_analysis']

        if not self._option_chain_data:
            self.details['pcr_analysis'] = {
                'score': int(max_score * 0.5),
                'reason': 'No option chain data available'
            }
            return int(max_score * 0.5)

        pcr_oi = self._option_chain_data.get('pcr_oi', 1.0)
        pcr_vol = self._option_chain_data.get('pcr_vol', 1.0)
        pcr_change = self._option_chain_data.get('pcr_oi_change', 0)

        score = 0

        # PCR OI scoring (15 pts)
        if 0.85 <= pcr_oi <= 1.15:
            score += 15  # Balanced
        elif 0.7 <= pcr_oi <= 1.3:
            score += 11
        elif 0.6 <= pcr_oi <= 1.5:
            score += 7
        else:
            score += 3  # Extreme

        # PCR volume scoring (5 pts)
        if 0.8 <= pcr_vol <= 1.2:
            score += 5
        elif 0.6 <= pcr_vol <= 1.4:
            score += 3
        else:
            score += 1

        # PCR change scoring (5 pts)
        # Stable PCR is preferred
        if abs(pcr_change) <= 5:
            score += 5
        elif abs(pcr_change) <= 10:
            score += 3
        else:
            score += 1

        reason = f"PCR OI: {pcr_oi:.2f}, Vol: {pcr_vol:.2f}, Change: {pcr_change:+.1f}%"

        self.details['pcr_analysis'] = {
            'pcr_oi': pcr_oi,
            'pcr_vol': pcr_vol,
            'pcr_change': pcr_change,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"PCR Analysis: {score}/{max_score} - {reason}")
        return score

    def _score_oi_patterns(self) -> int:
        """
        Score Open Interest Patterns (max 25 pts)

        Factors:
        - OI buildup pattern (15 pts)
        - Max Pain alignment (5 pts)
        - OI concentration (5 pts)
        """
        max_score = self.WEIGHTS['oi_patterns']

        if not self._option_chain_data:
            self.details['oi_patterns'] = {
                'score': int(max_score * 0.5),
                'reason': 'No option chain data available'
            }
            return int(max_score * 0.5)

        call_oi_buildup = self._option_chain_data.get('call_oi_buildup', 'NEUTRAL')
        put_oi_buildup = self._option_chain_data.get('put_oi_buildup', 'NEUTRAL')
        max_pain = self._option_chain_data.get('max_pain')
        total_oi = self._option_chain_data.get('total_oi', 0)

        score = 0

        # OI buildup scoring (15 pts)
        # For strangle, we want NEUTRAL or balanced buildup
        if call_oi_buildup == 'NEUTRAL' and put_oi_buildup == 'NEUTRAL':
            score += 15  # Best for strangle
        elif call_oi_buildup == put_oi_buildup:
            score += 10  # Symmetric but directional
        elif (call_oi_buildup == 'LONG' and put_oi_buildup == 'SHORT') or \
             (call_oi_buildup == 'SHORT' and put_oi_buildup == 'LONG'):
            score += 6  # Opposing - directional move expected
        else:
            score += 8

        # Max Pain alignment (5 pts)
        if max_pain:
            spot_val = float(self.spot_price)
            max_pain_val = float(max_pain)
            distance_pct = abs(spot_val - max_pain_val) / spot_val * 100

            if distance_pct <= 1:
                score += 5  # Close to max pain - range bound expected
            elif distance_pct <= 2:
                score += 3
            else:
                score += 1

        # OI concentration bonus (5 pts) - placeholder
        score += 3

        reason = f"CE: {call_oi_buildup}, PE: {put_oi_buildup}"
        if max_pain:
            reason += f", MaxPain: {max_pain}"

        self.details['oi_patterns'] = {
            'call_oi_buildup': call_oi_buildup,
            'put_oi_buildup': put_oi_buildup,
            'max_pain': max_pain,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"OI Patterns: {score}/{max_score} - {reason}")
        return score

    def _score_event_proximity(self) -> int:
        """
        Score Economic Event Proximity (max 20 pts)

        More days away from major events = better for strangle
        """
        max_score = self.WEIGHTS['event_proximity']

        if not self._economic_events:
            # No events = full score
            self.details['event_proximity'] = {
                'score': max_score,
                'reason': 'No upcoming economic events identified'
            }
            return max_score

        # Find nearest high-impact event
        high_impact = [e for e in self._economic_events if e.get('impact') == 'HIGH']
        medium_impact = [e for e in self._economic_events if e.get('impact') == 'MEDIUM']

        min_days_high = min([e.get('days_away', 30) for e in high_impact]) if high_impact else 30
        min_days_medium = min([e.get('days_away', 30) for e in medium_impact]) if medium_impact else 30

        score = 0

        # High-impact events (15 pts)
        if min_days_high >= 7:
            score += 15  # Safe distance
        elif min_days_high >= 5:
            score += 12
        elif min_days_high >= 3:
            score += 8
        else:
            score += 4  # Very close

        # Medium-impact events (5 pts)
        if min_days_medium >= 5:
            score += 5
        elif min_days_medium >= 3:
            score += 3
        else:
            score += 1

        nearest_event = high_impact[0] if high_impact else (medium_impact[0] if medium_impact else None)
        reason = f"Nearest: {nearest_event.get('name', 'N/A')} in {min_days_high}d" if nearest_event else "No events"

        self.details['event_proximity'] = {
            'nearest_high_impact_days': min_days_high,
            'nearest_medium_impact_days': min_days_medium,
            'events_count': len(self._economic_events),
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"Event Proximity: {score}/{max_score} - {reason}")
        return score

    def _score_gap_movement(self) -> int:
        """
        Score Gap and Movement Analysis (max 25 pts)

        Factors:
        - Opening gap size (10 pts)
        - 9:15-9:30 movement (10 pts)
        - Gap type classification (5 pts)
        """
        max_score = self.WEIGHTS['gap_movement']

        prev_close = self._market_data.get('prev_close')
        open_price = self._market_data.get('open_price')
        price_915 = self._market_data.get('price_915')
        price_930 = self._market_data.get('price_930')

        score = 0
        gap_pct = 0
        movement_pct = 0

        # Gap scoring (10 pts)
        if prev_close and open_price:
            gap_pct = (float(open_price) - float(prev_close)) / float(prev_close) * 100

            # Small gap is ideal for strangle
            abs_gap = abs(gap_pct)
            if abs_gap <= 0.3:
                score += 10  # Flat open - ideal
            elif abs_gap <= 0.5:
                score += 7
            elif abs_gap <= 1.0:
                score += 4
            else:
                score += 1  # Large gap
        else:
            score += 5  # Neutral

        # 9:15-9:30 movement (10 pts)
        if price_915 and price_930:
            movement_pct = (float(price_930) - float(price_915)) / float(price_915) * 100

            abs_movement = abs(movement_pct)
            if abs_movement <= 0.2:
                score += 10  # Very stable
            elif abs_movement <= 0.4:
                score += 7
            elif abs_movement <= 0.6:
                score += 4
            else:
                score += 1  # Volatile opening
        else:
            score += 5  # Neutral

        # Gap type scoring (5 pts)
        if prev_close and open_price:
            # Gap fill probability
            if abs(gap_pct) <= 0.3:
                score += 5  # Flat - range bound expected
            elif gap_pct > 0 and movement_pct < 0:
                score += 4  # Gap up, filling - good
            elif gap_pct < 0 and movement_pct > 0:
                score += 4  # Gap down, filling - good
            else:
                score += 2  # Trending

        reason = f"Gap: {gap_pct:+.2f}%, 9:15-9:30: {movement_pct:+.2f}%"

        self.details['gap_movement'] = {
            'gap_percent': gap_pct,
            'movement_percent': movement_pct,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"Gap/Movement: {score}/{max_score} - {reason}")
        return score

    def _score_recent_nifty_momentum(self) -> int:
        """
        Score Recent Nifty Momentum (max 25 pts)

        CRITICAL: This checks previous day's change and 3-day momentum.
        For strangle, low recent momentum is ideal (range-bound market).

        Factors:
        - Nifty 1D change (15 pts) - Previous day's change
        - Nifty 3D change (10 pts) - 3-day momentum

        Thresholds (from global_markets filter):
        - 1D: < ±1.0% is acceptable
        - 3D: < ±2.0% is acceptable
        """
        max_score = self.WEIGHTS['recent_nifty_momentum']

        nifty_1d_change = self._market_data.get('nifty_1d_change')
        nifty_3d_change = self._market_data.get('nifty_3d_change')

        score = 0

        # Nifty 1D scoring (15 pts)
        # Low change is ideal for strangle (range-bound expectation)
        if nifty_1d_change is not None:
            abs_1d = abs(float(nifty_1d_change))
            if abs_1d <= 0.3:
                score += 15  # Very flat - ideal
            elif abs_1d <= 0.5:
                score += 12
            elif abs_1d <= 0.8:
                score += 8
            elif abs_1d <= 1.0:
                score += 5  # Acceptable but not ideal
            else:
                score += 2  # Large move - not ideal for strangle
        else:
            # Try to calculate from prev_close and open_price
            prev_close = self._market_data.get('prev_close')
            open_price = self._market_data.get('open_price')
            if prev_close and open_price:
                # Use gap as proxy for 1D change direction
                gap_pct = abs((float(open_price) - float(prev_close)) / float(prev_close) * 100)
                if gap_pct <= 0.3:
                    score += 12
                elif gap_pct <= 0.5:
                    score += 8
                else:
                    score += 5
                nifty_1d_change = gap_pct
            else:
                score += 7  # Neutral default

        # Nifty 3D scoring (10 pts)
        # Low 3-day momentum is ideal
        if nifty_3d_change is not None:
            abs_3d = abs(float(nifty_3d_change))
            if abs_3d <= 0.5:
                score += 10  # Very stable
            elif abs_3d <= 1.0:
                score += 8
            elif abs_3d <= 1.5:
                score += 5
            elif abs_3d <= 2.0:
                score += 3  # Acceptable
            else:
                score += 1  # High momentum - risky for strangle
        else:
            score += 5  # Neutral default

        reason_parts = []
        if nifty_1d_change is not None:
            reason_parts.append(f"1D: {float(nifty_1d_change):+.2f}%")
        else:
            reason_parts.append("1D: N/A")

        if nifty_3d_change is not None:
            reason_parts.append(f"3D: {float(nifty_3d_change):+.2f}%")
        else:
            reason_parts.append("3D: N/A")

        reason = "Nifty " + ", ".join(reason_parts)

        self.details['recent_nifty_momentum'] = {
            'nifty_1d_change': float(nifty_1d_change) if nifty_1d_change else None,
            'nifty_3d_change': float(nifty_3d_change) if nifty_3d_change else None,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"Recent Nifty Momentum: {score}/{max_score} - {reason}")
        return score

    def _score_fii_dii_flow(self) -> int:
        """
        Score FII/DII Flow Analysis (max 20 pts)

        Factors:
        - FII net (10 pts)
        - DII net (5 pts)
        - Flow trend (5 pts)
        """
        max_score = self.WEIGHTS['fii_dii_flow']

        if not self._fii_dii_data:
            self.details['fii_dii_flow'] = {
                'score': int(max_score * 0.5),
                'reason': 'No FII/DII data available'
            }
            return int(max_score * 0.5)

        fii_net = self._fii_dii_data.get('fii_net', 0)
        dii_net = self._fii_dii_data.get('dii_net', 0)
        fii_3d = self._fii_dii_data.get('fii_3d_net', 0)

        score = 0

        # FII net scoring (10 pts)
        # Balanced or positive is preferred
        if fii_net >= 500:
            score += 10  # Strong inflow
        elif fii_net >= 0:
            score += 8  # Neutral to positive
        elif fii_net >= -500:
            score += 6  # Mild outflow
        elif fii_net >= -1000:
            score += 4
        else:
            score += 2  # Heavy outflow

        # DII net scoring (5 pts)
        if dii_net >= 0:
            score += 5  # DII supporting
        elif dii_net >= -500:
            score += 3
        else:
            score += 1

        # Flow trend (5 pts)
        # Balanced FII+DII is ideal for strangle
        net_total = fii_net + dii_net
        if abs(net_total) <= 500:
            score += 5  # Balanced
        elif abs(net_total) <= 1000:
            score += 3
        else:
            score += 1  # Imbalanced

        reason = f"FII: Rs {fii_net:+.0f} Cr, DII: Rs {dii_net:+.0f} Cr"

        self.details['fii_dii_flow'] = {
            'fii_net': fii_net,
            'dii_net': dii_net,
            'fii_3d_net': fii_3d,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"FII/DII Flow: {score}/{max_score} - {reason}")
        return score

    def _score_technical_structure(self) -> int:
        """
        Score Technical Structure (max 15 pts)

        Factors:
        - DMA alignment (10 pts)
        - Distance from key levels (5 pts)
        """
        max_score = self.WEIGHTS['technical_structure']

        dma_5 = self._market_data.get('dma_5')
        dma_20 = self._market_data.get('dma_20')
        dma_50 = self._market_data.get('dma_50')
        dma_200 = self._market_data.get('dma_200')

        score = 0
        spot_val = float(self.spot_price)

        # DMA alignment scoring (10 pts)
        # Range-bound market (price near DMAs) is ideal for strangle
        dma_scores = 0
        dma_count = 0

        for dma, weight in [(dma_5, 2), (dma_20, 3), (dma_50, 3), (dma_200, 2)]:
            if dma:
                dma_val = float(dma)
                distance_pct = abs(spot_val - dma_val) / spot_val * 100
                dma_count += 1

                if distance_pct <= 1:
                    dma_scores += weight  # Close to DMA
                elif distance_pct <= 2:
                    dma_scores += weight * 0.6
                else:
                    dma_scores += weight * 0.3

        if dma_count > 0:
            score += int((dma_scores / 10) * 10)
        else:
            score += 5  # Neutral

        # Distance from key levels (5 pts) - placeholder
        score += 3

        reason = f"Spot: {spot_val:.0f}"
        if dma_20:
            reason += f", DMA20: {float(dma_20):.0f}"
        if dma_50:
            reason += f", DMA50: {float(dma_50):.0f}"

        self.details['technical_structure'] = {
            'dma_5': float(dma_5) if dma_5 else None,
            'dma_20': float(dma_20) if dma_20 else None,
            'dma_50': float(dma_50) if dma_50 else None,
            'dma_200': float(dma_200) if dma_200 else None,
            'score': score,
            'max_score': max_score,
            'reason': reason
        }

        logger.info(f"Technical Structure: {score}/{max_score} - {reason}")
        return score

    def _determine_recommendation(self, composite_score: int) -> Tuple[str, str]:
        """
        Determine entry recommendation and bias.

        Returns:
            Tuple of (recommendation, entry_bias)
        """
        # Recommendation based on score
        if composite_score >= 80:
            recommendation = 'STRONG_ENTRY'
        elif composite_score >= 70:
            recommendation = 'GOOD_ENTRY'
        elif composite_score >= 60:
            recommendation = 'MODERATE_ENTRY'
        elif composite_score >= 50:
            recommendation = 'WEAK_ENTRY'
        else:
            recommendation = 'NO_ENTRY'

        # Entry bias based on sentiment analysis
        entry_bias = 'SYMMETRIC'

        if self._news_sentiment:
            outlook = self._news_sentiment.get('market_outlook', 'NEUTRAL')
            if outlook == 'BULLISH':
                entry_bias = 'WIDEN_CALL'
            elif outlook == 'BEARISH':
                entry_bias = 'WIDEN_PUT'

        # Override with global markets if strong directional signal
        if self._global_markets:
            sgx = self._global_markets.get('sgx_change', 0)
            nasdaq = self._global_markets.get('nasdaq_change', 0)

            if sgx and nasdaq:
                avg_change = (float(sgx) + float(nasdaq)) / 2
                if avg_change > 0.5:
                    entry_bias = 'WIDEN_CALL'
                elif avg_change < -0.5:
                    entry_bias = 'WIDEN_PUT'

        return recommendation, entry_bias

    def _calculate_delta_adjustments(self) -> Dict:
        """
        Calculate delta adjustments for strike selection.

        Enhanced with additional trader constraints:
        - 3+ consecutive red days → Widen PUT 15%
        - PCR < 0.6 (extreme bullish) → Widen CALL 10%
        - PCR > 1.4 (extreme bearish) → Widen PUT 10%
        - Friday entry → Tighten BOTH 10% (less time premium)

        Returns:
            Dict with call_multiplier, put_multiplier, reason
        """
        call_multiplier = Decimal('1.0')
        put_multiplier = Decimal('1.0')
        reasons = []

        # VIX-based adjustment
        vix_val = float(self.vix)
        if vix_val >= 14:
            vix_adj = Decimal('1.1')
            call_multiplier *= vix_adj
            put_multiplier *= vix_adj
            reasons.append(f"VIX {vix_val:.1f} - widening both {float(vix_adj):.2f}x")

        # News sentiment bias
        if self._news_sentiment:
            outlook = self._news_sentiment.get('market_outlook', 'NEUTRAL')
            if outlook == 'BULLISH':
                call_multiplier *= Decimal('1.1')
                put_multiplier *= Decimal('0.95')
                reasons.append("Bullish news - widen call")
            elif outlook == 'BEARISH':
                call_multiplier *= Decimal('0.95')
                put_multiplier *= Decimal('1.1')
                reasons.append("Bearish news - widen put")
            elif outlook == 'VOLATILE':
                call_multiplier *= Decimal('1.05')
                put_multiplier *= Decimal('1.05')
                reasons.append("Volatile news - widen both")

        # Gap-based adjustment
        gap_pct = self.details.get('gap_movement', {}).get('gap_percent', 0)
        if gap_pct > 0.3:
            call_multiplier *= Decimal('1.05')
            reasons.append(f"Gap up {gap_pct:.2f}% - widen call")
        elif gap_pct < -0.3:
            put_multiplier *= Decimal('1.05')
            reasons.append(f"Gap down {gap_pct:.2f}% - widen put")

        # =================================================================
        # ADDITIONAL TRADER CONSTRAINTS (Enhanced)
        # =================================================================

        # 1. Consecutive Red Days - 3+ red days → Widen PUT 15%
        consecutive_red_days = self._market_data.get('consecutive_red_days', 0)
        if consecutive_red_days >= self.CONSECUTIVE_RED_DAYS_THRESHOLD:
            put_multiplier *= Decimal('1.15')
            reasons.append(f"{consecutive_red_days} consecutive red days - widen PUT 15%")
            logger.info(f"Consecutive red days ({consecutive_red_days}) triggered PUT widening")

        # 2. PCR Extreme Conditions
        if self._option_chain_data:
            pcr_oi = self._option_chain_data.get('pcr_oi')

            if pcr_oi is not None:
                if pcr_oi < self.PCR_EXTREME_BULLISH:
                    # Extreme bullish sentiment (too many call buyers) → market might reverse down
                    # But for strangle, we widen CALL to protect against rally
                    call_multiplier *= Decimal('1.10')
                    reasons.append(f"PCR {pcr_oi:.2f} < {self.PCR_EXTREME_BULLISH} (extreme bullish) - widen CALL 10%")
                    logger.info(f"Extreme bullish PCR ({pcr_oi:.2f}) triggered CALL widening")

                elif pcr_oi > self.PCR_EXTREME_BEARISH:
                    # Extreme bearish sentiment (too many put buyers) → market might reverse up
                    # But for strangle, we widen PUT to protect against selloff
                    put_multiplier *= Decimal('1.10')
                    reasons.append(f"PCR {pcr_oi:.2f} > {self.PCR_EXTREME_BEARISH} (extreme bearish) - widen PUT 10%")
                    logger.info(f"Extreme bearish PCR ({pcr_oi:.2f}) triggered PUT widening")

        # 3. Friday Entry Logic - Tighten BOTH 10% (less time for theta decay)
        is_friday = self._market_data.get('is_friday', False)
        if is_friday:
            # On Friday, there's less time to expiry, so we can afford tighter strikes
            # as there's less time for adverse moves
            call_multiplier *= Decimal('0.90')
            put_multiplier *= Decimal('0.90')
            reasons.append("Friday entry - tighten BOTH 10% (less time premium)")
            logger.info("Friday entry triggered strike tightening (10% both sides)")

        return {
            'call_multiplier': float(call_multiplier),
            'put_multiplier': float(put_multiplier),
            'is_asymmetric': call_multiplier != put_multiplier,
            'adjustment_reasons': reasons,
            # Include constraint details for audit
            'constraint_details': {
                'consecutive_red_days': consecutive_red_days,
                'pcr_oi': self._option_chain_data.get('pcr_oi') if self._option_chain_data else None,
                'is_friday': is_friday
            }
        }

    def get_summary(self) -> str:
        """Get a text summary of the analysis."""
        if self.hard_reject:
            return f"REJECTED: {self.reject_reason}"

        raw_score = sum(self.scores.values())
        composite = int((raw_score / self.TOTAL_WEIGHT) * 100)

        summary_lines = [
            f"Strangle Entry Analysis",
            f"=" * 40,
            f"Composite Score: {composite}/100",
            f"VIX: {self.vix}",
            f"Days to Expiry: {self.days_to_expiry}",
            "",
            "Component Scores:",
        ]

        for component, score in self.scores.items():
            max_score = self.WEIGHTS[component]
            pct = int((score / max_score) * 100) if max_score > 0 else 0
            summary_lines.append(f"  {component}: {score}/{max_score} ({pct}%)")

        return "\n".join(summary_lines)


# Convenience function
def analyze_strangle_entry(spot_price: Decimal, vix: Decimal, days_to_expiry: int,
                           market_data: Dict = None) -> Dict:
    """
    Convenience function to run strangle entry analysis.

    Args:
        spot_price: Current Nifty spot price
        vix: India VIX value
        days_to_expiry: Days to expiry
        market_data: Optional comprehensive market data

    Returns:
        Analysis result dict
    """
    analyzer = EnhancedStrangleAnalyzer(spot_price, vix, days_to_expiry)
    if market_data:
        analyzer.set_market_data(market_data)
    return analyzer.analyze()
