import logging
from datetime import date
from .base import CASData, AccountInfo, HoldingEntry, TransactionEntry, mask_pan as _mask_pan

logger = logging.getLogger('apps.investments')


def parse_cams_cas(pdf_path: str, password: str) -> CASData:
    """Parse CAMS CAS PDF using the casparser library."""
    try:
        import casparser
        data = casparser.read_cas_pdf(pdf_path, password=password, output='dict')
        return _normalize(data)
    except ImportError:
        raise RuntimeError('casparser library not installed. Run: pip install casparser')
    except Exception as e:
        raise ValueError(f'CAMS CAS parse error: {e}')


def _normalize(data: dict) -> CASData:
    investor = data.get('investor_info', {})
    account_info = AccountInfo(
        holder_name=investor.get('name', ''),
        pan_masked=_mask_pan(investor.get('pan', '')),
        pan_full=investor.get('pan', ''),
        email_masked=investor.get('email', ''),
        mobile_masked=investor.get('mobile', ''),
        depository='',
    )

    # Extract month/year from statement period
    period = data.get('statement_period', {})
    if period.get('to'):
        try:
            from datetime import datetime
            d = datetime.strptime(period['to'], '%Y-%m-%d')
            account_info.statement_month = d.month
            account_info.statement_year = d.year
        except (ValueError, TypeError):
            pass

    holdings = []
    transactions = []

    for folio in data.get('folios', []):
        for scheme in folio.get('schemes', []):
            isin = scheme.get('isin', '') or scheme.get('isin_growth', '')
            scheme_name = scheme.get('scheme', '')
            units = float(scheme.get('close', 0) or 0)
            nav = float(scheme.get('nav', 0) or 0)
            value = float(scheme.get('valuation', {}).get('value', 0) or 0)
            cost = float(scheme.get('valuation', {}).get('cost', 0) or 0)

            if units > 0 or value > 0:
                holdings.append(HoldingEntry(
                    isin=isin,
                    security_name=scheme_name,
                    asset_class='M',
                    quantity=units,
                    current_price=nav,
                    current_value=value,
                    total_cost=cost,
                    extra_data={
                        'units': units,
                        'nav': nav,
                        'folio_number': folio.get('folio', ''),
                        'plan_type': 'DIRECT' if 'direct' in scheme_name.lower() else 'REGULAR',
                        'option_type': 'GROWTH' if 'growth' in scheme_name.lower() else 'IDCW',
                    },
                ))

            for txn in scheme.get('transactions', []):
                try:
                    txn_date = _parse_date(txn.get('date', ''))
                except Exception:
                    continue

                txn_type_raw = txn.get('type', '').upper()
                txn_type = _map_txn_type(txn_type_raw)
                amount = float(txn.get('amount', 0) or 0)
                txn_units = float(txn.get('units', 0) or 0)
                txn_nav = float(txn.get('nav', 0) or 0)

                transactions.append(TransactionEntry(
                    isin=isin,
                    security_name=scheme_name,
                    transaction_date=txn_date,
                    order_no=txn.get('order_id', ''),
                    description=txn.get('description', txn_type_raw),
                    transaction_type=txn_type,
                    opening_balance=0,
                    debit=abs(txn_units) if txn_units < 0 else 0,
                    credit=txn_units if txn_units > 0 else 0,
                    closing_balance=0,
                    amount=abs(amount),
                    nav_at_transaction=txn_nav or None,
                ))

    return CASData(
        account_info=account_info,
        holdings=holdings,
        transactions=transactions,
        cas_type='CAMS',
    )


def _parse_date(date_str: str) -> date:
    from datetime import datetime
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Cannot parse date: {date_str}')


def _map_txn_type(raw: str) -> str:
    mapping = {
        'PURCHASE': 'PURCHASE',
        'REDEMPTION': 'SALE',
        'SIP': 'SIP',
        'SWP': 'SWP',
        'STP': 'STP',
        'DIVIDEND': 'DIVIDEND',
        'SWITCH': 'TRANSFER_OUT',
        'BONUS': 'BONUS',
    }
    for key, value in mapping.items():
        if key in raw:
            return value
    return 'OTHER'
