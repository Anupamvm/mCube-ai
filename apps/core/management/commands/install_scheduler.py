"""
Management command to install the daily task scheduler
"""

from django.core.management.base import BaseCommand
from apps.core.background_tasks import install_daily_task_scheduler


class Command(BaseCommand):
    help = 'Install daily task scheduler for automated trading'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\nInstalling Daily Task Scheduler...\n'))

        result = install_daily_task_scheduler()

        if result['status'] == 'success':
            self.stdout.write(self.style.SUCCESS('\n✅ Scheduler installed successfully!'))
            self.stdout.write(f"   First run: {result['first_run']}")
            self.stdout.write('\nNext steps:')
            self.stdout.write('1. Enable auto-trading: python manage.py enable_trading')
            self.stdout.write('2. Start worker: python manage.py process_tasks\n')
        else:
            self.stdout.write(self.style.ERROR(f'\n❌ Installation failed: {result.get("error")}\n'))
