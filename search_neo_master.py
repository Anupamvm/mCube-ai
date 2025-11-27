"""
Search Neo's scrip master for NIFTY Dec 2, 2025 contracts
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client
import json
from datetime import date

def search_neo_master():
    """Search Neo's scrip master for Dec 2, 2025 NIFTY options"""

    try:
        client = get_kotak_neo_client()
        print("✅ Neo client authenticated\n")

        print("Downloading Neo scrip master...")
        print("=" * 80)

        # Get scrip master - this should return all available contracts
        try:
            # Try getting scrip master for NSE F&O
            scrip_master = client.scrip_master(exchange_segment='nse_fo')

            if scrip_master:
                print(f"✅ Downloaded scrip master")
                print(f"Type: {type(scrip_master)}")

                # If it's a string (CSV format or URL)
                if isinstance(scrip_master, str):
                    import csv
                    import io
                    import requests

                    # Check if it's a URL
                    if scrip_master.startswith('http'):
                        print(f"\n📥 Downloading CSV from: {scrip_master}")
                        response = requests.get(scrip_master)
                        if response.status_code == 200:
                            scrip_master = response.text
                            print("✅ CSV downloaded successfully")
                        else:
                            print(f"❌ Failed to download: {response.status_code}")
                            return

                    # Parse CSV
                    lines = scrip_master.strip().split('\n')
                    print(f"Total lines: {len(lines)}")

                    if lines:
                        print(f"\nHeader: {lines[0][:200]}")

                        # Parse as CSV
                        reader = csv.DictReader(io.StringIO(scrip_master))
                        all_contracts = list(reader)

                        print(f"Total contracts: {len(all_contracts)}")

                        # Show sample contract structure
                        if all_contracts:
                            print(f"\n📋 Sample contract fields: {all_contracts[0].keys()}")
                            print(f"📋 Sample contract: {all_contracts[0]}")

                        # Filter for NIFTY (search in all fields)
                        nifty_contracts = [s for s in all_contracts if any('NIFTY' in str(v) for v in s.values())]
                        print(f"\n✅ NIFTY contracts: {len(nifty_contracts)}")

                        # Filter for December 2025 (search for '02DEC' or '2DEC' in expiry or symbol)
                        dec_2_contracts = [s for s in nifty_contracts if any('02DEC' in str(v).upper() or '2DEC' in str(v).upper() for v in s.values())]
                        print(f"✅ Dec 2, 2025 contracts: {len(dec_2_contracts)}")

                        if dec_2_contracts:
                            print("\n✅ DEC 2, 2025 CONTRACTS FOUND:")
                            print("=" * 80)
                            for i, contract in enumerate(dec_2_contracts[:50]):
                                # Print all fields to see structure
                                if i == 0:
                                    print(f"Fields: {contract.keys()}\n")

                                # Get symbol from various possible field names
                                symbol = (contract.get('pTrdSymbol') or
                                        contract.get('pSymbol') or
                                        contract.get('Trading Symbol') or
                                        contract.get('Symbol') or 'N/A')

                                expiry = (contract.get('lExpiryDate') or
                                        contract.get('Expiry Date') or
                                        contract.get('Expiry') or 'N/A')

                                print(f"[{i+1}] {symbol} - Expiry: {expiry}")

                                # Look for Dec 2, 2025 specifically
                                if any(x in str(symbol) or x in str(expiry) for x in ['02DEC2025', '02-DEC-2025', '2025-12-02', 'DEC 02 2025']):
                                    print(f"    ⭐ MATCHES DEC 2, 2025!")

                # If it's a list
                elif isinstance(scrip_master, list):
                    print(f"Total contracts: {len(scrip_master)}")

                    # Filter for NIFTY
                    nifty_contracts = [s for s in scrip_master if 'NIFTY' in str(s.get('pSymbol', '') or s.get('pTrdSymbol', ''))]
                    print(f"NIFTY contracts: {len(nifty_contracts)}")

                    # Filter for December 2025
                    dec_2025 = [s for s in nifty_contracts if 'DEC' in str(s.get('pTrdSymbol', '')) or 'DEC' in str(s.get('pSymbol', ''))]
                    print(f"December contracts: {len(dec_2025)}")

                    # Look for specific date patterns (02, 2, or 2nd)
                    target_date_contracts = []
                    for s in dec_2025:
                        symbol = str(s.get('pTrdSymbol', '')) or str(s.get('pSymbol', ''))
                        # Check for various date patterns
                        if any(pattern in symbol for pattern in ['02DEC', '2DEC', 'DEC2', 'DEC02']):
                            target_date_contracts.append(s)

                    print(f"Dec 2 contracts found: {len(target_date_contracts)}")

                    if target_date_contracts:
                        print("\n✅ FOUND DEC 2, 2025 CONTRACTS!")
                        print("=" * 80)
                        for i, contract in enumerate(target_date_contracts[:20]):
                            symbol = contract.get('pTrdSymbol', contract.get('pSymbol', 'N/A'))
                            exchange = contract.get('pExchSeg', 'N/A')
                            lot_size = contract.get('lLotSize', 'N/A')
                            expiry = contract.get('lExpiryDate', 'N/A')

                            print(f"\n[{i+1}] Symbol: {symbol}")
                            print(f"    Exchange: {exchange}")
                            print(f"    Lot Size: {lot_size}")
                            print(f"    Expiry: {expiry}")

                            # Print all keys to see structure
                            if i == 0:
                                print(f"\n    Available fields: {contract.keys()}")
                    else:
                        print("\n❌ No Dec 2 contracts found. Showing sample December contracts:")
                        print("=" * 80)
                        for i, contract in enumerate(dec_2025[:10]):
                            symbol = contract.get('pTrdSymbol', contract.get('pSymbol', 'N/A'))
                            print(f"  [{i+1}] {symbol}")

                # If it's a dict
                elif isinstance(scrip_master, dict):
                    print(f"Keys: {scrip_master.keys()}")

                    # Check if data is nested
                    if 'data' in scrip_master:
                        data = scrip_master['data']
                        print(f"Data type: {type(data)}")
                        if isinstance(data, list):
                            print(f"Data length: {len(data)}")
                            # Show first few items
                            for i, item in enumerate(data[:5]):
                                print(f"\n[{i+1}] {json.dumps(item, indent=2, default=str)[:500]}")
            else:
                print("❌ No scrip master data returned")

        except AttributeError:
            print("❌ scrip_master() method not available on client")
            print("\nTrying alternative: Searching for specific contract...")

            # Try searching directly
            result = client.search_scrip(
                exchange_segment='nse_fo',
                symbol='NIFTY',
                expiry='',  # Empty to get all
                option_type='',
                strike_price=''
            )

            print(f"Search result type: {type(result)}")
            print(f"Search result: {json.dumps(result, indent=2, default=str)[:1000]}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    search_neo_master()
