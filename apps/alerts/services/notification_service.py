"""
Unified notification API.

Every Telegram notification should go through ``notify()``.  It handles:

1. Template lookup → fill defaults (status, priority, buttons, dedup_key)
2. Min P&L change gate → skip if P&L hasn't moved enough since last alert
3. Aggregation check → buffer if aggregatable, schedule flush
4. Escalation check → upgrade priority if repeated
5. Build NotificationPayload → render via formatter
6. Send or edit via TelegramClient

Usage::

    from apps.alerts.services.notification_service import notify

    notify('CIRCUIT_BREAKER',
        title="Circuit Breaker Expired",
        instrument="Kotak Neo - Main",
        metrics={"Trigger": "WEEKLY_LOSS", "Since": "09 Mar"},
    )
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def notify(
    event_type: str,
    *,
    title: str = '',
    status: str = '',
    instrument: Optional[str] = None,
    strategy: Optional[str] = None,
    task: Optional[str] = None,
    metrics: Optional[dict] = None,
    position: Optional[dict] = None,
    context: Optional[list] = None,
    market: Optional[dict] = None,
    actions: Optional[list] = None,
    system: Optional[dict] = None,
    keyboard: Optional[list] = None,
    priority: str = '',
    dedup_key: Optional[str] = None,
    position_id: Optional[int] = None,
    update_message_id: Optional[int] = None,
    collapsible: Optional[bool] = None,
    pnl_pct: Optional[float] = None,
    _skip_aggregation: bool = False,
    _items: Optional[list] = None,        # Preserved from aggregation merge, unused here
) -> Tuple[bool, str]:
    """
    Send a structured notification.  Single entry point for all alerts.

    Returns:
        (success, detail_string) — detail is message_id, "rate_limited",
        "pnl_change_too_small", "aggregation_buffered", or error message.
    """
    from apps.alerts.services.notification_templates import TemplateRegistry
    from apps.alerts.services.notification_payload import NotificationPayload
    from apps.alerts.services.notification_formatter import format_notification, mode_labels_from_config
    from apps.alerts.services.telegram_client import get_telegram_client
    from apps.alerts.services.button_registry import ButtonRegistry
    from apps.alerts.services.aggregation_buffer import AggregationBuffer
    from apps.alerts.services.escalation_tracker import EscalationTracker

    template = TemplateRegistry.get(event_type)

    # 1. Apply template defaults ──────────────────────────────────────────
    status = status or template.default_status
    priority = priority or template.default_priority
    if not title and template.title_format:
        title = template.title_format.format(
            instrument=instrument or '', count='', task=task or ''
        )
    if not dedup_key and template.dedup_key_format:
        dedup_key = template.dedup_key_format.format(
            position_id=position_id or '', instrument=instrument or ''
        )
    if collapsible is None:
        collapsible = template.collapsible

    # 2. Min P&L change gate ──────────────────────────────────────────────
    if template.min_pnl_change_pct > 0 and pnl_pct is not None and position_id:
        if not _pnl_changed_enough(position_id, pnl_pct, template.min_pnl_change_pct):
            return True, "pnl_change_too_small"

    # 3. Aggregation ──────────────────────────────────────────────────────
    if template.aggregatable and not _skip_aggregation:
        group_key = f"{event_type}_{instrument or 'all'}"
        buffered = AggregationBuffer.add(event_type, group_key, {
            'title': title, 'instrument': instrument, 'strategy': strategy,
            'task': task, 'metrics': metrics, 'position': position,
            'context': context, 'market': market, 'actions': actions,
            'system': system, 'position_id': position_id, 'pnl_pct': pnl_pct,
        })
        if buffered:
            return True, "aggregation_buffered"

    # 4. Escalation ───────────────────────────────────────────────────────
    if dedup_key:
        priority = EscalationTracker.check_and_escalate(dedup_key, priority)

    # 5. Build payload ────────────────────────────────────────────────────
    config = _get_config()
    mode_label, sizing_label = mode_labels_from_config(config) if config else ('', '')

    # Auto-attach buttons from registry
    if keyboard is None and template.buttons:
        keyboard = ButtonRegistry.get_buttons(
            template.buttons,
            {'position_id': position_id, 'instrument': instrument, 'task': task}
        )

    payload = NotificationPayload(
        title=title,
        status=status,
        instrument=instrument,
        strategy=strategy,
        task=task,
        metrics=metrics or {},
        position=position,
        context=context,
        market=market,
        actions=actions,
        system=system,
        keyboard=keyboard,
        priority=priority,
        dedup_key=dedup_key,
        mode_label=mode_label,
        sizing_label=sizing_label,
        collapsible=collapsible,
    )

    # 6. Send or edit ─────────────────────────────────────────────────────
    client = get_telegram_client()
    if not client.is_enabled():
        logger.warning("Telegram notifications disabled - client not configured")
        return False, "Telegram client not configured"

    if update_message_id:
        text = format_notification(payload)
        reply_markup = {'inline_keyboard': keyboard} if keyboard else None
        return client.edit_message(update_message_id, text, reply_markup=reply_markup)

    return client.send_notification(payload)


def _pnl_changed_enough(position_id: int, current_pnl_pct: float, threshold: float) -> bool:
    """Check if P&L has moved enough since last alert to warrant re-sending."""
    from django.core.cache import cache

    key = f'tg_last_pnl_{position_id}'
    last_pnl = cache.get(key)
    if last_pnl is not None:
        if abs(current_pnl_pct - float(last_pnl)) < threshold:
            return False
    cache.set(key, str(current_pnl_pct), timeout=3600)  # 1 hour TTL
    return True


def clear_escalation(key: str):
    """Clear escalation counter when condition resolves."""
    from apps.alerts.services.escalation_tracker import EscalationTracker
    EscalationTracker.clear(key)


def _get_config():
    """Get TradingCoreConfig singleton, or None if unavailable."""
    try:
        from apps.core.models import TradingCoreConfig
        return TradingCoreConfig.get_solo()
    except Exception:
        return None
