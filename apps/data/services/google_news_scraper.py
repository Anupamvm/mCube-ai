"""
Google News RSS Scraper

Supplemental news source alongside GNews.io. Uses the public Google News RSS
feed (no API key required) and follows redirect URLs to fetch full article
content from publisher pages.

Returns the same dict format as GNewsClient so it plugs into all existing
consumers (NewsImpactAnalyzer, NewsProcessor) without adaptation.
"""

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from django.core.cache import cache

logger = logging.getLogger(__name__)


class GoogleNewsScraper:
    """
    Scrapes Google News RSS feed for stock and market news.

    Mirrors the GNewsClient public API (fetch_stock_news, fetch_market_news)
    so callers can merge results from both sources without adaptation.
    """

    RSS_BASE_URL = "https://news.google.com/rss/search"
    CACHE_TTL = 14400           # 4 hours (fresher than GNews 8h)
    CONTENT_FETCH_TIMEOUT = 5   # seconds per publisher page fetch
    MAX_CONTENT_CHARS = 2000    # truncate extracted body text

    REQUEST_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
    }

    # Suffixes stripped from company names before building queries — same list
    # as GNewsClient.fetch_stock_news (gnews_client.py:304)
    _NAME_SUFFIXES = [' Ltd', ' Limited', ' Inc', ' Corporation', ' Corp', ' Pvt', ' Private']

    def fetch_stock_news(
        self,
        stock_symbol: str,
        stock_name: Optional[str] = None,
        max_results: int = 20
    ) -> Dict:
        """
        Fetch Google News for a stock. max_results=20 covers ~2 pages of results.

        Returns the same dict structure as GNewsClient.fetch_stock_news().
        """
        if stock_name:
            clean = stock_name
            for suffix in self._NAME_SUFFIXES:
                clean = clean.replace(suffix, '')
            clean = clean.strip()
            query = f'"{clean}" OR {stock_symbol} NSE stock India'
        else:
            query = f'{stock_symbol} NSE stock India'

        return self._fetch_rss(query, max_results)

    def fetch_market_news(self, max_results: int = 20) -> Dict:
        """
        Fetch broad Indian market news from Google News RSS.

        Single RSS call covering Nifty/Sensex/RBI/FII — simpler than the
        GNewsClient multi-keyword loop since RSS returns up to 100 items.
        Returns the same dict structure as GNewsClient.fetch_market_news().
        """
        query = 'Nifty OR Sensex OR RBI OR FII OR "Indian stock market"'
        return self._fetch_rss(query, max_results)

    def _fetch_rss(self, query: str, max_results: int) -> Dict:
        """
        Core RSS fetch and parse. Always returns success=True; partial results
        are acceptable (same contract as GNewsClient.fetch_market_news).
        """
        cache_key = f"gnews_rss:{hashlib.md5(query.encode()).hexdigest()[:16]}:{max_results}"
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[GoogleNews] Cache hit: {query[:60]}")
            return cached

        params = {'q': query, 'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en'}
        url = f"{self.RSS_BASE_URL}?{urlencode(params)}"

        try:
            response = requests.get(url, headers=self.REQUEST_HEADERS, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning(f"[GoogleNews] RSS fetch failed: {e}")
            return {'success': False, 'articles': [], 'totalArticles': 0, 'error': str(e)}

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            logger.warning(f"[GoogleNews] XML parse failed: {e}")
            return {'success': False, 'articles': [], 'totalArticles': 0, 'error': 'XML parse error'}

        channel = root.find('channel')
        if channel is None:
            return {'success': True, 'articles': [], 'totalArticles': 0}

        articles = []
        for item in channel.findall('item')[:max_results]:
            try:
                article = self._normalize_article(item)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.debug(f"[GoogleNews] Skipping item: {e}")

        result = {'success': True, 'articles': articles, 'totalArticles': len(articles)}
        cache.set(cache_key, result, self.CACHE_TTL)
        logger.info(f"[GoogleNews] Fetched {len(articles)} articles for: {query[:60]}")
        return result

    def _normalize_article(self, item) -> Optional[Dict]:
        """
        Convert a parsed RSS <item> element into a GNewsClient-compatible dict.
        Follows the Google redirect URL to resolve the real publisher URL and
        fetches full article body text.
        """
        title = (item.findtext('title') or '').strip()
        google_url = (item.findtext('link') or '').strip()
        pub_date_str = (item.findtext('pubDate') or '').strip()

        source_elem = item.find('source')
        source_name = source_elem.text.strip() if source_elem is not None and source_elem.text else 'Google News'
        source_url = source_elem.get('url', '') if source_elem is not None else ''

        if not title or not google_url:
            return None

        # Strip HTML from description to get plain snippet
        raw_desc = item.findtext('description') or ''
        if raw_desc:
            description = BeautifulSoup(raw_desc, 'html.parser').get_text(separator=' ', strip=True)
        else:
            description = ''

        published_at = self._parse_pub_date(pub_date_str)
        real_url, full_content = self._resolve_and_fetch(google_url)

        return {
            'title': title,
            'description': description,
            'content': full_content or description,
            'url': real_url or google_url,
            'image': '',
            'publishedAt': published_at,
            'source': {'name': source_name, 'url': source_url},
        }

    def _parse_pub_date(self, pub_date_str: str) -> str:
        """Convert RFC 2822 pubDate to ISO 8601 string."""
        if not pub_date_str:
            return datetime.now(timezone.utc).isoformat()
        try:
            return parsedate_to_datetime(pub_date_str).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()

    def _resolve_and_fetch(self, google_url: str) -> Tuple[str, str]:
        """
        Follow the Google News redirect to the publisher page, then extract
        article body text. Returns ('', '') on any failure so callers fall
        back to the RSS snippet — article is still included either way.
        """
        try:
            resp = requests.get(
                google_url,
                headers=self.REQUEST_HEADERS,
                timeout=self.CONTENT_FETCH_TIMEOUT,
                allow_redirects=True
            )
            real_url = resp.url
            content = self._extract_article_content(resp.text)
            return real_url, content
        except requests.exceptions.Timeout:
            logger.debug(f"[GoogleNews] Content fetch timeout: {google_url[:80]}")
            return '', ''
        except Exception as e:
            logger.debug(f"[GoogleNews] Content fetch error: {e}")
            return '', ''

    def _extract_article_content(self, html: str) -> str:
        """
        Extract article body text from publisher HTML using BeautifulSoup.

        Priority: <article> tag → <main> tag → all <p> tags.
        Returns empty string if no usable content found (< 200 chars).
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                tag.decompose()

            for selector in (soup.find('article'), soup.find('main')):
                if selector:
                    text = selector.get_text(separator=' ', strip=True)
                    if len(text) > 200:
                        return text[:self.MAX_CONTENT_CHARS]

            text = ' '.join(p.get_text(strip=True) for p in soup.find_all('p'))
            return text[:self.MAX_CONTENT_CHARS] if len(text) > 200 else ''

        except Exception as e:
            logger.debug(f"[GoogleNews] Content extraction error: {e}")
            return ''


def get_google_news_scraper() -> GoogleNewsScraper:
    """Get a GoogleNewsScraper instance. Mirrors get_gnews_client() pattern."""
    return GoogleNewsScraper()
