from __future__ import annotations
import json
import logging
from datetime import datetime
import requests
import redis
from django.conf import settings

logger = logging.getLogger('apps.investments')

MFAPI_BASE = getattr(settings, 'MFAPI_BASE_URL', 'https://api.mfapi.in/mf')
REDIS_URL = getattr(settings, 'INVESTMENTS_REDIS_URL', 'redis://localhost:6379/2')

_redis = redis.from_url(REDIS_URL, decode_responses=True)


class MFAPIClient:
    def search_schemes(self, query: str) -> list[dict]:
        """
        MFAPI's own name-search endpoint (/mf/search?q=). Does a literal
        substring match server-side, so it must be called with just the core
        fund identity (AMC + strategy name), not the full plan-qualified
        name — see mf_scheme_matcher._core_query(). Returns a much smaller,
        more precise candidate set than scanning the full bulk scheme list.
        """
        query = (query or '').strip()
        if not query:
            return []
        cache_key = f'inv:mf:search:{query.lower()}'
        cached = _redis.get(cache_key)
        if cached:
            return json.loads(cached)

        try:
            resp = requests.get(f'{MFAPI_BASE}/search', params={'q': query}, timeout=25)
            resp.raise_for_status()
            results = resp.json()
        except Exception as e:
            logger.warning('MFAPI search failed for "%s": %s', query, e)
            return []

        _redis.setex(cache_key, 86400, json.dumps(results))
        return results

    def get_isin_map(self) -> dict:
        cache_key = 'inv:mf:isin_map'
        cached = _redis.get(cache_key)
        if cached:
            return json.loads(cached)

        logger.info('Fetching MFAPI scheme list to build ISIN map')
        try:
            resp = requests.get(f'{MFAPI_BASE}', timeout=30)
            resp.raise_for_status()
            schemes = resp.json()
        except Exception as e:
            logger.error('MFAPI scheme list fetch failed: %s', e)
            return {}

        isin_map = {}
        for s in schemes:
            code = s.get('schemeCode')
            if s.get('isinGrowth'):
                isin_map[s['isinGrowth']] = code
            if s.get('isinDivReinvestment'):
                isin_map[s['isinDivReinvestment']] = code

        _redis.setex(cache_key, 86400, json.dumps(isin_map))
        logger.info('Built ISIN map with %d entries', len(isin_map))
        return isin_map

    def get_scheme_list(self) -> list:
        cache_key = 'inv:mf:scheme_list'
        cached = _redis.get(cache_key)
        if cached:
            return json.loads(cached)

        try:
            resp = requests.get(f'{MFAPI_BASE}', timeout=30)
            resp.raise_for_status()
            schemes = resp.json()
            _redis.setex(cache_key, 86400, json.dumps(schemes))
            return schemes
        except Exception as e:
            logger.error('MFAPI scheme list fetch failed: %s', e)
            return []

    def get_latest_nav(self, scheme_code: int) -> dict | None:
        cache_key = f'inv:mf:nav:{scheme_code}:latest'
        cached = _redis.get(cache_key)
        if cached:
            return json.loads(cached)

        try:
            resp = requests.get(f'{MFAPI_BASE}/{scheme_code}/latest', timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get('data'):
                _redis.setex(cache_key, 21600, json.dumps(data['data'][0]))
                return data['data'][0]
        except Exception as e:
            logger.warning('MFAPI latest NAV fetch failed for %s: %s', scheme_code, e)
        return None

    def get_nav_history(self, scheme_code: int) -> tuple[list, dict]:
        cache_key = f'inv:mf:nav:{scheme_code}:history'
        cached = _redis.get(cache_key)
        if cached:
            payload = json.loads(cached)
            return payload['data'], payload['meta']

        try:
            resp = requests.get(f'{MFAPI_BASE}/{scheme_code}', timeout=30)
            resp.raise_for_status()
            data = resp.json()
            nav_data = data.get('data', [])
            meta = data.get('meta', {})
            _redis.setex(cache_key, 86400, json.dumps({'data': nav_data, 'meta': meta}))
            return nav_data, meta
        except Exception as e:
            logger.error('MFAPI NAV history fetch failed for %s: %s', scheme_code, e)
        return [], {}

    def fetch_and_save_scheme(self, scheme_code: int, isin: str):
        from apps.investments.models import MutualFundScheme
        from django.utils import timezone

        nav_data, meta = self.get_nav_history(scheme_code)
        latest_nav = None
        nav_date = None
        if nav_data:
            latest = nav_data[0]
            latest_nav = float(latest.get('nav', 0))
            try:
                nav_date = datetime.strptime(latest['date'], '%d-%m-%Y').date()
            except Exception:
                pass

        # scheme_category comes as "Equity Scheme - Flexi Cap Fund" — split
        # into a broad category and the actual fund-strategy sub-category
        # (Large Cap / Flexi Cap / Index Fund / Momentum etc.) rather than
        # storing the whole compound string as one opaque "category".
        raw_category = meta.get('scheme_category', '') or ''
        if ' - ' in raw_category:
            category, sub_category = raw_category.split(' - ', 1)
        else:
            category, sub_category = raw_category, ''

        scheme, _ = MutualFundScheme.objects.update_or_create(
            isin=isin,
            defaults={
                'scheme_code': scheme_code,
                'scheme_name': meta.get('scheme_name', ''),
                'amc': meta.get('fund_house', ''),
                'category': category.strip(),
                'sub_category': sub_category.strip(),
                'scheme_type': meta.get('scheme_type', ''),
                'latest_nav': latest_nav,
                'nav_date': nav_date,
                'last_synced': timezone.now(),
            },
        )
        return scheme

    def sync_nav_history_to_db(self, scheme_code: int, isin: str):
        from apps.investments.models import MutualFundScheme, NAVHistory

        nav_data, meta = self.get_nav_history(scheme_code)
        if not nav_data:
            return 0

        try:
            scheme = MutualFundScheme.objects.get(isin=isin)
        except MutualFundScheme.DoesNotExist:
            scheme = self.fetch_and_save_scheme(scheme_code, isin)

        to_create = []
        for entry in nav_data:
            try:
                date = datetime.strptime(entry['date'], '%d-%m-%Y').date()
                nav = float(entry['nav'])
                to_create.append(NAVHistory(scheme=scheme, date=date, nav=nav))
            except Exception:
                continue

        NAVHistory.objects.bulk_create(to_create, ignore_conflicts=True)
        logger.info('Synced %d NAV records for %s', len(to_create), isin)
        return len(to_create)
