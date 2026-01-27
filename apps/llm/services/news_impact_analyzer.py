"""
News Impact Analyzer Service

Analyzes news articles for trading impact using LLM.
- Scores each article from -1.0 (highly negative) to 1.0 (highly positive)
- Determines if news should block a trade (hard block for highly negative)
- Sorts articles by impact for UI display

Thresholds:
- BLOCK_THRESHOLD (-0.6): Highly negative news blocks the trade
- WARNING_THRESHOLD (-0.3): Negative news shows warning
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class NewsImpactAnalyzer:
    """
    Analyzes news articles for trading impact using LLM.

    Impact Labels:
        HIGHLY_NEGATIVE: score <= -0.6 (blocks trade)
        NEGATIVE: -0.6 < score <= -0.3 (warning)
        NEUTRAL: -0.3 < score < 0.3
        POSITIVE: 0.3 <= score < 0.6
        HIGHLY_POSITIVE: score >= 0.6
    """

    # Thresholds for trade decisions
    BLOCK_THRESHOLD = -0.6   # Highly negative - blocks trade (no override)
    WARNING_THRESHOLD = -0.3  # Negative - shows warning

    def __init__(self):
        """Initialize with vLLM client"""
        from apps.llm.services.vllm_client import get_vllm_client
        self.llm_client = get_vllm_client()

    def _get_impact_label(self, score: float) -> str:
        """Convert impact score to label"""
        if score <= self.BLOCK_THRESHOLD:
            return "HIGHLY_NEGATIVE"
        elif score <= self.WARNING_THRESHOLD:
            return "NEGATIVE"
        elif score < 0.3:
            return "NEUTRAL"
        elif score < 0.6:
            return "POSITIVE"
        else:
            return "HIGHLY_POSITIVE"

    def _get_trade_recommendation(self, score: float) -> str:
        """Get trade recommendation based on score"""
        if score <= self.BLOCK_THRESHOLD:
            return "BLOCK"
        elif score <= self.WARNING_THRESHOLD:
            return "WARN"
        else:
            return "PROCEED"

    def analyze_article_impact(
        self,
        article: Dict,
        stock_symbol: str,
        stock_name: str,
        trade_direction: str,
        industry_name: Optional[str] = None
    ) -> Dict:
        """
        Analyze a single article's impact on a potential trade.

        Args:
            article: Article dict with 'title', 'description', 'content'
            stock_symbol: Stock symbol (e.g., 'RELIANCE')
            stock_name: Full stock name
            trade_direction: 'LONG' or 'SHORT'
            industry_name: Optional industry/sector name

        Returns:
            Dict with:
                - impact_score: float (-1.0 to 1.0)
                - impact_label: str (HIGHLY_NEGATIVE to HIGHLY_POSITIVE)
                - blocks_trade: bool
                - reasoning: str
                - confidence: float (0.0 to 1.0)
                - trade_recommendation: str (BLOCK/WARN/PROCEED)
        """
        if not self.llm_client.is_enabled():
            logger.warning("LLM not available for news impact analysis")
            return {
                'impact_score': 0.0,
                'impact_label': 'NEUTRAL',
                'blocks_trade': False,
                'reasoning': 'LLM not available - defaulting to neutral',
                'confidence': 0.0,
                'trade_recommendation': 'PROCEED'
            }

        title = article.get('title', '')
        description = article.get('description', '')
        content = article.get('content', description)  # Use description if no content

        # Truncate content to avoid token limits (~1500 chars)
        if len(content) > 1500:
            content = content[:1500] + "..."

        # Build the prompt
        direction_context = "bullish" if trade_direction == "LONG" else "bearish"
        industry_context = f" in the {industry_name} sector" if industry_name else ""

        prompt = f"""You are a financial news analyst evaluating news impact on a potential {trade_direction} trade.

Stock: {stock_symbol} ({stock_name}){industry_context}
Trade Direction: {trade_direction} (looking for {direction_context} signals)

NEWS ARTICLE:
Title: {title}
Content: {content}

ANALYSIS TASK:
For a {trade_direction} trade:
- Negative news = bearish impact (bad for LONG, good for SHORT)
- Positive news = bullish impact (good for LONG, bad for SHORT)

Consider:
1. Direct impact on the company (earnings, management, operations)
2. Regulatory or legal issues
3. Market/industry headwinds
4. Competitive threats
5. Macroeconomic factors

