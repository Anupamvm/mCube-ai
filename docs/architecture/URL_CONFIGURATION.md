# URL Configuration Guide - mCube Trading System

## Overview
This document describes the URL routing configuration for the mCube Trading System and how to properly handle URLs.

## Fixed Issues

### 1. URL Routing
- **Fixed**: The `/test/` URL was not being resolved
- **Reason**: The test page is located at `/system/test/` not `/test/`
- **Solution**: Added a redirect from `/test/` to `/system/test/` for convenience, and properly organized all URL patterns

### 2. Missing URL Files
Created empty URL configuration files for all apps:
- `apps/accounts/urls.py`
- `apps/strategies/urls.py`
- `apps/positions/urls.py`
- `apps/orders/urls.py`
- `apps/risk/urls.py`
- `apps/alerts/urls.py`
- `apps/llm/urls.py`

### 3. Enhanced Error Handling
Added comprehensive error handling with:
- Custom error handlers (400, 403, 404, 500)
- Beautiful error page template
- Detailed error messages
- Debug mode shows available URLs
- Custom middleware for error logging

### 4. Security & Logging Middleware
Added three custom middleware classes:
- `URLLoggingMiddleware`: Logs all incoming requests (DEBUG mode only)
- `ErrorHandlingMiddleware`: Catches and logs exceptions with full traceback
- `SecurityHeadersMiddleware`: Adds security headers to all responses

## URL Structure

### Main URLs (Root Level)

| URL Pattern | Description | Access |
|-------------|-------------|--------|
| `/` | Home page | Public |
| `/admin/` | Django admin interface | Staff only |
| `/test/` | Redirects to system test page | Redirects to `/system/test/` |
| `/system/test/` | System test page | Admin only |

### App URLs

#### Brokers (`/brokers/`)
- `/brokers/` - Broker dashboard
- `/brokers/login/` - Login page
- `/brokers/logout/` - Logout
- `/brokers/kotakneo/login/` - Kotak Neo login
- `/brokers/kotakneo/data/` - Kotak Neo data
- `/brokers/breeze/login/` - Breeze login
- `/brokers/breeze/data/` - Breeze data
- `/brokers/breeze/nifty-quote/` - Nifty quote
- `/brokers/breeze/option-chain/` - Option chain data
- `/brokers/breeze/historical/` - Historical data
- `/brokers/api/positions/` - API: Get positions
- `/brokers/api/limits/` - API: Get limits

#### Data (`/data/`)
- `/data/trendlyne/login/` - Trendlyne login
- `/data/trendlyne/fetch/` - Fetch Trendlyne data
- `/data/trendlyne/status/` - Trendlyne status

#### Analytics (`/analytics/`)
- `/analytics/learning/` - Learning dashboard
- `/analytics/learning/start/` - Start learning session
- `/analytics/learning/<id>/stop/` - Stop learning session
- `/analytics/learning/<id>/pause/` - Pause learning session
- `/analytics/learning/<id>/resume/` - Resume learning session
- `/analytics/patterns/` - View patterns
- `/analytics/patterns/<id>/` - Pattern details
- `/analytics/suggestions/` - View suggestions
- `/analytics/suggestions/<id>/approve/` - Approve suggestion
- `/analytics/suggestions/<id>/reject/` - Reject suggestion
- `/analytics/api/learning-status/` - API: Learning status
- `/analytics/api/performance-metrics/` - API: Performance metrics
- `/analytics/api/pnl-data/` - API: P&L data

#### Other Apps
- `/accounts/` - Account management (URLs to be added)
- `/positions/` - Position management (URLs to be added)
- `/orders/` - Order management (URLs to be added)
- `/strategies/` - Strategy management (URLs to be added)
- `/risk/` - Risk management (URLs to be added)
- `/alerts/` - Alert management (URLs to be added)
- `/llm/` - LLM integration (URLs to be added)

## Error Handling

### Custom Error Pages

The system now includes a beautiful, responsive error page that shows:
- Error code (400, 403, 404, 500)
- Error title
- Detailed error message
- Helpful actions (Go Home, Go Back, Login if needed)
- In DEBUG mode: List of all available URLs

### Error Handlers

| Error Code | Handler Function | Description |
|------------|-----------------|-------------|
| 400 | `error_400` | Bad Request |
| 403 | `error_403` | Forbidden/Access Denied |
| 404 | `error_404` | Page Not Found |
| 500 | `error_500` | Internal Server Error |

