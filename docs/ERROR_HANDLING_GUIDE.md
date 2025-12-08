# Error Handling Guide

## Overview

This guide shows how to use the centralized error handling system to replace generic `except Exception as e` patterns with specific, actionable error handling.

---

## 📦 **Available Tools**

### **Custom Exceptions**

```python
from apps.core.utils.error_handlers import (
    BrokerAPIException,          # Broker API failures
    DataValidationException,      # Invalid input data
    AuthenticationException,      # Auth failures
    ConfigurationException        # Missing/invalid config
)
```

### **Decorators**

```python
from apps.core.utils.error_handlers import (
    handle_api_errors,           # For Django API views
    handle_broker_errors,        # For broker API calls
    retry_on_failure,            # Retry failed operations
    safe_execute                 # Safe execution with fallback
)
```

---

## 🔄 **Migration Patterns**

### **Pattern 1: Django API Views**

#### ❌ **BEFORE** (Generic Exception Handling)
```python
@login_required
@require_POST
def my_view(request):
    try:
        broker = request.POST.get('broker')
        quantity = int(request.POST.get('quantity'))

        # ... business logic ...

        return JsonResponse({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"Error: {e}")
        return JsonResponse({'error': str(e)}, status=500)
```

#### ✅ **AFTER** (Specific Exception Handling)
```python
from apps.core.utils.error_handlers import (
    handle_api_errors,
    DataValidationException,
    BrokerAPIException
)

@login_required
@require_POST
@handle_api_errors  # <-- Add this decorator
def my_view(request):
    # Validation with specific exceptions
    broker = request.POST.get('broker')
    if not broker:
        raise DataValidationException(
            "Missing broker parameter",
            field='broker',
            reason='Required field not provided'
        )

    try:
        quantity = int(request.POST.get('quantity'))
    except (ValueError, TypeError):
        raise DataValidationException(
            "Invalid quantity",
            field='quantity',
            value=request.POST.get('quantity'),
            reason='Must be a valid integer'
        )

    # Business logic - errors caught by decorator
    result = perform_operation(broker, quantity)
    return JsonResponse({'success': True, 'data': result})
```

**Benefits:**
- ✅ Specific error types for different failures
- ✅ Consistent error response format
- ✅ Proper HTTP status codes (400 for validation, 500 for server errors)
- ✅ Better logging with context
- ✅ Cleaner code (no try/except clutter)

---

### **Pattern 2: Broker API Calls**

#### ❌ **BEFORE**
```python
def place_order(symbol, quantity):
    try:
        breeze = get_breeze_client()
        response = breeze.place_order(
            stock_code=symbol,
            quantity=quantity
        )
        return response
    except Exception as e:
        logger.error(f"Order failed: {e}")
        return {'error': str(e)}
```

#### ✅ **AFTER**
```python
from apps.core.utils.error_handlers import (
    handle_broker_errors,
    BrokerAPIException
)

@handle_broker_errors(broker_name='breeze')
def place_order(symbol, quantity):
    breeze = get_breeze_client()

    response = breeze.place_order(
        stock_code=symbol,
        quantity=quantity
    )

    # Check broker response
    if response.get('Status') != 200:
        raise BrokerAPIException(
            f"Order placement failed: {response.get('Error')}",
            broker='breeze',
            operation='place_order',
            original_error=response
        )

    return response
```

---

### **Pattern 3: Retry Transient Failures**

Use for network errors, rate limits, temporary API issues:

```python
from apps.core.utils.error_handlers import retry_on_failure

@retry_on_failure(
    max_attempts=3,
    delay_seconds=2.0,
    backoff_multiplier=2.0
)
def fetch_option_chain():
    """
    Will retry up to 3 times with increasing delays:
    - Attempt 1: immediate
    - Attempt 2: wait 2.0s
    - Attempt 3: wait 4.0s (2.0 * 2.0)
    """
    breeze = get_breeze_client()
    return breeze.get_option_chain_quotes(...)
```

---

### **Pattern 4: Safe Execution (Optional Operations)**

For operations where failure shouldn't crash the app:

```python
from apps.core.utils.error_handlers import safe_execute

# Old way - verbose try/except
try:
    vix = get_india_vix()
except:
    vix = Decimal('15.0')  # Default

# New way - clean and concise
vix = safe_execute(
    lambda: get_india_vix(),
    default_return=Decimal('15.0')
)
```

---

### **Pattern 5: Log Execution Time**

```python
from apps.core.utils.error_handlers import LogExecutionTime

def fetch_large_dataset():
    with LogExecutionTime("Fetch option chain for all expiries"):
        data = fetch_and_save_nifty_option_chain_all_expiries()
    # Automatically logs: "Fetch option chain for all expiries completed in 3.45s"
    return data
```

