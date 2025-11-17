# Indian Number Formatting Implementation

## Overview
This document describes the implementation of Indian numbering system (lakhs and crores) across the entire mCube Trading System.

## Indian Numbering Format
- **Standard**: 77,200,970 → **Indian**: 7,72,00,970
- First comma after 3 digits from right
- Subsequent commas after every 2 digits
- Currency symbol: ₹ (Indian Rupee)

## Implementation Components

### 1. Core Formatting Functions
**File**: `apps/core/utils/formatting.py`

#### Functions:
- `format_indian_currency(amount)` - Formats amount with ₹ symbol and Indian commas
  ```python
  format_indian_currency(77200970) → "₹7,72,00,970.00"
  ```

- `format_percentage(value, decimal_places=2)` - Formats percentages
  ```python
  format_percentage(0.05) → "5.00%"
  ```

- `format_quantity(quantity)` - Formats quantities with commas
  ```python
  format_quantity(50000) → "50,000"
  ```

- `shorten_large_number(number)` - Compact notation with K/L/Cr
  ```python
  shorten_large_number(77200970) → "7.72Cr"
  ```

**Key Change**: Updated currency symbol from "Rs." to "₹"

### 2. Template Filters
**File**: `apps/core/templatetags/indian_formatting.py`

#### Custom Template Filters:
- `{{ amount|indian_currency }}` - Formats with ₹ symbol
- `{{ number|indian_number }}` - Formats without symbol
- `{{ number|indian_compact }}` - Compact notation (K/L/Cr)

#### Usage in Templates:
```django
{% load indian_formatting %}

<p>Margin: {{ margin_available|indian_currency }}</p>
<!-- Output: Margin: ₹7,72,00,970.00 -->

<p>Investment: {{ total_investment|indian_compact }}</p>
<!-- Output: Investment: 7.72Cr -->
```

### 3. Views and Backend
**File**: `apps/core/views.py`

#### Updated Functions:
1. **home_page()** - Formats total_pnl before passing to template
2. **verify_kotak_login()** - Formats margin and investment in success messages
3. **verify_breeze_login()** - Formats margin and investment in success messages
4. **test_accounts()** - Formats all monetary values in test output
5. **test_positions()** - Formats P&L calculations

#### Import Statement:
```python
from apps.core.utils import format_indian_number, format_currency
```

### 4. Broker Interfaces
**File**: `apps/brokers/interfaces.py`

#### Updated Dataclasses:
- `MarginData.__str__()` - Uses `format_currency()` for all monetary fields
- `Position.__str__()` - Uses `format_currency()` for prices and P&L

### 5. Templates Updated

#### Broker Templates:
1. **apps/brokers/templates/brokers/dashboard.html**
   - Margin Available/Used for both Kotak Neo and Breeze
   - Total Bank Balance, Allocated F&O, Net Balance, Collateral Value

2. **apps/brokers/templates/brokers/broker_data.html**
   - All limit/fund fields
   - Position prices (Avg Price, LTP)
   - Position P&L (Realized and Unrealized)

#### Core Templates:
3. **apps/core/templates/core/home.html**
   - Total P&L in dashboard stats

## Formatting Applied To

### ✅ Completed Areas:
1. **Backend Views** - All test functions and verification views
2. **Broker Login Messages** - Success messages with margin/investment
3. **Templates** - Dashboard, broker data, home page
4. **Dataclass Representations** - MarginData, Position __str__ methods
5. **Home Page Dashboard** - P&L display

### 📊 Monetary Values Now Formatted:
- Available Margin
- Used Margin
- Total Investment
- Stock Holdings Investment
- F&O Position Investment
- Average Price
- Last Traded Price (LTP)
- Realized P&L
- Unrealized P&L
- Total P&L
- Available Capital
- Total Bank Balance
- Allocated F&O
- Net Balance
- Collateral Value

## Usage Examples

### In Python Code:
```python
from apps.core.utils import format_currency, format_indian_number

# Format currency
margin = 77200970.50
formatted = format_currency(margin)  # "₹7,72,00,970.50"

# Format without symbol
investment = 1234567
formatted = format_indian_number(investment, decimals=2)  # "12,34,567.00"
```

### In Django Templates:
```django
{% load indian_formatting %}

<!-- Currency with symbol -->
<p>{{ margin_available|indian_currency }}</p>

<!-- Number without symbol -->
<p>{{ quantity|indian_number }}</p>

<!-- Compact notation -->
<p>{{ large_value|indian_compact }}</p>
```

### In Dataclasses:
```python
from apps.core.utils import format_currency

@dataclass
class MarginData:
    available_margin: float

    def __str__(self):
        return f"Available: {format_currency(self.available_margin)}"
```

## Files Modified

1. `apps/core/utils/formatting.py` - Updated currency symbol
2. `apps/core/views.py` - Added formatting to all monetary displays
3. `apps/brokers/interfaces.py` - Updated __str__ methods
4. `apps/core/templatetags/__init__.py` - Created
5. `apps/core/templatetags/indian_formatting.py` - Created custom filters
6. `apps/brokers/templates/brokers/dashboard.html` - Applied filters
7. `apps/brokers/templates/brokers/broker_data.html` - Applied filters
8. `apps/core/templates/core/home.html` - Removed redundant formatting

## Testing

### Manual Testing Steps:
1. Login to Kotak Neo - Verify margin displays as ₹7,72,00,970.00
2. Login to Breeze - Verify margin displays with Indian formatting
3. View broker dashboard - Check all monetary values
4. Check home page - Verify P&L displays correctly
5. Run system tests - Confirm all test outputs use Indian formatting

### Expected Output Examples:
```
✅ Kotak Neo login successful!
Available Margin: ₹7,26,11,019.54,
F&O Positions: 0,
Stock Holdings: 5,
Total Investment: ₹45,67,890.00

✅ Breeze login successful!
Available Margin: ₹1,52,10,863.91,
F&O Positions: 1,
Stock Holdings: 0,
Total Investment: ₹7,72,00,970.00
```

## Benefits

1. **Consistency** - All monetary values use same format across system
2. **Readability** - Indian users can quickly read lakhs and crores
3. **Professional** - Proper ₹ symbol instead of "Rs."
4. **Reusable** - Template filters can be used in any template
5. **Maintainable** - Centralized formatting functions

## Future Enhancements

1. Add formatting to API responses (if REST API is implemented)
2. Add formatting to report exports (PDF/Excel)
3. Add formatting to email notifications
4. Add formatting to Telegram bot messages
5. Add admin interface custom display formatting
6. Consider adding user preference for formatting style

## Notes

- The formatting is applied at the display layer (views and templates)
- Database values remain as numeric types (float/Decimal)
- All calculations happen on raw numeric values
- Formatting only applied when displaying to user
- Template filters handle None/null values gracefully
- Backward compatible - existing code continues to work
