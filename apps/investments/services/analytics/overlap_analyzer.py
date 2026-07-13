import logging
from collections import defaultdict
from apps.investments.models import InvestmentProduct, MutualFundScheme, FamilyMember
from apps.data.models import TLStockData

logger = logging.getLogger('apps.investments')


def compute_overlap(member_ids: list, user) -> dict:
    """AMC, category, and sector concentration analysis across selected members."""
    members = FamilyMember.objects.filter(pk__in=member_ids, user=user)
    products = InvestmentProduct.objects.filter(
        investment_account__family_member__in=members,
        is_active=True,
    ).select_related('investment_account')

    total_value = sum(float(p.current_value) for p in products)
    if total_value == 0:
        return {'error': 'No portfolio value to analyse'}

    # AMC / category concentration (MF only), sector concentration (equity only)
    amc_totals = defaultdict(float)
    category_totals = defaultdict(float)
    sector_totals = defaultdict(float)
    product_type_totals = defaultdict(float)
    expense_weighted_sum = 0.0

    for product in products:
        val = float(product.current_value)
        product_type_totals[product.product_type] += val

        if product.product_type == 'MUTUAL_FUND' and product.isin:
            try:
                scheme = MutualFundScheme.objects.get(isin=product.isin)
                if scheme.amc:
                    amc_totals[scheme.amc] += val
                if scheme.category:
                    category_totals[scheme.category] += val
                if scheme.expense_ratio:
                    expense_weighted_sum += float(scheme.expense_ratio) * val
            except MutualFundScheme.DoesNotExist:
                pass

        if product.product_type == 'EQUITY' and product.isin:
            stock = TLStockData.objects.filter(isin=product.isin).first()
            if stock and stock.sector_name:
                sector_totals[stock.sector_name] += val

    # Weighted average expense ratio
    mf_total = product_type_totals.get('MUTUAL_FUND', 0)
    wer = (expense_weighted_sum / mf_total) if mf_total else 0

    # Sort by value desc
    def _pct(d, total):
        return {k: {'value': round(v, 2), 'pct': round(v / total * 100, 2)} for k, v in sorted(d.items(), key=lambda x: -x[1])}

    # Concentration warnings
    warnings = []
    for amc, val in amc_totals.items():
        pct = val / total_value * 100
        if pct > 35:
            warnings.append(f'High AMC concentration: {amc} is {pct:.1f}% of portfolio')

    for cat, val in category_totals.items():
        pct = val / total_value * 100
        if pct > 40:
            warnings.append(f'High category concentration: {cat} is {pct:.1f}% of portfolio')

    for sector, val in sector_totals.items():
        pct = val / total_value * 100
        if pct > 40:
            warnings.append(f'High sector concentration: {sector} is {pct:.1f}% of portfolio')

    re_val = product_type_totals.get('REAL_ESTATE', 0)
    if re_val / total_value > 0.6:
        warnings.append(f'Real estate concentration {re_val/total_value*100:.1f}% exceeds 60% threshold')

    return {
        'total_portfolio_value': round(total_value, 2),
        'amc_concentration': _pct(amc_totals, total_value),
        'category_concentration': _pct(category_totals, total_value),
        'sector_concentration': _pct(sector_totals, total_value),
        'asset_type_allocation': _pct(dict(product_type_totals), total_value),
        'weighted_expense_ratio': round(wer * 100, 4),
        'estimated_annual_cost': round(mf_total * wer, 2),
        'warnings': warnings,
    }
