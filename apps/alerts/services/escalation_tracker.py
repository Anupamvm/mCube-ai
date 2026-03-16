"""
Progressive escalation tracker for repeated notifications.

Tracks how many times a condition fires within a 1-hour window and
upgrades the notification priority when thresholds are crossed.

Example: broker sync fails 3 times → WARNING, 5 times → HIGH, 10 → CRITICAL.
Auto-clears after 1 hour of silence.
"""

import logging

logger = logging.getLogger(__name__)

# Escalation thresholds: after N occurrences within window, upgrade priority
_ESCALATION_RULES = [
    (10, 'CRITICAL'),
    (5,  'HIGH'),
    (3,  'WARNING'),
]

_WINDOW_SECONDS = 3600  # 1 hour


class EscalationTracker:
    """Redis-backed occurrence counter with priority escalation."""

    PREFIX = 'tg_esc_'

    @classmethod
    def check_and_escalate(cls, key: str, base_priority: str) -> str:
        """
        Increment counter for key. Return escalated priority if threshold met.
        """
        from django.core.cache import cache

        cache_key = f"{cls.PREFIX}{key}"
        try:
            count = cache.get(cache_key, 0)
            count += 1
            cache.set(cache_key, count, timeout=_WINDOW_SECONDS)

            for threshold, escalated_priority in _ESCALATION_RULES:
                if count >= threshold:
                    if escalated_priority != base_priority:
                        logger.info(
                            f"Escalating {key}: {base_priority} → {escalated_priority} "
                            f"({count} occurrences)"
                        )
                    return escalated_priority

            return base_priority
        except Exception:
            return base_priority  # Fail-open

    @classmethod
    def clear(cls, key: str):
        """Clear escalation counter (condition resolved)."""
        from django.core.cache import cache

        cache_key = f"{cls.PREFIX}{key}"
        try:
            cache.delete(cache_key)
        except Exception:
            pass

    @classmethod
    def get_count(cls, key: str) -> int:
        """Get current occurrence count (for adding to context messages)."""
        from django.core.cache import cache

        try:
            return cache.get(f"{cls.PREFIX}{key}", 0)
        except Exception:
            return 0
