"""
URL configuration for core app
"""

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('test/', views.system_test_page, name='system_test'),
    path('docs/<str:doc_name>/', views.view_documentation, name='view_documentation'),
]
