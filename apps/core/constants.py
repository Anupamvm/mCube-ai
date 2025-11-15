"""
System-wide constants for mCube Trading System

This module contains all configuration constants used across the application.
These values are based on the trading rules and risk parameters defined in
the system design document.
"""

from decimal import Decimal

# ============================================================================
# BROKER CONFIGURATION
# ============================================================================

BROKER_KOTAK = 'KOTAK'
BROKER_ICICI = 'ICICI'

BROKER_CHOICES = [
    (BROKER_KOTAK, 'Kotak Securities'),
    (BROKER_ICICI, 'ICICI Securities'),
]

# ============================================================================
# ACCOUNT CONFIGURATION
# ============================================================================

# Kotak Account - Options Trading
KOTAK_CONFIG = {
    'allocated_capital': Decimal('60000000'),  # ₹6 Crores
    'strategy': 'WEEKLY_NIFTY_STRANGLE',
    'max_margin_usage': Decimal('0.40'),  # 40% of total capital
    'initial_margin_for_first_trade': Decimal('0.50'),  # 50% of available
    'max_concurrent_positions': 1,  # ONE POSITION RULE
    'stop_loss_per_position': Decimal('100000'),  # ₹1 Lakh
    'daily_loss_limit': Decimal('200000'),  # ₹2 Lakhs
    'weekly_profit_target': Decimal('175000'),  # ₹1.75 Lakhs
    'monthly_profit_target': Decimal('700000'),  # ₹7 Lakhs
}

# ICICI Account - Futures Trading
ICICI_CONFIG = {
    'allocated_capital': Decimal('12000000'),  # ₹1.2 Crores
    'max_leverage': 5,
    'strategy': 'LLM_VALIDATED_FUTURES',
    'max_total_exposure': Decimal('60000000'),  # ₹6 Crores
    'single_position_max': Decimal('15000000'),  # ₹1.5 Crores
    'max_concurrent_positions': 1,  # ONE POSITION RULE
    'initial_margin_for_first_trade': Decimal('0.50'),  # 50% of available
    'per_trade_risk': Decimal('60000'),  # ₹60,000
    'daily_loss_limit': Decimal('150000'),  # ₹1.5 Lakhs
    'weekly_profit_target': Decimal('150000'),  # ₹1.5 Lakhs
    'monthly_profit_target': Decimal('600000'),  # ₹6 Lakhs
}

# ============================================================================
# POSITION & TRADE CONSTANTS
# ============================================================================

POSITION_STATUS_ACTIVE = 'ACTIVE'
POSITION_STATUS_CLOSED = 'CLOSED'

POSITION_STATUS_CHOICES = [
    (POSITION_STATUS_ACTIVE, 'Active'),
    (POSITION_STATUS_CLOSED, 'Closed'),
]

DIRECTION_LONG = 'LONG'
DIRECTION_SHORT = 'SHORT'
DIRECTION_NEUTRAL = 'NEUTRAL'  # For strangles

DIRECTION_CHOICES = [
    (DIRECTION_LONG, 'Long'),
    (DIRECTION_SHORT, 'Short'),
    (DIRECTION_NEUTRAL, 'Neutral'),
]

# ============================================================================
# STRATEGY CONSTANTS
# ============================================================================

STRATEGY_KOTAK_STRANGLE = 'WEEKLY_NIFTY_STRANGLE'
STRATEGY_ICICI_FUTURES = 'LLM_VALIDATED_FUTURES'

STRATEGY_CHOICES = [
    (STRATEGY_KOTAK_STRANGLE, 'Weekly Nifty Strangle'),
    (STRATEGY_ICICI_FUTURES, 'LLM Validated Futures'),
]

# ============================================================================
# KOTAK STRANGLE STRATEGY PARAMETERS
# ============================================================================

KOTAK_STRANGLE_PARAMS = {
    'instrument': 'NIFTY',
    'base_delta_pct': Decimal('0.50'),  # 0.5% base delta
    'min_days_to_expiry': 1,  # Skip if < 1 day
    'min_profit_pct_to_exit': Decimal('50.00'),  # 50% profit minimum for EOD exit
    'exit_day': 'THURSDAY',
    'exit_time': '15:15',  # 3:15 PM IST
    'delta_rebalance_threshold': 300,  # Alert if |net_delta| > 300
    'target_profit_pct': Decimal('70.00'),  # 70% of premium
    'stop_loss_pct': Decimal('100.00'),  # 100% of premium (total loss)

    # VIX-based delta adjustments
    'vix_normal_threshold': 15,
    'vix_elevated_threshold': 18,
    'vix_elevated_multiplier': Decimal('1.10'),
    'vix_high_multiplier': Decimal('1.20'),
}

# ============================================================================
# ICICI FUTURES STRATEGY PARAMETERS
# ============================================================================

