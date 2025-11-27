"""
Debug script to check actual field names in Neo scrip master
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client, _get_neo_scrip_master

def debug_fields():
    try:
        client = get_kotak_neo_client()
        print("✅ Neo authenticated\n")

        # Get scrip master
        scrip_master = _get_neo_scrip_master(client)
        print(f"✅ Got {len(scrip_master)} contracts\n")

        # Show first NIFTY option contract fields
        print("Looking for NIFTY option contracts...")
        print("="*80)

        count = 0
        for contract in scrip_master:
            # Try different field names for symbol
            symbol_name = (contract.get('pSymbolName') or
                          contract.get('pSymbol') or
                          contract.get('Symbol') or
                          contract.get('Instrument Name'))

            if symbol_name and 'NIFTY' in str(symbol_name):
                count += 1
                if count <= 3:  # Show first 3
                    print(f"\n[Contract {count}]")
                    print(f"All fields: {contract.keys()}")
                    print(f"\nFull contract:")
                    for key, value in contract.items():
                        print(f"  {key}: {value}")
                    print("="*80)

                if count == 3:
                    break

        if count == 0:
            print("\n❌ No NIFTY contracts found!")
            print("\nShowing first 3 contracts of ANY type:")
            for i, contract in enumerate(scrip_master[:3]):
                print(f"\n[Contract {i+1}]")
                print(f"All fields: {contract.keys()}")
                print(f"\nFull contract:")
                for key, value in contract.items():
                    print(f"  {key}: {value}")
                print("="*80)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    debug_fields()
