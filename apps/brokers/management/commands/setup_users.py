"""
Management command to setup initial users and groups for the mCube Trading System.

SECURITY:
  Passwords are loaded from environment variables or auto-generated securely.
  Set the following environment variables to customize:
    - MCUBE_ADMIN_PASSWORD: Admin user password
    - MCUBE_TRADER_PASSWORD: Trader user password

Usage:
    python manage.py setup_users
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from apps.brokers.models import BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice
from apps.core.utils.password_utils import get_password_from_env


class Command(BaseCommand):
    help = 'Setup initial users and groups for mCube Trading System'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up users and groups...'))

        # Create groups
        admin_group, created = Group.objects.get_or_create(name='Admin')
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created Admin group'))
        else:
            self.stdout.write('  Admin group already exists')

        user_group, created = Group.objects.get_or_create(name='User')
        if created:
            self.stdout.write(self.style.SUCCESS('✓ Created User group'))
        else:
            self.stdout.write('  User group already exists')

        # Setup Admin permissions (full access)
        admin_permissions = Permission.objects.all()
        admin_group.permissions.set(admin_permissions)
        self.stdout.write(self.style.SUCCESS('✓ Admin group has full permissions'))

        # Setup User permissions (limited to viewing broker data)
        user_permissions = []

        # Add view permissions for broker models
        for model in [BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice]:
            content_type = ContentType.objects.get_for_model(model)
            view_perm = Permission.objects.get(
                codename=f'view_{model._meta.model_name}',
                content_type=content_type
            )
            user_permissions.append(view_perm)

        user_group.permissions.set(user_permissions)
        self.stdout.write(self.style.SUCCESS('✓ User group has view permissions'))

        # Create default admin user
        # SECURITY: Password loaded from MCUBE_ADMIN_PASSWORD env var or auto-generated
        admin_username = 'admin'
        admin_email = 'admin@mcube.ai'
        admin_password = get_password_from_env('MCUBE_ADMIN_PASSWORD')

        if not User.objects.filter(username=admin_username).exists():
            admin_user = User.objects.create_superuser(
                username=admin_username,
                email=admin_email,
                password=admin_password,
                first_name='Admin',
                last_name='User'
            )
            admin_user.groups.add(admin_group)
            self.stdout.write(self.style.SUCCESS(f'✓ Created admin user: {admin_username}'))

            # Show password only if auto-generated (not from env var)
            import os
            if 'MCUBE_ADMIN_PASSWORD' not in os.environ:
                self.stdout.write(self.style.WARNING(f'  Auto-generated Password: {admin_password}'))
                self.stdout.write(self.style.WARNING('  ⚠️  Save this password or set MCUBE_ADMIN_PASSWORD env var!'))
            else:
                self.stdout.write('  Password loaded from MCUBE_ADMIN_PASSWORD environment variable')
        else:
            self.stdout.write('  Admin user already exists')

        # Create default trader user
        # SECURITY: Password loaded from MCUBE_TRADER_PASSWORD env var or auto-generated
        trader_username = 'trader'
        trader_email = 'trader@mcube.ai'
        trader_password = get_password_from_env('MCUBE_TRADER_PASSWORD')

        if not User.objects.filter(username=trader_username).exists():
            trader_user = User.objects.create_user(
                username=trader_username,
                email=trader_email,
                password=trader_password,
                first_name='Trader',
                last_name='User'
            )
            trader_user.groups.add(user_group)
            self.stdout.write(self.style.SUCCESS(f'✓ Created trader user: {trader_username}'))

            # Show password only if auto-generated (not from env var)
            if 'MCUBE_TRADER_PASSWORD' not in os.environ:
                self.stdout.write(self.style.WARNING(f'  Auto-generated Password: {trader_password}'))
                self.stdout.write(self.style.WARNING('  ⚠️  Save this password or set MCUBE_TRADER_PASSWORD env var!'))
            else:
                self.stdout.write('  Password loaded from MCUBE_TRADER_PASSWORD environment variable')
        else:
            self.stdout.write('  Trader user already exists')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Setup Complete!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write('')
        self.stdout.write('Default Users Created:')
        self.stdout.write('')
        self.stdout.write(f'  Admin User:')
        self.stdout.write(f'    Username: {admin_username}')
        self.stdout.write(f'    Email:    {admin_email}')
        self.stdout.write(f'    Access:   Full system access')
        self.stdout.write('')
        self.stdout.write(f'  Trader User:')
        self.stdout.write(f'    Username: {trader_username}')
        self.stdout.write(f'    Email:    {trader_email}')
        self.stdout.write(f'    Access:   View broker data and execute trades')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✓ Passwords are securely managed via environment variables or auto-generated'))
        self.stdout.write('')
        self.stdout.write('To set custom passwords, use environment variables:')
        self.stdout.write('  export MCUBE_ADMIN_PASSWORD="your_secure_password"')
        self.stdout.write('  export MCUBE_TRADER_PASSWORD="your_secure_password"')
        self.stdout.write('')
        self.stdout.write('Login at: http://localhost:8000/brokers/login/')
        self.stdout.write('')
