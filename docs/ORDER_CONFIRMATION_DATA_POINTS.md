# Order Confirmation Dialog - Complete Data Points Reference

**Purpose:** Technical reference for all data points displayed in order confirmation dialogs
**Date:** November 21, 2024

---

## 🔵 FUTURES ORDER CONFIRMATION DATA

### Primary Data Points
| Data Field | Variable Name | Source | Format | Example |
|------------|--------------|--------|--------|---------|
| Symbol | `contract.symbol` | Frontend State | String | "TCS" |
| Expiry | `contractDetails.expiry_formatted` | API Response | DD-MMM-YYYY | "26-DEC-2024" |
| Direction | `contract.direction` | User Selection | String | "LONG" or "SHORT" |
| Lots | `contract.lots` | User Input | Number | 5 |
| Quantity | `contract.lots * lotSize` | Calculated | Number | 625 |
| Entry Price | `contract.entry_price` | Analyzed/Market | Currency | ₹4,250.00 |
| Margin | `marginRequired` | Calculated | Currency | ₹2,65,625 |

### Contract Verification Data
| Data Field | Variable Name | Source | Format | Example |
|------------|--------------|--------|--------|---------|
| Instrument Token | `instrument.token` | SecurityMaster | String | "52977" |
| Stock Code | `instrument.stock_code` | SecurityMaster | String | "TCS" |
| Company Name | `instrument.company_name` | SecurityMaster | String | "Tata Consultancy Services Ltd" |
| Lot Size | `instrument.lot_size` | SecurityMaster | Number | 125 |
| Data Source | `instrument.source` | API Response | String | "SecurityMaster" or "ContractData fallback" |

### API Response Structure (Futures)
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

### Frontend Code Location
- **File:** `apps/trading/templates/trading/manual_triggers.html`
- **Lines:** 2641-2709
- **Function:** Part of `placeOrder()` function

### Backend Code Location
- **File:** `apps/trading/api_views.py`
- **Lines:** 1146-1224
- **Endpoint:** `/trading/api/get-contract-details/`

---

## 🟢 STRANGLE ORDER CONFIRMATION DATA

### Header Information
| Data Field | Variable Name | Source | Format | Example |
|------------|--------------|--------|--------|---------|
| Suggestion ID | `suggestion.id` | Database | String | "#123" |
| Strategy | Fixed Text | Hardcoded | String | "Nifty SHORT Strangle" |
| Spot Price | `suggestion.spot_price` | Market Data | Currency | ₹27,000 |
| Expiry Date | `suggestion.expiry` | Suggestion | Date | "2024-11-28" |
| Days to Expiry | Calculated | Frontend | String | "7 days" |

### CALL Contract Data
| Data Field | Variable Name | Source | Format | Example |
|------------|--------------|--------|--------|---------|
| Strike | `suggestion.call_strike` | Suggestion | Number | 27050 |
| Premium | `suggestion.call_premium` | Market Data | Currency | ₹125.50 |
| Symbol | `callSymbol` | Constructed | String | "NIFTY28NOV27050CE" |
| Token | `callData.instrument_token` | Neo API | String | "NIFTY28NOV27050CE" |
| Expiry | `callData.expiry` | Neo API | String | "28NOV2024" |

### PUT Contract Data
| Data Field | Variable Name | Source | Format | Example |
|------------|--------------|--------|--------|---------|
| Strike | `suggestion.put_strike` | Suggestion | Number | 26950 |
| Premium | `suggestion.put_premium` | Market Data | Currency | ₹118.75 |
| Symbol | `putSymbol` | Constructed | String | "NIFTY28NOV26950PE" |
| Token | `putData.instrument_token` | Neo API | String | "NIFTY28NOV26950PE" |
| Expiry | `putData.expiry` | Neo API | String | "28NOV2024" |

### Trade Execution Data
| Data Field | Variable Name | Source | Format | Example |
|------------|--------------|--------|--------|---------|
| Lots | `suggestion.lots` | User Input | Number | 10 |
| Lot Size | `lotSize` | Neo API | Number | 75 |
| Total Quantity | `lots * lotSize` | Calculated | Number | 750 |
| Premium Collection | Calculated | Frontend | Currency | ₹1,83,187 |
| Margin Required | `suggestion.margin` | Calculated | Currency | ₹2,45,000 |
| Margin Available | `suggestion.availableMargin` | Account | Currency | ₹5,00,000 |

### API Response Structure (Options)
```json
{
  "success": true,
  "lot_size": 75,
  "symbol": "NIFTY28NOV27050CE",
  "instrument_token": "NIFTY28NOV27050CE",
  "expiry": "28NOV2024",
  "exchange_segment": "nse_fo"
}
```

### Frontend Code Location
- **File:** `apps/trading/templates/trading/manual_triggers.html`
- **Lines:** 5281-5366
- **Function:** Inside strangle confirmation handler

### Backend Code Location
- **File:** `apps/trading/api_views.py`
- **Lines:** 1227-1273
- **Endpoint:** `/trading/api/get-lot-size/`
- **Neo Integration:** `apps/brokers/integrations/kotak_neo.py:567-663`

---

## 📊 CALCULATED FIELDS

