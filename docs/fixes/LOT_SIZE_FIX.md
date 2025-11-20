# NIFTY Lot Size Fix - "Valid Lotwise Quantity" Error

**Date:** November 20, 2025
**Issue:** Neo API rejecting orders with error: `'stCode': 1009, 'errMsg': 'please provide valid lotwise quantity'`
**Root Cause:** Incorrect lot size (50 instead of 75)
**Status:** ✅ FIXED

---

## Problem

### Error Message
```json
{
  "stCode": 1009,
  "errMsg": "please provide valid lotwise quantity",
  "stat": "Not_Ok"
}
```

### User Report
> "NFO 2025-11-20 19:21:21,390 Kotak Neo order response: {'stCode': 1009, 'errMsg': 'please provide valid lotwise quantity', 'stat': 'Not_Ok'} .. I guess you are passing 20 as a number when it should change as per lotsize.."

---

## Root Cause Analysis

### Issue
The code was using **lot_size = 50** for NIFTY options, but the actual lot size is **75**.

### Impact
- For 20 lots: We were sending **1000 quantity** (20 × 50)
- Neo API expects: **1500 quantity** (20 × 75)
- Neo API validation: 1000 is NOT a multiple of 75 → Error!

### Verification from SecurityMaster

Checked `/Users/anupammangudkar/Downloads/SecurityMaster/FONSEScripMaster.txt`:

```csv
"53246","OPTIDX","NIFTY","OPTION","25-Nov-2025","27050","CE",...,75,5,"NIFTY 50",...
"53247","OPTIDX","NIFTY","OPTION","25-Nov-2025","27050","PE",...,75,5,"NIFTY 50",...
"52849","OPTIDX","NIFTY","OPTION","25-Nov-2025","25450","CE",...,75,5,"NIFTY 50",...
"52850","OPTIDX","NIFTY","OPTION","25-Nov-2025","25450","PE",...,75,5,"NIFTY 50",...
```

**Column "LotSize" shows: 75** ✅

---

## Fix Applied

### 1. Backend Fix - kotak_neo.py

**File:** `apps/brokers/integrations/kotak_neo.py`
**Line:** 540

**Before:**
```python
lot_size = 50  # NIFTY lot size (this should ideally be fetched from contract data)
```

**After:**
```python
lot_size = 75  # NIFTY lot size (correct as of Nov 2025)
```

### 2. Frontend Fix - manual_triggers.html

**File:** `apps/trading/templates/trading/manual_triggers.html`
**Line:** 5221

**Before:**
```javascript
const lotSize = 50;  // NIFTY lot size
```

**After:**
```javascript
const lotSize = 75;  // NIFTY lot size (correct as of Nov 2025)
```

### 3. Added Logging - kotak_neo.py

**File:** `apps/brokers/integrations/kotak_neo.py`
**Line:** 408-409

**Added:**
```python
# Log order details before placing
logger.info(f"Placing Neo order: symbol={trading_symbol}, type={transaction_type}, qty={quantity}, product={product}, order_type={order_type}")
```

**Purpose:** Debug future quantity-related issues

---

## Impact of Fix

### Before (Incorrect - Lot Size 50)

**For 167 lots:**
- Batch 1: 20 lots × 50 = **1,000 qty** ❌
- Batch 2: 20 lots × 50 = **1,000 qty** ❌
- ...
- Batch 9: 7 lots × 50 = **350 qty** ❌

**Neo API Validation:**
- 1,000 % 75 = 25 (remainder) → ❌ NOT VALID
- 350 % 75 = 50 (remainder) → ❌ NOT VALID

**Result:** All orders rejected with error 1009

### After (Correct - Lot Size 75)

**For 167 lots:**
- Batch 1: 20 lots × 75 = **1,500 qty** ✅
- Batch 2: 20 lots × 75 = **1,500 qty** ✅
- ...
- Batch 9: 7 lots × 75 = **525 qty** ✅

**Neo API Validation:**
- 1,500 % 75 = 0 → ✅ VALID (exactly 20 lots)
- 525 % 75 = 0 → ✅ VALID (exactly 7 lots)

**Result:** All orders should now be accepted ✅

---

## Example Calculation

### Scenario: 167 Lots Strangle Order

**With Correct Lot Size (75):**

| Batch | Lots | Quantity (lots × 75) | Valid? |
|-------|------|---------------------|--------|
| 1 | 20 | 1,500 | ✅ (1500/75 = 20) |
| 2 | 20 | 1,500 | ✅ (1500/75 = 20) |
| 3 | 20 | 1,500 | ✅ (1500/75 = 20) |
| 4 | 20 | 1,500 | ✅ (1500/75 = 20) |
| 5 | 20 | 1,500 | ✅ (1500/75 = 20) |
| 6 | 20 | 1,500 | ✅ (1500/75 = 20) |
| 7 | 20 | 1,500 | ✅ (1500/75 = 20) |
| 8 | 20 | 1,500 | ✅ (1500/75 = 20) |
| 9 | 7 | 525 | ✅ (525/75 = 7) |

**Total:**
- CALL orders: 9 (each valid)
- PUT orders: 9 (each valid)
- Total orders: 18
- Total quantity: 167 × 75 = **12,525** (per leg)

---

