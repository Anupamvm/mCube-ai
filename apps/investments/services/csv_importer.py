import csv
import io
import logging
from datetime import datetime
from decimal import Decimal
from apps.investments.models import InvestmentAccount, InvestmentProduct, DataSource

logger = logging.getLogger('apps.investments')


REQUIRED_COLUMNS = {'symbol', 'shares'}
OPTIONAL_COLUMNS = {'isin', 'purchase_date', 'purchase_price', 'name'}


def import_equity_csv(account: InvestmentAccount, csv_content: str) -> dict:
    """
    Parse equity portfolio CSV and create/update InvestmentProduct records.
    Expected CSV columns: symbol, shares[, isin, purchase_date, purchase_price, name]
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    headers = {h.lower().strip() for h in (reader.fieldnames or [])}

    if not REQUIRED_COLUMNS.issubset(headers):
        missing = REQUIRED_COLUMNS - headers
        raise ValueError(f'CSV missing required columns: {missing}. Found: {headers}')

    created = 0
    updated = 0
    errors = []

    for i, row in enumerate(reader, start=2):
        try:
            row = {k.lower().strip(): v.strip() for k, v in row.items() if k}
            symbol = row.get('symbol', '').upper()
            isin = row.get('isin', '')
            shares = float(row.get('shares', 0))
            purchase_price = float(row.get('purchase_price', 0) or 0)
            name = row.get('name', '') or symbol
            purchase_date_str = row.get('purchase_date', '')

            if not symbol or not shares:
                continue

            purchase_date = None
            if purchase_date_str:
                for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                    try:
                        purchase_date = datetime.strptime(purchase_date_str, fmt).date()
                        break
                    except ValueError:
                        continue

            invested = round(shares * purchase_price, 2) if purchase_price else 0

            extra_data = {
                'symbol': symbol,
                'shares': shares,
                'avg_purchase_price': purchase_price,
                'exchange': 'NSE',
            }
            if purchase_date:
                extra_data['purchase_date'] = purchase_date.isoformat()

            product, created_flag = InvestmentProduct.objects.update_or_create(
                investment_account=account,
                product_type='EQUITY',
                isin=isin or '',
                extra_data__symbol=symbol,
                defaults={
                    'name': name or symbol,
                    'isin': isin or '',
                    'data_source': DataSource.CSV,
                    'invested_value': Decimal(str(invested)),
                    'current_value': Decimal(str(invested)),
                    'extra_data': extra_data,
                    'is_active': True,
                },
            )

            if purchase_date and not product.investment_date:
                product.investment_date = purchase_date
                product.save(update_fields=['investment_date'])

            if created_flag:
                created += 1
            else:
                updated += 1

        except Exception as e:
            errors.append(f'Row {i}: {e}')
            logger.warning('CSV import error row %d: %s', i, e)

    logger.info('CSV import complete: %d created, %d updated, %d errors', created, updated, len(errors))
    return {'created': created, 'updated': updated, 'errors': errors}
