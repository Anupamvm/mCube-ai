# Futures Trade Suggestion Tracking - Implementation

## Overview
Extended the trade suggestion tracking system to cover both futures trading workflows:
1. **Verify Future Trade** - Manual verification of a specific futures contract
2. **Shortlisted Futures Algorithm** - Automated screening of top 3 futures contracts

Both now save complete suggestions to the database with Breeze API margin data.

---

## Features Added

### 1. Verify Future Trade Tracking

**When:** A user manually verifies a specific futures contract and it passes analysis.

**What Gets Saved:**
- Strategy: `icici_futures`
- Suggestion Type: `FUTURES`
- Instrument: Stock symbol (e.g., RELIANCE, TCS)
- Direction: LONG, SHORT, or NEUTRAL
- Market data: Spot price, expiry date, days to expiry
- Position sizing: Recommended lots (from Breeze margin API), margin breakdown
- Risk metrics: Max profit/loss, stop loss, target prices
- Complete algorithm reasoning: Composite score, execution log, analysis metrics

**Margin Data Source:** Breeze API via `PositionSizer.calculate_comprehensive_position()`

### 2. Shortlisted Futures Algorithm Tracking

**When:** Futures algorithm analyzes multiple contracts and returns top 3 PASS results.

**What Gets Saved:**
- Top 3 contracts that passed the analysis
- Each saved as a separate `TradeSuggestion` record
- Conservative position sizing: 1 lot by default
- Estimated margin: 12% of position value (futures standard)
- Returns `suggestion_ids` array in response

---

## Implementation Details

### Verify Future Trade (`verify_future_trade`)

**Location:** `apps/trading/views.py` lines 1964-2056

**Key Changes:**
```python
# Only save if PASS
if passed:
    # Calculate position sizing using Breeze API
    position_calc = sizer.calculate_comprehensive_position(
        stock_symbol=stock_symbol,
        expiry=expiry_breeze,
        futures_price=futures_price,
        lot_size=lot_size,
        direction=direction,
        available_capital=available_capital,
        risk_percent=2.0
    )

    # Extract margin data from Breeze response
    margin_data = position_calc.get('margin_data', {})
    sizing_data = position_calc.get('position_sizing', {})

    # Create TradeSuggestion with Breeze margin info
    suggestion = TradeSuggestion.objects.create(
        user=request.user,
        strategy='icici_futures',
        suggestion_type='FUTURES',
        instrument=stock_symbol,
        direction=direction.upper(),
        # Margin from Breeze API
        margin_required=Decimal(str(margin_data.get('total_margin', 0))),
        margin_available=Decimal(str(margin_data.get('available_margin', 0))),
        margin_per_lot=Decimal(str(margin_data.get('margin_per_lot', 0))),
        # ... other fields
    )

    # Add suggestion_id to response
    response_data['suggestion_id'] = suggestion.id
```

**Stop Loss & Target Calculation:**
```python
if direction == 'LONG':
    stop_loss_price = futures_price * Decimal('0.98')  # 2% below
    target_price = futures_price * Decimal('1.04')     # 4% above
elif direction == 'SHORT':
    stop_loss_price = futures_price * Decimal('1.02')  # 2% above
    target_price = futures_price * Decimal('0.96')     # 4% below
```

### Shortlisted Futures Algorithm (`trigger_futures_algorithm`)

**Location:** `apps/trading/views.py` lines 843-948

**Key Changes:**
```python
# Save top 3 PASS results
suggestion_ids = []
for result in passed_results[:3]:
    # Estimate margin (12% of position value)
    estimated_margin_per_lot = futures_price * lot_size * Decimal('0.12')

    # Conservative: 1 lot recommendation
    recommended_lots = 1
    margin_required = estimated_margin_per_lot * recommended_lots

    suggestion = TradeSuggestion.objects.create(
        user=request.user,
        strategy='icici_futures',
        suggestion_type='FUTURES',
        instrument=symbol,
        direction=direction.upper(),
        recommended_lots=recommended_lots,
        margin_required=margin_required,
        margin_per_lot=estimated_margin_per_lot,
        # ... other fields
    )

    suggestion_ids.append(suggestion.id)

# Add to response
response_data['suggestion_ids'] = suggestion_ids
```

**Why Conservative 1 Lot:**
- Futures algorithm analyzes many contracts
- Users can view all 3 and decide which to trade
- Position sizing can be adjusted when taking the trade
- Safer default for automated screening

---

## Response Format

