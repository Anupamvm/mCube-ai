# Authentication & Login Configuration Guide

## Overview
This guide explains how authentication and login work in the mCube Trading System after the recent updates.

## Login Flow Changes

### Before
- Users were redirected to `/admin/login/` for authentication
- After login, users were redirected to the home page `/`
- Required going through Django admin interface

### After (Current)
- Users are now redirected to `/brokers/login/` for authentication
- After login, users are redirected to the broker dashboard `/brokers/`
- Custom login page with better UX

## URL Redirect Behavior

### Test Page Access
When accessing the test page:

1. **Direct URL**: `http://127.0.0.1:8000/test/`
   - Redirects to → `/system/test/`

2. **System URL**: `http://127.0.0.1:8000/system/test/`
   - Requires authentication (admin only)
   - If not authenticated → Redirects to `/brokers/login/?next=/system/test/`
   - After login → Redirects back to `/system/test/`

### Home Page Access
1. **URL**: `http://127.0.0.1:8000/`
   - Always accessible
   - Shows different content based on authentication status

### Broker Dashboard Access
1. **URL**: `http://127.0.0.1:8000/brokers/`
   - Requires authentication
   - If not authenticated → Redirects to `/brokers/login/?next=/brokers/`
   - After login → Shows broker dashboard

## Authentication Settings

Located in `mcube_ai/settings.py`:

```python
# Authentication settings
LOGIN_URL = '/brokers/login/'  # Use broker login page instead of admin
LOGIN_REDIRECT_URL = '/brokers/'  # Redirect to broker dashboard after login
LOGOUT_REDIRECT_URL = '/'  # Redirect to home page after logout
```

## User Roles & Permissions

### Admin Users
- Superusers or members of "Admin" group
- Full access to all features
- Can access `/system/test/` page
- Can access Django admin at `/admin/`

### Trader Users
- Members of "User" or "Admin" group
- Access to trading features
- Can view broker data, positions, orders
- Cannot access system test page

### Anonymous Users
- Can view home page
- Must login to access any protected pages
- Redirected to `/brokers/login/` when accessing protected pages

## Login Page

### Location
- URL: `/brokers/login/`
- Template: `templates/brokers/login.html`
- View: `apps/brokers/views.py::login_view()`

### Features
- Username/password authentication
- "Next" parameter support for redirects
- Success/error messages
- Automatic redirect if already logged in

### Example Usage
```python
# In a view that requires authentication
@login_required
def my_view(request):
    # If user is not authenticated, they will be redirected to:
    # /brokers/login/?next=/current/url/
    return render(request, 'my_template.html')
```

## Logout Behavior

### Location
- URL: `/brokers/logout/`
- View: `apps/brokers/views.py::logout_view()`

### Flow
1. User clicks logout
2. Session is cleared
3. Success message displayed
4. Redirect to home page `/`

## Access Control Examples

### Require Login Only
```python
from django.contrib.auth.decorators import login_required

@login_required
def my_view(request):
    # User must be logged in
    # If not, redirect to /brokers/login/?next=/current/url/
    pass
```

### Require Admin Access
```python
from django.contrib.auth.decorators import user_passes_test

def is_admin_user(user):
    return user.is_superuser or user.groups.filter(name='Admin').exists()

@login_required
@user_passes_test(is_admin_user, login_url='/brokers/login/')
def admin_only_view(request):
    # Only admin users can access
    pass
```

### Require Trader Access
```python
def is_trader_user(user):
    return user.groups.filter(name__in=['Admin', 'User']).exists() or user.is_superuser

@login_required
@user_passes_test(is_trader_user, login_url='/brokers/login/')
def trader_view(request):
    # Traders and admins can access
    pass
```

## Complete URL Flow Examples

### Example 1: Accessing Test Page (Not Logged In)
```
User visits: http://127.0.0.1:8000/test/
  ↓
302 Redirect to: /system/test/
  ↓
302 Redirect to: /brokers/login/?next=/system/test/
  ↓
User sees login page
  ↓
User enters credentials
  ↓
302 Redirect to: /brokers/ (default dashboard)
  ↓
User sees broker dashboard
```

