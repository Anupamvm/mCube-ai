"""
Resolves an ISIN for mutual fund holdings that arrived without one.

MF Central's own exports (both the Stimulsoft PDF and the XLSX "Portfolio
Details" sheet) have no ISIN column at all — holdings are identified only by
scheme name + AMC + folio number. Every downstream feature that depends on
ISIN (NAV/price refresh, category/sub-category enrichment, risk metrics,
fund-level XIRR) is silently inert for these holdings until an ISIN is
resolved by some other means (e.g. a matching NSDL import backfills it by
name — see product_resolver.py).

This module closes that gap directly using MFAPI's own /mf/search endpoint:
it extracts the "core" fund identity from our (often plan/parenthetical-
qualified) scheme name, asks MFAPI for schemes matching that core name, then
picks the best plan-variant match from that small, precise candidate set —
rather than fuzzy-scanning its entire ~37k-scheme bulk list.
"""
from __future__ import annotations
import re
import logging

logger = logging.getLogger('apps.investments')

_SEPARATORS_RE = re.compile(r'[^a-z0-9]+')
# The point at which an AMC's own scheme-name formatting starts qualifying
# the core fund identity with plan/option details we want to search without,
# then disambiguate against ourselves.
_CORE_QUERY_STOP_RE = re.compile(r'\s*[-(]|\bgrowth\b|\bdirect\b|\bregular\b|\bidcw\b', re.IGNORECASE)

# Match confidence must clear this bar, AND beat the runner-up by a healthy
# margin — a wrong ISIN silently corrupts price/NAV/tax data, so an
# ambiguous match is worse than no match.
_MIN_SCORE = 0.5
_MIN_MARGIN = 0.08
_GROWTH_TOKENS = {'growth'}
_PAYOUT_TOKENS = {'idcw', 'dividend', 'payout', 'bonus'}


def _tokens(name: str) -> set[str]:
    normalized = _SEPARATORS_RE.sub(' ', (name or '').lower()).strip()
    return set(t for t in normalized.split(' ') if t)


def _core_query(name: str) -> str:
    """Strip plan/option qualifiers to get a search-friendly core fund name."""
    m = _CORE_QUERY_STOP_RE.search(name or '')
    return (name[:m.start()] if m else (name or '')).strip()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def resolve_isin(scheme_name: str, client) -> tuple[str, str] | None:
    """
    Best-effort ISIN match for one scheme name via MFAPI's search endpoint.
    Returns (isin, matched_scheme_name) or None if no confident match exists.
    """
    our_tokens = _tokens(scheme_name)
    if not our_tokens:
        return None

    query = _core_query(scheme_name)
    if not query:
        return None

    candidates = client.search_schemes(query)
    if not candidates:
        return None

    our_specifies_plan_type = bool(our_tokens & (_GROWTH_TOKENS | _PAYOUT_TOKENS))

    scored = []
    for c in candidates:
        name = c.get('schemeName', '')
        code = c.get('schemeCode')
        if not name or not code:
            continue
        cand_tokens = _tokens(name)
        score = _jaccard(our_tokens, cand_tokens)
        # When our own captured name doesn't say Growth/IDCW at all (common
        # gap in MF Central's raw export), prefer a Growth-plan candidate
        # over a payout/IDCW one on an otherwise-tied score — Growth is the
        # overwhelmingly common real-world default, and our stored
        # current_value already reflects unit-based accumulation, not payouts.
        if not our_specifies_plan_type:
            if cand_tokens & _GROWTH_TOKENS:
                score += 0.01
            elif cand_tokens & _PAYOUT_TOKENS:
                score -= 0.01
        scored.append({'score': score, 'isin': None, 'code': code, 'name': name})

    scored.sort(key=lambda c: c['score'], reverse=True)
    if not scored:
        return None

    best = scored[0]
    runner_up_score = scored[1]['score'] if len(scored) > 1 else 0.0
    if best['score'] < _MIN_SCORE or (best['score'] - runner_up_score) < _MIN_MARGIN:
        logger.debug(
            'ISIN match too ambiguous for "%s" (query="%s"): best=%.2f (%s) runner_up=%.2f',
            scheme_name[:60], query, best['score'], best['name'][:60], runner_up_score,
        )
        return None

    _, meta = client.get_nav_history(best['code'])
    isin = meta.get('isin_growth') or meta.get('isin_div_reinvestment')
    if not isin:
        logger.debug('Matched "%s" to scheme %s but it has no ISIN', scheme_name[:60], best['name'][:60])
        return None

    return isin, best['name']


def backfill_isins(products_qs) -> int:
    """
    Resolve and save ISINs for any MUTUAL_FUND products in `products_qs` that
    have none — the prerequisite for price refresh, category enrichment, risk
    metrics, and fund-level XIRR, none of which work without an ISIN.
    """
    from .mfapi_client import MFAPIClient

    missing = list(products_qs.filter(isin=''))
    if not missing:
        return 0

    client = MFAPIClient()
    resolved = 0
    for product in missing:
        match = resolve_isin(product.name, client)
        if not match:
            continue
        isin, matched_name = match
        product.isin = isin
        product.save(update_fields=['isin'])
        resolved += 1
        logger.info('Resolved ISIN for "%s" -> %s (matched "%s")', product.name[:60], isin, matched_name[:60])

    logger.info('MF ISIN backfill: %d/%d holdings matched', resolved, len(missing))
    return resolved
