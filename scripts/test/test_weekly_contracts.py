"""
Find NIFTY weekly contracts for December 2, 2025
"""
import os, sys, django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client

def find_weekly_contracts():
    try:
        client = get_kotak_neo_client()
        print("✅ Neo client authenticated\n")

        # Search for NIFTY options expiring on Dec 2, 2025
        print("Searching for Dec 2, 2025 weekly contracts...")
        print("=" * 80)

        # Try exact date format
        result = client.search_scrip(
            exchange_segment='nse_fo',
            symbol='NIFTY',
            expiry='02-DEC-2025',  # Try with dashes
            option_type='',
            strike_price=''
        )

        if result and len(result) > 0:
            print(f"\n✅ Found {len(result)} contracts for 02-DEC-2025:")
            for i, scrip in enumerate(result[:20]):
                symbol = scrip.get('pTrdSymbol', 'N/A')
                lot = scrip.get('lLotSize', 'N/A')
                strike = scrip.get('lToken', 'N/A')
                print(f"  [{i+1}] {symbol} - Lot: {lot}")
        else:
            print("\n❌ No contracts found for 02-DEC-2025")

            print("\n" + "=" * 80)
            print("Listing contracts with 'DEC' to find pattern...")
            print("=" * 80)

            # Get all NIFTY contracts and filter
            result_all = client.search_scrip(
                exchange_segment='nse_fo',
                symbol='NIFTY',
                expiry='',
                option_type='',
                strike_price=''
            )

            if result_all:
                # Look for patterns
                dec_contracts = [s for s in result_all if 'DEC' in str(s.get('pTrdSymbol', ''))]

                print(f"\nFound {len(dec_contracts)} DEC contracts. Sample:")
                for i, scrip in enumerate(dec_contracts[:30]):
                    symbol = scrip.get('pTrdSymbol', 'N/A')
                    print(f"  {symbol}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    find_weekly_contracts()
