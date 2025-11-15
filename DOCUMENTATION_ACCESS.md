# Documentation Access Guide

## Overview
All documentation files are now accessible through the web interface for admin users.

## Accessing Documentation

### From the Home Page
1. Login as an admin user at: `http://127.0.0.1:8000/brokers/login/`
2. Navigate to the home page: `http://127.0.0.1:8000/`
3. Scroll to the "Documentation" section (visible only for admin users)
4. Click on any documentation card to view

### Direct URLs

Admin users can directly access documentation using these URLs:

| Documentation | URL |
|---------------|-----|
| Quick Start Guide | `/system/docs/quick_start/` |
| Setup Guide | `/system/docs/setup_guide/` |
| Celery Setup | `/system/docs/celery_setup/` |
| Telegram Bot Guide | `/system/docs/telegram_bot/` |
| URL Configuration | `/system/docs/url_config/` |
| Authentication Guide | `/system/docs/auth_guide/` |
| Fixes Summary | `/system/docs/fixes_summary/` |

### Full URLs
```
http://127.0.0.1:8000/system/docs/quick_start/
http://127.0.0.1:8000/system/docs/setup_guide/
http://127.0.0.1:8000/system/docs/celery_setup/
http://127.0.0.1:8000/system/docs/telegram_bot/
http://127.0.0.1:8000/system/docs/url_config/
http://127.0.0.1:8000/system/docs/auth_guide/
http://127.0.0.1:8000/system/docs/fixes_summary/
```

## Access Requirements

- **Authentication**: Must be logged in
- **Authorization**: Must be an admin user (superuser or member of "Admin" group)
- **Redirect**: Non-authenticated users are redirected to `/brokers/login/`

## Features

### Secure Access
- Only admin users can view documentation
- Automatic redirect to login for unauthorized access
- Session-based authentication

### Browser-Friendly Display
- Documentation is served as plain text
- Opens in a new tab (target="_blank")
- Easy to read in browser
- Can be printed or saved directly

### Available Documentation

#### 1. Quick Start Guide
30-minute setup guide for getting started with mCube Trading System
- Initial setup steps
- Basic configuration
- First run instructions

#### 2. Setup Guide
Complete installation and configuration instructions
- Detailed installation steps
- Environment setup
- Database configuration
- Broker integration

#### 3. Celery Setup
Background task configuration and management
- Celery installation
- Task configuration
- Worker management
- Monitoring tasks

#### 4. Telegram Bot Guide
Bot commands and usage instructions
- Bot setup
- Available commands
- Configuration
- Usage examples

#### 5. URL Configuration
URL routing and configuration guide (NEW)
- Fixed URL issues
- URL structure
- Error handling
- Testing instructions

#### 6. Authentication Guide
Login flow and permissions guide (NEW)
- Authentication settings
- Login behavior
- User roles
- Access control

#### 7. Fixes Summary
Summary of all recent fixes and improvements (NEW)
- URL fixes
- Authentication updates
- Error handling enhancements
- Files modified

## Implementation Details

### View Function
Location: `apps/core/views.py::view_documentation()`

The view:
- Validates doc_name against allowed documents
- Checks file existence
- Returns file as plain text with UTF-8 encoding
- Requires admin authentication

### URL Pattern
Location: `apps/core/urls.py`

```python
path('docs/<str:doc_name>/', views.view_documentation, name='view_documentation'),
```

### Allowed Documents
Defined in `view_documentation()` function:

```python
allowed_docs = {
    'quick_start': 'QUICK_START.md',
    'setup_guide': 'SETUP_GUIDE.md',
    'celery_setup': 'CELERY_SETUP.md',
    'telegram_bot': 'TELEGRAM_BOT_GUIDE.md',
    'url_config': 'URL_CONFIGURATION.md',
    'auth_guide': 'AUTHENTICATION_GUIDE.md',
    'fixes_summary': 'FIXES_SUMMARY.md',
}
```

### Security Features
- **Path Validation**: Only allowed document names can be accessed
- **File Existence Check**: Returns 404 if file doesn't exist
- **Admin Only**: Requires `@user_passes_test(is_admin_user)`
- **No Directory Traversal**: doc_name is validated against whitelist

## Home Page Integration

The documentation section appears on the home page for authenticated admin users:

### Documentation Cards
- Visual cards with icons
- Clear descriptions
- Opens in new tab
- Grid layout for easy navigation

### Visibility
- Only shown to authenticated admin users
- Hidden for regular users and anonymous visitors
- Part of the comprehensive home page dashboard

## Adding New Documentation

To add new documentation to the system:

1. **Create the markdown file** in the project root directory
2. **Update the view** in `apps/core/views.py`:
   ```python
   allowed_docs = {
       # ... existing docs ...
       'my_new_doc': 'MY_NEW_DOC.md',
   }
   ```
3. **Add to home page** in `apps/core/templates/core/home.html`:
   ```html
   <a href="{% url 'core:view_documentation' 'my_new_doc' %}" target="_blank" class="doc-card">
       <div class="doc-icon">📄</div>
       <h3>My New Doc</h3>
       <p>Description here</p>
   </a>
   ```

## Troubleshooting

### Error: "Documentation not found"
- Check that the doc_name is in the `allowed_docs` dictionary
- Verify the file exists in the project root directory
- Ensure the file name matches exactly (case-sensitive)

### Error: 403 Forbidden
- User must be logged in
- User must be an admin (superuser or in "Admin" group)
- Check user permissions in Django admin

### Error: 404 Not Found
- Verify the URL pattern is correct
- Check that the doc_name parameter is valid
- Ensure the file exists at the specified path

## File Locations

### Documentation Files
Location: `/Users/anupammangudkar/Projects/mCube-ai/mCube-ai/*.md`

All markdown files are stored in the project root directory for easy access and editing.

### View Code
Location: `apps/core/views.py` (line 143-173)

### URL Configuration
Location: `apps/core/urls.py` (line 12)

### Home Template
Location: `apps/core/templates/core/home.html` (lines 140-174)

## Summary

✅ Documentation is now accessible through the web interface
✅ Admin-only access with proper authentication
✅ Clean, browser-friendly display
✅ Integrated into home page with visual cards
✅ Secure with path validation and access control
✅ Easy to add new documentation files

All documentation is now one click away from the home page for admin users!
