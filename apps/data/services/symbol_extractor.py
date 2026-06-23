"""
Symbol Extractor Service

Extracts NSE stock symbols from news article text using a lookup table
built from ContractStockData and TLStockData.

Design:
- Class-level lookup cache (loaded once per process)
- Multi-variant matching: full name, short name, ticker code
- Strips common corporate suffixes before matching
- Word-boundary matching to avoid false positives
"""

import re
import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Corporate suffixes to strip when building lookup variants
_STRIP_SUFFIXES = (
    ' limited', ' ltd', ' ltd.', ' l.t.d.', ' industries', ' industry',
    ' corporation', ' corp', ' incorporated', ' inc', ' pvt', ' private',
    ' holdings', ' holding', ' enterprises', ' enterprise', ' group',
    ' technologies', ' technology', ' services', ' solutions', ' systems',
    ' finance', ' financial', ' bank', ' banks', ' insurance',
)

# Tokens that are too generic to use as standalone matchers even if >= 3 chars
_BLOCKLIST = {
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
    'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him',
    'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way',
    'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too',
    'use', 'big', 'per', 'net', 'set', 'buy', 'sell', 'hold',
    'tax', 'gst', 'ipo', 'nse', 'bse', 'rbi', 'sebi', 'fii', 'dii',
    'npa', 'emi', 'upi', 'pan', 'kra', 'nav', 'aum', 'roi', 'eps',
    'roe', 'bps', 'yoy', 'qoq', 'mom', 'nii', 'nim', 'gnpa', 'nnpa',
    'care', 'crisil', 'icra', 'india', 'nifty', 'sensex',
}

# Manual aliases for well-known abbreviations that don't come through name-stripping.
# These take precedence over the DB lookup (first match wins in the lookup build,
# but these are injected after DB load so they always win).
_MANUAL_ALIASES: Dict[str, str] = {
    'sbi': 'SBIN',
    'lic': 'LICI',
    'ril': 'RELIANCE',
    'hul': 'HINDUNILVR',
    'itc': 'ITC',
    'ntpc': 'NTPC',
    'ongc': 'ONGC',
    'bhel': 'BHEL',
    'sail': 'SAIL',
    'nmdc': 'NMDC',
    'gail': 'GAIL',
    'bpcl': 'BPCL',
    'hpcl': 'HPCL',
    'ioc': 'IOC',
    'mrf': 'MRF',
    'tvs': 'TVSMOTOR',
    'm&m': 'M&M',
}


def _normalize(text: str) -> str:
    """Lowercase and remove punctuation for lookup key generation."""
    return re.sub(r'[^a-z0-9 ]', ' ', text.lower()).strip()


def _strip_corporate_suffix(name: str) -> str:
    """Remove common corporate suffixes from a normalized company name."""
    result = name
    for suffix in _STRIP_SUFFIXES:
        if result.endswith(suffix):
            result = result[: -len(suffix)].strip()
            break
    return result


def _build_variants(company_name: str, nse_code: str) -> List[str]:
    """
    Return all text variants that should map to nse_code.

    E.g., 'Reliance Industries Limited' → ['reliance industries limited',
    'reliance industries', 'reliance']
    """
    base = _normalize(company_name)
    variants: List[str] = []

    # Full normalized name
    if len(base) >= 3 and base not in _BLOCKLIST:
        variants.append(base)

    # Strip suffix once
    stripped = _strip_corporate_suffix(base)
    if stripped != base and len(stripped) >= 3 and stripped not in _BLOCKLIST:
        variants.append(stripped)

    # Strip suffix again (handles "Tata Consultancy Services Ltd" → "Tata Consultancy")
    stripped2 = _strip_corporate_suffix(stripped)
    if stripped2 != stripped and len(stripped2) >= 3 and stripped2 not in _BLOCKLIST:
        variants.append(stripped2)

    # NSE code itself (as lowercase)
    code = nse_code.lower().strip()
    if len(code) >= 3 and code not in _BLOCKLIST:
        variants.append(code)

    return variants


