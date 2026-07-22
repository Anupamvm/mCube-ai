"""
URL configuration for llmskill app
"""

from django.urls import path

from . import views

app_name = 'llmskill'

urlpatterns = [
    path('verify/<int:position_id>/', views.verify_trade_page, name='verify_trade_page'),
    path('data-view/', views.get_data_view, name='get_data_view'),
    path('api/get-data/', views.get_data_api, name='get_data'),
]
