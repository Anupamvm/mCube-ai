"""
Shared dedup helper for all MF holding import paths.

Canonical identity order:
  1. ISIN  — most reliable, used when available
  2. Name  — fallback when ISIN is absent (mangled PDF, XLSX without ISIN column)
  3. Create — when no match found

Side-effects:
  - When matched by ISIN but a name-only duplicate exists, the duplicate is deleted.
  - When matched by name and we now have an ISIN, it is written back to the record.
"""
from __future__ import annotations
from decimal import Decimal
import logging

logger = logging.getLogger('apps.investments')


def resolve_mf_product(
    account,
    scheme_name: str,
    isin: str,
    defaults: dict,
) -> tuple:
    """
    Return (InvestmentProduct, created: bool).

    `defaults` must contain at least: invested_value, current_value, as_of_date, data_source.
    """
    from apps.investments.models import InvestmentProduct

    product = None

    # ── 1. ISIN match ────────────────────────────────────────────────────
    if isin:
        product = InvestmentProduct.objects.filter(
            investment_account=account,
            product_type='MUTUAL_FUND',
            isin=isin,
        ).first()

    # ── 2. Name match (scheme names are consistent within MF Central) ────
    if product is None and scheme_name:
        # Prefer ISIN-keyed record if multiple rows share the name
        product = (
            InvestmentProduct.objects.filter(
                investment_account=account,
                product_type='MUTUAL_FUND',
                name=scheme_name,
            )
            .order_by('-isin')   # non-empty ISIN sorts first
            .first()
        )

    # ── 3. Create ─────────────────────────────────────────────────────────
    if product is None:
        product = InvestmentProduct.objects.create(
            investment_account=account,
            product_type='MUTUAL_FUND',
            name=scheme_name,
            isin=isin or '',
            is_active=True,
            **defaults,
        )
        logger.debug('MF product created: %s isin=%s', scheme_name[:40], isin)
        return product, True

    # ── Update existing ────────────────────────────────────────────────────
    changed = False

    # Backfill ISIN if we now have one and the record doesn't
    if isin and not product.isin:
        product.isin = isin
        changed = True

    # Detect a PDF placeholder: invested == current means no real cost data.
    # In that case, keep any real invested_value already on the record.
    incoming_invested = defaults.get('invested_value')
    incoming_current  = defaults.get('current_value')
    is_pdf_placeholder = (
        incoming_invested is not None
        and incoming_current is not None
        and Decimal(str(incoming_invested)) == Decimal(str(incoming_current))
    )

    for k, v in defaults.items():
        # Preserve real cost basis — don't overwrite with PDF placeholder
        if k == 'invested_value' and is_pdf_placeholder:
            existing_iv = product.invested_value
            existing_cv = product.current_value
            if existing_iv and existing_cv and existing_iv != existing_cv:
                continue   # keep the real invested_value from XLSX

        if k == 'extra_data':
            # Merge, don't replace — preserves keys the current import doesn't
            # know about (e.g. a manually-set category) instead of wiping them.
            merged = {**(product.extra_data or {}), **(v or {})}
            if merged != product.extra_data:
                product.extra_data = merged
                changed = True
            continue

        current_val = getattr(product, k, None)
        if isinstance(current_val, Decimal) and not isinstance(v, Decimal):
            v = Decimal(str(v))
        if current_val != v:
            setattr(product, k, v)
            changed = True

    if changed:
        product.save()

    # ── Merge: delete name-only duplicates now that we have/kept the canonical ──
    dupe_qs = InvestmentProduct.objects.filter(
        investment_account=account,
        product_type='MUTUAL_FUND',
        name=scheme_name,
        isin='',
    ).exclude(pk=product.pk)
    deleted, _ = dupe_qs.delete()
    if deleted:
        logger.info('Merged %d duplicate(s) for "%s" into id=%d', deleted, scheme_name[:40], product.pk)

    return product, False
