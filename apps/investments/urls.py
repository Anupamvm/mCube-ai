from django.urls import path
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.middleware.csrf import get_token
from django.http import JsonResponse
from .views.family_views import (
    FamilyMemberListCreateView, FamilyMemberDetailView,
    member_net_worth, member_analytics, member_insights,
)
from .views.account_views import AccountListCreateView, AccountDetailView, AccountProductsView
from .views.product_views import (
    ProductListView, ProductDetailView, ProductCreateView,
    ProductValuationHistoryView, update_product_value, set_product_category,
)
from .views.upload_views import (
    cas_upload_list, cas_upload_detail, cas_reparse, equity_csv_upload,
    smart_upload, portfolio_file_upload, manual_asset_entry, manual_asset_detail,
    clear_account_csv, CASPasswordListCreateView, CASPasswordDetailView,
)
from .views.analytics_views import (
    consolidated_portfolio, trigger_price_update,
    overlap_analysis, health_score_view,
    risk_summary, tenor_ladder, portfolio_trend, sync_mf_categories,
)
from .views.fund_views import fund_detail, fund_nav_history, fund_risk_metrics, fund_my_holding
from .views.report_views import generate_report, download_report
from .views.group_views import PortfolioGroupListCreateView, PortfolioGroupDetailView, group_net_worth


@login_required
def investments_home(request):
    return render(request, 'investments/index.html')


@login_required
def member_page(request, pk):
    return render(request, 'investments/member_detail.html', {'member_id': pk})


@login_required
def account_page(request, pk):
    return render(request, 'investments/account_detail.html', {'account_id': pk})


@login_required
def upload_page(request):
    return render(request, 'investments/upload_cas.html')


@login_required
def consolidated_page(request):
    return render(request, 'investments/consolidated.html')


@login_required
def reports_page(request):
    return render(request, 'investments/reports.html')


def csrf_token_view(request):
    return JsonResponse({'csrfToken': get_token(request)})


app_name = 'investments'

urlpatterns = [
    # ── Django template pages ─────────────────────────────────────────────────
    path('', investments_home, name='home'),
    path('member/<int:pk>/', member_page, name='member-page'),
    path('account/<int:pk>/', account_page, name='account-page'),
    path('upload/', upload_page, name='upload-page'),
    path('consolidated/', consolidated_page, name='consolidated-page'),
    path('reports/', reports_page, name='reports-page'),

    # ── Family Members ────────────────────────────────────────────────────────
    path('api/family-members/', FamilyMemberListCreateView.as_view(), name='family-list'),
    path('api/family-members/<int:pk>/', FamilyMemberDetailView.as_view(), name='family-detail'),
    path('api/family-members/<int:pk>/net-worth/', member_net_worth, name='member-net-worth'),
    path('api/family-members/<int:pk>/analytics/', member_analytics, name='member-analytics'),
    path('api/family-members/<int:pk>/insights/', member_insights, name='member-insights'),

    # ── Investment Accounts ───────────────────────────────────────────────────
    path('api/accounts/', AccountListCreateView.as_view(), name='account-list'),
    path('api/accounts/<int:pk>/', AccountDetailView.as_view(), name='account-detail'),
    path('api/accounts/<int:pk>/products/', AccountProductsView.as_view(), name='account-products'),
    path('api/accounts/<int:account_pk>/products/add/', ProductCreateView.as_view(), name='account-add-product'),

    # ── Investment Products ───────────────────────────────────────────────────
    path('api/products/', ProductListView.as_view(), name='product-list'),
    path('api/products/<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('api/products/<int:pk>/valuations/', ProductValuationHistoryView.as_view(), name='product-valuations'),
    path('api/products/<int:pk>/update-value/', update_product_value, name='product-update-value'),
    path('api/products/<int:pk>/set-category/', set_product_category, name='product-set-category'),

    # ── Smart Upload (single endpoint, auto-detects format) ──────────────────
    path('api/uploads/smart/', smart_upload, name='smart-upload'),
    path('api/accounts/<int:pk>/clear-csv/', clear_account_csv, name='account-clear-csv'),

    # ── Uploads ───────────────────────────────────────────────────────────────
    path('api/uploads/cas/', cas_upload_list, name='cas-upload-list'),
    path('api/uploads/cas/<int:pk>/', cas_upload_detail, name='cas-upload-detail'),
    path('api/uploads/cas/<int:pk>/reparse/', cas_reparse, name='cas-reparse'),
    path('api/uploads/equity-csv/', equity_csv_upload, name='equity-csv-upload'),
    path('api/uploads/portfolio-file/', portfolio_file_upload, name='portfolio-file-upload'),
    path('api/uploads/passwords/', CASPasswordListCreateView.as_view(), name='cas-passwords'),
    path('api/uploads/passwords/<int:pk>/', CASPasswordDetailView.as_view(), name='cas-password-detail'),

    # ── Manual Asset Entry ────────────────────────────────────────────────────
    path('api/assets/manual/', manual_asset_entry, name='manual-asset-entry'),
    path('api/assets/manual/<int:pk>/', manual_asset_detail, name='manual-asset-detail'),

    # ── Portfolio Analytics ───────────────────────────────────────────────────
    path('api/portfolio/consolidated/', consolidated_portfolio, name='consolidated'),
    path('api/portfolio/groups/', PortfolioGroupListCreateView.as_view(), name='group-list'),
    path('api/portfolio/groups/<int:pk>/', PortfolioGroupDetailView.as_view(), name='group-detail'),
    path('api/portfolio/groups/<int:pk>/net-worth/', group_net_worth, name='group-net-worth'),

    # ── Analytics ─────────────────────────────────────────────────────────────
    path('api/analytics/update-prices/', trigger_price_update, name='update-prices'),
    path('api/analytics/sync-categories/', sync_mf_categories, name='sync-categories'),
    path('api/analytics/overlap/', overlap_analysis, name='overlap'),
    path('api/analytics/health-score/', health_score_view, name='health-score'),
    path('api/analytics/risk-summary/', risk_summary, name='risk-summary'),
    path('api/analytics/tenor-ladder/', tenor_ladder, name='tenor-ladder'),
    path('api/analytics/trend/', portfolio_trend, name='portfolio-trend'),

    # ── Mutual Funds ──────────────────────────────────────────────────────────
    path('api/funds/<str:isin>/', fund_detail, name='fund-detail'),
    path('api/funds/<str:isin>/nav-history/', fund_nav_history, name='fund-nav-history'),
    path('api/funds/<str:isin>/risk-metrics/', fund_risk_metrics, name='fund-risk-metrics'),
    path('api/funds/<str:isin>/my-holding/', fund_my_holding, name='fund-my-holding'),

    # ── Reports ───────────────────────────────────────────────────────────────
    path('api/reports/generate/', generate_report, name='report-generate'),
    path('api/reports/download/<str:token>/', download_report, name='report-download'),

    # ── CSRF bootstrap (called by Next.js on first load) ─────────────────────
    path('api/csrf/', csrf_token_view, name='csrf-token'),
]
