"""
URL configuration for mcube_ai project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from apps.core.views import home_page

urlpatterns = [
    # Home page
    path('', home_page, name='home'),

    # Admin interface
    path('admin/', admin.site.urls),

    # Direct access to test page (redirects to /system/test/)
    path('test/', RedirectView.as_view(url='/system/test/', permanent=False), name='test_redirect'),

    # Core system URLs (includes test page at /system/test/)
    path('system/', include('apps.core.urls')),

    # App URLs
    path('accounts/', include('apps.accounts.urls')),
    path('brokers/', include('apps.brokers.urls')),
    path('data/', include('apps.data.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('positions/', include('apps.positions.urls')),
    path('strategies/', include('apps.strategies.urls')),
    path('risk/', include('apps.risk.urls')),
    path('alerts/', include('apps.alerts.urls')),
    path('llm/', include('apps.llm.urls')),
    path('trading/', include('apps.trading.urls')),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT if hasattr(settings, 'STATIC_ROOT') else None)

# Custom error handlers
handler404 = 'apps.core.views.error_404'
handler403 = 'apps.core.views.error_403'
handler500 = 'apps.core.views.error_500'
handler400 = 'apps.core.views.error_400'
