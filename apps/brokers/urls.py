"""
URL configuration for brokers app
"""

from django.urls import path
from apps.brokers import views

app_name = 'brokers'

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('', views.broker_dashboard, name='dashboard'),

    # Kotak Neo URLs
    path('kotakneo/login/', views.kotakneo_login, name='kotakneo_login'),
    path('kotakneo/data/', views.kotakneo_data, name='kotakneo_data'),

    # Breeze URLs
    path('breeze/login/', views.breeze_login, name='breeze_login'),
    path('breeze/data/', views.breeze_data, name='breeze_data'),
    path('breeze/nifty-quote/', views.nifty_quote, name='nifty_quote'),
    path('breeze/option-chain/', views.breeze_option_chain, name='option_chain'),
    path('breeze/historical/', views.breeze_historical, name='historical'),

    # API endpoints
    path('api/positions/', views.api_positions, name='api_positions'),
    path('api/limits/', views.api_limits, name='api_limits'),
]