## Confirmation Dialog Update

### Before (Incorrect):
```
Lots: 167 (8350 qty)  ← WRONG!
Premium Collection: ₹67,218  ← WRONG!
```

**Calculation:**
- 167 lots × 50 = 8,350 qty ❌
- Premium: (1.85 + 6.20) × 8,350 = ₹67,218 ❌

### After (Correct):
```
Lots: 167 (12,525 qty)  ← CORRECT!
Premium Collection: ₹100,826  ← CORRECT!
```

**Calculation:**
- 167 lots × 75 = 12,525 qty ✅
- Premium: (1.85 + 6.20) × 12,525 = ₹100,826 ✅

---

## Testing Checklist

- [x] Verified correct lot size from SecurityMaster (75)
- [x] Updated backend lot_size variable
- [x] Updated frontend lotSize variable
- [x] Added debug logging for quantity
- [ ] Test during market hours to confirm orders accepted
- [ ] Verify actual quantity in Neo platform matches (1,500 per 20-lot batch)

---

## Future Improvements

### 1. Dynamic Lot Size Lookup ⚠️ RECOMMENDED

**Issue:** Lot sizes can change over time or differ by instrument

**Solution:** Fetch lot size from SecurityMaster or ContractData

**Example:**
```python
from apps.data.models import ContractData

def get_lot_size_for_symbol(trading_symbol):
    """Fetch lot size from SecurityMaster data"""
    # Extract instrument details from symbol
    # e.g., "NIFTY25NOV27050CE" → instrument="NIFTY", expiry="25NOV"

    contract = ContractData.objects.filter(
        symbol=trading_symbol
    ).first()

    if contract:
        return contract.lot_size
    else:
        # Fallback to hardcoded values
        return 75  # NIFTY default
```

**Benefits:**
- ✅ Always accurate
- ✅ Handles lot size changes
- ✅ Works for all instruments (NIFTY, BANKNIFTY, etc.)
- ✅ No manual updates needed

### 2. Add Lot Size to Trade Suggestion Model

**Add field to TradeSuggestion model:**
```python
class TradeSuggestion(models.Model):
    ...
    lot_size = models.IntegerField(default=75)  # Store lot size with suggestion
    ...
```

**Benefits:**
- Historical accuracy (lot size at time of suggestion)
- Frontend can use stored value
- Audit trail

### 3. Validation Before API Call

**Add validation in place_option_order():**
```python
def place_option_order(trading_symbol, quantity, ...):
    # Get expected lot size
    expected_lot_size = get_lot_size_for_symbol(trading_symbol)

    # Validate quantity is a multiple of lot size
    if quantity % expected_lot_size != 0:
        raise ValueError(
            f"Invalid quantity {quantity} for {trading_symbol}. "
            f"Must be a multiple of lot size {expected_lot_size}"
        )

    # Proceed with order placement
    ...
```

**Benefits:**
- ✅ Catch errors before API call
- ✅ Clear error messages
- ✅ Saves API rate limits

---

## Known Lot Sizes (as of Nov 2025)

| Instrument | Lot Size | Source |
|------------|----------|--------|
| NIFTY 50 | **75** | SecurityMaster ✅ |
| NIFTY BANK | 35 | SecurityMaster |
| NIFTY FIN | 65 | SecurityMaster |
| NIFTY MIDCAP | 140 | SecurityMaster |

**Note:** NIFTY lot size changed from 50 to 75 recently. Always verify from SecurityMaster.

---

## Logs Expected After Fix

### Before Order Placement:
```
INFO: Placing Neo order: symbol=NIFTY25NOV27050CE, type=S, qty=1500, product=NRML, order_type=MKT
```

### Neo API Response (Success):
```json
{
  "stat": "Ok",
  "nOrdNo": "237362700735243",
  "stCode": 200
}
```

### Backend Log:
```
INFO: ✅ Order placed successfully: 237362700735243 for NIFTY25NOV27050CE
INFO: ✅ CALL SELL batch 1: Order ID 237362700735243
```

---

## Summary

### What Was Wrong
- ❌ Hardcoded lot size: 50
- ❌ Quantity calculation: 20 × 50 = 1,000
- ❌ Neo API validation failed: 1,000 % 75 ≠ 0

### What We Fixed
- ✅ Corrected lot size: 75
- ✅ Quantity calculation: 20 × 75 = 1,500
- ✅ Neo API validation passes: 1,500 % 75 = 0

### Files Modified
1. `apps/brokers/integrations/kotak_neo.py` (Line 540)
2. `apps/trading/templates/trading/manual_triggers.html` (Line 5221)
3. `apps/brokers/integrations/kotak_neo.py` (Line 408 - added logging)

### Impact
- ✅ Orders will now pass Neo API validation
- ✅ Correct quantity displayed to user
- ✅ Correct premium collection calculated
- ✅ Better debug logging for future issues

---

**Status:** ✅ READY FOR MARKET HOURS TESTING

**Expected Result:** Orders should now be accepted by Neo API during market hours

**Next Step:** Test with a small order (2 lots = 150 qty) during market hours to verify fix

---

**Fixed By:** Claude Code Assistant
**Date:** November 20, 2025
**Fix Time:** 10 minutes
**Root Cause:** Outdated/incorrect lot size constant
