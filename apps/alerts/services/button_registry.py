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
    callback_prefix: str
    id_field: str = 'position_id'
    condition: Optional[Callable] = None    # show only if condition(ctx) is True


class ButtonRegistry:
    _registry: Dict[str, List[ButtonSpec]] = {}

    @classmethod
    def register(cls, key: str, buttons: List[ButtonSpec]):
        cls._registry[key] = buttons

    @classmethod
    def get_buttons(cls, key: str, context: dict) -> Optional[List[List[dict]]]:
        """
        Resolve a button set key into Telegram inline keyboard rows.

        Returns list-of-rows suitable for ``NotificationPayload.keyboard``,
        or None if no buttons match.
        """
        specs = cls._registry.get(key)
        if not specs:
            return None
        row = []
        for spec in specs:
            if spec.condition and not spec.condition(context):
                continue
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
