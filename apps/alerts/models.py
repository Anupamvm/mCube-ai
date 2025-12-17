"""
Alert and notification models for mCube Trading System
"""

from django.db import models
from apps.core.models import TimeStampedModel
from apps.core.constants import ALERT_PRIORITY_CHOICES


class Alert(TimeStampedModel):
    """Alert/notification model"""

    account = models.ForeignKey(
        'accounts.BrokerAccount',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts'
    )

    priority = models.CharField(
        max_length=20,
        choices=ALERT_PRIORITY_CHOICES,
        db_index=True,
        help_text="Alert priority level"
    )

    alert_type = models.CharField(
        max_length=50,
        help_text="Type of alert (SL_HIT, TARGET_HIT, DELTA_ALERT, CIRCUIT_BREAKER, etc.)"
    )

    title = models.CharField(max_length=200)
    message = models.TextField()

    # Related objects
    position = models.ForeignKey(
        'positions.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts'
    )

    order = models.ForeignKey(
        'brokers.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts'
    )

    # Delivery status
    send_telegram = models.BooleanField(default=True)
    send_email = models.BooleanField(default=False)
    send_sms = models.BooleanField(default=False)

    telegram_sent = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    sms_sent = models.BooleanField(default=False)

    telegram_sent_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    sms_sent_at = models.DateTimeField(null=True, blank=True)

    # User action
    requires_action = models.BooleanField(default=False)
    action_taken = models.BooleanField(default=False)
    action_taken_at = models.DateTimeField(null=True, blank=True)
    action_notes = models.TextField(blank=True)

    # Additional data
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['priority', '-created_at']),
            models.Index(fields=['account', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_priority_display()} - {self.title}"

    def mark_sent(self, channel: str):
        """
        Mark alert as sent via specific channel

        Args:
            channel: telegram, email, or sms
        """
        from django.utils import timezone

        if channel == 'telegram':
            self.telegram_sent = True
            self.telegram_sent_at = timezone.now()
        elif channel == 'email':
            self.email_sent = True
            self.email_sent_at = timezone.now()
        elif channel == 'sms':
            self.sms_sent = True
            self.sms_sent_at = timezone.now()

        self.save()

    def is_fully_sent(self) -> bool:
        """Check if alert was sent via all requested channels"""
        if self.send_telegram and not self.telegram_sent:
            return False
        if self.send_email and not self.email_sent:
            return False
        if self.send_sms and not self.sms_sent:
            return False
        return True


class AlertLog(TimeStampedModel):
    """Alert delivery log"""

    alert = models.ForeignKey(
        Alert,
        on_delete=models.CASCADE,
        related_name='logs'
    )

    channel = models.CharField(max_length=20, help_text="telegram, email, sms")
    status = models.CharField(max_length=20, help_text="SUCCESS, FAILED, PENDING")
    response = models.TextField(blank=True, help_text="Response from service")
    error_message = models.TextField(blank=True)

    retry_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'alert_logs'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['alert', 'channel'])]

    def __str__(self):
        return f"{self.alert.title} - {self.channel} - {self.status}"
