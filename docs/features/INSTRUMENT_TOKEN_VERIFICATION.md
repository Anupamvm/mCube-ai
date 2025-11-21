# Instrument Token Verification in Order Confirmation

**Date:** November 21, 2025
**Feature:** Pre-Order Contract Verification
**Status:** ✅ Implemented
**Category:** Safety Enhancement

---

## Overview

Added **instrument token verification** to the order confirmation dialog to ensure users can verify they are placing orders on the **correct contract** before execution.

### Problem Solved

Previously, the confirmation dialog only showed:
- Symbol
- Expiry (display format)
- Direction
- Lots
- Prices

**Missing:** No way to verify the **exact contract** (instrument token) that will be traded.

### Solution

Before showing the confirmation dialog, the system now:
1. ✅ Fetches complete contract details from SecurityMaster
2. ✅ Shows instrument token in the confirmation
3. ✅ Displays stock code, company name, lot size
4. ✅ Indicates data source (SecurityMaster vs fallback)

---

## Implementation

### 1. New API Endpoint

**File:** `apps/trading/api_views.py:1146-1224`
**Endpoint:** `/trading/api/get-contract-details/`

```python
@login_required
@require_GET
def get_contract_details(request):
    """
    Get complete contract details including instrument token from SecurityMaster.

    GET params:
        - symbol: Stock symbol (e.g., 'TCS')
        - expiry: Expiry date in YYYY-MM-DD format (e.g., '2024-12-26')

    Returns:
        JSON with contract details and instrument token
    """
```

**Returns:**
```json
{
  "success": true,
  "symbol": "TCS",
  "expiry": "2024-12-26",
  "expiry_formatted": "26-DEC-2024",
  "lot_size": 125,
  "price": 4250.50,
  "volume": 15000,
  "instrument": {
    "token": "52977",
    "stock_code": "TCS",
    "company_name": "Tata Consultancy Services Ltd",
    "lot_size": 125,
    "source": "SecurityMaster"
  }
}
```

### 2. URL Route

**File:** `apps/trading/urls.py:34`

```python
path('api/get-contract-details/', api_views.get_contract_details, name='api_get_contract_details'),
```

### 3. Frontend Integration

**File:** `apps/trading/templates/trading/manual_triggers.html:2641-2709`

**Flow:**
1. User clicks "Place Order"
2. System fetches contract details (with instrument token)
3. Shows enhanced confirmation dialog
4. User verifies instrument token matches expected contract
5. User confirms or cancels

**Code:**
```javascript
// FETCH CONTRACT DETAILS (including instrument token) BEFORE CONFIRMATION
statusDiv.className = 'order-status pending show';
statusDiv.textContent = 'Fetching contract details...';

const expiryToVerify = contract.expiry_date || contract.expiry;
const detailsResponse = await fetch(`/trading/api/get-contract-details/?symbol=${contract.symbol}&expiry=${expiryToVerify}`);
const contractDetails = await detailsResponse.json();

if (!contractDetails.success) {
    alert(`Error: ${contractDetails.error}\n\nCannot verify contract. Order cancelled.`);
    return;
}

const instrument = contractDetails.instrument || {};
```

---

## Enhanced Confirmation Dialog

### Before
```
⚠️ CONFIRM ORDER PLACEMENT

Symbol: TCS
Expiry: 26-Dec-2024
Direction: LONG
Lots: 5
Quantity: 625

Entry Price: ₹4,250.00
Margin Required: ₹265,625

This will place a REAL order with your broker.
Are you absolutely sure?
```

### After (With Instrument Token)
```
⚠️ CONFIRM ORDER PLACEMENT

Symbol: TCS
Expiry: 26-DEC-2024
Direction: LONG
Lots: 5
Quantity: 625

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 CONTRACT VERIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Instrument Token: 52977
Stock Code: TCS
Company: Tata Consultancy Services Ltd
Lot Size: 125
Source: SecurityMaster
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Entry Price: ₹4,250.00
Margin Required: ₹265,625

This will place a REAL order with your broker.
Are you absolutely sure?
```

---

## Benefits

### For Traders
✅ **Verify exact contract** before order placement
✅ **See instrument token** to cross-check with broker terminal
✅ **Confirm expiry date** in both formats (YYYY-MM-DD and DD-MMM-YYYY)
✅ **Validate lot size** matches expected contract

### For Safety
✅ **Prevents wrong contract selection** - Can verify token manually
✅ **Shows data source** - Know if using SecurityMaster or fallback
✅ **Catches database mismatches** - Will show error if contract not found
✅ **Cancels order** if contract details cannot be fetched

### For Debugging
✅ **Console logging** shows full contract details
✅ **Error messages** indicate what went wrong
✅ **Source indicator** shows if SecurityMaster lookup succeeded

