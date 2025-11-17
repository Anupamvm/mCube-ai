# Trendlyne Data Download Triggers

## Overview
Added intelligent download triggers for Market Snapshot and Forecaster data with automatic freshness checks. These triggers prevent unnecessary downloads by checking if existing files are less than 10 minutes old.

## Features

### 1. Market Snapshot Data Trigger
**Button**: Available on System Test page (`/test/`)

**Functionality**:
- ✅ Checks if existing files are older than 10 minutes
- ✅ Only downloads if data is stale
- ✅ Automatically logs in to Trendlyne
- ✅ Downloads latest market snapshot
- ✅ Parses and populates `TLStockData` model
- ✅ Runs in background thread (no timeout)

**URL**: `/system/test/trigger-market-snapshot/`

**Button Labels**:
- "Refresh Data" - When files are > 10 minutes old
- "Download Again" - When files are < 10 minutes old
- "Download Now" - When no files exist
- "Create & Download" - When directory doesn't exist

### 2. Forecaster Data Trigger
**Button**: Available on System Test page (`/test/`)

**Functionality**:
- ✅ Checks if existing files are older than 10 minutes
- ✅ Only downloads if data is stale
- ✅ Automatically logs in to Trendlyne
- ✅ Downloads all 21 screener pages
- ✅ Saves CSV files to `apps/data/tldata/forecaster/`
- ✅ Runs in background thread (no timeout)

**URL**: `/system/test/trigger-forecaster/`

**Button Labels**:
- "Refresh Data" - When files are > 10 minutes old
- "Download Again" - When files are < 10 minutes old
- "Download Now" - When no files exist
- "Create & Download" - When directory doesn't exist

## Implementation Details

### Files Modified

#### 1. **apps/core/views.py**
Added two new trigger functions:

```python
@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_market_snapshot_download(request):
    """
    Trigger Market Snapshot data download and database population.
    Only downloads if existing files are older than 10 minutes.
    """
```

```python
@login_required
@user_passes_test(is_admin_user, login_url='/login/')
def trigger_forecaster_download(request):
    """
    Trigger Forecaster data download (21 screener pages).
    Only downloads if existing files are older than 10 minutes.
    """
```

**Updated test functions**:
- `test_trendlyne()` - Added trigger URLs and dynamic button labels to Market Snapshot test
- `test_trendlyne()` - Added trigger URLs and dynamic button labels to Forecaster test

#### 2. **apps/core/urls.py**
Added URL routes:
```python
path('test/trigger-market-snapshot/', views.trigger_market_snapshot_download, name='trigger_market_snapshot'),
path('test/trigger-forecaster/', views.trigger_forecaster_download, name='trigger_forecaster'),
```

## Workflow

### Market Snapshot Data Flow:
1. **User clicks "Refresh Data" button**
2. **System checks file age**
   - If < 10 minutes: Skip download, only parse existing data
   - If > 10 minutes: Proceed to download
3. **Download process** (if needed):
   - Initialize Chrome driver with download directory
   - Login to Trendlyne using credentials from `CredentialStore`
   - Navigate to Market Snapshot export page
   - Download latest XLSX/CSV file
   - Close browser
4. **Parse & Populate**:
   - Run `trendlyne_data_manager --parse-market-snapshot`
   - Populate `TLStockData` model
   - Log record count
5. **User feedback**:
   - Success message: "Market Snapshot data download initiated..."
   - Instruction: "Refresh in 30 seconds to see results"

### Forecaster Data Flow:
1. **User clicks "Refresh Data" button**
2. **System checks file age**
   - Checks most recent file in `forecaster/` directory
   - If < 10 minutes: Skip download
   - If > 10 minutes: Proceed to download
3. **Download process** (if needed):
   - Initialize Chrome driver
   - Login to Trendlyne
   - Navigate through 21 screener pages
   - Download each page as CSV
   - Save to `apps/data/tldata/forecaster/`
   - Close browser
4. **Count files**:
   - Log number of CSV files downloaded
   - Expected: 21 files
5. **User feedback**:
   - Success message: "Forecaster data download initiated (21 screener pages)..."
   - Instruction: "Refresh in 60 seconds to see results"

## Smart Freshness Check

### 10-Minute Threshold
Files are considered **fresh** if they were modified within the last 10 minutes.

**Rationale**:
- Trendlyne data updates periodically (not real-time)
- Market snapshot typically updates every few minutes during market hours
- Prevents redundant downloads and Trendlyne rate limiting
- Saves bandwidth and processing time

