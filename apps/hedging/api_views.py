"""
REST API endpoints for the Covered Call Protection ("Cover Position") feature.

All endpoints are web-UI driven and require an authenticated user — no
Celery task, cron, or signal handler is permitted to call the
place/roll/close execution paths behind these views (see execution_service.py).

Mirrors the @csrf_exempt + @login_required convention already used by the
existing live-position endpoints in apps.trading.api_views (e.g.
close_live_position) for consistency within this codebase.
"""
import json
import logging
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.hedging.models import HEDGE_STATUS_ACTIVE, HedgeAuditLog, HedgeLeg, HedgePosition
from apps.hedging.services import chain_service, execution_service, payoff_engine
from apps.hedging.services.recommendation_engine import CoveredCallRecommendationEngine
from apps.hedging.services.validators import HedgeValidationError

logger = logging.getLogger(__name__)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, '%Y-%m-%d').date()


def _json_body(request) -> dict:
    try:
        return json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return {}


def _error_response(exc, status=400):
    if isinstance(exc, HedgeValidationError):
        return JsonResponse({'success': False, 'error': exc.message, 'code': exc.code}, status=status)
    return JsonResponse({'success': False, 'error': str(exc)}, status=status)


def _serialize_chain_row(row: dict) -> dict:
    return {
        'strike': float(row['strike']),
        'ltp': float(row['ltp'] or 0),
        'bid': float(row['bid'] or 0),
        'ask': float(row['ask'] or 0),
        'open_interest': int(row['open_interest'] or 0),
        'volume': int(row['volume'] or 0),
        'delta': float(row['delta']) if row.get('delta') is not None else None,
        'gamma': float(row['gamma']) if row.get('gamma') is not None else None,
        'theta': float(row['theta']) if row.get('theta') is not None else None,
        'vega': float(row['vega']) if row.get('vega') is not None else None,
        'iv': float(row['iv']) if row.get('iv') is not None else None,
    }


def _serialize_score(score) -> dict:
    if score is None:
        return None
    return {
        'strike': score.strike,
        'premium': score.premium,
        'delta': score.delta,
        'theta': score.theta,
        'open_interest': score.open_interest,
        'composite_score': round(score.composite_score, 4),
        'effective_breakeven': round(score.effective_breakeven, 2),
        'probability_otm_pct': round(score.probability_otm_pct, 1),
        'explanation': score.explanation,
    }


# ─────────────────────────────────────────────────────────────────────────

@require_GET
@login_required
def chain_and_recommendations(request):
    try:
        broker = request.GET.get('broker', '').lower()
        underlying_symbol = request.GET.get('symbol', '')
        futures_expiry = _parse_date(request.GET.get('futures_expiry'))
        option_expiry_raw = request.GET.get('option_expiry')
        option_expiry = _parse_date(option_expiry_raw) if option_expiry_raw else futures_expiry

        ctx = execution_service.get_futures_context(broker, underlying_symbol, futures_expiry)
        spot_price = Decimal(str(ctx['ltp']))

        chain_rows = chain_service.fetch_covered_call_chain(underlying_symbol, option_expiry, spot_price)
        days_to_expiry = max((option_expiry - date.today()).days, 0)

        engine = CoveredCallRecommendationEngine(
            underlying_symbol=underlying_symbol,
            spot_price=float(spot_price),
            futures_avg_price=ctx['average_price'],
            uncovered_lots=ctx['uncovered_lots'],
            lot_size=ctx['lot_size'],
            days_to_expiry=days_to_expiry,
            chain_rows=chain_rows,
        )
        scored = engine.score_strikes()
        presets = engine.get_presets()

        from apps.core.models import TradingCoreConfig

        return JsonResponse({
            'success': True,
            'default_batch_delay_seconds': TradingCoreConfig.get_instance().default_batch_delay_seconds,
            'spot_price': float(spot_price),
            'futures_avg_price': ctx['average_price'],
            'futures_lots': ctx['lots'],
            'already_covered_lots': ctx['already_covered_lots'],
            'uncovered_lots': ctx['uncovered_lots'],
            'lot_size': ctx['lot_size'],
            'lot_size_unconfirmed': ctx['lot_size_unconfirmed'],
            'option_expiry': option_expiry.isoformat(),
            'chain': [_serialize_chain_row(row) for row in chain_rows],
            'recommendations': {k: _serialize_score(v) for k, v in presets.items()},
            'ranked_strikes': [_serialize_score(s) for s in scored],
        })
    except HedgeValidationError as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("chain_and_recommendations failed")
        return _error_response(exc, status=500)


