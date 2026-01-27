# Analytics App Documentation

**Location**: `apps/analytics/`

The analytics app tracks trading performance and implements a learning system to improve strategy parameters over time.

---

## What This App Does

1. **P&L Tracking** - Daily, weekly, monthly performance
2. **Trade Analysis** - Detailed analysis of each trade
3. **Pattern Discovery** - Find profitable/unprofitable patterns
4. **Parameter Optimization** - Suggest parameter improvements
5. **Learning Engine** - Continuous improvement system

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | 7 analytics models |
| `services/learning_engine.py` | Learning orchestration |
| `services/pattern_recognition.py` | Pattern discovery |
| `services/parameter_optimizer.py` | Parameter suggestions |
| `tasks.py` | Scheduled analytics tasks |
| `views.py` | API endpoints |

---

## Key Models

### DailyPnL

Daily performance summary per account.

```python
# Fields
account = ForeignKey(BrokerAccount)
date = DateField()
realized_pnl = DecimalField()      # Closed positions P&L
unrealized_pnl = DecimalField()    # Open positions P&L
total_pnl = DecimalField()         # Combined

# Trade Counts
trades_count = IntegerField()
winning_trades = IntegerField()
losing_trades = IntegerField()

# Capital
starting_capital = DecimalField()
ending_capital = DecimalField()
max_drawdown = DecimalField()

# Methods
def calculate_win_rate(self):
    if self.trades_count == 0:
        return 0
    return (self.winning_trades / self.trades_count) * 100
```

### Performance

Weekly/Monthly/Yearly aggregated metrics.

```python
# Fields
account = ForeignKey(BrokerAccount)
period_type = CharField()          # WEEKLY, MONTHLY, YEARLY
period_start = DateField()
period_end = DateField()

# Metrics
total_pnl = DecimalField()
total_trades = IntegerField()
winning_trades = IntegerField()
losing_trades = IntegerField()
win_rate = DecimalField()
profit_factor = DecimalField()     # Gross profit / Gross loss
sharpe_ratio = DecimalField()
max_drawdown = DecimalField()

# By Strategy
strategy_performance = JSONField()  # P&L breakdown by strategy
```

### LearningSession

Tracks a learning analysis session.

```python
# Fields
name = CharField()
status = CharField()               # RUNNING, STOPPED, PAUSED, COMPLETED
started_at = DateTimeField()
stopped_at = DateTimeField()

# Controls
min_trades_required = IntegerField()    # Min trades to analyze
confidence_threshold = DecimalField()   # Min confidence (%)

# Results
trades_analyzed = IntegerField()
patterns_discovered = IntegerField()
parameters_adjusted = IntegerField()

# Improvement
pre_learning_win_rate = DecimalField()
post_learning_win_rate = DecimalField()
improvement_pct = DecimalField()
```

### TradePerformance

Detailed analysis of each trade.

```python
# Fields
position = OneToOneField(Position)
entry_conditions = JSONField()     # Market state at entry
exit_conditions = JSONField()      # Market state at exit

# Scoring
entry_score = IntegerField()       # 0-100 quality score
exit_score = IntegerField()        # 0-100 quality score
entry_time_quality = CharField()   # EXCELLENT, GOOD, AVERAGE, POOR

# Excursions
max_favorable_excursion = DecimalField()   # Best price reached
max_adverse_excursion = DecimalField()     # Worst price reached
hold_duration_minutes = IntegerField()

# Lessons
what_worked = TextField()
what_failed = TextField()
lessons_learned = TextField()

# Pattern Matching
similar_patterns_count = IntegerField()
pattern_success_rate = DecimalField()
```

### LearningPattern

Discovered patterns from trade analysis.

```python
# Fields
session = ForeignKey(LearningSession)
pattern_type = CharField()         # ENTRY_TIMING, STRIKE_SELECTION, etc.
name = CharField()
description = TextField()
conditions = JSONField()           # Pattern definition

# Statistics
occurrences = IntegerField()
profitable_occurrences = IntegerField()
success_rate = DecimalField()
confidence_score = DecimalField()
avg_profit = DecimalField()
avg_loss = DecimalField()

# Status
is_actionable = BooleanField()     # Use in trading?
recommendation = TextField()
validation_status = CharField()    # ACTIVE, TESTING, INVALIDATED
```

