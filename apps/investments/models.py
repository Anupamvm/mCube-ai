import hashlib
from django.db import models
from django.contrib.auth.models import User
from apps.core.models import TimeStampedModel


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class Relationship(models.TextChoices):
    SELF = 'SELF', 'Self'
    SPOUSE = 'SPOUSE', 'Spouse'
    FATHER = 'FATHER', 'Father'
    MOTHER = 'MOTHER', 'Mother'
    CHILD = 'CHILD', 'Child'
    HUF = 'HUF', 'HUF'
    TRUST = 'TRUST', 'Trust'
    OTHER = 'OTHER', 'Other'


class AccountType(models.TextChoices):
    DEMAT = 'DEMAT', 'Demat Account'
    MF_FOLIO = 'MF_FOLIO', 'Mutual Fund Folio'
    SAVINGS_BANK = 'SAVINGS_BANK', 'Savings Bank'
    PPF = 'PPF', 'PPF Account'
    EPF = 'EPF', 'EPF / PF Account'
    NPS = 'NPS', 'NPS Account'
    REAL_ESTATE = 'REAL_ESTATE', 'Real Estate'
    PHYSICAL_GOLD = 'PHYSICAL_GOLD', 'Physical Gold'
    CUSTOM = 'CUSTOM', 'Other / Custom'


class ProductType(models.TextChoices):
    MUTUAL_FUND = 'MUTUAL_FUND', 'Mutual Fund'
    EQUITY = 'EQUITY', 'Equity / Stock'
    FD = 'FD', 'Fixed Deposit'
    RD = 'RD', 'Recurring Deposit'
    SGB = 'SGB', 'Sovereign Gold Bond'
    BOND = 'BOND', 'Bond / Debenture'
    PPF = 'PPF', 'PPF'
    EPF = 'EPF', 'EPF / PF'
    NPS = 'NPS', 'NPS'
    REAL_ESTATE = 'REAL_ESTATE', 'Real Estate'
    PHYSICAL_GOLD = 'PHYSICAL_GOLD', 'Physical Gold'
    CRYPTO = 'CRYPTO', 'Crypto'
    CASH = 'CASH', 'Cash / Liquid'
    SAVINGS = 'SAVINGS', 'Savings Account'
    OTHER = 'OTHER', 'Other'


class DataSource(models.TextChoices):
    CAS = 'CAS', 'CAS Upload'
    CSV = 'CSV', 'CSV Import'
    MANUAL = 'MANUAL', 'Manual Entry'
    SYSTEM = 'SYSTEM', 'System Generated'


class CASType(models.TextChoices):
    NSDL = 'NSDL', 'NSDL e-CAS'
    CAMS = 'CAMS', 'CAMS CAS'
    KFINTECH = 'KFINTECH', 'KFintech CAS'


class ParseStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    DONE = 'DONE', 'Done'
    ERROR = 'ERROR', 'Error'


class TransactionType(models.TextChoices):
    PURCHASE = 'PURCHASE', 'Purchase / Buy'
    SALE = 'SALE', 'Sale / Redemption'
    PLEDGE = 'PLEDGE', 'Pledge'
    UNPLEDGE = 'UNPLEDGE', 'Pledge Closure'
    TRANSFER_IN = 'TRANSFER_IN', 'Transfer In'
    TRANSFER_OUT = 'TRANSFER_OUT', 'Transfer Out'
    BONUS = 'BONUS', 'Bonus / Split'
    DIVIDEND = 'DIVIDEND', 'Dividend'
    SIP = 'SIP', 'SIP'
    SWP = 'SWP', 'SWP'
    STP = 'STP', 'STP'
    OTHER = 'OTHER', 'Other'


class GroupType(models.TextChoices):
    FAMILY = 'FAMILY', 'Full Family'
    RETIREMENT = 'RETIREMENT', 'Retirement Corpus'
    TAX_SAVING = 'TAX_SAVING', 'Tax Saving'
    CUSTOM = 'CUSTOM', 'Custom'


class ValuationSource(models.TextChoices):
    AUTO = 'AUTO', 'Auto (NAV / Price Feed)'
    MANUAL = 'MANUAL', 'Manual Update'
    NAV_UPDATE = 'NAV_UPDATE', 'NAV Update Task'


# ---------------------------------------------------------------------------
# Family Member
# ---------------------------------------------------------------------------

