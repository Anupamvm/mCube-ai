"""
Redis-backed aggregation buffer for grouping similar notifications.

Flow:
1. First item for a group_key → stored in Redis, Celery task scheduled
2. Subsequent items within window → appended to Redis list
3. When Celery task fires (after window expires) → flush() merges all items
   into one grouped NotificationPayload and sends it
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AggregationBuffer:
    """
    Groups notifications by (event_type, instrument) within a time window.

    Uses Django cache (Redis) for cross-process coordination.  Fails open:
    if Redis is unavailable the caller sends immediately.
    """

    BUFFER_PREFIX = 'tg_agg_'

    @classmethod
    def add(cls, event_type: str, group_key: str, payload_data: dict) -> bool:
        """
        Add a notification to the aggregation buffer.

        Returns True if buffered (caller should NOT send).
        Returns False if aggregation not possible (caller should send normally).
        """
        from django.core.cache import cache
        from apps.alerts.services.notification_templates import TemplateRegistry

        template = TemplateRegistry.get(event_type)
        cache_key = f"{cls.BUFFER_PREFIX}{group_key}"
        window = template.aggregate_window_secs

        try:
            existing = cache.get(cache_key)
            if existing:
                items = json.loads(existing)
                items.append(payload_data)
                cache.set(cache_key, json.dumps(items, default=str), timeout=window + 10)
                return True

            # First item — create buffer and schedule flush
            cache.set(cache_key, json.dumps([payload_data], default=str), timeout=window + 10)

            from apps.alerts.tasks import flush_notification_buffer
            flush_notification_buffer.apply_async(
                kwargs={'event_type': event_type, 'group_key': group_key},
                countdown=window,
            )
            return True

        except Exception:
            logger.warning(f"Aggregation buffer failed for {group_key}, sending immediately")
            return False  # Fail-open: let caller send normally

    @classmethod
    def flush(cls, event_type: str, group_key: str) -> Optional[dict]:
        """
        Flush the buffer and return merged payload data.

        Returns None if buffer is empty (already flushed or expired).
        """
        from django.core.cache import cache

        cache_key = f"{cls.BUFFER_PREFIX}{group_key}"
        raw = cache.get(cache_key)
        if not raw:
            return None

        cache.delete(cache_key)
        items = json.loads(raw)

        if len(items) == 1:
            return items[0]

        return cls._merge_items(event_type, items)

    @classmethod
    def _merge_items(cls, event_type: str, items: list) -> dict:
        """Merge multiple buffered payloads into one grouped payload."""
        from apps.alerts.services.notification_templates import TemplateRegistry

        template = TemplateRegistry.get(event_type)
        count = len(items)
        title = template.aggregate_title_format.format(count=count)
        instrument = items[0].get('instrument', '')

        # Build per-item summary lines for grouped context
        item_lines = []
        for item in items:
            pid = item.get('position_id', '?')
            metrics = item.get('metrics', {})
            pnl_display = metrics.get('P&L', '')
            strategy = item.get('strategy', '')
            line = f"#{pid}"
            if strategy:
                line += f" {strategy}"
            if pnl_display:
                line += f" · {pnl_display}"
            item_lines.append(line)

        return {
            'title': title,
            'instrument': instrument,
            'metrics': {'Positions': str(count)},
            'context': item_lines,
            '_items': items,  # Keep originals for individual button handling
        }
