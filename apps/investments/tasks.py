from __future__ import annotations
import logging
import tempfile
import os
from celery import shared_task
from django.contrib.auth.models import User
from django.core.cache import cache

logger = logging.getLogger('apps.investments')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def parse_cas_upload_task(self, upload_id: int, password: str):
    """Parse a CAS PDF file and create accounts/products/transactions."""
    from apps.investments.models import CASUpload, FamilyMember, InvestmentAccount, InvestmentProduct, Transaction
    from apps.investments.services.encryption import decrypt_bytes
    from apps.investments.services.cas_parser.nsdl_parser import parse_nsdl_cas
    from apps.investments.services.cas_parser.cams_parser import parse_cams_cas
    from apps.investments.services.cas_parser.kfintech_parser import parse_kfintech_cas
    from apps.investments.services.mfapi_client import MFAPIClient
    from datetime import date

    try:
        upload = CASUpload.objects.get(pk=upload_id)
    except CASUpload.DoesNotExist:
        logger.error('CAS upload %d not found', upload_id)
        return

    upload.parse_status = 'PROCESSING'
    upload.save(update_fields=['parse_status'])

    try:
        # Decrypt and write to temp file
        raw_bytes = bytes(upload.encrypted_content)
        decrypted = decrypt_bytes(raw_bytes)

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(decrypted)
            tmp_path = tmp.name

        try:
            # Parse based on CAS type
            if upload.cas_type == 'NSDL':
                cas_data = parse_nsdl_cas(tmp_path, password)
            elif upload.cas_type == 'CAMS':
                cas_data = parse_cams_cas(tmp_path, password)
            elif upload.cas_type == 'KFINTECH':
                cas_data = parse_kfintech_cas(tmp_path, password)
            else:
                cas_data = parse_nsdl_cas(tmp_path, password)
        finally:
            os.unlink(tmp_path)

        member = upload.family_member
        info = cas_data.account_info

        # Update member PAN info if parsed
        if info.pan_masked and not member.pan_masked:
            member.pan_masked = info.pan_masked
            member.save(update_fields=['pan_masked'])

        # Update statement period
        if info.statement_month:
            upload.statement_month = info.statement_month
            upload.statement_year = info.statement_year

        # Create or update InvestmentAccount (DEMAT for NSDL)
        account_defaults = {
            'institution_name': info.dp_name or '',
            'dp_id': info.dp_id or '',
            'client_id': info.client_id or '',
            'depository': info.depository or 'NSDL',
            'account_type': 'DEMAT' if upload.cas_type == 'NSDL' else 'MF_FOLIO',
            'nominee_registered': info.nominee_registered,
            'data_source': 'CAS',
        }

        if upload.cas_type == 'NSDL' and info.dp_id and info.client_id:
            account, _ = InvestmentAccount.objects.get_or_create(
                family_member=member,
                dp_id=info.dp_id,
                client_id=info.client_id,
                defaults={**account_defaults, 'account_name': f'{info.dp_name or "Demat"} ({info.client_id})'},
            )
        else:
            account, _ = InvestmentAccount.objects.get_or_create(
                family_member=member,
                account_type='MF_FOLIO',
                data_source='CAS',
                defaults={**account_defaults, 'account_name': f'{upload.cas_type} MF Folio'},
            )

        accounts_created = 1
        products_created = 0
        transactions_created = 0

        # Build ISIN → scheme_code map for MF products
        mf_client = MFAPIClient()
        isin_map = mf_client.get_isin_map()

        # Create holdings as InvestmentProduct records
        for holding in cas_data.holdings:
            product_type_map = {
                'E': 'EQUITY',
                'M': 'MUTUAL_FUND',
                'SGB': 'SGB',
                'C': 'BOND',
                'G': 'BOND',
                'I': 'BOND',
                'P': 'EQUITY',
                'A': 'MUTUAL_FUND',
            }
            product_type = product_type_map.get(holding.asset_class, 'OTHER')

            extra = dict(holding.extra_data)
            # Always persist quantity/units from the CAS holding so price updaters
            # can compute current_value = quantity × live_price without re-parsing.
            if holding.quantity:
                key = 'units' if product_type == 'MUTUAL_FUND' else 'shares'
                extra[key] = holding.quantity
            if holding.current_price:
                extra['current_price'] = holding.current_price
            if holding.avg_cost_per_unit:
                extra['avg_cost_per_unit'] = holding.avg_cost_per_unit

            if product_type == 'MUTUAL_FUND':
                scheme_code = isin_map.get(holding.isin)
                if scheme_code:
                    extra['scheme_code'] = scheme_code

            product, created = InvestmentProduct.objects.update_or_create(
                investment_account=account,
                isin=holding.isin,
                product_type=product_type,
                defaults={
                    'name': holding.security_name,
                    'data_source': 'CAS',
                    'is_active': True,
                    'invested_value': holding.total_cost or holding.current_value,
                    'current_value': holding.current_value,
                    'as_of_date': date.today(),
                    'extra_data': extra,
                },
            )
            if created:
                products_created += 1

        # Create transactions
        for txn in cas_data.transactions:
            product = InvestmentProduct.objects.filter(
                investment_account=account,
                isin=txn.isin,
            ).first()

            _, created = Transaction.objects.get_or_create(
                investment_account=account,
                isin=txn.isin,
                transaction_date=txn.transaction_date,
                order_no=txn.order_no,
                defaults={
                    'product': product,
                    'cas_upload': upload,
                    'security_name': txn.security_name,
                    'description': txn.description,
                    'transaction_type': txn.transaction_type,
                    'units_debit': txn.debit,
                    'units_credit': txn.credit,
                    'units_balance': txn.closing_balance,
                    'amount': txn.amount,
                    'nav_at_transaction': txn.nav_at_transaction,
                },
            )
            if created:
                transactions_created += 1

        upload.accounts_created = accounts_created
        upload.products_created = products_created
        upload.transactions_created = transactions_created
        upload.parse_status = 'DONE'
        upload.save()

        logger.info(
            'CAS upload %d parsed: %d accounts, %d products, %d transactions',
            upload_id, accounts_created, products_created, transactions_created,
        )

        # Trigger analytics computation — best-effort; don't fail the parse if broker is down.
        try:
            compute_portfolio_analytics_task.delay(member.id)
        except Exception as broker_err:
            logger.warning('Could not queue analytics task after parse: %s', broker_err)

    except Exception as e:
        logger.exception('CAS parse failed for upload %d: %s', upload_id, e)
        upload.parse_status = 'ERROR'
        upload.parse_error = str(e)[:500]
        upload.save(update_fields=['parse_status', 'parse_error'])
        raise self.retry(exc=e)