class FamilyMember(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_members')
    name = models.CharField(max_length=200)
    relationship = models.CharField(max_length=20, choices=Relationship.choices, default=Relationship.SELF)
    pan_masked = models.CharField(max_length=20, blank=True, help_text='e.g. AAXXXXXX1B')
    pan_hash = models.CharField(max_length=64, blank=True, db_index=True,
                                help_text='SHA-256 of uppercase PAN for dedup detection')
    email_masked = models.CharField(max_length=100, blank=True)
    mobile_masked = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        unique_together = [('user', 'pan_hash')]

    def __str__(self):
        return f'{self.name} ({self.relationship}) — {self.user.username}'

    @staticmethod
    def make_pan_hash(pan: str) -> str:
        return hashlib.sha256(pan.upper().strip().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Investment Account
# ---------------------------------------------------------------------------

class InvestmentAccount(TimeStampedModel):
    family_member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name='accounts')
    account_name = models.CharField(max_length=200, help_text='e.g. HDFC Demat, SBI PPF, Flat in Pune')
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    institution_name = models.CharField(max_length=200, blank=True)
    account_number_masked = models.CharField(max_length=50, blank=True)
    dp_id = models.CharField(max_length=20, blank=True)
    client_id = models.CharField(max_length=20, blank=True)
    depository = models.CharField(max_length=10, blank=True, help_text='NSDL or CDSL')
    nominee_registered = models.BooleanField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    data_source = models.CharField(max_length=10, choices=DataSource.choices, default=DataSource.MANUAL)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['account_name']

    def __str__(self):
        return f'{self.account_name} ({self.family_member.name})'

    @property
    def current_value(self):
        return self.products.filter(is_active=True).aggregate(
            total=models.Sum('current_value')
        )['total'] or 0

    @property
    def invested_value(self):
        return self.products.filter(is_active=True).aggregate(
            total=models.Sum('invested_value')
        )['total'] or 0


# ---------------------------------------------------------------------------
# Investment Product
# ---------------------------------------------------------------------------

class InvestmentProduct(TimeStampedModel):
    investment_account = models.ForeignKey(InvestmentAccount, on_delete=models.CASCADE, related_name='products')
    product_type = models.CharField(max_length=20, choices=ProductType.choices)
    name = models.CharField(max_length=500)
    isin = models.CharField(max_length=20, blank=True, db_index=True)
    data_source = models.CharField(max_length=10, choices=DataSource.choices, default=DataSource.MANUAL)
    is_active = models.BooleanField(default=True)
    invested_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    as_of_date = models.DateField(null=True, blank=True)
    gain_loss = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    xirr = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    extra_data = models.JSONField(default=dict, blank=True,
                                  help_text='Product-type-specific fields (units, nav, interest_rate, etc.)')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-current_value']
        indexes = [
            models.Index(fields=['isin', 'is_active']),
            models.Index(fields=['product_type', 'is_active']),
        ]

    def __str__(self):
        return f'{self.name} ({self.product_type})'

    def save(self, *args, **kwargs):
        self.gain_loss = self.current_value - self.invested_value
        super().save(*args, **kwargs)

    @property
    def gain_loss_pct(self):
        if self.invested_value and self.invested_value != 0:
            return ((self.current_value - self.invested_value) / self.invested_value) * 100
        return 0


# ---------------------------------------------------------------------------
# Product Valuation History
# ---------------------------------------------------------------------------

class ProductValuationHistory(TimeStampedModel):
    product = models.ForeignKey(InvestmentProduct, on_delete=models.CASCADE, related_name='valuations')
    date = models.DateField(db_index=True)
    value = models.DecimalField(max_digits=20, decimal_places=2)
    source = models.CharField(max_length=20, choices=ValuationSource.choices, default=ValuationSource.MANUAL)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']
        unique_together = [('product', 'date')]

    def __str__(self):
        return f'{self.product.name} @ {self.date}: ₹{self.value}'


# ---------------------------------------------------------------------------
# CAS Upload
# ---------------------------------------------------------------------------

class CASUpload(TimeStampedModel):
    family_member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name='cas_uploads')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='investment_uploads')
    cas_type = models.CharField(max_length=10, choices=CASType.choices)
    statement_month = models.IntegerField(null=True, blank=True)
    statement_year = models.IntegerField(null=True, blank=True)
    original_filename = models.CharField(max_length=500)
    encrypted_content = models.BinaryField(null=True, blank=True)
    parse_status = models.CharField(max_length=20, choices=ParseStatus.choices, default=ParseStatus.PENDING)
    parse_error = models.TextField(blank=True)
    accounts_created = models.IntegerField(default=0)
    products_created = models.IntegerField(default=0)
    transactions_created = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.cas_type} CAS — {self.family_member.name} ({self.statement_month}/{self.statement_year})'


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

class Transaction(TimeStampedModel):
    investment_account = models.ForeignKey(InvestmentAccount, on_delete=models.CASCADE, related_name='transactions')
    product = models.ForeignKey(InvestmentProduct, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='transactions')
    cas_upload = models.ForeignKey(CASUpload, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='transactions')
    isin = models.CharField(max_length=20, blank=True, db_index=True)
    security_name = models.CharField(max_length=500, blank=True)
    transaction_date = models.DateField(db_index=True)
    order_no = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=500, blank=True)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices, default=TransactionType.OTHER)
    units_debit = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    units_credit = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    units_balance = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True,
                                 help_text='Rupee amount (available in CAMS CAS, not NSDL)')
    nav_at_transaction = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['isin', 'transaction_date']),
            models.Index(fields=['investment_account', 'transaction_date']),
        ]

    def __str__(self):
        return f'{self.transaction_type} {self.security_name} @ {self.transaction_date}'


