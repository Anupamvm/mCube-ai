from __future__ import annotations
import re
import logging
from datetime import datetime, date
import pdfplumber
from .base import CASData, AccountInfo, HoldingEntry, TransactionEntry

logger = logging.getLogger('apps.investments')

DATE_RE = re.compile(r'(\d{2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{4})')
ISIN_RE = re.compile(r'\b(IN[A-Z0-9]{10})\b')
AMOUNT_RE = re.compile(r'[\d,]+\.?\d*')
# NSDL masked PAN: 2 letters + 4-6 X + 1-3 alphanumeric + 1 digit + 1 letter
PAN_RE = re.compile(r'[A-Z]{2}X{4,6}[A-Z0-9]*[0-9][A-Z]\b')


def parse_nsdl_cas(pdf_path: str, password: str) -> CASData:
    """Parse NSDL e-CAS PDF and return normalized CASData."""
    try:
        pdf = pdfplumber.open(pdf_path, password=password)
    except Exception as e:
        raise ValueError(f'Cannot open PDF: {e}')

    pages_text = []
    for page in pdf.pages:
        pages_text.append(page.extract_text(layout=True) or '')
    pdf.close()

    full_text = '\n'.join(pages_text)

    account_info = _parse_account_info(full_text)
    holdings = _parse_holdings(full_text)
    transactions = _parse_transactions(full_text)

    return CASData(
        account_info=account_info,
        holdings=holdings,
        transactions=transactions,
        cas_type='NSDL',
    )


def _parse_account_info(text: str) -> AccountInfo:
    info = AccountInfo()
    info.depository = 'NSDL'

    # Statement period: "Statement for the period from 01-Mar-2026 to 31-Mar-2026"
    period_match = re.search(r'Statement for the period from\s+(\d{2}-\w{3}-\d{4})\s+to\s+(\d{2}-\w{3}-\d{4})', text)
    if period_match:
        try:
            d = datetime.strptime(period_match.group(2), '%d-%b-%Y')
            info.statement_month = d.month
            info.statement_year = d.year
        except ValueError:
            pass
    else:
        # Fallback: look for any month/year in header
        dates = DATE_RE.findall(text[:5000])
        for ds in reversed(dates):
            try:
                d = datetime.strptime(ds, '%d-%b-%Y')
                info.statement_month = d.month
                info.statement_year = d.year
                break
            except ValueError:
                continue

    # Holder name from "(PAN:AAXXXXXX5B)" pattern — name comes right before it
    pan_context = re.search(r'([A-Z][A-Z\s]{5,50})\s*\(PAN\s*:', text)
    if pan_context:
        info.holder_name = pan_context.group(1).strip().title()
    else:
        # Fallback: name after "NSDL ID: XXXXXXXXX\n"
        nsdl_id_match = re.search(r'NSDL ID:\s*\d+\s*\n\s*([A-Z][A-Z\s]+?)(?:\n|\r)', text)
        if nsdl_id_match:
            info.holder_name = nsdl_id_match.group(1).strip().title()

    # PAN masked (anywhere in text, not just first 3000 chars)
    # First try explicit "(PAN:AAXXXXXX5B)" form
    explicit_pan = re.search(r'\(PAN\s*:\s*([A-Z0-9X]{10})\)', text)
    if explicit_pan:
        info.pan_masked = explicit_pan.group(1)
    else:
        pan_matches = PAN_RE.findall(text)
        if pan_matches:
            info.pan_masked = pan_matches[0]

    # DP ID: "DP ID: IN300214"
    dp_id_match = re.search(r'DP\s+ID\s*:\s*(IN\d+)', text)
    if dp_id_match:
        info.dp_id = dp_id_match.group(1)

    # Client ID: "Client ID: 26147603"
    client_match = re.search(r'Client\s+ID\s*:\s*(\d+)', text)
    if client_match:
        info.client_id = client_match.group(1)

    # DP Name: the broker name (appears before "ACCOUNT HOLDER" block)
    dp_match = re.search(
        r'(KOTAK|HDFC|ICICI|SBI|ZERODHA|ANGEL|MOTILAL|AXIS|BAJAJ|IIFL|SHAREKHAN)\s+'
        r'(?:SECURITIES|BROKING|BANK|CAPITAL)\s*(?:LIMITED|LTD)?',
        text, re.IGNORECASE
    )
    if dp_match:
        info.dp_name = dp_match.group(0).strip()

    # Nominee status
    if re.search(r'Nominee.*Registered', text, re.IGNORECASE):
        info.nominee_registered = True
    elif re.search(r'Nominee.*Not.*Registered', text, re.IGNORECASE):
        info.nominee_registered = False

    # Account type
    if re.search(r'\bHUF\b', text[:8000]):
        info.account_type = 'HUF'

    return info


