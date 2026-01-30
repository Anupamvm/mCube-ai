"""
Background Tasks & Scheduler for mCube Trading System

Orchestrates all automated trading tasks:
- Pre-market setup
- Trade entry
- Position monitoring
- Position closing
- End-of-day analysis

Uses Celery for all background task processing.
"""

import datetime as dt
import pytz
from celery import shared_task
from django.utils import timezone

from .models import TradingSchedule, NseFlag, BkLog, DayReport, TodaysPosition

IST = pytz.timezone('Asia/Kolkata')

__all__ = [
    'task_scheduler',
    'install_daily_task_scheduler',
    'setup_day_task',
    'start_day_task',
    'monitor_task',
    'closing_day_task',
    'analyse_day_task',
    'stop_all_scheduled_tasks',
]


# ========== Utility Functions ==========

def _tz_now() -> dt.datetime:
    """Get current time in IST"""
    return dt.datetime.now(IST)


def _today_ist_date() -> dt.date:
    """Get today's date in IST"""
    return _tz_now().date()


def _booly(val: str | bool | int | None, default: bool = False) -> bool:
    """Convert string/int to boolean"""
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}


def _log(level: str, action: str, message: str, task_name: str = "") -> None:
    """Log to BkLog and console"""
    ts = _tz_now().isoformat()
    line = f"[{ts}] [{level.upper()}] {action}: {message}"
    print(line)

    try:
        BkLog.objects.create(
            level=level,
            action=action,
            message=message,
            background_task=task_name
        )
    except Exception as e:
        print(f"Failed to write to BkLog: {e}")


def _get_times_for(date_: dt.date) -> dict:
    """
    Get trading times for a specific date

    Returns dict with timezone-aware datetimes for all trading events.
    If TradingSchedule doesn't exist for the date, uses defaults.
    """
    try:
        sched, _ = TradingSchedule.objects.get_or_create(date=date_)
        return sched.as_datetimes(IST)
    except Exception as e:
        _log("error", "_get_times_for", f"Error getting schedule: {e}")
        # Return default times
        def at(h, m, s=0):
            return IST.localize(dt.datetime.combine(date_, dt.time(h, m, s)))

        return {
            't_open': at(9, 15, 10),
            't_take_trade': at(9, 30, 0),
            't_last_trade': at(10, 15, 0),
            't_close_pos': at(15, 25, 30),
            't_mkt_close': at(15, 32, 0),
            't_close_day': at(15, 45, 0),
        }


def _trading_enabled() -> bool:
    """
    Check if automated trading is enabled

    Returns True if NseFlag('autoTradingEnabled') is set to truthy value
    """
    try:
        enabled = NseFlag.get_bool('autoTradingEnabled', default=False)
        return enabled
    except Exception:
        return False


# ========== Celery Tasks ==========

