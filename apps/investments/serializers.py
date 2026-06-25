from rest_framework import serializers
from .models import (
    FamilyMember, InvestmentAccount, InvestmentProduct, ProductValuationHistory,
    CASUpload, Transaction, MutualFundScheme, NAVHistory,
    PortfolioGroup, PortfolioSnapshot, PortfolioHealthScore, UserCASPassword,
)


class FamilyMemberSerializer(serializers.ModelSerializer):
    total_net_worth = serializers.SerializerMethodField()
    total_invested = serializers.SerializerMethodField()
    accounts_count = serializers.SerializerMethodField()

    class Meta:
        model = FamilyMember
        fields = [
            'id', 'name', 'relationship', 'pan_masked', 'email_masked',
            'mobile_masked', 'date_of_birth', 'notes',
            'total_net_worth', 'total_invested', 'accounts_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

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
    family_member_name = serializers.CharField(source='family_member.name', read_only=True)

    class Meta:
        model = InvestmentAccount
        fields = [
            'id', 'family_member', 'family_member_name', 'account_name', 'account_type',
            'institution_name', 'account_number_masked', 'dp_id', 'client_id', 'depository',
            'nominee_registered', 'is_active', 'data_source', 'notes',
            'current_value', 'invested_value', 'products_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_current_value(self, obj):
        return float(obj.current_value)

    def get_invested_value(self, obj):
        return float(obj.invested_value)

    def get_products_count(self, obj):
        return obj.products.filter(is_active=True).count()


class InvestmentProductSerializer(serializers.ModelSerializer):
    gain_loss_pct = serializers.SerializerMethodField()
    account_name = serializers.CharField(source='investment_account.account_name', read_only=True)
    member_name = serializers.CharField(source='investment_account.family_member.name', read_only=True)

    class Meta:
        model = InvestmentProduct
        fields = [
            'id', 'investment_account', 'account_name', 'member_name',
            'product_type', 'name', 'isin', 'data_source', 'is_active',
            'invested_value', 'current_value', 'as_of_date',
            'gain_loss', 'gain_loss_pct', 'xirr',
            'extra_data', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['gain_loss', 'created_at', 'updated_at']

    def get_gain_loss_pct(self, obj):
        return round(float(obj.gain_loss_pct), 2)


class ProductValuationHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductValuationHistory
        fields = ['id', 'product', 'date', 'value', 'source', 'notes', 'created_at']
        read_only_fields = ['created_at']


class CASUploadSerializer(serializers.ModelSerializer):
    family_member_name = serializers.CharField(source='family_member.name', read_only=True)

    class Meta:
        model = CASUpload
        fields = [
            'id', 'family_member', 'family_member_name', 'cas_type',
            'statement_month', 'statement_year', 'original_filename',
            'parse_status', 'parse_error',
            'accounts_created', 'products_created', 'transactions_created',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'parse_status', 'parse_error', 'accounts_created',
            'products_created', 'transactions_created', 'created_at', 'updated_at',
        ]


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
