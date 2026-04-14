"""
Notification template registry.

Each event type has a template that defines default status, priority,
aggregation behaviour, dedup key format, and other rendering hints.
The ``notify()`` function in ``notification_service`` looks up the template
first and fills any caller-omitted fields from it.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class NotificationTemplate:
    """Defaults and behaviour hints for one notification event type."""

    default_status: str
    default_priority: str
    title_format: str = ''                # "{instrument} Near Stop-Loss"
    aggregatable: bool = False
    aggregate_title_format: str = ''      # "{count} Stop-Loss Alerts"
    aggregate_window_secs: int = 30
    collapsible: bool = True              # Use <blockquote expandable>
    buttons: str = ''                     # ButtonRegistry key
    dedup_key_format: str = ''            # "sl_triggered_{position_id}"
    min_pnl_change_pct: float = 0.0      # Min P&L % change to re-alert
    service_group: str = 'general'        # For service-level rate cap


class TemplateRegistry:
    """Simple in-memory registry — templates are registered at import time."""

    _templates: Dict[str, NotificationTemplate] = {}
    _default = NotificationTemplate(default_status='INFO', default_priority='INFO')

    @classmethod
    def register(cls, event_type: str, template: NotificationTemplate):
        cls._templates[event_type] = template

    @classmethod
    def get(cls, event_type: str) -> NotificationTemplate:
        return cls._templates.get(event_type, cls._default)


# ── Register all templates at import time ────────────────────────────────

TemplateRegistry.register('SL_TRIGGERED', NotificationTemplate(
    default_status='ACTION_REQUIRED',
    default_priority='CRITICAL',
    title_format='Stop-Loss Hit',
    aggregatable=True,
    aggregate_title_format='{count} Stop-Loss Alerts',
    aggregate_window_secs=30,
    collapsible=True,
    buttons='SL_TRIGGERED',
    dedup_key_format='sl_triggered_{position_id}',
    min_pnl_change_pct=2.0,
    service_group='position_monitor',
))

TemplateRegistry.register('TARGET_HIT', NotificationTemplate(
    default_status='ACTION_REQUIRED',
    default_priority='HIGH',
    title_format='Target Hit',
    aggregatable=True,
    aggregate_title_format='{count} Target Hit Alerts',
    aggregate_window_secs=30,
    buttons='EXIT_CONFIRMATION',
    dedup_key_format='target_hit_{position_id}',
    service_group='position_monitor',
))

TemplateRegistry.register('NEAR_SL', NotificationTemplate(
    default_status='WARNING',
    default_priority='HIGH',
    title_format='Near Stop-Loss',
    aggregatable=True,
    aggregate_title_format='{count} Positions Near SL',
    aggregate_window_secs=30,
    dedup_key_format='near_sl_{position_id}',
    service_group='position_monitor',
))

TemplateRegistry.register('EXIT_SUGGESTION', NotificationTemplate(
    default_status='ACTION_REQUIRED',
    default_priority='HIGH',
    title_format='Exit Suggestion',
    aggregatable=False,
    buttons='EXIT_CONFIRMATION',
    dedup_key_format='exit_suggestion_{position_id}',
    min_pnl_change_pct=1.0,
    service_group='position_monitor',
))

TemplateRegistry.register('CIRCUIT_BREAKER', NotificationTemplate(
    default_status='WARNING',
    default_priority='WARNING',
    title_format='Circuit Breaker Expired',
    aggregatable=True,
    aggregate_title_format='{count} Circuit Breaker Alerts',
    aggregate_window_secs=60,
    buttons='CIRCUIT_BREAKER',
    dedup_key_format='circuit_breaker_{instrument}',
    service_group='risk',
))

TemplateRegistry.register('SYSTEM_STATUS', NotificationTemplate(
    default_status='INFO',
    default_priority='INFO',
    collapsible=False,
    service_group='system',
))

TemplateRegistry.register('JOB_COMPLETED', NotificationTemplate(
    default_status='SUCCESS',
    default_priority='INFO',
    collapsible=False,
    service_group='system',
))

TemplateRegistry.register('CRITICAL_ERROR', NotificationTemplate(
    default_status='CRITICAL',
    default_priority='CRITICAL',
    buttons='CRITICAL_ERROR',
    dedup_key_format='critical_{instrument}',
    service_group='system',
))

TemplateRegistry.register('TRADE_EXECUTED', NotificationTemplate(
    default_status='EXECUTED',
    default_priority='HIGH',
    title_format='Position Closed',
    collapsible=True,
    service_group='position_monitor',
))

TemplateRegistry.register('RISK_WARNING', NotificationTemplate(
    default_status='WARNING',
    default_priority='HIGH',
    aggregatable=True,
    aggregate_window_secs=60,
    buttons='RISK_WARNING',
    dedup_key_format='risk_{instrument}',
    service_group='risk',
))

TemplateRegistry.register('TASK_ERROR', NotificationTemplate(
    default_status='ERROR',
    default_priority='HIGH',
    aggregatable=True,
    aggregate_window_secs=30,
    buttons='TASK_ERROR',
    dedup_key_format='task_error_{instrument}',
    service_group='system',
))

TemplateRegistry.register('BROKER_HEALTH', NotificationTemplate(
    default_status='WARNING',
    default_priority='HIGH',
    dedup_key_format='broker_health_{instrument}',
    service_group='system',
))

TemplateRegistry.register('HINDSIGHT_DIGEST', NotificationTemplate(
    default_status='INFO',
    default_priority='INFO',
    title_format='Hindsight Tracker Update',
    collapsible=True,
    service_group='reports',
))
