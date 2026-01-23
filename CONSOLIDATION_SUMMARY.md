# Historical Data Model Consolidation - Summary

## Overview
Successfully consolidated historical data storage to use **only** the `HistoricalPrice` model from the `Brokers` module, removing the duplicate `HistoricalData` model from the `Trading` module.

## Changes Made

### 1. ✅ Enhanced HistoricalPrice Model (`apps/brokers/models.py`)

**Added Fields:**
- `interval` - Candle interval (1minute, 5minute, 30minute, 1day) with default '1day'

**Updated Constraints:**
- Updated `unique_together` to include `interval` field
- Added index for `['stock_code', 'exchange_code', 'product_type', 'interval', '-datetime']`
- Added index for `['stock_code', 'expiry_date', 'strike_price']`

**Added Methods:**
- `replace_data(cls, ...)` - Delete existing data and save fresh data from Breeze API
- `get_latest_data(cls, ...)` - Retrieve latest historical data for an instrument

### 2. ✅ Updated API Views (`apps/trading/api/historical_data_views.py`)

**Changed:**
- Import: `from apps.brokers.models import HistoricalPrice` (was `from apps.trading.models import HistoricalData`)
- All references: `HistoricalData` → `HistoricalPrice`

**Files Updated:**
- `get_breeze_historical_data()` - Fetch and save API endpoint
- `get_stored_historical_data()` - Retrieve from database endpoint
- `prepare_historical_data()` - Data preparation endpoint
- `verify_historical_data()` - Verification endpoint

### 3. ✅ Updated Futures Analyzer (`apps/trading/futures_analyzer.py`)

**Changed:**
- Import: `from apps.brokers.models import HistoricalPrice`
- All references: `HistoricalData` → `HistoricalPrice`
- Field: `fetched_at` → `created_at` (inherited from TimeStampedModel)

**Functions Updated:**
- `fetch_historical_data_for_instrument()` - Data fetching
- `verify_historical_data()` - Historical verification
- `prepare_data_for_analysis()` - Data preparation

### 4. ✅ Removed from Trading Admin (`apps/trading/admin.py`)

**Removed:**
- Import of `HistoricalData` from models
- Entire `HistoricalDataAdmin` class (lines 469-554)
  - list_display, list_filter, search_fields
  - fieldsets configuration
  - price_display() method
  - raw_data_display() method
  - get_queryset() optimization

### 5. ✅ Removed HistoricalData Model (`apps/trading/models.py`)

**Deleted:**
- Entire `HistoricalData` class (lines 461-663)
  - INTERVAL_CHOICES
  - PRODUCT_TYPE_CHOICES
  - RIGHT_CHOICES
  - All field definitions
  - Meta class with indexes and constraints
  - __str__() method
  - replace_data() classmethod
  - get_latest_data() classmethod

### 6. ✅ Updated Documentation

**Files Updated:**
- `HISTORICAL_DATA_SETUP.md`
  - File path: `apps/trading/models.py` → `apps/brokers/models.py`
  - Model name: `HistoricalData` → `HistoricalPrice`

- `apps/trading/api/HISTORICAL_DATA_API_USAGE.md`
  - All model references: `HistoricalData` → `HistoricalPrice`
  - Import statements updated

## Migration Required

After these code changes, you **MUST** run database migrations:

```bash
# Step 1: Create migration for HistoricalPrice changes
python manage.py makemigrations brokers

# Step 2: Create migration to remove HistoricalData
python manage.py makemigrations trading

# Step 3: Apply migrations
python manage.py migrate
```

## Database Changes

### What Will Happen:
1. **brokers_historicalprice** table will be updated:
   - New `interval` column added (default: '1day')
   - New indexes created
   - Updated unique constraint

2. **trading_historicaldata** table will be **DROPPED**:
   - All data in this table will be **LOST**
   - If you have important data, export it first!

### Data Migration (if needed):
If you have existing data in `trading_historicaldata` that you want to keep:

```python
# Run this BEFORE migrations
from apps.trading.models import HistoricalData  # Old model
from apps.brokers.models import HistoricalPrice  # New model

# Copy all data
for old_record in HistoricalData.objects.all():
    HistoricalPrice.objects.create(
        datetime=old_record.datetime,
        stock_code=old_record.stock_code,
        exchange_code=old_record.exchange_code,
        product_type=old_record.product_type,
        interval=old_record.interval,
        expiry_date=old_record.expiry_date,
        right=old_record.right,
        strike_price=old_record.strike_price,
        open=old_record.open,
        high=old_record.high,
        low=old_record.low,
        close=old_record.close,
        volume=old_record.volume,
        open_interest=old_record.open_interest or 0,
    )
```

## Benefits of Consolidation

1. **Single Source of Truth**: All historical data in one place
2. **Better Organization**: Historical data under Brokers (data source) makes more sense
3. **No Duplication**: Eliminates confusion about which model to use
4. **Cleaner Admin**: Historical data appears once in Django Admin under "Brokers"
5. **Consistent API**: All code uses the same model and methods

## Testing Checklist

After migration, test these functions:

- [ ] Fetch historical data from Breeze API
  ```bash
  curl -X POST http://localhost:8000/trading/api/get-breeze-historical-data/ \
    -H "Content-Type: application/json" \
    -d '{"stock_code": "ITC", "from_date": "2025-01-01", "to_date": "2025-01-23", "interval": "1day"}'
  ```

- [ ] Retrieve stored historical data
  ```bash
  curl -X GET "http://localhost:8000/trading/api/get-stored-historical-data/?stock_code=ITC&interval=1day"
  ```

- [ ] Verify futures trade (uses historical data)
  - Go to http://localhost:8000/trading/triggers/#verify
  - Select a contract and verify

- [ ] Check Django Admin
  - Go to http://localhost:8000/admin/
  - Navigate to Brokers > Historical Prices
  - Verify data displays correctly

- [ ] Run test suite
  ```bash
  python scripts/test/test_historical_data_api.py
  ```

## Files Changed Summary

| File | Action | Lines Changed |
|------|--------|---------------|
| `apps/brokers/models.py` | Enhanced | +115 lines (interval field + methods) |
| `apps/trading/models.py` | Removed model | -203 lines |
| `apps/trading/admin.py` | Removed admin | -87 lines |
| `apps/trading/api/historical_data_views.py` | Updated imports | 1 line + replacements |
| `apps/trading/futures_analyzer.py` | Updated imports | 1 line + replacements |
| `HISTORICAL_DATA_SETUP.md` | Updated | Multiple replacements |
| `apps/trading/api/HISTORICAL_DATA_API_USAGE.md` | Updated | Multiple replacements |

## Rollback Plan

If something goes wrong, you can rollback:

```bash
# 1. Revert code changes
git checkout -- apps/brokers/models.py
git checkout -- apps/trading/models.py
git checkout -- apps/trading/admin.py
git checkout -- apps/trading/api/historical_data_views.py
git checkout -- apps/trading/futures_analyzer.py

# 2. Rollback migrations
python manage.py migrate brokers <previous_migration>
python manage.py migrate trading <previous_migration>
```

## Next Steps

1. **Backup database** (recommended before migrations)
2. **Run migrations** (see commands above)
3. **Test all functionality** (use checklist above)
4. **Monitor logs** for any errors
5. **Re-fetch historical data** if needed

## Admin Interface

**Before:**
- Trading > Historical Data (duplicate)
- Brokers > Historical Prices

**After:**
- Brokers > Historical Prices (only location)

All historical data is now managed through the Brokers admin interface.

---

## Status: ✅ Code Changes Complete

**Pending:** Run database migrations

**Date Completed:** 2026-01-23
