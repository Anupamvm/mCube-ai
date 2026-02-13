"""
Task Default Configuration

Defines display names, categories, schedule defaults, and descriptions for all
Celery beat tasks. Extracted to its own module so both views.py and
decorators.py can import without circular-import issues.
"""

TASK_DEFAULT_CONFIG = {
    # =========================================================================
    # MARKET DATA TASKS
    # =========================================================================
    'morning-data-sync': {
        'display_name': 'Morning Data Sync',
        'description': 'Full morning data synchronization including market data, news, and indices',
        'schedule_type': 'crontab',
        'category': 'data',
        'default_hour': 7,
        'default_minute': 0,
        'default_days': [0, 1, 2, 3, 4],  # Weekdays
    },
    'update-pre-market-data': {
        'display_name': 'Pre-Market Data Update',
        'description': 'Fetches pre-market data before market opens',
        'schedule_type': 'crontab',
        'category': 'data',
        'default_hour': 8,
        'default_minute': 50,
        'default_days': [0, 1, 2, 3, 4],
    },
    'update-live-market-data': {
        'display_name': 'Live Market Data Update',
        'description': 'Updates live market data during trading hours',
        'schedule_type': 'recurring',
        'category': 'data',
        'default_hour': 9,
        'default_minute': 15,
        'default_recurring_start_hour': 9,
        'default_recurring_start_minute': 15,
        'default_recurring_end_hour': 15,
        'default_recurring_end_minute': 30,
        'default_recurring_interval_minutes': 5,
        'default_days': [0, 1, 2, 3, 4],
    },
    'update-post-market-data': {
        'display_name': 'Post-Market Data Update',
        'description': 'Updates data after market close for end-of-day analysis',
        'schedule_type': 'crontab',
        'category': 'data',
        'default_hour': 15,
        'default_minute': 35,
        'default_days': [0, 1, 2, 3, 4],
    },

    # =========================================================================
    # STRATEGY EXECUTION TASKS
    # =========================================================================
    'setup-trading-day': {
        'display_name': 'Setup Trading Day',
        'description': 'Prepares system for trading day (loads strategies, checks accounts)',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'default_hour': 8,
        'default_minute': 55,
        'default_days': [0, 1, 2, 3, 4],
    },
    'start-trading-day': {
        'display_name': 'Start Trading Day',
        'description': 'Initiates trading at market open',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'default_hour': 9,
        'default_minute': 15,
        'default_days': [0, 1, 2, 3, 4],
    },
    'evaluate-options-strategy': {
        'display_name': 'Evaluate Options Strategy',
        'description': 'Analyzes market conditions and selects options strategies',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'default_hour': 9,
        'default_minute': 30,
        'default_days': [0, 1, 2, 3, 4],
    },
    'start-options-trade': {
        'display_name': 'Start Options Trade',
        'description': 'Executes options trades based on strategy evaluation',
        'schedule_type': 'crontab',
        'category': 'transactions',
        'default_hour': 9,
        'default_minute': 40,
        'default_days': [0, 1, 2, 3, 4],
    },
    'batch-options-averaging': {
        'display_name': 'Options Averaging (Batch)',
        'description': 'Runs averaging logic for options positions at regular intervals',
        'schedule_type': 'recurring',
        'category': 'transactions',
        'default_hour': 9,
        'default_minute': 40,
        'default_recurring_start_hour': 9,
        'default_recurring_start_minute': 40,
        'default_recurring_end_hour': 9,
        'default_recurring_end_minute': 55,
        'default_recurring_interval_minutes': 5,
        'default_days': [0, 1, 2, 3, 4],
    },
    'batch-options-averaging-10am': {
        'display_name': 'Options Averaging (10 AM)',
        'description': 'Continues options averaging after 10 AM',
        'schedule_type': 'recurring',
        'category': 'transactions',
        'default_hour': 10,
        'default_minute': 0,
        'default_recurring_start_hour': 10,
        'default_recurring_start_minute': 0,
        'default_recurring_end_hour': 10,
        'default_recurring_end_minute': 30,
        'default_recurring_interval_minutes': 5,
        'default_days': [0, 1, 2, 3, 4],
    },
    'screen-futures-opportunities': {
        'display_name': 'Futures Screening',
        'description': 'Scans for futures trading opportunities (pre-market)',
        'schedule_type': 'crontab',
        'category': 'strategies',
        'default_hour': 8,
        'default_minute': 30,
        'default_days': [0, 1, 2, 3, 4],
    },
    'execute-futures-algorithm': {
        'display_name': 'Screen Futures Opportunities',
        'description': 'Screens futures after market stabilizes (9:40 AM). Sends TOP 3 to Telegram for confirmation. On approval, executes immediately with batching.',
        'schedule_type': 'crontab',
        'category': 'transactions',
        'default_hour': 9,
        'default_minute': 40,
        'default_days': [0, 1, 2, 3, 4],  # Mon-Fri
        'default_task_params': {
            'top_contracts': 50,
            'batch_size': 3,
            'this_month_volume': 1000,
            'next_month_volume': 800,
            'min_score': 65,
        },
        'task_param_fields': [
            {'name': 'top_contracts', 'label': 'Top Contracts by Volume', 'type': 'number',
             'min': 10, 'max': 100, 'default': 50, 'help': 'Number of contracts to analyze'},
            {'name': 'batch_size', 'label': 'Batch Size', 'type': 'number',
             'min': 1, 'max': 20, 'default': 5, 'help': 'Contracts per parallel task'},
            {'name': 'this_month_volume', 'label': 'This Month Min Volume', 'type': 'number',
             'min': 100, 'max': 10000, 'default': 1000, 'help': 'Min volume for current month contracts'},
            {'name': 'next_month_volume', 'label': 'Next Month Min Volume', 'type': 'number',
             'min': 100, 'max': 10000, 'default': 800, 'help': 'Min volume for next month contracts'},
            {'name': 'min_score', 'label': 'Min Score', 'type': 'number',
             'min': 50, 'max': 90, 'default': 65, 'help': 'Minimum score for qualification'},
        ],
    },
    'check-futures-averaging': {
        'display_name': 'Futures Averaging Check',
        'description': 'Checks and executes averaging for futures positions',
        'schedule_type': 'recurring',
        'category': 'transactions',
        'default_hour': 9,
        'default_minute': 0,
        'default_recurring_start_hour': 9,
        'default_recurring_start_minute': 30,
        'default_recurring_end_hour': 15,
        'default_recurring_end_minute': 0,
        'default_recurring_interval_minutes': 10,
        'default_days': [0, 1, 2, 3, 4],
    },
    'close-trading-day': {
        'display_name': 'Close Trading Day',
        'description': 'Closes positions and finalizes trading day',
        'schedule_type': 'crontab',
        'category': 'transactions',
        'default_hour': 15,
        'default_minute': 25,
        'default_days': [0, 1, 2, 3, 4],
    },

    # =========================================================================
    # TRADE CONFIRMATION TASKS
    # =========================================================================
    'check-confirmation-timeouts': {
        'display_name': 'Confirmation Timeout Check',
        'description': 'Checks for pending trade confirmations that exceeded timeout and triggers revalidation',
        'schedule_type': 'interval',
        'category': 'monitoring',
        'default_interval_seconds': 60,
        'default_days': [0, 1, 2, 3, 4],
    },

    # =========================================================================
    # POSITION MONITORING TASKS
    # =========================================================================
    'monitor-and-manage-positions': {
        'display_name': 'Position Monitor & Manager',
        'description': 'Monitors all positions: updates P&L, checks exit conditions, executes exits',
        'schedule_type': 'interval',
        'category': 'transactions',
        'default_interval_seconds': 60,
        'default_days': [0, 1, 2, 3, 4],
    },

    # =========================================================================
    # RISK MANAGEMENT TASKS
    # =========================================================================
    'check-risk-limits-all-accounts': {
        'display_name': 'Risk Limits Check',
        'description': 'Monitors risk limits across all trading accounts',
        'schedule_type': 'interval',
        'category': 'risk',
        'default_interval_seconds': 60,
        'default_days': [0, 1, 2, 3, 4],
    },
    'monitor-circuit-breakers': {
        'display_name': 'Circuit Breaker Monitor',
        'description': 'Monitors market circuit breakers and trading halts',
        'schedule_type': 'interval',
        'category': 'risk',
        'default_interval_seconds': 30,
        'default_days': [0, 1, 2, 3, 4],
    },

    # =========================================================================
    # REPORTING & ANALYTICS TASKS
    # =========================================================================
    'generate-daily-pnl-report': {
        'display_name': 'Daily P&L Report',
        'description': 'Generates end-of-day profit/loss report',
        'schedule_type': 'crontab',
        'category': 'reports',
        'default_hour': 16,
        'default_minute': 0,
        'default_days': [0, 1, 2, 3, 4],
    },
    'sync-benchmark-data': {
        'display_name': 'Sync Benchmark Data',
        'description': 'Syncs benchmark indices for performance comparison',
        'schedule_type': 'crontab',
        'category': 'reports',
        'default_hour': 16,
        'default_minute': 15,
        'default_days': [0, 1, 2, 3, 4],
    },
    'daily-data-aggregation': {
        'display_name': 'Daily Data Aggregation',
        'description': 'Aggregates daily trading data for analytics',
        'schedule_type': 'crontab',
        'category': 'reports',
        'default_hour': 16,
        'default_minute': 30,
        'default_days': [0, 1, 2, 3, 4],
    },
    'update-equity-curves': {
        'display_name': 'Update Equity Curves',
        'description': 'Updates equity curves for portfolio tracking',
        'schedule_type': 'crontab',
        'category': 'reports',
        'default_hour': 17,
        'default_minute': 0,
        'default_days': [0, 1, 2, 3, 4],
    },
}

