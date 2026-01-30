"""
Financial Year Trade Analytics Service

Fetches historical trade data from broker APIs for the current Indian Financial Year
and calculates monthly P&L performance for Futures and Options separately.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from django.db import models, transaction
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncMonth
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_financial_year_dates() -> Tuple[date, date]:
    """
    Get the start and end dates of current Indian financial year.
    FY runs from April 1 to March 31.
    """
    today = date.today()
    if today.month >= 4:
        fy_start = date(today.year, 4, 1)
        fy_end = date(today.year + 1, 3, 31)
    else:
        fy_start = date(today.year - 1, 4, 1)
        fy_end = date(today.year, 3, 31)

    # Don't go beyond today
    fy_end = min(fy_end, today)

    return fy_start, fy_end


def get_fy_label() -> str:
    """Get FY label like 'FY 2024-25'."""
    fy_start, _ = get_financial_year_dates()
    return f"FY {fy_start.year}-{str(fy_start.year + 1)[-2:]}"


class FYTradeAnalytics:
    """
    Service to fetch and analyze FY trade data from broker APIs.
    """

    def __init__(self):
        self.fy_start, self.fy_end = get_financial_year_dates()

    def sync_fy_trades_from_brokers(self, clear_existing: bool = False) -> Dict:
        """
        Sync all FY trades from both broker APIs to BrokerTradeHistory.

        Args:
            clear_existing: If True, clears existing trades before sync

        Returns:
            dict: Summary with counts and errors
        """
        from apps.accounts.models import BrokerAccount
        from apps.brokers.models import BrokerTradeHistory
        from apps.core.constants import BROKER_KOTAK, BROKER_ICICI

        result = {
            'success': True,
            'fy_label': get_fy_label(),
            'fy_start': self.fy_start.strftime('%Y-%m-%d'),
            'fy_end': self.fy_end.strftime('%Y-%m-%d'),
            'accounts': [],
            'total_trades_synced': 0,
            'errors': []
        }

        try:
            # Optionally clear existing
            if clear_existing:
                deleted = BrokerTradeHistory.objects.filter(
                    trade_date__gte=self.fy_start,
                    trade_date__lte=self.fy_end
                ).delete()[0]
                logger.info(f"Cleared {deleted} existing FY trades")

            # Get active accounts
            accounts = BrokerAccount.objects.filter(is_active=True)

            for account in accounts:
                account_result = {
                    'account_name': account.account_name,
                    'broker': account.get_broker_display(),
                    'trades_synced': 0,
                    'errors': []
                }

                try:
                    if account.broker == BROKER_ICICI:
                        # Check Breeze session first
                        from apps.brokers.utils.auth_manager import get_credentials, is_session_valid_breeze
                        creds = get_credentials('breeze')
                        if not creds or not is_session_valid_breeze(creds):
                            account_result['errors'].append('Breeze session expired. Please login at /brokers/breeze/login/')
                            account_result['auth_required'] = True
                            result['errors'].append(f'Breeze session expired for {account.account_name}')
                            continue

                        # Breeze supports date range
                        synced = self._sync_breeze_fy_trades(account)
                    elif account.broker == BROKER_KOTAK:
                        # Neo returns all available trades with historical dates
                        synced = self._sync_neo_trades(account)
                    else:
                        account_result['errors'].append(f'Unknown broker: {account.broker}')
                        continue

                    account_result['trades_synced'] = synced
                    result['total_trades_synced'] += synced

                except Exception as e:
                    error_msg = f"Error syncing {account.broker}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    account_result['errors'].append(error_msg)
                    result['errors'].append(error_msg)

                result['accounts'].append(account_result)

            return result

        except Exception as e:
            logger.error(f"Fatal error in sync_fy_trades: {e}", exc_info=True)
            result['success'] = False
            result['errors'].append(str(e))
            return result

    def _sync_breeze_fy_trades(self, account) -> int:
        """
        Sync FY trades from ICICI Breeze API.

        NOTE: The Breeze get_trade_list API may only return same-day trades.
        Historical trades may require:
        1. Daily sync during market hours
        2. Manual import from Breeze portal Contract Notes

        Fetches in monthly chunks to test API behavior.
        Tries native trade_list API first, falls back to order filtering.
        """
        from apps.brokers.integrations.breeze import get_trade_list, get_trade_list_via_orders
        from apps.brokers.models import BrokerTradeHistory

        logger.info(f"=== STARTING BREEZE FY TRADES SYNC ===")
        logger.info(f"FY Period: {self.fy_start} to {self.fy_end}")

        total_synced = 0

        # First, test today's date to verify API is working
        today = date.today()
        logger.info(f"=== Testing Breeze API with today's date: {today} ===")

        today_result = get_trade_list(
            from_date=today.strftime('%Y-%m-%d'),
            to_date=today.strftime('%Y-%m-%d'),
            exchange_code='NFO'
        )
        logger.info(f"Today's trades result: success={today_result.get('success')}, "
                   f"trades_count={len(today_result.get('trades', []))}, "
                   f"error={today_result.get('error')}, message={today_result.get('message')}")

        if today_result.get('success'):
            for trade in today_result.get('trades', []):
                saved = self._save_trade(account, trade, 'ICICI')
                if saved:
                    total_synced += 1
            logger.info(f"Saved {total_synced} trades from today")

        # Now try historical dates (monthly chunks)
        current_date = self.fy_start

        while current_date <= self.fy_end:
            # Skip today since we already processed it
            if current_date == today:
                if current_date.month == 12:
                    current_date = date(current_date.year + 1, 1, 1)
                else:
                    current_date = date(current_date.year, current_date.month + 1, 1)
                continue

            # Calculate month end
            if current_date.month == 12:
                month_end = date(current_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(current_date.year, current_date.month + 1, 1) - timedelta(days=1)

            month_end = min(month_end, self.fy_end)

            # Skip if this month is in the future
            if current_date > today:
                break

            logger.info(f"=== Fetching Breeze trades: {current_date} to {month_end} ===")

            # Try native trade list API first
            nfo_result = get_trade_list(
                from_date=current_date.strftime('%Y-%m-%d'),
                to_date=month_end.strftime('%Y-%m-%d'),
                exchange_code='NFO'
            )

            logger.info(f"Native get_trade_list result: success={nfo_result.get('success')}, "
                       f"trades_count={len(nfo_result.get('trades', []))}, "
                       f"error={nfo_result.get('error')}, message={nfo_result.get('message')}")

            # If native API returns no trades, try fallback via orders
            if nfo_result.get('success') and len(nfo_result.get('trades', [])) == 0:
                logger.info(f"Native trade list empty, trying order filtering fallback...")
                nfo_result = get_trade_list_via_orders(
                    from_date=current_date.strftime('%Y-%m-%d'),
                    to_date=month_end.strftime('%Y-%m-%d'),
                    exchange_code='NFO'
                )
                logger.info(f"Fallback get_trade_list_via_orders result: success={nfo_result.get('success')}, "
                           f"trades_count={len(nfo_result.get('trades', []))}, "
                           f"error={nfo_result.get('error')}")

            if nfo_result.get('success'):
                trades = nfo_result.get('trades', [])
                logger.info(f"Got {len(trades)} trades for {current_date} to {month_end}")
                if trades:
                    logger.info(f"First trade sample: {trades[0]}")
                for trade in trades:
                    saved = self._save_trade(account, trade, 'ICICI')
                    if saved:
                        total_synced += 1
            else:
                logger.warning(f"Failed to fetch NFO trades: {nfo_result.get('error')}")

            # Move to next month
            if current_date.month == 12:
                current_date = date(current_date.year + 1, 1, 1)
            else:
                current_date = date(current_date.year, current_date.month + 1, 1)

        logger.info(f"=== BREEZE SYNC COMPLETE: {total_synced} total trades synced ===")

        if total_synced == 0:
            logger.warning(
                "NOTE: Breeze get_trade_list API may only support same-day trades. "
                "For historical FY data, consider:\n"
                "1. Running sync daily during market hours\n"
                "2. Downloading Contract Notes from Breeze portal and importing manually\n"
                "3. Using a different Breeze API endpoint if available"
            )

        return total_synced

    def _sync_neo_trades(self, account) -> int:
        """
        Sync trades from Kotak Neo API.

        The Neo trade_report() API returns all available trades with their
        fill dates (flDt field), not just today's trades.
        """
        from apps.brokers.integrations.kotak_neo import get_trade_book

        total_synced = 0

        result = get_trade_book()

        if result.get('success'):
            for trade in result.get('trades', []):
                # trade_date is now properly parsed from flDt field in get_trade_book()
                # Only sync trades within FY date range
                trade_date = trade.get('trade_date')
                if trade_date and self.fy_start <= trade_date <= self.fy_end:
                    saved = self._save_trade(account, trade, 'KOTAK')
                    if saved:
                        total_synced += 1
        else:
            logger.warning(f"Failed to fetch Neo trades: {result.get('error')}")

        logger.info(f"Neo sync complete: {total_synced} trades")
        return total_synced

    def _save_trade(self, account, trade_data: Dict, broker: str) -> bool:
        """
        Save a trade to BrokerTradeHistory with deduplication.
        Uses update_or_create to handle existing records (updates price if it was 0).
        """
        from apps.brokers.models import BrokerTradeHistory

        try:
            # Log incoming trade data for debugging
            logger.debug(f"Saving trade data: {trade_data}")

            trade_id = trade_data.get('trade_id', '')
            order_id = trade_data.get('order_id', '')

            # Generate unique key for dedup
            if not trade_id:
                trade_id = f"{order_id}_{trade_data.get('trade_datetime', '')}"

            # Parse trade date - try multiple sources
            trade_date = trade_data.get('trade_date')
            trade_time = trade_data.get('trade_time')
            trade_datetime = trade_data.get('trade_datetime')

            # If trade_date is a string, parse it
            if isinstance(trade_date, str):
                try:
                    trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        trade_date = datetime.strptime(trade_date, '%d-%b-%Y').date()
                    except ValueError:
                        trade_date = None
            # If trade_date is a datetime, extract date
            elif hasattr(trade_date, 'date') and callable(getattr(trade_date, 'date', None)):
                trade_date = trade_date.date()

            # If still no trade_date, try to extract from trade_datetime
            if not trade_date and trade_datetime:
                if hasattr(trade_datetime, 'date') and callable(getattr(trade_datetime, 'date', None)):
                    trade_date = trade_datetime.date()
                    if not trade_time and hasattr(trade_datetime, 'time'):
                        trade_time = trade_datetime.time()
                elif isinstance(trade_datetime, str):
                    # Try to parse datetime string
                    for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%d-%b-%Y %H:%M:%S']:
                        try:
                            dt = datetime.strptime(trade_datetime[:19], fmt)
                            trade_date = dt.date()
                            trade_time = dt.time()
                            break
                        except ValueError:
                            continue

            # Final fallback - use today's date if still no date
            if not trade_date:
                logger.warning(f"Could not parse trade_date from trade_data, using today: {trade_data}")
                trade_date = date.today()

            # Parse trade time from trade_datetime if not already set
            if not trade_time and trade_datetime:
                if hasattr(trade_datetime, 'time') and callable(getattr(trade_datetime, 'time', None)):
                    trade_time = trade_datetime.time()

            # Determine instrument type (FUTURES or OPTIONS)
            trading_symbol = trade_data.get('trading_symbol', '') or trade_data.get('symbol', '')
            option_type = trade_data.get('option_type', '')

            # Parse strike price
            strike_price = trade_data.get('strike_price')
            if strike_price:
                try:
                    strike_price = Decimal(str(strike_price))
                except:
                    strike_price = None

            # Parse expiry date
            expiry_date = trade_data.get('expiry_date')
            if expiry_date and isinstance(expiry_date, str):
                try:
                    expiry_date = datetime.strptime(expiry_date, '%d-%b-%Y').date()
                except:
                    try:
                        expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                    except:
                        expiry_date = None

            # Create trade record
            symbol = trade_data.get('symbol', trading_symbol.split()[0] if trading_symbol else '')
            transaction_type = trade_data.get('transaction_type', 'BUY').upper()
            quantity = int(trade_data.get('quantity', 0))
            price_value = trade_data.get('price', 0)
            price = Decimal(str(price_value)) if price_value else Decimal('0')

            logger.info(f"Saving trade: {symbol} {transaction_type} {quantity}@{price} on {trade_date}")

            # Store raw_data for debugging (remove datetime objects which aren't JSON serializable)
            raw_data = trade_data.get('raw_data', {})
            if not raw_data:
                # If no raw_data provided, store the parsed trade_data (excluding non-serializable)
                raw_data = {k: str(v) if hasattr(v, 'isoformat') else v
                           for k, v in trade_data.items() if k != 'raw_data'}

            # Use update_or_create to handle existing records (updates price if was 0)
            # Unique constraint is on (broker, trade_id, trade_date)
            obj, created = BrokerTradeHistory.objects.update_or_create(
                broker=broker,
                trade_id=trade_id,
                trade_date=trade_date,
                defaults={
                    'account': account,
                    'order_id': order_id or '',
                    'symbol': symbol,
                    'trading_symbol': trading_symbol,
                    'segment': trade_data.get('exchange', 'NFO'),
                    'trade_type': transaction_type,
                    'product_type': trade_data.get('product', 'NRML'),
                    'quantity': quantity,
                    'price': price,
                    'trade_time': trade_time,
                    'expiry_date': expiry_date,
                    'strike_price': strike_price,
                    'option_type': option_type,
                    'raw_data': raw_data,
                }
            )

            action = "Created" if created else "Updated"
            logger.info(f"{action} trade {trade_id} with price {price}")
            return True

        except Exception as e:
            logger.error(f"Error saving trade: {e}", exc_info=True)
            return False

    def get_monthly_performance(self, account=None) -> Dict:
        """
        Calculate monthly P&L performance for FY using CSV imported data.
        Separates Futures and Options.

        Uses BrokerContractPnL (CSV imports) which has accurate P&L per contract.
        Monthly breakdown is based on contract expiry date.

        Returns:
            dict with monthly breakdown for futures and options
        """
        from apps.brokers.models import BrokerContractPnL

        # Query CSV imported contracts for FY (by expiry date)
        queryset = BrokerContractPnL.objects.filter(
            models.Q(expiry_date__gte=self.fy_start, expiry_date__lte=self.fy_end) |
            models.Q(expiry_date__isnull=True)
        )

        # Initialize result structure
        result = {
            'fy_label': get_fy_label(),
            'fy_start': self.fy_start.strftime('%Y-%m-%d'),
            'fy_end': self.fy_end.strftime('%Y-%m-%d'),
            'total_trades': queryset.count(),
            'data_source': 'csv_import',
            'months': [],
            'futures': {
                'total_trades': 0,
                'realized_pnl': Decimal('0'),
                'open_positions': 0,
            },
            'options': {
                'total_trades': 0,
                'realized_pnl': Decimal('0'),
                'open_positions': 0,
            },
            'overall': {
                'total_trades': 0,
                'realized_pnl': Decimal('0'),
                'open_positions': 0,
            }
        }

        if queryset.count() == 0:
            return result

        # Track monthly P&L by expiry month
        monthly_pnl = defaultdict(lambda: {
            'futures': {'pnl': Decimal('0'), 'contracts': 0},
            'options': {'pnl': Decimal('0'), 'contracts': 0},
        })

        for contract in queryset:
            # Use expiry_date for monthly grouping, or created_at if no expiry
            if contract.expiry_date:
                month_key = contract.expiry_date.strftime('%Y-%m')
            else:
                month_key = contract.created_at.strftime('%Y-%m')

            # Determine category from segment
            category = 'options' if contract.segment == 'OPTIONS' else 'futures'

            # Use net_pnl from CSV import (already includes all charges)
            pnl = contract.net_pnl or Decimal('0')

            monthly_pnl[month_key][category]['pnl'] += pnl
            monthly_pnl[month_key][category]['contracts'] += 1

        # Build monthly results
        for month_key in sorted(monthly_pnl.keys()):
            data = monthly_pnl[month_key]

            futures_pnl = data['futures']['pnl']
            options_pnl = data['options']['pnl']
            total_pnl = futures_pnl + options_pnl

            month_entry = {
                'month': month_key,
                'month_label': datetime.strptime(month_key, '%Y-%m').strftime('%b %Y'),
                'futures': {
                    'trades': data['futures']['contracts'],
                    'realized_pnl': float(futures_pnl),
                },
                'options': {
                    'trades': data['options']['contracts'],
                    'realized_pnl': float(options_pnl),
                },
                'total': {
                    'trades': data['futures']['contracts'] + data['options']['contracts'],
                    'realized_pnl': float(total_pnl),
                }
            }

            result['months'].append(month_entry)

            # Accumulate totals
            result['futures']['total_trades'] += data['futures']['contracts']
            result['futures']['realized_pnl'] += futures_pnl

            result['options']['total_trades'] += data['options']['contracts']
            result['options']['realized_pnl'] += options_pnl

        # Calculate overall totals
        result['overall']['total_trades'] = result['futures']['total_trades'] + result['options']['total_trades']
        result['overall']['realized_pnl'] = result['futures']['realized_pnl'] + result['options']['realized_pnl']

        # Convert Decimals to floats for JSON
        for key in ['futures', 'options', 'overall']:
            result[key]['realized_pnl'] = float(result[key]['realized_pnl'])

        # Backwards compatibility - keep 'net_pnl' as alias for 'realized_pnl'
        for key in ['futures', 'options', 'overall']:
            result[key]['net_pnl'] = result[key]['realized_pnl']

        return result

    def get_broker_breakdown(self) -> Dict:
        """
        Get performance breakdown by broker using CSV imported data.

        Uses BrokerContractPnL (CSV imports) which has accurate P&L per contract.
        """
        from apps.brokers.models import BrokerContractPnL

        # Query CSV imported contracts for FY (by expiry date)
        queryset = BrokerContractPnL.objects.filter(
            models.Q(expiry_date__gte=self.fy_start, expiry_date__lte=self.fy_end) |
            models.Q(expiry_date__isnull=True)
        )

        result = {
            'fy_label': get_fy_label(),
            'data_source': 'csv_import',
            'brokers': []
        }

        broker_names = {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}

        for broker_code in ['KOTAK', 'ICICI']:
            broker_contracts = queryset.filter(broker=broker_code)

            if not broker_contracts.exists():
                continue

            # Aggregate P&L from CSV imports
            futures_pnl = Decimal('0')
            options_pnl = Decimal('0')
            total_contracts = 0

            for contract in broker_contracts:
                pnl = contract.net_pnl or Decimal('0')
                total_contracts += 1

                if contract.segment == 'OPTIONS':
                    options_pnl += pnl
                else:
                    futures_pnl += pnl

            total_pnl = futures_pnl + options_pnl

            result['brokers'].append({
                'broker': broker_names.get(broker_code, broker_code),
                'broker_code': broker_code,
                'total_trades': total_contracts,
                'net_pnl': float(total_pnl),
                'futures_pnl': float(futures_pnl),
                'options_pnl': float(options_pnl),
                'open_positions': 0,  # CSV imports are closed positions
            })

        return result

    def get_imported_contract_pnl_summary(self, broker: str = None) -> Dict:
        """
        Get FY P&L summary from imported CSV data (BrokerContractPnL).

        This aggregates P&L from CSV imports separately from API-synced trades.
        Useful for historical data that can't be fetched via API.

        Args:
            broker: Optional filter by broker ('KOTAK' or 'ICICI')

        Returns:
            dict with aggregated P&L by segment and broker
        """
        from apps.brokers.models import BrokerContractPnL
        from django.db.models import Sum, Count

        queryset = BrokerContractPnL.objects.all()

        if broker:
            queryset = queryset.filter(broker=broker)

        # Filter by expiry date within FY (for contracts that have expiry)
        # Note: Some imports may not have expiry_date, include those too
        queryset = queryset.filter(
            models.Q(expiry_date__gte=self.fy_start, expiry_date__lte=self.fy_end) |
            models.Q(expiry_date__isnull=True)
        )

        result = {
            'fy_label': get_fy_label(),
            'source': 'CSV Import',
            'total_records': queryset.count(),
            'futures': {
                'records': 0,
                'net_pnl': Decimal('0'),
                'gross_pnl': Decimal('0'),
                'total_charges': Decimal('0'),
            },
            'options': {
                'records': 0,
                'net_pnl': Decimal('0'),
                'gross_pnl': Decimal('0'),
                'total_charges': Decimal('0'),
            },
            'overall': {
                'net_pnl': Decimal('0'),
                'gross_pnl': Decimal('0'),
                'total_charges': Decimal('0'),
            },
            'by_broker': [],
        }

        if queryset.count() == 0:
            return result

        # Aggregate by segment
        segment_agg = queryset.values('segment').annotate(
            records=Count('id'),
            total_net_pnl=Sum('net_pnl'),
            total_gross_pnl=Sum('gross_pnl'),
            total_charges=Sum('total_charges'),
        )

        for agg in segment_agg:
            segment = agg['segment'].lower()
            if segment in result:
                result[segment]['records'] = agg['records']
                result[segment]['net_pnl'] = agg['total_net_pnl'] or Decimal('0')
                result[segment]['gross_pnl'] = agg['total_gross_pnl'] or Decimal('0')
                result[segment]['total_charges'] = agg['total_charges'] or Decimal('0')

        # Calculate overall totals
        result['overall']['net_pnl'] = result['futures']['net_pnl'] + result['options']['net_pnl']
        result['overall']['gross_pnl'] = result['futures']['gross_pnl'] + result['options']['gross_pnl']
        result['overall']['total_charges'] = result['futures']['total_charges'] + result['options']['total_charges']

        # Aggregate by broker
        broker_agg = queryset.values('broker').annotate(
            records=Count('id'),
            total_net_pnl=Sum('net_pnl'),
            futures_pnl=Sum('net_pnl', filter=models.Q(segment='FUTURES')),
            options_pnl=Sum('net_pnl', filter=models.Q(segment='OPTIONS')),
        )

        broker_names = {'KOTAK': 'Kotak Neo', 'ICICI': 'ICICI Breeze'}
        for agg in broker_agg:
            result['by_broker'].append({
                'broker': broker_names.get(agg['broker'], agg['broker']),
                'broker_code': agg['broker'],
                'records': agg['records'],
                'net_pnl': float(agg['total_net_pnl'] or 0),
                'futures_pnl': float(agg['futures_pnl'] or 0),
                'options_pnl': float(agg['options_pnl'] or 0),
            })

        # Convert Decimals to floats for JSON
        for key in ['futures', 'options', 'overall']:
            for field in ['net_pnl', 'gross_pnl', 'total_charges']:
                result[key][field] = float(result[key][field])

        return result

    def get_combined_fy_summary(self) -> Dict:
        """
        Get FY P&L summary from CSV imports (primary data source).

        CSV imports contain accurate P&L data from broker statements.
        API-synced trades are not reliable for historical P&L calculation.

        Returns:
            dict with FY totals from CSV imports
        """
        # Get CSV imported data (now the primary source)
        imported_data = self.get_imported_contract_pnl_summary()

        result = {
            'fy_label': get_fy_label(),
            'data_source': 'csv_import',
            'csv_imports': {
                'total_records': imported_data.get('total_records', 0),
                'futures_pnl': imported_data.get('futures', {}).get('net_pnl', 0),
                'options_pnl': imported_data.get('options', {}).get('net_pnl', 0),
                'total_pnl': imported_data.get('overall', {}).get('net_pnl', 0),
                'total_charges': imported_data.get('overall', {}).get('total_charges', 0),
            },
            'by_broker': imported_data.get('by_broker', []),
            # For backwards compatibility
            'combined': {
                'futures_pnl': imported_data.get('futures', {}).get('net_pnl', 0),
                'options_pnl': imported_data.get('options', {}).get('net_pnl', 0),
                'total_pnl': imported_data.get('overall', {}).get('net_pnl', 0),
            },
        }

        return result


# Singleton
_analytics = None


def get_fy_analytics() -> FYTradeAnalytics:
    """Get singleton FYTradeAnalytics instance."""
    global _analytics
    if _analytics is None:
        _analytics = FYTradeAnalytics()
    return _analytics
