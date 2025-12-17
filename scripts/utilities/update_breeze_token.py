#!/usr/bin/env python3
"""
Update Breeze Session Token

This script helps update the Breeze (ICICI Direct) session token in the database.
The session token needs to be obtained manually from the ICICI Direct portal.

Steps to get session token:
1. Login to https://api.icicidirect.com/apiuser/login
2. After successful login, you'll see a session token
3. Copy the session token and run this script with it
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/Users/anupammangudkar/PyProjects/mCube-ai')
os.environ['DJANGO_SETTINGS_MODULE'] = 'mcube_ai.settings'
django.setup()

from apps.core.models import CredentialStore
from django.utils import timezone
from apps.brokers.integrations.breeze import get_breeze_client


def update_session_token(new_token=None):
    """Update Breeze session token in database"""

    if not new_token:
        print("\n" + "="*80)
        print("📝 BREEZE SESSION TOKEN UPDATE")
        print("="*80)
        print("\nTo get a new session token:")
        print("1. Go to: https://api.icicidirect.com/apiuser/login")
        print("2. Login with your ICICI Direct credentials")
        print("3. After login, you'll see a session token on the page")
        print("4. Copy that token and paste it below\n")

        new_token = input("Enter new session token: ").strip()

    if not new_token:
        print("❌ No token provided. Exiting.")
        return False

    # Update in database
    try:
        creds = CredentialStore.objects.filter(service='breeze').first()
        if not creds:
            print("❌ Breeze credentials not found in database")
            print("   Run: python manage.py setup_credentials --setup-breeze")
            return False

        old_token = creds.session_token
        creds.session_token = new_token
        creds.last_session_update = timezone.now()
        creds.save()

        print(f"\n✅ Session token updated successfully!")
        print(f"   Old token: {old_token[:20]}..." if old_token else "   Old token: None")
        print(f"   New token: {new_token[:20]}...")
        print(f"   Updated at: {creds.last_session_update}")

        # Test the new token
        print("\n🔍 Testing new session token...")
        try:
            breeze = get_breeze_client()

            # Try to get funds to verify token works
            funds = breeze.get_funds()
            if funds and funds.get('Status') == 200:
                print("✅ Token verified! Successfully connected to Breeze API")

                # Show account info
                success = funds.get('Success', {})
                if success:
                    print(f"\n📊 Account Summary:")
                    print(f"   Available Cash: ₹{success.get('block_amount', 0):,.2f}")
                    print(f"   Net Available Funds: ₹{success.get('net_available_funds', 0):,.2f}")
                return True
            else:
                print(f"⚠️ Token accepted but API returned: {funds.get('Error', 'Unknown error')}")
                return True

        except Exception as e:
            error_msg = str(e)
            if 'session key is expired' in error_msg.lower():
                print("❌ Token is expired or invalid. Please get a fresh token from ICICI portal.")
            elif 'resource not available' in error_msg.lower():
                print("❌ Token doesn't match your API key or is invalid.")
            else:
                print(f"⚠️ Token saved but verification failed: {error_msg}")
                print("   The token might still be valid. Try running your tests.")
            return False

    except Exception as e:
        print(f"❌ Error updating token: {e}")
        return False


def main():
    """Main function"""
    if len(sys.argv) > 1:
        # Token provided as command line argument
        token = sys.argv[1]
        success = update_session_token(token)
    else:
        # Interactive mode
        success = update_session_token()

    if success:
        print("\n🎉 You can now run your validation tests!")
        print("   python test_complete_validation.py")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()