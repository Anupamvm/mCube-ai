"""
Telegram message formatter for structured notifications.

Renders a NotificationPayload into an HTML-formatted string optimised
for Telegram mobile:

  ┌─ SUMMARY (always visible, ~5-6 lines) ──────────────────────────────┐
  │ [EMOJI] [BOLD TITLE]  ·  [STATUS LABEL]                             │
  │ INSTRUMENT_CODE  ·  DD Mon HH:MM                                    │
  │ Strategy  ·  task label                                             │
  │ Metric1: VALUE  ·  Metric2: VALUE                                   │
  │ Metric3: VALUE  ·  Metric4: VALUE                                   │
  │ [ACTION BUTTONS]                                                    │
  └─────────────────────────────────────────────────────────────────────┘
  ──────────────────────────────        ← visual separator
  ┌─ DETAILS (scrollable) ──────────────────────────────────────────────┐
  │ 📍 Position          🧠 Context       📊 Market                    │
  │ ⚡ Action             🖥 System                                     │
  └─────────────────────────────────────────────────────────────────────┘
  ⚙️ Mode  ·  Sizing                      ← footer always last

Design principles:
  • Fast comprehension < 3 seconds — most critical info in first 4 lines
  • Mobile-first: ~35 chars per line, no horizontal scrolling
  • Emojis as visual anchors only where meaningful
  • <code> for instruments so they pop on dark background
  • Section headers bold — easy to skim when scrolling
"""

import pytz
from datetime import datetime
from typing import Optional

from apps.alerts.services.notification_payload import NotificationPayload

_IST = pytz.timezone('Asia/Kolkata')

# Visual separator — Unicode box-drawing character, renders cleanly in Telegram.
_SEP = "─" * 30

# Status → (emoji, display label)
_STATUS_CONFIG = {
    'INFO':            ('ℹ️',  'Info'),
    'WARNING':         ('⚠️',  'Warning'),
    'ACTION_REQUIRED': ('🔔',  'Action Required'),
    'EXECUTED':        ('✅',  'Executed'),
    'SUCCESS':         ('💰',  'Success'),
    'ERROR':           ('🚨',  'Error'),
    'CRITICAL':        ('🚨',  'Critical'),
}

# Celery task name → short display label for the header location line.
_TASK_LABELS = {
    'monitor_and_manage_positions':      'position monitor',
    'alert_open_positions_pre_close':    'pre-close alert',
    'reconcile_positions_eod':           'EOD reconcile',
    'check_risk_limits_all_accounts':    'risk check',
    'monitor_circuit_breakers':          'circuit breaker',
    'execute_futures_algorithm':         'futures algo',
    'evaluate_options_strategy':         'options strategy',
    'close_trading_day':                 'close trading day',
    'send_morning_briefing':             'morning brief',
    'health_check_brokers':              'broker health',
    'broker_health_check':               'broker health',
    'evaluate_kotak_strangle_entry':     'strangle entry',
    'evaluate_kotak_strangle_exit':      'strangle exit',
    'batch_options_averaging':           'options averaging',
    'review_overnight_positions':        'overnight review',
    'monitor_opening_volatility':        'opening volatility',
    'breeze_session_get_client':         'broker auth',
    'refresh_breeze_session':            'session refresh',
    'premarket_data_fetch':              'pre-market data',
    'market_opening_validation':         'market open',
    'trade_start_evaluation':            'trade start',
    'check_futures_averaging':           'futures averaging',
    'start_options_trade':               'options trade',
    'aggregate_futures_results':         'futures screening',
    'run_day_analysis':                  'day analysis',
}


