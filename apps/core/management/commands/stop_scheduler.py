"""
Management command to stop all scheduled tasks
"""

from django.core.management.base import BaseCommand
from apps.core.background_tasks import stop_all_scheduled_tasks


class Command(BaseCommand):
    help = 'Stop all scheduled background tasks'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n⚠️  Stopping all scheduled tasks...\n'))

        result = stop_all_scheduled_tasks()

        if result['status'] == 'success':
            self.stdout.write(self.style.SUCCESS(
                f'\n✅ Stopped all tasks ({result["deleted"]} deleted)\n'
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f'\n❌ Failed to stop tasks: {result.get("error")}\n'
            ))
