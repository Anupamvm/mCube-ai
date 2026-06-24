from __future__ import annotations
from apps.investments.models import InvestmentProduct, MutualFundScheme
from collections import defaultdict


def generate_insights(family_member=None, portfolio_group=None) -> list[str]:
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
        return []

    products = list(products)
    total_value = sum(float(p.current_value) for p in products)
    if total_value == 0:
        return ['Upload your first CAS statement or add investments to get portfolio insights.']

    insights = []
    type_vals = defaultdict(float)
    for p in products:
        type_vals[p.product_type] += float(p.current_value)

    # MF expense ratio insight
    mf_val = type_vals.get('MUTUAL_FUND', 0)
    if mf_val > 0:
        total_er = 0
        for p in products:
            if p.product_type == 'MUTUAL_FUND' and p.isin:
                try:
                    s = MutualFundScheme.objects.get(isin=p.isin)
                    if s.expense_ratio:
                        total_er += float(s.expense_ratio) * float(p.current_value)
                except MutualFundScheme.DoesNotExist:
                    pass
        wer = total_er / mf_val
        annual_cost = mf_val * wer
        if wer > 0:
            insights.append(
                f'Weighted expense ratio {wer*100:.2f}% costs approx ₹{annual_cost:,.0f}/year on your MF portfolio of ₹{mf_val:,.0f}.'
            )

    # Real estate dominance
    re_pct = type_vals.get('REAL_ESTATE', 0) / total_value
    if re_pct > 0.5:
        insights.append(
            f'{re_pct*100:.0f}% of net worth is in real estate — a highly illiquid asset. Ensure adequate liquid investments for emergencies.'
        )

    # FD tax efficiency
    fd_val = type_vals.get('FD', 0)
    if fd_val > 500000:
        insights.append(
            f'FD interest income of ₹{fd_val*0.075:,.0f} (est. at 7.5%) is fully taxable at slab rate. Consider tax-efficient alternatives like debt MFs for surplus above ₹5L.'
        )

    # Low equity exposure
    equity_pct = (type_vals.get('EQUITY', 0) + type_vals.get('MUTUAL_FUND', 0)) / total_value
    if equity_pct < 0.15:
        insights.append(
            f'Equity exposure is only {equity_pct*100:.0f}%. For long-term wealth creation, consider increasing equity allocation through MFs or direct stocks.'
        )

    # Too many MF schemes
    mf_count = sum(1 for p in products if p.product_type == 'MUTUAL_FUND')
    if mf_count > 10:
        insights.append(
            f'You hold {mf_count} mutual fund schemes. Many may overlap significantly. Consider consolidating to 5–7 core funds.'
        )

    # SGB & PPF benefits
    if type_vals.get('SGB', 0) == 0 and total_value > 2000000:
        insights.append(
            'Sovereign Gold Bonds (SGBs) offer 2.5% interest + gold appreciation + tax-free maturity after 8 years. Consider allocating 5–10% to gold via SGBs.'
        )

    if not insights:
        insights.append('Your portfolio looks reasonably well-structured. Keep monitoring and rebalance annually.')

    return insights
