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


class LLMProviderConfig(TimeStampedModel):
    """
    Singleton: which LLM provider currently serves ALL requests system-wide.

    Set from /llm/models/. When active_provider='openai', every service that
    calls apps.llm.services.llm_router.get_active_llm_client() (instead of
    reaching for a specific vllm/ollama client directly) is redirected to
    OpenAI, regardless of which local backend it would normally use.
    """

    PROVIDER_CHOICES = [
        ('vllm', 'Local (self-hosted vLLM)'),
        ('openai', 'OpenAI (ChatGPT, cloud)'),
    ]

    active_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='vllm')

    # Stored plainly, same convention as apps.core.models.CredentialStore - no
    # encryption layer exists elsewhere in this codebase for API keys either.
    openai_api_key = models.CharField(max_length=200, blank=True, help_text="OpenAI API key")
    openai_model = models.CharField(max_length=100, default='gpt-4o-mini')

    switched_at = models.DateTimeField(null=True, blank=True)
    switched_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+'
    )

    class Meta:
        db_table = 'llm_provider_config'
        verbose_name = 'LLM Provider Config'
        verbose_name_plural = 'LLM Provider Config'

    def __str__(self):
        return f"Active LLM provider: {self.get_active_provider_display()}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