@shared_task
def import_equity_csv_task(account_id: int, csv_content: str):
    """Import equity holdings from a CSV string."""
    from apps.investments.models import InvestmentAccount
    from apps.investments.services.csv_importer import import_equity_csv

    try:
        account = InvestmentAccount.objects.get(pk=account_id)
        result = import_equity_csv(account, csv_content)
        logger.info('CSV import for account %d: %s', account_id, result)
        compute_portfolio_analytics_task.delay(account.family_member_id)
        return result
    except Exception as e:
        logger.error('CSV import failed for account %d: %s', account_id, e)
        raise


@shared_task
def sync_mf_scheme_list_task():
    """Fetch all MFAPI schemes and build/update the ISIN map in Redis."""
    from apps.investments.services.mfapi_client import MFAPIClient
    from apps.investments.models import MutualFundScheme
    from django.utils import timezone

    client = MFAPIClient()
    schemes = client.get_scheme_list()

    updated = 0
    for s in schemes:
        code = s.get('schemeCode')
        name = s.get('schemeName', '')
        isin_growth = s.get('isinGrowth', '')
        isin_div = s.get('isinDividend', '')

        for isin in filter(None, [isin_growth, isin_div]):
            MutualFundScheme.objects.update_or_create(
                isin=isin,
                defaults={
                    'scheme_code': code,
                    'scheme_name': name,
                    'last_synced': timezone.now(),
                },
            )
            updated += 1

    logger.info('MFAPI scheme list sync: %d ISIN records upserted', updated)
    return updated


@shared_task
def sync_nav_history_task(scheme_code: int, isin: str):
    """Fetch and store full NAV history for one scheme."""
    from apps.investments.services.mfapi_client import MFAPIClient
    client = MFAPIClient()
    return client.sync_nav_history_to_db(scheme_code, isin)


@shared_task
def update_all_prices_task(user_id: int | None = None, member_ids: list | None = None):
    """Update NAVs, equity prices, and gold prices; then recompute analytics."""
    from apps.investments.services.price_updater import update_mf_navs, update_equity_prices, update_gold_prices

    mf_updated = update_mf_navs(member_ids)
    eq_updated = update_equity_prices(member_ids)
    gold_updated = update_gold_prices()

    logger.info('Price update: MF=%d, Equity=%d, Gold=%d', mf_updated, eq_updated, gold_updated)

    # Re-run analytics for affected members — best-effort; don't fail if broker is down.
    def _queue_or_run(mid):
        try:
            compute_portfolio_analytics_task.delay(mid)
        except Exception:
            try:
                compute_portfolio_analytics_task(mid)
            except Exception as e:
                logger.warning('Analytics task failed for member %d: %s', mid, e)

    if member_ids:
        for mid in member_ids:
            _queue_or_run(mid)
    elif user_id:
        from apps.investments.models import FamilyMember
        for member in FamilyMember.objects.filter(user_id=user_id):
            _queue_or_run(member.id)

    return {'mf': mf_updated, 'equity': eq_updated, 'gold': gold_updated}


