"""
Trading URLs
"""

from django.urls import path
from . import views

app_name = 'trading'

urlpatterns = [
    # Trade Suggestions
    path('suggestions/', views.pending_suggestions, name='pending_suggestions'),
    path('suggestion/<int:suggestion_id>/', views.suggestion_detail, name='suggestion_detail'),
    path('suggestion/<int:suggestion_id>/approve/', views.approve_suggestion, name='approve'),
    path('suggestion/<int:suggestion_id>/reject/', views.reject_suggestion, name='reject'),
    path('suggestion/<int:suggestion_id>/execute/', views.execute_suggestion, name='execute_suggestion'),
    path('suggestion/<int:suggestion_id>/confirm/', views.confirm_execution, name='confirm_execution'),

    # Auto-Trade Configuration
    path('config/auto-trade/', views.auto_trade_config, name='auto_trade_config'),

    # History
    path('history/', views.suggestion_history, name='suggestion_history'),
]
