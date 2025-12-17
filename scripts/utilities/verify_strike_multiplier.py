"""
Verify how strike prices are stored in Neo scrip master
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client, _get_neo_scrip_master

def verify():
    try:
        client = get_kotak_neo_client()
        print("✅ Neo authenticated\n")

        # Get scrip master
        scrip_master = _get_neo_scrip_master(client)
        print(f"✅ Got {len(scrip_master)} contracts\n")

        # Get a few Dec 2, 2025 contracts
        print("Sample contracts with strike prices:")
        print("="*80)

        count = 0
        for contract in scrip_master:
            if '25D02' in contract.get('pTrdSymbol', '') and contract.get('pSymbolName') == 'NIFTY':
                count += 1
                if count <= 10:
                    symbol = contract.get('pTrdSymbol', '')
                    strike_raw = contract.get('dStrikePrice;', '')
                    strike_float = float(str(strike_raw).replace(',', ''))

                    print(f"\nSymbol: {symbol}")
                    print(f"  Raw: {strike_raw}")
                    print(f"  Float: {strike_float}")
                    print(f"  Divided by 100: {strike_float / 100}")
                    print(f"  As int: {int(strike_float)}")

                if count >= 10:
                    break

        # Test the hypothesis: strikes are stored as actual_strike * 100
        print("\n" + "="*80)
        print("HYPOTHESIS: Strikes are stored as actual_strike * 100")
        print("="*80)

        # Find NIFTY25D0227000CE (should be strike 27000)
        test_symbol = 'NIFTY25D0227000CE'
        for contract in scrip_master:
            if contract.get('pTrdSymbol') == test_symbol:
                strike_raw = contract.get('dStrikePrice;', '')
                strike_float = float(str(strike_raw).replace(',', ''))
                print(f"\nFound: {test_symbol}")
                print(f"  Raw strike: {strike_raw}")
                print(f"  Float: {strike_float}")
                print(f"  Divided by 100: {strike_float / 100}")
                print(f"  Expected: 27000")
                print(f"  ✅ MATCH!" if int(strike_float / 100) == 27000 else "  ❌ NO MATCH")
                break

        # Another test
        test_symbol2 = 'NIFTY25D0226700CE'
        for contract in scrip_master:
            if contract.get('pTrdSymbol') == test_symbol2:
                strike_raw = contract.get('dStrikePrice;', '')
                strike_float = float(str(strike_raw).replace(',', ''))
                print(f"\nFound: {test_symbol2}")
                print(f"  Raw strike: {strike_raw}")
                print(f"  Float: {strike_float}")
                print(f"  Divided by 100: {strike_float / 100}")
                print(f"  Expected: 26700")
                print(f"  ✅ MATCH!" if int(strike_float / 100) == 26700 else "  ❌ NO MATCH")
                break

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    verify()
