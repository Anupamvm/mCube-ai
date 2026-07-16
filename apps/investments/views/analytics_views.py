from __future__ import annotations
import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import FamilyMember, PortfolioGroup, InvestmentProduct, PortfolioHealthScore
from ..serializers import PortfolioSnapshotSerializer, PortfolioHealthScoreSerializer
from ..tasks import update_all_prices_task, sync_missing_mf_categories_task

logger = logging.getLogger('apps.investments')


def _resolve_members(request):
    """FamilyMembers for a comma-separated `member_ids` query param, defaulting to all of the user's members."""
    member_ids_param = request.query_params.get('member_ids', '')
    if member_ids_param:
        member_ids = [int(x) for x in member_ids_param.split(',') if x.strip().isdigit()]
        return FamilyMember.objects.filter(pk__in=member_ids, user=request.user)
    return FamilyMember.objects.filter(user=request.user)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def consolidated_portfolio(request):
    members = _resolve_members(request)

    products = InvestmentProduct.objects.filter(
        investment_account__family_member__in=members,
        is_active=True,
    ).select_related('investment_account')

    total_invested = 0.0
    total_current = 0.0
    asset_allocation: dict[str, float] = {}
    account_ids: set[int] = set()

    for p in products:
        iv = float(p.invested_value)
        cv = float(p.current_value)
        total_invested += iv
        total_current += cv
        asset_allocation[p.product_type] = asset_allocation.get(p.product_type, 0.0) + cv
        account_ids.add(p.investment_account_id)

    from ..services.analytics.xirr_calculator import compute_family_xirr

    return Response({
        'total_invested_value': round(total_invested, 2),
        'total_current_value': round(total_current, 2),
        'total_gain_loss': round(total_current - total_invested, 2),
        'gain_loss_pct': round(
            ((total_current - total_invested) / total_invested * 100) if total_invested else 0, 2
        ),
        'xirr': compute_family_xirr(members),
        'asset_allocation': {k: round(v, 2) for k, v in asset_allocation.items()},
        'accounts_count': len(account_ids),
        'products_count': products.count(),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_price_update(request):
    member_ids_param = request.data.get('member_ids', [])
    try:
        task = update_all_prices_task.delay(
            user_id=request.user.id,
            member_ids=member_ids_param or None,
        )
        return Response({
            'status': 'price_update_queued',
            'task_id': task.id,
            'message': 'Price update queued — refresh in a moment to see updated values.',
        })
    except Exception as e:
        # Broker unavailable — run synchronously so the user still gets a result.
        logger.warning('Celery broker unavailable, running price update synchronously: %s', e)
        try:
            from apps.investments.tasks import update_all_prices_task as task_fn
            result = task_fn(user_id=request.user.id, member_ids=member_ids_param or None)
            message = (
                f"Updated {result.get('mf', 0)} mutual fund, {result.get('equity', 0)} equity, "
                f"and {result.get('gold', 0)} gold holdings."
            )
            return Response({'status': 'price_update_complete', 'result': result, 'message': message})
        except Exception as sync_err:
            logger.error('Synchronous price update failed: %s', sync_err)
            return Response({'error': str(sync_err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_mf_categories(request):
    """Backfill fund categories from MFAPI for held ISINs that don't have one yet."""
    member_id = request.data.get('member_id')
    try:
        task = sync_missing_mf_categories_task.delay(user_id=request.user.id, member_id=member_id)
        return Response({'status': 'sync_queued', 'task_id': task.id})
    except Exception as e:
        logger.warning('Celery broker unavailable, running category sync synchronously: %s', e)
        try:
            from apps.investments.tasks import sync_missing_mf_categories_task as task_fn
            result = task_fn(user_id=request.user.id, member_id=member_id)
            return Response({'status': 'sync_complete', 'updated': result})
        except Exception as sync_err:
            logger.error('Synchronous category sync failed: %s', sync_err)
            return Response({'error': str(sync_err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def overlap_analysis(request):
    member_ids = request.data.get('member_ids', [])
    if not member_ids:
        members = FamilyMember.objects.filter(user=request.user)
        member_ids = list(members.values_list('id', flat=True))

    from ..services.analytics.overlap_analyzer import compute_overlap
    try:
        result = compute_overlap(member_ids, request.user)
        return Response(result)
    except Exception as e:
        logger.error('Overlap analysis error: %s', e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def health_score_view(request):
    member_id = request.query_params.get('member_id')
    group_id = request.query_params.get('group_id')

    if member_id:
        try:
            member = FamilyMember.objects.get(pk=member_id, user=request.user)
        except FamilyMember.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        score = PortfolioHealthScore.objects.filter(family_member=member).first()
    elif group_id:
        try:
            group = PortfolioGroup.objects.get(pk=group_id, user=request.user)
        except PortfolioGroup.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        score = PortfolioHealthScore.objects.filter(portfolio_group=group).first()
    else:
        return Response({'error': 'member_id or group_id required'}, status=status.HTTP_400_BAD_REQUEST)

    if not score:
        return Response({'error': 'No health score computed yet'}, status=status.HTTP_404_NOT_FOUND)

    return Response(PortfolioHealthScoreSerializer(score).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def risk_summary(request):
    """Value-weighted risk/performance metrics across all mutual fund holdings for the given members."""
    from datetime import date, timedelta
    from ..models import MutualFundScheme, NAVHistory
    from ..services.analytics.risk_metrics import compute_risk_metrics
    from ..services.analytics.returns_calculator import compute_trailing_returns

    members = _resolve_members(request)
    products = InvestmentProduct.objects.filter(
        investment_account__family_member__in=members,
        is_active=True,
        product_type='MUTUAL_FUND',
    ).exclude(isin='')

    # Dedup by ISIN — a fund held by two members is only computed once.
    value_by_isin: dict[str, float] = {}
    name_by_isin: dict[str, str] = {}
    for p in products:
        value_by_isin[p.isin] = value_by_isin.get(p.isin, 0.0) + float(p.current_value)
        name_by_isin.setdefault(p.isin, p.name)

    total_mf_value = sum(value_by_isin.values())
    if total_mf_value == 0:
        return Response({'error': 'No mutual fund holdings to analyse'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    since = date.today() - timedelta(days=365 * 3)
    metric_keys = ['sharpe_ratio', 'sortino_ratio', 'std_dev_annual', 'max_drawdown', 'beta', 'alpha_annual']
    weighted_sums = {k: 0.0 for k in metric_keys}
    weight_totals = {k: 0.0 for k in metric_keys}
    covered_value = 0.0
    excluded_funds = []

    return_period_keys = ['1M', '3M', '6M', '1Y', '3Y', '5Y']
    return_weighted_sums = {k: 0.0 for k in return_period_keys}
    return_weight_totals = {k: 0.0 for k in return_period_keys}

    schemes = {s.isin: s for s in MutualFundScheme.objects.filter(isin__in=value_by_isin.keys())}
    for isin, value in value_by_isin.items():
        scheme = schemes.get(isin)
        metrics = {}
        if scheme:
            nav_qs = NAVHistory.objects.filter(scheme=scheme, date__gte=since).order_by('date')
            full_nav_qs = NAVHistory.objects.filter(scheme=scheme)
            if nav_qs.count() >= 30:
                metrics = compute_risk_metrics(nav_qs, sub_category=scheme.sub_category, scheme_name=scheme.scheme_name)

            for label, entry in compute_trailing_returns(full_nav_qs).items():
                if label in return_weight_totals:
                    # CAGR beyond 1Y is the comparable, annualised figure to weight
                    ret = entry.get('cagr_pct', entry.get('return_pct'))
                    return_weighted_sums[label] += ret * value
                    return_weight_totals[label] += value

        if not metrics:
            excluded_funds.append({'isin': isin, 'name': name_by_isin[isin], 'value': round(value, 2)})
            continue

        covered_value += value
        for k in metric_keys:
            v = metrics.get(k)
            if v is not None:
                weighted_sums[k] += v * value
                weight_totals[k] += value

    result = {
        'total_mf_value': round(total_mf_value, 2),
        'covered_value': round(covered_value, 2),
        'coverage_pct': round(covered_value / total_mf_value * 100, 2),
        'excluded_funds': excluded_funds,
        'weighted_sharpe': round(weighted_sums['sharpe_ratio'] / weight_totals['sharpe_ratio'], 4) if weight_totals['sharpe_ratio'] else None,
        'weighted_sortino': round(weighted_sums['sortino_ratio'] / weight_totals['sortino_ratio'], 4) if weight_totals['sortino_ratio'] else None,
        'weighted_std_dev': round(weighted_sums['std_dev_annual'] / weight_totals['std_dev_annual'], 4) if weight_totals['std_dev_annual'] else None,
        'weighted_max_drawdown': round(weighted_sums['max_drawdown'] / weight_totals['max_drawdown'], 4) if weight_totals['max_drawdown'] else None,
        'weighted_beta': round(weighted_sums['beta'] / weight_totals['beta'], 4) if weight_totals['beta'] else None,
        'weighted_alpha': round(weighted_sums['alpha_annual'] / weight_totals['alpha_annual'], 4) if weight_totals['alpha_annual'] else None,
        'weighted_returns': {
            label: round(return_weighted_sums[label] / return_weight_totals[label], 2)
            for label in return_period_keys if return_weight_totals[label]
        },
    }
    return Response(result)


_RETURNS_TYPE_LABELS = {
    'MUTUAL_FUND': 'Mutual Fund', 'EQUITY': 'Equity', 'FD': 'Fixed Deposit', 'RD': 'Recurring Deposit',
    'SGB': 'Sovereign Gold Bond', 'BOND': 'Bond', 'PPF': 'PPF', 'EPF': 'EPF / PF', 'NPS': 'NPS',
    'REAL_ESTATE': 'Real Estate', 'PHYSICAL_GOLD': 'Physical Gold', 'CRYPTO': 'Crypto',
    'CASH': 'Cash', 'SAVINGS': 'Savings', 'OTHER': 'Other',
}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def returns_breakdown(request):
    """
    XIRR-based performance breakdown grouped by fund / AMC / sector / asset
    class. Each group's XIRR is computed from the *pooled* cashflows of every
    holding in that group (via compute_products_xirr) — the true return of
    treating the group as one investment — not a naive average of individual
    fund XIRRs, which would misweight small and large holdings equally.

    XIRR needs real transaction-dated cashflows to mean anything; holdings
    imported without transaction history (common for MF Central-only imports)
    fall back to a same-day synthetic cashflow, which is undefined for XIRR
    and correctly returns None. gain_loss_pct (always computable from
    invested vs current value) is included on every group so the view stays
    useful even where a true annualised return can't be established yet.
    """
    from ..models import MutualFundScheme
    from apps.data.models import TLStockData
    from ..services.analytics.xirr_calculator import compute_products_xirr
    from ..serializers import _normalize_category

    group_by = request.query_params.get('group_by', 'fund')
    members = _resolve_members(request)
    products = list(InvestmentProduct.objects.filter(
        investment_account__family_member__in=members,
        is_active=True,
    ))
    if not products:
        return Response({'error': 'No holdings to analyse'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    isins = {p.isin for p in products if p.isin}
    schemes = {s.isin: s for s in MutualFundScheme.objects.filter(isin__in=isins)}
    equity_isins = {p.isin for p in products if p.isin and p.product_type == 'EQUITY'}
    stocks = {s.isin: s for s in TLStockData.objects.filter(isin__in=equity_isins)}

    def key_fund(p):
        label = p.name[:60]
        return (p.isin or f'p{p.id}'), label

    def key_amc(p):
        if p.product_type == 'MUTUAL_FUND':
            scheme = schemes.get(p.isin)
            amc = (scheme.amc if scheme and scheme.amc else '') or (p.extra_data or {}).get('amc', '')
            label = amc or 'Unknown AMC'
            return label, label
        label = 'Direct Equity' if p.product_type == 'EQUITY' else _RETURNS_TYPE_LABELS.get(p.product_type, p.product_type)
        return label, label

    def key_sector(p):
        if p.product_type == 'EQUITY':
            stock = stocks.get(p.isin)
            label = (stock.sector_name if stock and stock.sector_name else 'Unclassified')
            return label, label
        return 'Mutual Funds / Other', 'Mutual Funds / Other'

    def key_category(p):
        # Fund strategy/category (Flexi Cap, Mid Cap, Index Fund, Sectoral...)
        # — the meaningful grouping for mutual funds, unlike "sector" (a
        # stock-market concept a diversified fund doesn't have just one of).
        if p.product_type == 'MUTUAL_FUND':
            scheme = schemes.get(p.isin)
            sub_cat = scheme.sub_category if scheme and scheme.sub_category else ''
            if sub_cat:
                return sub_cat, sub_cat
            raw_cat = _normalize_category((p.extra_data or {}).get('category', ''))
            label = raw_cat or 'Uncategorised Fund'
            return label, label
        label = 'Direct Equity' if p.product_type == 'EQUITY' else _RETURNS_TYPE_LABELS.get(p.product_type, p.product_type)
        return label, label

    def key_asset_class(p):
        return p.product_type, _RETURNS_TYPE_LABELS.get(p.product_type, p.product_type)

    key_fn = {
        'fund': key_fund, 'amc': key_amc, 'sector': key_sector,
        'category': key_category, 'asset_class': key_asset_class,
    }.get(group_by, key_fund)

    buckets: dict = {}
    for p in products:
        key, label = key_fn(p)
        buckets.setdefault(key, {'label': label, 'products': []})
        buckets[key]['products'].append(p)

    groups = []
    for key, b in buckets.items():
        prods = b['products']
        invested = sum(float(x.invested_value) for x in prods)
        current = sum(float(x.current_value) for x in prods)
        xirr = compute_products_xirr(prods)
        groups.append({
            'key': key,
            'label': b['label'],
            'invested_value': round(invested, 2),
            'current_value': round(current, 2),
            'gain_loss': round(current - invested, 2),
            'gain_loss_pct': round((current - invested) / invested * 100, 2) if invested else 0,
            'xirr_pct': round(xirr * 100, 2) if xirr is not None else None,
            'holdings_count': len(prods),
            # Only meaningful for a single-holding group (e.g. group_by=fund)
            # — lets the UI offer "add missing purchase date" for that one
            # product specifically when XIRR isn't computable.
            'product_id': prods[0].id if len(prods) == 1 else None,
        })

    groups.sort(key=lambda g: (g['xirr_pct'] is None, -(g['xirr_pct'] or 0)))

    return Response({
        'group_by': group_by,
        'groups': groups,
        'total_invested': round(sum(g['invested_value'] for g in groups), 2),
        'total_current': round(sum(g['current_value'] for g in groups), 2),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tenor_ladder(request):
    """Maturity-bucket breakdown of debt-like holdings (FD/RD/Bond/SGB) using extra_data.maturity_date."""
    from datetime import date, datetime

    members = _resolve_members(request)
    products = InvestmentProduct.objects.filter(
        investment_account__family_member__in=members,
        is_active=True,
        product_type__in=['FD', 'RD', 'BOND', 'SGB'],
    )

    buckets = {'<1Y': 0.0, '1-3Y': 0.0, '3-5Y': 0.0, '5Y+': 0.0}
    total_debt_value = 0.0
    covered_value = 0.0
    weighted_years_sum = 0.0
    missing = 0
    today = date.today()

    for p in products:
        value = float(p.current_value)
        total_debt_value += value

        maturity_str = (p.extra_data or {}).get('maturity_date')
        if not maturity_str:
            missing += 1
            continue
        try:
            maturity = datetime.strptime(maturity_str, '%Y-%m-%d').date()
        except ValueError:
            missing += 1
            continue

        years = (maturity - today).days / 365.0
        if years <= 0:
            continue  # already matured — excluded from the forward-looking ladder
        bucket = '<1Y' if years < 1 else '1-3Y' if years < 3 else '3-5Y' if years < 5 else '5Y+'
        buckets[bucket] += value
        covered_value += value
        weighted_years_sum += years * value

    return Response({
        'buckets': {k: round(v, 2) for k, v in buckets.items()},
        'weighted_avg_tenor_years': round(weighted_years_sum / covered_value, 2) if covered_value else None,
        'covered_value': round(covered_value, 2),
        'total_debt_value': round(total_debt_value, 2),
        'holdings_missing_maturity': missing,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def portfolio_trend(request):
    """Invested vs current value over time, summed across the given members' PortfolioSnapshots."""
    from ..models import PortfolioSnapshot

    members = _resolve_members(request)
    snapshots = PortfolioSnapshot.objects.filter(family_member__in=members).order_by('snapshot_date')

    by_date: dict = {}
    for s in snapshots:
        entry = by_date.setdefault(s.snapshot_date, {'invested': 0.0, 'current': 0.0})
        entry['invested'] += float(s.total_invested)
        entry['current'] += float(s.current_value)

    series = [
        {'date': str(d), 'invested': round(v['invested'], 2), 'current': round(v['current'], 2)}
        for d, v in sorted(by_date.items())
    ]
    return Response({'series': series})