### ParameterAdjustment

Suggested parameter changes.

```python
# Fields
session = ForeignKey(LearningSession)
parameter_name = CharField()
parameter_category = CharField()   # strategy, risk, entry, exit
current_value = CharField()
suggested_value = CharField()
reason = TextField()
supporting_data = JSONField()

# Assessment
expected_improvement_pct = DecimalField()
confidence = DecimalField()
risk_level = CharField()           # LOW, MEDIUM, HIGH

# Workflow
status = CharField()               # SUGGESTED, APPROVED, APPLIED, REJECTED
reviewed_by = CharField()
reviewed_at = DateTimeField()
review_notes = TextField()

# Testing
applied_at = DateTimeField()
actual_improvement_pct = DecimalField()  # After implementation
```

---

## Learning Engine

**File**: `services/learning_engine.py`

### Starting a Learning Session

```python
from apps.analytics.services.learning_engine import LearningEngine

engine = LearningEngine(min_trades=10, confidence_threshold=70.0)

# Start new session
session = engine.start_learning("Weekly Analysis")

# Run analysis
trades_analyzed = engine.analyze_trades(session)
patterns_found = engine.discover_patterns(session)
suggestions = engine.suggest_improvements(session)
metrics = engine.calculate_metrics(session, 'weekly')

# Stop when done
engine.stop_learning(session)
```

### Trade Analysis

```python
# Analyze all closed positions
count = engine.analyze_trades(session)

# For each position:
# 1. Calculate entry/exit quality scores
# 2. Find max favorable/adverse excursion
# 3. Assess entry timing quality
# 4. Generate lessons learned
# 5. Create TradePerformance record
```

---

## Pattern Recognition

**File**: `services/pattern_recognition.py`

### Discovering Patterns

```python
from apps.analytics.services.pattern_recognition import PatternRecognizer

recognizer = PatternRecognizer(session)

# Discover all patterns
total = recognizer.discover_all_patterns()

# Or discover specific types
recognizer.discover_entry_timing_patterns()
recognizer.discover_exit_timing_patterns()
recognizer.discover_market_condition_patterns()
```

### Pattern Types

| Type | Description |
|------|-------------|
| `ENTRY_TIMING` | Which hours have best win rates |
| `EXIT_TIMING` | Which days have best exits |
| `STRIKE_SELECTION` | Which strike distances work |
| `MARKET_CONDITION` | VIX levels, trends, etc. |
| `DELTA_BEHAVIOR` | Option delta patterns |
| `VIX_PATTERN` | VIX-based patterns |

### Example: Entry Timing Pattern

```python
# Analysis finds:
# - 10:00 AM entries have 78% win rate
# - 9:30 AM entries have 45% win rate

# Creates pattern:
LearningPattern.objects.create(
    session=session,
    pattern_type='ENTRY_TIMING',
    name='10AM_optimal_entry',
    description='Entries at 10:00 AM have significantly higher win rate',
    conditions={'entry_hour': 10},
    occurrences=50,
    profitable_occurrences=39,
    success_rate=78.0,
    is_actionable=True,
    recommendation='Prefer 10:00 AM entries over 9:30 AM'
)
```

---

## Parameter Optimizer

**File**: `services/parameter_optimizer.py`

### Generating Suggestions

```python
from apps.analytics.services.parameter_optimizer import ParameterOptimizer

optimizer = ParameterOptimizer(session)

# Generate all suggestions
count = optimizer.generate_suggestions()

# Types of suggestions:
# - Timing adjustments (entry_window_start, exit_day)
# - Strike adjustments (delta percentage)
# - Risk adjustments (stop_loss_pct)
```

### Example Suggestion

