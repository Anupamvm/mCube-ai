# Position Sizing Implementation

## Overview
Comprehensive position sizing system that calculates optimal lot sizes for futures and options trades based on available margin, risk management rules, and averaging down scenarios.

## Components

### 1. Position Sizing Service (`apps/trading/services/position_sizer.py`)

**PositionSizer Class:**
- Fetches margin from Breeze API (for futures) or Neo API (for options)
- Calculates optimal lot sizes considering multiple constraints
- Supports averaging down scenarios for futures (3x margin requirement)
- Implements risk management rules

**Risk Management Rules:**
- Max 25% of available margin per position
- Reserve 3x margin for averaging down (futures)
- Keep 20% margin buffer
- Hard caps: 10 lots for futures, 20 lots for options

### 2. Futures Position Sizing

**Method:** `calculate_futures_position_size()`

**Inputs:**
- Symbol, entry price, stop loss, target
- Lot size, direction (LONG/SHORT)

**Calculations:**
- Per-lot margin requirement (~20% of contract value)
- Risk per lot = (Entry - SL) × Lot Size
- Profit per lot = (Target - Entry) × Lot Size
- Max lots from available margin
- Max lots from position % limit (25%)
- Max lots with averaging down (3x margin)

**Outputs:**
```python
{
    # Single Position
    'recommended_lots': 3,
    'total_quantity': 375,  # 3 lots × 125 lot_size
    'margin_required': 150000,
    'max_loss': 15000,
    'max_profit': 45000,
    'risk_reward_ratio': 3.0,

    # Averaging Down Scenario
    'averaging_down': {
        'total_lots': 9,  # 3 lots × 3 entries
        'entry_1': 1000,  # Initial entry
        'entry_2': 950,   # Entry at -5%
        'entry_3': 900,   # Entry at -10%
        'average_entry': 950,
        'margin_required': 450000,
        'max_loss': 35000,
        'max_profit': 135000,
    }
}
```

### 3. Options Position Sizing

**Method:** `calculate_options_position_size()`

**Inputs:**
- Symbol, strike, option_type (CE/PE)
- Premium, lot size
- Stop loss premium, target premium
- Strategy (BUY/SELL)

**Calculations:**
- For BUY: Margin = Premium paid
- For SELL: Margin = ~25% of strike value (SPAN + Exposure)
- Max lots from available margin
- Max lots from position % limit

**Outputs:**
```python
{
    'recommended_lots': 5,
    'total_quantity': 250,  # 5 lots × 50 lot_size
    'margin_required': 25000,
    'max_loss': 5000,
    'max_profit': 15000,
    'risk_reward_ratio': 3.0,
}
```

### 4. Database Model (`apps/trading/models.py`)

**PositionSize Model:**
- Stores all position sizing calculations
- Tracks margin usage and recommendations
- Auto-expires after 24 hours
- Includes full calculation details in JSON

**Fields:**
- Core: symbol, instrument_type, direction
- Prices: entry_price, stop_loss, target
- Contract: lot_size, strike, option_type
- Margin: available_margin, margin_per_lot, margin_source
- Results: recommended_lots, total_quantity, margin_required
- P&L: max_loss, max_profit, risk_reward_ratio
- Averaging: averaging_data (JSON, futures only)
- Full details: calculation_details (JSON)
- Status: ACTIVE, EXECUTED, EXPIRED

### 5. API Endpoint

**URL:** `/trading/trigger/calculate-position-sizing/`

**Request (Futures):**
```json
{
    "instrument_type": "FUTURES",
    "symbol": "RELIANCE",
    "direction": "LONG",
    "entry_price": 2500,
    "stop_loss": 2450,
    "target": 2600,
    "lot_size": 250
}
```

**Request (Options):**
```json
{
    "instrument_type": "OPTIONS",
    "symbol": "NIFTY",
    "strike": 24000,
    "option_type": "CE",
    "premium": 150,
    "stop_loss_premium": 100,
    "target_premium": 250,
    "lot_size": 50,
    "strategy": "BUY"
}
```

**Response:**
```json
{
    "success": true,
    "position_size_id": 123,
    "result": {
        "recommended_lots": 3,
        "total_quantity": 750,
        "margin_required": 150000,
        "max_loss": 37500,
        "max_profit": 75000,
        "risk_reward_ratio": 2.0,
        // ... full details
    }
}
```

### 6. Admin Interface

**Features:**
- View all position sizing calculations
- Color-coded by instrument type (Blue=Futures, Green=Options)
- Shows recommended lots, quantities, and P&L
- Expandable JSON displays for:
  - Averaging down data
  - Full calculation details
- Filter by instrument type, direction, status
- Auto-expires after 24 hours

## Margin Sources

### Breeze API (Futures)
- Fetches real-time available margin
- Uses `get_funds()` endpoint
- Fields: availablemargin, usedmargin, totalmargin

### Neo API (Options)
- **TODO: Implement Neo margin API integration**
- Currently using placeholder (₹100,000)
- Should fetch from Neo trade API

## Usage Example

### In Views/Services:
```python
from apps.trading.services.position_sizer import PositionSizer
from decimal import Decimal

sizer = PositionSizer(user=request.user)

# For futures
result = sizer.calculate_futures_position_size(
    symbol='RELIANCE',
    entry_price=Decimal('2500'),
    stop_loss=Decimal('2450'),
    target=Decimal('2600'),
    lot_size=250,
    direction='LONG'
)

print(f"Recommended: {result['recommended_lots']} lots")
print(f"Max Loss: ₹{result['max_loss']:,.2f}")
print(f"Max Profit: ₹{result['max_profit']:,.2f}")
print(f"With Averaging: {result['averaging_down']['total_lots']} lots")
```

## Integration Points

### Future Integrations:
1. **Verify Future Trade** - Auto-calculate position size after verification
2. **Nifty Strangle** - Calculate position size for both legs
3. **Manual Execution** - Show position sizing before order placement
4. **Trade Suggestions** - Include position sizing in algorithm output

## Auto-Cleanup

Position sizing records auto-expire after 24 hours and should be cleaned up periodically:

```python
from django.utils import timezone
from apps.trading.models import PositionSize

# Clean up expired records
PositionSize.objects.filter(
    expires_at__lt=timezone.now(),
    status='ACTIVE'
).update(status='EXPIRED')
```

## Notes

1. **Margin Estimates:** Futures margin uses conservative 20% estimate. Actual broker margin may vary.

2. **Averaging Down:** Assumes 3 entries at entry, entry-5%, entry-10%. Customize based on strategy.

3. **Neo Integration:** Neo margin API needs implementation for accurate options margin.

4. **Authentication:** Handles Breeze authentication errors and triggers re-login flow.

5. **Database Storage:** All calculations stored for audit trail and analysis.