@shared_task
def accrue_fd_interest_task():
    """Recompute current_value for all FD and RD products."""
    from apps.investments.models import InvestmentProduct
    from apps.investments.services.valuation_engine import compute_product_value

    updated = 0
    for product in InvestmentProduct.objects.filter(product_type__in=['FD', 'RD'], is_active=True):
        compute_product_value(product)
        updated += 1
    logger.info('FD/RD interest accrual: %d products updated', updated)
    return updated


@shared_task
def compute_portfolio_analytics_task(member_id: int):
    """Compute XIRR, health score, and save portfolio snapshot for a family member."""
    from apps.investments.models import FamilyMember, InvestmentProduct, PortfolioSnapshot
    from apps.investments.services.analytics.xirr_calculator import compute_product_xirr
    from apps.investments.services.analytics.health_scorer import compute_health_score
    from apps.investments.services.analytics.insights_generator import generate_insights
    from django.utils import timezone
    from datetime import date

    try:
        member = FamilyMember.objects.get(pk=member_id)
    except FamilyMember.DoesNotExist:
        return

    products = InvestmentProduct.objects.filter(
        investment_account__family_member=member,
        is_active=True,
    )

    # Update XIRR per product
    for product in products:
        try:
            xirr = compute_product_xirr(product)
            if xirr is not None:
                product.xirr = xirr
                product.save(update_fields=['xirr'])
        except Exception as e:
            logger.debug('XIRR failed for product %d: %s', product.id, e)

    # Build type breakdown
    type_vals = {}
    total_invested = 0
    total_current = 0
    for p in products:
        type_vals[p.product_type] = type_vals.get(p.product_type, 0) + float(p.current_value)
        total_invested += float(p.invested_value)
        total_current += float(p.current_value)

    gain = total_current - total_invested
    gain_pct = (gain / total_invested * 100) if total_invested else 0

    PortfolioSnapshot.objects.update_or_create(
        family_member=member,
        portfolio_group=None,
        snapshot_date=date.today(),
        defaults={
            'total_invested': total_invested,
            'current_value': total_current,
            'gain_loss': gain,
            'gain_loss_pct': gain_pct,
            'net_worth_breakdown': type_vals,
            'asset_allocation': {k: round(v / total_current * 100, 2) for k, v in type_vals.items()} if total_current else {},
        },
    )

    # Recompute health score
    try:
        compute_health_score(family_member=member)
    except Exception as e:
        logger.warning('Health score failed for member %d: %s', member_id, e)

    logger.info('Portfolio analytics updated for member %d', member_id)


@shared_task
def compute_health_scores_all_task():
    """Recompute health scores for all family members."""
    from apps.investments.models import FamilyMember
    for member in FamilyMember.objects.all():
        try:
            compute_portfolio_analytics_task.delay(member.id)
        except Exception as e:
            logger.error('Health score task failed for member %d: %s', member.id, e)


@shared_task
def generate_report_task(token: str, report_format: str, report_name: str,
                          member_id: int | None, group_id: int | None, user_id: int):
    """Generate a PDF or Excel report and cache it for download."""
    from apps.investments.models import FamilyMember, PortfolioGroup

    member = None
    group = None
    try:
        if member_id:
            member = FamilyMember.objects.get(pk=member_id)
        if group_id:
            group = PortfolioGroup.objects.get(pk=group_id)
    except Exception as e:
        logger.error('Report entity not found: %s', e)
        return

    try:
        if report_format == 'excel':
            from apps.investments.services.reports.excel_generator import generate_excel_report
            content, filename = generate_excel_report(member=member, group=group, report_name=report_name)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            from apps.investments.services.reports.pdf_generator import generate_pdf_report
            content, filename = generate_pdf_report(member=member, group=group, report_name=report_name)
            content_type = 'application/pdf'

        cache.set(f'inv:report:{token}', {
            'content': content,
            'filename': filename,
            'content_type': content_type,
        }, timeout=600)

        logger.info('Report %s generated, token=%s', report_name, token)
    except Exception as e:
        logger.error('Report generation failed: %s', e)