def _parse_float(s: str) -> float:
    """Parse Indian number format like 1,23,456.78"""
    try:
        return float(s.replace(',', '').strip())
    except (ValueError, AttributeError):
        return 0.0


# (regex_pattern, asset_class) for sections that appear after the equity section
_SECTION_PATTERNS = [
    (r'Mutual\s+Funds?\s*\(M\)', 'M'),
    (r'Preference\s+Shares?\s*\(P\)', 'P'),
    (r'Sovereign\s+Gold\s+Bonds?\s*\(SGB\)', 'SGB'),
    (r'Corporate\s+Bonds?\s*\(C\)', 'C'),
    (r'Government\s+Securities?\s*\(G\)', 'G'),
    (r'Mutual\s+Fund\s+Folios?\s*\(F\)', 'F'),
]
_TXN_START_RE = re.compile(r'\bISIN\s*:\s*IN[A-Z0-9]{10}\b')


def _parse_holdings(text: str) -> list[HoldingEntry]:
    """
    Anchor on the equity column header (only in actual holdings, not the
    portfolio composition summary table) then slice each section and parse it.
    """
    col_anchor = re.search(r'ISIN\s+Company Name\s+Face Value', text)
    if not col_anchor:
        return []

    holdings_text = text[col_anchor.start():]

    # Find all section markers (pattern, start_pos, end_pos, asset_class)
    sections_found: list[tuple[int, int, str]] = []
    for pattern, asset_class in _SECTION_PATTERNS:
        m = re.search(pattern, holdings_text)
        if m:
            sections_found.append((m.start(), m.end(), asset_class))
    sections_found.sort()

    txn_m = _TXN_START_RE.search(holdings_text)
    holdings_end = txn_m.start() if txn_m else len(holdings_text)

    # Equity: from col header to first section marker (or holdings end)
    equity_end = sections_found[0][0] if sections_found else holdings_end

    holdings: list[HoldingEntry] = []
    holdings.extend(_parse_holding_section(holdings_text[:equity_end], 'E'))

    for idx, (sec_start, sec_end, asset_class) in enumerate(sections_found):
        next_boundary = sections_found[idx + 1][0] if idx + 1 < len(sections_found) else holdings_end
        content = holdings_text[sec_end:next_boundary]
        if asset_class == 'F':
            holdings.extend(_parse_mf_folio_section(content))
        else:
            holdings.extend(_parse_holding_section(content, asset_class))

    # Aggregate multiple folios of the same ISIN (e.g. 4 SIP folios of same MF scheme)
    seen: dict[tuple, HoldingEntry] = {}
    for h in holdings:
        key = (h.isin, h.asset_class)
        if key not in seen:
            seen[key] = h
        else:
            ex = seen[key]
            ex.quantity += h.quantity
            ex.current_value += h.current_value
            if ex.total_cost is not None and h.total_cost is not None:
                ex.total_cost += h.total_cost
            ex.current_price = ex.current_value / ex.quantity if ex.quantity else 0

    return list(seen.values())


