import logging
from datetime import date
from decimal import Decimal
from django.db import transaction
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import CASUpload, FamilyMember, CASType, UserCASPassword, InvestmentProduct, Transaction
from ..serializers import CASUploadSerializer, UserCASPasswordSerializer
from ..services.encryption import encrypt_bytes
from ..tasks import parse_cas_upload_task, import_equity_csv_task, run_cas_parse

logger = logging.getLogger('apps.investments')

_SPREADSHEET_EXTS = {'.xls', '.xlsx', '.csv'}
_BROKER_HINTS = [
    ('KOTAK', 'Kotak Securities'), ('PORTFOLIOEQTSUMMARY', 'Kotak Securities'),
    ('ICICI', 'ICICI Direct'),     ('ICICIDIRECT', 'ICICI Direct'),
    ('ZERODHA', 'Zerodha'),        ('KITE', 'Zerodha'),
    ('HDFC', 'HDFC Sky'),          ('ANGEL', 'Angel One'),
    ('GROWW', 'Groww'),            ('UPSTOX', 'Upstox'),
    ('AXIS', 'Axis Direct'),       ('MOTILAL', 'Motilal Oswal'),
    ('5PAISA', '5paisa'),          ('SBISEC', 'SBI Securities'),
]

def _detect_broker(filename: str) -> str:
    n = filename.upper().replace('-', '').replace('_', '')
    for key, name in _BROKER_HINTS:
        if key in n:
            return name
    return 'Demat Account'


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def cas_upload_list(request):
    if request.method == 'GET':
        uploads = CASUpload.objects.filter(family_member__user=request.user)
        member_id = request.query_params.get('member_id')
        if member_id:
            uploads = uploads.filter(family_member_id=member_id)
        return Response(CASUploadSerializer(uploads, many=True).data)

    # POST — upload new CAS file
    member_id = request.data.get('member_id')
    password = request.data.get('password', '')
    cas_type = request.data.get('cas_type', CASType.NSDL)
    uploaded_file = request.FILES.get('file')

    if not member_id or not uploaded_file:
        return Response({'error': 'member_id and file are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        member = FamilyMember.objects.get(pk=member_id, user=request.user)
    except FamilyMember.DoesNotExist:
        return Response({'error': 'Family member not found'}, status=status.HTTP_404_NOT_FOUND)

    raw_bytes = uploaded_file.read()
    encrypted = encrypt_bytes(raw_bytes)

    upload = CASUpload.objects.create(
        family_member=member,
        uploaded_by=request.user,
        cas_type=cas_type,
        original_filename=uploaded_file.name,
        encrypted_content=encrypted,
        parse_status='PENDING',
    )

    # Collect saved passwords to try automatically (in order)
    saved_passwords = list(
        UserCASPassword.objects.filter(user=request.user).values_list('password', flat=True)
    )

    # Fire async parse task — passwords passed to task, not stored in upload record
    try:
        parse_cas_upload_task.delay(upload.id, password, saved_passwords)
        logger.info('CAS parse task queued: upload=%d member=%s', upload.id, member.name)
    except Exception as e:
        logger.error('Failed to queue CAS parse task: %s', e)

    return Response(CASUploadSerializer(upload).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def cas_upload_detail(request, pk):
    try:
        upload = CASUpload.objects.get(pk=pk, family_member__user=request.user)
    except CASUpload.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        cascade = str(request.query_params.get('cascade', '')).lower() in ('true', '1', 'yes')
        products_archived = 0
        transactions_deleted = 0
        family_member_id = upload.family_member_id

        with transaction.atomic():
            if cascade:
                products_archived = InvestmentProduct.objects.filter(
                    source_upload=upload, is_active=True,
                ).update(is_active=False)
                transactions_deleted, _ = Transaction.objects.filter(cas_upload=upload).delete()
            upload.delete()

        if cascade:
            try:
                from ..tasks import compute_portfolio_analytics_task
                compute_portfolio_analytics_task.delay(family_member_id)
            except Exception:
                pass

        return Response({
            'products_archived': products_archived,
            'transactions_deleted': transactions_deleted,
        }, status=status.HTTP_200_OK)

    return Response(CASUploadSerializer(upload).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def cas_reparse(request, pk):
    try:
        upload = CASUpload.objects.get(pk=pk, family_member__user=request.user)
    except CASUpload.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    password = request.data.get('password', '')
    saved_passwords = list(
        UserCASPassword.objects.filter(user=request.user).values_list('password', flat=True)
    )
    upload.parse_status = 'PENDING'
    upload.parse_error = ''
    upload.save(update_fields=['parse_status', 'parse_error'])
    parse_cas_upload_task.delay(upload.id, password, saved_passwords)
    return Response({'status': 'reparse queued'})


class CASPasswordListCreateView(generics.ListCreateAPIView):
    """Manage saved CAS PDF passwords for auto-try on upload."""
    serializer_class = UserCASPasswordSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return UserCASPassword.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CASPasswordDetailView(generics.DestroyAPIView):
    serializer_class = UserCASPasswordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserCASPassword.objects.filter(user=self.request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def equity_csv_upload(request):
    account_id = request.data.get('account_id')
    csv_file = request.FILES.get('file')

    if not account_id or not csv_file:
        return Response({'error': 'account_id and file are required'}, status=status.HTTP_400_BAD_REQUEST)

    from ..models import InvestmentAccount
    try:
        account = InvestmentAccount.objects.get(pk=account_id, family_member__user=request.user)
    except InvestmentAccount.DoesNotExist:
        return Response({'error': 'Account not found'}, status=status.HTTP_404_NOT_FOUND)

    csv_bytes = csv_file.read()
    import_equity_csv_task.delay(account.id, csv_bytes.decode('utf-8'))
    return Response({'status': 'CSV import queued', 'account_id': account.id})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_account_csv(request, pk):
    """Delete all CSV-imported products from an account (pre-upload cleanup)."""
    from ..models import InvestmentAccount
    from ..services.portfolio_importer import clear_csv_products
    try:
        account = InvestmentAccount.objects.get(pk=pk, family_member__user=request.user)
    except InvestmentAccount.DoesNotExist:
        return Response({'error': 'Account not found'}, status=status.HTTP_404_NOT_FOUND)
    deleted = clear_csv_products(account)
    return Response({'deleted': deleted})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def smart_upload(request):
    """
    Single upload endpoint — auto-detects file type and routes appropriately.

    PDF  → encrypted, queued for async smart-parse (CAMS/KFintech/NSDL auto-detected).
    XLS/XLSX/CSV → synchronous equity portfolio import (broker auto-detected from filename/headers).

    Returns:
      PDF:         {mode:'pdf', id, status:'PENDING', poll_url}
      Spreadsheet: {mode:'spreadsheet', created, updated, skipped, errors, account_name}
    """
    member_id = request.data.get('member_id')
    uploaded_file = request.FILES.get('file')
    password = request.data.get('password', '')
    clear_before_import = str(request.data.get('clear_before_import', '')).lower() in ('true', '1', 'yes')

    if not member_id or not uploaded_file:
        return Response({'error': 'member_id and file are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        member = FamilyMember.objects.get(pk=member_id, user=request.user)
    except FamilyMember.DoesNotExist:
        return Response({'error': 'Family member not found'}, status=status.HTTP_404_NOT_FOUND)

    filename = uploaded_file.name
    ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    raw_bytes = uploaded_file.read()

    # Magic-byte override: treat as PDF even if extension says otherwise
    # (MF Central downloads PDFs with .xlsx extension)
    if raw_bytes[:4] == b'%PDF':
        ext = '.pdf'

    # ── Spreadsheet: synchronous ───────────────────────────────────────────
    if ext in _SPREADSHEET_EXTS:
        # MF Central CAS XLSX has a "Portfolio Details" sheet — detect and route specially
        if ext in ('.xlsx', '.xls'):
            try:
                import io, openpyxl
                wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True)
                is_mfcentral_cas = 'Portfolio Details' in wb.sheetnames
                wb.close()
            except Exception:
                is_mfcentral_cas = False
        else:
            is_mfcentral_cas = False

        if is_mfcentral_cas:
            from ..services.cas_parser.mfcentral_xlsx_parser import save_mfcentral_xlsx
            try:
                result = save_mfcentral_xlsx(member, raw_bytes, filename, request.user)
            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                logger.exception('MF Central XLSX import failed: %s', e)
                return Response({'error': f'Import failed: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            try:
                from ..tasks import compute_portfolio_analytics_task, sync_missing_mf_categories_task
                compute_portfolio_analytics_task.delay(member.id)
                sync_missing_mf_categories_task.delay(member_id=member.id)
            except Exception:
                pass

            return Response({
                'mode': 'pdf',   # same result shape as PDF CAS
                'id': result['upload_id'],
                'cas_type': 'CAMS',
                'products_created': result['products_created'],
                'products_updated': result['products_updated'],
                'transactions_created': result['transactions_created'],
                'parse_status': 'DONE',
            })

        from ..models import InvestmentAccount
        from ..services.portfolio_importer import import_portfolio_file

        broker_name = _detect_broker(filename)
        account, _ = InvestmentAccount.objects.get_or_create(
            family_member=member,
            account_type='DEMAT',
            institution_name=broker_name,
            defaults={'account_name': f'{broker_name} Demat', 'data_source': 'CSV'},
        )

        upload = CASUpload.objects.create(
            family_member=member,
            uploaded_by=request.user,
            cas_type='PORTFOLIO',
            original_filename=filename,
            parse_status='PROCESSING',
        )

        try:
            result = import_portfolio_file(account, raw_bytes, filename,
                                           clear_existing=clear_before_import, cas_upload=upload)
        except ValueError as e:
            upload.parse_status = 'ERROR'
            upload.parse_error = str(e)[:500]
            upload.save(update_fields=['parse_status', 'parse_error'])
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception('Portfolio import failed: %s', e)
            upload.parse_status = 'ERROR'
            upload.parse_error = str(e)[:500]
            upload.save(update_fields=['parse_status', 'parse_error'])
            return Response({'error': f'Import failed: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        upload.parse_status = 'DONE'
        upload.products_created = result.get('created', 0)
        upload.products_updated = result.get('updated', 0)
        upload.save(update_fields=['parse_status', 'products_created', 'products_updated'])

        try:
            from ..tasks import compute_portfolio_analytics_task
            compute_portfolio_analytics_task.delay(member.id)
        except Exception:
            pass

        return Response({
            'mode': 'spreadsheet',
            'detected_broker': broker_name,
            'account_name': account.account_name,
            **result,
        })

    # ── PDF: synchronous CAS parse ────────────────────────────────────────
    encrypted = encrypt_bytes(raw_bytes)
    upload = CASUpload.objects.create(
        family_member=member,
        uploaded_by=request.user,
        cas_type='CAMS',       # corrected during parsing
        original_filename=filename,
        encrypted_content=encrypted,
        parse_status='PENDING',
    )

    saved_passwords = list(
        UserCASPassword.objects.filter(user=request.user).values_list('password', flat=True)
    )

    try:
        result = run_cas_parse(upload.id, password, saved_passwords)
        upload.refresh_from_db()
        return Response({
            'mode': 'pdf',
            'id': upload.id,
            'cas_type': upload.cas_type,
            'products_created': result['products_created'],
            'products_updated': result['products_updated'],
            'transactions_created': result['transactions_created'],
            'parse_status': 'DONE',
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def portfolio_file_upload(request):
    """
    Upload an equity portfolio export file (Kotak .xls TSV, XLSX, CSV).
    Upserts holdings into a DEMAT account; auto-creates account if not supplied.
    """
    member_id = request.data.get('member_id')
    account_id = request.data.get('account_id')
    broker_name = (request.data.get('broker_name') or 'Demat Account').strip()
    portfolio_file = request.FILES.get('file')

    if not member_id or not portfolio_file:
        return Response({'error': 'member_id and file are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        member = FamilyMember.objects.get(pk=member_id, user=request.user)
    except FamilyMember.DoesNotExist:
        return Response({'error': 'Family member not found'}, status=status.HTTP_404_NOT_FOUND)

    from ..models import InvestmentAccount

    if account_id:
        try:
            account = InvestmentAccount.objects.get(pk=account_id, family_member__user=request.user)
        except InvestmentAccount.DoesNotExist:
            return Response({'error': 'Account not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        account, _ = InvestmentAccount.objects.get_or_create(
            family_member=member,
            account_type='DEMAT',
            institution_name=broker_name,
            defaults={
                'account_name': f'{broker_name} Demat',
                'data_source': 'CSV',
            },
        )

    raw_bytes = portfolio_file.read()
    filename = portfolio_file.name

    upload = CASUpload.objects.create(
        family_member=member,
        uploaded_by=request.user,
        cas_type='PORTFOLIO',
        original_filename=filename,
        parse_status='PROCESSING',
    )

    try:
        from ..services.portfolio_importer import import_portfolio_file
        result = import_portfolio_file(account, raw_bytes, filename, cas_upload=upload)
    except ValueError as e:
        upload.parse_status = 'ERROR'
        upload.parse_error = str(e)[:500]
        upload.save(update_fields=['parse_status', 'parse_error'])
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception('Portfolio file import failed: %s', e)
        upload.parse_status = 'ERROR'
        upload.parse_error = str(e)[:500]
        upload.save(update_fields=['parse_status', 'parse_error'])
        return Response({'error': f'Import failed: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    upload.parse_status = 'DONE'
    upload.products_created = result.get('created', 0)
    upload.products_updated = result.get('updated', 0)
    upload.save(update_fields=['parse_status', 'products_created', 'products_updated'])

    try:
        from ..tasks import compute_portfolio_analytics_task
        compute_portfolio_analytics_task.delay(member.id)
    except Exception:
        pass

    return Response({
        'account_id': account.id,
        'account_name': account.account_name,
        **result,
    })


# Asset type → (account_type, product_type)
_ASSET_MAP = {
    'PPF':           ('PPF', 'PPF'),
    'EPF':           ('EPF', 'EPF'),
    'NPS':           ('NPS', 'NPS'),
    'FD':            ('SAVINGS_BANK', 'FD'),
    'RD':            ('SAVINGS_BANK', 'RD'),
    'SAVINGS':       ('SAVINGS_BANK', 'SAVINGS'),
    'PHYSICAL_GOLD': ('PHYSICAL_GOLD', 'PHYSICAL_GOLD'),
    'REAL_ESTATE':   ('REAL_ESTATE', 'REAL_ESTATE'),
    'BOND':          ('SAVINGS_BANK', 'BOND'),
    'SGB':           ('DEMAT', 'SGB'),
    'MUTUAL_FUND':   ('MF_FOLIO', 'MUTUAL_FUND'),
    'EQUITY':        ('DEMAT', 'EQUITY'),
    'CRYPTO':        ('CUSTOM', 'CRYPTO'),
    'CASH':          ('SAVINGS_BANK', 'CASH'),
    'OTHER':         ('CUSTOM', 'OTHER'),
}


@api_view(['POST', 'GET'])
@permission_classes([IsAuthenticated])
def manual_asset_entry(request):
    """
    GET  — list manual assets for the user (product_type filter optional).
    POST — create or update a manual asset (PPF, Gold, Real Estate, FD, etc.).

    POST body:
      member_id, asset_type, name, institution (opt), account_number (opt),
      invested_value, current_value (defaults to invested_value), as_of_date (opt),
      notes (opt), extra_data (opt JSON)
    """
    from ..models import InvestmentAccount, InvestmentProduct, DataSource
    from ..serializers import InvestmentProductSerializer

    if request.method == 'GET':
        qs = InvestmentProduct.objects.filter(
            investment_account__family_member__user=request.user,
            data_source=DataSource.MANUAL,
            is_active=True,
        ).select_related('investment_account__family_member')
        member_id = request.query_params.get('member_id')
        if member_id:
            qs = qs.filter(investment_account__family_member_id=member_id)
        return Response(InvestmentProductSerializer(qs, many=True).data)

    # POST
    member_id = request.data.get('member_id')
    asset_type = (request.data.get('asset_type') or '').upper()
    name = (request.data.get('name') or '').strip()
    institution = (request.data.get('institution') or '').strip()
    account_number = (request.data.get('account_number') or '').strip()
    invested_value = request.data.get('invested_value', 0)
    current_value = request.data.get('current_value')
    as_of_date_str = request.data.get('as_of_date') or date.today().isoformat()
    investment_date_str = request.data.get('investment_date') or as_of_date_str
    notes = (request.data.get('notes') or '').strip()
    extra_data = request.data.get('extra_data') or {}

    if current_value is None:
        current_value = invested_value

    if not member_id or not asset_type or not name:
        return Response(
            {'error': 'member_id, asset_type, and name are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if asset_type not in _ASSET_MAP:
        return Response(
            {'error': f'Unknown asset_type. Valid: {list(_ASSET_MAP)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        member = FamilyMember.objects.get(pk=member_id, user=request.user)
    except FamilyMember.DoesNotExist:
        return Response({'error': 'Family member not found'}, status=status.HTTP_404_NOT_FOUND)

    account_type, product_type = _ASSET_MAP[asset_type]

    account_lookup: dict = {'family_member': member, 'account_type': account_type}
    if institution:
        account_lookup['institution_name'] = institution

    account_name = institution or name
    if asset_type not in ('PPF', 'EPF', 'NPS', 'PHYSICAL_GOLD', 'REAL_ESTATE'):
        account_name = f'{institution or ""} {asset_type}'.strip()

    account, _ = InvestmentAccount.objects.get_or_create(
        **account_lookup,
        defaults={
            'account_name': account_name,
            'account_number_masked': account_number,
            'data_source': DataSource.MANUAL,
            'notes': notes,
        },
    )

    product, created = InvestmentProduct.objects.update_or_create(
        investment_account=account,
        product_type=product_type,
        name=name,
        defaults={
            'isin': '',
            'data_source': DataSource.MANUAL,
            'is_active': True,
            'invested_value': Decimal(str(invested_value)),
            'current_value': Decimal(str(current_value)),
            'as_of_date': as_of_date_str,
            'investment_date': investment_date_str,
            'extra_data': extra_data,
            'notes': notes,
        },
    )

    try:
        from ..tasks import compute_portfolio_analytics_task
        compute_portfolio_analytics_task.delay(member.id)
    except Exception:
        pass

    return Response(
        {
            'created': created,
            'product': InvestmentProductSerializer(product).data,
            'account_id': account.id,
            'account_name': account.account_name,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def manual_asset_detail(request, pk):
    """Update current_value/notes of a manual asset, or soft-delete it."""
    from ..models import InvestmentProduct, DataSource
    from ..serializers import InvestmentProductSerializer

    try:
        product = InvestmentProduct.objects.get(
            pk=pk,
            investment_account__family_member__user=request.user,
            data_source=DataSource.MANUAL,
        )
    except InvestmentProduct.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        product.is_active = False
        product.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PUT — partial update
    for field in ('current_value', 'invested_value', 'as_of_date', 'investment_date', 'notes', 'name'):
        if field in request.data:
            setattr(product, field, request.data[field])
    if 'extra_data' in request.data:
        product.extra_data = {**product.extra_data, **request.data['extra_data']}
    product.save()

    try:
        from ..tasks import compute_portfolio_analytics_task
        compute_portfolio_analytics_task.delay(product.investment_account.family_member_id)
    except Exception:
        pass

    return Response(InvestmentProductSerializer(product).data)
