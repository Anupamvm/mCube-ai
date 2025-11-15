"""
Django management command to run the Telegram bot

Usage:
    python manage.py run_telegram_bot

The bot will run continuously and handle commands from Telegram.
Press Ctrl+C to stop the bot.
"""

from django.core.management.base import BaseCommand
from apps.alerts.services.telegram_bot import start_bot


class Command(BaseCommand):
    help = 'Run the Telegram bot for manual trading system control'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Telegram bot...'))
        self.stdout.write('Press Ctrl+C to stop the bot')
        self.stdout.write('')

        try:
            start_bot()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n\nBot stopped by user'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Bot error: {str(e)}'))
            raise
