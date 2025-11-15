"""
Analytics app URL configuration
"""

from django.urls import path
from apps.analytics import views

app_name = 'analytics'

urlpatterns = [
    # Learning Control
    path('learning/', views.learning_dashboard, name='learning_dashboard'),
    path('learning/start/', views.start_learning, name='start_learning'),
    path('learning/<int:session_id>/stop/', views.stop_learning, name='stop_learning'),
    path('learning/<int:session_id>/pause/', views.pause_learning, name='pause_learning'),
    path('learning/<int:session_id>/resume/', views.resume_learning, name='resume_learning'),

    # Patterns
    path('patterns/', views.view_patterns, name='view_patterns'),
    path('patterns/<int:pattern_id>/', views.view_pattern_detail, name='view_pattern_detail'),

    # Suggestions
    path('suggestions/', views.view_suggestions, name='view_suggestions'),
    path('suggestions/<int:suggestion_id>/approve/', views.approve_suggestion, name='approve_suggestion'),
    path('suggestions/<int:suggestion_id>/reject/', views.reject_suggestion, name='reject_suggestion'),

    # API Endpoints
    path('api/learning-status/', views.api_learning_status, name='api_learning_status'),
    path('api/performance-metrics/', views.api_performance_metrics, name='api_performance_metrics'),
    path('api/pnl-data/', views.api_pnl_data, name='api_pnl_data'),
]
