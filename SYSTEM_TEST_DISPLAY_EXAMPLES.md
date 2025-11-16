# System Test Page - Display Examples

**URL**: http://127.0.0.1:8000/system/test/

---

## Dashboard Header

```
mCube AI - System Test Dashboard
Comprehensive system health check for all critical functionalities

Total Tests: 45
Passed: 42
Failed: 3
Pass Rate: 93.33%
```

---

## Trendlyne Integration Section (Current Status)

### Test 5: F&O Data Freshness

#### Scenario 1: Fresh Data Available
```
✓ F&O Data Freshness [PASS]
  Latest: contract_data.csv (0 days old) | Updated 5 records at 2025-11-16 15:59:55

  [Populate Data]
```

**Color**: Green background on status indicator

#### Scenario 2: Stale Data (3 days old)
```
⚠ F&O Data Freshness [WARNING]
  Latest: contract_data.csv (3 days old) | Updated 125 records at 2025-11-13 10:20:15

  [Populate Data]
```

**Color**: Orange background on status indicator

#### Scenario 3: No Data Files
```
✗ F&O Data Freshness [FAIL]
  No F&O data files found in trendlyne_data directory

  [Download & Populate]
```

**Color**: Red background on status indicator

#### Scenario 4: Directory Missing
```
✗ F&O Data Freshness [FAIL]
  Data directory not found at /trendlyne_data

  [Create & Download]
```

**Color**: Red background on status indicator

---

### Test 13: Trendlyne Database Summary

#### Scenario 1: Database Populated (Current)
```
✓ Trendlyne Database Summary [PASS]
  Total: 51 records | Last update: 2025-11-16 10:09:21 |
  ContractData: 5 | ContractStockData: 5 | TLStockData: 10 |
  OptionChain: 10 | Event: 10 | NewsArticle: 8 |
  InvestorCall: 1 | KnowledgeBase: 2

  [Refresh Data]
```

**Color**: Green background on status indicator

#### Scenario 2: Large Dataset
```
✓ Trendlyne Database Summary [PASS]
  Total: 300 records | Last update: 2025-11-16 15:30:45 |
  ContractData: 125 | ContractStockData: 45 | TLStockData: 50 |
  OptionChain: 60 | Event: 15 | NewsArticle: 12 |
  InvestorCall: 8 | KnowledgeBase: 10

  [Refresh Data]
```

**Color**: Green background on status indicator

#### Scenario 3: Empty Database
```
✗ Trendlyne Database Summary [FAIL]
  Total: 0 records | Last update: Never |
  ContractData: 0 | ContractStockData: 0 | TLStockData: 0 |
  OptionChain: 0 | Event: 0 | NewsArticle: 0 |
  InvestorCall: 0 | KnowledgeBase: 0

  [Download Now]
```

**Color**: Red background on status indicator

---

## User Actions & Messages

### Action 1: Click "Populate Data" Button

**Immediate Response** (page redirects):
```
✅ F&O data population initiated.
   Refresh in 30 seconds to see updated record counts.
```

**After 30 seconds** (user refreshes):
```
✓ F&O Data Freshness [PASS]
  Latest: contract_data.csv (0 days old) | Updated 125 records at 2025-11-16 16:00:15

  [Populate Data]
```

**Backend Log Entry**:
```
2025-11-16 16:00:15,123 INFO: F&O data population completed: 125 contract records
```

---

### Action 2: Click "Refresh Data" Button

**Immediate Response** (page redirects):
```
✅ Full Trendlyne data cycle initiated
   (Download → Parse → Populate → Cleanup).
   Refresh in 60 seconds to see all updated statistics.
```

**After 60 seconds** (user refreshes):
```
✓ Trendlyne Database Summary [PASS]
  Total: 300 records | Last update: 2025-11-16 16:01:45 |
  ContractData: 125 | ContractStockData: 45 | TLStockData: 50 |
  OptionChain: 60 | Event: 15 | NewsArticle: 12 |
  InvestorCall: 8 | KnowledgeBase: 10

  [Refresh Data]
```