All error handlers are located in `apps/core/views.py`.

## Middleware Features

### 1. URL Logging (DEBUG mode only)
Logs every incoming request with:
- HTTP method
- Request path
- User (authenticated or anonymous)
- Client IP address
- Response status code

Example log output:
```
DEBUG Request: GET /system/test/ | User: admin | IP: 127.0.0.1
DEBUG Response: 302 for /system/test/
```

### 2. Error Handling
- Catches all exceptions during request processing
- Logs full traceback for debugging
- Returns JSON errors for AJAX/API requests
- Returns HTML error pages for regular requests

### 3. Security Headers
Automatically adds security headers to all responses:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (production only)

## Testing URLs

### Using Django's Check Command
```bash
python manage.py check
```

### Listing All URLs
```bash
# Show all available URLs
python -c "
from django.urls import get_resolver
from django.conf import settings
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()
def show_urls(patterns, prefix=''):
    for p in patterns:
        if hasattr(p, 'url_patterns'):
            show_urls(p.url_patterns, prefix + str(p.pattern))
        else:
            print(f'{prefix}{p.pattern}')
show_urls(get_resolver().url_patterns)
"
```

### Testing with cURL
```bash
# Test home page
curl -I http://127.0.0.1:8000/

# Test system test page
curl -I http://127.0.0.1:8000/system/test/

# Test invalid URL (should return 404)
curl -I http://127.0.0.1:8000/invalid/
```

## Best Practices

### 1. Always Use Named URLs
```python
# Good
from django.urls import reverse
url = reverse('core:system_test')

# Bad
url = '/system/test/'
```

### 2. Use app_name in URLs
All app URL files should include `app_name`:
```python
app_name = 'myapp'
```

### 3. Handle Errors Gracefully
- Always provide helpful error messages
- Include navigation options in error pages
- Log errors for debugging

### 4. Test URLs After Changes
After modifying URL configurations:
1. Run `python manage.py check`
2. Test the URLs manually
3. Check logs for any warnings

## Common Issues and Solutions

### Issue: URL not found (404)
**Solution**:
1. Check the URL pattern in the respective app's `urls.py`
2. Ensure the app's URLs are included in the main `mcube_ai/urls.py`
3. Verify the URL namespace if using named URLs

### Issue: Redirect to login page
**Solution**:
- The view requires authentication
- Login at `/brokers/login/` or `/admin/login/`

### Issue: 500 Internal Server Error
**Solution**:
1. Check the error logs in `logs/mcube_ai.log`
2. Enable DEBUG mode to see detailed error page
3. Check the middleware logs for the exception traceback

## Configuration Files

### Main URL Configuration
- Location: `mcube_ai/urls.py`
- Purpose: Root URL patterns and error handlers

### App URL Configurations
- Location: `apps/<app_name>/urls.py`
- Purpose: App-specific URL patterns

### Middleware
- Location: `apps/core/middleware.py`
- Purpose: Request/response processing and error handling

### Error Templates
- Location: `templates/core/error.html`
- Purpose: Generic error page for all HTTP errors

## Environment Variables

The following settings affect URL behavior:

| Setting | Description | Default |
|---------|-------------|---------|
| `DEBUG` | Enable debug mode with detailed errors | `True` |
| `ALLOWED_HOSTS` | List of allowed host/domain names | `[]` |
| `LOGIN_URL` | Default login URL | `/admin/login/` |

## Security Considerations

1. **Never commit credentials**: URL files should never contain API keys or passwords
2. **Use HTTPS in production**: Set `SECURE_SSL_REDIRECT = True`
3. **Disable DEBUG in production**: Set `DEBUG = False`
4. **Set ALLOWED_HOSTS**: Add your domain to `ALLOWED_HOSTS`
5. **Enable CSRF protection**: Already enabled by default

## Summary

All URLs are now properly configured with:
- ✅ Fixed URL routing issues
- ✅ Created missing URL configuration files
- ✅ Enhanced error handling with custom error pages
- ✅ Added comprehensive logging middleware
- ✅ Implemented security headers
- ✅ Proper error messages when something goes wrong

The test page is accessible at:
- **http://127.0.0.1:8000/test/** (redirects to system/test/)
- **http://127.0.0.1:8000/system/test/** (direct access)

Both URLs require admin login. The `/test/` URL automatically redirects to `/system/test/` for convenience.
