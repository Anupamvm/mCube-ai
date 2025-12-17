#!/usr/bin/env python
"""
Test Breeze API with SBIN to find correct parameters
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.breeze import get_breeze_client

def test_breeze_sbin():
    """Test different parameter combinations for SBIN"""

    breeze = get_breeze_client()

    print("\n" + "="*80)
    print("TESTING BREEZE API WITH SBIN")
    print("="*80 + "\n")

    # Test 1: Get option chain quotes for futures
    print("Test 1: Get option chain quotes for SBIN futures")
    print("-" * 80)
    try:
        response = breeze.get_option_chain_quotes(
            stock_code="SBIN",
            exchange_code="NFO",
            product_type="futures",
            expiry_date="30-DEC-2025"
        )
        print(f"Response: {response}")
        print()
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 2: Try with different expiry format
    print("Test 2: Try with 30-Dec-2025")
    print("-" * 80)
    try:
        response = breeze.get_option_chain_quotes(
            stock_code="SBIN",
            exchange_code="NFO",
            product_type="futures",
            expiry_date="30-Dec-2025"
        )
        print(f"Response: {response}")
        print()
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 3: Get quotes
    print("Test 3: Get quotes for SBIN")
    print("-" * 80)
    try:
        response = breeze.get_quotes(
            stock_code="SBIN",
            exchange_code="NFO",
            product_type="futures",
            expiry_date="30-Dec-2025",
            right="others",
            strike_price="0"
        )
        print(f"Response: {response}")
        print()
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 4: Try placing with Margin product type
    print("Test 4: Try placing order with product='margin'")
    print("-" * 80)
    try:
        response = breeze.place_order(
            stock_code="SBIN",
            exchange_code="NFO",
            product="margin",  # Try margin instead of futures
            action="buy",
            order_type="market",
            quantity="750",  # 1 lot
            price="0",
            validity="day",
            stoploss="0",
            disclosed_quantity="0",
            expiry_date="30-Dec-2025",
            right="others",
            strike_price="0"
        )
        print(f"Response: {response}")
        print()
    except Exception as e:
        print(f"Error: {e}\n")

    # Test 5: Check if market is open
    print("Test 5: Get customer details to check session")
    print("-" * 80)
    try:
        response = breeze.get_funds()
        print(f"Funds Response Status: {response.get('Status')}")
        print()
    except Exception as e:
        print(f"Error: {e}\n")

    print("="*80)


if __name__ == '__main__':
    test_breeze_sbin()
