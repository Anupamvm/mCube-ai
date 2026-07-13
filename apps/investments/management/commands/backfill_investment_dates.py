"""
Management command: backfill_investment_dates

Populates InvestmentProduct.investment_date for existing rows that predate
the field, so XIRR (computed at product/account/member/family/fund level)
uses the real date capital was deployed instead of the DB row's created_at.

Resolution order per product:
  1. Has linked Transaction rows -> earliest transaction_date (exact).
  2. extra_data['purchase_date'] (captured by CSV/portfolio imports) (exact).
  3. as_of_date (best-effort guess).
  4. created_at date (last-resort guess).

Products resolved via (3) or (4) are guesses — the printed summary flags how
many fell into each bucket so they can be corrected by hand later.

Usage:
    python manage.py backfill_investment_dates [--dry-run]
"""

from __future__ import annotations
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Backfill InvestmentProduct.investment_date for rows created before the field existed'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be done without making changes')

    def handle(self, *args, **options):
        from apps.investments.models import InvestmentProduct, Transaction

        dry_run = options['dry_run']

        products = InvestmentProduct.objects.filter(investment_date__isnull=True)
        total = products.count()

        counts = {'transactions': 0, 'purchase_date': 0, 'as_of_date': 0, 'created_at': 0, 'skipped': 0}

        for product in products:
            resolved_date = None
            source = None

            earliest_txn = (
                Transaction.objects.filter(product=product)
                .order_by('transaction_date')
                .values_list('transaction_date', flat=True)
                .first()
            )
            if earliest_txn:
                resolved_date = earliest_txn
                source = 'transactions'
            else:
                purchase_date_str = (product.extra_data or {}).get('purchase_date')
                if purchase_date_str:
                    resolved_date = purchase_date_str
                    source = 'purchase_date'
                elif product.as_of_date:
                    resolved_date = product.as_of_date
                    source = 'as_of_date'
                elif product.created_at:
                    resolved_date = product.created_at.date()
                    source = 'created_at'

            if not resolved_date:
                counts['skipped'] += 1
                continue

            counts[source] += 1
            if not dry_run:
                product.investment_date = resolved_date
                product.save(update_fields=['investment_date'])

        self.stdout.write(self.style.SUCCESS(
            f'{"[DRY RUN] " if dry_run else ""}Backfilled {total - counts["skipped"]}/{total} products:'
        ))
        self.stdout.write(f'  exact — from transactions:    {counts["transactions"]}')
        self.stdout.write(f'  exact — from purchase_date:   {counts["purchase_date"]}')
        self.stdout.write(f'  guess — from as_of_date:       {counts["as_of_date"]}')
        self.stdout.write(f'  guess — from created_at:       {counts["created_at"]}')
        self.stdout.write(f'  skipped (no data available):  {counts["skipped"]}')
        if counts['as_of_date'] or counts['created_at']:
            self.stdout.write(self.style.WARNING(
                f'{counts["as_of_date"] + counts["created_at"]} product(s) got a guessed investment_date — '
                'review and correct manually where accuracy matters.'
            ))
