"""
API Views for Level 2 Deep-Dive Analysis

Includes automatic fresh Trendlyne data fetching before analysis
"""

import logging
import threading
from datetime import datetime

from django.db import models
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from apps.data.models import DeepDiveAnalysis
from apps.trading.level2_report_generator import Level2ReportGenerator
from apps.data.trendlyne import get_all_trendlyne_data

logger = logging.getLogger(__name__)


class FuturesDeepDiveView(APIView):
    """
    Generate Level 2 deep-dive analysis for a stock that PASSED Level 1

    AUTOMATIC FRESH DATA: Fetches latest Trendlyne data before analysis

    POST /api/trading/futures/deep-dive/
    Body:
    {
        "symbol": "RELIANCE",
        "expiry_date": "2024-01-25",
        "level1_results": {...}  # Full Level 1 results
    }

    Returns immediately with analysis_id and status='processing'
    Frontend should poll /api/trading/deep-dive/{id}/status/ for completion
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Initiate deep-dive analysis with fresh data"""
        symbol = request.data.get('symbol')
        expiry_date = request.data.get('expiry_date')
        level1_results = request.data.get('level1_results', {})

        # Validate inputs
        if not symbol or not expiry_date:
            return Response({
                'success': False,
                'error': 'symbol and expiry_date are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify Level 1 passed
        level1_verdict = level1_results.get('verdict')
        if level1_verdict != 'PASS':
            return Response({
                'success': False,
                'error': 'Deep-dive analysis only available for stocks that PASSED Level 1',
                'level1_verdict': level1_verdict
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            logger.info(f"🚀 Initiating Level 2 deep-dive for {symbol} (Expiry: {expiry_date})")

            # Create analysis record with PENDING status
            deep_dive = DeepDiveAnalysis.objects.create(
                symbol=symbol,
                expiry=expiry_date,
                level1_score=level1_results.get('composite_score', 0),
                level1_direction=level1_results.get('direction', 'NEUTRAL'),
                report={'status': 'PROCESSING', 'message': 'Fetching fresh Trendlyne data...'},
                user=request.user,
                decision='PENDING'
            )

            logger.info(f"Created analysis record (ID: {deep_dive.id}) with PROCESSING status")

            # Start background analysis task
            analysis_thread = threading.Thread(
                target=self._run_analysis_with_fresh_data,
                args=(deep_dive.id, symbol, expiry_date, level1_results),
                daemon=True
            )
            analysis_thread.start()

            # Return immediately with analysis ID
            return Response({
                'success': True,
                'analysis_id': deep_dive.id,
                'status': 'PROCESSING',
                'message': 'Deep-dive analysis initiated. Fetching fresh Trendlyne data...',
                'estimated_time': '60-120 seconds',
                'poll_url': f'/api/trading/deep-dive/{deep_dive.id}/status/'
            })

        except Exception as e:
            logger.error(f"Error initiating deep-dive analysis: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _run_analysis_with_fresh_data(self, analysis_id, symbol, expiry_date, level1_results):
        """
        Background task: Fetch fresh data and run analysis

        This runs in a separate thread to avoid blocking the API response
        """
        try:
            logger.info(f"[Thread] Starting background analysis for {symbol} (ID: {analysis_id})")

            # Get the analysis record
            deep_dive = DeepDiveAnalysis.objects.get(id=analysis_id)

            # Step 1: Fetch fresh Trendlyne data
            logger.info(f"[Thread] Step 1/3: Fetching fresh Trendlyne data for {symbol}...")
            deep_dive.report = {
                'status': 'PROCESSING',
                'message': 'Downloading latest Trendlyne data...',
                'progress': 33
            }
            deep_dive.save()

            try:
                # Fetch all Trendlyne data
                get_all_trendlyne_data()
                logger.info(f"[Thread] ✅ Fresh Trendlyne data downloaded successfully")
            except Exception as e:
                logger.warning(f"[Thread] ⚠️  Trendlyne data fetch failed: {e}. Proceeding with existing data.")

            # Step 2: Generate comprehensive analysis
            logger.info(f"[Thread] Step 2/3: Analyzing {symbol} across all dimensions...")
            deep_dive.report = {
                'status': 'PROCESSING',
                'message': 'Running comprehensive multi-factor analysis...',
                'progress': 66
            }
            deep_dive.save()

            report_generator = Level2ReportGenerator(symbol, expiry_date, level1_results)
            report = report_generator.generate_report()

            # Step 3: Save final report
            logger.info(f"[Thread] Step 3/3: Finalizing report...")

            # Extract key metrics
            conviction_score = report['executive_summary']['conviction_score']
            risk_grade = report['detailed_analysis']['risk_assessment'].get('risk_grade', 'UNKNOWN')

            # Mark as complete
            report['status'] = 'COMPLETED'
            report['completed_at'] = datetime.now().isoformat()

            deep_dive.report = report
            deep_dive.conviction_score = conviction_score
            deep_dive.risk_grade = risk_grade
            deep_dive.save()

            logger.info(f"[Thread] ✅ Deep-dive analysis completed for {symbol} (ID: {analysis_id})")
            logger.info(f"[Thread] Conviction Score: {conviction_score}/100, Risk: {risk_grade}")

        except Exception as e:
            logger.error(f"[Thread] ❌ Error in background analysis: {e}", exc_info=True)

            # Mark as failed
            try:
                deep_dive = DeepDiveAnalysis.objects.get(id=analysis_id)
                deep_dive.report = {
                    'status': 'FAILED',
                    'error': str(e),
                    'message': f'Analysis failed: {str(e)[:200]}'
                }
                deep_dive.save()
            except Exception as save_error:
                logger.error(f"[Thread] Failed to update error status: {save_error}")


class DeepDiveStatusView(APIView):
    """
    Check status of deep-dive analysis (for polling)

    GET /api/trading/deep-dive/{analysis_id}/status/

    Returns:
    - PROCESSING: Still running (with progress updates)
    - COMPLETED: Analysis finished (includes full report)
    - FAILED: Analysis failed (includes error message)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, analysis_id):
        """Get analysis status"""
        try:
            deep_dive = DeepDiveAnalysis.objects.get(id=analysis_id, user=request.user)
        except DeepDiveAnalysis.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Analysis not found'
            }, status=status.HTTP_404_NOT_FOUND)

        report = deep_dive.report
        status_info = report.get('status', 'UNKNOWN')

        if status_info == 'PROCESSING':
            return Response({
                'success': True,
                'analysis_id': deep_dive.id,
                'status': 'PROCESSING',
                'message': report.get('message', 'Analysis in progress...'),
                'progress': report.get('progress', 0),
                'symbol': deep_dive.symbol,
                'expiry': deep_dive.expiry.isoformat()
            })

        elif status_info == 'COMPLETED':
            return Response({
                'success': True,
                'analysis_id': deep_dive.id,
                'status': 'COMPLETED',
                'report': report,
                'conviction_score': deep_dive.conviction_score,
                'risk_grade': deep_dive.risk_grade,
                'completed_at': report.get('completed_at'),
                'message': 'Analysis completed successfully'
            })

        elif status_info == 'FAILED':
            return Response({
                'success': False,
                'analysis_id': deep_dive.id,
                'status': 'FAILED',
                'error': report.get('error', 'Unknown error'),
                'message': report.get('message', 'Analysis failed')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        else:
            # Unknown status - return what we have
            return Response({
                'success': True,
                'analysis_id': deep_dive.id,
                'status': status_info,
                'report': report
            })


class DeepDiveDecisionView(APIView):
    """
    Record user decision on deep-dive analysis

    POST /api/trading/deep-dive/{analysis_id}/decision/
    Body:
    {
        "decision": "EXECUTED",  # EXECUTED, MODIFIED, REJECTED
        "notes": "Looks good, executing trade",
        "entry_price": 2850.50,
        "lot_size": 100
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, analysis_id):
        """Record decision"""
        try:
            deep_dive = DeepDiveAnalysis.objects.get(id=analysis_id, user=request.user)
        except DeepDiveAnalysis.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Analysis not found'
            }, status=status.HTTP_404_NOT_FOUND)

        decision = request.data.get('decision')
        notes = request.data.get('notes', '')

        if decision not in ['EXECUTED', 'MODIFIED', 'REJECTED']:
            return Response({
                'success': False,
                'error': 'Invalid decision. Must be EXECUTED, MODIFIED, or REJECTED'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update decision
        deep_dive.decision = decision
        deep_dive.decision_notes = notes
        deep_dive.decision_timestamp = timezone.now()

        # If executed, record trade details
        if decision == 'EXECUTED':
            entry_price = request.data.get('entry_price')
            lot_size = request.data.get('lot_size')

            if entry_price and lot_size:
                deep_dive.mark_executed(entry_price, lot_size)
            else:
                return Response({
                    'success': False,
                    'error': 'entry_price and lot_size required for EXECUTED decision'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            deep_dive.save()

        logger.info(f"Decision recorded for analysis {analysis_id}: {decision}")

        return Response({
            'success': True,
            'analysis_id': deep_dive.id,
            'decision': decision,
            'message': f'Decision recorded: {decision}'
        })


class TradeCloseView(APIView):
    """
    Close a trade and record exit price

    POST /api/trading/deep-dive/{analysis_id}/close/
    Body:
    {
        "exit_price": 2920.75
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, analysis_id):
        """Close trade"""
        try:
            deep_dive = DeepDiveAnalysis.objects.get(
                id=analysis_id,
                user=request.user,
                trade_executed=True
            )
        except DeepDiveAnalysis.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Executed trade not found'
            }, status=status.HTTP_404_NOT_FOUND)

        exit_price = request.data.get('exit_price')
        if not exit_price:
            return Response({
                'success': False,
                'error': 'exit_price is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Close trade
        deep_dive.close_trade(exit_price)

        logger.info(f"Trade closed for analysis {analysis_id}: P&L = ₹{deep_dive.pnl} ({deep_dive.pnl_pct}%)")

        return Response({
            'success': True,
            'analysis_id': deep_dive.id,
            'entry_price': float(deep_dive.entry_price),
            'exit_price': float(deep_dive.exit_price),
            'pnl': float(deep_dive.pnl),
            'pnl_pct': float(deep_dive.pnl_pct),
            'message': 'Trade closed successfully'
        })


class DeepDiveHistoryView(APIView):
    """
    Get deep-dive analysis history for user

    GET /api/trading/deep-dive/history/?symbol=RELIANCE&decision=EXECUTED
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get history"""
        # Filter parameters
        symbol = request.query_params.get('symbol')
        decision = request.query_params.get('decision')
        limit = int(request.query_params.get('limit', 20))

        # Build query
        query = DeepDiveAnalysis.objects.filter(user=request.user)

        if symbol:
            query = query.filter(symbol__iexact=symbol)
        if decision:
            query = query.filter(decision=decision)

        # Get results
        analyses = query[:limit]

        # Serialize
        results = []
        for analysis in analyses:
            results.append({
                'id': analysis.id,
                'symbol': analysis.symbol,
                'expiry': analysis.expiry.isoformat(),
                'created_at': analysis.created_at.isoformat(),
                'level1_score': analysis.level1_score,
                'conviction_score': analysis.conviction_score,
                'decision': analysis.decision,
                'trade_executed': analysis.trade_executed,
                'pnl': float(analysis.pnl) if analysis.pnl else None,
                'pnl_pct': float(analysis.pnl_pct) if analysis.pnl_pct else None
            })

        return Response({
            'success': True,
            'count': len(results),
            'results': results
        })


class PerformanceMetricsView(APIView):
    """
    Get performance metrics for deep-dive analyses

    GET /api/trading/deep-dive/performance/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get performance metrics"""
        user_analyses = DeepDiveAnalysis.objects.filter(user=request.user)

        # Overall stats
        total_analyses = user_analyses.count()
        executed_trades = user_analyses.filter(trade_executed=True)
        executed_count = executed_trades.count()

        # Calculate metrics
        if total_analyses > 0:
            execution_rate = (executed_count / total_analyses) * 100
        else:
            execution_rate = 0

        # Trade performance
        closed_trades = executed_trades.filter(exit_price__isnull=False)
        winning_trades = closed_trades.filter(pnl__gt=0)
        losing_trades = closed_trades.filter(pnl__lt=0)

        if closed_trades.count() > 0:
            win_rate = (winning_trades.count() / closed_trades.count()) * 100
            avg_win = winning_trades.aggregate(models.Avg('pnl_pct'))['pnl_pct__avg'] or 0
            avg_loss = losing_trades.aggregate(models.Avg('pnl_pct'))['pnl_pct__avg'] or 0
            total_pnl = closed_trades.aggregate(models.Sum('pnl'))['pnl__sum'] or 0
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            total_pnl = 0

        # Decision breakdown
        decisions = user_analyses.values('decision').annotate(
            count=models.Count('id')
        )

        return Response({
            'success': True,
            'metrics': {
                'total_analyses': total_analyses,
                'executed_trades': executed_count,
                'execution_rate': round(execution_rate, 2),
                'closed_trades': closed_trades.count(),
                'open_trades': executed_trades.filter(exit_price__isnull=True).count(),
                'win_rate': round(win_rate, 2),
                'avg_win_pct': round(avg_win, 2),
                'avg_loss_pct': round(avg_loss, 2),
                'total_pnl': round(float(total_pnl), 2),
                'decisions': list(decisions)
            }
        })