Return ONLY a valid JSON object (no markdown, no explanation):
{{"impact_score": <-1.0 to 1.0>, "impact_label": "<HIGHLY_NEGATIVE|NEGATIVE|NEUTRAL|POSITIVE|HIGHLY_POSITIVE>", "reasoning": "<one sentence explaining the impact>", "confidence": <0.0 to 1.0>}}"""

        system_prompt = "You are a financial news analyst. Respond ONLY with valid JSON, no markdown formatting."

        try:
            success, response, metadata = self.llm_client.generate(
                prompt=prompt,
                system=system_prompt,
                temperature=0.2,
                max_tokens=200
            )

            if not success:
                logger.error(f"LLM analysis failed for article: {title[:50]}")
                return self._default_result("LLM analysis failed")

            # Parse JSON response
            result = self._parse_llm_response(response)

            # Add computed fields
            result['blocks_trade'] = result['impact_score'] <= self.BLOCK_THRESHOLD
            result['trade_recommendation'] = self._get_trade_recommendation(result['impact_score'])

            # Validate and normalize label
            if result['impact_label'] not in ['HIGHLY_NEGATIVE', 'NEGATIVE', 'NEUTRAL', 'POSITIVE', 'HIGHLY_POSITIVE']:
                result['impact_label'] = self._get_impact_label(result['impact_score'])

            logger.info(f"Article impact: {result['impact_label']} ({result['impact_score']:.2f}) - {title[:50]}")
            return result

        except Exception as e:
            logger.error(f"Error analyzing article impact: {e}", exc_info=True)
            return self._default_result(f"Analysis error: {str(e)}")

    def _parse_llm_response(self, response: str) -> Dict:
        """Parse LLM JSON response with fallback handling"""
        try:
            # Clean up response
            response = response.strip()

            # Remove markdown code blocks if present
            if response.startswith("```json"):
                response = response[7:]
            elif response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            # Parse JSON
            data = json.loads(response)

            # Validate and normalize
            impact_score = float(data.get('impact_score', 0.0))
            impact_score = max(-1.0, min(1.0, impact_score))  # Clamp to [-1, 1]

            return {
                'impact_score': impact_score,
                'impact_label': data.get('impact_label', self._get_impact_label(impact_score)),
                'reasoning': data.get('reasoning', 'No reasoning provided'),
                'confidence': float(data.get('confidence', 0.5))
            }

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {response[:200]}, error: {e}")
            return self._default_result("Failed to parse LLM response")

    def _default_result(self, reason: str) -> Dict:
        """Return default neutral result"""
        return {
            'impact_score': 0.0,
            'impact_label': 'NEUTRAL',
            'blocks_trade': False,
            'reasoning': reason,
            'confidence': 0.0,
            'trade_recommendation': 'PROCEED'
        }

    def analyze_news_for_trade(
        self,
        stock_news: Dict,
        industry_news: Dict,
        competitor_news: Dict,
        stock_symbol: str,
        stock_name: str,
        trade_direction: str,
        industry_name: Optional[str] = None,
        max_articles_per_category: int = 5
    ) -> Dict:
        """
        Analyze all news categories for a trade.

        Args:
            stock_news: Dict with 'articles' list
            industry_news: Dict with 'articles' list
            competitor_news: Dict with 'articles' list
            stock_symbol: Stock symbol
            stock_name: Full stock name
            trade_direction: 'LONG' or 'SHORT'
            industry_name: Industry/sector name
            max_articles_per_category: Max articles to analyze per category

        Returns:
            Dict with:
                - trade_allowed: bool (False if blocked by highly negative news)
                - blocking_articles: List of articles that block the trade
                - warning_articles: List of articles with warnings
                - stock_news: Dict with articles sorted by impact
                - industry_news: Dict with articles sorted by impact
                - competitor_news: Dict with articles sorted by impact
                - summary: Overall analysis summary
        """
        blocking_articles = []
        warning_articles = []
        all_analyzed = []

        # Process each category
        categories = [
            ('stock', stock_news),
            ('industry', industry_news),
            ('competitor', competitor_news)
        ]

        analyzed_news = {
            'stock_news': {'articles': [], 'totalArticles': 0},
            'industry_news': {'articles': [], 'totalArticles': 0},
            'competitor_news': {'articles': [], 'totalArticles': 0}
        }

        for category_name, news_data in categories:
            articles = news_data.get('articles', [])[:max_articles_per_category]
            analyzed_articles = []

            for article in articles:
                # Analyze impact
                impact = self.analyze_article_impact(
                    article=article,
                    stock_symbol=stock_symbol,
                    stock_name=stock_name,
                    trade_direction=trade_direction,
                    industry_name=industry_name
                )

                # Add impact data to article
                enriched_article = {
                    **article,
                    'impact_score': impact['impact_score'],
                    'impact_label': impact['impact_label'],
                    'impact_reasoning': impact['reasoning'],
                    'impact_confidence': impact['confidence'],
                    'blocks_trade': impact['blocks_trade'],
                    'trade_recommendation': impact['trade_recommendation'],
                    'news_category': category_name
                }

                analyzed_articles.append(enriched_article)
                all_analyzed.append(enriched_article)

                # Track blocking and warning articles
                if impact['blocks_trade']:
                    blocking_articles.append(enriched_article)
                elif impact['trade_recommendation'] == 'WARN':
                    warning_articles.append(enriched_article)

            # Sort articles by absolute impact score (most impactful first)
            analyzed_articles.sort(key=lambda x: abs(x['impact_score']), reverse=True)

            # Store in result
            key = f"{category_name}_news"
            analyzed_news[key] = {
                'articles': analyzed_articles,
                'totalArticles': news_data.get('totalArticles', len(analyzed_articles)),
                **{k: v for k, v in news_data.items() if k not in ['articles', 'totalArticles']}
            }

        # Determine if trade is allowed
        trade_allowed = len(blocking_articles) == 0

        # Build summary
        total_analyzed = len(all_analyzed)
        negative_count = len([a for a in all_analyzed if a['impact_score'] < -0.3])
        positive_count = len([a for a in all_analyzed if a['impact_score'] > 0.3])
        neutral_count = total_analyzed - negative_count - positive_count

        # Calculate overall sentiment
        if total_analyzed > 0:
            avg_score = sum(a['impact_score'] for a in all_analyzed) / total_analyzed
        else:
            avg_score = 0.0

        summary = {
            'total_analyzed': total_analyzed,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'positive_count': positive_count,
            'blocking_count': len(blocking_articles),
            'warning_count': len(warning_articles),
            'average_impact_score': round(avg_score, 3),
            'overall_sentiment': self._get_impact_label(avg_score)
        }

        result = {
            'trade_allowed': trade_allowed,
            'blocking_articles': blocking_articles,
            'warning_articles': warning_articles,
            'summary': summary,
            **analyzed_news
        }

        if not trade_allowed:
            logger.warning(f"Trade BLOCKED for {stock_symbol}: {len(blocking_articles)} highly negative articles found")
        elif warning_articles:
            logger.info(f"Trade WARNED for {stock_symbol}: {len(warning_articles)} negative articles found")
        else:
            logger.info(f"Trade ALLOWED for {stock_symbol}: No blocking news, avg score: {avg_score:.2f}")

        return result


# Global instance
_news_impact_analyzer = None


def get_news_impact_analyzer() -> NewsImpactAnalyzer:
    """Get or create global NewsImpactAnalyzer instance"""
    global _news_impact_analyzer

    if _news_impact_analyzer is None:
        _news_impact_analyzer = NewsImpactAnalyzer()

    return _news_impact_analyzer


def analyze_article_impact(
    article: Dict,
    stock_symbol: str,
    stock_name: str,
    trade_direction: str,
    industry_name: Optional[str] = None
) -> Dict:
    """
    Convenience function to analyze a single article's impact.

    Args:
        article: Article dict with 'title', 'description', 'content'
        stock_symbol: Stock symbol
        stock_name: Full stock name
        trade_direction: 'LONG' or 'SHORT'
        industry_name: Optional industry name

    Returns:
        Dict with impact_score, impact_label, blocks_trade, reasoning, etc.
    """
    analyzer = get_news_impact_analyzer()
    return analyzer.analyze_article_impact(
        article=article,
        stock_symbol=stock_symbol,
        stock_name=stock_name,
        trade_direction=trade_direction,
        industry_name=industry_name
    )


def analyze_news_for_trade(
    stock_news: Dict,
    industry_news: Dict,
    competitor_news: Dict,
    stock_symbol: str,
    stock_name: str,
    trade_direction: str,
    industry_name: Optional[str] = None
) -> Dict:
    """
    Convenience function to analyze all news for a trade.

    Returns:
        Dict with trade_allowed, blocking_articles, warning_articles,
        and enriched news data sorted by impact.
    """
    analyzer = get_news_impact_analyzer()
    return analyzer.analyze_news_for_trade(
        stock_news=stock_news,
        industry_news=industry_news,
        competitor_news=competitor_news,
        stock_symbol=stock_symbol,
        stock_name=stock_name,
        trade_direction=trade_direction,
        industry_name=industry_name
    )
