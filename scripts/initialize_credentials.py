#!/usr/bin/env python
"""
Credential Initialization Script

This script demonstrates how to programmatically initialize API credentials
in the CredentialStore model from the old mCube3 project.

It can be run from the Django shell:
    python manage.py shell < scripts/initialize_credentials.py

Or directly if configured with Django:
    python scripts/initialize_credentials.py

Sample Data from Old mCube3 Project:
- Uses the same field mappings as the old project
- Directly compatible with both BreezeAPI and NeoAPI wrappers
"""

import os
import django
from pathlib import Path

# Setup Django
if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

from apps.core.models import CredentialStore
from django.utils import timezone


def initialize_breeze_credentials():
    """
    Initialize ICICI Breeze credentials from old project format.

    Old mCube3 format:
    - api_key: Breeze API Key
    - api_secret: Breeze API Secret
    - session_token: Trading session token
    - last_session_update: When token was last obtained
    """

    print("=" * 60)
    print("Initializing ICICI Breeze Credentials")
    print("=" * 60)

    # Check if already exists
    existing = CredentialStore.objects.filter(service='breeze').first()

    breeze_config = {
        'name': 'default',
        'api_key': 'YOUR_BREEZE_API_KEY_HERE',  # Replace with actual key
        'api_secret': 'YOUR_BREEZE_API_SECRET_HERE',  # Replace with actual secret
        'session_token': None,  # Will be set on first login
        'last_session_update': None,
    }

    if existing:
        print(f"✓ Breeze credentials already exist (created: {existing.created_at})")
        print(f"  Name: {existing.name}")
        print(f"  API Key: {existing.api_key[:8]}..." if existing.api_key else "  API Key: Not set")
        print(f"  Session Token: {'Set' if existing.session_token else 'Not set'}")

        # Optional: Update if needed
        update = input("\nUpdate Breeze credentials? (y/n): ").lower()
        if update == 'y':
            existing.api_key = breeze_config['api_key']
            existing.api_secret = breeze_config['api_secret']
            existing.save()
            print("✓ Breeze credentials updated")
    else:
        cred = CredentialStore.objects.create(
            service='breeze',
            **breeze_config
        )
        print(f"✓ Breeze credentials created")
        print(f"  Name: {cred.name}")
        print(f"  Service: {cred.get_service_display()}")
        print(f"  Created: {cred.created_at}")


def initialize_kotakneo_credentials():
    """
    Initialize Kotak Neo v2 credentials.

    v2 API format:
    - api_key: Consumer Key
    - ucc: Unique Client Code
    - mobile_number: Registered mobile number
    - totp_secret: TOTP secret from authenticator registration
    - neo_password: MPIN (6-digit trading pin)
    """

    print("\n" + "=" * 60)
    print("Initializing Kotak Neo v2 Credentials")
    print("=" * 60)

    existing = CredentialStore.objects.filter(service='kotakneo').first()

    kotakneo_config = {
        'name': 'default',
        'api_key': 'YOUR_CONSUMER_KEY_HERE',  # Replace with actual Consumer Key
        'ucc': 'YOUR_UCC_HERE',  # Replace with actual UCC
        'mobile_number': '9999999999',  # Replace with actual mobile number
        'username': '9999999999',  # Same as mobile_number (legacy compat)
        'totp_secret': 'YOUR_TOTP_SECRET_HERE',  # Replace with TOTP secret from registration
        'neo_password': 'YOUR_MPIN_HERE',  # Replace with actual 6-digit MPIN
    }

    if existing:
        print(f"✓ Kotak Neo credentials already exist (created: {existing.created_at})")
        print(f"  Name: {existing.name}")
        print(f"  Consumer Key: {existing.api_key[:8]}..." if existing.api_key else "  Consumer Key: Not set")
        print(f"  UCC: {existing.ucc if existing.ucc else 'Not set'}")
        print(f"  Mobile: {existing.mobile_number if existing.mobile_number else 'Not set'}")
        print(f"  TOTP Secret: {'Set' if existing.totp_secret else 'Not set'}")
        print(f"  MPIN: {'Set' if existing.neo_password else 'Not set'}")

        update = input("\nUpdate Kotak Neo credentials? (y/n): ").lower()
        if update == 'y':
            existing.api_key = kotakneo_config['api_key']
            existing.ucc = kotakneo_config['ucc']
            existing.mobile_number = kotakneo_config['mobile_number']
            existing.username = kotakneo_config['username']
            existing.totp_secret = kotakneo_config['totp_secret']
            existing.neo_password = kotakneo_config['neo_password']
            existing.save()
            print("✓ Kotak Neo credentials updated")
    else:
        cred = CredentialStore.objects.create(
            service='kotakneo',
            **kotakneo_config
        )
        print(f"✓ Kotak Neo credentials created")
        print(f"  Name: {cred.name}")
        print(f"  Service: {cred.get_service_display()}")
        print(f"  Created: {cred.created_at}")


