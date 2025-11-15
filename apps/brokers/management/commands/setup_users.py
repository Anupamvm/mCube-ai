"""
Management command to setup initial users and groups for the mCube Trading System.

Usage:
    python manage.py setup_users
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from apps.brokers.models import BrokerLimit, BrokerPosition, OptionChainQuote, HistoricalPrice


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
        admin_username = 'admin'
        admin_email = 'admin@mcube.ai'
        admin_password = 'admin123'  # Change this in production!

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
            self.stdout.write(self.style.WARNING(f'  Password: {admin_password}'))
            self.stdout.write(self.style.WARNING('  ⚠️  CHANGE THIS PASSWORD IN PRODUCTION!'))
        else:
            self.stdout.write('  Admin user already exists')

        # Create default trader user
        trader_username = 'trader'
        trader_email = 'trader@mcube.ai'
        trader_password = 'trader123'  # Change this in production!

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
            self.stdout.write(self.style.WARNING(f'  Password: {trader_password}'))
            self.stdout.write(self.style.WARNING('  ⚠️  CHANGE THIS PASSWORD IN PRODUCTION!'))
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
        self.stdout.write(f'    Password: {admin_password}')
        self.stdout.write(f'    Access:   Full system access')
        self.stdout.write('')
        self.stdout.write(f'  Trader User:')
        self.stdout.write(f'    Username: {trader_username}')
        self.stdout.write(f'    Password: {trader_password}')
        self.stdout.write(f'    Access:   View broker data and execute trades')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('⚠️  IMPORTANT: Change default passwords before deploying to production!'))
        self.stdout.write('')
        self.stdout.write('Login at: http://localhost:8000/brokers/login/')
        self.stdout.write('')
