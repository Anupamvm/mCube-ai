# Algorithm Testing App

The `algo_test` app provides tools for testing and validating trading algorithms before live deployment.

---

## Purpose

- Test algorithm logic with various market scenarios
- Log test executions for analysis and comparison
- Monitor position P&L snapshots over time
- Save and reuse test scenarios as templates

---

## Models

### AlgoTestScenario

Stores saved test scenarios for algorithm analysis.

| Field | Type | Description |
|-------|------|-------------|
| `user` | ForeignKey | User who created the scenario |
| `name` | CharField | Scenario name |
| `description` | TextField | Detailed description |
| `strategy` | CharField | Strategy type: `options`, `futures`, or `both` |
| `inputs` | JSONField | Input parameters for the test |
| `results` | JSONField | Calculated results |
| `is_template` | BooleanField | Whether this is a public template |
| `created_at` | DateTimeField | Creation timestamp |
| `updated_at` | DateTimeField | Last update timestamp |

### OptionsTestLog

Logs options algorithm test executions (Kotak Strangle strategy).

| Field | Type | Description |
|-------|------|-------------|
| `nifty_spot` | DecimalField | NIFTY spot price |
| `india_vix` | DecimalField | India VIX value |
| `days_to_expiry` | IntegerField | Days to expiry |
| `available_margin` | DecimalField | Available margin |
| `active_positions` | IntegerField | Number of active positions |
| `adjusted_delta` | DecimalField | Calculated adjusted delta |
| `call_strike` | IntegerField | Selected call strike |
| `put_strike` | IntegerField | Selected put strike |
| `premium_collected` | DecimalField | Total premium collected |
| `filter_results` | JSONField | Results of each filter check |
| `status` | CharField | `pass`, `fail`, or `error` |
| `decision` | CharField | `ENTRY`, `REJECT`, or `ERROR` |

### FuturesTestLog

Logs futures algorithm test executions (ICICI Futures strategy).

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | CharField | Stock symbol |
| `current_price` | DecimalField | Current stock price |
| `oi_score` | DecimalField | Open Interest score |
| `sector_score` | DecimalField | Sector strength score |
| `technical_score` | DecimalField | Technical analysis score |
| `composite_score` | DecimalField | Combined score |
| `factor_details` | JSONField | Detailed factor breakdown |
| `llm_confidence` | DecimalField | LLM validation confidence |
| `llm_recommendation` | CharField | LLM recommendation |
| `status` | CharField | `qualified`, `not_qualified`, `blocked`, or `error` |
| `decision` | CharField | `LONG`, `SHORT`, or `BLOCK` |
| `position_size` | IntegerField | Recommended position size |
| `margin_required` | DecimalField | Required margin |

### PositionMonitorSnapshot

Stores periodic snapshots of position monitoring data.

| Field | Type | Description |
|-------|------|-------------|
| `position` | ForeignKey | Related Position |
| `current_price` | DecimalField | Current price at snapshot |
| `current_time` | DateTimeField | Snapshot time |
| `unrealized_pnl` | DecimalField | Unrealized P&L |
| `unrealized_pnl_pct` | DecimalField | Unrealized P&L percentage |
| `call_premium` | DecimalField | Call option premium (options only) |
| `put_premium` | DecimalField | Put option premium (options only) |
| `current_delta` | DecimalField | Current delta (options only) |
| `sl_hit` | BooleanField | Whether stop-loss was hit |
| `target_hit` | BooleanField | Whether target was hit |
| `action` | CharField | Recommended action (e.g., `HOLD`, `EXIT`) |

---

## Usage

### Creating a Test Scenario

```python
from apps.algo_test.models import AlgoTestScenario

scenario = AlgoTestScenario.objects.create(
    user=request.user,
    name="High VIX Strangle Test",
    strategy="options",
    inputs={
        "nifty_spot": 24500,
        "india_vix": 18.5,
        "days_to_expiry": 5,
        "available_margin": 5000000
    },
    results={
        "call_strike": 24800,
        "put_strike": 24200,
        "premium": 245.50,
        "decision": "ENTRY"
    }
)
```

### Logging an Options Test

```python
from apps.algo_test.models import OptionsTestLog

log = OptionsTestLog.objects.create(
    user=request.user,
    nifty_spot=24500,
    india_vix=15.2,
    days_to_expiry=4,
    available_margin=5000000,
    adjusted_delta=0.18,
    call_strike=24800,
    put_strike=24200,
    premium_collected=250.00,
    filter_results={
        "vix_check": True,
        "dte_check": True,
        "margin_check": True
    },
    status="pass",
    decision="ENTRY"
)
```

### Taking Position Snapshots

```python
from apps.algo_test.models import PositionMonitorSnapshot
from apps.positions.models import Position

position = Position.objects.get(id=1)
snapshot = PositionMonitorSnapshot.objects.create(
    position=position,
    current_price=24550,
    current_time=timezone.now(),
    unrealized_pnl=12500,
    unrealized_pnl_pct=2.5,
    sl_hit=False,
    target_hit=False,
    action="HOLD"
)
```

---

## Django Admin

Access algorithm testing data at:
- http://localhost:8000/admin/algo_test/algotestscenario/
- http://localhost:8000/admin/algo_test/optionstestlog/
- http://localhost:8000/admin/algo_test/futurestestlog/
- http://localhost:8000/admin/algo_test/positionmonitorsnapshot/

---

## File Reference

| File | Purpose |
|------|---------|
| `apps/algo_test/models.py` | Data models |
| `apps/algo_test/admin.py` | Admin configuration |
| `apps/algo_test/views.py` | Views (if any) |
| `apps/algo_test/services.py` | Business logic |
| `apps/algo_test/urls.py` | URL routes |

---

*See [03-TRADING-STRATEGIES.md](../03-TRADING-STRATEGIES.md) for details on the algorithms being tested.*
