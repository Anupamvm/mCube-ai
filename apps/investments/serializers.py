from rest_framework import serializers
from .models import (
    FamilyMember, InvestmentAccount, InvestmentProduct, ProductValuationHistory,
    CASUpload, Transaction, MutualFundScheme, NAVHistory,
    PortfolioGroup, PortfolioSnapshot, PortfolioHealthScore, UserCASPassword,
)

# Fund category strings vary in case by source (MF Central's own "Category"
# column is inconsistently all-caps, e.g. "EQUITY" vs "EQUITY FUND" in the
# same export) which otherwise splits one logical category into multiple
# dashboard chart slices. Title-case for consistent display, but preserve
# common all-caps acronyms that title() would otherwise mangle (e.g. ELSS).
_CATEGORY_ACRONYMS = {
    'Elss': 'ELSS', 'Etf': 'ETF', 'Sip': 'SIP', 'Psu': 'PSU', 'Sdl': 'SDL',
    'Nps': 'NPS', 'Ppf': 'PPF', 'Epf': 'EPF', 'Nfo': 'NFO', 'Fd': 'FD',
    'Rd': 'RD', 'Sgb': 'SGB',
}


def _normalize_category(raw: str) -> str:
    value = (raw or '').strip()
    if not value:
        return value
    titled = value.title()
    for wrong, right in _CATEGORY_ACRONYMS.items():
        titled = titled.replace(wrong, right)
    return titled