class TelegramMessageFormatter:
    """
    Renders a NotificationPayload into an HTML Telegram message.

    The message is structured as:

        [Header]     status emoji + bold title + italic status label
        [Location]   instrument in <code> + timestamp | strategy · task
        [Metrics]    key: bold-value pairs, 2 per line
        ─── separator ─────────────────────────────────
        [Sections]   📍 Position / 🧠 Context / 📊 Market / ⚡ Action / 🖥 System
        [Footer]     ⚙️ mode · sizing

    Inline keyboards are managed by the caller (TelegramClient.send_notification).
    """

    def format(self, payload: NotificationPayload) -> str:
        """Render payload to an HTML string. Returns at most 4096 chars (Telegram limit)."""
        parts: list[str] = []

        # ── 1. Header row ──────────────────────────────────────────────────────
        parts.append(self._header(payload))

        # ── 2. Location row (instrument + timestamp + strategy/task) ──────────
        loc = self._location(payload)
        if loc:
            parts.append(loc)

        # ── 3. Metrics block (key→value pairs inline) ─────────────────────────
        if payload.metrics:
            parts.append(self._metrics(payload.metrics))

        # ── 4. Detail sections ────────────────────────────────────────────────
        detail_sections = self._details(payload)
        if detail_sections:
            inner = "\n".join(detail_sections)
            if payload.collapsible:
                # Telegram Bot API 7.0+: expandable blockquote
                # Collapses to ~3 lines natively, user taps to expand
                parts.append(f"\n<blockquote expandable>{inner}\n</blockquote>")
            else:
                parts.append(f"\n{_SEP}")
                parts.extend(detail_sections)

        # ── 5. Footer ─────────────────────────────────────────────────────────
        footer = self._footer(payload)
        if footer:
            parts.append(footer)

        text = "\n".join(parts)

        # Hard truncate to Telegram's 4096-char limit (guard only — should never
        # fire for well-structured payloads).
        if len(text) > 4090:
            text = text[:4087] + "…"

        return text

    # ─── Private rendering helpers ────────────────────────────────────────────

    def _header(self, payload: NotificationPayload) -> str:
        """Line 1: ⚠️ Bold Title  ·  Italic Label"""
        emoji, label = _STATUS_CONFIG.get(payload.status, ('📢', payload.status))
        return f"{emoji} <b>{payload.title}</b>  ·  <i>{label}</i>"

    def _location(self, payload: NotificationPayload) -> str:
        """
        Line 2: INSTRUMENT_CODE  ·  DD Mon HH:MM
        Line 3: Strategy  ·  task label            (only if at least one exists)
        """
        lines = []

        # Instrument + timestamp
        ts = _ist_ts(payload.timestamp)
        if payload.instrument:
            lines.append(f"<code>{payload.instrument}</code>  ·  {ts}")
        else:
            lines.append(ts)

        # Strategy / task (secondary context)
        secondary = []
        if payload.strategy:
            secondary.append(payload.strategy)
        if payload.task:
            task_display = _TASK_LABELS.get(payload.task, payload.task.replace('_', ' '))
            secondary.append(task_display)
        if secondary:
            lines.append("  ·  ".join(secondary))

        return "\n".join(lines) if lines else ""

    def _metrics(self, metrics: dict) -> str:
        """
        Render metrics as 2-per-line pairs:
          Metric1: VALUE  ·  Metric2: VALUE
          Metric3: VALUE
        Values are bolded; keys are plain.
        """
        pairs = [f"{k}: <b>{v}</b>" for k, v in metrics.items()]
        rows = []
        for i in range(0, len(pairs), 2):
            rows.append("  ·  ".join(pairs[i: i + 2]))
        return "\n".join(rows)

    def _details(self, payload: NotificationPayload) -> list[str]:
        """Build all detail sections that have data."""
        out = []
        if payload.position:
            out.append(_kv_section("📍 Position", payload.position))
        if payload.context:
            out.append(_list_section("🧠 Context", payload.context))
        if payload.market:
            out.append(_kv_section("📊 Market", payload.market))
        if payload.actions:
            out.append(_list_section("⚡ Action", payload.actions))
        if payload.system:
            out.append(_kv_section("🖥 System", payload.system))
        return out

    def _footer(self, payload: NotificationPayload) -> str:
        """⚙️ Mode  ·  Sizing — always last line when mode info is present."""
        tags = []
        if payload.mode_label:
            tags.append(payload.mode_label)
        if payload.sizing_label:
            tags.append(payload.sizing_label)
        return f"\n<i>⚙️ {' · '.join(tags)}</i>" if tags else ""


# ─── Section rendering utilities ──────────────────────────────────────────────

def _kv_section(header: str, data: dict) -> str:
    """
    📍 Position
      • Direction: LONG · 1 lot
      • Entry: ₹2,500.00
    """
    lines = [f"\n<b>{header}</b>"]
    for k, v in data.items():
        lines.append(f"  • {k}: {v}")
    return "\n".join(lines)


def _list_section(header: str, items: list) -> str:
    """
    🧠 Context
      • Stop-loss level reached
      • System will NOT auto-execute
    """
    lines = [f"\n<b>{header}</b>"]
    for item in items:
        lines.append(f"  • {item}")
    return "\n".join(lines)


def _ist_ts(dt: Optional[datetime]) -> str:
    """Format datetime as 'D Mon HH:MM' in IST."""
    if dt is None:
        from django.utils import timezone
        dt = timezone.now()
    ist_dt = dt.astimezone(_IST)
    return ist_dt.strftime("%-d %b %H:%M")


# ─── Module-level convenience ─────────────────────────────────────────────────

_formatter = TelegramMessageFormatter()


def format_notification(payload: NotificationPayload) -> str:
    """Render a NotificationPayload to an HTML Telegram string."""
    return _formatter.format(payload)


def mode_labels_from_config(config) -> tuple[str, str]:
    """
    Extract (mode_label, sizing_label) strings from a TradingCoreConfig instance.
    Convenience to avoid repeating the same two attribute calls everywhere.
    """
    return (
        config.get_notification_level_display_short(),
        config.get_position_sizing_display_short(),
    )
