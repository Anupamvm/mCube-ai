"""
News Analysis Service for Strangle Strategy

Bridges NewsImpactAnalyzer with strangle algorithm.
Provides market sentiment analysis for:
1. Entry filtering (block on highly negative news)
2. Delta adjustment (asymmetric strikes based on sentiment)
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from django.utils import timezone

logger = logging.getLogger(__name__)


class StrangleNewsAnalyzer:
    """
    News analysis service for Nifty Strangle strategy.

    Provides:
    - Market sentiment analysis for entry decisions
    - Delta adjustment factors for asymmetric strikes
    - Blocking news detection
    """

    # Thresholds
    BLOCK_THRESHOLD = -0.4  # Block entry if avg sentiment below this
    WARN_THRESHOLD = -0.2   # Warn if avg sentiment below this
    BLOCKING_ARTICLE_THRESHOLD = -0.6  # Individual article blocking threshold

    def __init__(self):
        """Initialize with NewsImpactAnalyzer"""
        self._analyzer = None
        self._gnews_client = None

    @property
    def analyzer(self):
        """Lazy load NewsImpactAnalyzer"""
        if self._analyzer is None:
            try:
                from apps.llm.services.news_impact_analyzer import get_news_impact_analyzer
                self._analyzer = get_news_impact_analyzer()
            except Exception as e:
                logger.error(f"Failed to load NewsImpactAnalyzer: {e}")
                self._analyzer = None
        return self._analyzer

    @property
    def gnews_client(self):
        """Lazy load GNewsClient"""
        if self._gnews_client is None:
            try:
                from apps.data.services.gnews_client import get_gnews_client
                self._gnews_client = get_gnews_client()
            except Exception as e:
                logger.error(f"Failed to load GNewsClient: {e}")
                self._gnews_client = None
        return self._gnews_client

    def get_recent_news_from_db(self, hours_back: int = 4) -> List[Dict]:
        """
        Fetch recent market news from NewsArticle database.

        Args:
            hours_back: Number of hours to look back for news

        Returns:
            List of article dicts
        """
        try:
            from apps.data.models import NewsArticle

            cutoff_time = timezone.now() - timedelta(hours=hours_back)

            # Fetch market news with existing impact analysis
            articles = NewsArticle.objects.filter(
                news_type='MARKET',
                published_at__gte=cutoff_time
            ).order_by('-published_at')[:50]

            article_list = []
            for article in articles:
                article_dict = {
                    'title': article.title,
                    'description': article.summary,
                    'content': article.content,
                    'url': article.url,
                    'publishedAt': article.published_at.isoformat(),
                    'source': {'name': article.source},
                    # Include existing analysis if available
                    'impact_score': article.sentiment_score,
                    'impact_label': article.sentiment_label,
                    'impact_category': article.impact_category,
                    'market_direction': article.market_direction,
                    'impact_reasoning': article.impact_reasoning,
                    'relevance': article.relevance_score,
                }
                article_list.append(article_dict)

            logger.info(f"[StrangleNews] Found {len(article_list)} recent market articles in DB")
            return article_list

        except Exception as e:
            logger.error(f"[StrangleNews] Error fetching from DB: {e}")
            return []

    def fetch_fresh_news(self, max_articles: int = 30) -> List[Dict]:
        """
        Fetch fresh market news via GNewsClient.

        Args:
            max_articles: Maximum number of articles to fetch

        Returns:
            List of article dicts
        """
        if not self.gnews_client:
            logger.warning("[StrangleNews] GNewsClient not available")
            return []

        try:
            result = self.gnews_client.fetch_market_news(
                max_results_per_keyword=5,
                use_cache=True
            )

            if result.get('success'):
                articles = result.get('articles', [])[:max_articles]
                logger.info(f"[StrangleNews] Fetched {len(articles)} fresh market articles")
                return articles
            else:
                logger.warning(f"[StrangleNews] GNews fetch failed: {result.get('error')}")
                return []

        except Exception as e:
            logger.error(f"[StrangleNews] Error fetching fresh news: {e}")
            return []

    def analyze_articles(self, articles: List[Dict]) -> Dict:
        """
        Analyze articles using NewsImpactAnalyzer.

        Args:
            articles: List of article dicts

        Returns:
            Dict with analysis results
        """
        if not self.analyzer:
            logger.warning("[StrangleNews] NewsImpactAnalyzer not available")
            return self._default_analysis("NewsImpactAnalyzer not available")

        if not articles:
            return self._default_analysis("No articles to analyze")

        try:
            # Check if articles already have impact analysis
            analyzed_articles = []
            articles_needing_analysis = []

            for article in articles:
                if article.get('impact_score') is not None:
                    analyzed_articles.append(article)
                else:
                    articles_needing_analysis.append(article)

            # Analyze articles that need it
            if articles_needing_analysis:
                logger.info(f"[StrangleNews] Analyzing {len(articles_needing_analysis)} articles with LLM")
                result = self.analyzer.analyze_market_news(
                    articles=articles_needing_analysis,
                    top_n=20
                )
                analyzed_articles.extend(result.get('articles', []))

            # Calculate overall metrics
            if not analyzed_articles:
                return self._default_analysis("No articles analyzed")

            # Filter by relevance
            relevant_articles = [
                a for a in analyzed_articles
                if a.get('relevance', 0.5) >= 0.2
            ]

            if not relevant_articles:
                return self._default_analysis("No relevant articles found")

            # Calculate average sentiment
            total_score = sum(a.get('impact_score', 0) for a in relevant_articles)
            avg_score = total_score / len(relevant_articles)

            # Count by direction
            bearish_count = len([a for a in relevant_articles if a.get('market_direction') == 'BEARISH'])
            bullish_count = len([a for a in relevant_articles if a.get('market_direction') == 'BULLISH'])
            neutral_count = len(relevant_articles) - bearish_count - bullish_count

            # Identify blocking articles
            blocking_articles = [
                a for a in relevant_articles
                if a.get('impact_score', 0) <= self.BLOCKING_ARTICLE_THRESHOLD
            ]

            # Determine market outlook
            if avg_score <= -0.3:
                outlook = 'BEARISH'
            elif avg_score >= 0.3:
                outlook = 'BULLISH'
            elif bearish_count > bullish_count * 1.5:
                outlook = 'VOLATILE'  # More bearish news but not extremely negative
            else:
                outlook = 'NEUTRAL'

            # Get top negative and positive news
            sorted_articles = sorted(relevant_articles, key=lambda x: x.get('impact_score', 0))
            top_negative = sorted_articles[:3]
            top_positive = sorted_articles[-3:][::-1]

            return {
                'articles_analyzed': len(relevant_articles),
                'average_sentiment': round(avg_score, 3),
                'market_outlook': outlook,
                'blocking_articles': blocking_articles,
                'bearish_count': bearish_count,
                'bullish_count': bullish_count,
                'neutral_count': neutral_count,
                'top_negative_news': [
                    {'title': a.get('title', '')[:80], 'score': a.get('impact_score', 0)}
                    for a in top_negative if a.get('impact_score', 0) < 0
                ],
                'top_positive_news': [
                    {'title': a.get('title', '')[:80], 'score': a.get('impact_score', 0)}
                    for a in top_positive if a.get('impact_score', 0) > 0
                ],
                'confidence': min(1.0, len(relevant_articles) / 10),  # Higher confidence with more articles
                'analyzed_at': timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"[StrangleNews] Analysis error: {e}", exc_info=True)
            return self._default_analysis(f"Analysis error: {str(e)}")

    def _default_analysis(self, reason: str) -> Dict:
        """Return default neutral analysis"""
        return {
            'articles_analyzed': 0,
            'average_sentiment': 0.0,
            'market_outlook': 'NEUTRAL',
            'blocking_articles': [],
            'bearish_count': 0,
            'bullish_count': 0,
            'neutral_count': 0,
            'top_negative_news': [],
            'top_positive_news': [],
            'confidence': 0.0,
            'reason': reason,
            'analyzed_at': timezone.now().isoformat(),
        }

    def get_market_sentiment(self, hours_back: int = 4) -> Dict:
        """
        Get overall market sentiment for strangle entry decision.

        Args:
            hours_back: Hours to look back for news

        Returns:
            Dict with sentiment analysis including:
            - articles_analyzed: int
            - average_sentiment: float (-1.0 to 1.0)
            - market_outlook: str (BULLISH/BEARISH/NEUTRAL/VOLATILE)
            - blocking_articles: list
            - confidence: float (0.0 to 1.0)
        """
        logger.info(f"[StrangleNews] Getting market sentiment (last {hours_back}h)")

        # First try to get recent news from DB
        articles = self.get_recent_news_from_db(hours_back=hours_back)

        # If insufficient articles, fetch fresh
        if len(articles) < 5:
            logger.info("[StrangleNews] Insufficient DB articles, fetching fresh news")
            fresh_articles = self.fetch_fresh_news(max_articles=30)
            articles.extend(fresh_articles)

            # Deduplicate by URL
            seen_urls = set()
            unique_articles = []
            for article in articles:
                url = article.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_articles.append(article)
            articles = unique_articles

        # Analyze
        analysis = self.analyze_articles(articles)

        logger.info(
            f"[StrangleNews] Sentiment: {analysis['average_sentiment']:.2f}, "
            f"Outlook: {analysis['market_outlook']}, "
            f"Articles: {analysis['articles_analyzed']}"
        )

        return analysis

    def check_blocking_news(self) -> Tuple[bool, List[Dict]]:
        """
        Check if there's any news that should block trade entry.

        Returns:
            Tuple of (has_blocking_news, blocking_articles)
        """
        sentiment = self.get_market_sentiment(hours_back=4)

        blocking_articles = sentiment.get('blocking_articles', [])
        has_blocking = len(blocking_articles) > 0

        if has_blocking:
            logger.warning(
                f"[StrangleNews] BLOCKING NEWS FOUND: {len(blocking_articles)} "
                f"articles with score <= {self.BLOCKING_ARTICLE_THRESHOLD}"
            )

        return has_blocking, blocking_articles

    def get_delta_adjustment(self, sentiment: Optional[Dict] = None) -> Dict:
        """
        Get delta adjustment factors based on news sentiment.

        Args:
            sentiment: Pre-computed sentiment dict (optional, will fetch if not provided)

        Returns:
            Dict with:
            - news_multiplier: Decimal - overall delta multiplier
            - call_bias: Decimal - multiplier for call strike distance
            - put_bias: Decimal - multiplier for put strike distance
            - reason: str - explanation
        """
        if sentiment is None:
            sentiment = self.get_market_sentiment(hours_back=4)

        outlook = sentiment.get('market_outlook', 'NEUTRAL')
        avg_score = sentiment.get('average_sentiment', 0.0)
        confidence = sentiment.get('confidence', 0.0)

        # Base adjustments by outlook
        adjustments = {
            'BULLISH': {
                'news_multiplier': Decimal('1.1'),
                'call_bias': Decimal('1.15'),  # Widen call more
                'put_bias': Decimal('0.95'),   # Keep put tighter
                'reason': 'Bullish market news - widening call side'
            },
            'BEARISH': {
                'news_multiplier': Decimal('1.1'),
                'call_bias': Decimal('0.95'),  # Keep call tighter
                'put_bias': Decimal('1.15'),   # Widen put more
                'reason': 'Bearish market news - widening put side'
            },
            'VOLATILE': {
                'news_multiplier': Decimal('1.15'),
                'call_bias': Decimal('1.1'),   # Widen both
                'put_bias': Decimal('1.1'),
                'reason': 'Mixed/volatile news - widening both sides'
            },
            'NEUTRAL': {
                'news_multiplier': Decimal('1.0'),
                'call_bias': Decimal('1.0'),
                'put_bias': Decimal('1.0'),
                'reason': 'Neutral news sentiment - no adjustment'
            }
        }

        result = adjustments.get(outlook, adjustments['NEUTRAL']).copy()

        # Scale adjustment by confidence
        # Lower confidence = smaller adjustment
        if confidence < 0.5:
            scale = Decimal(str(0.5 + confidence))  # 0.5 to 1.0

            # Move values toward 1.0 based on confidence
            result['news_multiplier'] = Decimal('1.0') + (result['news_multiplier'] - Decimal('1.0')) * scale
            result['call_bias'] = Decimal('1.0') + (result['call_bias'] - Decimal('1.0')) * scale
            result['put_bias'] = Decimal('1.0') + (result['put_bias'] - Decimal('1.0')) * scale

            result['reason'] += f' (scaled by {float(scale):.0%} confidence)'

        # Add sentiment data
        result['sentiment'] = {
            'outlook': outlook,
            'average_score': avg_score,
            'confidence': confidence,
            'articles_analyzed': sentiment.get('articles_analyzed', 0)
        }

        logger.info(
            f"[StrangleNews] Delta adjustment: "
            f"multiplier={float(result['news_multiplier']):.2f}, "
            f"call_bias={float(result['call_bias']):.2f}, "
            f"put_bias={float(result['put_bias']):.2f}"
        )

        return result


# Global instance
_strangle_news_analyzer = None


def get_strangle_news_analyzer() -> StrangleNewsAnalyzer:
    """Get or create global StrangleNewsAnalyzer instance"""
    global _strangle_news_analyzer

    if _strangle_news_analyzer is None:
        _strangle_news_analyzer = StrangleNewsAnalyzer()

    return _strangle_news_analyzer


def get_market_sentiment_for_strangle(hours_back: int = 4) -> Dict:
    """
    Convenience function to get market sentiment for strangle entry.

    Args:
        hours_back: Hours to look back for news

    Returns:
        Dict with sentiment analysis
    """
    analyzer = get_strangle_news_analyzer()
    return analyzer.get_market_sentiment(hours_back=hours_back)


def check_blocking_news() -> Tuple[bool, List[Dict]]:
    """
    Convenience function to check for blocking news.

    Returns:
        Tuple of (has_blocking_news, blocking_articles)
    """
    analyzer = get_strangle_news_analyzer()
    return analyzer.check_blocking_news()


def get_news_delta_adjustment(sentiment: Optional[Dict] = None) -> Dict:
    """
    Convenience function to get delta adjustment factors.

    Args:
        sentiment: Optional pre-computed sentiment dict

    Returns:
        Dict with adjustment factors
    """
    analyzer = get_strangle_news_analyzer()
    return analyzer.get_delta_adjustment(sentiment=sentiment)
