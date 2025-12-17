"""
Find specific strike prices for Dec 2, 2025
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client, _get_neo_scrip_master

def find_strikes():
    try:
        client = get_kotak_neo_client()
        print("✅ Neo authenticated\n")

        # Get scrip master
        scrip_master = _get_neo_scrip_master(client)
        print(f"✅ Got {len(scrip_master)} contracts\n")

        # Filter for Dec 2, 2025 NIFTY options
        dec2_contracts = []
        for contract in scrip_master:
            symbol = contract.get('pTrdSymbol', '')
            if '25D02' in symbol and contract.get('pSymbolName') == 'NIFTY':
                dec2_contracts.append(contract)

        print(f"Found {len(dec2_contracts)} NIFTY Dec 2, 2025 contracts\n")

        # Look for specific strikes we're testing
        target_strikes = [26800, 26850, 26900, 27000]

        for strike in target_strikes:
            print(f"\n{'='*80}")
            print(f"Strike: {strike}")
            print(f"{'='*80}")

            # Find call and put
            call_matches = []
            put_matches = []

            for contract in dec2_contracts:
                strike_raw = str(contract.get('dStrikePrice;', ''))
                try:
                    strike_float = float(strike_raw.replace(',', ''))
                    strike_int = int(strike_float)

                    if strike_int == strike:
                        opt_type = contract.get('pOptionType')
                        if opt_type == 'CE':
                            call_matches.append(contract)
                        elif opt_type == 'PE':
                            put_matches.append(contract)
                except:
                    pass

            if call_matches:
                for c in call_matches:
                    print(f"  CALL: {c.get('pTrdSymbol')} (Lot: {c.get('lLotSize')})")
            else:
                print(f"  CALL: ❌ NOT FOUND")

            if put_matches:
                for p in put_matches:
                    print(f"  PUT:  {p.get('pTrdSymbol')} (Lot: {p.get('lLotSize')})")
            else:
                print(f"  PUT:  ❌ NOT FOUND")

        # Show all available strikes (sorted)
        print(f"\n{'='*80}")
        print(f"ALL AVAILABLE STRIKES (Calls only, sorted)")
        print(f"{'='*80}")

        strikes_set = set()
        for contract in dec2_contracts:
            if contract.get('pOptionType') == 'CE':
                strike_raw = str(contract.get('dStrikePrice;', ''))
                try:
                    strike_float = float(strike_raw.replace(',', ''))
                    strikes_set.add(int(strike_float))
                except:
                    pass

        strikes_sorted = sorted(list(strikes_set))
        print(f"\nTotal unique strikes: {len(strikes_sorted)}")
        print(f"Range: {strikes_sorted[0]} to {strikes_sorted[-1]}")

        # Show strikes around 26800-27000
        print(f"\nStrikes in range 26500-27500:")
        in_range = [s for s in strikes_sorted if 26500 <= s <= 27500]
        for strike in in_range:
            print(f"  {strike}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    find_strikes()
