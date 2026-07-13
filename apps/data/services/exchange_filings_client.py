"""
Exchange Filings Client

Fetches corporate announcements from NSE and BSE public APIs and stores
them as NewsArticle records with:
  - source_quality_score = 1.0  (exchange-grade, highest authority)
  - news_type = 'STOCK'
  - symbols_mentioned populated via SymbolExtractor

NSE API notes:
  - Requires a session cookie obtained by visiting the NSE homepage first.
  - Returns JSON list of announcements with symbol, subject, description, date.

BSE API notes:
  - Public endpoint, no session required.
  - Returns JSON with a list of announcements.

Both clients store articles idempotently (URL unique constraint prevents duplicates).
"""

import hashlib
import logging
from datetime import datetime
from typing import Dict, List

import pytz
import requests
from django.utils import timezone

_IST = pytz.timezone('Asia/Kolkata')

logger = logging.getLogger(__name__)

# Filing category → event_type mapping used for LLM-prompt enrichment
_FILING_CATEGORY_MAP = {
    'board meeting': 'GUIDANCE',
    'financial results': 'EARNINGS',
    'quarterly results': 'EARNINGS',
    'annual results': 'EARNINGS',
    'dividend': 'EARNINGS',
    'buyback': 'EARNINGS',
    'rights issue': 'EARNINGS',
    'bonus': 'EARNINGS',
    'merger': 'ACQUISITION',
    'acquisition': 'ACQUISITION',
    'takeover': 'ACQUISITION',
    'amalgamation': 'ACQUISITION',
    'sebi': 'REGULATORY',
    'penalty': 'LEGAL',
    'order': 'REGULATORY',
    'show cause': 'LEGAL',
    'agm': 'GUIDANCE',
    'egm': 'GUIDANCE',
    'management': 'MANAGEMENT',
    'ceo': 'MANAGEMENT',
    'md': 'MANAGEMENT',
}


def _classify_event_type(subject: str) -> str:
    """Map a filing subject string to an event_type constant."""
    subject_lower = subject.lower()
    for keyword, event_type in _FILING_CATEGORY_MAP.items():
        if keyword in subject_lower:
            return event_type
    return 'REGULATORY'  # default for exchange filings


def _build_filing_url(exchange: str, symbol: str, filing_id: str) -> str:
    """
    Build a unique, clickable URL for a filing.

    NSE: company announcements page (seqno disambiguates per-filing in our DB;
         the param is ignored by NSE but makes each URL unique for dedup).
    BSE: announcement detail page (newsid IS honoured by BSE's ann.html handler).
    """
    if exchange == 'NSE':
        return (
            f"https://www.nseindia.com/companies-listing/corporate-filings-announcements"
            f"?symbol={symbol}&seqno={filing_id}"
        )
    else:  # BSE
        return (
            f"https://www.bseindia.com/corporates/ann.html"
            f"?scrip={symbol}&newsid={filing_id}"
        )


