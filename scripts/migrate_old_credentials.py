#!/usr/bin/env python
"""
Migrate Credentials from Old mCube3 Project

This script migrates API credentials from the old mCube3 project database
to the new mCube-ai system. It handles the schema differences and ensures
data integrity during migration.

Usage:
    # From within the new project
    python manage.py shell < scripts/migrate_old_credentials.py

    # Or directly
    python scripts/migrate_old_credentials.py
"""

import os
import sys
import django
from pathlib import Path

# Setup Django for new project
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import CredentialStore
from django.utils import timezone


def migrate_from_old_project(old_db_path):
    """
    Migrate credentials from old mCube3 project database.

    This function:
    1. Connects to old SQLite database
    2. Reads CredentialStore entries
    3. Maps old schema to new schema
    4. Creates/updates credentials in new system

    Args:
        old_db_path: Path to old mCube3 project's database
    """

    import sqlite3

    print("=" * 70)
    print("Migrating Credentials from Old mCube3 Project")
    print("=" * 70)

    if not os.path.exists(old_db_path):
        print(f"❌ Old database not found: {old_db_path}")
        return False

    print(f"\nConnecting to old database: {old_db_path}")

    try:
        old_conn = sqlite3.connect(old_db_path)
        old_cursor = old_conn.cursor()

        # Query old credentials table
        old_cursor.execute("""
            SELECT
                name, service, api_key, api_secret, session_token,
                username, password, pan, neo_password, sid,
                created_at, last_session_update
            FROM tools_credentialstore
            ORDER BY service, name
        """)

        old_credentials = old_cursor.fetchall()
        old_conn.close()

        if not old_credentials:
            print("⚠️  No credentials found in old database")
            return False

        print(f"✓ Found {len(old_credentials)} credential(s) in old database\n")

        # Column mapping
        columns = [
            'name', 'service', 'api_key', 'api_secret', 'session_token',
            'username', 'password', 'pan', 'neo_password', 'sid',
            'created_at', 'last_session_update'
        ]

        # Migrate each credential
        migrated_count = 0
        for row in old_credentials:
            cred_data = dict(zip(columns, row))

            print(f"Migrating: {cred_data['service'].upper()}")
            print(f"  Name: {cred_data['name']}")

            # Update or create
            cred, created = CredentialStore.objects.update_or_create(
                service=cred_data['service'],
                name=cred_data['name'],
                defaults={
                    'api_key': cred_data.get('api_key'),
                    'api_secret': cred_data.get('api_secret'),
                    'session_token': cred_data.get('session_token'),
                    'username': cred_data.get('username'),
                    'password': cred_data.get('password'),
                    'pan': cred_data.get('pan'),
                    'neo_password': cred_data.get('neo_password'),
                    'sid': cred_data.get('sid'),
                }
            )

            status = "✓ Created" if created else "✓ Updated"
            print(f"  {status}")
            migrated_count += 1

        print(f"\n{'=' * 70}")
        print(f"✅ Migration complete! {migrated_count} credential(s) migrated")
        print(f"{'=' * 70}")

        return True

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_migration():
    """Verify that migration was successful"""

    print(f"\n{'=' * 70}")
    print("Verifying Migration")
    print(f"{'=' * 70}\n")

    credentials = CredentialStore.objects.all()

    if not credentials.exists():
        print("⚠️  No credentials found in new database")
        return False

    print(f"✓ Found {credentials.count()} credential(s) in new database:\n")

    for cred in credentials:
        service_display = cred.get_service_display()
        print(f"{service_display}:")
        print(f"  Name: {cred.name}")
        if cred.api_key:
            print(f"  API Key: {cred.api_key[:12]}...")
        if cred.username:
            print(f"  Username: {cred.username}")
        if cred.pan:
            print(f"  PAN: {cred.pan}")
        print(f"  Created: {cred.created_at}")
        if cred.last_session_update:
            print(f"  Last Updated: {cred.last_session_update}")
        print()

    return True


def main():
    """Main migration flow"""

    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + "  Migrate Credentials from Old mCube3 Project".center(68) + "║")
    print("╚" + "=" * 68 + "╝\n")

    # Default path to old database
    old_project_path = Path(
        "/Users/anupammangudkar/Projects/mCube-ai/old_mCubeProject"
    )

    old_db_path = old_project_path / "mCube3/mCube3/db.sqlite3"

    print("Old project database paths to check:")
    print(f"1. {old_db_path}")

    # Ask user if they want to provide custom path
    print("\nOptions:")
    print("1. Use default path")
    print("2. Provide custom path")
    print("3. Cancel")

    choice = input("\nSelect option (1-3): ").strip()

    if choice == '3':
        print("Migration cancelled")
        return

    if choice == '2':
        old_db_path = input("Enter path to old db.sqlite3: ").strip()

    # Perform migration
    if migrate_from_old_project(old_db_path):
        # Verify
        if verify_migration():
            print(f"\n{'=' * 70}")
            print("✅ Migration successful!")
            print(f"{'=' * 70}")
            print("\nNext steps:")
            print("1. Verify all credentials are correct")
            print("2. Test connections: python manage.py setup_credentials --test-breeze")
            print("3. Run: python manage.py setup_credentials --status")
            print()
            return True

    print(f"\n{'=' * 70}")
    print("❌ Migration failed or incomplete")
    print(f"{'=' * 70}\n")
    return False


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