# ---------------------------------------------------------------------------
# Mutual Fund Scheme (MFAPI data)
# ---------------------------------------------------------------------------

class MutualFundScheme(TimeStampedModel):
    isin = models.CharField(max_length=20, unique=True, db_index=True)
    scheme_code = models.IntegerField(null=True, blank=True, db_index=True,
                                      help_text='MFAPI numeric scheme code')
    scheme_name = models.CharField(max_length=500)
    amc = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=100, blank=True)
    sub_category = models.CharField(max_length=100, blank=True)
    scheme_type = models.CharField(max_length=50, blank=True, help_text='Open/Close/Interval')
    plan_type = models.CharField(max_length=20, blank=True, help_text='DIRECT or REGULAR')
    option_type = models.CharField(max_length=20, blank=True, help_text='GROWTH or IDCW')
    expense_ratio = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    aum = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    benchmark = models.CharField(max_length=200, blank=True)
    launch_date = models.DateField(null=True, blank=True)
    risk_level = models.CharField(max_length=30, blank=True)
    latest_nav = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    nav_date = models.DateField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['scheme_name']

    def __str__(self):
        return f'{self.scheme_name} ({self.isin})'


# ---------------------------------------------------------------------------
# NAV History
# ---------------------------------------------------------------------------

class NAVHistory(TimeStampedModel):
    scheme = models.ForeignKey(MutualFundScheme, on_delete=models.CASCADE, related_name='nav_history')
    date = models.DateField(db_index=True)
    nav = models.DecimalField(max_digits=20, decimal_places=4)

    class Meta:
        unique_together = [('scheme', 'date')]
        indexes = [models.Index(fields=['scheme', 'date'])]
        ordering = ['-date']

    def __str__(self):
        return f'{self.scheme.isin} @ {self.date}: {self.nav}'


# ---------------------------------------------------------------------------
# Equity Price
# ---------------------------------------------------------------------------

class EquityPrice(TimeStampedModel):
    isin = models.CharField(max_length=20, db_index=True)
    symbol = models.CharField(max_length=50, blank=True)
    company_name = models.CharField(max_length=500, blank=True)
    date = models.DateField(db_index=True)
    price = models.DecimalField(max_digits=20, decimal_places=4)
    source = models.CharField(max_length=20, blank=True, default='YAHOO')

    class Meta:
        unique_together = [('isin', 'date')]
        indexes = [models.Index(fields=['isin', 'date'])]
        ordering = ['-date']

    def __str__(self):
        return f'{self.isin} @ {self.date}: {self.price}'


# ---------------------------------------------------------------------------
# Portfolio Group
# ---------------------------------------------------------------------------

class PortfolioGroup(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolio_groups')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(FamilyMember, blank=True, related_name='groups')
    group_type = models.CharField(max_length=20, choices=GroupType.choices, default=GroupType.CUSTOM)

    class Meta:
        ordering = ['name']
        unique_together = [('user', 'name')]

    def __str__(self):
        return f'{self.name} ({self.user.username})'


# ---------------------------------------------------------------------------
# Portfolio Snapshot
# ---------------------------------------------------------------------------

class PortfolioSnapshot(TimeStampedModel):
    family_member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, null=True, blank=True,
                                      related_name='snapshots')
    portfolio_group = models.ForeignKey(PortfolioGroup, on_delete=models.CASCADE, null=True, blank=True,
                                        related_name='snapshots')
    snapshot_date = models.DateField(db_index=True)
    total_invested = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    gain_loss = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    gain_loss_pct = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    xirr = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    asset_allocation = models.JSONField(default=dict, blank=True)
    net_worth_breakdown = models.JSONField(default=dict, blank=True,
                                           help_text='Value per product_type category')

    class Meta:
        ordering = ['-snapshot_date']
        indexes = [
            models.Index(fields=['family_member', 'snapshot_date']),
            models.Index(fields=['portfolio_group', 'snapshot_date']),
        ]

    def __str__(self):
        owner = self.family_member or self.portfolio_group
        return f'{owner} snapshot @ {self.snapshot_date}'


# ---------------------------------------------------------------------------
# Portfolio Health Score
# ---------------------------------------------------------------------------

class PortfolioHealthScore(TimeStampedModel):
    family_member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, null=True, blank=True,
                                      related_name='health_scores')
    portfolio_group = models.ForeignKey(PortfolioGroup, on_delete=models.CASCADE, null=True, blank=True,
                                        related_name='health_scores')
    score_date = models.DateField(db_index=True)
    total_score = models.IntegerField(default=0, help_text='0–100')
    diversification_score = models.IntegerField(default=0)
    concentration_score = models.IntegerField(default=0)
    expense_score = models.IntegerField(default=0)
    risk_adjusted_score = models.IntegerField(default=0)
    allocation_score = models.IntegerField(default=0)
    tax_efficiency_score = models.IntegerField(default=0)
    methodology = models.JSONField(default=dict, blank=True)
    insights = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-score_date']

    def __str__(self):
        owner = self.family_member or self.portfolio_group
        return f'{owner} health score {self.total_score}/100 @ {self.score_date}'