class NSEFilingsClient:
    """
    Fetches corporate announcements from NSE's public API.

    NSE requires a session cookie set by visiting the homepage first.
    All failures are non-fatal — returns empty list on any error.
    """

    BASE_URL = 'https://www.nseindia.com'
    API_URL = 'https://www.nseindia.com/api/corporate-announcements'
    HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.nseindia.com/',
    }

    def _make_session(self) -> requests.Session:
        """Return a session with NSE cookies initialised."""
        s = requests.Session()
        s.headers.update(self.HEADERS)
        try:
            s.get(self.BASE_URL, timeout=10)
        except Exception as e:
            logger.warning(f"NSE session init failed: {e}")
        return s

    def fetch(self, hours_back: int = 4) -> List[Dict]:
        """
        Fetch recent corporate announcements from NSE.

        Returns list of normalised dicts:
          {symbol, company_name, subject, description, date_str, filing_id}
        """
        try:
            session = self._make_session()
            params = {'index': 'equities'}
            resp = session.get(self.API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            announcements = data if isinstance(data, list) else data.get('data', [])
            results = []
            cutoff_ts = timezone.now().timestamp() - hours_back * 3600

            for item in announcements:
                try:
                    date_str = item.get('an_dt') or item.get('date') or ''
                    # NSE timestamps are in IST — localise correctly before comparing
                    ts = None
                    for fmt in ('%d-%b-%Y %H:%M:%S', '%d-%b-%Y', '%Y-%m-%dT%H:%M:%S'):
                        try:
                            ts = _IST.localize(
                                datetime.strptime(date_str.strip(), fmt)
                            ).timestamp()
                            break
                        except ValueError:
                            continue

                    if ts and ts < cutoff_ts:
                        continue

                    symbol = (item.get('symbol') or '').strip().upper()
                    subject = item.get('subject') or item.get('desc') or ''
                    description = item.get('attchmntText') or item.get('desc') or subject
                    filing_id = str(
                        item.get('seqNo') or item.get('id') or
                        hashlib.md5(f"{symbol}{subject}".encode()).hexdigest()[:12]
                    )

                    if symbol and subject:
                        results.append({
                            'symbol': symbol,
                            'company_name': item.get('sm_name') or item.get('company') or symbol,
                            'subject': subject,
                            'description': description,
                            'date_str': date_str,
                            'filing_id': filing_id,
                        })
                except Exception:
                    continue

            logger.info(f"NSE: fetched {len(results)} recent announcements")
            return results

        except Exception as e:
            logger.warning(f"NSE filings fetch failed: {e}")
            return []


class BSEFilingsClient:
    """
    Fetches corporate announcements from BSE's public API.
    No session cookie required.
    """

    API_URL = (
        'https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w'
    )
    HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json',
        'Referer': 'https://www.bseindia.com/',
        'Origin': 'https://www.bseindia.com',
    }

    def fetch(self, hours_back: int = 4) -> List[Dict]:
        """
        Fetch recent corporate announcements from BSE.
        Returns same normalised dict structure as NSEFilingsClient.fetch().
        """
        try:
            params = {
                'pageno': 1,
                'strCat': '-1',
                'strPrevDate': '',
                'strScrip': '',
                'strSearch': 'P',
                'strToDate': '',
                'strType': 'C',
                'subcategory': '-1',
            }
            resp = requests.get(
                self.API_URL, params=params, headers=self.HEADERS, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

            table = data.get('Table', []) or []
            results = []
            cutoff_ts = timezone.now().timestamp() - hours_back * 3600

            for item in table:
                try:
                    date_str = item.get('DissemDT') or item.get('NewsDate') or ''
                    # BSE timestamps are in IST — localise correctly before comparing
                    ts = None
                    for fmt in ('%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y'):
                        try:
                            ts = _IST.localize(
                                datetime.strptime(date_str.strip()[:19], fmt)
                            ).timestamp()
                            break
                        except ValueError:
                            continue

                    if ts and ts < cutoff_ts:
                        continue

                    scrip = (item.get('SCRIP_CD') or '').strip()
                    company_name = (item.get('SLONGNAME') or item.get('SCRIP_CD') or '').strip()
                    headline = item.get('NEWSSUB') or item.get('Headline') or ''
                    body = item.get('ATTACHMENTNAME') or headline
                    filing_id = str(
                        item.get('NEWSID') or item.get('NewsID') or
                        hashlib.md5(f"{scrip}{headline}".encode()).hexdigest()[:12]
                    )

                    if headline:
                        results.append({
                            'symbol': scrip,       # BSE code, may differ from NSE code
                            'company_name': company_name,
                            'subject': headline,
                            'description': body,
                            'date_str': date_str,
                            'filing_id': filing_id,
                        })
                except Exception:
                    continue

            logger.info(f"BSE: fetched {len(results)} recent announcements")
            return results

        except Exception as e:
            logger.warning(f"BSE filings fetch failed: {e}")
            return []


class ExchangeFilingsClient:
    """
    Orchestrates NSE + BSE filing fetches and stores results as NewsArticle records.

    Each filing is stored with:
      - source_quality_score = 1.0
      - news_type = 'STOCK'
      - symbols_mentioned resolved via SymbolExtractor
      - event_type classified from subject text
      - sentiment_score = None (will be analyzed by LLM on next algorithm run
        via on-demand NewsImpactAnalyzer, or in a future morning sync)
    """

    def fetch_and_store_all(self, hours_back: int = 4) -> Dict:
        """
        Fetch from both NSE and BSE and store new articles.
        Returns summary dict with counts.
        """
        from apps.data.models import NewsArticle
        from apps.data.services.symbol_extractor import get_symbol_extractor

        extractor = get_symbol_extractor()
        stats = {'nse': 0, 'bse': 0, 'skipped': 0, 'errors': 0}

        def _store(filing: Dict, exchange: str) -> bool:
            """Store one filing as a NewsArticle. Returns True if new."""
            try:
                url = _build_filing_url(exchange, filing['symbol'], filing['filing_id'])
                if NewsArticle.objects.filter(url=url).exists():
                    stats['skipped'] += 1
                    return False

                # Resolve NSE symbol from company name (BSE codes differ from NSE)
                nse_symbols = extractor.extract_symbols_from_text(
                    filing['company_name'], filing['subject']
                )
                # If the exchange already provided an NSE symbol directly, prefer it
                if exchange == 'NSE' and filing['symbol']:
                    nse_symbols = list({filing['symbol']} | set(nse_symbols))

                event_type = _classify_event_type(filing['subject'])
                title = f"[{exchange}] {filing['company_name']}: {filing['subject']}"
                content = filing['description'] or filing['subject']

                # search_keywords: stock symbol + company name so keyword-based
                # queries (get_historical_news_analysis) also find this filing.
                keywords = [k for k in [filing.get('symbol', ''), filing.get('company_name', '')] if k]

                NewsArticle.objects.create(
                    title=title[:500],
                    content=content,
                    summary=filing['subject'][:500],
                    source=exchange,
                    url=url,
                    published_at=timezone.now(),
                    category='Stock',       # Required: UI queries filter by category='Stock'
                    news_type='STOCK',
                    symbols_mentioned=nse_symbols,
                    search_keywords=keywords,
                    source_quality_score=1.0,   # Exchange-grade authority
                    event_type=event_type,
                )
                return True

            except Exception as e:
                logger.debug(f"Error storing {exchange} filing: {e}")
                stats['errors'] += 1
                return False

        # NSE
        for filing in NSEFilingsClient().fetch(hours_back=hours_back):
            if _store(filing, 'NSE'):
                stats['nse'] += 1

        # BSE
        for filing in BSEFilingsClient().fetch(hours_back=hours_back):
            if _store(filing, 'BSE'):
                stats['bse'] += 1

        logger.info(
            f"ExchangeFilings: stored NSE={stats['nse']}, BSE={stats['bse']}, "
            f"skipped={stats['skipped']}, errors={stats['errors']}"
        )
        return stats


def get_exchange_filings_client() -> ExchangeFilingsClient:
    return ExchangeFilingsClient()