class SymbolExtractor:
    """
    Builds a lookup from company names/tickers → NSE codes and uses it to
    extract symbols from free-form news article text.

    Thread-safe read-only access after _ensure_loaded().
    """

    _lookup: Dict[str, str] = {}   # normalized_variant → nse_code
    _loaded: bool = False

    def _build_lookup(self) -> None:
        """Load ContractStockData and TLStockData into the class-level lookup."""
        from apps.data.models import ContractStockData, TLStockData

        lookup: Dict[str, str] = {}

        # Load from ContractStockData (primary F&O universe)
        for row in ContractStockData.objects.values('nse_code', 'stock_name'):
            code = (row['nse_code'] or '').strip()
            name = (row['stock_name'] or '').strip()
            if not code:
                continue
            for variant in _build_variants(name, code):
                if variant not in lookup:
                    lookup[variant] = code

        # Load from TLStockData (broader universe)
        for row in TLStockData.objects.values('nsecode', 'stock_name'):
            code = (row['nsecode'] or '').strip()
            name = (row['stock_name'] or '').strip()
            if not code:
                continue
            for variant in _build_variants(name, code):
                if variant not in lookup:
                    lookup[variant] = code

        # Inject manual aliases (override DB if different)
        lookup.update(_MANUAL_ALIASES)

        SymbolExtractor._lookup = lookup
        SymbolExtractor._loaded = True
        logger.info(f"SymbolExtractor: loaded {len(lookup)} name variants for symbol lookup")

    def _ensure_loaded(self) -> None:
        if not SymbolExtractor._loaded:
            try:
                self._build_lookup()
            except Exception as e:
                logger.warning(f"SymbolExtractor: could not build lookup: {e}")

    def extract_symbols_from_text(self, title: str, content: str) -> List[str]:
        """
        Return list of NSE codes found in title + first 500 chars of content.

        Uses word-boundary matching so 'HDFC' in 'HDFC Bank reported...' matches
        but 'SBI' inside 'subsidiary' does not.
        """
        self._ensure_loaded()
        if not SymbolExtractor._lookup:
            return []

        # Work on title + limited content to avoid false positives in long body text
        search_text = _normalize(f"{title} {content[:500]}")

        found: Set[str] = set()

        # Sort variants longest-first so "reliance industries" is tried before "reliance"
        for variant, nse_code in sorted(
            SymbolExtractor._lookup.items(), key=lambda kv: -len(kv[0])
        ):
            if len(variant) < 3:
                continue
            # Use word-boundary pattern
            pattern = r'(?<![a-z0-9])' + re.escape(variant) + r'(?![a-z0-9])'
            if re.search(pattern, search_text):
                found.add(nse_code)

        return sorted(found)

    def extract_and_tag(self, article) -> List[str]:
        """
        Extract symbols from article text and update symbols_mentioned if currently empty.

        Returns the list of extracted symbols (may be empty).
        """
        if article.symbols_mentioned:
            return article.symbols_mentioned  # already tagged, don't overwrite

        symbols = self.extract_symbols_from_text(article.title, article.content or article.summary or '')
        if symbols:
            article.symbols_mentioned = symbols
            article.save(update_fields=['symbols_mentioned'])
            logger.debug(f"SymbolExtractor: tagged article {article.id} with {symbols}")
        return symbols

    @classmethod
    def invalidate_cache(cls) -> None:
        """Force reload of lookup on next use (call after ContractStockData changes)."""
        cls._loaded = False
        cls._lookup = {}


# Module-level singleton
_extractor: Optional[SymbolExtractor] = None


def get_symbol_extractor() -> SymbolExtractor:
    global _extractor
    if _extractor is None:
        _extractor = SymbolExtractor()
    return _extractor
