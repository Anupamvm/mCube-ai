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
    CACHE_TTL = 28800  # 8 hour cache - avoid repetitive API calls for same keywords

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

    def _sanitize_query(self, query: str) -> str:
        """
        Sanitize query string to avoid GNews API syntax errors.

        Removes or replaces special characters that can cause query syntax errors:
        - & (AND operator in GNews)
        - | (OR operator)
        - Unbalanced quotes
        - Other problematic characters

        Args:
            query: Raw query string

        Returns:
            Sanitized query string safe for GNews API
        """
        if not query:
            return query

        # Replace common problematic patterns
        sanitized = query

        # Replace & with space (e.g., "S&P 500" -> "S P 500")
        sanitized = sanitized.replace('&', ' ')

        # Replace | with OR (explicit operator)
        sanitized = sanitized.replace('|', ' OR ')

        # Remove unbalanced quotes
        quote_count = sanitized.count('"')
        if quote_count % 2 != 0:
            sanitized = sanitized.replace('"', '')

        # Remove other problematic characters
        for char in ['[', ']', '{', '}', '\\', '^', '~']:
            sanitized = sanitized.replace(char, ' ')

        # Collapse multiple spaces
        while '  ' in sanitized:
            sanitized = sanitized.replace('  ', ' ')

        return sanitized.strip()

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

        # Sanitize query to avoid syntax errors
        sanitized_query = self._sanitize_query(query)
        if not sanitized_query:
            logger.warning(f"[GNews] Empty query after sanitization: '{query}'")
            return {
                'success': False,
                'error': 'Invalid query',
                'articles': [],
                'totalArticles': 0
            }

        # Check cache first (use original query for cache key consistency)
        cache_key = self._build_cache_key(query, max_results)
        if use_cache:
            cached_result = cache.get(cache_key)
            if cached_result:
                logger.info(f"[GNews] Cache hit for query: {query}")
                return cached_result

        try:
            # Build API request with sanitized query
            params = {
                'q': sanitized_query,
                'lang': lang,
                'country': country,
                'max': max_results,
                'apikey': self.api_key
            }

            logger.info(f"[GNews] Fetching news for query: {sanitized_query} (max: {max_results})")

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

            elif response.status_code == 400:
                # Query syntax error - non-critical, log as warning and continue
                logger.warning(f"[GNews] Query syntax error for '{sanitized_query}': {response.text[:200]}")
                return {
                    'success': False,
                    'error': 'Query syntax error',
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
                # Other error - log as warning for non-critical status codes
                log_level = logger.error if response.status_code >= 500 else logger.warning
                log_level(f"[GNews] API error {response.status_code} for '{sanitized_query}': {response.text[:200]}")
                return {
                    'success': False,
                    'error': f'API error: {response.status_code}',
                    'articles': [],
                    'totalArticles': 0
                }

        except requests.exceptions.Timeout:
            logger.warning(f"[GNews] Request timeout for query: {sanitized_query}")
            return {
                'success': False,
                'error': 'Request timeout',
                'articles': [],
                'totalArticles': 0
            }

        except requests.exceptions.RequestException as e:
            logger.warning(f"[GNews] Request error for '{sanitized_query}': {e}")
            return {
                'success': False,
                'error': f'Request error: {str(e)}',
                'articles': [],
                'totalArticles': 0
            }

        except Exception as e:
            logger.warning(f"[GNews] Unexpected error for '{sanitized_query}': {e}")
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
            industry_name: Industry name (e.g., "Oil and Gas", "IT Consulting & Software")
            max_results: Maximum number of articles

        Returns:
            News result dict

        Example:
            >>> client = GNewsClient()
            >>> news = client.fetch_industry_news("Oil and Gas", max_results=3)
        """
        # Map specific industry names to broader, more searchable terms
        industry_mappings = {
            'IT Consulting & Software': 'IT software technology',
            'IT - Software': 'IT software technology',
            'Banks - Private Sector': 'private banks banking',
            'Banks - Public Sector': 'public sector banks PSU banking',
            'Refineries': 'oil refinery petroleum',
            'Oil Exploration': 'oil gas exploration ONGC',
            'Automobile - Cars & SUVs': 'automobile cars automotive',
            'Automobile - Two Wheelers': 'two wheeler motorcycle scooter',
            'Pharmaceuticals': 'pharma pharmaceutical drugs',
            'Telecom Services': 'telecom telecommunications 5G',
            'Steel - Large': 'steel industry manufacturing',
            'Power Generation & Distribution': 'power electricity energy',
            'Cement': 'cement construction infrastructure',
            'FMCG': 'FMCG consumer goods retail',
            'Insurance': 'insurance sector LIC',
            'Real Estate': 'real estate property housing',
        }

        # Get mapped query or use original with cleanup
        if industry_name in industry_mappings:
            search_terms = industry_mappings[industry_name]
        else:
            # Clean up industry name - remove special chars, use key words
            search_terms = industry_name.replace('&', '').replace('-', ' ').strip()
            # Take first 2-3 significant words
            words = [w for w in search_terms.split() if len(w) > 2]
            search_terms = ' '.join(words[:3])

        query = f"{search_terms} India industry sector"
        logger.info(f"[GNews] Industry query: '{industry_name}' -> '{query}'")
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
        suffixes = [' Ltd.', ' Ltd', ' Limited', ' Inc.', ' Inc', ' Corporation', ' Corp.', ' Corp', ' Pvt.', ' Pvt', ' Private']
        cleaned_competitors = []

        for competitor in top_competitors:
            # Remove common suffixes
            clean_name = competitor.strip()
            for suffix in suffixes:
                clean_name = clean_name.replace(suffix, '')
            clean_name = clean_name.strip()

            # Skip if name is too short after cleaning
            if len(clean_name) < 2:
                continue

            # For single word names, use as-is
            # For multi-word names, use quotes for exact phrase
            if ' ' in clean_name:
                cleaned_competitors.append(f'"{clean_name}"')
            else:
                cleaned_competitors.append(clean_name)

        if not cleaned_competitors:
            return {
                'success': True,
                'articles': [],
                'totalArticles': 0
            }

        # Build OR query with cleaned names
        query = " OR ".join(cleaned_competitors)
        logger.info(f"[GNews] Competitor query: {top_competitors} -> '{query}'")
        return self.fetch_news(query, max_results=max_results)


    def fetch_market_news(
        self,
        max_results_per_keyword: int = 10,
        use_cache: bool = True
    ) -> Dict:
        """
        Fetch market-moving news for Indian markets using multiple keywords.

        Fetches news about:
        - US Fed decisions, interest rates
        - Global market movements (Dow, Nasdaq, S&P)
        - Economic data (jobs, GDP, inflation)
        - Asian markets (Nikkei, Hang Seng)
        - Crude oil, gold prices
        - FII/DII activity
        - RBI policy
        - Nifty, Sensex movements

        Args:
            max_results_per_keyword: Max articles per keyword (default: 10)
            use_cache: Whether to use cached results (default: True)

        Returns:
            Dict with all fetched articles and metadata
        """
        # Market-moving keywords for Indian markets
        keywords = [
            # Global markets - overnight performance
            "US stock market Dow Jones",
            "Nasdaq SP500 stock market",
            "Asian markets Nikkei Hang Seng",
            # US Fed and economic data
            "Federal Reserve interest rate",
            "US Fed meeting decision",
            "US jobs data employment",
            "US inflation CPI",
            # Commodities affecting India
            "crude oil price",
            "gold price market",
            # Indian market specific
            "Nifty Sensex India",
            "FII DII India investment",
            "RBI policy rate India",
            # Global economic indicators
            "global recession economy",
            "China economy manufacturing",
        ]

        all_articles = []
        seen_urls = set()
        failed_keywords = []
        successful_keywords = []

        logger.info(f"[GNews] Fetching market news with {len(keywords)} keyword groups")

        for keyword in keywords:
            try:
                result = self.fetch_news(
                    query=keyword,
                    max_results=max_results_per_keyword,
                    use_cache=use_cache
                )

                if result.get('success') and result.get('articles'):
                    successful_keywords.append(keyword)
                    for article in result['articles']:
                        # Deduplicate by URL
                        url = article.get('url', '')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            article['search_keyword'] = keyword
                            all_articles.append(article)

                    logger.debug(f"[GNews] Keyword '{keyword}': {len(result['articles'])} articles")
                elif not result.get('success'):
                    error_msg = result.get('error', 'unknown')
                    failed_keywords.append(keyword)
                    logger.debug(f"[GNews] Keyword '{keyword}' failed: {error_msg}")

                    # Stop immediately on auth/key errors — no point retrying other keywords
                    if error_msg in ('Invalid API key', 'Rate limit exceeded. Please try again later.'):
                        logger.warning(f"[GNews] {error_msg} — skipping remaining keywords")
                        break

            except Exception as e:
                failed_keywords.append(keyword)
                logger.warning(f"[GNews] Error fetching '{keyword}': {e}")
                continue

        # Log summary
        if failed_keywords:
            logger.info(f"[GNews] {len(failed_keywords)}/{len(keywords)} keywords failed (non-critical)")

        logger.info(f"[GNews] Total unique market articles fetched: {len(all_articles)} from {len(successful_keywords)} keywords")

        return {
            'success': True,  # Always return success - partial results are acceptable
            'articles': all_articles,
            'totalArticles': len(all_articles),
            'keywords_used': keywords,
            'successful_keywords': len(successful_keywords),
            'failed_keywords': len(failed_keywords)
        }


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
