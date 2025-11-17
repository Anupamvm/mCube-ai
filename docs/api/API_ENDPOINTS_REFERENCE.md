# API Endpoints Reference - System Test & Triggers

**Last Updated**: 2025-11-16
**Status**: ✅ PRODUCTION READY

---

## Overview

The System Test Page provides manual trigger endpoints for managing Trendlyne data operations. All endpoints require authentication and admin privileges.

---

## Endpoint: System Test Page

### GET `/system/test/`

**Purpose**: Display comprehensive system health check dashboard

**Authentication**: Login required (admin)

**Response**: HTML page with:
- System health statistics (total/passed/failed tests)
- Test results organized by category
- Trigger buttons for data operations
- Real-time database record counts
- File freshness information

**Example Usage**:
```bash
curl -b cookies.txt http://127.0.0.1:8000/system/test/
```

**Display Output**:
```
Dashboard Statistics:
- Total Tests: 45
- Passed: 42
- Failed: 3
- Pass Rate: 93.33%

Trendlyne Integration Section:
[Test 5] F&O Data Freshness
  ✓ Latest: contract_data.csv (0 days old) | Updated 5 records at 2025-11-16 15:59:55
  [Populate Data Button]

[Test 13] Trendlyne Database Summary
  ✓ Total: 51 records | Last update: 2025-11-16 10:09:21 | ...
  [Refresh Data Button]
```

**Status Codes**:
- `200`: Success (page displayed)
- `403`: Access denied (not admin)
- `404`: Page not found

---

## Endpoint: F&O Data Population Trigger

### POST `/system/test/trigger-fno-data/`

**Purpose**: Parse existing F&O CSV files and populate ContractData table

**Authentication**:
- Login required ✓
- Admin privilege required ✓

**Method**: POST only

**Request Format**:
```html
<!-- Automatically submitted via form button -->
<form method="post" action="/system/test/trigger-fno-data/">
  <input type="hidden" name="csrfmiddlewaretoken" value="...">
  <button type="submit">Populate Data</button>
</form>
```

**cURL Example**:
```bash
curl -X POST \
  -H "X-CSRFToken: <token>" \
  -b cookies.txt \
  http://127.0.0.1:8000/system/test/trigger-fno-data/
```

**What It Does**:
1. Starts background thread (non-blocking)
2. Executes: `python manage.py trendlyne_data_manager --parse-all`
3. Parses CSV files from `/trendlyne_data/contract_*.csv`
4. Updates ContractData database table
5. Counts resulting records
6. Logs operation with record count
7. Redirects user back to test page with success message

**Response**: Redirect to `/system/test/` with message

**Success Message**:
```
✅ F&O data population initiated.
   Refresh in 30 seconds to see updated record counts.
```

**Error Message**:
```
❌ Failed to start F&O data population: [Error Details]
```

**Processing Time**: ~30 seconds

**Log Entry**:
```
2025-11-16 16:00:15,123 INFO: F&O data population completed: 125 contract records
```

**Status Codes**:
- `302`: Redirect (successful trigger, processing in background)
- `403`: Access denied (not authenticated or not admin)
- `405`: Method not allowed (must use POST)

**Database Changes**:
- **Table Modified**: `data_contractdata`
- **Records Affected**: All matching contract records
- **Example**: 5 records created/updated with timestamps

---

## Endpoint: Full Trendlyne Data Cycle Trigger

### POST `/system/test/trigger-trendlyne-full/`

**Purpose**: Execute complete Trendlyne data pipeline (download → parse → populate → cleanup)

**Authentication**:
- Login required ✓
- Admin privilege required ✓

**Method**: POST only

**Request Format**:
```html
<form method="post" action="/system/test/trigger-trendlyne-full/">
  <input type="hidden" name="csrfmiddlewaretoken" value="...">
  <button type="submit">Refresh Data</button>
</form>
```

**cURL Example**:
```bash
curl -X POST \
  -H "X-CSRFToken: <token>" \
  -b cookies.txt \
  http://127.0.0.1:8000/system/test/trigger-trendlyne-full/
```