def initialize_trendlyne_credentials():
    """
    Initialize Trendlyne credentials.

    Format:
    - username: Email/Username
    - password: Password
    """

    print("\n" + "=" * 60)
    print("Initializing Trendlyne Credentials")
    print("=" * 60)

    existing = CredentialStore.objects.filter(service='trendlyne').first()

    trendlyne_config = {
        'name': 'default',
        'username': 'your_email@example.com',  # Replace with actual email
        'password': 'YOUR_PASSWORD_HERE',  # Replace with actual password
    }

    if existing:
        print(f"✓ Trendlyne credentials already exist (created: {existing.created_at})")
        print(f"  Name: {existing.name}")
        print(f"  Email: {existing.username if existing.username else 'Not set'}")

        update = input("\nUpdate Trendlyne credentials? (y/n): ").lower()
        if update == 'y':
            existing.username = trendlyne_config['username']
            existing.password = trendlyne_config['password']
            existing.save()
            print("✓ Trendlyne credentials updated")
    else:
        cred = CredentialStore.objects.create(
            service='trendlyne',
            **trendlyne_config
        )
        print(f"✓ Trendlyne credentials created")
        print(f"  Name: {cred.name}")
        print(f"  Service: {cred.get_service_display()}")
        print(f"  Created: {cred.created_at}")


def show_summary():
    """Display summary of all credentials"""

    print("\n" + "=" * 60)
    print("Credentials Summary")
    print("=" * 60)

    credentials = CredentialStore.objects.all()

    if not credentials.exists():
        print("⚠️  No credentials found in database")
        return

    for cred in credentials:
        print(f"\n{cred.get_service_display()}:")
        print(f"  Name: {cred.name}")
        if cred.api_key:
            print(f"  API Key: {cred.api_key[:8]}{'...' if len(cred.api_key) > 8 else ''}")
        if cred.username:
            print(f"  Username: {cred.username}")
        if cred.session_token:
            print(f"  Session Token: Set")
        print(f"  Created: {cred.created_at}")
        if cred.last_session_update:
            print(f"  Last Updated: {cred.last_session_update}")


def main():
    """Main initialization flow"""

    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  mCube Trading System - Credential Initialization  ".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Show current status
    print("Current Status:")
    show_summary()

    print("\n" + "=" * 60)
    print("Select action:")
    print("1. Setup all credentials")
    print("2. Setup Breeze only")
    print("3. Setup Kotak Neo only")
    print("4. Setup Trendlyne only")
    print("5. Show credentials summary")
    print("6. Exit")
    print("=" * 60)

    choice = input("\nEnter choice (1-6): ").strip()

    if choice == '1':
        initialize_breeze_credentials()
        initialize_kotakneo_credentials()
        initialize_trendlyne_credentials()
    elif choice == '2':
        initialize_breeze_credentials()
    elif choice == '3':
        initialize_kotakneo_credentials()
    elif choice == '4':
        initialize_trendlyne_credentials()
    elif choice == '5':
        show_summary()
    elif choice == '6':
        print("Exiting...")
        return
    else:
        print("Invalid choice")
        return

    # Show final summary
    show_summary()

    print("\n" + "=" * 60)
    print("✅ Credential initialization complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Update placeholders with actual API credentials")
    print("2. Test connections: python manage.py setup_credentials --test-breeze")
    print("3. See CREDENTIAL_SETUP_GUIDE.md for detailed instructions")
    print()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
