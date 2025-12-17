"""
Final test - get exact Neo symbol for Dec 2, 2025
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client
import json

def get_neo_symbol():
    try:
        client = get_kotak_neo_client()
        print("✅ Neo authenticated\n")

        # Search for Dec 2, 2025 weekly NIFTY options
        result = client.search_scrip(
            exchange_segment='nse_fo',
            symbol='NIFTY',
            expiry='02-DEC-2025',
            option_type='CE',
            strike_price='27100'
        )

        print("Raw Neo API response:")
        print("=" * 80)
        print(json.dumps(result, indent=2, default=str))
        print("=" * 80)

        print("\nType of result:", type(result))

        # Try to parse it
        if isinstance(result, list):
            print(f"\n✅ Result is a list with {len(result)} items")
            for i, item in enumerate(result[:5]):
                print(f"\n[{i+1}] {item}")
        elif isinstance(result, dict):
            print(f"\n✅ Result is a dict")
            print("Keys:", result.keys())

            # Check if data is in a specific key
            if 'data' in result:
                data = result['data']
                print(f"\nData type: {type(data)}")
                if isinstance(data, list):
                    print(f"Data has {len(data)} items")
                    for i, item in enumerate(data[:5]):
                        print(f"\n[{i+1}] {json.dumps(item, indent=2, default=str)}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    get_neo_symbol()