**What It Does** (4-Phase Cycle):

**Phase 1: Clear Previous Files**
- Removes all CSV/XLSX files from `/trendlyne_data/`
- Cleans up from previous run
- Estimated time: ~2 seconds

**Phase 2: Download New Data**
- Launches Selenium Chrome browser
- Logs into Trendlyne.com
- Downloads 8 data types:
  - Contract data (F&O)
  - Contract stock data
  - Stock fundamentals
  - Option chains
  - Economic events
  - Financial news
  - Investor calls
  - Knowledge base
- Saves to `/trendlyne_data/` as CSV files
- Estimated time: ~30-45 seconds

**Phase 3: Parse & Populate Database**
- Reads each CSV file with pandas
- Converts to Django model instances
- Performs atomic database inserts
- 8 database tables updated:
  - `data_contractdata`
  - `data_contractstockdata`
  - `data_tlstockdata`
  - `data_optionchain`
  - `data_event`
  - `data_newsarticle`
  - `data_investorcall`
  - `data_knowledgebase`
- Estimated time: ~10-15 seconds

**Phase 4: Clean Temporary Files**
- Deletes all downloaded CSV files
- Removes temporary folder if empty
- Frees disk space
- Estimated time: ~2 seconds

**Total Processing Time**: ~60-90 seconds

**Response**: Redirect to `/system/test/` with message

**Success Message**:
```
✅ Full Trendlyne data cycle initiated
   (Download → Parse → Populate → Cleanup).
   Refresh in 60 seconds to see all updated statistics.
```

**Error Message**:
```
❌ Failed to start Trendlyne full cycle: [Error Details]
```

**Log Entries**:
```
2025-11-16 16:01:15,234 INFO: [1/4] Clearing previous files...
2025-11-16 16:01:17,456 INFO: ✅ Cleared files: /trendlyne_data

2025-11-16 16:01:18,789 INFO: [2/4] Downloading data from Trendlyne...
2025-11-16 16:01:45,123 INFO: ✅ Download phase complete

2025-11-16 16:01:46,456 INFO: [3/4] Parsing files and populating database...
2025-11-16 16:02:00,789 INFO: ✅ Parse phase complete

2025-11-16 16:02:01,234 INFO: [4/4] Cleaning up temporary files...
2025-11-16 16:02:03,567 INFO: ✅ Cleaned files: /trendlyne_data

2025-11-16 16:02:03,890 INFO: Full Trendlyne cycle completed: 300 total records | {
  'ContractData': 125,
  'ContractStockData': 45,
  'TLStockData': 50,
  'OptionChain': 60,
  'Event': 15,
  'NewsArticle': 12,
  'InvestorCall': 8,
  'KnowledgeBase': 10
}
```

**Database Changes**:
- **Tables Modified**: All 8 Trendlyne data tables
- **Records Example**: 300 total records created/updated
- **Timestamp**: All records marked with operation timestamp
- **Transaction**: Atomic operation (all-or-nothing)

**Status Codes**:
- `302`: Redirect (successful trigger, processing in background)
- `403`: Access denied (not authenticated or not admin)
- `405`: Method not allowed (must use POST)

---

## Endpoint: Existing Trendlyne Download Trigger

### POST `/system/test/trigger-trendlyne/`

**Purpose**: Download Trendlyne data (deprecated - use full cycle instead)

**Authentication**:
- Login required ✓
- Admin privilege required ✓

**Method**: POST only

**Note**: This endpoint is for compatibility. Use `trigger-trendlyne-full/` for complete pipeline.

**Response**: Redirect to `/system/test/` with message

**Processing Time**: ~30-45 seconds

---

## Common Response Patterns

### Success Flow
```
1. User clicks trigger button on test page
2. Browser POSTs to endpoint with CSRF token
3. View validates request (POST, authenticated, admin)
4. Background thread started for long operation
5. Immediate redirect response sent to browser
6. User sees success message
7. Browser displays: "Refresh in X seconds to see results"
8. User waits X seconds
9. User clicks Refresh or presses F5
10. Page loads current database state
11. Updated record counts and timestamps displayed
```

