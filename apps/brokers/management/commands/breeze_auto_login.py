"""
Breeze Auto Login Management Command

Automates the ICICI Breeze login process.
First validates existing token - only opens browser if token is invalid.

Usage:
    python manage.py breeze_auto_login              # Validate first, browser only if needed
    python manage.py breeze_auto_login --force      # Skip validation, force browser login
    python manage.py breeze_auto_login --timeout=600  # Custom timeout (seconds)

Requirements:
    - Chrome browser installed
    - Selenium (pip install selenium)
    - Breeze credentials configured with username/password
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Automated Breeze login - validates token first, opens browser only if needed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip token validation and force browser login'
        )
        parser.add_argument(
            '--headless',
            action='store_true',
            help='Run browser in headless mode (not recommended, OTP needs user input)'
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=300,
            help='Timeout in seconds to wait for OTP entry (default: 300 = 5 minutes)'
        )
        parser.add_argument(
            '--task-name',
            type=str,
            default='manual CLI login',
            help='Task description shown in Telegram OTP request (default: "manual CLI login")'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== Breeze Auto Login ===\n'))

        force = options['force']
        headless = options['headless']
        timeout = options['timeout']
        task_name = options['task_name']

        if headless:
            self.stdout.write(self.style.WARNING(
                'WARNING: Headless mode is not recommended as you need to enter OTP manually.'
            ))

        # Check if credentials are configured
        from apps.core.models import CredentialStore
        creds = CredentialStore.objects.filter(service='breeze').first()

        if not creds:
            raise CommandError(
                'Breeze credentials not found. Run: python manage.py setup_credentials --setup-breeze'
            )

        if not creds.api_key:
            raise CommandError('Breeze API key not configured')

        self.stdout.write(f'API Key: {creds.api_key[:10]}...')
        if creds.username:
            self.stdout.write(f'Username: {creds.username}')
        self.stdout.write(f'Timeout: {timeout} seconds')
        self.stdout.write(f'Force browser: {force}')
        self.stdout.write('')

        # Run auto-login
        try:
            from apps.brokers.services.breeze_auto_login import auto_login_breeze

            if not force:
                self.stdout.write('Step 1: Validating existing session token...')
            else:
                self.stdout.write('Skipping validation (--force flag used)')

            success, message = auto_login_breeze(
                headless=headless,
                timeout=timeout,
                skip_validation=force,
                task_name=task_name
            )

            if success:
                if 'Existing token is valid' in message:
                    self.stdout.write(self.style.SUCCESS(f'\n✅ {message}'))
                    self.stdout.write(self.style.SUCCESS('No browser login needed - token is already valid!'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'\n✅ {message}'))
                    self.stdout.write(self.style.SUCCESS('New session token has been saved to the database.'))
            else:
                self.stdout.write(self.style.ERROR(f'\n❌ {message}'))
                raise CommandError('Auto-login failed')

        except ImportError as e:
            raise CommandError(
                f'Selenium not installed: {e}\n'
                'Install with: pip install selenium'
            )
        except Exception as e:
            raise CommandError(f'Error during auto-login: {e}')
