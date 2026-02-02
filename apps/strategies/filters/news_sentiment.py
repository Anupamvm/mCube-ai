"""
Market News Sentiment Filter for Strangle Strategy

Checks market news sentiment before entry:
- Fetches recent market news (last 4 hours)
- Analyzes with LLM for market impact
- Blocks on highly negative sentiment (avg < -0.4)
- Warns on moderately negative sentiment (avg < -0.2)

Thresholds:
- BLOCK_THRESHOLD (-0.4): Highly negative news blocks the trade
- WARN_THRESHOLD (-0.2): Negative news shows warning
- BLOCKING_ARTICLE_THRESHOLD (-0.6): Single article blocks trade
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


# Thresholds
BLOCK_THRESHOLD = -0.4      # Average sentiment to block entry
WARN_THRESHOLD = -0.2       # Average sentiment to warn
BLOCKING_ARTICLE_THRESHOLD = -0.6  # Single article blocking threshold


def check_market_news_sentiment(
    max_hours_old: int = 4,
    block_threshold: float = BLOCK_THRESHOLD,
    warn_threshold: float = WARN_THRESHOLD
) -> Dict:
    """
    Check market news sentiment for strangle entry.

    Logic:
    1. Fetch recent market news (last 4 hours) from NewsArticle DB
    2. If no recent news, fetch fresh via GNewsClient
    3. Run analyze_market_news() to get overall sentiment
    4. BLOCK if:
       - average_impact_score < -0.4 (bearish sentiment)
       - OR any blocking_articles (score < -0.6)
    5. WARN if average_impact_score < -0.2
    6. PASS otherwise

    Args:
        max_hours_old: Maximum age of news to consider (default: 4 hours)
        block_threshold: Average sentiment threshold to block (default: -0.4)
        warn_threshold: Average sentiment threshold to warn (default: -0.2)

    Returns:
        dict: {
            'passed': bool,
            'message': str,
            'details': {
                'articles_analyzed': int,
                'average_sentiment': float,
                'market_outlook': str,  # BULLISH/NEUTRAL/BEARISH/VOLATILE
                'blocking_articles': list,
                'top_negative_news': list,
                'top_positive_news': list,
                'confidence': float
            }
        }
    """
    logger.info(f"[NewsFilter] Checking market news sentiment (last {max_hours_old}h)...")

    try:
        # Import analyzer service
        from apps.strategies.services.strangle_news_analyzer import get_strangle_news_analyzer

        analyzer = get_strangle_news_analyzer()
        sentiment = analyzer.get_market_sentiment(hours_back=max_hours_old)

        # Extract metrics
        articles_analyzed = sentiment.get('articles_analyzed', 0)
        avg_sentiment = sentiment.get('average_sentiment', 0.0)
        market_outlook = sentiment.get('market_outlook', 'NEUTRAL')
        blocking_articles = sentiment.get('blocking_articles', [])
        confidence = sentiment.get('confidence', 0.0)

        # Build details
        details = {
            'articles_analyzed': articles_analyzed,
            'average_sentiment': avg_sentiment,
            'market_outlook': market_outlook,
            'blocking_articles': [
                {
                    'title': a.get('title', '')[:80],
                    'score': a.get('impact_score', 0)
                }
                for a in blocking_articles
            ],
            'top_negative_news': sentiment.get('top_negative_news', []),
            'top_positive_news': sentiment.get('top_positive_news', []),
            'confidence': confidence,
            'bearish_count': sentiment.get('bearish_count', 0),
            'bullish_count': sentiment.get('bullish_count', 0),
            'neutral_count': sentiment.get('neutral_count', 0),
        }

        # Decision logic
        # Case 1: No articles analyzed - pass with warning (fail-open)
        if articles_analyzed == 0:
            logger.warning("[NewsFilter] No news articles analyzed - passing with low confidence")
            return {
                'passed': True,
                'message': f"No market news available (fail-open policy)",
                'details': details
            }

        # Case 2: Blocking articles found - BLOCK
        if len(blocking_articles) > 0:
            blocking_titles = [a.get('title', '')[:50] for a in blocking_articles[:2]]
            logger.warning(
                f"[NewsFilter] BLOCKED: {len(blocking_articles)} highly negative articles found"
            )
            return {
                'passed': False,
                'message': (
                    f"Highly negative news detected: {len(blocking_articles)} blocking articles "
                    f"({blocking_titles[0]}...)"
                ),
                'details': details
            }

        # Case 3: Average sentiment below block threshold - BLOCK
        if avg_sentiment < block_threshold:
            logger.warning(
                f"[NewsFilter] BLOCKED: Average sentiment {avg_sentiment:.2f} < {block_threshold}"
            )
            return {
                'passed': False,
                'message': (
                    f"Bearish market sentiment ({avg_sentiment:.2f}), "
                    f"outlook: {market_outlook}"
                ),
                'details': details
            }

        # Case 4: Average sentiment below warn threshold - PASS with warning
        if avg_sentiment < warn_threshold:
            logger.info(
                f"[NewsFilter] PASSED with warning: Sentiment {avg_sentiment:.2f} "
                f"(outlook: {market_outlook})"
            )
            return {
                'passed': True,
                'message': (
                    f"Moderately negative sentiment ({avg_sentiment:.2f}), "
                    f"outlook: {market_outlook} - proceed with caution"
                ),
                'details': details
            }

        # Case 5: Neutral or positive sentiment - PASS
        sentiment_desc = "positive" if avg_sentiment > 0.2 else "neutral"
        logger.info(
            f"[NewsFilter] PASSED: {sentiment_desc.capitalize()} sentiment {avg_sentiment:.2f}, "
            f"outlook: {market_outlook}"
        )
        return {
            'passed': True,
            'message': (
                f"{sentiment_desc.capitalize()} market sentiment ({avg_sentiment:.2f}), "
                f"outlook: {market_outlook}"
            ),
            'details': details
        }

    except Exception as e:
        # Fail-open: If news analysis fails, allow trade with warning
        logger.error(f"[NewsFilter] Error in news sentiment check: {e}", exc_info=True)
        return {
            'passed': True,
            'message': f"News analysis unavailable ({str(e)[:50]}) - fail-open policy",
            'details': {
                'articles_analyzed': 0,
                'average_sentiment': 0.0,
                'market_outlook': 'UNKNOWN',
                'blocking_articles': [],
                'top_negative_news': [],
                'top_positive_news': [],
                'confidence': 0.0,
                'error': str(e)
            }
        }


def get_news_summary_for_telegram(sentiment: Dict) -> str:
    """
    Format news sentiment for Telegram notification.

    Args:
        sentiment: Sentiment dict from get_market_sentiment()

    Returns:
        Formatted string for Telegram
    """
    outlook = sentiment.get('market_outlook', 'UNKNOWN')
    avg_score = sentiment.get('average_sentiment', 0.0)
    articles = sentiment.get('articles_analyzed', 0)
    bearish = sentiment.get('bearish_count', 0)
    bullish = sentiment.get('bullish_count', 0)

    # Outlook emoji
    outlook_emoji = {
        'BULLISH': '+',
        'BEARISH': '-',
        'VOLATILE': '~',
        'NEUTRAL': '=',
        'UNKNOWN': '?'
    }.get(outlook, '?')

    summary = f"News: {outlook_emoji}{outlook} ({avg_score:+.2f})\n"
    summary += f"  Articles: {articles} ({bullish}+ / {bearish}-)"

    # Top news
    top_neg = sentiment.get('top_negative_news', [])
    if top_neg:
        summary += f"\n  Top negative: {top_neg[0].get('title', '')[:40]}..."

    return summary
