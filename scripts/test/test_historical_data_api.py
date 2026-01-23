#!/usr/bin/env python
"""
Test script for Historical Data API

This script tests the historical data fetching API with various scenarios.
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

import json
from datetime import datetime, timedelta
from django.test import RequestFactory
from django.contrib.auth.models import User
from apps.trading.api.historical_data_views import get_breeze_historical_data, get_stored_historical_data


def create_test_request(user, data):
    """Create a mock POST request with data"""
    factory = RequestFactory()
    request = factory.post(
        '/api/get-breeze-historical-data/',
        data=json.dumps(data),
        content_type='application/json'
    )
    request.user = user
    return request


def create_get_request(user, params):
    """Create a mock GET request with query parameters"""
    factory = RequestFactory()
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    request = factory.get(f'/api/get-stored-historical-data/?{query_string}')
    request.user = user
    return request


def test_stock_data(user):
    """Test fetching stock (cash) data"""
    print("\n" + "="*80)
    print("TEST 1: Fetching Stock Data (ITC - NSE - Cash)")
    print("="*80)

    data = {
        'stock_code': 'ITC',
        'exchange_code': 'NSE',
        'from_date': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
        'to_date': datetime.now().strftime('%Y-%m-%d'),
        'interval': '1day'
    }

    print(f"\nRequest Data: {json.dumps(data, indent=2)}")

    request = create_test_request(user, data)
    response = get_breeze_historical_data(request)
    result = json.loads(response.content)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Success: {result.get('success')}")

    if result.get('success'):
        print(f"✓ Message: {result['message']}")
        print(f"✓ Deleted: {result['data']['deleted_count']} records")
        print(f"✓ Created: {result['data']['created_count']} records")
        print(f"✓ Total Candles: {result['data']['total_candles']}")
        if result['data'].get('date_range'):
            print(f"✓ Date Range: {result['data']['date_range']['first']} to {result['data']['date_range']['last']}")

        # Show sample candles
        if result['data'].get('candles'):
            print("\nSample Candles (first 3):")
            for candle in result['data']['candles'][:3]:
                print(f"  {candle['datetime']}: O={candle['open']}, H={candle['high']}, "
                      f"L={candle['low']}, C={candle['close']}, V={candle['volume']}")
    else:
        print(f"✗ Error: {result.get('error')}")
        if result.get('details'):
            print(f"✗ Details: {result['details']}")

    return result.get('success', False)


def test_futures_data(user):
    """Test fetching futures data"""
    print("\n" + "="*80)
    print("TEST 2: Fetching Futures Data (NIFTY - NFO)")
    print("="*80)

    # Calculate next expiry (last Thursday of current month)
    from calendar import monthrange
    today = datetime.now().date()
    last_day = monthrange(today.year, today.month)[1]
    last_date = datetime(today.year, today.month, last_day).date()
    last_thursday = last_date
    while last_thursday.weekday() != 3:  # 3 = Thursday
        last_thursday -= timedelta(days=1)

    if last_thursday <= today:
        # Move to next month
        if today.month == 12:
            next_month = 1
            next_year = today.year + 1
        else:
            next_month = today.month + 1
            next_year = today.year
        last_day = monthrange(next_year, next_month)[1]
        last_date = datetime(next_year, next_month, last_day).date()
        last_thursday = last_date
        while last_thursday.weekday() != 3:
            last_thursday -= timedelta(days=1)

    expiry_date = last_thursday.strftime('%Y-%m-%d')

    data = {
        'stock_code': 'NIFTY',
        'exchange_code': 'NFO',
        'product_type': 'futures',
        'expiry_date': expiry_date,
        'from_date': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
        'to_date': datetime.now().strftime('%Y-%m-%d'),
        'interval': '5minute'
    }

    print(f"\nRequest Data: {json.dumps(data, indent=2)}")

    request = create_test_request(user, data)
    response = get_breeze_historical_data(request)
    result = json.loads(response.content)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Success: {result.get('success')}")

    if result.get('success'):
        print(f"✓ Message: {result['message']}")
        print(f"✓ Instrument: {result['data']['instrument']}")
        print(f"✓ Created: {result['data']['created_count']} records")
    else:
        print(f"✗ Error: {result.get('error')}")
        if result.get('details'):
            print(f"✗ Details: {result['details']}")

    return result.get('success', False)


def test_options_data(user):
    """Test fetching options data"""
    print("\n" + "="*80)
    print("TEST 3: Fetching Options Data (NIFTY 24500 CE)")
    print("="*80)

    # Use same expiry calculation as futures test
    from calendar import monthrange
    today = datetime.now().date()
    last_day = monthrange(today.year, today.month)[1]
    last_date = datetime(today.year, today.month, last_day).date()
    last_thursday = last_date
    while last_thursday.weekday() != 3:
        last_thursday -= timedelta(days=1)

    if last_thursday <= today:
        if today.month == 12:
            next_month = 1
            next_year = today.year + 1
        else:
            next_month = today.month + 1
            next_year = today.year
        last_day = monthrange(next_year, next_month)[1]
        last_date = datetime(next_year, next_month, last_day).date()
        last_thursday = last_date
        while last_thursday.weekday() != 3:
            last_thursday -= timedelta(days=1)

    expiry_date = last_thursday.strftime('%Y-%m-%d')

    data = {
        'stock_code': 'NIFTY',
        'exchange_code': 'NFO',
        'product_type': 'options',
        'expiry_date': expiry_date,
        'strike_price': 24500,
        'right': 'call',
        'from_date': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d'),
        'to_date': datetime.now().strftime('%Y-%m-%d'),
        'interval': '1minute'
    }

    print(f"\nRequest Data: {json.dumps(data, indent=2)}")

    request = create_test_request(user, data)
    response = get_breeze_historical_data(request)
    result = json.loads(response.content)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Success: {result.get('success')}")

    if result.get('success'):
        print(f"✓ Message: {result['message']}")
        print(f"✓ Instrument: {result['data']['instrument']}")
        print(f"✓ Created: {result['data']['created_count']} records")
    else:
        print(f"✗ Error: {result.get('error')}")
        if result.get('details'):
            print(f"✗ Details: {result['details']}")

    return result.get('success', False)


def test_retrieve_stored_data(user):
    """Test retrieving stored data from database"""
    print("\n" + "="*80)
    print("TEST 4: Retrieving Stored Data from Database")
    print("="*80)

    params = {
        'stock_code': 'ITC',
        'exchange_code': 'NSE',
        'product_type': 'cash',
        'interval': '1day',
        'limit': 10
    }

    print(f"\nRequest Params: {json.dumps(params, indent=2)}")

    request = create_get_request(user, params)
    response = get_stored_historical_data(request)
    result = json.loads(response.content)

    print(f"\nResponse Status: {response.status_code}")
    print(f"Success: {result.get('success')}")

    if result.get('success'):
        print(f"✓ Instrument: {result['data']['instrument']}")
        print(f"✓ Retrieved: {result['data']['count']} candles")

        if result['data'].get('candles'):
            print("\nSample Candles (first 5):")
            for candle in result['data']['candles'][:5]:
                print(f"  {candle['datetime']}: O={candle['open']}, H={candle['high']}, "
                      f"L={candle['low']}, C={candle['close']}")
    else:
        print(f"✗ Error: {result.get('error')}")

    return result.get('success', False)


def test_error_handling(user):
    """Test various error scenarios"""
    print("\n" + "="*80)
    print("TEST 5: Error Handling")
    print("="*80)

    test_cases = [
        {
            'name': 'Missing stock_code',
            'data': {
                'from_date': '2025-01-01',
                'to_date': '2025-01-23'
            },
            'expected_error': 'Missing required parameter: stock_code'
        },
        {
            'name': 'Invalid date format',
            'data': {
                'stock_code': 'ITC',
                'from_date': '01-01-2025',  # Wrong format
                'to_date': '2025-01-23'
            },
            'expected_error': 'Invalid date format'
        },
        {
            'name': 'Invalid date range',
            'data': {
                'stock_code': 'ITC',
                'from_date': '2025-01-23',
                'to_date': '2025-01-01'  # to_date before from_date
            },
            'expected_error': 'Invalid date range'
        },
        {
            'name': 'Missing expiry for futures',
            'data': {
                'stock_code': 'NIFTY',
                'product_type': 'futures',
                'from_date': '2025-01-01',
                'to_date': '2025-01-23'
            },
            'expected_error': 'Missing required parameter for futures: expiry_date'
        },
        {
            'name': 'Missing strike_price for options',
            'data': {
                'stock_code': 'NIFTY',
                'product_type': 'options',
                'expiry_date': '2025-01-30',
                'from_date': '2025-01-01',
                'to_date': '2025-01-23'
            },
            'expected_error': 'Missing required parameter for options: strike_price'
        }
    ]

    passed = 0
    failed = 0

    for test_case in test_cases:
        print(f"\n  Testing: {test_case['name']}")
        request = create_test_request(user, test_case['data'])
        response = get_breeze_historical_data(request)
        result = json.loads(response.content)

        if not result.get('success') and test_case['expected_error'] in result.get('error', ''):
            print(f"  ✓ PASS - Got expected error: {result['error']}")
            passed += 1
        else:
            print(f"  ✗ FAIL - Expected: {test_case['expected_error']}, Got: {result.get('error', 'No error')}")
            failed += 1

    print(f"\nError Handling Tests: {passed} passed, {failed} failed")
    return failed == 0


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("HISTORICAL DATA API TEST SUITE")
    print("="*80)

    # Get first superuser
    try:
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            print("\n✗ No superuser found. Please create a superuser first.")
            print("  Run: python manage.py createsuperuser")
            return

        print(f"\nUsing user: {user.username}")
    except Exception as e:
        print(f"\n✗ Error getting user: {e}")
        return

    # Run tests
    results = []

    try:
        results.append(('Stock Data', test_stock_data(user)))
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        results.append(('Stock Data', False))

    try:
        results.append(('Futures Data', test_futures_data(user)))
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        results.append(('Futures Data', False))

    try:
        results.append(('Options Data', test_options_data(user)))
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        results.append(('Options Data', False))

    try:
        results.append(('Retrieve Stored Data', test_retrieve_stored_data(user)))
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        results.append(('Retrieve Stored Data', False))

    try:
        results.append(('Error Handling', test_error_handling(user)))
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        results.append(('Error Handling', False))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("\nNote: Some tests may fail if:")
        print("  - Market is closed (historical data only available during market hours)")
        print("  - Breeze session token is expired (refresh at /brokers/breeze/login/)")
        print("  - Invalid expiry dates or strike prices")


if __name__ == '__main__':
    main()
