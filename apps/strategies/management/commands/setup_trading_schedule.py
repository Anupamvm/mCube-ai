"""
Management command to setup initial trading schedule configuration

Usage:
    python manage.py setup_trading_schedule
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.strategies.services.dynamic_scheduler import DynamicScheduler


class Command(BaseCommand):
    help = 'Setup initial trading schedule configuration'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('SETUP TRADING SCHEDULE CONFIGURATION'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write('')

        try:
            # Create default schedule
            created_count = DynamicScheduler.create_default_schedule()

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'✓ Created {created_count} schedule configurations'))
            self.stdout.write('')

            # List created schedules
            from apps.strategies.models import TradingScheduleConfig

            schedules = TradingScheduleConfig.objects.all().order_by('scheduled_time')

            self.stdout.write(self.style.WARNING('Schedule Summary:'))
            self.stdout.write(self.style.WARNING('-' * 80))

            for schedule in schedules:
                status = '✓' if schedule.is_enabled else '✗'
                recurring = f'(Every {schedule.interval_minutes} mins)' if schedule.is_recurring else ''
                self.stdout.write(
                    f'{status} {schedule.get_task_name_display():<30} @ {schedule.scheduled_time.strftime("%H:%M")} {recurring}'
                )

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('=' * 80))
            self.stdout.write(self.style.SUCCESS('SETUP COMPLETE'))
            self.stdout.write(self.style.SUCCESS('=' * 80))
            self.stdout.write('')
            self.stdout.write('Next steps:')
            self.stdout.write('1. Run migrations: python manage.py makemigrations && python manage.py migrate')
            self.stdout.write('2. Configure schedule via Django Admin: /admin/strategies/tradingscheduleconfig/')
            self.stdout.write('3. Restart Celery Beat: celery -A mcube_ai beat')
            self.stdout.write('')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Setup failed: {e}'))
            raise
