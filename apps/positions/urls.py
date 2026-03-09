"""
URL configuration for positions app
"""

from django.urls import path
from . import views

app_name = 'positions'

urlpatterns = [
    path('system/', views.system_positions, name='system_positions'),
    path('api/update-field/', views.update_position_field, name='update_field'),
    path('api/suggest-sl-target/', views.suggest_sl_target, name='suggest_sl_target'),
]