ICICI_FUTURES_PARAMS = {
    'min_days_to_expiry': 15,  # Skip if < 15 days
    'default_stop_loss_pct': Decimal('0.50'),  # 0.5%
    'default_target_pct': Decimal('1.00'),  # 1.0%
    'min_risk_reward_ratio': Decimal('2.0'),  # 1:2 RR minimum
    'min_profit_pct_to_exit': Decimal('50.00'),  # 50% profit minimum for EOD exit

    # Averaging parameters
    'allow_averaging': True,
    'max_average_attempts': 2,  # Maximum 2 averaging attempts
    'average_trigger_loss_pct': Decimal('1.0'),  # Average when down 1%
    'averaging_stop_loss_pct': Decimal('0.50'),  # 0.5% from new average

    # LLM validation
    'min_llm_confidence': Decimal('0.70'),  # 70% minimum
    'require_human_approval': True,

    # Screening parameters
    'min_composite_score': 65,  # Out of 100
    'oi_change_threshold_pct': Decimal('5.0'),  # 5% OI change
    'pcr_bullish_threshold': Decimal('1.3'),
    'pcr_bearish_threshold': Decimal('0.7'),
}

# ============================================================================
# MARKET TIMING CONSTANTS
# ============================================================================

MARKET_OPEN_TIME = '09:15'
MARKET_CLOSE_TIME = '15:30'
PRE_MARKET_START = '09:00'
POST_MARKET_END = '16:00'

# Entry window
ENTRY_WINDOW_START = '09:00'
ENTRY_WINDOW_END = '11:30'

# Exit times
KOTAK_EXIT_TIME = '15:15'  # Thursday exit time
MANDATORY_EXIT_TIME = '15:20'  # Friday mandatory exit

# ============================================================================
# RISK MANAGEMENT CONSTANTS
# ============================================================================

# System-wide risk limits
MAX_SYSTEM_DRAWDOWN_PCT = Decimal('15.00')  # 15% max drawdown
CIRCUIT_BREAKER_COOLDOWN_HOURS = 24

# Risk levels
RISK_LEVEL_LOW = 'LOW'
RISK_LEVEL_MEDIUM = 'MEDIUM'
RISK_LEVEL_HIGH = 'HIGH'
RISK_LEVEL_CRITICAL = 'CRITICAL'

RISK_LEVEL_CHOICES = [
    (RISK_LEVEL_LOW, 'Low'),
    (RISK_LEVEL_MEDIUM, 'Medium'),
    (RISK_LEVEL_HIGH, 'High'),
    (RISK_LEVEL_CRITICAL, 'Critical'),
]

# ============================================================================
# ENTRY FILTER CONSTANTS
# ============================================================================

FILTER_PARAMS = {
    # Global markets
    'sgx_nifty_max_change_pct': Decimal('0.5'),  # ±0.5%
    'us_markets_max_change_pct': Decimal('1.0'),  # ±1.0%

    # Nifty movement
    'nifty_1day_max_change_pct': Decimal('1.0'),  # ±1.0%
    'nifty_3day_max_change_pct': Decimal('2.0'),  # ±2.0%

    # VIX limits
    'vix_max_threshold': 20,

    # Event calendar
    'min_days_before_major_event': 5,
}

# ============================================================================
# ALERT PRIORITY CONSTANTS
# ============================================================================

ALERT_PRIORITY_INFO = 'INFO'
ALERT_PRIORITY_WARNING = 'WARNING'
ALERT_PRIORITY_CRITICAL = 'CRITICAL'

ALERT_PRIORITY_CHOICES = [
    (ALERT_PRIORITY_INFO, 'Info'),
    (ALERT_PRIORITY_WARNING, 'Warning'),
    (ALERT_PRIORITY_CRITICAL, 'Critical'),
]

ALERT_CHANNEL_TELEGRAM = 'TELEGRAM'
ALERT_CHANNEL_EMAIL = 'EMAIL'
ALERT_CHANNEL_SMS = 'SMS'

# Alert routing rules
ALERT_ROUTING = {
    ALERT_PRIORITY_INFO: [ALERT_CHANNEL_TELEGRAM],
    ALERT_PRIORITY_WARNING: [ALERT_CHANNEL_TELEGRAM, ALERT_CHANNEL_EMAIL],
    ALERT_PRIORITY_CRITICAL: [ALERT_CHANNEL_TELEGRAM, ALERT_CHANNEL_EMAIL, ALERT_CHANNEL_SMS],
}

# ============================================================================
# ORDER CONSTANTS
# ============================================================================

ORDER_TYPE_MARKET = 'MARKET'
ORDER_TYPE_LIMIT = 'LIMIT'
ORDER_TYPE_SL = 'SL'
ORDER_TYPE_SLM = 'SLM'