```python
ParameterAdjustment.objects.create(
    session=session,
    parameter_name='entry_window_start',
    parameter_category='strategy',
    current_value='09:30',
    suggested_value='10:00',
    reason='10:00 AM entries show 78% win rate vs 45% at 9:30',
    expected_improvement_pct=15.0,
    confidence=85.0,
    risk_level='LOW',
    status='SUGGESTED'
)
```

### Applying Suggestions

```python
# Review and approve
optimizer.apply_suggestion(suggestion, reviewed_by='admin')

# Or reject
optimizer.reject_suggestion(suggestion, reviewed_by='admin', reason='Too risky')
```

---

## Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `generate_daily_pnl_report` | 4:00 PM | Daily P&L report |
| `update_learning_patterns` | 5:00 PM | Pattern analysis |
| `send_weekly_summary` | Friday 6:00 PM | Weekly report |

### Daily P&L Report

```python
@shared_task
def generate_daily_pnl_report():
    for account in BrokerAccount.objects.filter(is_active=True):
        # Calculate today's P&L
        pnl = account.get_todays_pnl()
        trades = get_todays_trades(account)

        # Create DailyPnL record
        DailyPnL.objects.create(
            account=account,
            date=date.today(),
            total_pnl=pnl,
            trades_count=len(trades),
            ...
        )

    # Send Telegram summary
    send_daily_pnl_telegram()
```

### Weekly Summary

```python
@shared_task
def send_weekly_summary():
    # Aggregate weekly performance
    # Top winners/losers
    # Strategy breakdown
    # Send comprehensive Telegram report
```

---

## How to Study This App

1. **Start with `models.py`** - Understand the 7 models
2. **Read `learning_engine.py`** - Core orchestration
3. **Study `pattern_recognition.py`** - Pattern discovery
4. **Check `parameter_optimizer.py`** - Suggestions
5. **Review `tasks.py`** - Automated reports

---

## Learning Workflow

```
Daily Trading
      ↓
End of Day: generate_daily_pnl_report()
      ↓
DailyPnL records created
      ↓
5:00 PM: update_learning_patterns()
      ↓
Learning Engine:
├── Analyze recent trades
├── Calculate entry/exit scores
├── Identify patterns
├── Generate suggestions
└── Calculate metrics
      ↓
Patterns discovered (LearningPattern)
Suggestions created (ParameterAdjustment)
      ↓
Human Review:
├── Review suggestions
├── Approve/reject
└── Apply changes
      ↓
Track actual improvement
```

---

## Performance Metrics

| Metric | Description |
|--------|-------------|
| Win Rate | Winning trades / Total trades |
| Profit Factor | Gross profit / Gross loss |
| Sharpe Ratio | Risk-adjusted return |
| Max Drawdown | Largest peak-to-trough decline |
| Avg Profit | Average winning trade size |
| Avg Loss | Average losing trade size |

---

## Common Tasks for Developers

### View Daily P&L

```python
from apps.analytics.models import DailyPnL

# Get today's P&L for account
pnl = DailyPnL.objects.get(
    account=account,
    date=date.today()
)
print(f"P&L: {pnl.total_pnl}, Win Rate: {pnl.calculate_win_rate()}%")
```

### Run Learning Analysis

```python
from apps.analytics.services.learning_engine import LearningEngine

engine = LearningEngine()
session = engine.start_learning("Manual Analysis")
engine.analyze_trades(session)
engine.discover_patterns(session)
summary = engine.get_session_summary(session)
engine.stop_learning(session)
```

### View Patterns

```python
from apps.analytics.models import LearningPattern

patterns = LearningPattern.objects.filter(
    is_actionable=True,
    success_rate__gte=70
).order_by('-success_rate')

for p in patterns:
    print(f"{p.name}: {p.success_rate}% ({p.occurrences} trades)")
```

---

## Key Features

1. **Automated P&L Tracking** - Daily, weekly, monthly
2. **Trade Quality Scoring** - Entry/exit scoring 0-100
3. **Pattern Discovery** - Finds profitable patterns
4. **Suggestion System** - AI-generated improvements
5. **Human-in-the-Loop** - Suggestions require approval
6. **Improvement Tracking** - Measures actual vs expected

---

*For questions, check the code comments or ask the team.*
