"""
URL routing for data collection endpoints
"""

from django.urls import path
from . import views

app_name = 'data'

urlpatterns = [
    # Trendlyne endpoints
    path('trendlyne/login/', views.trendlyne_login_view, name='trendlyne-login'),
    path('trendlyne/fetch/', views.trendlyne_fetch_data_view, name='trendlyne-fetch'),
    path('trendlyne/status/', views.trendlyne_status_view, name='trendlyne-status'),
]