### Futures Calculations
```javascript
// Quantity Calculation
const quantity = contract.lots * lotSize;

// Margin Calculation (15% for futures)
const marginRequired = quantity * entryPrice * 0.15;

// Position Value
const positionValue = quantity * entryPrice;
```

### Options Calculations
```javascript
// Total Premium per lot
const callPremiumPerLot = callPremium * lotSize;
const putPremiumPerLot = putPremium * lotSize;

// Total Premium Collection
const totalPremium = (callPremiumPerLot + putPremiumPerLot) * lots;

// Days to Expiry
const daysToExpiry = Math.ceil((expiryDate - today) / (1000 * 60 * 60 * 24));
```

---

## 🔄 DATA FLOW SEQUENCE

### Futures Order Flow
```
1. User Action: Click "Place Order"
   ↓
2. Fetch Contract Details
   Request: GET /trading/api/get-contract-details/?symbol=TCS&expiry=2024-12-26
   ↓
3. Backend Processing
   - Query SecurityMaster for instrument token
   - Fetch contract data from database
   - Format expiry date for display
   ↓
4. Response Processing
   - Extract instrument details
   - Calculate margin requirements
   - Format confirmation message
   ↓
5. Display Confirmation
   - Show all data points in modal
   - Wait for user confirmation
   ↓
6. Order Placement
   POST /trading/api/place-futures-order/
   with expiry parameter included
```

### Strangle Order Flow
```
1. User Action: Click "Take This Trade"
   ↓
2. Parallel API Calls
   - GET /trading/api/get-lot-size/?trading_symbol=NIFTY28NOV27050CE
   - GET /trading/api/get-lot-size/?trading_symbol=NIFTY28NOV26950PE
   ↓
3. Neo API Processing (for each leg)
   - Call search_scrip() with symbol details
   - Extract token and lot size
   - Return contract information
   ↓
4. Frontend Processing
   - Combine CALL and PUT data
   - Calculate totals
   - Format confirmation dialog
   ↓
5. Display Confirmation
   - Show both contract details
   - Display tokens and expiries
   - Show margin and premium calculations
   ↓
6. Order Execution
   - Place CALL order via Neo API
   - Place PUT order via Neo API
   - 20-second delay between orders
```

---

## 🛠️ VARIABLE MAPPINGS

### Frontend to Backend Mapping (Futures)
| Frontend Variable | URL Parameter | Backend Variable | Database Field |
|-------------------|---------------|------------------|----------------|
| `contract.symbol` | `symbol` | `symbol_param` | `ContractData.symbol` |
| `contract.expiry_date` | `expiry` | `expiry_param` | `ContractData.expiry` |
| `contract.lots` | `lots` | `lots` | N/A (user input) |
| `contract.direction` | `direction` | `direction` | N/A (user input) |

### Frontend to Backend Mapping (Options)
| Frontend Variable | URL Parameter | Backend Variable | Neo API Parameter |
|-------------------|---------------|------------------|-------------------|
| `callSymbol` | `trading_symbol` | `trading_symbol` | Parsed for search |
| Symbol part | N/A | `symbol_name` | `symbol` |
| Expiry part | N/A | `expiry_str` | `expiry` |
| Strike part | N/A | `strike_price` | `strike_price` |
| CE/PE part | N/A | `option_type` | `option_type` |

---

## 🔍 DEBUG DATA POINTS

### Console Logging (Futures)
```javascript
console.log('[DEBUG] Contract details from API:', {
    success: true/false,
    symbol: "TCS",
    expiry: "2024-12-26",
    expiry_formatted: "26-DEC-2024",
    instrument: {
        token: "52977",
        stock_code: "TCS",
        lot_size: 125,
        source: "SecurityMaster"
    }
});
```

### Console Logging (Options)
```javascript
console.log('[DEBUG] CALL token:', callData.instrument_token);
console.log('[DEBUG] CALL expiry:', callData.expiry);
console.log('[DEBUG] PUT token:', putData.instrument_token);
console.log('[DEBUG] PUT expiry:', putData.expiry);
console.log('[DEBUG] Lot size:', lotSize);
```

### Backend Logging
```python
# Futures
logger.info(f"Searching SecurityMaster for {symbol} with expiry {expiry}")
logger.info(f"Found token: {token} for {symbol}")

# Options
logger.info(f"Searching scrip: symbol={symbol_name}, expiry={expiry_full}")
logger.info(f"Found scrip details: lot_size={lot_size}, token={token}")
```

---

## ✅ VALIDATION CHECKPOINTS

### Required Fields (Never Empty)
- ✅ Symbol (both Futures and Options)
- ✅ Expiry date (must be valid future date)
- ✅ Direction (LONG/SHORT for Futures)
- ✅ Lots (positive integer)
- ✅ Strike prices (for Options)

### Optional Fields (Can Be Empty)
- ⚠️ Instrument token (shows "N/A" if API fails)
- ⚠️ Company name (may be empty for indices)
- ⚠️ Volume data (may be 0 for illiquid contracts)

### Fallback Values
| Field | Fallback | When Used |
|-------|----------|-----------|
| Lot Size | 75 (NIFTY) or 125 (stocks) | SecurityMaster not available |
| Token | "N/A" | API failure |
| Source | "ContractData fallback" | SecurityMaster miss |
| Expiry Format | Original format | Formatting fails |

---

**This document provides complete technical reference for all data points in order confirmation dialogs.**