def _parse_holding_section(text: str, asset_class: str) -> list[HoldingEntry]:
    holdings = []
    lines = text.split('\n')

    for line in lines:
        line = line.strip()
        isin_match = ISIN_RE.search(line)
        if not isin_match:
            continue

        isin = isin_match.group(1)
        rest = line[isin_match.end():].strip()
        numbers = AMOUNT_RE.findall(rest)

        if len(numbers) < 2:
            continue

        floats = [_parse_float(n) for n in numbers]

        if asset_class == 'SGB':
            # SGB row: ISIN Issuer CouponRate DD Mon YYYY Units FaceValue MarketPrice Value
            # The date "DD-Mon-YYYY" is not parsed by AMOUNT_RE but "DD" is extracted from
            # the raw text because the date appears as "28-Jun-2030" and AMOUNT_RE extracts
            # ["2.50", "28", "2030", "600", "5091.00", "13914.62", "83487720.00"]
            # We want: units=floats[-4], market_price=floats[-2], value=floats[-1]
            quantity = floats[-4] if len(floats) >= 4 else (floats[0] if floats else 0)
            current_price = floats[-2] if len(floats) >= 2 else 0
            current_value = floats[-1] if floats else 0
            face_value = floats[-3] if len(floats) >= 3 else 0

            # Extract coupon rate from rest before first number (or from floats[0])
            coupon_rate = floats[0] if floats else 0

            # Maturity date from line
            maturity_match = re.search(r'(\d{2}-\w{3}-\d{4})', rest)
            maturity_date = maturity_match.group(1) if maturity_match else ''

            security_name = rest[:rest.find(numbers[0])].strip() if numbers else isin
            security_name = re.sub(r'^[\s,.\-]+|[\s,.\-]+$', '', security_name) or isin

            # Build a descriptive name from maturity date (issuer always "CENTRAL GOVERNMENT")
            security_name = f'Sovereign Gold Bond {maturity_date}' if maturity_date else (security_name or 'Sovereign Gold Bond')

            entry = HoldingEntry(
                isin=isin,
                security_name=security_name[:500],
                asset_class='SGB',
                quantity=quantity,
                current_price=current_price,
                current_value=current_value,
                extra_data={
                    'units': quantity,
                    'face_value_per_unit': face_value,
                    'coupon_rate': coupon_rate,
                    'maturity_date': maturity_date,
                    'market_price': current_price,
                },
            )
            holdings.append(entry)
            continue

        # Equity and MF: last 3 numbers are quantity, price, value
        if len(floats) >= 3:
            quantity = floats[-3]
            current_price = floats[-2]
            current_value = floats[-1]
        elif len(floats) == 2:
            quantity = floats[0]
            current_value = floats[-1]
            current_price = current_value / quantity if quantity else 0
        else:
            continue

        # Extract security name (text before first numeric token)
        name_end = rest.find(numbers[0]) if numbers else len(rest)
        security_name = rest[:name_end].strip()
        security_name = re.sub(r'^[\s\d,.\-]+|[\s,.\-]+$', '', security_name) or isin

        entry = HoldingEntry(
            isin=isin,
            security_name=security_name[:500],
            asset_class=asset_class,
            quantity=quantity,
            current_price=current_price,
            current_value=current_value,
        )

        if asset_class == 'M':
            entry.extra_data = {'units': quantity, 'nav': current_price}

        holdings.append(entry)

    return holdings


def _parse_mf_folio_section(text: str) -> list[HoldingEntry]:
    """
    Parse 'Mutual Fund Folios (F)' section which has 6 numeric columns per row:
    Units | AvgCostPerUnit | TotalCost | CurrentNAV | CurrentValue | UnrealisedGain
    Optionally preceded by a numeric Folio No. (making 7 tokens) or alphanumeric
    folio (making exactly 6 tokens).
    We use rightmost-6 to handle both cases uniformly.
    """
    holdings = []
    for line in text.split('\n'):
        line = line.strip()
        isin_match = ISIN_RE.search(line)
        if not isin_match:
            continue
        isin = isin_match.group(1)
        rest = line[isin_match.end():].strip()

        tokens = AMOUNT_RE.findall(rest)
        if len(tokens) < 6:
            continue

        # Rightmost 6 are always the data columns regardless of folio format
        data = [_parse_float(t) for t in tokens[-6:]]
        units, avg_cost, total_cost, nav, current_value, _ = data

        name_end = rest.find(tokens[0]) if tokens else len(rest)
        security_name = rest[:name_end].strip()
        security_name = re.sub(r'^[\s,.\-]+|[\s,.\-]+$', '', security_name) or isin

        holdings.append(HoldingEntry(
            isin=isin,
            security_name=security_name[:500],
            asset_class='M',  # MF folios are Mutual Funds
            quantity=units,
            current_price=nav,
            current_value=current_value,
            avg_cost_per_unit=avg_cost,
            total_cost=total_cost,
            extra_data={'units': units, 'nav': nav, 'folio_type': 'CAMS_KFINTECH'},
        ))
    return holdings