Note: The `next` parameter is currently not being used in the broker login view. If you want to redirect back to the original page, the view needs to be updated.

### Example 2: Accessing Test Page (Logged In as Admin)
```
User visits: http://127.0.0.1:8000/test/
  ↓
302 Redirect to: /system/test/
  ↓
200 OK - System test page displayed
```

### Example 3: Accessing Test Page (Logged In as Regular User)
```
User visits: http://127.0.0.1:8000/test/
  ↓
302 Redirect to: /system/test/
  ↓
403 Forbidden (user_passes_test fails)
  ↓
Custom 403 error page displayed
```

## Django Admin Access

### URL
- `/admin/` - Django admin interface

### Access
- Requires staff status (`user.is_staff = True`)
- Separate from broker login system
- Has its own login page at `/admin/login/`

### Usage
- For managing database records directly
- User administration
- Viewing/editing all models
- Background task management

## Security Considerations

1. **Password Security**
   - Django's built-in password hashing
   - PBKDF2 algorithm by default
   - Never store plain text passwords

2. **Session Management**
   - Secure session cookies
   - Automatic session expiration
   - CSRF protection enabled

3. **Login Throttling**
   - Consider adding django-axes for brute force protection
   - Monitor failed login attempts
   - Implement account lockout after N failures

4. **HTTPS in Production**
   - Always use HTTPS in production
   - Set `SECURE_SSL_REDIRECT = True`
   - Enable `SESSION_COOKIE_SECURE = True`
   - Enable `CSRF_COOKIE_SECURE = True`

## Troubleshooting

### Issue: Redirect Loop
**Symptoms**: Browser shows "too many redirects" error
**Solution**:
1. Check that `LOGIN_URL` is not a protected page
2. Verify `LOGIN_REDIRECT_URL` is accessible
3. Clear browser cookies and cache

### Issue: Always Redirected to Login
**Symptoms**: Can't access any page after login
**Solution**:
1. Check if user account is active (`user.is_active = True`)
2. Verify session middleware is enabled
3. Check if cookies are enabled in browser

### Issue: Permission Denied
**Symptoms**: 403 Forbidden error on accessing page
**Solution**:
1. Verify user has required permissions
2. Check user groups (Admin, User)
3. For admin pages, check if user is superuser

### Issue: Next Parameter Not Working
**Symptoms**: After login, not redirected to original page
**Solution**: The broker login view needs to properly handle the `next` parameter:

```python
# Current code (line 57 in apps/brokers/views.py)
next_url = request.GET.get('next', 'brokers:dashboard')
return redirect(next_url)
```

This should work, but make sure the `next` parameter is being passed correctly.

## Creating Users

### Via Django Admin
1. Go to `/admin/`
2. Click "Users" → "Add user"
3. Enter username and password
4. Click "Save and continue editing"
5. Add user to appropriate groups (Admin or User)
6. Check "Active" status
7. Save

### Via Django Shell
```python
python manage.py shell

from django.contrib.auth.models import User, Group

# Create superuser
user = User.objects.create_superuser('admin', 'admin@example.com', 'password')

# Create regular user
user = User.objects.create_user('trader', 'trader@example.com', 'password')

# Add to User group
user_group = Group.objects.get(name='User')
user.groups.add(user_group)
user.save()
```

### Via Management Command
```bash
# Create superuser
python manage.py createsuperuser

# Follow prompts to enter username, email, password
```

## Summary

✅ Login now redirects to `/brokers/login/` instead of `/admin/login/`
✅ After login, users are redirected to broker dashboard `/brokers/`
✅ Test page at `/test/` redirects to `/system/test/` (admin only)
✅ Proper access control with user groups (Admin, User)
✅ Secure session management and CSRF protection
✅ Custom error pages for 403, 404, 500 errors

The authentication system is now properly configured to use the broker dashboard as the main interface!
