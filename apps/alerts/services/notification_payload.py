"""
Structured notification payload for all Telegram alerts.

All outbound notifications should be constructed as a NotificationPayload and
rendered via TelegramMessageFormatter.  This separates *what* a message says
from *how* it looks, enabling:

  - Consistent mobile-optimised layout across all alert types
  - Per-position dedup key propagation (fixes rate-limiter cross-suppression)
  - Mode/sizing footer appended uniformly in one place
  - Easy unit-testing of message content without Telegram calls

Usage::

    from apps.alerts.services.notification_payload import NotificationPayload
    from apps.alerts.services.telegram_client import send_notification

    payload = NotificationPayload(
        title="Stop-Loss Hit",
        status="ACTION_REQUIRED",
        instrument="RELIANCE MAR FUT",
        strategy="ICICI Futures",
        task="monitor_and_manage_positions",
        metrics={"P&L": "-₹8,420 (-2.1%)", "Now": "₹2,450"},
        position={
            "Direction": "LONG  ·  1 lot",
            "Entry": "₹2,500.00",
            "Current": "₹2,450.00",
            "SL": "₹2,450.00 (triggered)",
        },
        context=["Stop-loss level reached", "System will NOT auto-execute"],
        keyboard=[[
            {"text": "✅ Close Now", "callback_data": "confirm_exit_42"},
            {"text": "⏸ Hold",       "callback_data": "hold_exit_42"},
        ]],
        priority="CRITICAL",
        dedup_key="exit_suggestion_42",
        mode_label="🔒 Full Control",
        sizing_label="🧪 Test (1 lot)",
    )

    send_notification(payload)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


# Valid status values — drives emoji and label in the header row.
# Use these constants to avoid typo-bugs at call sites.
STATUS_INFO = 'INFO'
STATUS_WARNING = 'WARNING'
STATUS_ACTION_REQUIRED = 'ACTION_REQUIRED'
STATUS_EXECUTED = 'EXECUTED'
STATUS_SUCCESS = 'SUCCESS'
STATUS_ERROR = 'ERROR'
STATUS_CRITICAL = 'CRITICAL'


@dataclass
class NotificationPayload:
    """
    Structured notification payload — decouples content from formatting.

    Fields
    ------
    title       Short event title shown bold in the header.
                e.g. "Stop-Loss Hit", "Exit Suggestion", "Risk Warning"

    status      One of the STATUS_* constants above — drives the header emoji
                and label ("Action Required", "Executed", etc.)

    instrument  Trading symbol shown in monospace for fast scanning.
                e.g. "RELIANCE MAR FUT"

    strategy    Strategy or subsystem name.
                e.g. "ICICI Futures", "Kotak Strangle", "Risk Manager"

    task        Celery task name or short label.
                e.g. "monitor_and_manage_positions"

    timestamp   UTC datetime — formatted to IST by the renderer.
                Defaults to timezone.now() when rendered.

    metrics     Key→value pairs shown inline in the header (max 4 pairs,
                rendered 2 per line).  Values should be pre-formatted strings.
                e.g. {"P&L": "-₹8,420 (-2.1%)", "SL": "₹2,450"}

    keyboard    Inline keyboard rows: list-of-list of {"text", "callback_data"}
                dicts.  Rendered right after the metrics, before details.

    position    "📍 Position" detail section — key→value dict.

    context     "🧠 Context" detail section — list of bullet strings explaining
                why the notification fired.

    market      "📊 Market" detail section — key→value dict (VIX, regime, etc.)

    actions     "⚡ Action" detail section — list of bullet strings describing
                what happened or what the user should do.

    system      "🖥 System" detail section — key→value dict for IDs / module.

    priority    Maps to TelegramClient rate-limiter priority.
                CRITICAL | HIGH | WARNING | INFO  (default: INFO)

    dedup_key   Explicit Redis cache key suffix for dedup.  When set, the
                rate-limiter uses this key instead of a message hash — prevents
                position-A alerts from suppressing position-B alerts.

    mode_label  Short display of notification_level, e.g. "🔒 Full Control".
                Rendered in the ⚙️ footer.

    sizing_label Short display of position_sizing_mode, e.g. "🧪 Test (1 lot)".
                Rendered in the ⚙️ footer beside mode_label.
    """

    # ── Required ──────────────────────────────────────────────────────────────
    title: str
    status: str

    # ── Header (compact summary, always visible on mobile) ────────────────────
    instrument: Optional[str] = None
    strategy: Optional[str] = None
    task: Optional[str] = None
    timestamp: Optional[datetime] = None

    # ── Summary metrics (≤ 4 pairs, 2 per rendered line) ─────────────────────
    metrics: Dict[str, str] = field(default_factory=dict)

    # ── Inline keyboard rows (rendered after metrics, above detail section) ───
    keyboard: Optional[List[List[Dict[str, str]]]] = None

    # ── Detail sections (below ─── separator line) ────────────────────────────
    position: Optional[Dict[str, str]] = None
    context: Optional[List[str]] = None
    market: Optional[Dict[str, str]] = None
    actions: Optional[List[str]] = None
    system: Optional[Dict[str, str]] = None

    # ── Delivery control ──────────────────────────────────────────────────────
    priority: str = 'INFO'
    dedup_key: Optional[str] = None

    # ── Mode / sizing footer ──────────────────────────────────────────────────
    mode_label: Optional[str] = None
    sizing_label: Optional[str] = None
