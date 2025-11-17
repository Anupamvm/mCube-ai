# System Test Page - Setup and Usage

## Overview

A comprehensive test page has been created to test all critical functionalities of the mCube AI Trading System. This page provides an easy way to verify that all components are working correctly.

## Features

The test page includes tests for:

### 1. **Database Tests**
- Database connection
- Migrations status
- Database tables verification

### 2. **Brokers**
- Broker limits access
- Broker positions access
- Option chain data
- Historical price data
- Credential store access

### 3. **Trendlyne Integration**
- Trendlyne credentials verification
- Trendlyne website accessibility
- ChromeDriver (Selenium) availability
- Trendlyne data directory check
- F&O data freshness (max 7 days old)
- Market snapshot data freshness
- Forecaster data (21 pages) verification
- Scraping dependencies (Selenium, BeautifulSoup, Pandas)

### 4. **Data App**
- Market data
- Trendlyne stock data
- Contract data (F&O)
- News articles
- Knowledge base (RAG system)

### 5. **Orders**
- Order records
- Order executions
- Order creation capability

### 6. **Positions**
- Position records
- One position per account rule
- P&L calculations
- Position monitoring

### 7. **Accounts**
- Broker accounts
- API credentials
- Capital calculations

### 8. **LLM Integration**
- Ollama connection
- LLM validations
- LLM prompt templates

### 9. **Redis**
- Redis connection for Celery

### 10. **Background Tasks**
- Background task system
- Task definitions

### 11. **Django Admin**
- Admin models registered
- Admin URL accessibility

## Access

### URL
The test page is accessible at: **`http://localhost:8000/system/test/`**

### Authentication
- **Login required**: You must be logged in as an admin user
- **Admin access only**: Regular users cannot access this page
- If not logged in, you'll be redirected to `/brokers/login/`

### Steps to Access

1. Start the Django development server:
   ```bash
   python manage.py runserver
   ```

2. Login as an admin user at: `http://localhost:8000/brokers/login/`

3. Navigate to the test page: `http://localhost:8000/system/test/`

## How It Works

The test page:
1. Runs all test functions automatically when you visit the page
2. Displays pass/fail status for each test with appropriate icons
3. Shows summary statistics (total tests, passed, failed, pass rate)
4. Groups tests by category for easy navigation
5. Auto-refreshes every 5 minutes
6. Provides links to Django Admin and Broker Dashboard

## Test Results Display

- **Green checkmark (✓)**: Test passed
- **Red X (✗)**: Test failed
- Each test shows a descriptive message with relevant details
- Category badges show the pass/fail ratio for each section

## Quick Actions

From the test page, you can:
- **Refresh Tests**: Manually refresh all tests
- **Access Django Admin**: Quick link to `/admin/`
- **Access Broker Dashboard**: Quick link to `/brokers/`

## Troubleshooting

### Issue: Page shows "Permission Denied"
**Solution**: Make sure you're logged in as an admin user (superuser or member of 'Admin' group)

### Issue: Some tests are failing
**Solution**: Check the error messages displayed for each failed test. Common issues:
- Database not migrated: Run `python manage.py migrate`
- Redis not running: Start Redis server
- Ollama not running: Start Ollama service
- Missing broker credentials: Configure credentials in Django admin

### Issue: Cannot access the page
**Solution**:
1. Make sure Django server is running
2. Check that the URL is correct: `http://localhost:8000/system/test/`
3. Verify you're logged in as an admin user

## Adding New Tests

To add new tests, edit `/apps/core/views.py` and:

1. Create a new test function following this pattern:
   ```python
   def test_your_feature():
       """Test your feature"""
       tests = []

       try:
           # Your test logic here
           tests.append({
               'name': 'Test Name',
               'status': 'pass',  # or 'fail'
               'message': 'Test description',
           })
       except Exception as e:
           tests.append({
               'name': 'Test Name',
               'status': 'fail',
               'message': f'Error: {str(e)}',
           })

       return {'category': 'Your Category', 'tests': tests}
   ```

2. Add the function to the `test_results` dictionary in `system_test_page()`:
   ```python
   test_results = {
       # ... existing tests ...
       'your_feature': test_your_feature(),
   }
   ```

## File Locations

- **View**: `/apps/core/views.py`
- **Template**: `/templates/core/system_test.html`
- **URLs**: `/apps/core/urls.py`
- **Main URL Config**: `/mcube_ai/urls.py`

## Security

- The page is protected by `@login_required` and `@user_passes_test(is_admin_user)`
- Only admin users (superusers or members of 'Admin' group) can access
- This ensures sensitive system information is not exposed to regular users

## Notes

- The page does **not** modify any data - it only reads and verifies
- Tests are non-destructive and safe to run at any time
- Auto-refresh is enabled (every 5 minutes) to keep data current
- The timestamp at the bottom shows when tests were last run

## Pre-existing Issues

If you encounter a `ModuleNotFoundError: No module named 'neo_api_client'` error:
- This is a pre-existing dependency issue with the Kotak Neo integration
- The test page will still work for most features
- To resolve: Install the correct Kotak Neo SDK or comment out the import in `/apps/brokers/integrations/kotak_neo.py`
