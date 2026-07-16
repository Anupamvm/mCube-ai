"""
URL configuration for the hedging (Cover Position / covered call) app.
"""
from django.urls import path
from . import api_views

app_name = 'hedging'

urlpatterns = [
    path('api/chain-and-recommendations/', api_views.chain_and_recommendations, name='chain_and_recommendations'),
    path('api/preview/', api_views.preview_cover_order, name='preview_cover_order'),
    path('api/place-order/', api_views.place_cover_order, name='place_cover_order'),
    path('api/order-progress/<str:broker>/<str:symbol>/', api_views.order_progress, name='order_progress'),
    path('api/active-status/', api_views.active_status, name='active_status'),
    path('api/roll/preview/', api_views.roll_preview, name='roll_preview'),
    path('api/roll/execute/', api_views.roll_execute, name='roll_execute'),
    path('api/close-leg/preview/', api_views.close_leg_preview, name='close_leg_preview'),
    path('api/close-leg/execute/', api_views.close_leg_execute, name='close_leg_execute'),
    path('api/history/<int:hedge_position_id>/', api_views.hedge_history, name='hedge_history'),
]