### Verify Future Trade Response
```json
{
    "success": true,
    "symbol": "RELIANCE",
    "expiry": "28-NOV-2025",
    "passed": true,
    "analysis": {
        "direction": "LONG",
        "entry_price": 2850.50,
        "stop_loss": 2793.49,
        "target": 2964.52,
        "composite_score": 78,
        "position_details": {
            "lot_size": 250,
            "recommended_lots": 5,
            "margin_required": 427650.00,
            "margin_per_lot": 85530.00,
            "available_capital": 500000,
            "capital_used_pct": 42.8
        }
    },
    "position_sizing": {
        "margin_data": {
            "total_margin": 427650.00,
            "available_margin": 4500000.00,
            "margin_per_lot": 85530.00,
            "source": "Breeze API"
        },
        "position_sizing": {
            "recommended_lots": 5,
            "capital_used_percent": 42.8
        }
    },
    "suggestion_id": 124,
    "execution_log": [...]
}
```

### Shortlisted Futures Response
```json
{
    "success": true,
    "all_contracts": [
        {
            "symbol": "RELIANCE",
            "expiry": "28-NOV-2025",
            "composite_score": 78,
            "direction": "LONG",
            "verdict": "PASS",
            "futures_price": 2850.50,
            "lot_size": 250,
            "volume": 15000
        },
        {
            "symbol": "TCS",
            "expiry": "28-NOV-2025",
            "composite_score": 72,
            "direction": "SHORT",
            "verdict": "PASS",
            "futures_price": 4125.25,
            "lot_size": 125,
            "volume": 12000
        },
        {
            "symbol": "INFY",
            "expiry": "28-NOV-2025",
            "composite_score": 68,
            "direction": "LONG",
            "verdict": "PASS",
            "futures_price": 1890.75,
            "lot_size": 300,
            "volume": 18000
        }
    ],
    "total_analyzed": 45,
    "total_passed": 3,
    "total_failed": 42,
    "suggestion_ids": [125, 126, 127]
}
```

---

## Database Schema (Same as Options)

All futures suggestions use the same `TradeSuggestion` model with:
- `suggestion_type = 'FUTURES'`
- `strategy = 'icici_futures'`
- `direction` = LONG/SHORT/NEUTRAL
- No call/put strikes (OPTIONS only)
- Margin data from Breeze API
- Risk metrics (max profit/loss, stop/target)

---

## Margin Calculation Differences

### Options (Strangle):
- **Source:** Kotak Neo API
- **Field:** `Net` (Total Margin)
- **Rule:** Use 50% of available margin
- **Calculation:** Backend calculates margin per strangle position

### Futures (Verify Trade):
- **Source:** ICICI Breeze API
- **Method:** `breeze.get_margin()` for specific contract
- **Rule:** Conservative position sizing via `PositionSizer`
- **Features:** Real-time margin for specific lot size

### Futures (Shortlisted):
- **Source:** Estimated (12% of position value)
- **Why:** Analyzing many contracts, Breeze API would be too slow
- **Calculation:** `futures_price × lot_size × 0.12`
- **Note:** Users can get exact margin when verifying individual contract

---

## JSON Serialization

Both implementations use the same `json_serial()` helper:
```python
def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")
```

**Applied to:**
- `algorithm_reasoning` (contains dates, decimals from analysis)
- `position_details` (contains margin data from Breeze)

---

## User Workflow

### Verify Future Trade:
```
1. User enters stock symbol and expiry
2. Click "Verify Future Trade"
3. Comprehensive analysis runs (9 steps)
4. If PASS:
   - Breeze API fetches real margin
   - Position sizer calculates recommended lots
   - TradeSuggestion saved to database
   - suggestion_id returned in response
5. User can:
   - Take trade (updates status to TAKEN)
   - Reject trade (updates status to REJECTED)
   - View in history with P&L tracking
```

### Shortlisted Futures:
```
1. User sets volume filters
2. Click "Run Futures Algorithm"
3. System analyzes ALL matching contracts
4. Sorts by score (PASS first, then FAIL)
5. Top 3 PASS results:
   - Saved as suggestions (conservative 1 lot each)
   - suggestion_ids returned in response
6. User reviews all 3 options
7. Can verify specific contract for detailed margin
8. Take/reject individual suggestions
```

---

## Admin View

Futures suggestions appear in Django admin with:
- **Strategy:** ICICI Futures
- **Type:** FUTURES (badge)
- **Direction:** LONG/SHORT/NEUTRAL (color-coded)
- **Instrument:** Stock symbol
- **Lots:** Recommended lot size
- **Margin:** Margin required
- **Status:** SUGGESTED/TAKEN/ACTIVE/CLOSED/etc.
- **P&L:** Realized P&L and ROM% (when closed)

**Filter by:**
- Status
- Strategy
- Suggestion Type (OPTIONS vs FUTURES)
- Created date

---

## Benefits

### For Verify Future Trade:
1. **Exact Margin Data:** Real-time from Breeze API
2. **Complete Audit Trail:** Every verification saved
3. **Historical Analysis:** Track which contracts were verified and traded
4. **Performance Tracking:** Compare suggested vs actual results

### For Shortlisted Futures:
1. **Batch Tracking:** All top 3 suggestions saved
2. **Comparison:** Review multiple options side-by-side
3. **Selection History:** Track which of the 3 was chosen
4. **Pattern Recognition:** Identify which filtering criteria work best

