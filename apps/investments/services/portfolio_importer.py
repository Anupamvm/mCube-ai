from __future__ import annotations
import csv
import io
import re
import logging
from decimal import Decimal
from datetime import date, datetime

logger = logging.getLogger('apps.investments')

_PURCHASE_DATE_FORMATS = ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%b-%Y', '%d %b %Y')


def _parse_purchase_date(raw: str):
    raw = (raw or '').strip()
    if not raw:
        return None
    for fmt in _PURCHASE_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _to_float(val) -> float:
    """Parse numbers including (parens) as negative and '+ / -' prefixed strings."""
    if val is None:
        return 0.0
    s = str(val).strip()
    if not s or s in ('-', '+', '--', 'n/a', 'nil', 'na'):
        return 0.0
    # Parentheses format: (5.21) → -5.21
    negative = s.startswith('(') and s.endswith(')')
    s = s.strip('()').replace(',', '').strip()
    # Leading sign with optional space: "- 2.10", "+ 0.20", "-69835.98"
    m = re.match(r'^([+\-])\s*(.+)$', s)
    if m:
        negative = m.group(1) == '-'
        s = m.group(2)
    try:
        n = float(s)
        return -n if negative else n
    except (ValueError, TypeError):
        return 0.0


def _detect_format(raw_bytes: bytes, filename: str) -> str:
    """Return 'tsv', 'csv', 'xlsx', or 'xls'."""
    lower = filename.lower()
    if lower.endswith('.xlsx'):
        return 'xlsx'
    if lower.endswith('.csv'):
        return 'csv'
    if lower.endswith('.xls'):
        # Real binary XLS starts with D0 CF magic bytes
        if raw_bytes[:2] == b'\xD0\xCF':
            return 'xls'
        # Kotak / broker exports are TSV masquerading as .xls
        return 'tsv'
    # Sniff from content
    try:
        sample = raw_bytes[:512].decode('utf-8-sig', errors='replace')
        if '\t' in sample.split('\n')[0]:
            return 'tsv'
    except Exception:
        pass
    return 'csv'


def _read_rows(raw_bytes: bytes, filename: str) -> list[dict]:
    """Parse file bytes into a list of header→value dicts."""
    fmt = _detect_format(raw_bytes, filename)

    if fmt == 'xlsx':
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return []
        headers = [str(c or '').strip() for c in all_rows[0]]
        return [
            {h: str(v if v is not None else '').strip() for h, v in zip(headers, row)}
            for row in all_rows[1:]
            if any(v is not None and str(v).strip() for v in row)
        ]

    if fmt == 'xls':
        import xlrd
        wb = xlrd.open_workbook(file_contents=raw_bytes)
        ws = wb.sheet_by_index(0)
        if ws.nrows == 0:
            return []
        headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
        result = []
        for r in range(1, ws.nrows):
            row = {headers[c]: str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)}
            if any(v for v in row.values()):
                result.append(row)
        return result

    delimiter = '\t' if fmt == 'tsv' else ','
    text = raw_bytes.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [
        {k: (v or '').strip() for k, v in row.items() if k}
        for row in reader
        if any((v or '').strip() for v in row.values())
    ]


# Flexible column-name synonyms — first match wins
_ALIASES: dict[str, list[str]] = {
    'isin':          ['isin code', 'isin', 'isin_code', 'scrip isin'],
    'name':          ['company name', 'security name', 'scrip name', 'stock name', 'script name',
                      'name', 'description'],
    'symbol':        ['stock symbol', 'symbol', 'scrip', 'ticker', 'nse symbol'],
    'security_type': ['security type', 'asset type', 'instrument type', 'type'],
    'quantity':      ['qty', 'quantity', 'shares', 'units', 'balance', 'no. of shares', 'holding qty'],
    'avg_cost':      ['average cost price', 'avg cost price', 'avg cost', 'avg unit cost',
                      'purchase_price', 'avg price', 'cost price', 'average price'],
    'current_price': ['current market price', 'current price', 'ltp', 'market price', 'nav',
                      'close price', 'closing price'],
    'invested_val':  ['invested value', 'value at cost', 'cost value', 'invested_value',
                      'purchase value', 'cost amount', 'book value'],
    'current_val':   ['value at market price', 'current value', 'market value',
                      'present value', 'market amount', 'mkt value'],
    'purchase_date': ['purchase_date', 'buy date', 'date of purchase', 'date'],
}

# Security Type values from broker CSVs → ProductType
_SECURITY_TYPE_TO_PRODUCT_TYPE = {
    'equity stock': 'EQUITY',
    'etf':          'EQUITY',
    'bonds':        'BOND',   # may be upgraded to SGB below
    'nsederv':      None,     # derivatives — skip
}


_MISSING = object()


def _resolve_product_type(security_type_raw: str, isin: str, name: str) -> str | None:
    """Map raw Security Type string to ProductType. Returns None to skip the row."""
    st = security_type_raw.lower().strip()
    mapped = _SECURITY_TYPE_TO_PRODUCT_TYPE.get(st, _MISSING)
    if mapped is _MISSING:
        # Unknown type — skip if looks like derivative, otherwise treat as equity
        return None if ('deriv' in st or 'fut' in st or 'opt' in st) else 'EQUITY'
    if mapped is None:
        return None  # explicit skip (NSEDERV etc.)
    if mapped == 'BOND':
        # SGBs: ISIN starts with IN002, or name contains SGB / Sovereign Gold
        if (isin.startswith('IN002') or 'sgb' in name.lower()
                or 'sovereign gold' in name.lower()):
            return 'SGB'
    return mapped


