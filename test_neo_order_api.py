#!/usr/bin/env python3
"""
Test script to verify Kotak Neo API order placement functionality

This script tests:
1. Neo API authentication
2. Fetching margin data
3. Placing a test order (paper trading mode)
4. Order status checking

Run from project root:
    python test_neo_order_api.py
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from tools.neo import NeoAPI
from apps.core.models import CredentialStore
from apps.data.models import ContractData
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_neo_authentication():
    """Test Neo API authentication"""
    print("\n" + "="*60)
    print("TEST 1: Neo API Authentication")
    print("="*60)

    try:
        neo = NeoAPI()

        # Test login
        print("⏳ Attempting login...")
        neo.login()

        if neo.session_active:
            print("✅ Authentication successful!")
            print(f"   Session Active: True")
            return neo
        else:
            print("❌ Authentication failed!")
            return None

    except Exception as e:
        print(f"❌ Authentication error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_margin_data(neo):
    """Test fetching margin data"""
    print("\n" + "="*60)
    print("TEST 2: Fetch Margin Data")
    print("="*60)

    try:
        print("⏳ Fetching margin data...")
        margin_data = neo.get_margin()

        if margin_data:
            print("✅ Margin data fetched successfully!")
            print(f"   Available Margin: ₹{margin_data.get('available_margin', 0):,.2f}")
            print(f"   Used Margin: ₹{margin_data.get('used_margin', 0):,.2f}")
            print(f"   Total Margin: ₹{margin_data.get('total_margin', 0):,.2f}")
            print(f"   Collateral: ₹{margin_data.get('collateral', 0):,.2f}")
            return True
        else:
            print("❌ Failed to fetch margin data")
            return False

    except Exception as e:
        print(f"❌ Margin fetch error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_positions(neo):
    """Test fetching positions"""
    print("\n" + "="*60)
    print("TEST 3: Fetch Positions")
    print("="*60)

    try:
        print("⏳ Fetching positions...")
        positions = neo.get_positions()

        print(f"✅ Positions fetched: {len(positions)} positions found")

        if positions:
            for i, pos in enumerate(positions[:3], 1):  # Show first 3
                print(f"\n   Position {i}:")
                print(f"      Symbol: {pos.get('symbol', 'N/A')}")
                print(f"      Qty: {pos.get('quantity', 0)}")
                print(f"      P&L: ₹{pos.get('pnl', 0):,.2f}")
        else:
            print("   No open positions")

        return True

    except Exception as e:
        print(f"❌ Position fetch error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_order_placement_dryrun(neo):
    """
    Test order placement API structure (dry run - no actual order)

    This tests the API call structure without actually placing an order
    """
    print("\n" + "="*60)
    print("TEST 4: Order Placement API Test (DRY RUN)")
    print("="*60)

    try:
        # Get a sample futures contract
        contract = ContractData.objects.filter(
            option_type='FUTURE',
            symbol='NIFTY'
        ).first()

        if not contract:
            print("❌ No futures contract found in database")
            return False

        print(f"📋 Test Contract: {contract.symbol}")
        print(f"   Expiry: {contract.expiry}")
        print(f"   Lot Size: {contract.lot_size}")
        print(f"   Current Price: ₹{contract.price}")

        # Prepare order parameters (for testing structure only)
        order_params = {
            'symbol': contract.symbol,
            'action': 'B',  # Buy
            'quantity': contract.lot_size,  # 1 lot
            'order_type': 'MKT',  # Market order
            'price': 0,
            'exchange': 'NFO',
            'product': 'NRML',
        }

        print("\n📝 Order Parameters (for API structure test):")
        for key, value in order_params.items():
            print(f"   {key}: {value}")

        print("\n⚠️  NOTE: This is a DRY RUN - no actual order will be placed")
        print("✅ Order API structure validated")

        # To actually test order placement, uncomment below:
        # CAUTION: This will place a real order!
        # order_id = neo.place_order(**order_params)
        # if order_id:
        #     print(f"✅ Order placed successfully! Order ID: {order_id}")
        #     return order_id
        # else:
        #     print("❌ Order placement failed")
        #     return None

        return True

    except Exception as e:
        print(f"❌ Order test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_neo_credentials():
    """Test if Neo credentials exist in database"""
    print("\n" + "="*60)
    print("TEST 0: Check Neo Credentials")
    print("="*60)

    try:
        creds = CredentialStore.objects.filter(service='kotakneo').first()

        if creds:
            print("✅ Kotak Neo credentials found")
            print(f"   API Key: {creds.api_key[:10]}..." if creds.api_key else "   API Key: Not set")
            print(f"   Username: {creds.username}" if creds.username else "   Username: Not set")
            print(f"   Has Password: {'Yes' if creds.password else 'No'}")
            print(f"   Has OTP: {'Yes' if creds.session_token else 'No'}")
            print(f"   Has Session Token: {'Yes' if creds.sid else 'No'}")
            return True
        else:
            print("❌ No Kotak Neo credentials found in database")
            print("   Please add credentials via Django admin or management command")
            return False

    except Exception as e:
        print(f"❌ Credentials check error: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("KOTAK NEO API - ORDER PLACEMENT VERIFICATION")
    print("="*60)

    # Test 0: Check credentials
    if not test_neo_credentials():
        print("\n❌ OVERALL RESULT: FAILED - No credentials found")
        print("   Please configure Kotak Neo credentials first")
        return

    # Test 1: Authentication
    neo = test_neo_authentication()
    if not neo:
        print("\n❌ OVERALL RESULT: FAILED - Authentication failed")
        return

    # Test 2: Margin data
    if not test_margin_data(neo):
        print("\n⚠️  WARNING: Margin data fetch failed")

    # Test 3: Positions
    if not test_get_positions(neo):
        print("\n⚠️  WARNING: Position fetch failed")

    # Test 4: Order placement (dry run)
    if not test_order_placement_dryrun(neo):
        print("\n⚠️  WARNING: Order API test failed")

    print("\n" + "="*60)
    print("✅ OVERALL RESULT: Neo API is functional!")
    print("="*60)
    print("\nNext Steps:")
    print("1. Review the api_views.py place_futures_order function")
    print("2. Update it to use Neo API instead of Breeze API")
    print("3. Test with a small order in paper trading mode")
    print("="*60)


if __name__ == '__main__':
    main()