@shared_task(name="setup_day_task")
def setup_day_task():
    """
    Pre-market setup task (9:15 AM)

    Sets up the day by:
    - Checking if market is open/tradable
    - Fetching VIX data
    - Calculating daily delta (volatility target)
    - Checking for open positions
    - Running technical analysis
    - Fetching Trendlyne data
    """
    task_name = "setup_day_task"
    _log("info", task_name, "Starting pre-market setup...")

    try:
        # Import here to avoid circular imports
        from apps.data.broker_integration import MarketDataUpdater
        from apps.data.trendlyne import get_all_trendlyne_data
        from tools.yahoofin import get_nse_vix

        # 1. Fetch Trendlyne data
        _log("info", task_name, "Fetching Trendlyne data...")
        try:
            get_all_trendlyne_data()
            _log("info", task_name, "Trendlyne data fetched successfully")
        except Exception as e:
            _log("error", task_name, f"Trendlyne fetch failed: {e}")

        # 2. Get VIX data
        _log("info", task_name, "Fetching VIX data...")
        try:
            vix_symbol, vix_value = get_nse_vix()
            NseFlag.set("nseVix", str(vix_value), "Current VIX value")

            # Categorize VIX
            if vix_value > 25:
                vix_status = "VHigh"
            elif vix_value > 20:
                vix_status = "High"
            elif vix_value < 12:
                vix_status = "VLow"
            elif vix_value < 15:
                vix_status = "Low"
            else:
                vix_status = "Normal"

            NseFlag.set("vixStatus", vix_status, "VIX status category")
            _log("info", task_name, f"VIX: {vix_value} ({vix_status})")
        except Exception as e:
            _log("error", task_name, f"VIX fetch failed: {e}")
            NseFlag.set("vixStatus", "Unknown")

        # 3. Update market data
        _log("info", task_name, "Updating pre-market data...")
        try:
            from apps.data.broker_integration import ScheduledDataUpdater
            stats = ScheduledDataUpdater.update_pre_market_data()
            _log("info", task_name, f"Pre-market data updated: {stats}")
        except Exception as e:
            _log("error", task_name, f"Market data update failed: {e}")

        # 4. Check open positions
        _log("info", task_name, "Checking open positions...")
        try:
            from tools.neo import isOpenPos
            has_open_pos = isOpenPos()
            NseFlag.set("openPositions", str(has_open_pos), "Has open positions")
            _log("info", task_name, f"Open positions: {has_open_pos}")
        except Exception as e:
            _log("warning", task_name, f"Could not check positions: {e}")
            NseFlag.set("openPositions", "false")

        # 5. Calculate daily delta (volatility-based position sizing)
        daily_delta = 0.35  # Default 35 bps
        vix_float = NseFlag.get_float("nseVix", 15.0)
        if vix_float > 25:
            daily_delta = 0.50  # Increase delta in high volatility
        elif vix_float < 12:
            daily_delta = 0.25  # Decrease delta in low volatility

        NseFlag.set("dailyDelta", str(daily_delta), "Daily volatility target")

        # 6. Determine if day is tradable
        is_tradable = True
        reasons = []

        # Check if it's a weekday
        today = _today_ist_date()
        if today.weekday() >= 5:  # Saturday or Sunday
            is_tradable = False
            reasons.append("Weekend")

        # Check VIX
        if vix_status == "VHigh":
            is_tradable = False
            reasons.append(f"VIX too high ({vix_float})")

        # Check for major events (you can enhance this)
        is_major_event = NseFlag.get_bool("isMajorEventDay", False)
        if is_major_event:
            is_tradable = False
            reasons.append("Major event day")

        NseFlag.set("isDayTradable", str(is_tradable), f"Tradable: {', '.join(reasons) if not is_tradable else 'Yes'}")

        _log("info", task_name, f"Day setup complete. Tradable: {is_tradable}")

        return {"status": "success", "tradable": is_tradable}

    except Exception as e:
        _log("error", task_name, f"Setup failed: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="start_day_task")
def start_day_task():
    """
    Trade entry task (9:30 AM)

    Evaluates market conditions and takes positions if:
    - Day is tradable
    - No existing open positions
    - Market conditions are favorable
    """
    task_name = "start_day_task"
    _log("info", task_name, "Checking for trade entry...")

    try:
        # Check if day is tradable
        if not NseFlag.get_bool("isDayTradable"):
            _log("info", task_name, "Day not tradable, skipping entry")
            return {"status": "skipped", "reason": "Not tradable"}

        # Check if already have open positions
        if NseFlag.get_bool("openPositions"):
            _log("info", task_name, "Already have open positions, skipping entry")
            return {"status": "skipped", "reason": "Already in position"}

        # Import signal generator
        from apps.data.signals import SignalGenerator
        from apps.data.validators import TradeValidator

        _log("info", task_name, "Scanning for trading opportunities...")

        # Generate signals for NIFTY
        generator = SignalGenerator()
        signal = generator.generate_index_signal("NIFTY")

        if signal.confidence < 60:
            _log("info", task_name, f"Signal confidence too low: {signal.confidence}")
            return {"status": "skipped", "reason": "Low confidence"}

        # Validate the trade
        validator = TradeValidator()

        # Determine trade type based on signal
        if signal.signal.name in ["STRONG_BUY", "BUY"]:
            trade_type = "FUTURES_LONG"
        elif signal.signal.name in ["STRONG_SELL", "SELL"]:
            trade_type = "FUTURES_SHORT"
        else:
            _log("info", task_name, f"Signal neutral: {signal.signal.name}")
            return {"status": "skipped", "reason": "Neutral signal"}

        # Get current expiry
        from apps.data.broker_integration import MarketDataUpdater
        updater = MarketDataUpdater()
        expiry = updater._get_current_expiry()

        # Validate
        validation = validator.validate_trade(trade_type, "NIFTY", expiry)

        if not validation.approved:
            _log("warning", task_name, f"Trade validation failed: {validation.warnings}")
            return {"status": "rejected", "validation": validation.warnings}

        _log("info", task_name, f"Trade approved: {trade_type} on NIFTY, Confidence: {validation.confidence}")

        # Note: Actual order placement should be done through the trading module
        # This is a placeholder for the trading logic
        return {
            "status": "approved",
            "trade": trade_type,
            "confidence": validation.confidence,
        }

    except Exception as e:
        _log("error", task_name, f"Entry task failed: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="monitor_task")
def monitor_task():
    """
    Position monitoring task

    Monitors:
    - Current P&L
    - Position changes
    - Stop loss violations
    - Profit target achievement
    """
    task_name = "monitor_task"
    _log("info", task_name, "Monitoring positions...")

    try:
        # Check if we have positions
        if not NseFlag.get_bool("openPositions"):
            _log("info", task_name, "No open positions to monitor")
            return {"status": "skipped"}

        # Get current P&L (placeholder - implement actual broker integration)
        current_pnl = NseFlag.get_float("currentPos", 0.0)

        _log("info", task_name, f"Current P&L: ₹{current_pnl:,.2f}")

        # Get last informed P&L
        informed_pnl = NseFlag.get_float("informedPos", 0.0)

        # If P&L changed significantly, send alert
        if abs(current_pnl - informed_pnl) > 5000:
            _log("warning", task_name, f"P&L changed significantly: ₹{current_pnl:,.2f} (was ₹{informed_pnl:,.2f})")
            NseFlag.set("informedPos", str(current_pnl))

        # Check stop loss
        stop_loss = NseFlag.get_float("stopLossLimit", -15000)
        if current_pnl < stop_loss:
            _log("critical", task_name, f"STOP LOSS HIT! P&L: ₹{current_pnl:,.2f}, Limit: ₹{stop_loss:,.2f}")
            return {"status": "stop_loss_hit", "pnl": current_pnl}

        return {"status": "success", "pnl": current_pnl}

    except Exception as e:
        _log("error", task_name, f"Monitor task failed: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="closing_day_task")
def closing_day_task():
    """
    Position closing task (3:25 PM)

    Closes positions if:
    - Profit target achieved
    - It's expiry day
    - Market closing time approaching
    """
    task_name = "closing_day_task"
    _log("info", task_name, "Checking if positions should be closed...")

    try:
        if not NseFlag.get_bool("openPositions"):
            _log("info", task_name, "No open positions to close")
            return {"status": "skipped"}

        # Get current P&L
        current_pnl = NseFlag.get_float("currentPos", 0.0)

        # Get profit target
        profit_target = NseFlag.get_float("minDailyProfitTarget", 5000)

        # Check if profit target achieved
        should_close = False
        reason = ""

        if current_pnl >= profit_target:
            should_close = True
            reason = f"Profit target achieved (₹{current_pnl:,.2f} >= ₹{profit_target:,.2f})"

        # Check if it's expiry day
        days_to_expiry = NseFlag.get_int("daysToExpiry", 7)
        if days_to_expiry <= 0:
            should_close = True
            reason = "Expiry day - closing all positions"

        # Check if it's close to market close (force close after 3:29 PM)
        now = _tz_now()
        market_close_time = now.replace(hour=15, minute=29, second=0)
        if now >= market_close_time:
            should_close = True
            reason = "Market closing time - force closing positions"

        if should_close:
            _log("info", task_name, f"Closing positions: {reason}")
            # Note: Actual position closing should be done through the trading module
            NseFlag.set("openPositions", "false")
            return {"status": "closed", "pnl": current_pnl, "reason": reason}
        else:
            _log("info", task_name, f"Keeping positions open. P&L: ₹{current_pnl:,.2f}, Target: ₹{profit_target:,.2f}")
            return {"status": "open", "pnl": current_pnl}

    except Exception as e:
        _log("error", task_name, f"Closing task failed: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="analyse_day_task")
def analyse_day_task():
    """
    End-of-day analysis task (3:45 PM)

    Creates daily report with:
    - All positions taken
    - Total P&L
    - Number of legs
    - Performance summary
    """
    task_name = "analyse_day_task"
    _log("info", task_name, "Running EOD analysis...")

    try:
        today = _today_ist_date()

        # Get final P&L
        final_pnl = NseFlag.get_float("currentPos", 0.0)

        # Create/update day report
        report, created = DayReport.objects.update_or_create(
            date=today,
            defaults={
                'day_of_week': today.strftime("%A"),
                'pnl': final_pnl,
                'num_legs': 0,
                'is_closed': not NseFlag.get_bool("openPositions"),
            }
        )

        _log("info", task_name, f"Day report created: {report}")

        # Reset flags for next day
        NseFlag.set("informedPos", "0")
        NseFlag.set("currentPos", "0")

        return {"status": "success", "report_id": report.id}

    except Exception as e:
        _log("error", task_name, f"Analysis task failed: {e}")
        return {"status": "error", "error": str(e)}


# ========== Task Scheduler ==========

@shared_task(name="task_scheduler")
def task_scheduler(target_date_iso: str = None):
    """
    Master scheduler - triggers all daily tasks via Celery

    This task runs once per day and schedules all intraday tasks.
    Only runs if autoTradingEnabled flag is True.
    """
    task_name = "task_scheduler"
    _log("info", task_name, "Master scheduler running...")

    # Check if trading is enabled
    if not _trading_enabled():
        msg = "Auto-trading is disabled. Skipping task scheduling."
        _log("info", task_name, msg)
        return {"status": "disabled"}

    # Resolve date
    if target_date_iso:
        try:
            day = dt.datetime.strptime(target_date_iso, "%Y-%m-%d").date()
        except ValueError:
            day = _today_ist_date()
            _log("warning", task_name, f"Invalid date '{target_date_iso}', using {day}")
    else:
        day = _today_ist_date()

    # Check if schedule is enabled for this day
    try:
        sched = TradingSchedule.objects.filter(date=day).first()
        if sched and not sched.enabled:
            msg = f"Trading disabled for {day}"
            _log("info", task_name, msg)
            return {"status": "disabled", "date": str(day)}
    except Exception:
        pass

    # Get times for the day
    times = _get_times_for(day)

    _log("info", task_name, f"Scheduling tasks for {day}...")

    # Schedule tasks using Celery's apply_async with eta
    # Note: For production, use Celery Beat for recurring schedules

    setup_day_task.apply_async(eta=times['t_open'])
    start_day_task.apply_async(eta=times['t_take_trade'])
    monitor_task.apply_async(eta=times['t_take_trade'])
    closing_day_task.apply_async(eta=times['t_close_pos'])
    analyse_day_task.apply_async(eta=times['t_close_day'])

    msg = f"All tasks scheduled for {day}"
    _log("info", task_name, msg)

    return {"status": "success", "date": str(day), "times": {k: v.isoformat() for k, v in times.items()}}


# ========== Installation & Management ==========

def install_daily_task_scheduler():
    """
    Install the master scheduler (run once on startup)

    This function creates default NseFlag entries and TradingSchedule.
    With Celery, scheduling is handled by Celery Beat (see celery.py).
    """
    action = "install_daily_task_scheduler"
    _log("info", action, "Installing daily task scheduler...")

    # Create default flags
    _ensure_default_flags()

    # Create TradingSchedule for today and tomorrow
    try:
        today = _today_ist_date()
        tomorrow = today + dt.timedelta(days=1)

        for date in [today, tomorrow]:
            sched, created = TradingSchedule.objects.get_or_create(date=date)
            if created:
                _log("info", action, f"Created TradingSchedule for {date}")
    except Exception as e:
        _log("error", action, f"Error creating schedule: {e}")

    print(f"\n✅ Task scheduler initialized!")
    print(f"   Trading tasks are managed by Celery Beat.")
    print(f"   Make sure Celery worker and beat are running.")

    return {"status": "success"}


def stop_all_scheduled_tasks():
    """
    Emergency stop - revokes all pending Celery tasks

    Use this to cancel all pending tasks.
    """
    action = "stop_all_scheduled_tasks"
    try:
        from mcube_ai.celery import app

        # Purge all pending tasks
        app.control.purge()

        _log("info", action, "Purged all pending Celery tasks")
        print("✅ Purged all pending Celery tasks")
        return {"status": "success"}
    except Exception as e:
        _log("error", action, f"Error stopping tasks: {e}")
        return {"status": "error", "error": str(e)}


def _ensure_default_flags():
    """Create default NseFlag entries"""
    defaults = {
        # Core toggle
        "autoTradingEnabled": ("false", "Enable/disable automated trading"),

        # Market status
        "isDayTradable": ("true", "Whether it's safe to trade today"),
        "nseVix": ("15.0", "Current VIX value"),
        "vixStatus": ("Normal", "VIX status: VHigh/High/Normal/Low/VLow"),
        "isMajorEventDay": ("false", "Is today a major event day (budget, election, etc.)"),

        # Positions
        "openPositions": ("false", "Do we have open positions"),
        "currentPos": ("0", "Current P&L"),
        "informedPos": ("0", "Last reported P&L"),

        # Risk parameters
        "dailyDelta": ("0.35", "Daily volatility target (as percentage)"),
        "stopLossLimit": ("-15000", "Stop loss limit in rupees"),
        "minDailyProfitTarget": ("5000", "Minimum daily profit target"),
        "daysToExpiry": ("7", "Days to F&O expiry"),

        # Position sizing
        "lotSize": ("50", "NIFTY lot size"),
        "maxTradeQnty": ("2", "Maximum lots to trade"),
    }

    created_count = 0
    for flag, (value, desc) in defaults.items():
        try:
            _, created = NseFlag.objects.get_or_create(
                flag=flag,
                defaults={'value': value, 'description': desc}
            )
            if created:
                created_count += 1
        except Exception as e:
            _log("error", "_ensure_default_flags", f"Error creating {flag}: {e}")

    _log("info", "_ensure_default_flags", f"Ensured {len(defaults)} flags, created {created_count}")