# Backwards-compatible alias
TASK_CONFIG_FIELDS = TASK_DEFAULT_CONFIG

# =============================================================================
# ALGORITHM TASK GROUPS
#
# Defines task dependency tiers per algorithm.
#   own_tasks     – unique to this algorithm, always toggled
#   shared_tasks  – needed by multiple algos, only disabled when no other algo needs them
#   monitoring_tasks – position monitoring, only disabled when no algo is active
# =============================================================================
ALGORITHM_TASK_GROUPS = {
    'options': {
        'display_name': 'Options Algorithm',
        'emoji': '\U0001f3af',
        'description': 'Strangle / Iron Condor strategy',
        'own_tasks': [
            'evaluate-options-strategy',
            'start-options-trade',
            'batch-options-averaging',
            'batch-options-averaging-10am',
        ],
        'shared_tasks': [
            'setup-trading-day',
            'start-trading-day',
            'close-trading-day',
        ],
        'monitoring_tasks': [
            'monitor-and-manage-positions',
        ],
    },
    'futures': {
        'display_name': 'Futures Algorithm',
        'emoji': '\U0001f4c8',
        'description': 'Futures screening & averaging',
        'own_tasks': [
            'execute-futures-algorithm',
            'check-futures-averaging',
        ],
        'shared_tasks': [
            'setup-trading-day',
            'start-trading-day',
            'close-trading-day',
        ],
        'monitoring_tasks': [
            'monitor-and-manage-positions',
        ],
    },
}