---

## Example Queries

**Get all futures suggestions for a user:**
```python
futures_suggestions = TradeSuggestion.objects.filter(
    user=request.user,
    suggestion_type='FUTURES'
).order_by('-created_at')
```

**Get PASS futures that were taken:**
```python
taken_futures = TradeSuggestion.objects.filter(
    user=request.user,
    suggestion_type='FUTURES',
    status='TAKEN'
)
```

**Calculate win rate for futures:**
```python
from django.db.models import Q

closed_futures = TradeSuggestion.objects.filter(
    user=request.user,
    suggestion_type='FUTURES',
    status__in=['SUCCESSFUL', 'LOSS', 'BREAKEVEN']
)

wins = closed_futures.filter(status='SUCCESSFUL').count()
total = closed_futures.count()
win_rate = (wins / total * 100) if total > 0 else 0

print(f"Futures Win Rate: {win_rate:.1f}% ({wins}/{total})")
```

**Compare options vs futures performance:**
```python
options_roi = TradeSuggestion.objects.filter(
    suggestion_type='OPTIONS',
    status='SUCCESSFUL'
).aggregate(Avg('return_on_margin'))

futures_roi = TradeSuggestion.objects.filter(
    suggestion_type='FUTURES',
    status='SUCCESSFUL'
).aggregate(Avg('return_on_margin'))
```

---

## Testing

### Test Verify Future Trade:
1. Navigate to manual triggers page
2. Enter a valid futures contract (e.g., RELIANCE | 2025-11-28)
3. Click "Verify Future Trade"
4. If analysis passes:
   - Check response for `suggestion_id`
   - Verify in Django admin
   - Check margin data is from Breeze
   - Verify position sizing calculations

### Test Shortlisted Futures:
1. Set volume filters (e.g., 1000/800)
2. Click "Run Futures Algorithm"
3. Wait for analysis (may take a few minutes)
4. Check response for `suggestion_ids` array
5. Verify in Django admin:
   - Should see 3 new suggestions (if 3+ passed)
   - All should be `icici_futures` strategy
   - Each with 1 lot recommended
   - Margin ~12% of position value

---

## Files Modified

1. **apps/trading/views.py**
   - `verify_future_trade()` (lines 1964-2056)
   - `trigger_futures_algorithm()` (lines 843-948)
   - Added JSON serialization helper
   - Added TradeSuggestion creation logic

2. **Database**
   - No schema changes needed
   - Uses existing TradeSuggestion model
   - Differentiates via `suggestion_type='FUTURES'`

---

## Key Differences: Options vs Futures

| Feature | Options (Strangle) | Futures (Verify) | Futures (Shortlist) |
|---------|-------------------|------------------|---------------------|
| **Margin Source** | Neo API | Breeze API | Estimated (12%) |
| **Lots** | 50% of max | PositionSizer calc | Conservative (1) |
| **Strikes** | Call + Put | N/A | N/A |
| **Premium** | Collected | N/A | N/A |
| **Stop/Target** | Breakevens | ±2%/±4% | ±2%/±4% |
| **Quantity** | Many (e.g., 89) | Few (e.g., 5) | 1 |
| **Save When** | Always | Only if PASS | Top 3 PASS |

---

## Future Enhancements

1. **Real-time Margin for Shortlist:**
   - Batch fetch margins for top 3 via Breeze
   - Replace estimated 12% with actual margins

2. **Position Sizing UI:**
   - Show margin breakdown for each of top 3
   - Let user adjust lots before taking trade

3. **Comparison View:**
   - Side-by-side comparison of top 3 futures
   - Highlight best R:R ratio, lowest margin, etc.

4. **Auto-Update Suggestions:**
   - Refresh margin data before trade execution
   - Alert if margin requirement changed significantly

---

## Status

**Implementation:** ✅ COMPLETE
**Verify Future Trade:** ✅ WORKING
**Shortlisted Futures:** ✅ WORKING
**Breeze Margin Integration:** ✅ INTEGRATED
**Database:** ✅ NO MIGRATION NEEDED
**Date:** 2025-11-19
**Ready for Production:** YES

---

## Summary

Trade suggestion tracking now covers:
- ✅ **Nifty Strangle** (Neo API, options)
- ✅ **Verify Future Trade** (Breeze API, single contract)
- ✅ **Shortlisted Futures** (Batch analysis, top 3)

All suggestions tracked with:
- Complete algorithm reasoning
- Margin data (real or estimated)
- Position sizing recommendations
- Risk metrics
- P&L tracking
- State machine management
- 24-hour expiry

Users can now:
- View complete history across all strategies
- Compare performance: Options vs Futures
- Track which contracts were suggested/taken
- Analyze win rate and ROM by strategy type
- Make data-driven decisions about which algorithms work best