### Age Calculation:
```python
file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
age_minutes = (datetime.now() - file_time).total_seconds() / 60

if age_minutes < 10:
    logger.info(f"Data is fresh ({age_minutes:.1f} minutes old). Skipping download.")
    should_download = False
```

## Background Threading

Both triggers use background threading to prevent HTTP timeouts:

```python
thread = threading.Thread(target=task_function, daemon=True)
thread.start()
```

**Benefits**:
- Immediate response to user
- No 30-second timeout limit
- Long-running downloads (21 pages) don't block
- User can navigate away while download proceeds

## Test Page Display

### Market Snapshot Test:
```
✓ Market Snapshot Data
  Latest: market_snapshot_2025-11-16.xlsx (0 days old)
  [Refresh Data]  ← Button appears here
```

### Forecaster Test:
```
✓ Forecaster Data (21 Pages)
  Found 21 forecaster CSV files (expected 21)
  [Refresh Data]  ← Button appears here
```

## Error Handling

### Trendlyne Login Failure:
```python
login_success = login_to_trendlyne(driver)
if not login_success:
    logger.error("Failed to login to Trendlyne")
    return
```

### File System Errors:
- Directory creation: `os.makedirs(data_dir, exist_ok=True)`
- Missing files: Graceful handling with appropriate button labels
- Permission errors: Logged with full traceback

### Browser Errors:
- Driver cleanup: `finally: driver.quit()`
- Headless mode option: `settings.TRENDLYNE_HEADLESS`

## Logging

All operations are logged at appropriate levels:

```python
logger.info(f"Market Snapshot data is fresh ({age_minutes:.1f} minutes old). Skipping download.")
logger.info("Downloading Market Snapshot data from Trendlyne...")
logger.info("Market Snapshot data download completed")
logger.info(f"Market Snapshot data population completed: {record_count} stock records")
logger.error(f"Market Snapshot data task failed: {e}", exc_info=True)
```

## Database Population

### Market Snapshot:
- Model: `apps.data.models.TLStockData`
- Command: `trendlyne_data_manager --parse-market-snapshot`
- Records: Typically 500-2000 stocks
- Fields: Stock name, sector, price, P/E ratio, market cap, etc.

### Forecaster:
- Files: 21 CSV files in `forecaster/` directory
- Models: Multiple (depends on screener type)
- No automatic database population (files used for analysis)

## Usage Examples

### From Django Admin:
1. Navigate to `/test/` (System Test page)
2. Scroll to "Trendlyne Integration" section
3. Find "Market Snapshot Data" or "Forecaster Data (21 Pages)"
4. Click the trigger button
5. Wait for success message
6. Refresh page after suggested time (30-60 seconds)
7. Verify updated file timestamp or record count

### From Code:
```python
# Manually trigger Market Snapshot download
from apps.core.views import trigger_market_snapshot_download
from django.test import RequestFactory

factory = RequestFactory()
request = factory.post('/system/test/trigger-market-snapshot/')
request.user = admin_user  # Must be admin
trigger_market_snapshot_download(request)
```

## Comparison with Existing Triggers

| Feature | F&O Data | Market Snapshot | Forecaster |
|---------|----------|-----------------|------------|
| Freshness Check | ❌ No | ✅ 10 min | ✅ 10 min |
| Auto Login | ❌ Manual | ✅ Yes | ✅ Yes |
| Background Thread | ✅ Yes | ✅ Yes | ✅ Yes |
| Database Population | ✅ Yes | ✅ Yes | ❌ No |
| File Count | 1 | 1 | 21 |
| Download Time | ~10s | ~15s | ~120s |

## Recommendations

### For Daily Use:
1. Click "Refresh Data" button once per day during market hours
2. Let the system decide if download is needed (10-min check)
3. Monitor logs for any errors

### For Development:
1. Use "Download Again" even if files are fresh
2. Check `apps/data/tldata/` for downloaded files
3. Verify database record counts after population

### For Production:
1. Set up cron job to trigger daily at market close
2. Enable `TRENDLYNE_HEADLESS = True` in settings
3. Monitor background task logs

## Security

- ✅ Admin-only access (`@user_passes_test(is_admin_user)`)
- ✅ Login required (`@login_required`)
- ✅ POST method only (CSRF protection)
- ✅ Credentials stored encrypted in `CredentialStore`
- ✅ No credentials in logs or error messages

## Future Enhancements

1. **Email notifications** when downloads complete
2. **Telegram bot integration** for remote triggers
3. **Scheduling** via Celery periodic tasks
4. **Download history** tracking in database
5. **Partial downloads** for individual screeners
6. **Data validation** after population
7. **Automatic retry** on download failure
8. **Rate limiting** to prevent Trendlyne blocks
