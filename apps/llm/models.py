"""
LLM integration models for mCube Trading System
"""

from decimal import Decimal
from django.db import models
from apps.core.models import TimeStampedModel


class LLMValidation(TimeStampedModel):
    """LLM trade validation record"""

    symbol = models.CharField(max_length=50)
    direction = models.CharField(max_length=10)

    # Input data
    prompt = models.TextField(help_text="Prompt sent to LLM")
    context_data = models.JSONField(default=dict, help_text="Market data, OI, sector info")

    # LLM response
    raw_response = models.TextField(help_text="Raw LLM response")
    parsed_response = models.JSONField(default=dict, help_text="Structured response")

    # Validation result
    recommendation = models.CharField(
        max_length=20,
        choices=[('LONG', 'Long'), ('SHORT', 'Short'), ('AVOID', 'Avoid')],
        help_text="LLM recommendation"
    )

    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Confidence score (0-100)"
    )

    reasoning = models.TextField(blank=True, help_text="LLM reasoning")
    risk_factors = models.JSONField(default=list, help_text="Identified risk factors")

    # Processing metadata
    model_used = models.CharField(max_length=100, default='deepseek-coder:33b')
    processing_time_ms = models.IntegerField(null=True, blank=True)

    # Human decision
    human_approved = models.BooleanField(null=True, blank=True)
    human_notes = models.TextField(blank=True)

    # Outcome tracking (filled after position closes)
    was_executed = models.BooleanField(default=False)
    actual_pnl = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    outcome_correct = models.BooleanField(null=True, blank=True)

    class Meta:
        db_table = 'llm_validations'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['symbol', '-created_at'])]

    def __str__(self):
        return f"{self.symbol} {self.recommendation} ({self.confidence_score}%)"


class LLMPrompt(TimeStampedModel):
    """LLM prompt templates"""

    name = models.CharField(max_length=100, unique=True)
    purpose = models.CharField(max_length=200)
    template = models.TextField(help_text="Prompt template with placeholders")

    is_active = models.BooleanField(default=True)
    version = models.CharField(max_length=20, default='1.0')

    # Performance tracking
    times_used = models.IntegerField(default=0)
    avg_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00')
    )

    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'llm_prompts'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (v{self.version})"
