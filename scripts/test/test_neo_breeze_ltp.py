#!/usr/bin/env python3
"""
Test Neo to Breeze symbol mapping and real-time LTP fetching.
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/Users/anupammangudkar/PyProjects/mCube-ai')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mCube.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import map_neo_symbol_to_breeze, get_ltp_from_neo

def test_symbol_mapping():
    """Test Neo to Breeze symbol mapping"""
    print("=" * 80)
    print("TEST 1: Neo to Breeze Symbol Mapping")
    print("=" * 80)

    test_symbols = [
        'BANKNIFTY25DECFUT',
        'NIFTY26JANFUT',
        'NIFTY25DECFUT'
    ]

    for neo_symbol in test_symbols:
        print(f"\n📝 Testing: {neo_symbol}")
        result = map_neo_symbol_to_breeze(neo_symbol)

        if result['success']:
            print(f"  ✅ SUCCESS")
            print(f"     Stock Code: {result['stock_code']}")
            print(f"     Expiry Date: {result['expiry_date']}")
            print(f"     Product Type: {result['product_type']}")
            print(f"     Exchange: {result['exchange_code']}")
        else:
            print(f"  ❌ FAILED: {result['error']}")


def test_live_ltp():
    """Test fetching live LTP via Breeze"""
    print("\n" + "=" * 80)
    print("TEST 2: Fetching Live LTP via Breeze")
    print("=" * 80)

    # Use BANKNIFTY25DECFUT from the actual position
    neo_symbol = 'BANKNIFTY25DECFUT'

    print(f"\n📊 Fetching LTP for: {neo_symbol}")
    ltp = get_ltp_from_neo(neo_symbol)

    if ltp:
        print(f"  ✅ Real-time LTP: ₹{ltp:.2f}")
    else:
        print(f"  ❌ Failed to fetch LTP")


if __name__ == "__main__":
    try:
        test_symbol_mapping()
        test_live_ltp()

        print("\n" + "=" * 80)
        print("✅ All tests completed!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
