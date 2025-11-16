"""
Algorithm Testing URLs
"""

from django.urls import path
from . import views

app_name = 'algo_test'

urlpatterns = [
    # Options testing
    path('options/', views.options_test_page, name='options_test'),
    path('options/analyze/', views.options_test_analyze, name='options_analyze'),

    # Futures testing
    path('futures/', views.futures_test_page, name='futures_test'),
    path('futures/analyze/', views.futures_test_analyze, name='futures_analyze'),

    # Monitoring
    path('monitor/', views.position_monitor_page, name='monitor'),

    # Risk
    path('risk/', views.risk_dashboard_page, name='risk'),
]