### Error Flow
```
1. User clicks trigger button
2. Browser POSTs request
3. View detects error during setup
4. No background thread started
5. Redirect response with error message
6. User sees error notification
7. Error logged for debugging
8. User can retry or check logs
```

### Authentication Flow
```
1. Unauthenticated user tries to access endpoint
2. View decorator redirects to login page
3. User logs in
4. Browser redirects back to test page
5. User clicks trigger button again
6. Request succeeds (now authenticated)
```

---

## Request/Response Examples

### Example 1: F&O Population Success

**Request**:
```http
POST /system/test/trigger-fno-data/ HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/x-www-form-urlencoded
Cookie: sessionid=abc123...
X-CSRFToken: xyz789...

csrfmiddlewaretoken=xyz789...
```

**Response**:
```http
HTTP/1.1 302 Found
Location: /system/test/
Set-Cookie: messages=...

<Redirect to /system/test/>
```

**Page Message** (after redirect):
```
✅ F&O data population initiated.
   Refresh in 30 seconds to see updated record counts.
```

**Django Log**:
```
2025-11-16 16:00:15,123 INFO: F&O data population completed: 125 contract records
```

---

### Example 2: Full Cycle Success

**Request**:
```http
POST /system/test/trigger-trendlyne-full/ HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/x-www-form-urlencoded
Cookie: sessionid=abc123...
X-CSRFToken: xyz789...

csrfmiddlewaretoken=xyz789...
```

**Response**:
```http
HTTP/1.1 302 Found
Location: /system/test/
Set-Cookie: messages=...

<Redirect to /system/test/>
```

**Page Message** (after redirect):
```
✅ Full Trendlyne data cycle initiated
   (Download → Parse → Populate → Cleanup).
   Refresh in 60 seconds to see all updated statistics.
```

**Django Log** (abbreviated):
```
2025-11-16 16:01:15 INFO: [1/4] Clearing previous files...
2025-11-16 16:01:18 INFO: [2/4] Downloading data from Trendlyne...
2025-11-16 16:01:45 INFO: ✅ Download phase complete
2025-11-16 16:01:46 INFO: [3/4] Parsing files and populating database...
2025-11-16 16:02:00 INFO: ✅ Parse phase complete
2025-11-16 16:02:01 INFO: [4/4] Cleaning up temporary files...
2025-11-16 16:02:03 INFO: Full Trendlyne cycle completed: 300 total records
```

---

### Example 3: Authentication Error

**Request** (not authenticated):
```http
POST /system/test/trigger-fno-data/ HTTP/1.1
Host: 127.0.0.1:8000

csrfmiddlewaretoken=...
```

**Response**:
```http
HTTP/1.1 302 Found
Location: /login/?next=/system/test/trigger-fno-data/

<Redirect to login page>
```

---

### Example 4: Permission Error

**Request** (authenticated but not admin):
```http
POST /system/test/trigger-fno-data/ HTTP/1.1
Host: 127.0.0.1:8000
Cookie: sessionid=user_not_admin...
X-CSRFToken: ...

csrfmiddlewaretoken=...
```

**Response**:
```http
HTTP/1.1 302 Found
Location: /login/?next=/system/test/trigger-fno-data/

<Redirect to login page (user_passes_test failed)>
```

---

## Background Processing Model

```
Timeline for Full Cycle Trigger:
├─ T+0s:     User clicks "Refresh Data" button
├─ T+0.5s:   Browser POSTs to /system/test/trigger-trendlyne-full/
├─ T+1s:     Django view receives request
├─ T+1.5s:   Admin check passes (user is authorized)
├─ T+2s:     Background thread spawned (daemon=True)
│            │ Thread begins: call_command('trendlyne_data_manager --full-cycle')
│            ├─ T+2s → T+20s:  Phase 1-2: Clear & Download files
│            ├─ T+20s → T+40s: Phase 3: Parse & populate database
│            └─ T+40s → T+42s: Phase 4: Cleanup temp files
├─ T+2.5s:   View returns redirect response to user
├─ T+3s:     Browser displays success message
├─ T+3s:     User sees: "Refresh in 60 seconds..."
├─ T+63s:    User refreshes page
├─ T+63.5s:  Server queries database for new counts
└─ T+64s:    Page displays updated statistics
             ✓ Test 13: Total 300 records, Last update: 2025-11-16 16:02:03
```

