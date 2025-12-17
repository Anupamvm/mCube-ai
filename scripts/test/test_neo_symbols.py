"""
Test script to discover actual Neo symbol format
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client
from datetime import date

def test_neo_symbol_formats():
    """Test different expiry formats to find what Neo accepts"""

    try:
        client = get_kotak_neo_client()
        print("✅ Neo client authenticated\n")

        expiry = date(2025, 12, 2)

        # Test different expiry formats
        expiry_formats = [
            ('02DEC2025', '02DEC2025'),
            ('02-DEC-2025', '02-DEC-2025'),
            ('02DEC25', '02DEC25'),
            ('02-DEC-25', '02-DEC-25'),
            ('2025-12-02', '2025-12-02'),
        ]

        print("Testing different expiry formats with Neo API:")
        print("=" * 80)

        for label, expiry_str in expiry_formats:
            print(f"\nTrying expiry format: {expiry_str}")

            try:
                result = client.search_scrip(
                    exchange_segment='nse_fo',
                    symbol='NIFTY',
                    expiry=expiry_str,
                    option_type='CE',
                    strike_price='27100'
                )

                if result and len(result) > 0:
                    print(f"  ✅ SUCCESS! Found {len(result)} results")
                    for i, scrip in enumerate(result[:3]):  # Show first 3
                        print(f"  [{i+1}] pTrdSymbol: {scrip.get('pTrdSymbol', 'N/A')}")
                        print(f"      pSymbol: {scrip.get('pSymbol', 'N/A')}")
                        print(f"      Lot Size: {scrip.get('lLotSize', 'N/A')}")
                else:
                    print(f"  ❌ No results")

            except Exception as e:
                print(f"  ❌ Error: {e}")

        print("\n" + "=" * 80)
        print("\nTrying to list ALL NIFTY options for December 2025:")
        print("=" * 80)

        # Try to get any NIFTY options for December 2025
        try:
            result = client.search_scrip(
                exchange_segment='nse_fo',
                symbol='NIFTY',
                expiry='',  # Empty to get all
                option_type='',
                strike_price=''
            )

            if result and len(result) > 0:
                print(f"\n✅ Found {len(result)} total NIFTY contracts")

                # Filter for December 2025
                dec_contracts = [s for s in result if 'DEC' in str(s.get('pTrdSymbol', '')) and '2025' in str(s.get('pTrdSymbol', ''))]

                if dec_contracts:
                    print(f"\nDec 2025 contracts found: {len(dec_contracts)}")
                    for i, scrip in enumerate(dec_contracts[:10]):  # Show first 10
                        print(f"  [{i+1}] {scrip.get('pTrdSymbol', 'N/A')} - Lot: {scrip.get('lLotSize', 'N/A')}")
                else:
                    print("\n❌ No December 2025 contracts found")
                    print("\nShowing some example contracts:")
                    for i, scrip in enumerate(result[:10]):
                        print(f"  [{i+1}] {scrip.get('pTrdSymbol', 'N/A')}")
            else:
                print("❌ No contracts found")

        except Exception as e:
            print(f"❌ Error listing contracts: {e}")

    except Exception as e:
        print(f"❌ Failed to connect to Neo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_neo_symbol_formats()
