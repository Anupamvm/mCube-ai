"""
Credential Management Command

This command helps set up and manage API credentials for brokers and data providers.

Usage:
    python manage.py setup_credentials --list                          # List all credentials
    python manage.py setup_credentials --setup-breeze                  # Setup ICICI Breeze
    python manage.py setup_credentials --setup-kotakneo                # Setup Kotak Neo
    python manage.py setup_credentials --setup-trendlyne               # Setup Trendlyne
    python manage.py setup_credentials --delete <service>              # Delete credentials
    python manage.py setup_credentials --status                        # Check all credentials status
    python manage.py setup_credentials --test-breeze                   # Test Breeze connection
    python manage.py setup_credentials --test-kotakneo                 # Test Kotak Neo connection
"""

from django.core.management.base import BaseCommand, CommandError
from apps.core.models import CredentialStore
import getpass
import sys


class Command(BaseCommand):
    help = 'Setup and manage API credentials for brokers and data providers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all stored credentials (without sensitive data)'
        )

        parser.add_argument(
            '--setup-breeze',
            action='store_true',
            help='Setup ICICI Breeze credentials'
        )

        parser.add_argument(
            '--setup-kotakneo',
            action='store_true',
            help='Setup Kotak Neo credentials'
        )

        parser.add_argument(
            '--setup-trendlyne',
            action='store_true',
            help='Setup Trendlyne credentials'
        )

        parser.add_argument(
            '--setup-gnewsio',
            action='store_true',
            help='Setup GNews.io credentials'
        )

        parser.add_argument(
            '--delete',
            type=str,
            metavar='SERVICE',
            help='Delete credentials for a service (breeze, kotakneo, trendlyne, gnewsio)'
        )

        parser.add_argument(
            '--status',
            action='store_true',
            help='Check status of all credentials'
        )

        parser.add_argument(
            '--test-breeze',
            action='store_true',
            help='Test ICICI Breeze connection'
        )

        parser.add_argument(
            '--test-kotakneo',
            action='store_true',
            help='Test Kotak Neo connection'
        )

    def handle(self, *args, **options):
        if options['list']:
            self.list_credentials()
        elif options['setup_breeze']:
            self.setup_breeze()
        elif options['setup_kotakneo']:
            self.setup_kotakneo()
        elif options['setup_trendlyne']:
            self.setup_trendlyne()
        elif options['setup_gnewsio']:
            self.setup_gnewsio()
        elif options['delete']:
            self.delete_credentials(options['delete'])
        elif options['status']:
            self.check_status()
        elif options['test_breeze']:
            self.test_breeze()
        elif options['test_kotakneo']:
            self.test_kotakneo()
        else:
            self.stdout.write(self.style.WARNING('No action specified. Use --help for options.'))

    def list_credentials(self):
        """List all stored credentials"""
        creds = CredentialStore.objects.all()

        if not creds.exists():
            self.stdout.write(self.style.WARNING('No credentials found.'))
            return

        self.stdout.write(self.style.SUCCESS('\n=== Stored Credentials ===\n'))
        for cred in creds:
            self.stdout.write(f"Service: {self.style.SUCCESS(cred.get_service_display())}")
            self.stdout.write(f"  Name: {cred.name}")
            self.stdout.write(f"  API Key: {cred.api_key[:8] + '...' if cred.api_key else 'Not set'}")
            self.stdout.write(f"  Username: {cred.username if cred.username else 'Not set'}")
            self.stdout.write(f"  Session Token: {'Set' if cred.session_token else 'Not set'}")
            if cred.service == 'kotakneo':
                self.stdout.write(f"  UCC: {cred.ucc or 'Not set'}")
                self.stdout.write(f"  Mobile: {cred.mobile_number or 'Not set'}")
                self.stdout.write(f"  TOTP Secret: {'Set' if cred.totp_secret else 'Not set'}")
                self.stdout.write(f"  MPIN: {'Set' if cred.neo_password else 'Not set'}")
            self.stdout.write(f"  Created: {cred.created_at}")
            self.stdout.write(f"  Last Updated: {cred.last_session_update or 'Never'}")
            self.stdout.write('')

    def setup_breeze(self):
        """Setup ICICI Breeze credentials"""
        self.stdout.write(self.style.SUCCESS('\n=== ICICI Breeze Setup ===\n'))

        name = input("Credential name (default: default): ").strip() or "default"

        self.stdout.write('\nYou need:')
        self.stdout.write('1. API Key (from Breeze console)')
        self.stdout.write('2. API Secret (from Breeze console)')
        self.stdout.write('3. ICICI Direct User ID (for auto-login)')
        self.stdout.write('4. ICICI Direct Password (for auto-login)')
        self.stdout.write('5. Session Token (optional, can use auto-login instead)')

        api_key = input("\nEnter API Key: ").strip()
        if not api_key:
            raise CommandError("API Key is required")

        api_secret = input("Enter API Secret: ").strip()
        if not api_secret:
            raise CommandError("API Secret is required")

        self.stdout.write(self.style.WARNING('\n-- Auto-Login Credentials (for automated token refresh) --'))
        username = input("Enter ICICI Direct User ID (optional, for auto-login): ").strip()
        password = ""
        if username:
            password = getpass.getpass("Enter ICICI Direct Password: ").strip()

        session_token = input("\nEnter Session Token (optional, will prompt on first use): ").strip()

        # Create or update credentials
        cred, created = CredentialStore.objects.update_or_create(
            service='breeze',
            name=name,
            defaults={
                'api_key': api_key,
                'api_secret': api_secret,
                'username': username or None,
                'password': password or None,
                'session_token': session_token or None,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Breeze credentials created for "{name}"'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Breeze credentials updated for "{name}"'))

        if username and password:
            self.stdout.write(self.style.SUCCESS('✅ Auto-login credentials saved'))
            self.stdout.write('   You can now use: python manage.py breeze_auto_login')
        else:
            self.stdout.write(self.style.WARNING('⚠️  Auto-login not configured (no username/password)'))

    def setup_kotakneo(self):
        """Setup Kotak Neo v2 credentials (TOTP + MPIN auth)"""
        self.stdout.write(self.style.SUCCESS('\n=== Kotak Neo v2 Setup ===\n'))

        name = input("Credential name (default: default): ").strip() or "default"

        self.stdout.write('\nYou need:')
        self.stdout.write('1. Consumer Key (from Kotak Neo API portal)')
        self.stdout.write('2. UCC - Unique Client Code (from profile section)')
        self.stdout.write('3. Mobile Number (registered mobile)')
        self.stdout.write('4. TOTP Secret (from TOTP registration on Kotak Neo app)')
        self.stdout.write('5. MPIN (6-digit trading pin)')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Note: Consumer Secret, PAN, and Password are NOT needed for v2.'))

        api_key = input("\nEnter Consumer Key: ").strip()
        if not api_key:
            raise CommandError("Consumer Key is required")

        ucc = input("Enter UCC (Unique Client Code): ").strip()
        if not ucc:
            raise CommandError("UCC is required")

        mobile_number = input("Enter Mobile Number: ").strip()
        if not mobile_number:
            raise CommandError("Mobile Number is required")

        totp_secret = getpass.getpass("Enter TOTP Secret Key: ").strip()
        if not totp_secret:
            raise CommandError("TOTP Secret is required for automated login")

        neo_password = getpass.getpass("Enter MPIN (6-digit): ").strip()
        if not neo_password:
            raise CommandError("MPIN is required")

        # Create or update credentials
        cred, created = CredentialStore.objects.update_or_create(
            service='kotakneo',
            name=name,
            defaults={
                'api_key': api_key,
                'ucc': ucc,
                'mobile_number': mobile_number,
                'username': mobile_number,  # Legacy field for compat
                'totp_secret': totp_secret,
                'neo_password': neo_password,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Kotak Neo credentials created for "{name}"'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Kotak Neo credentials updated for "{name}"'))

        # Verify TOTP secret works
        try:
            import pyotp
            totp = pyotp.TOTP(totp_secret)
            code = totp.now()
            self.stdout.write(self.style.SUCCESS(f'✅ TOTP secret verified (current code: {code})'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'⚠️  TOTP secret may be invalid: {e}'))

    def setup_trendlyne(self):
        """Setup Trendlyne credentials"""
        self.stdout.write(self.style.SUCCESS('\n=== Trendlyne Setup ===\n'))

        name = input("Credential name (default: default): ").strip() or "default"

        self.stdout.write('\nYou need:')
        self.stdout.write('1. Email/Username')
        self.stdout.write('2. Password')

        username = input("\nEnter Email/Username: ").strip()
        if not username:
            raise CommandError("Email/Username is required")

        password = getpass.getpass("Enter Password: ").strip()
        if not password:
            raise CommandError("Password is required")

        # Create or update credentials
        cred, created = CredentialStore.objects.update_or_create(
            service='trendlyne',
            name=name,
            defaults={
                'username': username,
                'password': password,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Trendlyne credentials created for "{name}"'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Trendlyne credentials updated for "{name}"'))

    def setup_gnewsio(self):
        """Setup GNews.io credentials"""
        self.stdout.write(self.style.SUCCESS('\n=== GNews.io Setup ===\n'))

        name = input("Credential name (default: default): ").strip() or "default"

        self.stdout.write('\nYou need:')
        self.stdout.write('1. API Key (from gnews.io dashboard)')
        self.stdout.write('2. Email/Username (optional, for reference)')
        self.stdout.write('3. Password (optional, for reference)')

        api_key = input("\nEnter API Key: ").strip()
        if not api_key:
            raise CommandError("API Key is required")

        username = input("Enter Email/Username (optional): ").strip()
        password = getpass.getpass("Enter Password (optional): ").strip() if username else ""

        # Create or update credentials
        cred, created = CredentialStore.objects.update_or_create(
            service='gnewsio',
            name=name,
            defaults={
                'api_key': api_key,
                'username': username or None,
                'password': password or None,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'\n✅ GNews.io credentials created for "{name}"'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ GNews.io credentials updated for "{name}"'))

    def delete_credentials(self, service):
        """Delete credentials for a service"""
        try:
            CredentialStore.objects.filter(service=service).delete()
            self.stdout.write(self.style.SUCCESS(f'✅ Credentials for {service} deleted'))
        except Exception as e:
            raise CommandError(f'Error deleting credentials: {e}')

    def check_status(self):
        """Check status of all credentials"""
        self.stdout.write(self.style.SUCCESS('\n=== Credentials Status ===\n'))

        services = ['breeze', 'kotakneo', 'trendlyne', 'gnewsio']

        for service in services:
            cred = CredentialStore.objects.filter(service=service).first()
            if cred:
                status = self.style.SUCCESS('✅ Set')
                token_status = 'Has token' if cred.session_token else 'No token'
                self.stdout.write(f"{service.upper():15} {status}  ({token_status})")

                # Show v2 field status for Kotak Neo
                if service == 'kotakneo':
                    ucc_ok = '✅' if cred.ucc else '❌'
                    totp_ok = '✅' if cred.totp_secret else '❌'
                    mobile_ok = '✅' if cred.mobile_number else '❌'
                    mpin_ok = '✅' if cred.neo_password else '❌'
                    key_ok = '✅' if cred.api_key else '❌'
                    self.stdout.write(f"{'':15}   v2 fields: Key{key_ok} UCC{ucc_ok} Mobile{mobile_ok} TOTP{totp_ok} MPIN{mpin_ok}")
            else:
                status = self.style.WARNING('⚠️  Not set')
                self.stdout.write(f"{service.upper():15} {status}")

    def test_breeze(self):
        """Test Breeze connection"""
        self.stdout.write(self.style.SUCCESS('\n=== Testing Breeze Connection ===\n'))

        try:
            cred = CredentialStore.objects.filter(service='breeze').first()
            if not cred:
                raise CommandError('Breeze credentials not found. Run --setup-breeze first')

            from apps.brokers.integrations.breeze import BreezeAPIClient

            api = BreezeAPI()

            self.stdout.write('Attempting login...')
            if api.login():
                self.stdout.write(self.style.SUCCESS('✅ Login successful'))

                margin = api.get_available_margin()
                self.stdout.write(f'✅ Available Margin: ₹{margin:,.2f}')

                positions = api.get_positions()
                self.stdout.write(f'✅ Open Positions: {len(positions)}')
            else:
                self.stdout.write(self.style.ERROR('❌ Login failed'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))

    def test_kotakneo(self):
        """Test Kotak Neo connection"""
        self.stdout.write(self.style.SUCCESS('\n=== Testing Kotak Neo Connection ===\n'))

        try:
            cred = CredentialStore.objects.filter(service='kotakneo').first()
            if not cred:
                raise CommandError('Kotak Neo credentials not found. Run --setup-kotakneo first')

            from tools.neo import NeoAPI

            api = NeoAPI()

            self.stdout.write('Attempting login...')
            if api.login():
                self.stdout.write(self.style.SUCCESS('✅ Login successful'))

                margin = api.get_available_margin()
                self.stdout.write(f'✅ Available Margin: ₹{margin:,.2f}')

                positions = api.get_positions()
                self.stdout.write(f'✅ Open Positions: {len(positions)}')
            else:
                self.stdout.write(self.style.ERROR('❌ Login failed'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
