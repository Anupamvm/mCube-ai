import logging
from datetime import date
from apps.investments.models import InvestmentProduct, MutualFundScheme, PortfolioHealthScore

logger = logging.getLogger('apps.investments')

MAX_SCORES = {
    'diversification': 20,
    'concentration': 20,
    'expense': 15,
    'risk_adjusted': 20,
    'allocation': 15,
    'tax_efficiency': 10,
}


def compute_health_score(family_member=None, portfolio_group=None) -> PortfolioHealthScore:
    if family_member:
        products = InvestmentProduct.objects.filter(
            investment_account__family_member=family_member,
            is_active=True,
        )
    elif portfolio_group:
        products = InvestmentProduct.objects.filter(
            investment_account__family_member__in=portfolio_group.members.all(),
            is_active=True,
        )
    else:
        raise ValueError('family_member or portfolio_group required')

    products = list(products)
    total_value = sum(float(p.current_value) for p in products)
    if total_value == 0:
        total_value = 1

    type_values = {}
    for p in products:
        type_values[p.product_type] = type_values.get(p.product_type, 0) + float(p.current_value)

    scores = {}
    methodology = {}
    insights = []

    # 1. Diversification (20 pts)
    unique_types = len(type_values)
    div_score = min(20, unique_types * 4)  # 4 pts per asset class, max 20
    scores['diversification'] = div_score
    methodology['diversification'] = f'{unique_types} asset class(es)'
    if unique_types < 3:
        insights.append(f'Your portfolio has only {unique_types} asset class(es). Consider diversifying across MF, equity, FD, gold, and others.')

    # 2. Concentration (20 pts)
    from collections import defaultdict
    amc_vals = defaultdict(float)
    for p in products:
        if p.product_type == 'MUTUAL_FUND' and p.isin:
            try:
                scheme = MutualFundScheme.objects.get(isin=p.isin)
                amc_vals[scheme.amc] += float(p.current_value)
            except MutualFundScheme.DoesNotExist:
                pass

    conc_score = 20
    max_amc_pct = max((v / total_value for v in amc_vals.values()), default=0)
    if max_amc_pct > 0.35:
        conc_score -= 10
        top_amc = max(amc_vals, key=amc_vals.get)
        insights.append(f'{top_amc} represents {max_amc_pct*100:.1f}% of your MF portfolio — consider diversifying AMC exposure.')

    re_pct = type_values.get('REAL_ESTATE', 0) / total_value
    if re_pct > 0.6:
        conc_score -= 5
        insights.append(f'Real estate is {re_pct*100:.1f}% of net worth — illiquid concentration risk.')
    scores['concentration'] = max(0, conc_score)
    methodology['concentration'] = f'Max AMC: {max_amc_pct*100:.1f}%, RE: {re_pct*100:.1f}%'

    # 3. Expense Efficiency (15 pts)
    mf_val = type_values.get('MUTUAL_FUND', 0)
    wer = 0.0
    if mf_val > 0:
        total_weighted_er = 0
        for p in products:
            if p.product_type == 'MUTUAL_FUND' and p.isin:
                try:
                    scheme = MutualFundScheme.objects.get(isin=p.isin)
                    if scheme.expense_ratio:
                        total_weighted_er += float(scheme.expense_ratio) * float(p.current_value)
                except MutualFundScheme.DoesNotExist:
                    pass
        wer = total_weighted_er / mf_val

    exp_score = 15
    if wer > 0.015:
        exp_score -= 10
        insights.append(f'Weighted expense ratio {wer*100:.2f}% is above 1.5%. Switch to direct plans where possible.')
    elif wer > 0.01:
        exp_score -= 5
    scores['expense'] = max(0, exp_score)
    methodology['expense'] = f'Weighted TER: {wer*100:.2f}%'

    # 4. Risk-adjusted Return (20 pts) — based on XIRR if available
    products_with_xirr = [p for p in products if p.xirr is not None]
    risk_score = 10  # default neutral
    if products_with_xirr:
        avg_xirr = sum(float(p.xirr) for p in products_with_xirr) / len(products_with_xirr)
        if avg_xirr > 0.12:
            risk_score = 20
        elif avg_xirr > 0.08:
            risk_score = 15
        elif avg_xirr > 0.05:
            risk_score = 10
        else:
            risk_score = 5
            insights.append(f'Portfolio XIRR of {avg_xirr*100:.1f}% is below inflation. Review underperforming instruments.')
    scores['risk_adjusted'] = risk_score
    methodology['risk_adjusted'] = f'{len(products_with_xirr)} products with XIRR data'

    # 5. Asset Allocation Balance (15 pts)
    equity_pct = (type_values.get('EQUITY', 0) + type_values.get('MUTUAL_FUND', 0)) / total_value
    debt_pct = (type_values.get('FD', 0) + type_values.get('RD', 0) + type_values.get('BOND', 0) +
                type_values.get('PPF', 0) + type_values.get('EPF', 0) + type_values.get('NPS', 0)) / total_value

    alloc_score = 15
    if equity_pct < 0.1:
        alloc_score -= 8
        insights.append(f'Equity exposure ({equity_pct*100:.1f}%) is very low — consider increasing for long-term wealth creation.')
    elif equity_pct > 0.9:
        alloc_score -= 5
        insights.append(f'Equity exposure ({equity_pct*100:.1f}%) is very high — add some fixed income for stability.')

    scores['allocation'] = max(0, alloc_score)
    methodology['allocation'] = f'Equity: {equity_pct*100:.1f}%, Debt: {debt_pct*100:.1f}%'

    # 6. Tax Efficiency (10 pts)
    tax_score = 5
    has_elss = any(
        p.product_type == 'MUTUAL_FUND' and 'elss' in p.name.lower()
        for p in products
    )
    has_sgb = 'SGB' in type_values
    has_ppf = 'PPF' in type_values
    has_epf = 'EPF' in type_values

    if has_elss:
        tax_score += 2
    if has_sgb:
        tax_score += 1
    if has_ppf or has_epf:
        tax_score += 2
    scores['tax_efficiency'] = min(10, tax_score)
    methodology['tax_efficiency'] = f'ELSS:{has_elss}, SGB:{has_sgb}, PPF/EPF:{has_ppf or has_epf}'

    total_score = sum(scores.values())

    return PortfolioHealthScore.objects.update_or_create(
        family_member=family_member,
        portfolio_group=portfolio_group,
        score_date=date.today(),
        defaults={
            'total_score': total_score,
            'diversification_score': scores['diversification'],
            'concentration_score': scores['concentration'],
            'expense_score': scores['expense'],
            'risk_adjusted_score': scores['risk_adjusted'],
            'allocation_score': scores['allocation'],
            'tax_efficiency_score': scores['tax_efficiency'],
            'methodology': methodology,
            'insights': insights,
        },
    )[0]
