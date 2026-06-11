"""
Dynamic button registry for Telegram inline keyboards.

Each notification template references a button set key. At send time,
``ButtonRegistry.get_buttons()`` resolves the specs into callback_data
strings using the provided context (position_id, instrument, task, etc.).
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class ButtonSpec:
    text: str
    callback_prefix: str = ''
    id_field: str = 'position_id'
    condition: Optional[Callable] = None    # show only if condition(ctx) is True
    url_path: Optional[str] = None          # when set, produces a URL button (not callback)


class ButtonRegistry:
    _registry: Dict[str, List[ButtonSpec]] = {}

    @classmethod
    def register(cls, key: str, buttons: List[ButtonSpec]):
        cls._registry[key] = buttons

    @classmethod
    def get_buttons(cls, key: str, context: dict) -> Optional[List[List[dict]]]:
        """
        Resolve a button set key into Telegram inline keyboard rows.

        Buttons with ``url_path`` produce URL-type buttons that open in the browser.
        Buttons with ``callback_prefix`` produce callback buttons handled by the bot.

        Returns list-of-rows suitable for ``NotificationPayload.keyboard``,
        or None if no buttons match.
        """
        from django.conf import settings

        specs = cls._registry.get(key)
        if not specs:
            return None
        row = []
        for spec in specs:
            if spec.condition and not spec.condition(context):
                continue
            if spec.url_path:
                base = getattr(settings, 'SITE_URL', '').rstrip('/')
                row.append({'text': spec.text, 'url': f"{base}{spec.url_path}"})
            else:
                id_val = context.get(spec.id_field, '')
                row.append({
                    'text': spec.text,
                    'callback_data': f"{spec.callback_prefix}_{id_val}"
                })
        return [row] if row else None


# ── Register button sets ────────────────────────────────────────────────

ButtonRegistry.register('EXIT_CONFIRMATION', [
    ButtonSpec('✅ Close Now', 'confirm_exit'),
    ButtonSpec('⏸️ Hold / Wait', 'hold_exit'),
])

ButtonRegistry.register('SL_TRIGGERED', [
    ButtonSpec('✅ Close Now', 'confirm_exit'),
    ButtonSpec('⏸️ Hold / Wait', 'hold_exit'),
])

ButtonRegistry.register('CIRCUIT_BREAKER', [
    ButtonSpec('✅ Acknowledge', 'ack_alert', id_field='instrument'),
    ButtonSpec('📊 View Positions', 'view_positions', id_field='instrument'),
])

ButtonRegistry.register('CRITICAL_ERROR', [
    ButtonSpec('🔄 Retry', 'retry_task', id_field='task'),
    ButtonSpec('✅ Acknowledge', 'ack_alert', id_field='instrument'),
])

ButtonRegistry.register('RISK_WARNING', [
    ButtonSpec('✅ Acknowledge', 'ack_alert', id_field='instrument'),
    ButtonSpec('📊 View Positions', 'view_positions', id_field='instrument'),
])

ButtonRegistry.register('TASK_ERROR', [
    ButtonSpec('🔄 Retry', 'retry_task', id_field='task'),
    ButtonSpec('✅ Acknowledge', 'ack_alert', id_field='instrument'),
])

ButtonRegistry.register('BROKER_LOGIN', [
    ButtonSpec('🔑 Login via Web', url_path='/brokers/breeze/login/'),
])
