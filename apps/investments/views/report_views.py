import logging
import secrets
from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import HttpResponse
from ..models import FamilyMember, PortfolioGroup
from ..tasks import generate_report_task

logger = logging.getLogger('apps.investments')

REPORT_TOKEN_TTL = 600  # 10 minutes


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_report(request):
    report_type = request.data.get('type', 'pdf')
    report_name = request.data.get('report_type', 'NET_WORTH')
    member_id = request.data.get('member_id')
    group_id = request.data.get('group_id')

    if member_id:
        try:
            FamilyMember.objects.get(pk=member_id, user=request.user)
        except FamilyMember.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

    if member_id:
        try:
            FamilyMember.objects.get(pk=member_id, user=request.user)
        except FamilyMember.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

    token = secrets.token_urlsafe(32)
    download_url = f'/investments/api/reports/download/{token}/'
    try:
        generate_report_task.delay(
            token=token,
            report_format=report_type.lower(),
            report_name=report_name,
            member_id=member_id,
            group_id=group_id,
            user_id=request.user.id,
        )
    except Exception as e:
        # Broker unavailable — generate synchronously and return download URL immediately.
        logger.warning('Celery broker unavailable, generating report synchronously: %s', e)
        try:
            from apps.investments.tasks import generate_report_task as task_fn
            task_fn(
                token=token,
                report_format=report_type.lower(),
                report_name=report_name,
                member_id=member_id,
                group_id=group_id,
                user_id=request.user.id,
            )
            return Response({'token': token, 'status': 'ready', 'download_url': download_url})
        except Exception as sync_err:
            logger.error('Synchronous report generation failed: %s', sync_err)
            return Response({'error': str(sync_err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({'token': token, 'status': 'generating', 'download_url': download_url})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_report(request, token):
    cache_key = f'inv:report:{token}'
    report_data = cache.get(cache_key)
    if not report_data:
        return Response(
            {'error': 'Report not ready or token expired'},
            status=status.HTTP_404_NOT_FOUND,
        )

    content_type = report_data.get('content_type', 'application/pdf')
    filename = report_data.get('filename', 'report.pdf')
    content = report_data.get('content')

    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    cache.delete(cache_key)
    return response
