"""
Management command: dedup_mf_products

Cleans up duplicate InvestmentProduct rows that arise when the same MF
scheme is imported from multiple sources (PDF CAS vs XLSX CAS).

Rules applied per (account, scheme_name):
  1. If a record with a real ISIN exists alongside one with isin='',
     delete the isin='' duplicate (data is merged onto the ISIN record).
  2. If multiple records with isin='' exist for the same name,
     keep the most recently updated one and delete the rest.
  3. Zero-unit / zero-value records are marked is_active=False (not deleted,
     in case they have linked transactions).

Usage:
    python manage.py dedup_mf_products [--dry-run] [--account-id N]
"""

from __future__ import annotations
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Remove duplicate MF product records across all investment accounts'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be done without making changes')
        parser.add_argument('--account-id', type=int, default=None,
                            help='Limit to a single InvestmentAccount id')

    def handle(self, *args, **options):
        from apps.investments.models import InvestmentProduct, InvestmentAccount

        dry_run = options['dry_run']
        acct_filter = options['account_id']

        accounts = InvestmentAccount.objects.all()
        if acct_filter:
            accounts = accounts.filter(pk=acct_filter)

        total_deleted = 0
        total_deactivated = 0

        for account in accounts:
            qs = InvestmentProduct.objects.filter(
                investment_account=account,
                product_type='MUTUAL_FUND',
            )

            # ── Group by name ─────────────────────────────────────────────
            by_name: dict[str, list] = {}
            for p in qs.order_by('-isin', 'pk'):
                by_name.setdefault(p.name, []).append(p)

            with transaction.atomic():
                for name, products in by_name.items():
                    if len(products) == 1:
                        # Check for zero-value deactivation
                        p = products[0]
                        if self._is_zero(p):
                            if not dry_run:
                                p.is_active = False
                                p.save(update_fields=['is_active'])
                            total_deactivated += 1
                            self.stdout.write(
                                f'  DEACTIVATE [{account.pk}] {name[:50]}'
                            )
                        continue

                    # Sort: ISIN-keyed first, then by pk descending (newest)
                    with_isin    = [p for p in products if p.isin]
                    without_isin = [p for p in products if not p.isin]

                    if with_isin:
                        canonical = with_isin[0]
                        to_delete = with_isin[1:] + without_isin
                    else:
                        # All isin=''; keep highest-pk (most recently updated)
                        canonical = max(without_isin, key=lambda p: p.pk)
                        to_delete = [p for p in without_isin if p.pk != canonical.pk]

                    for dup in to_delete:
                        self.stdout.write(
                            f'  DELETE [{account.pk}] "{name[:50]}" '
                            f'id={dup.pk} isin={dup.isin or "(empty)"}'
                        )
                        if not dry_run:
                            # Move any transactions to canonical before deleting
                            dup.transactions.all().update(product=canonical)
                            dup.delete()
                        total_deleted += 1

                    # Deactivate canonical if zero-value
                    if self._is_zero(canonical):
                        self.stdout.write(
                            f'  DEACTIVATE [{account.pk}] {canonical.name[:50]}'
                        )
                        if not dry_run:
                            canonical.is_active = False
                            canonical.save(update_fields=['is_active'])
                        total_deactivated += 1

        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix}Done: {total_deleted} deleted, {total_deactivated} deactivated'
            )
        )

    @staticmethod
    def _is_zero(p) -> bool:
        from decimal import Decimal
        zero = Decimal('0')
        iv = p.invested_value or zero
        cv = p.current_value  or zero
        return iv == zero and cv == zero
