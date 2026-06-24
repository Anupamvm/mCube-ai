"""
Management command to clean up log files.

Usage:
    python manage.py cleanup_logs            # Delete rotated files older than 7 days
    python manage.py cleanup_logs --days=3   # Custom retention
    python manage.py cleanup_logs --stats    # Show log sizes
    python manage.py cleanup_logs --truncate # Clear current log contents
    python manage.py cleanup_logs --dry-run  # Preview without deleting
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Clean up old rotated log files and show log statistics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=getattr(settings, 'LOG_RETENTION_DAYS', 7),
            help='Delete rotated files older than N days (default: from LOG_RETENTION_DAYS setting)'
        )
        parser.add_argument('--dry-run', action='store_true', help='Preview without deleting')
        parser.add_argument('--stats', action='store_true', help='Show log file sizes and stats')
        parser.add_argument(
            '--truncate', action='store_true',
            help='Clear contents of current log files (keeps filenames)'
        )

    def handle(self, *args, **options):
        log_dir = Path(getattr(settings, 'LOG_DIR', settings.BASE_DIR / 'logs'))

        if options['stats']:
            self._show_stats(log_dir)
            return

        if options['truncate']:
            self._truncate_logs(log_dir, options['dry_run'])
            return

        self._cleanup_rotated(log_dir, options['days'], options['dry_run'])

    def _human_size(self, size):
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} TB'

    def _walk_logs(self, log_dir):
        """Walk log directory, skip pids and __pycache__."""
        for root, dirs, files in os.walk(str(log_dir)):
            dirs[:] = sorted(d for d in dirs if d not in ('pids', '__pycache__'))
            for fname in sorted(files):
                yield os.path.join(root, fname), os.path.relpath(
                    os.path.join(root, fname), str(log_dir)
                )

    def _show_stats(self, log_dir):
        self.stdout.write(self.style.SUCCESS('\n=== Log File Statistics ===\n'))
        total = 0
        current_total = rotated_total = 0
        for fpath, rel in self._walk_logs(log_dir):
            try:
                size = os.path.getsize(fpath)
            except OSError:
                continue
            total += size
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            is_rotated = '.log.' in os.path.basename(fpath)
            if is_rotated:
                rotated_total += size
                label = f'  (rotated) {rel}'
            else:
                current_total += size
                label = f'  {rel}'
            self.stdout.write(
                f'{label:<55} {self._human_size(size):>10}  {mtime.strftime("%Y-%m-%d %H:%M")}'
            )
        self.stdout.write(f'\n  Current logs:  {self._human_size(current_total)}')
        self.stdout.write(f'  Rotated logs:  {self._human_size(rotated_total)}')
        self.stdout.write(self.style.SUCCESS(f'  Total:         {self._human_size(total)}\n'))

    def _cleanup_rotated(self, log_dir, days, dry_run):
        """Delete rotated backup files (e.g. app.log.2026-06-17) older than N days."""
        cutoff = datetime.now() - timedelta(days=days)
        deleted = freed = 0

        for fpath, rel in self._walk_logs(log_dir):
            if '.log.' not in os.path.basename(fpath):
                continue  # skip current (non-rotated) files
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                size = os.path.getsize(fpath)
            except OSError:
                continue

            if mtime >= cutoff:
                continue

            if dry_run:
                self.stdout.write(f'  [DRY RUN] Would delete: {rel} ({self._human_size(size)})')
            else:
                os.remove(fpath)
                self.stdout.write(f'  Deleted: {rel} ({self._human_size(size)})')
            deleted += 1
            freed += size

        if deleted == 0:
            self.stdout.write(self.style.WARNING(f'  No rotated log files older than {days} days found.'))
        else:
            verb = 'Would free' if dry_run else 'Freed'
            self.stdout.write(
                self.style.SUCCESS(f'\n  {verb} {self._human_size(freed)} from {deleted} rotated file(s).')
            )

    def _truncate_logs(self, log_dir, dry_run):
        """Truncate current (non-rotated) log files."""
        truncated = freed = 0
        for fpath, rel in self._walk_logs(log_dir):
            if not fpath.endswith('.log'):
                continue  # skip rotated backups
            try:
                size = os.path.getsize(fpath)
            except OSError:
                continue
            if dry_run:
                self.stdout.write(f'  [DRY RUN] Would truncate: {rel} ({self._human_size(size)})')
            else:
                with open(fpath, 'w'):
                    pass
                self.stdout.write(f'  Truncated: {rel} ({self._human_size(size)} cleared)')
            truncated += 1
            freed += size

        verb = 'Would clear' if dry_run else 'Cleared'
        self.stdout.write(
            self.style.SUCCESS(f'\n  {verb} {self._human_size(freed)} from {truncated} log file(s).')
        )
