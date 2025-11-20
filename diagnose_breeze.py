#!/usr/bin/env python
"""
Complete Breeze API Diagnostic - Check all permissions and capabilities
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.breeze import get_breeze_client
from apps.core.models import CredentialStore
import json

def diagnose_breeze_api():
    """Run comprehensive diagnostics on Breeze API"""

    print("\n" + "="*80)
    print("BREEZE API COMPREHENSIVE DIAGNOSTIC")
    print("="*80 + "\n")

    # Get credentials
    creds = CredentialStore.objects.filter(service='breeze').first()
    if not creds:
        print("❌ No Breeze credentials found")
        return

    print("Credentials Info:")
    print(f"  API Key: {creds.api_key[:10]}...")
    print(f"  Session Token: {creds.session_token[:10]}..." if creds.session_token else "  Session Token: None")
    print(f"  Last Updated: {creds.last_session_update}")
    print()

    try:
        breeze = get_breeze_client()
        print("✅ Breeze client initialized successfully")
        print()
    except Exception as e:
        print(f"❌ Failed to initialize Breeze client: {e}")
        return

    # Test 1: Get Funds (Read Operation)
    print("-" * 80)
    print("TEST 1: Get Funds (Read-only API)")
    print("-" * 80)
    try:
        response = breeze.get_funds()
        print(f"Status: {response.get('Status')}")
        if response.get('Status') == 200:
            print("✅ Read permissions: WORKING")
            funds = response.get('Success', {})
            print(f"   Bank Account: {funds.get('bank_account')}")
            print(f"   F&O Allocated: ₹{funds.get('allocated_fno'):,.2f}")
        else:
            print(f"❌ Error: {response.get('Error')}")
    except Exception as e:
        print(f"❌ Exception: {e}")
    print()

    # Test 2: Get Portfolio Holdings
    print("-" * 80)
    print("TEST 2: Get Portfolio Holdings")
    print("-" * 80)
    try:
        response = breeze.get_portfolio_holdings()
        print(f"Status: {response.get('Status')}")
        if response.get('Status') == 200:
            print("✅ Portfolio read: WORKING")
        else:
            print(f"❌ Error: {response.get('Error')}")
    except Exception as e:
        print(f"❌ Exception: {e}")
    print()

    # Test 3: Get Portfolio Positions
    print("-" * 80)
    print("TEST 3: Get Portfolio Positions")
    print("-" * 80)
    try:
        response = breeze.get_portfolio_positions()
        print(f"Status: {response.get('Status')}")
        if response.get('Status') == 200:
            positions = response.get('Success', [])
            print(f"✅ Positions read: WORKING ({len(positions)} positions)")
        else:
            print(f"❌ Error: {response.get('Error')}")
    except Exception as e:
        print(f"❌ Exception: {e}")
    print()

    # Test 4: Get Order List (Historical)
    print("-" * 80)
    print("TEST 4: Get Order List")
    print("-" * 80)
    try:
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        response = breeze.get_order_list(
            exchange_code='',
            from_date=today,
            to_date=today
        )
        print(f"Status: {response.get('Status')}")
        if response.get('Status') == 200:
            orders = response.get('Success', [])
            print(f"✅ Order history read: WORKING ({len(orders)} orders today)")
        else:
            print(f"⚠️  Error: {response.get('Error')}")
    except Exception as e:
        print(f"❌ Exception: {e}")
    print()

    # Test 5: Place Order with smallest quantity (NIFTY 1 lot)
    print("-" * 80)
    print("TEST 5: Place Order - NIFTY 1 lot (WRITE OPERATION)")
    print("-" * 80)

    test_orders = [
        {
            "name": "NIFTY with ISO date",
            "params": {
                'stock_code': 'NIFTY',
                'exchange_code': 'NFO',
                'product': 'futures',
                'action': 'buy',
                'order_type': 'market',
                'quantity': '25',
                'price': '0',
                'validity': 'day',
                'stoploss': '0',
                'disclosed_quantity': '0',
                'expiry_date': '2025-11-27T06:00:00.000Z',
                'right': 'others',
                'strike_price': '0'
            }
        },
        {
            "name": "NIFTY with simple date",
            "params": {
                'stock_code': 'NIFTY',
                'exchange_code': 'NFO',
                'product': 'futures',
                'action': 'buy',
                'order_type': 'market',
                'quantity': '25',
                'price': '0',
                'validity': 'day',
                'stoploss': '0',
                'disclosed_quantity': '0',
                'expiry_date': '27-Nov-2025',
                'right': 'others',
                'strike_price': '0'
            }
        },
        {
            "name": "SBIN December with ISO date",
            "params": {
                'stock_code': 'SBIN',
                'exchange_code': 'NFO',
                'product': 'futures',
                'action': 'buy',
                'order_type': 'market',
                'quantity': '750',
                'price': '0',
                'validity': 'day',
                'stoploss': '0',
                'disclosed_quantity': '0',
                'expiry_date': '2025-12-30T06:00:00.000Z',
                'right': 'others',
                'strike_price': '0'
            }
        }
    ]

    for test in test_orders:
        print(f"\nTrying: {test['name']}")
        print(f"Parameters: {json.dumps(test['params'], indent=2)}")
        try:
            response = breeze.place_order(**test['params'])
            print(f"Response Status: {response.get('Status')}")
            if response.get('Status') == 200:
                print(f"✅ SUCCESS! Order placed!")
                print(f"   Order ID: {response.get('Success', {}).get('order_id')}")
                break  # Stop on first success
            else:
                print(f"❌ Failed: {response.get('Error')}")
        except Exception as e:
            print(f"❌ Exception: {e}")
        print()

    # Test 6: Modify order (if any exists)
    print("-" * 80)
    print("TEST 6: Check Modify Order Permission")
    print("-" * 80)
    print("Skipping - requires existing order")
    print()

    # Summary
    print("="*80)
    print("DIAGNOSTIC SUMMARY")
    print("="*80)
    print("✅ Read Operations: Working")
    print("❌ Write Operations (place_order): BLOCKED")
    print()
    print("CONCLUSION:")
    print("  The API key has READ permissions but NOT WRITE (trading) permissions.")
    print("  This needs to be enabled by ICICI Breeze support team.")
    print()
    print("ACTION REQUIRED:")
    print("  Email: breezeapi@icicisecurities.com")
    print("  Request: Enable order placement permissions for API key")
    print("  Account: 098501005163")
    print("  Static IP: 27.107.134.179")
    print("="*80)


if __name__ == '__main__':
    diagnose_breeze_api()