**Backend Log Entry**:
```
2025-11-16 16:01:45,456 INFO: Full Trendlyne cycle completed: 300 total records | {
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

---

### Action 3: Error During Operation

**Immediate Response** (page redirects):
```
❌ Failed to start F&O data population: Connection timeout
```

**Solution**:
```
Click the button again to retry
or check Django logs for detailed error information
```

---

## Color Coding Reference

### Status Indicators

| Status | Icon | Background | Text Color | Meaning |
|--------|------|------------|------------|---------|
| PASS | ✓ | Green (#c6f6d5) | Dark Green (#22543d) | Working properly |
| WARNING | ⚠️ | Orange (#feebc8) | Dark Orange (#744210) | Needs attention soon |
| FAIL | ✗ | Red (#fed7d7) | Dark Red (#742a2a) | Action required |

### Message Color Coding

| Type | Background | Border | Example |
|------|-----------|--------|---------|
| Success | Green (#c6f6d5) | Green (#38a169) | ✅ Operation initiated |
| Error | Red (#fed7d7) | Red (#e53e3e) | ❌ Operation failed |
| Warning | Orange (#feebc8) | Orange (#dd6b20) | ⚠️ Please review |
| Info | Blue (#bee3f8) | Blue (#3182ce) | ℹ️ System information |

---

## Button States

### F&O Data Freshness Button States

| Condition | Button Text | Color | Action |
|-----------|------------|-------|--------|
| Files exist in DB | "Populate Data" | Blue | Parse and update |
| Files missing | "Download & Populate" | Blue | Download and parse |
| Directory missing | "Create & Download" | Blue | Create dir and download |
| No trigger needed | "Populate Data" | Blue | Parse existing files |

### Database Summary Button States

| Condition | Button Text | Color | Action |
|-----------|------------|-------|--------|
| Data exists | "Refresh Data" | Blue | Re-download and refresh |
| No data | "Download Now" | Blue | Download for first time |
| Error state | "Download & Populate" | Blue | Retry download and parse |

---

## Complete Flow Diagram

```
[Admin opens System Test Page]
         ↓
[Sees F&O Data Freshness - 0 days old]
         ↓
[Sees Database Summary - 51 records]
         ↓
[Clicks "Refresh Data" button]
         ↓
[Browser posts to /system/test/trigger-trendlyne-full/]
         ↓
[Backend starts thread: trendlyne_data_manager --full-cycle]
         ↓
[View immediately returns with success message]
         ↓
[Admin waits 60 seconds]
         ↓
[Admin clicks "Refresh Tests" or F5 to reload page]
         ↓
[Page queries database for updated counts]
         ↓
[Display shows:]
  ✓ Database Summary: Total 300 records | Last update: 2025-11-16 16:01:45
  ✓ ContractData: 125 | ContractStockData: 45 | TLStockData: 50 |
    OptionChain: 60 | Event: 15 | NewsArticle: 12 |
    InvestorCall: 8 | KnowledgeBase: 10
```

---

## HTML/CSS Structure

### Status Badge HTML
```html
<div class="test-status pass">✓</div>
<!-- OR -->
<div class="test-status warning">⚠</div>
<!-- OR -->
<div class="test-status fail">✗</div>
```

### Test Item HTML
```html
<div class="test-item">
  <div class="test-status pass">✓</div>
  <div class="test-content">
    <div class="test-name">F&O Data Freshness</div>
    <div class="test-message">
      Latest: contract_data.csv (0 days old) | Updated 5 records at 2025-11-16 15:59:55
    </div>
  </div>
  <div class="test-actions">
    <form method="post" action="/system/test/trigger-fno-data/">
      <button type="submit" class="trigger-btn">Populate Data</button>
    </form>
  </div>
</div>
```

### Button Styling
```css
.trigger-btn {
    background: #4299e1;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
}

.trigger-btn:hover {
    background: #3182ce;
    transform: translateY(-1px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
```

---

## Response Times

| Operation | Duration | Status Update |
|-----------|----------|----------------|
| F&O Parse-Only | ~30 seconds | Records count updates |
| Download Only | ~30-45 seconds | File count updates |
| Full Cycle | ~60-90 seconds | All tables updated |
| Page Load | ~2-3 seconds | Shows current state |
| Button Click | ~1-2 seconds | Returns with message |

---

## Accessibility Features

- ✓ Color + icon indicators (not color-only)
- ✓ Proper heading hierarchy (h1, h2, div.test-name)
- ✓ Form POST for button actions (not just links)
- ✓ Clear status messages
- ✓ Readable font sizes
- ✓ Sufficient color contrast

---

## Mobile Responsiveness

### Desktop (1200px+)
- Full layout with 4-column stats
- Side-by-side test items
- Full button text visible

### Tablet (768px-1199px)
- 2-column stats grid
- Responsive button sizing
- Stacked layout for narrow screens

### Mobile (< 768px)
- 1-column stats grid
- Full-width test items
- Buttons stack vertically

---

**Last Updated**: 2025-11-16
**Status**: ✅ PRODUCTION READY