@csrf_exempt
@require_POST
@login_required
def preview_cover_order(request):
    try:
        body = _json_body(request)
        result = execution_service.preview_cover_order(
            broker=body.get('broker', '').lower(),
            underlying_symbol=body.get('symbol', ''),
            futures_expiry_date=_parse_date(body['futures_expiry']),
            option_expiry_date=_parse_date(body.get('option_expiry') or body['futures_expiry']),
            strike=body['strike'],
            lots=int(body['lots']),
            order_type=body.get('order_type', 'MARKET'),
            limit_price=body.get('limit_price'),
        )
        return JsonResponse({'success': True, **result}, encoder=DjangoJSONEncoder)
    except HedgeValidationError as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("preview_cover_order failed")
        return _error_response(exc, status=500)


@csrf_exempt
@require_POST
@login_required
def place_cover_order(request):
    try:
        body = _json_body(request)
        if not body.get('confirm'):
            return JsonResponse({'success': False, 'error': "Missing 'confirm: true' — this endpoint places a real order."}, status=400)

        batch_delay_seconds = body.get('batch_delay_seconds')
        result = execution_service.place_cover_order(
            user=request.user,
            broker=body.get('broker', '').lower(),
            underlying_symbol=body.get('symbol', ''),
            futures_expiry_date=_parse_date(body['futures_expiry']),
            option_expiry_date=_parse_date(body.get('option_expiry') or body['futures_expiry']),
            strike=body['strike'],
            lots=int(body['lots']),
            order_type=body.get('order_type', 'MARKET'),
            limit_price=body.get('limit_price'),
            recommendation_snapshot=body.get('recommendation_snapshot'),
            batch_delay_seconds=int(batch_delay_seconds) if batch_delay_seconds is not None else None,
        )
        return JsonResponse(result)
    except HedgeValidationError as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("place_cover_order failed")
        return _error_response(exc, status=500)


@require_GET
@login_required
def order_progress(request, broker, symbol):
    progress = execution_service.get_order_progress(request.user.id, broker, symbol)
    return JsonResponse({'success': True, 'progress': progress})


@require_GET
@login_required
def active_status(request):
    """
    Bulk endpoint — one entry per ACTIVE hedge, so the Open Trades page's
    row loop does a single extra fetch instead of one call per row.
    """
    try:
        hedges = HedgePosition.objects.filter(status=HEDGE_STATUS_ACTIVE)
        result = {}
        for hedge in hedges:
            key = f"{hedge.broker}|{hedge.underlying_symbol}|{hedge.futures_expiry_date.isoformat()}"
            result[key] = {
                'hedge_position_id': hedge.id,
                'effective_breakeven': float(hedge.effective_breakeven) if hedge.effective_breakeven is not None else None,
                'futures_avg_price': float(hedge.futures_avg_price),
                'lots_covered': hedge.futures_lots_covered - hedge.uncovered_lots,
                'uncovered_lots': hedge.uncovered_lots,
                'net_premium_collected': float(hedge.net_premium_collected),
                'lot_size_unconfirmed': execution_service.is_lot_size_unconfirmed(hedge.futures_lot_size),
                'legs': [
                    {
                        'id': leg.id,
                        'strike': float(leg.strike_price),
                        'expiry': leg.expiry_date.isoformat(),
                        'lots': leg.lots,
                        'status': leg.status,
                    }
                    for leg in hedge.legs.exclude(status__in=[HedgeLeg.STATUS_CANCELLED, HedgeLeg.STATUS_FAILED])
                ],
            }
        return JsonResponse({'success': True, 'active_hedges': result})
    except Exception as exc:
        logger.exception("active_status failed")
        return _error_response(exc, status=500)


