"""
CSV Importers for Broker Trade History

Parses F&O trade history from CSV files:
- Kotak Neo: Gain/Loss CSV (Derivatives section)
- ICICI Breeze: FNO Portfolio CSV
"""

import csv
import io
import logging
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from django.db import transaction

from apps.brokers.models import BrokerContractPnL, CSVImportLog

logger = logging.getLogger(__name__)


# Symbol mapping for Breeze CSV (abbreviated to full symbol names)
BREEZE_SYMBOL_MAP = {
    'CNXBAN': 'BANKNIFTY',
    'HDFBAN': 'HDFCBANK',
    'NIFTY': 'NIFTY',
    'NIFTY50': 'NIFTY',
    'ICIBAN': 'ICICIBANK',
    'AXSBNK': 'AXISBANK',
    'SBIBNK': 'SBIN',
    'STABAN': 'SBIN',
    'KOTBNK': 'KOTAKBANK',
    'RELIND': 'RELIANCE',
    'INFTEC': 'INFY',
    'TATMOT': 'TATAMOTORS',
    'TATSTL': 'TATASTEEL',
    'HDFC': 'HDFC',
    'LT': 'LT',
    'TCS': 'TCS',
    'SUNPHA': 'SUNPHARMA',
    'TITIND': 'TITAN',
    'PERSYS': 'PERSISTENT',
    'BAJFI': 'BAJFINANCE',
    'JIOFIN': 'JIOFIN',
    'DIXTEC': 'DIXON',
    'ASIPAI': 'ASIANPAINT',
    'AVESUP': 'AUROPHARMA',
    'VARBEV': 'VBL',
}


def parse_decimal(value: str, default: Decimal = Decimal('0.00')) -> Decimal:
    """Parse a decimal value from string, handling commas and empty values."""
    if not value or value.strip() == '' or value.strip() == '-' or value.strip().upper() == 'NA':
        return default
    try:
        # Remove commas and parentheses (for negative values)
        cleaned = value.replace(',', '').replace('(', '-').replace(')', '').strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        logger.warning(f"Could not parse decimal: {value}")
        return default


def parse_int(value: str, default: int = 0) -> int:
    """Parse an integer value from string."""
    if not value or value.strip() == '' or value.strip() == '-' or value.strip().upper() == 'NA':
        return default
    try:
        cleaned = value.replace(',', '').strip()
        return int(float(cleaned))
    except (ValueError, TypeError):
        logger.warning(f"Could not parse int: {value}")
        return default


