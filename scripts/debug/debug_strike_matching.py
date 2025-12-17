"""
Debug strike matching in Neo scrip master
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client, _get_neo_scrip_master

def debug_strikes():
    try:
        client = get_kotak_neo_client()
        print("✅ Neo authenticated\n")

        # Get scrip master
        scrip_master = _get_neo_scrip_master(client)
        print(f"✅ Got {len(scrip_master)} contracts\n")

        # Find Dec 2, 2025 NIFTY Call options
        target_contracts = []

        for contract in scrip_master:
            # NIFTY options only
            if contract.get('pSymbolName') != 'NIFTY':
                continue

            # Call options only
            if contract.get('pOptionType') != 'CE':
                continue

            # Dec 2, 2025 pattern
            symbol = contract.get('pTrdSymbol', '')
            if '25D02' in symbol:
                target_contracts.append(contract)

        print(f"Found {len(target_contracts)} NIFTY Dec 2, 2025 Call options\n")

        # Show strikes around 26850
        print("Strikes around 26850:")
        print("=" * 80)

        for contract in sorted(target_contracts, key=lambda x: float(str(x.get('dStrikePrice;', '0')).replace(',', ''))):
            strike_raw = contract.get('dStrikePrice;', 'N/A')
            symbol = contract.get('pTrdSymbol', 'N/A')

            # Try to parse strike
            try:
                strike_float = float(str(strike_raw).replace(',', ''))
                strike_int = int(strike_float)

                # Show strikes around 26850
                if 26700 <= strike_int <= 27000:
                    print(f"Strike: {strike_int:6d} | Raw: {strike_raw:15s} | Symbol: {symbol}")
            except:
                pass

        # Check specific strike 26850
        print("\n" + "=" * 80)
        print("Searching for strike 26850 specifically:")
        print("=" * 80)

        matches = []
        for contract in target_contracts:
            strike_raw = str(contract.get('dStrikePrice;', ''))

            # Try different matching strategies
            if '26850' in strike_raw or '2.685e+06' in strike_raw or '2685000' in strike_raw:
                matches.append(contract)
                print(f"\nFound match!")
                print(f"  Symbol: {contract.get('pTrdSymbol')}")
                print(f"  Strike Raw: {strike_raw}")
                print(f"  Lot Size: {contract.get('lLotSize')}")

        if not matches:
            print("\n❌ Strike 26850 NOT found in Neo master!")
            print("\nThis means Neo doesn't have this strike listed.")
            print("NIFTY options typically trade at 50-point intervals.")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    debug_strikes()