class FamilyMemberSerializer(serializers.ModelSerializer):
    total_net_worth = serializers.SerializerMethodField()
    total_invested = serializers.SerializerMethodField()
    accounts_count = serializers.SerializerMethodField()

    class Meta:
        model = FamilyMember
        fields = [
            'id', 'name', 'relationship', 'pan_masked', 'email_masked',
            'mobile_masked', 'date_of_birth', 'notes', 'is_active',
            'total_net_worth', 'total_invested', 'accounts_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_pan_masked(self, value):
        if not value:
            return value
        pan = value.upper().strip()
        request = self.context.get('request')
        if request:
            pan_hash = FamilyMember.make_pan_hash(pan)
            qs = FamilyMember.objects.filter(user=request.user, pan_hash=pan_hash)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError('A family member with this PAN already exists.')
        return pan

    def get_total_net_worth(self, obj):
        total = 0
        for account in obj.accounts.filter(is_active=True):
            total += float(account.current_value)
        return round(total, 2)

    def get_total_invested(self, obj):
        total = 0
        for account in obj.accounts.filter(is_active=True):
            total += float(account.invested_value)
        return round(total, 2)

    def get_accounts_count(self, obj):
        return obj.accounts.filter(is_active=True).count()


class InvestmentAccountSerializer(serializers.ModelSerializer):
    current_value = serializers.SerializerMethodField()
    invested_value = serializers.SerializerMethodField()
    products_count = serializers.SerializerMethodField()
    transactions_count = serializers.SerializerMethodField()
    family_member_name = serializers.CharField(source='family_member.name', read_only=True)
    xirr = serializers.SerializerMethodField()

    class Meta:
        model = InvestmentAccount
        fields = [
            'id', 'family_member', 'family_member_name', 'account_name', 'account_type',
            'institution_name', 'account_number_masked', 'dp_id', 'client_id', 'depository',
            'nominee_registered', 'is_active', 'data_source', 'notes',
            'current_value', 'invested_value', 'products_count', 'transactions_count', 'xirr',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_current_value(self, obj):
        return float(obj.current_value)

    def get_invested_value(self, obj):
        return float(obj.invested_value)

    def get_products_count(self, obj):
        return obj.products.filter(is_active=True).count()

    def get_transactions_count(self, obj):
        return obj.transactions.count()

    def get_xirr(self, obj):
        from .services.analytics.xirr_calculator import compute_account_xirr
        return compute_account_xirr(obj)


class InvestmentProductSerializer(serializers.ModelSerializer):
    gain_loss_pct = serializers.SerializerMethodField()
    account_name = serializers.CharField(source='investment_account.account_name', read_only=True)
    member_name = serializers.CharField(source='investment_account.family_member.name', read_only=True)
    institution_name = serializers.CharField(source='investment_account.institution_name', read_only=True)
    account_type = serializers.CharField(source='investment_account.account_type', read_only=True)
    mf_amc = serializers.SerializerMethodField()
    mf_category = serializers.SerializerMethodField()
    mf_sub_category = serializers.SerializerMethodField()
    mf_risk_level = serializers.SerializerMethodField()
    equity_sector = serializers.SerializerMethodField()
    equity_industry = serializers.SerializerMethodField()
    equity_market_cap_cr = serializers.SerializerMethodField()

    class Meta:
        model = InvestmentProduct
        fields = [
            'id', 'investment_account', 'account_name', 'member_name',
            'institution_name', 'account_type',
            'product_type', 'name', 'isin', 'data_source', 'is_active',
            'invested_value', 'current_value', 'as_of_date', 'investment_date',
            'gain_loss', 'gain_loss_pct', 'xirr',
            'mf_amc', 'mf_category', 'mf_sub_category', 'mf_risk_level',
            'equity_sector', 'equity_industry', 'equity_market_cap_cr',
            'extra_data', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['gain_loss', 'created_at', 'updated_at']

    def get_gain_loss_pct(self, obj):
        return round(float(obj.gain_loss_pct), 2)

    def _mf_scheme(self, obj):
        schemes = self.context.get('mf_schemes')
        if not schemes or not obj.isin:
            return None
        return schemes.get(obj.isin)

    def get_mf_amc(self, obj):
        scheme = self._mf_scheme(obj)
        if scheme and scheme.amc:
            return scheme.amc
        # Fall back to the AMC name captured at CAS-parse time when the
        # ISIN hasn't been matched against a synced MutualFundScheme yet.
        return (obj.extra_data or {}).get('amc', '')

    def get_mf_category(self, obj):
        extra = obj.extra_data or {}
        # A manual override always wins.
        if extra.get('category_source') == 'manual' and extra.get('category'):
            return _normalize_category(extra['category'])
        scheme = self._mf_scheme(obj)
        if scheme and scheme.category:
            return _normalize_category(scheme.category)
        # Fall back to a category captured directly from the source file
        # (e.g. MF Central XLSX) when the ISIN hasn't been MFAPI-synced yet.
        return _normalize_category(extra.get('category', ''))

    def get_mf_sub_category(self, obj):
        scheme = self._mf_scheme(obj)
        return scheme.sub_category if scheme else ''

    def get_mf_risk_level(self, obj):
        scheme = self._mf_scheme(obj)
        return scheme.risk_level if scheme else ''

    def _equity_stock(self, obj):
        stocks = self.context.get('equity_stocks')
        if not stocks or not obj.isin:
            return None
        return stocks.get(obj.isin)

    def get_equity_sector(self, obj):
        stock = self._equity_stock(obj)
        return stock.sector_name if stock else ''

    def get_equity_industry(self, obj):
        stock = self._equity_stock(obj)
        return stock.industry_name if stock else ''

    def get_equity_market_cap_cr(self, obj):
        # Trendlyne reports market_capitalization in ₹ Crores.
        stock = self._equity_stock(obj)
        return stock.market_capitalization if stock else None


class ProductValuationHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductValuationHistory
        fields = ['id', 'product', 'date', 'value', 'source', 'notes', 'created_at']
        read_only_fields = ['created_at']


class CASUploadSerializer(serializers.ModelSerializer):
    family_member_name = serializers.CharField(source='family_member.name', read_only=True)
    affected_products_count = serializers.SerializerMethodField()
    affected_transactions_count = serializers.SerializerMethodField()

    class Meta:
        model = CASUpload
        fields = [
            'id', 'family_member', 'family_member_name', 'cas_type',
            'statement_month', 'statement_year', 'original_filename',
            'parse_status', 'parse_error',
            'accounts_created', 'products_created', 'products_updated', 'transactions_created',
            'affected_products_count', 'affected_transactions_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'parse_status', 'parse_error', 'accounts_created',
            'products_created', 'transactions_created', 'created_at', 'updated_at',
        ]

    def get_affected_products_count(self, obj):
        return obj.sourced_products.filter(is_active=True).count()

    def get_affected_transactions_count(self, obj):
        return obj.transactions.count()


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'id', 'investment_account', 'product', 'isin', 'security_name',
            'transaction_date', 'order_no', 'description', 'transaction_type',
            'units_debit', 'units_credit', 'units_balance',
            'amount', 'nav_at_transaction', 'created_at',
        ]
        read_only_fields = ['created_at']


class MutualFundSchemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MutualFundScheme
        fields = [
            'id', 'isin', 'scheme_code', 'scheme_name', 'amc', 'category',
            'sub_category', 'scheme_type', 'plan_type', 'option_type',
            'expense_ratio', 'aum', 'benchmark', 'launch_date', 'risk_level',
            'latest_nav', 'nav_date', 'last_synced',
        ]


class NAVHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = NAVHistory
        fields = ['id', 'scheme', 'date', 'nav']


class PortfolioGroupSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = PortfolioGroup
        fields = ['id', 'name', 'description', 'members', 'group_type', 'member_count', 'created_at']
        read_only_fields = ['created_at']

    def get_member_count(self, obj):
        return obj.members.count()


class PortfolioSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioSnapshot
        fields = [
            'id', 'family_member', 'portfolio_group', 'snapshot_date',
            'total_invested', 'current_value', 'gain_loss', 'gain_loss_pct',
            'xirr', 'asset_allocation', 'net_worth_breakdown',
        ]


class PortfolioHealthScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioHealthScore
        fields = [
            'id', 'family_member', 'portfolio_group', 'score_date',
            'total_score', 'diversification_score', 'concentration_score',
            'expense_score', 'risk_adjusted_score', 'allocation_score',
            'tax_efficiency_score', 'methodology', 'insights',
        ]


class UserCASPasswordSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCASPassword
        fields = ['id', 'label', 'password', 'order', 'created_at']
        read_only_fields = ['created_at']
