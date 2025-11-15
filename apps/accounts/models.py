"""
Account models for mCube Trading System

This module contains models for broker accounts and API credentials.
"""

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator

from apps.core.models import TimeStampedModel
from apps.core.constants import BROKER_CHOICES


class BrokerAccount(TimeStampedModel):
    """
    Broker account model

    Represents a trading account with a broker (Kotak or ICICI).
    Each account has allocated capital, risk limits, and configuration.

    Fields:
        broker: Broker name (KOTAK or ICICI)
        account_number: Unique account identifier
        account_name: Display name for the account
        allocated_capital: Total capital allocated to this account
        is_active: Whether the account is currently active
        is_paper_trading: Whether this is in paper trading mode
        max_daily_loss: Maximum loss allowed per day
        max_weekly_loss: Maximum loss allowed per week
    """

    broker = models.CharField(
        max_length=20,
        choices=BROKER_CHOICES,
        help_text="Broker name (KOTAK or ICICI)"
    )

    account_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique broker account number"
    )

    account_name = models.CharField(
        max_length=100,
        help_text="Display name for this account"
    )

    allocated_capital = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total capital allocated to this account"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this account is currently active for trading"
    )

    is_paper_trading = models.BooleanField(
        default=True,
        help_text="Whether this account is in paper trading mode"
    )

    max_daily_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Maximum loss allowed per day (circuit breaker)"
    )

    max_weekly_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Maximum loss allowed per week (circuit breaker)"
    )

    # Additional metadata
    notes = models.TextField(
        blank=True,
        help_text="Any additional notes about this account"
    )

    class Meta:
        db_table = 'broker_accounts'
        verbose_name = 'Broker Account'
        verbose_name_plural = 'Broker Accounts'
        ordering = ['broker', 'account_name']

    def __str__(self):
        return f"{self.get_broker_display()} - {self.account_name}"

    def get_available_capital(self) -> Decimal:
        """
        Calculate available capital not deployed in positions

        Returns:
            Decimal: Available capital for new positions
        """
        from apps.positions.models import Position

        # Sum up margin used by all active positions
        deployed = Position.objects.filter(
            account=self,
            status='ACTIVE'
        ).aggregate(
            total=models.Sum('margin_used')
        )['total'] or Decimal('0')

        available = self.allocated_capital - deployed
        return max(available, Decimal('0'))

    def get_total_pnl(self) -> Decimal:
        """
        Calculate total P&L (realized + unrealized)

        Returns:
            Decimal: Total P&L
        """
        from apps.positions.models import Position

        positions = Position.objects.filter(account=self)

        total_realized = positions.filter(
            status='CLOSED'
        ).aggregate(
            total=models.Sum('realized_pnl')
        )['total'] or Decimal('0')

        total_unrealized = positions.filter(
            status='ACTIVE'
        ).aggregate(
            total=models.Sum('unrealized_pnl')
        )['total'] or Decimal('0')

        return total_realized + total_unrealized

    def get_todays_pnl(self) -> Decimal:
        """
        Calculate today's P&L

        Returns:
            Decimal: Today's P&L
        """
        from datetime import date
        from apps.positions.models import Position

        today = date.today()

        # Realized P&L from positions closed today
        realized_today = Position.objects.filter(
            account=self,
            status='CLOSED',
            exit_time__date=today
        ).aggregate(
            total=models.Sum('realized_pnl')
        )['total'] or Decimal('0')

        # Unrealized P&L from active positions
        unrealized = Position.objects.filter(
            account=self,
            status='ACTIVE'
        ).aggregate(
            total=models.Sum('unrealized_pnl')
        )['total'] or Decimal('0')

        return realized_today + unrealized

    def deactivate(self, reason: str = ""):
        """
        Deactivate the account (triggered by circuit breakers)

        Args:
            reason: Reason for deactivation
        """
        self.is_active = False
        if reason:
            self.notes = f"{self.notes}\n[DEACTIVATED] {reason}".strip()
        self.save()


class APICredential(TimeStampedModel):
    """
    API credentials for broker accounts

    Stores encrypted API keys and secrets for broker API access.
    Credentials are never logged and should be encrypted at rest.

    Fields:
        account: Associated broker account
        consumer_key: API consumer key
        consumer_secret: API consumer secret (encrypted)
        access_token: API access token (encrypted)
        refresh_token: API refresh token (encrypted)
        is_valid: Whether credentials are currently valid
        last_authenticated: Last successful authentication timestamp
    """

    account = models.OneToOneField(
        BrokerAccount,
        on_delete=models.CASCADE,
        related_name='credentials',
        help_text="Associated broker account"
    )

    consumer_key = models.CharField(
        max_length=200,
        help_text="API consumer key"
    )

    consumer_secret = models.CharField(
        max_length=200,
        help_text="API consumer secret (encrypted)"
    )

    access_token = models.CharField(
        max_length=500,
        blank=True,
        help_text="API access token (encrypted)"
    )

    refresh_token = models.CharField(
        max_length=500,
        blank=True,
        help_text="API refresh token (encrypted)"
    )

    # Additional broker-specific fields
    mobile_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Mobile number (for Kotak)"
    )

    password = models.CharField(
        max_length=200,
        blank=True,
        help_text="Account password (encrypted)"
    )

    # Status tracking
    is_valid = models.BooleanField(
        default=False,
        help_text="Whether credentials are currently valid"
    )

    last_authenticated = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful authentication timestamp"
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Token expiration timestamp"
    )

    class Meta:
        db_table = 'api_credentials'
        verbose_name = 'API Credential'
        verbose_name_plural = 'API Credentials'

    def __str__(self):
        return f"Credentials for {self.account.account_name}"

    def is_expired(self) -> bool:
        """
        Check if credentials are expired

        Returns:
            bool: True if expired
        """
        from django.utils import timezone

        if not self.expires_at:
            return True

        return timezone.now() > self.expires_at

    def mark_invalid(self):
        """Mark credentials as invalid"""
        self.is_valid = False
        self.save()

    def mark_valid(self):
        """Mark credentials as valid"""
        from django.utils import timezone

        self.is_valid = True
        self.last_authenticated = timezone.now()
        self.save()
