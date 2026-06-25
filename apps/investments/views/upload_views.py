import logging
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import CASUpload, FamilyMember, CASType, UserCASPassword
from ..serializers import CASUploadSerializer, UserCASPasswordSerializer
from ..services.encryption import encrypt_bytes
from ..tasks import parse_cas_upload_task, import_equity_csv_task

logger = logging.getLogger('apps.investments')


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
        upload.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

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
