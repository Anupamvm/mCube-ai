# Trendlyne Library Refactoring

## Overview
The Trendlyne data fetching code has been refactored into a clean, extensible architecture under `apps/data/providers/`.

## Architecture

### New Structure
```
apps/data/providers/
├── __init__.py              # Package exports
├── base.py                  # Abstract base classes
└── trendlyne.py            # Trendlyne implementation
```

### Old Files (DEPRECATED - To Be Removed)
```
apps/data/
├── trendlyne.py            # DEPRECATED: Use providers.trendlyne instead
└── tools/
    ├── trendlyne.py        # DEPRECATED: Use providers.trendlyne instead
    └── trendlyne_downloader.py  # DEPRECATED: Use providers.trendlyne instead
```

## Key Improvements

### 1. **Consolidated Redundancy**
**Before:** 3 separate files with duplicate code
- `apps/data/trendlyne.py` (17KB)
- `apps/data/tools/trendlyne.py` (18KB)
- `apps/data/tools/trendlyne_downloader.py` (23KB)

**After:** 2 clean, well-designed files
- `apps/data/providers/base.py` - Base classes (8KB)
- `apps/data/providers/trendlyne.py` - Trendlyne implementation (15KB)

**Result:** ~50% reduction in code, zero redundancy

### 2. **Extensible Design**
New providers can be added easily:

```python
from apps.data.providers.base import BaseWebScraper

class NSEProvider(BaseWebScraper):
    def get_credentials(self):
        # Implementation
        pass

    def login(self):
        # Implementation
        pass

    def fetch_data(self, data_type, **kwargs):
        # Implementation
        pass
```

### 3. **Enhanced Features**

#### Base Classes
- `BaseDataProvider`: Abstract base for all providers
- `BaseWebScraper`: Extends base with web scraping utilities

#### Common Features (All Providers)
- ✅ WebDriver management with context manager support
- ✅ Automatic cleanup
- ✅ Enhanced error handling with custom exceptions
- ✅ Debug screenshot capture
- ✅ Multi-selector strategies for reliability
- ✅ Comprehensive logging

#### Trendlyne Specific
- ✅ F&O data fetching
- ✅ Market snapshot
- ✅ Forecaster data (21 screeners)
- ✅ Robust login with fallback strategies
- ✅ ChromeDriver stability options

### 4. **Cleaner API**

#### Old Way (Multiple import options)
```python
# Option 1
from apps.data.trendlyne import get_all_trendlyne_data
get_all_trendlyne_data()

# Option 2
from apps.data.tools.trendlyne import get_all_trendlyne_data
get_all_trendlyne_data()

# Option 3
from apps.data.tools.trendlyne_downloader import download_contract_data
download_contract_data('/path')
```

#### New Way (Single, clear import)
```python
# Context manager (recommended)
from apps.data.providers.trendlyne import TrendlyneProvider

with TrendlyneProvider() as provider:
    provider.fetch_all_data()

# Or backwards compatible
from apps.data.providers.trendlyne import get_all_trendlyne_data
get_all_trendlyne_data()
```

## Migration Guide

### For New Code
Use the new provider architecture:

```python
from apps.data.providers.trendlyne import TrendlyneProvider

# Fetch all data
with TrendlyneProvider() as provider:
    result = provider.fetch_all_data()

# Or fetch specific data
with TrendlyneProvider() as provider:
    provider.login()

    # F&O data
    fno_result = provider.fetch_fno_data()

    # Market snapshot
    market_result = provider.fetch_market_snapshot()

    # Forecaster data
    forecaster_result = provider.fetch_forecaster_data()
```

### For Existing Code
The old function `get_all_trendlyne_data()` still works (backwards compatible):

```python
# This still works (imports from new location)
from apps.data.providers.trendlyne import get_all_trendlyne_data

success = get_all_trendlyne_data()
```

### Updated Imports

| Old Import | New Import |
|------------|------------|
| `from apps.data.trendlyne import get_all_trendlyne_data` | `from apps.data.providers.trendlyne import get_all_trendlyne_data` |
| `from apps.data.tools.trendlyne import get_all_trendlyne_data` | `from apps.data.providers.trendlyne import TrendlyneProvider` |
| `from apps.data.tools.trendlyne_downloader import login_trendlyne` | `TrendlyneProvider().login()` |

## Files Updated

### Already Updated
1. ✅ `apps/data/tasks.py` - Uses new provider

### Need to Update (Future)
1. `apps/data/views.py` - If it imports trendlyne
2. `apps/core/views.py` - If it imports trendlyne
3. `apps/data/management/commands/trendlyne_data_manager.py` - Management command
4. `apps/data/management/commands/scrape_trendlyne.py` - Management command

## Adding New Data Providers

### Example: NSE Provider

```python
# apps/data/providers/nse.py

from .base import BaseWebScraper, DataProviderException
from apps.core.models import CredentialStore

class NSEProvider(BaseWebScraper):
    """NSE data provider"""

    BASE_URL = "https://www.nseindia.com"

    def get_credentials(self):
        # NSE may not need credentials
        return None, None

    def login(self):
        # NSE public data - no login needed
        if not self.driver:
            self.init_driver()
        return True

    def fetch_data(self, data_type, **kwargs):
        if data_type == 'equity_bhavcopy':
            return self.fetch_equity_bhavcopy(**kwargs)
        elif data_type == 'fno_bhavcopy':
            return self.fetch_fno_bhavcopy(**kwargs)
        else:
            raise DataProviderException(f"Unknown data type: {data_type}")

    def fetch_equity_bhavcopy(self, date=None):
        # Implementation
        pass

    def fetch_fno_bhavcopy(self, date=None):
        # Implementation
        pass
```