---

## Testing with cURL

### Setup: Get CSRF Token and Session

```bash
# 1. Get session cookie and CSRF token
curl -c cookies.txt http://127.0.0.1:8000/system/test/ > /tmp/page.html

# 2. Extract CSRF token
CSRF_TOKEN=$(grep -oP "name=\"csrfmiddlewaretoken\" value=\"\K[^\"]*" /tmp/page.html)

# 3. Login first
curl -b cookies.txt -c cookies.txt \
  -X POST \
  -d "username=admin&password=password" \
  http://127.0.0.1:8000/login/

# 4. Get new CSRF token (post-login)
curl -b cookies.txt http://127.0.0.1:8000/system/test/ > /tmp/page2.html
CSRF_TOKEN=$(grep -oP "name=\"csrfmiddlewaretoken\" value=\"\K[^\"]*" /tmp/page2.html)
```

### Trigger F&O Population

```bash
curl -X POST \
  -b cookies.txt \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d "csrfmiddlewaretoken=$CSRF_TOKEN" \
  http://127.0.0.1:8000/system/test/trigger-fno-data/ \
  -L  # Follow redirects

# Expected output: Redirects to /system/test/ with success message
```

### Trigger Full Cycle

```bash
curl -X POST \
  -b cookies.txt \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d "csrfmiddlewaretoken=$CSRF_TOKEN" \
  http://127.0.0.1:8000/system/test/trigger-trendlyne-full/ \
  -L  # Follow redirects

# Expected output: Redirects to /system/test/ with success message
```

---

## Error Handling & Recovery

### If Operation Fails

**Problem**: Button shows "Download & Populate" after operation

**Solution**:
1. Check Django logs for error details
2. Fix underlying issue (file permissions, API access, etc.)
3. Click button again to retry

**Log Location**: `logs/django.log` or console output

### If Files Are Stuck

**Problem**: Files not being cleaned up after cycle

**Solution**:
```bash
# Manual cleanup
python manage.py shell
>>> from apps.data.tools.trendlyne_downloader import cleanup_trendlyne_data
>>> cleanup_trendlyne_data()
```

### If Database Has Stale Data

**Problem**: Record counts don't match expected values

**Solution**:
1. Click "Refresh Data" to re-download and parse
2. Or manually clear:
```bash
python manage.py shell
>>> from apps.data.models import ContractData
>>> ContractData.objects.all().delete()
```

---

## Performance Characteristics

| Operation | Duration | Disk I/O | Memory | CPU |
|-----------|----------|----------|--------|-----|
| F&O Parse | ~30s | Low | ~100MB | Medium |
| Full Download | ~45s | Medium | ~150MB | High |
| Parse & Insert | ~15s | High | ~200MB | High |
| Cleanup | ~2s | Low | ~50MB | Low |

---

## Rate Limiting

**Current**: None implemented

**Recommended for Production**:
- Max 1 full cycle per 5 minutes
- Max 1 F&O parse per 1 minute
- Implement via cache or database flags

---

## Monitoring & Alerting

### Key Metrics to Monitor

1. **Operation Duration**: Should complete within expected time
2. **Record Count**: Should match expected totals
3. **Error Rate**: Should be 0 for successful deployments
4. **Disk Space**: Should have >1GB free

### Log Entry Format

```
[TIMESTAMP] [LEVEL] [Module]: [Message]

Example:
2025-11-16 16:01:15,234 INFO: [1/4] Clearing previous files...
2025-11-16 16:01:45,123 WARNING: ⚠️  No data for Contract Data
2025-11-16 16:02:03,890 ERROR: ❌ Failed to populate NewsArticle table
```

---

**Last Updated**: 2025-11-16
**Status**: ✅ PRODUCTION READY
**Tested**: Yes, all endpoints verified