ORDER_TYPE_CHOICES = [
    (ORDER_TYPE_MARKET, 'Market'),
    (ORDER_TYPE_LIMIT, 'Limit'),
    (ORDER_TYPE_SL, 'Stop Loss'),
    (ORDER_TYPE_SLM, 'Stop Loss Market'),
]

ORDER_STATUS_PENDING = 'PENDING'
ORDER_STATUS_PLACED = 'PLACED'
ORDER_STATUS_FILLED = 'FILLED'
ORDER_STATUS_PARTIAL = 'PARTIAL'
ORDER_STATUS_CANCELLED = 'CANCELLED'
ORDER_STATUS_REJECTED = 'REJECTED'

ORDER_STATUS_CHOICES = [
    (ORDER_STATUS_PENDING, 'Pending'),
    (ORDER_STATUS_PLACED, 'Placed'),
    (ORDER_STATUS_FILLED, 'Filled'),
    (ORDER_STATUS_PARTIAL, 'Partially Filled'),
    (ORDER_STATUS_CANCELLED, 'Cancelled'),
    (ORDER_STATUS_REJECTED, 'Rejected'),
]

# ============================================================================
# INSTRUMENT CONSTANTS
# ============================================================================

INSTRUMENT_NIFTY = 'NIFTY'
INSTRUMENT_BANKNIFTY = 'BANKNIFTY'
INSTRUMENT_FINNIFTY = 'FINNIFTY'

NIFTY_STRIKE_INTERVAL = 50
BANKNIFTY_STRIKE_INTERVAL = 100
FINNIFTY_STRIKE_INTERVAL = 50

# ============================================================================
# CELERY TASK SCHEDULES (in seconds)
# ============================================================================

TASK_SCHEDULE_MARKET_DATA_SYNC = 60  # Every 1 minute
TASK_SCHEDULE_OPTION_CHAIN_SYNC = 300  # Every 5 minutes
TASK_SCHEDULE_POSITION_MONITOR = 5  # Every 5 seconds
TASK_SCHEDULE_PNL_UPDATE = 10  # Every 10 seconds
TASK_SCHEDULE_RISK_CHECK = 60  # Every 1 minute
TASK_SCHEDULE_CIRCUIT_BREAKER = 30  # Every 30 seconds
TASK_SCHEDULE_OPPORTUNITY_SCAN = 1800  # Every 30 minutes

# ============================================================================
# TRADING DAYS
# ============================================================================

WEEKDAY_MONDAY = 0
WEEKDAY_TUESDAY = 1
WEEKDAY_WEDNESDAY = 2
WEEKDAY_THURSDAY = 3
WEEKDAY_FRIDAY = 4

TRADING_DAYS = [
    WEEKDAY_MONDAY,
    WEEKDAY_TUESDAY,
    WEEKDAY_WEDNESDAY,
    WEEKDAY_THURSDAY,
    WEEKDAY_FRIDAY,
]

# ============================================================================
# SECTOR ANALYSIS CONSTANTS
# ============================================================================

SECTOR_SIGNAL_BULLISH = 'STRONG_BULLISH'
SECTOR_SIGNAL_BEARISH = 'STRONG_BEARISH'
SECTOR_SIGNAL_MIXED = 'MIXED'
SECTOR_SIGNAL_NEUTRAL = 'NEUTRAL'

# ============================================================================
# OI ANALYSIS CONSTANTS
# ============================================================================

OI_SIGNAL_BULLISH = 'BULLISH'
OI_SIGNAL_BEARISH = 'BEARISH'
OI_SIGNAL_NEUTRAL = 'NEUTRAL'

# OI interpretation patterns
OI_PATTERN_LONG_BUILDUP = 'LONG_BUILDUP'  # OI ↑ + Price ↑
OI_PATTERN_SHORT_BUILDUP = 'SHORT_BUILDUP'  # OI ↑ + Price ↓
OI_PATTERN_SHORT_COVERING = 'SHORT_COVERING'  # OI ↓ + Price ↑
OI_PATTERN_LONG_UNWINDING = 'LONG_UNWINDING'  # OI ↓ + Price ↓

# ============================================================================
# LLM CONSTANTS
# ============================================================================

LLM_MODEL_DEEPSEEK = 'deepseek-coder:33b'
LLM_MAX_RETRIES = 3
LLM_TIMEOUT_SECONDS = 30

# ============================================================================
# PAPER TRADING
# ============================================================================

PAPER_TRADING_MODE = True  # Start in paper trading mode
PAPER_TRADING_INITIAL_BALANCE = Decimal('72000000')  # ₹7.2 Crores

# ============================================================================
# LOGGING LEVELS
# ============================================================================

LOG_LEVEL_DEBUG = 'DEBUG'
LOG_LEVEL_INFO = 'INFO'
LOG_LEVEL_WARNING = 'WARNING'
LOG_LEVEL_ERROR = 'ERROR'
LOG_LEVEL_CRITICAL = 'CRITICAL'
