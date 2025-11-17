"""
Management command to update existing TradingScheduleConfig records
to match the new schedule requirements

Run with: python manage.py update_schedule_configs
"""

from django.core.management.base import BaseCommand
from datetime import time
from apps.strategies.models import TradingScheduleConfig


class Command(BaseCommand):
    help = 'Update existing TradingScheduleConfig records to match new requirements'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
            self.stdout.write('')

        updated_count = 0

        # Update TRADE_START configuration
        self.stdout.write('Updating TRADE_START configuration...')
        try:
            trade_start = TradingScheduleConfig.objects.get(task_name='TRADE_START')

            changes = []

            if trade_start.scheduled_time != time(9, 40):
                changes.append(f"  scheduled_time: {trade_start.scheduled_time} → 09:40:00")
                if not dry_run:
                    trade_start.scheduled_time = time(9, 40)

            if not trade_start.is_recurring:
                changes.append(f"  is_recurring: False → True")
                if not dry_run:
                    trade_start.is_recurring = True

            if trade_start.interval_minutes != 5:
                changes.append(f"  interval_minutes: {trade_start.interval_minutes} → 5")
                if not dry_run:
                    trade_start.interval_minutes = 5

            if trade_start.start_time != time(9, 40):
                changes.append(f"  start_time: {trade_start.start_time} → 09:40:00")
                if not dry_run:
                    trade_start.start_time = time(9, 40)

            if trade_start.end_time != time(10, 15):
                changes.append(f"  end_time: {trade_start.end_time} → 10:15:00")
                if not dry_run:
                    trade_start.end_time = time(10, 15)

            if trade_start.days_of_week != [0, 1, 2, 3, 4]:
                changes.append(f"  days_of_week: {trade_start.days_of_week} → [0, 1, 2, 3, 4]")
                if not dry_run:
                    trade_start.days_of_week = [0, 1, 2, 3, 4]

            if trade_start.description != 'Evaluate strangle entries (9:40 AM - 10:15 AM window)':
                changes.append(f"  description: Updated")
                if not dry_run:
                    trade_start.description = 'Evaluate strangle entries (9:40 AM - 10:15 AM window)'

            if changes:
                self.stdout.write(f'  TRADE_START changes:')
                for change in changes:
                    self.stdout.write(self.style.SUCCESS(change))

                if not dry_run:
                    trade_start.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS('  ✅ TRADE_START updated'))
            else:
                self.stdout.write(self.style.SUCCESS('  ✅ TRADE_START already up to date'))

        except TradingScheduleConfig.DoesNotExist:
            self.stdout.write(self.style.WARNING('  ⚠️ TRADE_START config not found'))

        # Update TRADE_STOP configuration
        self.stdout.write('')
        self.stdout.write('Updating TRADE_STOP configuration...')
        try:
            trade_stop = TradingScheduleConfig.objects.get(task_name='TRADE_STOP')

            changes = []

            if trade_stop.days_of_week != [0, 1, 2, 3, 4]:
                changes.append(f"  days_of_week: {trade_stop.days_of_week} → [0, 1, 2, 3, 4]")
                if not dry_run:
                    trade_stop.days_of_week = [0, 1, 2, 3, 4]

            new_params = {'profit_threshold': 10000}
            if trade_stop.task_parameters != new_params:
                changes.append(f"  task_parameters: {trade_stop.task_parameters} → {new_params}")
                if not dry_run:
                    trade_stop.task_parameters = new_params

            if trade_stop.description != 'Evaluate exit conditions daily if profit >= configured threshold (e.g., ₹10k)':
                changes.append(f"  description: Updated")
                if not dry_run:
                    trade_stop.description = 'Evaluate exit conditions daily if profit >= configured threshold (e.g., ₹10k)'

            if changes:
                self.stdout.write(f'  TRADE_STOP changes:')
                for change in changes:
                    self.stdout.write(self.style.SUCCESS(change))

                if not dry_run:
                    trade_stop.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS('  ✅ TRADE_STOP updated'))
            else:
                self.stdout.write(self.style.SUCCESS('  ✅ TRADE_STOP already up to date'))

        except TradingScheduleConfig.DoesNotExist:
            self.stdout.write(self.style.WARNING('  ⚠️ TRADE_STOP config not found'))

        # Update TRADE_MONITOR configuration
        self.stdout.write('')
        self.stdout.write('Updating TRADE_MONITOR configuration...')
        try:
            trade_monitor = TradingScheduleConfig.objects.get(task_name='TRADE_MONITOR')

            changes = []

            if trade_monitor.interval_minutes != 15:
                changes.append(f"  interval_minutes: {trade_monitor.interval_minutes} → 15")
                if not dry_run:
                    trade_monitor.interval_minutes = 15

            new_params = {'delta_threshold': 300}
            if trade_monitor.task_parameters != new_params:
                changes.append(f"  task_parameters: {trade_monitor.task_parameters} → {new_params}")
                if not dry_run:
                    trade_monitor.task_parameters = new_params

            if trade_monitor.display_name != 'Trade Monitoring (Delta, P&L)':
                changes.append(f"  display_name: Updated")
                if not dry_run:
                    trade_monitor.display_name = 'Trade Monitoring (Delta, P&L)'

            if trade_monitor.description != 'Monitor active positions (delta, P&L, targets) - Configurable via UI':
                changes.append(f"  description: Updated")
                if not dry_run:
                    trade_monitor.description = 'Monitor active positions (delta, P&L, targets) - Configurable via UI'

            if changes:
                self.stdout.write(f'  TRADE_MONITOR changes:')
                for change in changes:
                    self.stdout.write(self.style.SUCCESS(change))

                if not dry_run:
                    trade_monitor.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS('  ✅ TRADE_MONITOR updated'))
            else:
                self.stdout.write(self.style.SUCCESS('  ✅ TRADE_MONITOR already up to date'))

        except TradingScheduleConfig.DoesNotExist:
            self.stdout.write(self.style.WARNING('  ⚠️ TRADE_MONITOR config not found'))

        # Summary
        self.stdout.write('')
        self.stdout.write('=' * 70)
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN COMPLETE - Would have updated {updated_count} configurations'))
            self.stdout.write(self.style.WARNING('Run without --dry-run to apply changes'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✅ Updated {updated_count} schedule configurations'))
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('⚠️ IMPORTANT: Restart Celery Beat for changes to take effect:'))
            self.stdout.write(self.style.WARNING('   sudo systemctl restart celery-beat'))
        self.stdout.write('=' * 70)
