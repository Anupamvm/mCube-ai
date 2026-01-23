"""
GNews API Client Service

This service provides integration with GNews.io API for fetching news articles
related to stocks, industries, and competitors.

Features:
- Fetch news for specific stocks/companies
- Fetch news for industries/sectors
- Handle API credentials from CredentialStore
- Rate limiting and error handling
- Cache news articles to reduce API calls
"""

import logging
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from django.core.cache import cache
from apps.core.models import CredentialStore

logger = logging.getLogger(__name__)


class GNewsClient:
    """
    Client for interacting with GNews.io API

    Usage:
        client = GNewsClient()
        news = client.fetch_news("RELIANCE", max_results=3)
    """

    BASE_URL = "https://gnews.io/api/v4"
    CACHE_TTL = 3600  # 1 hour cache

    def __init__(self):
        """Initialize GNews client with API credentials"""
        self.api_key = self._get_api_key()

    def _get_api_key(self) -> Optional[str]:
        """
        Retrieve GNews API key from CredentialStore

        Returns:
            API key string or None if not found
        """
        try:
            credential = CredentialStore.objects.filter(service='gnewsio').first()
            if credential and credential.api_key:
                return credential.api_key
            else:
                logger.error("GNews.io credentials not found in CredentialStore")
                return None
        except Exception as e:
            logger.error(f"Error fetching GNews credentials: {e}")
            return None

    def _build_cache_key(self, query: str, max_results: int) -> str:
        """Build cache key for news query"""
        return f"gnews:{query}:{max_results}"

    def fetch_news(
        self,
        query: str,
        max_results: int = 3,
        lang: str = "en",
        country: str = "in",
        use_cache: bool = True
    ) -> Dict:
        """
        Fetch news articles from GNews API

        Args:
            query: Search query (e.g., "RELIANCE" or "Oil and Gas India")
            max_results: Maximum number of articles to fetch (default: 3)
            lang: Language code (default: "en")
            country: Country code (default: "in" for India)
            use_cache: Whether to use cached results (default: True)

        Returns:
            Dict with structure:
            {
                'success': bool,
                'articles': [
                    {
                        'title': str,
                        'description': str,
                        'content': str,
                        'url': str,
                        'image': str,
                        'publishedAt': str,
                        'source': {'name': str, 'url': str}
                    },
                    ...
                ],
                'totalArticles': int,
                'error': str (only if success=False)
            }

        Example:
            >>> client = GNewsClient()
            >>> result = client.fetch_news("RELIANCE", max_results=3)
            >>> if result['success']:
            ...     for article in result['articles']:
            ...         print(article['title'])
        """
        if not self.api_key:
            return {
                'success': False,
                'error': 'GNews API key not configured',
                'articles': [],
                'totalArticles': 0
            }

        # Check cache first
        cache_key = self._build_cache_key(query, max_results)
        if use_cache:
            cached_result = cache.get(cache_key)
            if cached_result:
                logger.info(f"[GNews] Cache hit for query: {query}")
                return cached_result

        try:
            # Build API request
            params = {
                'q': query,
                'lang': lang,
                'country': country,
                'max': max_results,
                'apikey': self.api_key
            }

            logger.info(f"[GNews] Fetching news for query: {query} (max: {max_results})")

            response = requests.get(
                f"{self.BASE_URL}/search",
                params=params,
                timeout=10
            )

            # Check response status
            if response.status_code == 200:
                data = response.json()
                result = {
                    'success': True,
                    'articles': data.get('articles', []),
                    'totalArticles': data.get('totalArticles', 0)
                }

                # Cache the result
                cache.set(cache_key, result, self.CACHE_TTL)

                logger.info(f"[GNews] Fetched {len(result['articles'])} articles for query: {query}")
                return result

            elif response.status_code == 429:
                # Rate limit exceeded
                logger.warning(f"[GNews] Rate limit exceeded for query: {query}")
                return {
                    'success': False,
                    'error': 'Rate limit exceeded. Please try again later.',
                    'articles': [],
                    'totalArticles': 0
                }

            elif response.status_code == 403:
                # Invalid API key
                logger.error(f"[GNews] Invalid API key")
                return {
                    'success': False,
                    'error': 'Invalid API key',
                    'articles': [],
                    'totalArticles': 0
                }

            else:
                # Other error
                logger.error(f"[GNews] API error {response.status_code}: {response.text}")
                return {
                    'success': False,
                    'error': f'API error: {response.status_code}',
                    'articles': [],
                    'totalArticles': 0
                }

        except requests.exceptions.Timeout:
            logger.error(f"[GNews] Request timeout for query: {query}")
            return {
                'success': False,
                'error': 'Request timeout',
                'articles': [],
                'totalArticles': 0
            }

        except Exception as e:
            logger.error(f"[GNews] Error fetching news: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'articles': [],
                'totalArticles': 0
            }

    def fetch_stock_news(
        self,
        stock_symbol: str,
        stock_name: Optional[str] = None,
        max_results: int = 3
    ) -> Dict:
        """
        Fetch news for a specific stock

        Args:
            stock_symbol: Stock symbol (e.g., "RELIANCE")
            stock_name: Full stock name (e.g., "Reliance Industries")
            max_results: Maximum number of articles

        Returns:
            News result dict

        Example:
            >>> client = GNewsClient()
            >>> news = client.fetch_stock_news("RELIANCE", "Reliance Industries", max_results=3)
        """
        # Build search query with improved company name matching
        if stock_name:
            # Clean up stock name for better matching
            # Remove common suffixes that news articles often omit
            clean_name = stock_name
            suffixes = [' Ltd', ' Limited', ' Inc', ' Corporation', ' Corp', ' Pvt', ' Private']
            for suffix in suffixes:
                clean_name = clean_name.replace(suffix, '')

            # Use OR operator to search for both cleaned name and symbol
            # This increases chances of finding relevant articles
            query = f'("{clean_name}" OR {stock_symbol}) India'
        else:
            query = f"{stock_symbol} India"

        return self.fetch_news(query, max_results=max_results)

    def fetch_industry_news(
        self,
        industry_name: str,
        max_results: int = 3
    ) -> Dict:
        """
        Fetch news for a specific industry

        Args:
            industry_name: Industry name (e.g., "Oil and Gas")
            max_results: Maximum number of articles

        Returns:
            News result dict

        Example:
            >>> client = GNewsClient()
            >>> news = client.fetch_industry_news("Oil and Gas", max_results=3)
        """
        query = f"{industry_name} India"
        return self.fetch_news(query, max_results=max_results)

    def fetch_competitor_news(
        self,
        competitors: List[str],
        max_results: int = 3
    ) -> Dict:
        """
        Fetch news for competitor companies

        Args:
            competitors: List of competitor names
            max_results: Maximum number of articles total

        Returns:
            News result dict with articles from all competitors

        Example:
            >>> client = GNewsClient()
            >>> news = client.fetch_competitor_news(["TCS", "Infosys", "Wipro"], max_results=3)
        """
        if not competitors:
            return {
                'success': True,
                'articles': [],
                'totalArticles': 0
            }

        # Build query with competitor names
        # Limit to top 3 competitors to avoid overly long queries
        top_competitors = competitors[:3]

        # Clean up competitor names for better matching
        suffixes = [' Ltd', ' Limited', ' Inc', ' Corporation', ' Corp', ' Pvt', ' Private']
        cleaned_competitors = []

        for competitor in top_competitors:
            # Remove common suffixes
            clean_name = competitor
            for suffix in suffixes:
                clean_name = clean_name.replace(suffix, '')

            # Wrap in quotes if name has spaces for exact phrase matching
            if ' ' in clean_name:
                cleaned_competitors.append(f'"{clean_name}"')
            else:
                cleaned_competitors.append(clean_name)

        # Build OR query with cleaned names
        query = " OR ".join(cleaned_competitors) + " India"

        return self.fetch_news(query, max_results=max_results)


# Convenience function for easy import
def get_gnews_client() -> GNewsClient:
    """
    Get GNews client instance

    Returns:
        GNewsClient instance

    Example:
        >>> from apps.data.services.gnews_client import get_gnews_client
        >>> client = get_gnews_client()
        >>> news = client.fetch_stock_news("RELIANCE")
    """
    return GNewsClient()
