#!/usr/bin/env python3
"""
Test close position functionality
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/Users/anupammangudkar/PyProjects/mCube-ai')
os.environ['DJANGO_SETTINGS_MODULE'] = 'mcube_ai.settings'
django.setup()

from apps.brokers.integrations.kotak_neo import map_neo_symbol_to_breeze
from apps.brokers.integrations.breeze import get_breeze_client

def test_symbol_mapping():
    """Test symbol mapping for closing positions"""
    print("\n" + "="*80)
    print("Testing Symbol Mapping for Close Position")
    print("="*80)

    test_symbols = [
        'JIOFIN26JANFUT',
        'JIOFIN25DECFUT',
        'NIFTY26JANFUT'
    ]

    for symbol in test_symbols:
        print(f"\nSymbol: {symbol}")
        mapping = map_neo_symbol_to_breeze(symbol)

        if mapping['success']:
            print(f"  ✅ Stock Code: {mapping['stock_code']}")
            print(f"  ✅ Expiry: {mapping['expiry_date']}")
            print(f"  ✅ Exchange: {mapping['exchange_code']}")

            # Now test getting actual contract from Breeze
            try:
                breeze = get_breeze_client()
                resp = breeze.get_option_chain_quotes(
                    stock_code=mapping['stock_code'],
                    exchange_code='NFO',
                    product_type='futures',
                    expiry_date=""  # Get all
                )

                if resp and resp.get('Status') == 200:
                    contracts = resp.get('Success', [])
                    print(f"  ✅ Found {len(contracts)} contracts from Breeze")

                    # Match by month/year
                    calc_expiry = mapping['expiry_date']
                    calc_month_year = calc_expiry.split('-')[1:3]

                    for contract in contracts:
                        contract_expiry = contract.get('expiry_date', '')
                        if contract_expiry:
                            contract_month_year = contract_expiry.split('-')[1:3]

                            if contract_month_year == calc_month_year:
                                print(f"  ✅ Matched Contract:")
                                print(f"     Expiry: {contract_expiry}")
                                print(f"     Lot Size: {contract.get('lot_size')}")
                                print(f"     LTP: ₹{contract.get('ltp')}")
                                break
                    else:
                        print(f"  ⚠️ No matching contract found for {calc_month_year}")
                else:
                    print(f"  ❌ Breeze API error: {resp.get('Error')}")

            except Exception as e:
                print(f"  ❌ Exception: {e}")
        else:
            print(f"  ❌ Mapping failed: {mapping['error']}")


if __name__ == "__main__":
    test_symbol_mapping()
    print("\n" + "="*80)
    print("✅ Test Complete")
    print("="*80)
