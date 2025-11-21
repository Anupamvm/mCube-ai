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
            '--delete',
            type=str,
            metavar='SERVICE',
            help='Delete credentials for a service (breeze, kotakneo, trendlyne)'
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
        self.stdout.write('3. Session Token (from login)')

        api_key = input("\nEnter API Key: ").strip()
        if not api_key:
            raise CommandError("API Key is required")

        api_secret = input("Enter API Secret: ").strip()
        if not api_secret:
            raise CommandError("API Secret is required")

        session_token = input("Enter Session Token (optional, will prompt on first use): ").strip()

        # Create or update credentials
        cred, created = CredentialStore.objects.update_or_create(
            service='breeze',
            name=name,
            defaults={
                'api_key': api_key,
                'api_secret': api_secret,
                'session_token': session_token or None,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Breeze credentials created for "{name}"'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Breeze credentials updated for "{name}"'))

    def setup_kotakneo(self):
        """Setup Kotak Neo credentials"""
        self.stdout.write(self.style.SUCCESS('\n=== Kotak Neo Setup ===\n'))

        name = input("Credential name (default: default): ").strip() or "default"

        self.stdout.write('\nYou need:')
        self.stdout.write('1. Consumer Key (from Kotak console)')
        self.stdout.write('2. Consumer Secret (from Kotak console)')
        self.stdout.write('3. Mobile Number (login mobile)')
        self.stdout.write('4. Password (login password)')
        self.stdout.write('5. MPIN (trading MPIN)')
        self.stdout.write('6. PAN (optional)')

        api_key = input("\nEnter Consumer Key: ").strip()
        if not api_key:
            raise CommandError("Consumer Key is required")

        api_secret = input("Enter Consumer Secret: ").strip()
        if not api_secret:
            raise CommandError("Consumer Secret is required")

        username = input("Enter Mobile Number: ").strip()
        if not username:
            raise CommandError("Mobile Number is required")

        password = getpass.getpass("Enter Password: ").strip()
        if not password:
            raise CommandError("Password is required")

        neo_password = getpass.getpass("Enter MPIN: ").strip()
        if not neo_password:
            raise CommandError("MPIN is required")

        pan = input("Enter PAN (optional): ").strip()

        # Create or update credentials
        cred, created = CredentialStore.objects.update_or_create(
            service='kotakneo',
            name=name,
            defaults={
                'api_key': api_key,
                'api_secret': api_secret,
                'username': username,
                'password': password,
                'neo_password': neo_password,
                'pan': pan or None,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Kotak Neo credentials created for "{name}"'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Kotak Neo credentials updated for "{name}"'))

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

        services = ['breeze', 'kotakneo', 'trendlyne']

        for service in services:
            cred = CredentialStore.objects.filter(service=service).first()
            if cred:
                status = self.style.SUCCESS('✅ Set')
                token_status = 'Has token' if cred.session_token else 'No token'
                self.stdout.write(f"{service.upper():15} {status}  ({token_status})")
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