def _match_col(header_list: list[str], key: str) -> str | None:
    lower_map = {h.lower().strip(): h for h in header_list}
    for alias in _ALIASES.get(key, [key]):
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    return None


def clear_csv_products(account) -> int:
    """Delete all CSV-imported products from an account. Returns count deleted."""
    from apps.investments.models import InvestmentProduct, DataSource
    qs = InvestmentProduct.objects.filter(
        investment_account=account,
        data_source=DataSource.CSV,
    )
    count, _ = qs.delete()
    logger.info('Cleared %d CSV products from account %s', count, account)
    return count


def import_portfolio_file(account, raw_bytes: bytes, filename: str,
                          clear_existing: bool = False, cas_upload=None) -> dict:
    """
    Parse an equity portfolio export and upsert InvestmentProduct records.

    Handles:
    - Kotak / ICICIdirect / CDSL TSV exported as .xls
    - Standard .xlsx / .csv equity portfolio exports
    - Parentheses-as-negative number format
    - Duplicate detection via ISIN (primary) or symbol (fallback)
    - Security type mapping: EQUITY STOCK / ETF → EQUITY, BONDS → BOND/SGB, NSEDERV → skipped

    Returns dict: {rows_read, created, updated, skipped, errors, cleared}
    """
    from apps.investments.models import InvestmentProduct, DataSource

    cleared = 0
    if clear_existing:
        cleared = clear_csv_products(account)

    rows = _read_rows(raw_bytes, filename)
    if not rows:
        raise ValueError('No data rows found. Check the file format.')

    headers = list(rows[0].keys())
    col = {key: _match_col(headers, key) for key in _ALIASES}

    if not col['isin'] and not col['symbol']:
        raise ValueError(
            f'Cannot find ISIN or Symbol column. Headers detected: {headers}'
        )

    created = updated = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(rows, start=2):
        try:
            isin = (row.get(col['isin']) or '') if col['isin'] else ''
            isin = isin.strip().upper()
            name = ((row.get(col['name']) or '') if col['name'] else '').strip()
            symbol = ((row.get(col['symbol']) or '') if col['symbol'] else '').strip().upper()
            sec_type_raw = ((row.get(col['security_type']) or '') if col['security_type'] else '').strip()

            if not isin and not symbol:
                skipped += 1
                continue

            # Determine product type; None means skip (e.g. NSEDERV derivatives)
            if sec_type_raw:
                product_type = _resolve_product_type(sec_type_raw, isin, name)
                if product_type is None:
                    skipped += 1
                    continue
            else:
                product_type = 'EQUITY'

            qty = _to_float(row.get(col['quantity'])) if col['quantity'] else 0.0
            avg_cost = _to_float(row.get(col['avg_cost'])) if col['avg_cost'] else 0.0
            cur_price = _to_float(row.get(col['current_price'])) if col['current_price'] else 0.0
            inv_val = _to_float(row.get(col['invested_val'])) if col['invested_val'] else 0.0
            cur_val = _to_float(row.get(col['current_val'])) if col['current_val'] else 0.0
            purchase_date = _parse_purchase_date(row.get(col['purchase_date'])) if col['purchase_date'] else None

            # Compute from quantity × price when aggregate columns not present
            if not inv_val and qty and avg_cost:
                inv_val = round(qty * avg_cost, 2)
            if not cur_val and qty and cur_price:
                cur_val = round(qty * cur_price, 2)

            display_name = name or symbol or isin
            extra: dict = {}
            if symbol:
                extra['symbol'] = symbol
            if qty:
                extra['shares'] = qty
            if avg_cost:
                extra['avg_cost_per_unit'] = avg_cost
            if cur_price:
                extra['current_price'] = cur_price

            common_fields = {
                'product_type': product_type,
                'name': display_name,
                'data_source': DataSource.CSV,
                'is_active': True,
                'invested_value': Decimal(str(round(inv_val, 2))),
                'current_value': Decimal(str(round(cur_val, 2))),
                'as_of_date': date.today(),
                'extra_data': extra,
                'source_upload': cas_upload,
            }

            if isin:
                # Lookup by ISIN only so product_type gets corrected on re-upload
                existing = InvestmentProduct.objects.filter(
                    investment_account=account,
                    isin=isin,
                ).first()
                if existing:
                    for k, v in common_fields.items():
                        setattr(existing, k, v)
                    existing.save()
                    product = existing
                    was_created = False
                else:
                    product = InvestmentProduct.objects.create(
                        investment_account=account,
                        isin=isin,
                        **common_fields,
                    )
                    was_created = True
            else:
                # No ISIN: match by symbol in extra_data
                existing = InvestmentProduct.objects.filter(
                    investment_account=account,
                    isin='',
                    extra_data__symbol=symbol,
                ).first()
                if existing:
                    for k, v in common_fields.items():
                        setattr(existing, k, v)
                    existing.save()
                    product = existing
                    was_created = False
                else:
                    product = InvestmentProduct.objects.create(
                        investment_account=account,
                        isin='',
                        **common_fields,
                    )
                    was_created = True

            # Preserve the earliest known purchase date — never overwrite on re-upload.
            if purchase_date and not product.investment_date:
                product.investment_date = purchase_date
                product.save(update_fields=['investment_date'])

            if was_created:
                created += 1
            else:
                updated += 1

        except Exception as e:
            errors.append(f'Row {i}: {e}')
            logger.warning('Portfolio import row %d error: %s', i, e)

    logger.info(
        'Portfolio import [%s]: cleared=%d, %d created, %d updated, %d skipped, %d errors',
        filename, cleared, created, updated, skipped, len(errors),
    )
    return {
        'rows_read': len(rows),
        'cleared': cleared,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
    }
