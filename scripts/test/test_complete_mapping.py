"""
Complete end-to-end test of Breeze → Neo symbol mapping
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.kotak_neo import map_breeze_symbol_to_neo, get_kotak_neo_client
from datetime import datetime

def test_symbol_mapping():
    """Test complete symbol mapping flow"""

    try:
        print("="*80)
        print("COMPLETE SYMBOL MAPPING TEST")
        print("="*80)

        # Get Neo client
        client = get_kotak_neo_client()
        print("\n✅ Neo client authenticated\n")

        # Test cases: Breeze symbols that need to be mapped to Neo
        test_cases = [
            {
                'breeze_symbol': 'NIFTY02DEC26850CE',
                'expiry_date': datetime(2025, 12, 2),
                'description': 'Dec 2, 2025 - Call 26850'
            },
            {
                'breeze_symbol': 'NIFTY02DEC26800CE',
                'expiry_date': datetime(2025, 12, 2),
                'description': 'Dec 2, 2025 - Call 26800'
            },
            {
                'breeze_symbol': 'NIFTY02DEC26900PE',
                'expiry_date': datetime(2025, 12, 2),
                'description': 'Dec 2, 2025 - Put 26900'
            },
            {
                'breeze_symbol': 'NIFTY02DEC27000PE',
                'expiry_date': datetime(2025, 12, 2),
                'description': 'Dec 2, 2025 - Put 27000'
            },
        ]

        print("Testing symbol mappings:")
        print("="*80)

        for i, test in enumerate(test_cases, 1):
            print(f"\n[Test {i}] {test['description']}")
            print(f"  Breeze Symbol: {test['breeze_symbol']}")
            print(f"  Expiry Date: {test['expiry_date'].strftime('%d %b %Y')}")
            print()

            # Map symbol
            result = map_breeze_symbol_to_neo(
                breeze_symbol=test['breeze_symbol'],
                expiry_date=test['expiry_date'],
                client=client
            )

            if result['success']:
                print(f"  ✅ SUCCESS!")
                print(f"  Neo Symbol: {result['neo_symbol']}")
                print(f"  Lot Size: {result['lot_size']}")
                print(f"  Token: {result['token']}")
            else:
                print(f"  ❌ FAILED!")
                print(f"  Error: {result['error']}")
                if result.get('neo_symbol'):
                    print(f"  Attempted Symbol: {result['neo_symbol']}")

        print("\n" + "="*80)
        print("TEST COMPLETE")
        print("="*80)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_symbol_mapping()
