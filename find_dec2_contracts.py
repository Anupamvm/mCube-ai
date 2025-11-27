"""
Find December 2, 2025 NIFTY contracts in scrip master
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client, _get_neo_scrip_master

def find_dec2():
    try:
        client = get_kotak_neo_client()
        print("✅ Neo authenticated\n")

        # Get scrip master
        scrip_master = _get_neo_scrip_master(client)
        print(f"✅ Got {len(scrip_master)} contracts\n")

        # Search for December 2, 2025 pattern: "25D02"
        print("Searching for December 2, 2025 pattern: '25D02'")
        print("="*80)

        dec2_contracts = []
        for contract in scrip_master:
            symbol = contract.get('pTrdSymbol', '')
            if '25D02' in symbol and 'NIFTY' in symbol:
                dec2_contracts.append(contract)

        print(f"\nFound {len(dec2_contracts)} contracts with '25D02' pattern\n")

        if dec2_contracts:
            # Show first 20
            for i, contract in enumerate(dec2_contracts[:20]):
                symbol = contract.get('pTrdSymbol', '')
                symbol_name = contract.get('pSymbolName', '')
                option_type = contract.get('pOptionType', '')
                strike = contract.get('dStrikePrice;', '')
                lot_size = contract.get('lLotSize', '')

                print(f"[{i+1}] {symbol}")
                print(f"    Symbol Name: {symbol_name}, Type: {option_type}, Strike: {strike}, Lot: {lot_size}")
        else:
            print("❌ NO contracts found with '25D02' pattern!")
            print("\nSearching for ANY December 2025 NIFTY contracts...")

            # Try different patterns
            patterns = ['25D', 'DEC25', 'D25']
            for pattern in patterns:
                print(f"\n  Pattern: '{pattern}'")
                matches = [c for c in scrip_master
                          if pattern in c.get('pTrdSymbol', '') and 'NIFTY' in c.get('pTrdSymbol', '')]
                print(f"  Found: {len(matches)} contracts")
                if matches:
                    for i, c in enumerate(matches[:5]):
                        print(f"    [{i+1}] {c.get('pTrdSymbol', '')}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    find_dec2()