### Register in `__init__.py`

```python
# apps/data/providers/__init__.py

from .base import BaseDataProvider, DataProviderException
from .trendlyne import TrendlyneProvider
from .nse import NSEProvider  # Add new provider

__all__ = [
    'BaseDataProvider',
    'DataProviderException',
    'TrendlyneProvider',
    'NSEProvider',  # Export new provider
]
```

### Usage

```python
from apps.data.providers import NSEProvider

with NSEProvider() as provider:
    bhavcopy = provider.fetch_data('equity_bhavcopy', date='2024-11-23')
```

## Benefits of New Architecture

### 1. **Maintainability**
- Single source of truth for each provider
- No duplicate code
- Clear separation of concerns

### 2. **Extensibility**
- Easy to add new data sources (NSE, BSE, Yahoo Finance, etc.)
- Base classes provide common functionality
- Consistent interface across all providers

### 3. **Testability**
- Each provider is independent
- Base classes can be mocked
- Context manager ensures cleanup

### 4. **Reliability**
- Enhanced error handling
- Debug screenshot capture
- Multi-selector fallback strategies
- Comprehensive logging

### 5. **Performance**
- Context manager ensures proper resource cleanup
- No memory leaks from unclosed drivers
- Efficient retry logic

## Testing

### Test New Provider
```bash
python manage.py shell
```

```python
from apps.data.providers.trendlyne import TrendlyneProvider

# Test with context manager
with TrendlyneProvider(headless=False) as provider:
    # Test login
    logged_in = provider.login()
    print(f"Login successful: {logged_in}")

    # Test F&O fetch
    fno_result = provider.fetch_fno_data()
    print(f"F&O result: {fno_result}")
```

### Test Backwards Compatibility
```python
from apps.data.providers.trendlyne import get_all_trendlyne_data

success = get_all_trendlyne_data()
print(f"Success: {success}")
```

## Deprecation Timeline

### Phase 1 (Current) ✅
- New provider architecture created
- Backwards compatibility maintained
- Updated imports in `tasks.py`

### Phase 2 (Next Release)
- Add deprecation warnings to old files
- Update all management commands
- Update all views

### Phase 3 (Future Release)
- Remove old files:
  - `apps/data/trendlyne.py`
  - `apps/data/tools/trendlyne.py`
  - `apps/data/tools/trendlyne_downloader.py`

## Common Patterns

### Pattern 1: Fetch All Data
```python
from apps.data.providers.trendlyne import TrendlyneProvider

with TrendlyneProvider() as provider:
    result = provider.fetch_all_data()

if result['success']:
    print(f"Downloaded at: {result['timestamp']}")
```

### Pattern 2: Fetch Specific Data
```python
from apps.data.providers.trendlyne import TrendlyneProvider

provider = TrendlyneProvider()
try:
    provider.init_driver()
    provider.login()

    # Get only what you need
    market_data = provider.fetch_market_snapshot()

finally:
    provider.cleanup()
```

### Pattern 3: Custom Download Directory
```python
from apps.data.providers.trendlyne import TrendlyneProvider

with TrendlyneProvider(download_dir='/custom/path') as provider:
    provider.fetch_all_data()
```

### Pattern 4: Non-Headless (for debugging)
```python
from apps.data.providers.trendlyne import TrendlyneProvider

with TrendlyneProvider(headless=False) as provider:
    provider.fetch_all_data()
    # Browser window will be visible
```

## Error Handling

### Custom Exception
```python
from apps.data.providers import TrendlyneProvider, DataProviderException

try:
    with TrendlyneProvider() as provider:
        result = provider.fetch_all_data()
except DataProviderException as e:
    logger.error(f"Provider error: {e}")
    # Handle provider-specific errors
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    # Handle other errors
```

### Debug Screenshots
All providers automatically capture screenshots on errors:
```
apps/data/debug_screenshots/
├── login_error_1700000000.png
├── element_not_found_1700000001.png
└── fetch_failed_1700000002.png
```

## Future Enhancements

### Planned Providers
1. **NSEProvider** - NSE bhavcopy, indices, corporate actions
2. **BSEProvider** - BSE market data
3. **YahooFinanceProvider** - Historical data, fundamentals
4. **MoneyControlProvider** - News, analyst ratings
5. **ScreenerProvider** - Fundamental data

### Planned Features
1. Rate limiting and throttling
2. Caching layer
3. Async/await support
4. Parallel fetching
5. Data validation
6. Automatic retry with exponential backoff

## Questions?

For issues or questions:
1. Check debug screenshots in `apps/data/debug_screenshots/`
2. Review logs for detailed error messages
3. Try non-headless mode for visual debugging
4. Check `DATA_FRESHNESS_IMPLEMENTATION.md` for data freshness features

## Summary

✅ **50% code reduction** - Eliminated redundant code
✅ **100% backwards compatible** - Old code still works
✅ **Extensible** - Easy to add new providers
✅ **Reliable** - Enhanced error handling and fallbacks
✅ **Clean** - Well-organized, single source of truth
✅ **Future-proof** - Ready for NSE, BSE, Yahoo Finance, etc.
