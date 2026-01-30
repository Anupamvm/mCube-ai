"""
Management command to view trading system status
"""

from django.core.management.base import BaseCommand
from apps.core.models import NseFlag, DayReport
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone('Asia/Kolkata')


class Command(BaseCommand):
    help = 'View current trading system status'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== mCube Trading System Status ===\n'))

        # Trading Status
        self.stdout.write(self.style.HTTP_INFO('Trading Status:'))
        enabled = NseFlag.get_bool('autoTradingEnabled')
        status_color = self.style.SUCCESS if enabled else self.style.WARNING
        self.stdout.write(f'  Automated Trading: {status_color(str(enabled).upper())}')

        tradable = NseFlag.get('isDayTradable', 'Unknown')
        self.stdout.write(f'  Day Tradable: {tradable}')

        has_positions = NseFlag.get_bool('openPositions')
        pos_color = self.style.WARNING if has_positions else self.style.SUCCESS
        self.stdout.write(f'  Open Positions: {pos_color(str(has_positions).upper())}')

        # Market Conditions
        self.stdout.write(self.style.HTTP_INFO('\nMarket Conditions:'))
        vix = NseFlag.get('nseVix', 'N/A')
        vix_status = NseFlag.get('vixStatus', 'N/A')
        self.stdout.write(f'  VIX: {vix} ({vix_status})')

        # Risk Parameters
        self.stdout.write(self.style.HTTP_INFO('\nRisk Parameters:'))
        self.stdout.write(f'  Stop Loss: ₹{NseFlag.get("stopLossLimit", "N/A")}')
        self.stdout.write(f'  Profit Target: ₹{NseFlag.get("minDailyProfitTarget", "N/A")}')
        self.stdout.write(f'  Daily Delta: {NseFlag.get("dailyDelta", "N/A")}')

        # Current P&L
        current_pnl = NseFlag.get('currentPos', '0')
        try:
            pnl_float = float(current_pnl)
            pnl_color = self.style.SUCCESS if pnl_float >= 0 else self.style.ERROR
            self.stdout.write(f'  Current P&L: {pnl_color(f"₹{pnl_float:,.2f}")}')
        except:
            self.stdout.write(f'  Current P&L: {current_pnl}')

        # Celery Worker Status
        self.stdout.write(self.style.HTTP_INFO('\nCelery Workers:'))
        try:
            from mcube_ai.celery import app
            inspect = app.control.inspect()
            active = inspect.active()

            if active:
                for worker, tasks in active.items():
                    self.stdout.write(f'  {worker}: {len(tasks)} active tasks')
            else:
                self.stdout.write(self.style.WARNING('  No workers responding'))

            # Get scheduled tasks count
            scheduled = inspect.scheduled()
            if scheduled:
                total_scheduled = sum(len(tasks) for tasks in scheduled.values())
                self.stdout.write(f'  Scheduled Tasks: {total_scheduled}')
            else:
                self.stdout.write('  Scheduled Tasks: 0')

        except Exception as e:
            self.stdout.write(f'  Error checking Celery: {e}')

        # Recent Reports
        self.stdout.write(self.style.HTTP_INFO('\nRecent Reports (Last 5 days):'))
        try:
            reports = DayReport.objects.all()[:5]
            if reports:
                for report in reports:
                    pnl_color = self.style.SUCCESS if report.pnl >= 0 else self.style.ERROR
                    self.stdout.write(
                        f'  {report.date} ({report.day_of_week}): '
                        f'{pnl_color(f"₹{report.pnl:,.2f}")} '
                        f'[{report.num_legs} legs, {"Closed" if report.is_closed else "Open"}]'
                    )
            else:
                self.stdout.write('  No reports yet')
        except Exception as e:
            self.stdout.write(f'  Error loading reports: {e}')

        self.stdout.write('')
