"""
Django management command to run the Telegram bot

Usage:
    python manage.py run_telegram_bot

The bot will run continuously and handle commands from Telegram.
Press Ctrl+C to stop the bot.

IMPORTANT: Only ONE instance can run at a time. If you see a conflict error,
check for other running instances and stop them first.
"""

from django.core.management.base import BaseCommand
from apps.alerts.services.telegram_bot import start_bot, is_bot_running, BOT_LOCK_FILE


class Command(BaseCommand):
    help = 'Run the Telegram bot for manual trading system control'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force start by removing stale lock file (use with caution)',
        )

    def handle(self, *args, **options):
        # Check if already running
        if is_bot_running():
            self.stdout.write(self.style.ERROR(''))
            self.stdout.write(self.style.ERROR('=' * 60))
            self.stdout.write(self.style.ERROR('TELEGRAM BOT IS ALREADY RUNNING!'))
            self.stdout.write(self.style.ERROR('=' * 60))
            self.stdout.write('')
            self.stdout.write('Only one bot instance can run at a time.')
            self.stdout.write('This prevents the "Conflict: terminated by other getUpdates" error.')
            self.stdout.write('')
            self.stdout.write('To stop the existing bot:')
            self.stdout.write(self.style.WARNING('  pkill -f "run_telegram_bot"'))
            self.stdout.write('')
            self.stdout.write(f'Lock file: {BOT_LOCK_FILE}')

            if options.get('force'):
                import os
                self.stdout.write('')
                self.stdout.write(self.style.WARNING('--force flag detected, removing lock file...'))
                try:
                    os.remove(BOT_LOCK_FILE)
                    self.stdout.write(self.style.SUCCESS('Lock file removed. Retrying...'))
                    self.stdout.write('')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Failed to remove lock: {e}'))
                    return
            else:
                self.stdout.write('')
                self.stdout.write('If you are sure no other instance is running, use:')
                self.stdout.write(self.style.WARNING('  python manage.py run_telegram_bot --force'))
                return

        self.stdout.write(self.style.SUCCESS('Starting Telegram bot...'))
        self.stdout.write('Press Ctrl+C to stop the bot')
        self.stdout.write('')

        try:
            start_bot()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n\nBot stopped by user'))
        except RuntimeError as e:
            self.stdout.write(self.style.ERROR(f'\n{str(e)}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Bot error: {str(e)}'))
            raise