class KotakFNOImporter:
    """
    Parse Kotak Gain/Loss CSV - Derivatives section only.

    CSV Format (actual structure):
    - Rows 1-4: Client info header
    - Row 5: Empty
    - Row 6: Column headers
    - Row 7+: Data sections (Equity, Mutual Funds, ETF, Derivatives)
    - "Derivatives" section marker indicates start of F&O data

    Contract formats:
      - Futures: "BANKNIFTY 25NOV25 XX 0" (SYMBOL DDMMMYY XX 0)
      - Options: "NIFTY 02DEC25 CE 26850" (SYMBOL DDMMMYY CE/PE STRIKE)
    - Security Types: FUTSTK, FUTIDX, OPTIDX, OPTSTK
    """

    def __init__(self):
        self.batch_id = None
        self.errors = []
        self.records_created = 0
        self.records_updated = 0
        self.records_skipped = 0

    def parse_contract(self, script_name: str, security_type: str) -> Dict:
        """
        Parse Kotak contract string to extract symbol, expiry, strike, option_type.

        Examples:
        - "BANKNIFTY 25NOV25 XX 0" -> Futures
        - "NIFTY 02DEC25 CE 26850" -> Call Option
        - "RELIANCE 26DEC25 PE 1200" -> Put Option
        """
        result = {
            'symbol': '',
            'expiry_date': None,
            'strike_price': None,
            'option_type': '',
            'segment': 'FUTURES',
            'security_type': security_type,
        }

        if not script_name:
            return result

        parts = script_name.strip().split()
        if len(parts) < 2:
            result['symbol'] = script_name
            return result

        # First part is always the symbol
        result['symbol'] = parts[0]

        # Second part is the expiry date (DDMMMYY format)
        if len(parts) >= 2:
            try:
                expiry_str = parts[1].upper()
                # Handle formats: 25NOV25, 02DEC25
                result['expiry_date'] = datetime.strptime(expiry_str, '%d%b%y').date()
            except ValueError:
                logger.warning(f"Could not parse expiry date: {parts[1]}")

        # Determine if this is futures or options
        if security_type in ['FUTSTK', 'FUTIDX']:
            result['segment'] = 'FUTURES'
        elif security_type in ['OPTIDX', 'OPTSTK']:
            result['segment'] = 'OPTIONS'
            # Third part is CE/PE, fourth is strike
            if len(parts) >= 3:
                opt_type = parts[2].upper()
                if opt_type in ['CE', 'PE']:
                    result['option_type'] = opt_type
            if len(parts) >= 4:
                try:
                    result['strike_price'] = Decimal(parts[3])
                except (InvalidOperation, ValueError):
                    pass
        else:
            # Fallback: check if third part is CE/PE
            if len(parts) >= 3 and parts[2].upper() in ['CE', 'PE']:
                result['segment'] = 'OPTIONS'
                result['option_type'] = parts[2].upper()
                if len(parts) >= 4:
                    try:
                        result['strike_price'] = Decimal(parts[3])
                    except (InvalidOperation, ValueError):
                        pass
            elif len(parts) >= 3 and parts[2].upper() == 'XX':
                result['segment'] = 'FUTURES'

        return result

    def import_file(self, file_obj, user=None) -> Dict:
        """
        Import F&O data from Kotak Gain/Loss CSV file.

        Args:
            file_obj: File object or file path
            user: User performing the import

        Returns:
            dict with import results
        """
        self.batch_id = f"KOTAK_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.errors = []
        self.records_created = 0
        self.records_updated = 0
        self.records_skipped = 0

        # Get filename
        if hasattr(file_obj, 'name'):
            filename = file_obj.name
        else:
            filename = 'kotak_fno.csv'

        # Create import log
        import_log = CSVImportLog.objects.create(
            import_batch_id=self.batch_id,
            file_type='KOTAK_FNO',
            original_filename=filename,
            status='PROCESSING',
            imported_by=user,
        )

        try:
            # Read CSV content
            if hasattr(file_obj, 'read'):
                content = file_obj.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8-sig')  # Handle BOM
            else:
                with open(file_obj, 'r', encoding='utf-8-sig') as f:
                    content = f.read()

            # Parse CSV
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)

            logger.info(f"Read {len(rows)} rows from Kotak CSV")

            # Find the Derivatives section
            derivatives_start = -1
            in_derivatives = False

            for i, row in enumerate(rows):
                if not row or len(row) == 0:
                    continue

                first_cell = str(row[0]).strip().lower()

                # Look for "Derivatives" section marker
                if first_cell == 'derivatives':
                    derivatives_start = i + 1  # Data starts after the marker
                    in_derivatives = True
                    logger.info(f"Found 'Derivatives' section at row {i+1}")
                    continue

                # If we're past derivatives and hit another section, stop
                if in_derivatives and first_cell in ['', 'disclaimer']:
                    logger.info(f"End of Derivatives section at row {i+1}")
                    break

            if derivatives_start == -1:
                raise ValueError("Could not find 'Derivatives' section in the CSV. Make sure this is a Kotak Gain/Loss report.")

            # Process data rows from Derivatives section
            with transaction.atomic():
                for i in range(derivatives_start, len(rows)):
                    row = rows[i]

                    # Skip empty rows
                    if not row or len(row) < 5:
                        continue

                    script_name = str(row[0]).strip() if row[0] else ''

                    # Stop at empty row or disclaimer
                    if not script_name or script_name.lower() in ['', 'disclaimer']:
                        break

                    security_type = str(row[1]).strip() if len(row) > 1 else ''

                    # Only process derivatives (FUTSTK, FUTIDX, OPTIDX, OPTSTK)
                    if security_type not in ['FUTSTK', 'FUTIDX', 'OPTIDX', 'OPTSTK']:
                        self.records_skipped += 1
                        continue

                    try:
                        self._process_kotak_row(row)
                    except Exception as e:
                        error_msg = f"Row {i+1}: {str(e)}"
                        self.errors.append(error_msg)
                        logger.warning(error_msg)

            # Update import log
            import_log.records_created = self.records_created
            import_log.records_updated = self.records_updated
            import_log.records_skipped = self.records_skipped
            import_log.errors = self.errors
            import_log.status = 'SUCCESS' if not self.errors else 'PARTIAL'
            import_log.save()

            return {
                'success': True,
                'batch_id': self.batch_id,
                'records_created': self.records_created,
                'records_updated': self.records_updated,
                'records_skipped': self.records_skipped,
                'errors': self.errors,
            }

        except Exception as e:
            logger.exception(f"Error importing Kotak CSV: {e}")
            import_log.status = 'FAILED'
            import_log.errors = [str(e)]
            import_log.save()

            return {
                'success': False,
                'batch_id': self.batch_id,
                'error': str(e),
                'errors': [str(e)],
            }

    def _process_kotak_row(self, row: List[str]):
        """
        Process a single row from Kotak CSV.

        Column mapping (0-indexed):
        0: Script Name
        1: Security Type
        2: ISIN
        3: Quantity
        4: Buy Amt. (A)
        5: Sell Amt. (B)
        6: Intraday
        7: <1yr.
        8: >1yr.
        9: Total(T = B - A) - Gross P&L
        10: GST (C)
        11: Brokerage (D)
        12: Misc. (E)
        13: STT/CTT (S)
        14: Total (C+D+E+S)
        15: Net P&L (T-S)
        16: Gross P&L (T+(C+D+E))
        """
        script_name = str(row[0]).strip()
        security_type = str(row[1]).strip() if len(row) > 1 else ''

        # Parse contract details
        contract = self.parse_contract(script_name, security_type)

        # Parse numeric values with correct column indices
        quantity = parse_int(row[3] if len(row) > 3 else '')
        buy_amount = parse_decimal(row[4] if len(row) > 4 else '')
        sell_amount = parse_decimal(row[5] if len(row) > 5 else '')
        gross_pnl = parse_decimal(row[9] if len(row) > 9 else '')  # Total(T = B - A)
        gst = parse_decimal(row[10] if len(row) > 10 else '')
        brokerage = parse_decimal(row[11] if len(row) > 11 else '')
        misc_charges = parse_decimal(row[12] if len(row) > 12 else '')
        stt = parse_decimal(row[13] if len(row) > 13 else '')
        total_charges = parse_decimal(row[14] if len(row) > 14 else '')
        net_pnl = parse_decimal(row[15] if len(row) > 15 else '')

        # Create or update record
        obj, created = BrokerContractPnL.objects.update_or_create(
            broker='KOTAK',
            import_batch_id=self.batch_id,
            trading_symbol=script_name,
            defaults={
                'symbol': contract['symbol'],
                'segment': contract['segment'],
                'security_type': contract['security_type'],
                'expiry_date': contract['expiry_date'],
                'strike_price': contract['strike_price'],
                'option_type': contract['option_type'],
                'quantity': quantity,
                'buy_amount': buy_amount,
                'sell_amount': sell_amount,
                'gross_pnl': gross_pnl,
                'net_pnl': net_pnl,
                'gst': gst,
                'brokerage': brokerage,
                'stt': stt,
                'misc_charges': misc_charges,
                'total_charges': total_charges,
                'raw_data': {'row': row},
            }
        )

        if created:
            self.records_created += 1
        else:
            self.records_updated += 1

        logger.debug(f"{'Created' if created else 'Updated'} record for {script_name}: Net P&L = {net_pnl}")