---

## Error Handling

### Contract Not Found
```
Error: Contract not found for TCS with expiry 2024-12-26

Cannot verify contract. Order cancelled.
```
**Action:** Order is automatically cancelled

### SecurityMaster Lookup Fails
```javascript
{
  "instrument": {
    "token": "Not found in SecurityMaster",
    "stock_code": "TCS",
    "lot_size": 125,
    "source": "ContractData fallback"
  }
}
```
**Action:** Shows fallback data, user can still proceed but knows SecurityMaster wasn't available

### API Error
```
Error fetching contract details: Network error

Order cancelled for safety.
```
**Action:** Order is automatically cancelled

---

## Console Logging

### Debug Output
```javascript
[DEBUG] Contract details from API: {
  success: true,
  symbol: "TCS",
  expiry: "2024-12-26",
  expiry_formatted: "26-DEC-2024",
  lot_size: 125,
  price: 4250.5,
  volume: 15000,
  instrument: {
    token: "52977",
    stock_code: "TCS",
    company_name: "Tata Consultancy Services Ltd",
    lot_size: 125,
    source: "SecurityMaster"
  }
}
```

---

## How to Verify Correct Contract

### Step 1: Check Instrument Token
Look up the instrument token in:
- ICICI Breeze terminal
- NSE website
- SecurityMaster CSV file

**Example:** TCS December 2024 futures should have a specific token (e.g., 52977)

### Step 2: Match Expiry
Verify the expiry date matches your selected contract:
- **Display format:** 26-DEC-2024
- **Database format:** 2024-12-26

### Step 3: Verify Lot Size
Check that lot size matches the contract:
- TCS futures: 125 lots
- NIFTY futures: 75 lots (changes periodically)

### Step 4: Check Source
Prefer "SecurityMaster" source:
- ✅ **SecurityMaster:** Most accurate, from official NSE data
- ⚠️ **ContractData fallback:** From database, may be stale

---

## Code Locations

### Backend
- **API Endpoint:** `apps/trading/api_views.py:1146-1224`
- **URL Route:** `apps/trading/urls.py:34`
- **SecurityMaster Lookup:** `apps/brokers/utils/security_master.py`

### Frontend
- **Contract Fetch:** `apps/trading/templates/trading/manual_triggers.html:2641-2709`
- **Confirmation Dialog:** Lines 2664-2691
- **Error Handling:** Lines 2652-2709

---

## Testing Checklist

When placing an order:

- [ ] Confirmation shows "Fetching contract details..." briefly
- [ ] Instrument token is displayed (not "N/A")
- [ ] Stock code matches symbol
- [ ] Company name is shown
- [ ] Lot size is correct
- [ ] Source shows "SecurityMaster" (preferred)
- [ ] Expiry date matches your selection
- [ ] Cancel works (doesn't place order)
- [ ] Confirm proceeds to order placement

### Error Scenarios to Test

- [ ] Invalid expiry → Shows error, cancels order
- [ ] Symbol not in database → Shows error, cancels order
- [ ] SecurityMaster unavailable → Shows fallback source
- [ ] Network error → Shows error, cancels order

---

## Security Considerations

### Pre-Flight Verification
✅ Fetches contract details **before** showing confirmation
✅ Cancels order if verification fails
✅ Does not proceed without successful contract lookup

### Data Validation
✅ Validates expiry format (YYYY-MM-DD)
✅ Checks contract exists in database
✅ Verifies SecurityMaster lookup

### User Confirmation
✅ Shows complete contract details
✅ User must explicitly confirm
✅ Can cancel at any time

---

## Future Enhancements

### Potential Improvements
- [ ] Show contract premium/discount to spot
- [ ] Display open interest
- [ ] Show bid/ask spreads
- [ ] Add "Copy Token" button
- [ ] Link to NSE contract details page
- [ ] Show historical price chart

### UX Improvements
- [ ] Use modal dialog instead of alert
- [ ] Add visual contract card
- [ ] Color-code by expiry (current/next month)
- [ ] Show similar contracts for comparison

---

## Summary

### What Was Added
1. ✅ New API endpoint `/api/get-contract-details/`
2. ✅ SecurityMaster instrument token lookup
3. ✅ Enhanced confirmation dialog with contract verification
4. ✅ Pre-flight contract validation
5. ✅ Comprehensive error handling

### Result
🎯 **Users can now verify the exact contract** (via instrument token) before placing orders
🔒 **Orders are cancelled** if contract cannot be verified
📊 **Complete transparency** with stock code, company name, lot size
✅ **Prevents wrong contract selection** with visual verification

---

**Implemented By:** Claude Code Assistant
**Date:** November 21, 2025
**Files Modified:** 3
**Lines Added:** ~150
**Status:** ✅ Ready for Testing
