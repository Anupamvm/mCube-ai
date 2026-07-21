"""
LLM Skill models for mCube Trading System

Stores data snapshots gathered for trade verification, and (once wired
in a follow-up) the LLM's verdict on that data.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class TradeVerificationSnapshot(TimeStampedModel):
    """
    A "Get Data" snapshot: everything known about a symbol/contract at the
    moment a user clicked Verify Trade / Get Data, either from an open
    position or from a pre-trade contract analysis screen.

    llm_provider / llm_verdict / llm_verified_at are reserved for the LLM
    verification call (not wired yet) so no further migration is needed
    once that's built.
    """

    position = models.ForeignKey(
        'positions.Position',
        on_delete=models.SET_NULL,
        related_name='verification_snapshots',
        null=True,
        blank=True,
        help_text="Open position this snapshot was taken for, if any"
    )

    symbol = models.CharField(max_length=50, db_index=True)
    expiry_date = models.DateField(null=True, blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    data_snapshot = models.JSONField(
        default=dict,
        help_text="Aggregated technical/OI/news/analyst data at snapshot time"
    )

    # Reserved for the LLM verification call (not wired yet)
    llm_provider = models.CharField(max_length=20, blank=True)
    llm_verdict = models.JSONField(null=True, blank=True)
    llm_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'llmskill_trade_verification_snapshots'
        verbose_name = 'Trade Verification Snapshot'
        verbose_name_plural = 'Trade Verification Snapshots'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['symbol', '-created_at']),
        ]

    def __str__(self):
        return f"{self.symbol} snapshot @ {self.created_at:%Y-%m-%d %H:%M}"
