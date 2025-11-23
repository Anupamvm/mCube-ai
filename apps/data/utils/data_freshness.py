"""
Data Freshness Utility

Ensures that Trendlyne data (TLStockData and ContractStockData) is never older than 30 minutes.
Automatically triggers updates when data is stale.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Staleness threshold: 30 minutes
STALENESS_THRESHOLD_MINUTES = 30
CACHE_KEY_PREFIX = "data_freshness_"


class DataFreshnessChecker:
    """
    Check and ensure data freshness for Trendlyne models
    """

    def __init__(self, staleness_threshold_minutes: int = STALENESS_THRESHOLD_MINUTES):
        """
        Initialize freshness checker

        Args:
            staleness_threshold_minutes: Minutes after which data is considered stale
        """
        self.staleness_threshold = timedelta(minutes=staleness_threshold_minutes)

    def check_tlstock_data_freshness(self, symbol: Optional[str] = None) -> Dict:
        """
        Check freshness of TLStockData

        Args:
            symbol: Optional specific symbol to check. If None, checks latest update.

        Returns:
            dict: {
                'is_fresh': bool,
                'last_updated': datetime,
                'age_minutes': float,
                'needs_update': bool,
                'model': 'TLStockData'
            }
        """
        from apps.data.models import TLStockData

        try:
            if symbol:
                record = TLStockData.objects.filter(nsecode=symbol).first()
            else:
                record = TLStockData.objects.order_by('-updated_at').first()

            if not record:
                logger.warning("No TLStockData records found in database")
                return {
                    'is_fresh': False,
                    'last_updated': None,
                    'age_minutes': float('inf'),
                    'needs_update': True,
                    'model': 'TLStockData',
                    'reason': 'No data in database'
                }

            last_updated = record.updated_at
            age = timezone.now() - last_updated
            age_minutes = age.total_seconds() / 60

            is_fresh = age < self.staleness_threshold
            needs_update = not is_fresh

            return {
                'is_fresh': is_fresh,
                'last_updated': last_updated,
                'age_minutes': age_minutes,
                'needs_update': needs_update,
                'model': 'TLStockData',
                'record_count': TLStockData.objects.count()
            }

        except Exception as e:
            logger.error(f"Error checking TLStockData freshness: {e}")
            return {
                'is_fresh': False,
                'last_updated': None,
                'age_minutes': float('inf'),
                'needs_update': True,
                'model': 'TLStockData',
                'error': str(e)
            }

    def check_contractstock_data_freshness(self, symbol: Optional[str] = None) -> Dict:
        """
        Check freshness of ContractStockData

        Args:
            symbol: Optional specific NSE code to check. If None, checks latest update.

        Returns:
            dict: {
                'is_fresh': bool,
                'last_updated': datetime,
                'age_minutes': float,
                'needs_update': bool,
                'model': 'ContractStockData'
            }
        """
        from apps.data.models import ContractStockData

        try:
            if symbol:
                record = ContractStockData.objects.filter(nse_code=symbol).first()
            else:
                record = ContractStockData.objects.order_by('-updated_at').first()

            if not record:
                logger.warning("No ContractStockData records found in database")
                return {
                    'is_fresh': False,
                    'last_updated': None,
                    'age_minutes': float('inf'),
                    'needs_update': True,
                    'model': 'ContractStockData',
                    'reason': 'No data in database'
                }

            last_updated = record.updated_at
            age = timezone.now() - last_updated
            age_minutes = age.total_seconds() / 60

            is_fresh = age < self.staleness_threshold
            needs_update = not is_fresh

            return {
                'is_fresh': is_fresh,
                'last_updated': last_updated,
                'age_minutes': age_minutes,
                'needs_update': needs_update,
                'model': 'ContractStockData',
                'record_count': ContractStockData.objects.count()
            }

        except Exception as e:
            logger.error(f"Error checking ContractStockData freshness: {e}")
            return {
                'is_fresh': False,
                'last_updated': None,
                'age_minutes': float('inf'),
                'needs_update': True,
                'model': 'ContractStockData',
                'error': str(e)
            }

    def check_all_freshness(self) -> Dict:
        """
        Check freshness of all Trendlyne data models

        Returns:
            dict: {
                'all_fresh': bool,
                'needs_update': bool,
                'models': {
                    'TLStockData': {...},
                    'ContractStockData': {...}
                },
                'oldest_age_minutes': float
            }
        """
        tlstock_status = self.check_tlstock_data_freshness()
        contractstock_status = self.check_contractstock_data_freshness()

        all_fresh = tlstock_status['is_fresh'] and contractstock_status['is_fresh']
        needs_update = tlstock_status['needs_update'] or contractstock_status['needs_update']

        oldest_age = max(
            tlstock_status['age_minutes'],
            contractstock_status['age_minutes']
        )

        return {
            'all_fresh': all_fresh,
            'needs_update': needs_update,
            'models': {
                'TLStockData': tlstock_status,
                'ContractStockData': contractstock_status
            },
            'oldest_age_minutes': oldest_age,
            'threshold_minutes': STALENESS_THRESHOLD_MINUTES
        }

    def ensure_fresh_data(self, force: bool = False) -> Dict:
        """
        Ensure data is fresh, trigger update if needed

        Args:
            force: Force update even if data appears fresh

        Returns:
            dict: {
                'success': bool,
                'was_stale': bool,
                'update_triggered': bool,
                'freshness_status': dict,
                'message': str
            }
        """
        # Check cache to prevent duplicate update triggers
        cache_key = f"{CACHE_KEY_PREFIX}update_in_progress"
        update_in_progress = cache.get(cache_key, False)

        if update_in_progress and not force:
            logger.info("Data update already in progress, skipping...")
            return {
                'success': True,
                'was_stale': False,
                'update_triggered': False,
                'message': 'Update already in progress',
                'freshness_status': self.check_all_freshness()
            }

        freshness_status = self.check_all_freshness()

        if force or freshness_status['needs_update']:
            logger.info(f"Data is stale (age: {freshness_status['oldest_age_minutes']:.1f} min). Triggering update...")

            # Set cache flag to prevent duplicate updates (30 min TTL)
            cache.set(cache_key, True, 1800)

            try:
                # Trigger async update
                update_result = self._trigger_data_update()

                return {
                    'success': update_result['success'],
                    'was_stale': True,
                    'update_triggered': True,
                    'freshness_status': freshness_status,
                    'update_result': update_result,
                    'message': update_result.get('message', 'Update triggered successfully')
                }

            except Exception as e:
                logger.error(f"Failed to trigger data update: {e}")
                # Clear cache on error so next request can retry
                cache.delete(cache_key)

                return {
                    'success': False,
                    'was_stale': True,
                    'update_triggered': False,
                    'freshness_status': freshness_status,
                    'error': str(e),
                    'message': f'Failed to trigger update: {str(e)}'
                }

        else:
            logger.info(f"Data is fresh (age: {freshness_status['oldest_age_minutes']:.1f} min)")
            return {
                'success': True,
                'was_stale': False,
                'update_triggered': False,
                'freshness_status': freshness_status,
                'message': 'Data is already fresh'
            }

    def _trigger_data_update(self) -> Dict:
        """
        Trigger Trendlyne data update using Celery task or management command

        Returns:
            dict: {
                'success': bool,
                'method': str,
                'message': str
            }
        """
        try:
            # Try to use Celery task first (async)
            from apps.data.tasks import fetch_and_import_trendlyne_data

            logger.info("Triggering Trendlyne data update via Celery task...")
            task = fetch_and_import_trendlyne_data.delay()

            return {
                'success': True,
                'method': 'celery_task',
                'task_id': task.id,
                'message': f'Async update triggered (task: {task.id})'
            }

        except (ImportError, Exception) as celery_error:
            logger.warning(f"Celery not available ({celery_error}), falling back to management command...")

            # Fallback: Use management command in thread
            import threading
            from django.core.management import call_command
            from io import StringIO

            def update_task():
                try:
                    logger.info("Running Trendlyne update via management command...")
                    output = StringIO()
                    call_command('trendlyne_data_manager', '--full-cycle', stdout=output)
                    logger.info(f"Trendlyne update completed: {output.getvalue()}")
                except Exception as e:
                    logger.error(f"Trendlyne update failed: {e}", exc_info=True)
                    # Clear cache to allow retry
                    cache.delete(f"{CACHE_KEY_PREFIX}update_in_progress")

            thread = threading.Thread(target=update_task, daemon=True)
            thread.start()

            return {
                'success': True,
                'method': 'management_command',
                'message': 'Background update started via management command'
            }


# Singleton instance
_freshness_checker = None


def get_freshness_checker() -> DataFreshnessChecker:
    """Get singleton freshness checker instance"""
    global _freshness_checker
    if _freshness_checker is None:
        _freshness_checker = DataFreshnessChecker()
    return _freshness_checker


def ensure_fresh_data(force: bool = False) -> Dict:
    """
    Convenience function to ensure data freshness

    Args:
        force: Force update even if data appears fresh

    Returns:
        dict: Freshness check and update result
    """
    checker = get_freshness_checker()
    return checker.ensure_fresh_data(force=force)


def check_data_freshness() -> Dict:
    """
    Convenience function to check data freshness without triggering updates

    Returns:
        dict: Freshness status for all models
    """
    checker = get_freshness_checker()
    return checker.check_all_freshness()
