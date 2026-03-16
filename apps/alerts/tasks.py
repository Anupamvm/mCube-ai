"""
Celery tasks for the alerts app.
"""

from celery import shared_task


@shared_task(name='flush_notification_buffer')
def flush_notification_buffer(event_type: str, group_key: str):
    """Flush aggregation buffer and send grouped notification."""
    from apps.alerts.services.aggregation_buffer import AggregationBuffer
    from apps.alerts.services.notification_service import notify

    merged = AggregationBuffer.flush(event_type, group_key)
    if merged is None:
        return  # Already flushed or expired

    # Send the merged notification (bypass aggregation to avoid re-buffering)
    notify(event_type, _skip_aggregation=True, **merged)