def _parse_transactions(text: str) -> list[TransactionEntry]:
    """
    Transaction blocks in NSDL CAS are headed by 'ISIN : INE040A01034 - HDFC BANK LIMITED'.
    Scan the entire text for these blocks directly (no end-marker needed because the
    doubled-character nav bars that appear on every page would falsely trigger end markers).
    """
    transactions = []

    # Find all ISIN : INxxxxxx - Security Name block headers
    isin_block_re = re.compile(r'ISIN\s*:\s*(IN[A-Z0-9]{10})\s*-\s*(.+?)(?=\n|$)')
    block_starts = list(isin_block_re.finditer(text))

    for idx, block_match in enumerate(block_starts):
        isin = block_match.group(1)
        security_name = block_match.group(2).strip()

        block_start = block_match.end()
        block_end = block_starts[idx + 1].start() if idx + 1 < len(block_starts) else block_start + 4000
        block_content = text[block_start:block_end]

        for line in block_content.split('\n'):
            line = line.strip()
            date_match = DATE_RE.search(line)
            if not date_match:
                continue

            try:
                txn_date = datetime.strptime(date_match.group(1), '%d-%b-%Y').date()
            except ValueError:
                continue

            numbers = AMOUNT_RE.findall(line)
            floats = [_parse_float(n) for n in numbers]

            order_match = re.search(r'\b(\d{8,20})\b', line)
            order_no = order_match.group(1) if order_match else ''

            description = re.sub(r'\d{2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{4}', '', line)
            description = re.sub(r'\b\d{8,20}\b', '', description)
            description = re.sub(r'[\d,]+\.?\d*', '', description)
            description = re.sub(r'\s+', ' ', description).strip()

            txn_type = _infer_transaction_type(description)

            # NSDL columns: Opening Balance | Debit | Credit | Closing Balance
            opening = floats[-4] if len(floats) >= 4 else 0
            debit = floats[-3] if len(floats) >= 3 else 0
            credit = floats[-2] if len(floats) >= 2 else 0
            closing = floats[-1] if len(floats) >= 1 else 0

            transactions.append(TransactionEntry(
                isin=isin,
                security_name=security_name[:500],
                transaction_date=txn_date,
                order_no=order_no,
                description=description[:500],
                transaction_type=txn_type,
                opening_balance=opening,
                debit=debit,
                credit=credit,
                closing_balance=closing,
            ))

    return transactions


def _infer_transaction_type(description: str) -> str:
    desc_upper = description.upper()
    if any(k in desc_upper for k in ['PLEDGE CLOSURE', 'UNPLEDGE']):
        return 'UNPLEDGE'
    if 'PLEDGE' in desc_upper:
        return 'PLEDGE'
    if any(k in desc_upper for k in ['PURCHASE', 'BUY']):
        return 'PURCHASE'
    if any(k in desc_upper for k in ['SALE', 'SELL', 'REDEMPTION']):
        return 'SALE'
    if 'TRANSFER' in desc_upper:
        return 'TRANSFER_IN' if 'IN' in desc_upper else 'TRANSFER_OUT'
    if 'BONUS' in desc_upper or 'SPLIT' in desc_upper:
        return 'BONUS'
    if 'DIVIDEND' in desc_upper:
        return 'DIVIDEND'
    if 'EDIS' in desc_upper or 'BLOCK' in desc_upper:
        return 'TRANSFER_OUT'
    return 'OTHER'
