from django.contrib import admin
from .models import (
    FamilyMember, InvestmentAccount, InvestmentProduct, ProductValuationHistory,
    CASUpload, Transaction, MutualFundScheme, NAVHistory, EquityPrice,
    PortfolioGroup, PortfolioSnapshot, PortfolioHealthScore,
)


@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'relationship', 'pan_masked', 'user', 'created_at']
    list_filter = ['relationship', 'user']
    search_fields = ['name', 'pan_masked', 'user__username']
    readonly_fields = ['pan_hash', 'created_at', 'updated_at']


class InvestmentProductInline(admin.TabularInline):
    model = InvestmentProduct
    extra = 0
    fields = ['product_type', 'name', 'isin', 'invested_value', 'current_value', 'is_active']
    readonly_fields = ['gain_loss']


@admin.register(InvestmentAccount)
class InvestmentAccountAdmin(admin.ModelAdmin):
    list_display = ['account_name', 'account_type', 'institution_name', 'family_member', 'is_active']
    list_filter = ['account_type', 'is_active', 'data_source']
    search_fields = ['account_name', 'institution_name', 'family_member__name']
    inlines = [InvestmentProductInline]


@admin.register(InvestmentProduct)
class InvestmentProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'product_type', 'isin', 'invested_value', 'current_value', 'gain_loss', 'is_active']
    list_filter = ['product_type', 'is_active', 'data_source']
    search_fields = ['name', 'isin']
    readonly_fields = ['gain_loss', 'created_at', 'updated_at']


@admin.register(CASUpload)
class CASUploadAdmin(admin.ModelAdmin):
    list_display = ['family_member', 'cas_type', 'statement_month', 'statement_year',
                    'parse_status', 'products_created', 'created_at']
    list_filter = ['cas_type', 'parse_status']
    search_fields = ['family_member__name', 'original_filename']
    readonly_fields = ['encrypted_content', 'created_at', 'updated_at']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['security_name', 'transaction_type', 'transaction_date', 'units_credit',
                    'units_debit', 'amount', 'investment_account']
    list_filter = ['transaction_type', 'transaction_date']
    search_fields = ['isin', 'security_name']
    date_hierarchy = 'transaction_date'


@admin.register(MutualFundScheme)
class MutualFundSchemeAdmin(admin.ModelAdmin):
    list_display = ['isin', 'scheme_name', 'amc', 'category', 'plan_type', 'latest_nav', 'nav_date']
    list_filter = ['amc', 'category', 'plan_type', 'option_type']
    search_fields = ['isin', 'scheme_name', 'amc']
    readonly_fields = ['last_synced', 'created_at', 'updated_at']


@admin.register(NAVHistory)
class NAVHistoryAdmin(admin.ModelAdmin):
    list_display = ['scheme', 'date', 'nav']
    list_filter = ['date']
    search_fields = ['scheme__isin', 'scheme__scheme_name']
    date_hierarchy = 'date'


@admin.register(PortfolioGroup)
class PortfolioGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'group_type', 'user']
    filter_horizontal = ['members']


@admin.register(PortfolioSnapshot)
class PortfolioSnapshotAdmin(admin.ModelAdmin):
    list_display = ['family_member', 'portfolio_group', 'snapshot_date', 'current_value', 'xirr']
    date_hierarchy = 'snapshot_date'


admin.site.register(EquityPrice)
admin.site.register(ProductValuationHistory)
admin.site.register(PortfolioHealthScore)