@csrf_exempt
@require_POST
@login_required
def roll_preview(request):
    try:
        body = _json_body(request)
        new_expiry = _parse_date(body['new_expiry']) if body.get('new_expiry') else None
        result = execution_service.preview_roll(int(body['hedge_leg_id']), body['new_strike'], new_expiry)
        return JsonResponse({'success': True, **result})
    except HedgeValidationError as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("roll_preview failed")
        return _error_response(exc, status=500)


@csrf_exempt
@require_POST
@login_required
def roll_execute(request):
    try:
        body = _json_body(request)
        if not body.get('confirm'):
            return JsonResponse({'success': False, 'error': "Missing 'confirm: true' — this endpoint places real orders."}, status=400)
        new_expiry = _parse_date(body['new_expiry']) if body.get('new_expiry') else None
        result = execution_service.execute_roll(
            user=request.user,
            hedge_leg_id=int(body['hedge_leg_id']),
            new_strike=body['new_strike'],
            new_expiry=new_expiry,
            order_type=body.get('order_type', 'MARKET'),
        )
        return JsonResponse({'success': True, **result})
    except HedgeValidationError as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("roll_execute failed")
        return _error_response(exc, status=500)


@csrf_exempt
@require_POST
@login_required
def close_leg_preview(request):
    try:
        body = _json_body(request)
        result = execution_service.preview_close_leg(int(body['hedge_leg_id']))
        return JsonResponse({'success': True, **result})
    except HedgeValidationError as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("close_leg_preview failed")
        return _error_response(exc, status=500)


@csrf_exempt
@require_POST
@login_required
def close_leg_execute(request):
    try:
        body = _json_body(request)
        if not body.get('confirm'):
            return JsonResponse({'success': False, 'error': "Missing 'confirm: true' — this endpoint places a real order."}, status=400)
        result = execution_service.execute_close_leg(
            user=request.user,
            hedge_leg_id=int(body['hedge_leg_id']),
            order_type=body.get('order_type', 'MARKET'),
        )
        return JsonResponse({'success': True, **result})
    except HedgeValidationError as exc:
        return _error_response(exc)
    except Exception as exc:
        logger.exception("close_leg_execute failed")
        return _error_response(exc, status=500)


@require_GET
@login_required
def hedge_history(request, hedge_position_id):
    try:
        hedge = HedgePosition.objects.get(id=hedge_position_id)
        legs = [
            {
                'id': leg.id, 'direction': leg.direction, 'leg_role': leg.leg_role,
                'strike': float(leg.strike_price), 'expiry': leg.expiry_date.isoformat(),
                'lots': leg.lots, 'status': leg.status,
                'premium_per_share': float(leg.premium_per_share) if leg.premium_per_share is not None else None,
                'charges': float(leg.charges), 'created_at': leg.created_at.isoformat(),
            }
            for leg in hedge.legs.all()
        ]
        audit_log = [
            {
                'id': entry.id, 'action': entry.action, 'user': entry.user.username if entry.user else None,
                'notes': entry.notes, 'created_at': entry.created_at.isoformat(),
            }
            for entry in hedge.audit_logs.all()
        ]
        return JsonResponse({'success': True, 'legs': legs, 'audit_log': audit_log})
    except HedgePosition.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Hedge position not found'}, status=404)
    except Exception as exc:
        logger.exception("hedge_history failed")
        return _error_response(exc, status=500)
