# Position Sizing UI Redesign - Complete Specification

## Current Issues

1. **0 Lots Calculation**: Initial lots showing 0 despite having sufficient margin
2. **Separated UI**: Position sizing shown as "Step 10" separate from main display
3. **Non-interactive**: User cannot edit values and see live updates
4. **Take Trade button**: Located separately, should be part of position sizing section

## New Design Requirements

### For Nifty Strangle (Options)

**Data Source**: Neo API for margin
**Display Location**: Integrated into main strangle result display (not as Step 10)

**UI Components**:
1. **Margin Display Section** (Top)
   - Available Margin: ₹X,XX,XXX
   - Used Margin: ₹X,XX,XXX
   - Source: Neo API / Placeholder
   - Last Updated: timestamp

2. **Position Builder** (Interactive)
   - **Editable Fields**:
     - Number of Lots: [___] (slider + input)
     - Call Strike: [____] (dropdown from available strikes)
     - Put Strike: [____] (dropdown from available strikes)
     - Call Premium: ₹[___] (editable, auto-fetched)
     - Put Premium: ₹[___] (editable, auto-fetched)

3. **Live Calculations** (Auto-update on field change)
   - Margin Required: ₹X,XX,XXX
   - Total Premium Collected: ₹X,XX,XXX
   - Return on Margin: X.XX%
   - Max Profit: ₹X,XX,XXX (both expire worthless)
   - Breakeven Points: Upper ₹XX,XXX | Lower ₹XX,XXX

4. **Critical P&L Analysis** (Table)
   | Scenario | Nifty Price | P&L | ROI % |
   |----------|-------------|-----|-------|
   | At R1 | ₹24,500 | +₹X,XXX | +X% |
   | At S1 | ₹23,500 | -₹X,XXX | -X% |
   | +5% Rise | ₹25,000 | -₹X,XXX | -X% |
   | -5% Drop | ₹23,000 | -₹X,XXX | -X% |
   | Upper BE | ₹24,155 | ₹0 | 0% |
   | Lower BE | ₹23,845 | ₹0 | 0% |

5. **Averaging Protocol Display**
   - Show 20-50-50 protocol
   - Calculate and display:
     - Attempt 1 (20%): X lots @ -1%
     - Attempt 2 (50%): X lots @ -2%
     - Attempt 3 (50%): X lots @ -3%
     - Total After All: XX lots
     - Total Margin Reserved: ₹X,XX,XXX

6. **Calculation Details** (Collapsible)
   ```
   Calculation Breakdown:
   - Margin per lot: ₹XX,XXX (30% of higher strike × 50)
   - Available margin: ₹5,00,000
   - Usable (85%): ₹4,25,000
   - Max lots from margin: X
   - Max lots from 30% limit: X
   - With averaging reserve (2.2x): X lots
   - Recommended: X lots
   ```

7. **Action Buttons** (Bottom)
   - **✅ Execute Trade** (primary button)
   - **📝 Save for Later** (secondary)
   - **❌ Reject** (tertiary)

### For Futures Algorithm

**Data Source**: Breeze API for margin
**Display Location**: Integrated into futures verification result

**Similar UI with Futures-specific fields**:
- Entry Price (editable)
- Stop Loss (editable)
- Target (editable)
- Lot Size (fixed based on contract)
- Number of Lots (editable with slider)

**Futures-specific Calculations**:
- Position Value: Entry × Lot Size × Lots
- Margin Required: ~20% of position value
- Risk per Lot: (Entry - SL) × Lot Size
- Reward per Lot: (Target - Entry) × Lot Size
- Risk:Reward Ratio

**Futures Averaging**:
- Entry 1: Current price
- Entry 2: -5% from entry
- Entry 3: -10% from entry
- Show average entry price and total P&L

## Implementation Plan

### Phase 1: Fix 0 Lots Issue ✅
1. Implement actual Neo API margin fetching
2. Increase placeholder to ₹5 lakhs
3. Add detailed logging for lot calculations
4. Debug why margin_per_lot might be too high

### Phase 2: Backend Response Update
1. Add all editable fields to response
2. Include margin data in main response (not in step 10)
3. Add available strikes list
4. Return calculation breakdown

### Phase 3: Frontend UI Redesign
1. Remove "Step 10" position sizing display
2. Create new integrated Position Sizing component
3. Add editable inputs with change handlers
4. Implement live recalculation on value change
5. Add P&L table with color coding
6. Show averaging protocol visually
7. Move action buttons to bottom of section

### Phase 4: Futures Integration
1. Create similar UI for futures
2. Implement Breeze margin API
3. Add futures-specific fields
4. Implement futures averaging logic

## Technical Details

### Backend Changes Needed

**File**: `apps/trading/views.py` - `trigger_nifty_strangle()`
- Move position sizing from Step 10 to main response
- Include: `margin_data`, `position_sizing`, `available_strikes`
- Don't show in execution_log, show as separate section

**File**: `apps/trading/services/strangle_position_sizer.py`
- Fix 0 lots calculation
- Return calculation breakdown
- Add method to recalculate with custom lots

### Frontend Changes Needed

**File**: `apps/trading/templates/trading/manual_triggers.html`
- Create `buildPositionSizingUI()` function
- Add `updatePositionCalculations()` for live updates
- Replace static display with interactive form
- Add event listeners for input changes
- Style with gradient backgrounds and clean layout

### API Response Format

```json
{
  "success": true,
  "strangle": {
    "call_strike": 24200,
    "put_strike": 23800,
    "call_premium": 80.5,
    "put_premium": 75.3,
    // ... existing fields
  },
  "margin_data": {
    "available": 500000,
    "used": 0,
    "source": "neo_api",
    "fetched_at": "2025-01-19T15:30:00"
  },
  "position_sizing": {
    "recommended_lots": 5,
    "margin_per_lot": 36300,
    "premium_per_lot": 7790,
    "calculations": {
      "from_margin": 8,
      "from_limit": 6,
      "with_averaging": 5,
      "selected": 5
    },
    "pnl_analysis": {
      // ... critical levels
    },
    "averaging_protocol": {
      // ... 20-50-50 details
    }
  },
  "available_strikes": {
    "calls": [24000, 24100, 24200, 24300, 24400],
    "puts": [23600, 23700, 23800, 23900, 24000]
  }
}
```

## Next Steps

1. Test with actual Neo API credentials
2. Debug 0 lots issue with detailed logging
3. Implement new UI design
4. Test with live data
5. Repeat for futures algorithm
