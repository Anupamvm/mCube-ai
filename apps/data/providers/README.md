# Data Providers Library

Clean, extensible architecture for fetching data from multiple sources.

## Quick Start

### Trendlyne Data

```python
from apps.data.providers.trendlyne import TrendlyneProvider

# Fetch all data
with TrendlyneProvider() as provider:
    result = provider.fetch_all_data()

# Fetch specific data
with TrendlyneProvider() as provider:
    provider.login()
    fno_data = provider.fetch_fno_data()
    market_data = provider.fetch_market_snapshot()
    forecaster_data = provider.fetch_forecaster_data()
```

## Available Providers

### Current
- **TrendlyneProvider** - F&O contracts, market snapshot, forecaster data

### Planned
- **NSEProvider** - Equity/F&O bhavcopy, indices, corporate actions
- **BSEProvider** - Market data, corporate actions
- **YahooFinanceProvider** - Historical prices, fundamentals
- **MoneyControlProvider** - News, analyst ratings
- **ScreenerProvider** - Fundamental data

## Adding a New Provider

1. Create new file in `apps/data/providers/your_provider.py`
2. Extend `BaseWebScraper` or `BaseDataProvider`
3. Implement required methods:
   - `get_credentials()`
   - `login()`
   - `fetch_data(data_type, **kwargs)`
4. Export in `__init__.py`

### Example

```python
# apps/data/providers/nse.py

from .base import BaseWebScraper, DataProviderException

class NSEProvider(BaseWebScraper):
    BASE_URL = "https://www.nseindia.com"

    def get_credentials(self):
        return None, None  # Public data

    def login(self):
        if not self.driver:
            self.init_driver()
        return True

    def fetch_data(self, data_type, **kwargs):
        if data_type == 'equity_bhavcopy':
            return self.fetch_equity_bhavcopy(**kwargs)
        elif data_type == 'fno_bhavcopy':
            return self.fetch_fno_bhavcopy(**kwargs)
        else:
            raise DataProviderException(f"Unknown type: {data_type}")

    def fetch_equity_bhavcopy(self, date=None):
        # Implementation
        pass
```

## Base Classes

### `BaseDataProvider`
Abstract base with common functionality:
- WebDriver management
- Credential handling
- Error handling
- Logging
- Context manager support

### `BaseWebScraper`
Extends `BaseDataProvider` with:
- `wait_for_element()` - Wait for elements
- `try_multiple_selectors()` - Fallback strategies
- `save_debug_screenshot()` - Error debugging

## API Reference

### TrendlyneProvider

#### Methods

**`fetch_all_data(download_dir=None)`**
Fetch all Trendlyne data types.

**`fetch_fno_data(download_dir=None)`**
Download F&O contracts data.

**`fetch_market_snapshot(download_dir=None)`**
Download market snapshot data.

**`fetch_forecaster_data(output_dir=None)`**
Scrape forecaster data (21 screeners).

**`login()`**
Login to Trendlyne.

#### Parameters

- `headless` (bool): Run browser in headless mode (default: True)
- `download_dir` (str): Custom download directory

## Error Handling

```python
from apps.data.providers import TrendlyneProvider, DataProviderException

try:
    with TrendlyneProvider() as provider:
        result = provider.fetch_all_data()
except DataProviderException as e:
    # Provider-specific errors
    logger.error(f"Provider error: {e}")
except Exception as e:
    # Other errors
    logger.error(f"Unexpected error: {e}")
```

Debug screenshots saved to: `apps/data/debug_screenshots/`

## Documentation

- **Full migration guide:** `../TRENDLYNE_REFACTORING.md`
- **Cleanup summary:** `../../../TRENDLYNE_CLEANUP_SUMMARY.md`
- **Data freshness:** `../../../DATA_FRESHNESS_IMPLEMENTATION.md`

## Examples

### Custom Download Directory
```python
with TrendlyneProvider(download_dir='/custom/path') as provider:
    provider.fetch_all_data()
```

### Non-Headless Mode (Debugging)
```python
with TrendlyneProvider(headless=False) as provider:
    provider.fetch_all_data()  # Browser window visible
```

### Selective Fetching
```python
provider = TrendlyneProvider()
try:
    provider.init_driver()
    provider.login()

    # Get only what you need
    fno_data = provider.fetch_fno_data()
    print(f"Downloaded: {fno_data['filename']}")

finally:
    provider.cleanup()
```

## Testing

```bash
python manage.py shell
```

```python
from apps.data.providers import TrendlyneProvider

# Test provider creation
provider = TrendlyneProvider()
print(f"Provider: {provider}")
print(f"Download dir: {provider.download_dir}")

# Test context manager
with TrendlyneProvider() as provider:
    print("Context manager works!")
```

## Backwards Compatibility

Old imports still work:

```python
# Still works (redirects to new location)
from apps.data.trendlyne import get_all_trendlyne_data
success = get_all_trendlyne_data()
```

## License

Internal use only - mCube Trading System