---

## 📋 **Complete Example: Before & After**

### ❌ **BEFORE** (Generic Error Handling)

```python
@login_required
@require_POST
def place_futures_order_view(request):
    try:
        # Get parameters
        broker = request.POST.get('broker')
        symbol = request.POST.get('symbol')
        quantity = request.POST.get('quantity')

        # Get broker connection
        broker_conn = BrokerConnection.objects.filter(
            user=request.user,
            broker_name=broker,
            is_active=True
        ).first()

        if not broker_conn:
            return JsonResponse({'error': f'No active {broker} connection'}, status=400)

        # Place order
        if broker == 'breeze':
            breeze = get_breeze_client()
            response = breeze.place_order(
                stock_code=symbol,
                quantity=quantity
            )

        return JsonResponse({'success': True, 'order_id': response.get('order_id')})

    except Exception as e:
        logger.error(f"Error placing order: {e}")
        return JsonResponse({'error': str(e)}, status=500)
```

### ✅ **AFTER** (Specific Error Handling)

```python
from apps.core.utils.error_handlers import (
    handle_api_errors,
    DataValidationException,
    BrokerAPIException,
    retry_on_failure
)

@login_required
@require_POST
@handle_api_errors
def place_futures_order_view(request):
    # Validate parameters
    broker = request.POST.get('broker')
    if not broker:
        raise DataValidationException(
            "Broker is required",
            field='broker',
            reason='Missing required parameter'
        )

    symbol = request.POST.get('symbol')
    if not symbol:
        raise DataValidationException(
            "Symbol is required",
            field='symbol',
            reason='Missing required parameter'
        )

    try:
        quantity = int(request.POST.get('quantity', 0))
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
    except (ValueError, TypeError) as e:
        raise DataValidationException(
            "Invalid quantity",
            field='quantity',
            value=request.POST.get('quantity'),
            reason=str(e)
        )

    # Get broker connection
    broker_conn = BrokerConnection.objects.filter(
        user=request.user,
        broker_name=broker,
        is_active=True
    ).first()

    if not broker_conn:
        raise DataValidationException(
            f"No active {broker} connection found for user",
            field='broker',
            reason='Broker not connected'
        )

    # Place order with retry
    order_result = _place_order_with_retry(broker, symbol, quantity)

    return JsonResponse({
        'success': True,
        'order_id': order_result.get('order_id'),
        'message': 'Order placed successfully'
    })


@retry_on_failure(max_attempts=3, delay_seconds=1.0)
@handle_broker_errors(broker_name='breeze')
def _place_order_with_retry(broker, symbol, quantity):
    """Place order with automatic retry on failure"""
    if broker == 'breeze':
        breeze = get_breeze_client()
        response = breeze.place_order(
            stock_code=symbol,
            quantity=quantity
        )

        if response.get('Status') != 200:
            raise BrokerAPIException(
                f"Order placement failed: {response.get('Error')}",
                broker='breeze',
                operation='place_order',
                original_error=response
            )

        return response.get('Success', {})
```

---

## 🎯 **Error Response Format**

All errors now return consistent JSON format:

### **Validation Error (400)**
```json
{
  "error": "Invalid quantity",
  "error_type": "DataValidationException",
  "success": false,
  "field": "quantity",
  "reason": "Must be a valid integer",
  "invalid_value": "abc"
}
```

### **Broker API Error (502)**
```json
{
  "error": "Order placement failed: Insufficient margin",
  "error_type": "BrokerAPIException",
  "success": false,
  "broker": "breeze",
  "operation": "place_order",
  "original_error": "..."
}
```

### **Authentication Error (401)**
```json
{
  "error": "Breeze session token expired",
  "error_type": "AuthenticationException",
  "success": false
}
```

---

## 📝 **Best Practices**

1. **Use specific exceptions** instead of generic `Exception`
2. **Add context** to exceptions (field names, broker names, etc.)
3. **Use decorators** for consistent error handling
4. **Retry transient failures** (network, rate limits)
5. **Log with context** (operation name, user, parameters)
6. **Return proper HTTP status codes**:
   - 400: Bad Request (validation errors)
   - 401: Unauthorized (auth failures)
   - 500: Internal Server Error (unexpected errors)
   - 502: Bad Gateway (external service failures)

---

## 🔧 **Migration Checklist**

- [ ] Replace `except Exception as e` with `@handle_api_errors` decorator
- [ ] Use specific exception classes for different error types
- [ ] Add validation with `DataValidationException`
- [ ] Wrap broker calls with `@handle_broker_errors`
- [ ] Add retry logic for transient failures
- [ ] Test error responses match expected format
- [ ] Update frontend to handle new error format

---

**Next Steps:** Apply these patterns throughout the codebase to eliminate generic exception handlers!
