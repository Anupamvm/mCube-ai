# Zero Lots Calculation Fix

## Issue
Position sizing was showing "Initial: 0 lots" despite having sufficient margin.

## Root Cause Analysis

### Problem 1: Margin Estimation Too High
**Before**: Used 30% of strike value as margin requirement
```python
margin_per_lot = strike × 50 × 0.30 = 24,000 × 50 × 0.30 = ₹360,000 per lot
```

**Reality**: Actual margin for OTM Nifty strangles is 15-20% of notional value

**Fix**: Reduced to 18%
```python
margin_per_lot = strike × 50 × 0.18 = 24,000 × 50 × 0.18 = ₹216,000 per lot
```

**Impact**: 40% reduction in margin requirement per lot

### Problem 2: Placeholder Margin Too Low
**Before**: ₹5 lakhs placeholder when Neo API unavailable

**Reality**: Typical capital for strangle trading is ₹10-20 lakhs

**Fix**: Increased to ₹10 lakhs
```python
'available_margin': Decimal('1000000')
```

### Problem 3: Over-Conservative Averaging Reserve
**Before**: Reserved margin for averaging using 2.2x multiplier
```python
max_lots_with_averaging = usable_margin / (margin_per_lot × 2.2)
```

This was too restrictive and often resulted in 0 lots.

**Fix**: Removed the pre-allocation constraint
- Initial position uses max 30% of available margin
- Averaging logic handles margin dynamically based on actual balance
- Each averaging attempt calculates affordable lots based on current balance

## Calculation Example

### Before (0 lots issue)
- Available Margin: ₹500,000
- Margin per lot: ₹360,000
- Usable (85%): ₹425,000
- With averaging reserve (÷2.2): ₹425,000 / (₹360,000 × 2.2) = 0.53 → **0 lots**

### After (fixed)
- Available Margin: ₹1,000,000
- Margin per lot: ₹216,000
- Max Position (30%): ₹300,000
- Max lots: ₹300,000 / ₹216,000 = 1.38 → **1 lot initially**

Averaging scenarios (calculated dynamically):
- Attempt 1: 20% of ₹10L = ₹2L / ₹216K = 0.92 → 1 lot (capped at initial)
- Attempt 2: 50% of ₹10L = ₹5L / ₹216K = 2.31 → 2 lots
- Attempt 3: 50% of ₹10L = ₹5L / ₹216K = 2.31 → 2 lots

**Total after all averaging**: 1 + 1 + 2 + 2 = 6 lots

## Files Modified

### `/apps/trading/services/strangle_position_sizer.py`

**Changes**:
1. Line 95: Increased placeholder margin from ₹5L to ₹10L
2. Line 151: Reduced margin estimation from 30% to 18%
3. Lines 260-274: Removed over-conservative averaging reserve constraint
4. Lines 106-190: Added `get_neo_margin_for_strangle()` method for future actual margin API integration

## Next Steps

### Immediate Testing
Test with actual Nifty strikes to verify:
- Initial lots > 0
- Margin calculations are realistic
- Averaging scenarios are properly calculated

### Future Enhancements
1. **Implement Neo Margin Calculator API**: Get actual margin from Neo instead of estimation
2. **Dynamic Margin Adjustment**: Adjust margin % based on VIX levels
   - Low VIX (< 15): Use 15% margin
   - Medium VIX (15-20): Use 18% margin
   - High VIX (> 20): Use 22% margin
3. **Fetch User's Actual Margin**: Replace placeholder with real Neo API call on every calculation

## Testing Checklist

- [ ] Generate Nifty Strangle position
- [ ] Verify initial lots > 0
- [ ] Check that margin per lot is realistic (₹150K - ₹250K range)
- [ ] Verify averaging scenarios show increasing lots
- [ ] Check P&L calculations are correct
- [ ] Test with different strike prices
- [ ] Test with different margin amounts
