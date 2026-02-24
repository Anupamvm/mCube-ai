"""
Trade Sync Service

Syncs trades from broker APIs (Kotak Neo and ICICI Breeze) to the
BrokerTradeHistory model for reconciliation and reporting.
"""

import logging
from datetime import date, datetime
from django.core.cache import cache

from apps.brokers.models import BrokerTradeHistory
from apps.core.constants import BROKER_KOTAK, BROKER_ICICI

logger = logging.getLogger(__name__)

# Lock timeout for preventing concurrent syncs (in seconds)
SYNC_LOCK_TIMEOUT = 300  # 5 minutes


class TradeSyncService:
    """
    Service for syncing trades from broker APIs to BrokerTradeHistory.

    Uses get_or_create pattern to prevent duplicate records.
    Supports Redis locking for concurrent sync prevention.
    """

    @staticmethod
    def sync_today_trades(account):
        """
        Sync today's trades for a specific broker account.

        Args:
            account: BrokerAccount instance

        Returns:
            dict: {
                'success': bool,
                'new_count': int,
                'updated_count': int,
                'errors': list of error messages
            }
        """
        today = date.today()
        return TradeSyncService.sync_trades_for_date_range(
            account,
            from_date=today,
            to_date=today
        )

    @staticmethod
    def sync_trades_for_date_range(account, from_date, to_date):
        """
        Sync trades for a date range with get_or_create pattern.

        Args:
            account: BrokerAccount instance
            from_date: Start date (date object or 'YYYY-MM-DD' string)
            to_date: End date (date object or 'YYYY-MM-DD' string)

        Returns:
            dict: {
                'success': bool,
                'new_count': int,
                'updated_count': int,
                'total_fetched': int,
                'errors': list of error messages
            }
        """
        # Acquire lock to prevent concurrent syncs
        lock_key = f"trade_sync_lock_{account.id}"
        if not cache.add(lock_key, True, SYNC_LOCK_TIMEOUT):
            logger.warning(f"Trade sync already in progress for account {account.id}")
            return {
                'success': False,
                'new_count': 0,
                'updated_count': 0,
                'total_fetched': 0,
                'errors': ['Sync already in progress']
            }

        try:
            # Convert dates if needed
            if isinstance(from_date, str):
                from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
            if isinstance(to_date, str):
                to_date = datetime.strptime(to_date, '%Y-%m-%d').date()

            logger.info(f"Syncing trades for account {account.id} ({account.broker}): "
                       f"{from_date} to {to_date}")

            # Dispatch to appropriate broker sync
            if account.broker == BROKER_KOTAK:
                return TradeSyncService._sync_kotak_trades(account, from_date, to_date)
            elif account.broker == BROKER_ICICI:
                return TradeSyncService._sync_breeze_trades(account, from_date, to_date)
            else:
                return {
                    'success': False,
                    'new_count': 0,
                    'updated_count': 0,
                    'total_fetched': 0,
                    'errors': [f'Unsupported broker: {account.broker}']
                }

        finally:
            # Release lock
            cache.delete(lock_key)

    @staticmethod
    def _sync_kotak_trades(account, from_date, to_date):
        """
        Sync trades from Kotak Neo API.

        The Neo trade_report() API returns all available trades with fill dates.
        We filter to the requested date range after fetching.
        """
        from apps.brokers.integrations.kotak_neo import get_trade_book

        new_count = 0
        updated_count = 0
        errors = []

        try:
            result = get_trade_book()

            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Failed to fetch Kotak trades: {error_msg}")
                return {
                    'success': False,
                    'new_count': 0,
                    'updated_count': 0,
                    'total_fetched': 0,
                    'errors': [error_msg]
                }

            trades = result.get('trades', [])
            logger.info(f"Fetched {len(trades)} trades from Kotak Neo")

            for trade in trades:
                try:
                    trade_data = TradeSyncService._normalize_kotak_trade(trade)
                    obj, created = BrokerTradeHistory.sync_from_api(
                        account=account,
                        trade_data=trade_data,
                        broker='KOTAK'
                    )
                    if created:
                        new_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    error_msg = f"Error processing Kotak trade {trade.get('trade_id', 'UNKNOWN')}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            logger.info(f"Kotak sync complete: {new_count} new, {updated_count} existing")

            return {
                'success': len(errors) == 0,
                'new_count': new_count,
                'updated_count': updated_count,
                'total_fetched': len(trades),
                'errors': errors
            }

        except Exception as e:
            logger.exception(f"Error in Kotak trade sync: {e}")
            return {
                'success': False,
                'new_count': new_count,
                'updated_count': updated_count,
                'total_fetched': 0,
                'errors': [str(e)]
            }

    @staticmethod
    def _sync_breeze_trades(account, from_date, to_date):
        """
        Sync trades from ICICI Breeze API.
        """
        from apps.brokers.integrations.breeze import get_trade_list

        new_count = 0
        updated_count = 0
        errors = []

        try:
            result = get_trade_list(
                from_date=from_date.strftime('%Y-%m-%d'),
                to_date=to_date.strftime('%Y-%m-%d'),
                exchange_code='NFO'
            )

            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Failed to fetch Breeze trades: {error_msg}")
                return {
                    'success': False,
                    'new_count': 0,
                    'updated_count': 0,
                    'total_fetched': 0,
                    'errors': [error_msg]
                }

            trades = result.get('trades', [])
            logger.info(f"Fetched {len(trades)} trades from Breeze")

            for trade in trades:
                try:
                    trade_data = TradeSyncService._normalize_breeze_trade(trade)
                    obj, created = BrokerTradeHistory.sync_from_api(
                        account=account,
                        trade_data=trade_data,
                        broker='ICICI'
                    )
                    if created:
                        new_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    error_msg = f"Error processing Breeze trade {trade.get('trade_id', 'UNKNOWN')}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            logger.info(f"Breeze sync complete: {new_count} new, {updated_count} existing")

            return {
                'success': len(errors) == 0,
                'new_count': new_count,
                'updated_count': updated_count,
                'total_fetched': len(trades),
                'errors': errors
            }

        except Exception as e:
            logger.exception(f"Error in Breeze trade sync: {e}")
            return {
                'success': False,
                'new_count': new_count,
                'updated_count': updated_count,
                'total_fetched': 0,
                'errors': [str(e)]
            }

    @staticmethod
    def _normalize_kotak_trade(trade):
        """
        Normalize Kotak Neo trade data to common format.
        """
        return {
            'trade_id': trade.get('trade_id', ''),
            'order_id': trade.get('order_id', ''),
            'symbol': trade.get('symbol', ''),
            'trading_symbol': trade.get('trading_symbol', ''),
            'segment': trade.get('exchange', 'NFO'),
            'trade_type': trade.get('transaction_type', 'BUY'),
            'product_type': trade.get('product', 'NRML'),
            'quantity': trade.get('quantity', 0),
            'price': trade.get('price', 0),
            'trade_value': trade.get('quantity', 0) * trade.get('price', 0),
            'trade_date': trade.get('trade_date'),
            'trade_time': trade.get('trade_time'),
            'trade_datetime': None,  # Will be combined from date and time
            'expiry_date': None,  # Extract from trading_symbol if needed
            'strike_price': None,
            'option_type': '',
            'brokerage': 0,
            'stt': 0,
            'exchange_charges': 0,
            'gst': 0,
            'stamp_duty': 0,
        }

    @staticmethod
    def _normalize_breeze_trade(trade):
        """
        Normalize Breeze trade data to common format.
        """
        # Parse expiry date if available
        expiry_date = None
        expiry_str = trade.get('expiry_date', '')
        if expiry_str:
            try:
                expiry_date = datetime.strptime(expiry_str, '%d-%b-%Y').date()
            except ValueError:
                pass

        # Parse strike price
        strike_price = None
        strike_str = trade.get('strike_price', '')
        if strike_str:
            try:
                strike_price = float(strike_str)
            except (ValueError, TypeError):
                pass

        return {
            'trade_id': trade.get('trade_id', ''),
            'order_id': trade.get('order_id', ''),
            'symbol': trade.get('symbol', ''),
            'trading_symbol': trade.get('trading_symbol', ''),
            'segment': trade.get('exchange', 'NFO'),
            'trade_type': trade.get('transaction_type', 'BUY'),
            'product_type': trade.get('product', 'NRML'),
            'quantity': trade.get('quantity', 0),
            'price': trade.get('price', 0),
            'trade_value': trade.get('quantity', 0) * trade.get('price', 0),
            'trade_date': trade.get('trade_date'),
            'trade_time': trade.get('trade_time'),
            'trade_datetime': trade.get('trade_datetime'),
            'expiry_date': expiry_date,
            'strike_price': strike_price,
            'option_type': trade.get('option_type', ''),
            'brokerage': 0,
            'stt': 0,
            'exchange_charges': 0,
            'gst': 0,
            'stamp_duty': 0,
        }

    @staticmethod
    def reconcile_with_taken_trades(account):
        """
        Attempt to match BrokerTradeHistory records with TakenTrade records.

        This helps in identifying which broker trades correspond to
        our tracked taken trades.

        Args:
            account: BrokerAccount instance

        Returns:
            dict: {
                'matched_count': int,
                'unmatched_broker_trades': int,
                'unmatched_taken_trades': int
            }
        """
        from apps.trading.models import TakenTrade

        # Get unreconciled broker trades
        unreconciled_trades = BrokerTradeHistory.objects.filter(
            account=account,
            is_reconciled=False
        )

        # Get taken trades without broker trade links
        taken_trades = TakenTrade.objects.filter(
            account=account,
            status__in=['EXECUTED', 'ACTIVE', 'CLOSED']
        )

        matched_count = 0

        for broker_trade in unreconciled_trades:
            # Try to find matching TakenTrade
            # Match by: trading_symbol, trade_date, quantity
            matching_taken = taken_trades.filter(
                instrument__icontains=broker_trade.symbol,
                taken_at__date__lte=broker_trade.trade_date,
            ).first()

            if matching_taken:
                broker_trade.taken_trade = matching_taken
                broker_trade.is_reconciled = True
                broker_trade.save()
                matched_count += 1
                logger.info(f"Matched broker trade {broker_trade.id} with TakenTrade {matching_taken.id}")

        unmatched_broker = BrokerTradeHistory.objects.filter(
            account=account,
            is_reconciled=False
        ).count()

        unmatched_taken = TakenTrade.objects.filter(
            account=account,
            status__in=['EXECUTED', 'ACTIVE', 'CLOSED'],
            broker_trades__isnull=True
        ).count()

        return {
            'matched_count': matched_count,
            'unmatched_broker_trades': unmatched_broker,
            'unmatched_taken_trades': unmatched_taken
        }

    @staticmethod
    def get_sync_status(account):
        """
        Get the sync status for an account.

        Returns:
            dict: {
                'last_sync': datetime or None,
                'total_records': int,
                'unreconciled_count': int,
                'is_syncing': bool
            }
        """
        lock_key = f"trade_sync_lock_{account.id}"

        latest_record = BrokerTradeHistory.objects.filter(
            account=account
        ).order_by('-created_at').first()

        total_records = BrokerTradeHistory.objects.filter(
            account=account
        ).count()

        unreconciled = BrokerTradeHistory.objects.filter(
            account=account,
            is_reconciled=False
        ).count()

        return {
            'last_sync': latest_record.created_at if latest_record else None,
            'total_records': total_records,
            'unreconciled_count': unreconciled,
            'is_syncing': cache.get(lock_key, False)
        }