class BreezeFNOImporter:
    """
    Parse Breeze FNO Portfolio CSV.

    CSV Format (actual structure):
    - Row 1: "Futures," section marker
    - Row 2: Headers - Contract,Trade Flow,Open Position Qty,...
    - Row 3+: Data rows

    Contract format: "FUT-HDFBAN-24-Feb-2026" or "OPT-NIFTY-24-Apr-2025-CE-22500"
    Contains: Realized P&L, Unrealized P&L per contract
    """

    def __init__(self):
        self.batch_id = None
        self.errors = []
        self.records_created = 0
        self.records_updated = 0
        self.records_skipped = 0

    def parse_contract(self, contract_str: str) -> Dict:
        """
        Parse Breeze contract string.

        Examples:
        - "FUT-HDFBAN-24-Feb-2026" -> HDFCBANK Futures Feb 2026
        - "FUT-CNXBAN-31-Jul-2025" -> BANKNIFTY Futures Jul 2025
        - "OPT-NIFTY-24-Apr-2025-CE-22500" -> NIFTY Call Option
        """
        result = {
            'symbol': '',
            'expiry_date': None,
            'strike_price': None,
            'option_type': '',
            'segment': 'FUTURES',
            'security_type': '',
        }

        if not contract_str:
            return result

        parts = contract_str.strip().split('-')
        if len(parts) < 4:
            result['symbol'] = contract_str
            return result

        # First part: FUT or OPT
        contract_type = parts[0].upper()
        if contract_type == 'FUT':
            result['segment'] = 'FUTURES'
            result['security_type'] = 'FUTIDX'  # Will be refined based on symbol
        elif contract_type == 'OPT':
            result['segment'] = 'OPTIONS'
            result['security_type'] = 'OPTIDX'  # Will be refined based on symbol

        # Second part: Symbol (may need mapping)
        raw_symbol = parts[1].upper()
        result['symbol'] = BREEZE_SYMBOL_MAP.get(raw_symbol, raw_symbol)

        # Refine security type based on symbol
        index_symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'CNXBAN']
        if result['symbol'] in index_symbols or raw_symbol in index_symbols:
            result['security_type'] = 'FUTIDX' if result['segment'] == 'FUTURES' else 'OPTIDX'
        else:
            result['security_type'] = 'FUTSTK' if result['segment'] == 'FUTURES' else 'OPTSTK'

        # Parse expiry date: DD-MMM-YYYY format
        # For FUT: FUT-SYMBOL-DD-MMM-YYYY
        # For OPT: OPT-SYMBOL-DD-MMM-YYYY-CE/PE-STRIKE
        try:
            if len(parts) >= 5:
                # parts[2] = day, parts[3] = month, parts[4] = year
                expiry_str = f"{parts[2]}-{parts[3]}-{parts[4]}"
                result['expiry_date'] = datetime.strptime(expiry_str, '%d-%b-%Y').date()

                # For options, parts[5] = CE/PE, parts[6] = strike
                if contract_type == 'OPT' and len(parts) >= 7:
                    result['option_type'] = parts[5].upper()
                    try:
                        result['strike_price'] = Decimal(parts[6])
                    except (InvalidOperation, ValueError):
                        pass
        except ValueError as e:
            logger.warning(f"Could not parse date from contract: {contract_str}, error: {e}")

        return result

    def import_file(self, file_obj, user=None) -> Dict:
        """
        Import F&O data from Breeze FNO Portfolio CSV file.

        Args:
            file_obj: File object or file path
            user: User performing the import

        Returns:
            dict with import results
        """
        self.batch_id = f"BREEZE_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.errors = []
        self.records_created = 0
        self.records_updated = 0
        self.records_skipped = 0

        # Get filename
        if hasattr(file_obj, 'name'):
            filename = file_obj.name
        else:
            filename = 'breeze_fno.csv'

        # Create import log
        import_log = CSVImportLog.objects.create(
            import_batch_id=self.batch_id,
            file_type='BREEZE_FNO',
            original_filename=filename,
            status='PROCESSING',
            imported_by=user,
        )

        try:
            # Read CSV content
            if hasattr(file_obj, 'read'):
                content = file_obj.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8-sig')  # Handle BOM
            else:
                with open(file_obj, 'r', encoding='utf-8-sig') as f:
                    content = f.read()

            # Parse CSV
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)

            logger.info(f"Read {len(rows)} rows from Breeze CSV")

            # Find header row (contains "Contract" column)
            header_row_idx = -1
            for i, row in enumerate(rows):
                if row and len(row) > 0:
                    first_cell = str(row[0]).strip().lower()
                    if first_cell == 'contract':
                        header_row_idx = i
                        logger.info(f"Found header row at index {i}")
                        break

            if header_row_idx == -1:
                raise ValueError("Could not find header row with 'Contract' column. Make sure this is a Breeze FNO Portfolio CSV.")

            # Process data rows
            with transaction.atomic():
                for i in range(header_row_idx + 1, len(rows)):
                    row = rows[i]

                    # Skip empty rows
                    if not row or len(row) < 3:
                        continue

                    contract = str(row[0]).strip() if row[0] else ''
                    if not contract:
                        continue

                    # Only process FUT and OPT contracts
                    if not contract.upper().startswith(('FUT-', 'OPT-')):
                        self.records_skipped += 1
                        continue

                    try:
                        self._process_breeze_row(row)
                    except Exception as e:
                        error_msg = f"Row {i+1}: {str(e)}"
                        self.errors.append(error_msg)
                        logger.warning(error_msg)

            # Update import log
            import_log.records_created = self.records_created
            import_log.records_updated = self.records_updated
            import_log.records_skipped = self.records_skipped
            import_log.errors = self.errors
            import_log.status = 'SUCCESS' if not self.errors else 'PARTIAL'
            import_log.save()

            return {
                'success': True,
                'batch_id': self.batch_id,
                'records_created': self.records_created,
                'records_updated': self.records_updated,
                'records_skipped': self.records_skipped,
                'errors': self.errors,
            }

        except Exception as e:
            logger.exception(f"Error importing Breeze CSV: {e}")
            import_log.status = 'FAILED'
            import_log.errors = [str(e)]
            import_log.save()

            return {
                'success': False,
                'batch_id': self.batch_id,
                'error': str(e),
                'errors': [str(e)],
            }

    def _process_breeze_row(self, row: List[str]):
        """
        Process a single row from Breeze CSV.

        Column mapping (0-indexed):
        0: Contract
        1: Trade Flow
        2: Open Position Qty
        3: Open Position Value
        4: Open Position Avg. Price
        5: LTP
        6: Profit/Loss Unrealized
        7: Profit/Loss Realized
        """
        contract_str = str(row[0]).strip()

        # Parse contract details
        contract = self.parse_contract(contract_str)

        # Parse numeric values
        open_qty = parse_int(row[2] if len(row) > 2 else '')
        open_value = parse_decimal(row[3] if len(row) > 3 else '')
        unrealized_pnl = parse_decimal(row[6] if len(row) > 6 else '')
        realized_pnl = parse_decimal(row[7] if len(row) > 7 else '')

        # Calculate gross/net P&L (sum of realized + unrealized)
        gross_pnl = realized_pnl + unrealized_pnl
        net_pnl = gross_pnl  # Breeze doesn't show charges in this CSV

        # Create or update record
        obj, created = BrokerContractPnL.objects.update_or_create(
            broker='ICICI',
            import_batch_id=self.batch_id,
            trading_symbol=contract_str,
            defaults={
                'symbol': contract['symbol'],
                'segment': contract['segment'],
                'security_type': contract['security_type'],
                'expiry_date': contract['expiry_date'],
                'strike_price': contract['strike_price'],
                'option_type': contract['option_type'],
                'quantity': open_qty,
                'buy_amount': open_value,
                'sell_amount': Decimal('0.00'),
                'gross_pnl': gross_pnl,
                'net_pnl': net_pnl,
                'realized_pnl': realized_pnl,
                'unrealized_pnl': unrealized_pnl,
                'raw_data': {'row': row},
            }
        )

        if created:
            self.records_created += 1
        else:
            self.records_updated += 1

        logger.debug(f"{'Created' if created else 'Updated'} record for {contract_str}: Realized={realized_pnl}, Unrealized={unrealized_pnl}")


def delete_import_batch(batch_id: str) -> Dict:
    """
    Delete all records associated with an import batch.

    Args:
        batch_id: The import batch ID to delete

    Returns:
        dict with deletion results
    """
    try:
        with transaction.atomic():
            # Delete contract P&L records
            deleted_pnl = BrokerContractPnL.objects.filter(import_batch_id=batch_id).delete()[0]

            # Delete import log
            deleted_log = CSVImportLog.objects.filter(import_batch_id=batch_id).delete()[0]

            return {
                'success': True,
                'batch_id': batch_id,
                'records_deleted': deleted_pnl,
                'logs_deleted': deleted_log,
            }

    except Exception as e:
        logger.exception(f"Error deleting batch {batch_id}: {e}")
        return {
            'success': False,
            'batch_id': batch_id,
            'error': str(e),
        }
