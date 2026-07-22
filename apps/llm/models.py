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
    Singleton: LLM provider configuration and per-task routing.

    Two tiers are configured independently and can both be active at once:
      - Local: the self-hosted vLLM server (just one - no vendor choice).
      - Online: exactly one cloud vendor at a time (OpenAI or Anthropic),
        chosen via online_provider, each with its own key/model.

    Rather than one global switch, individual call sites are classified into
    a task type and each task type is routed to whichever tier fits it best:
      - understanding_target: news/report comprehension (sentiment,
        summaries, insight extraction, RAG Q&A) - local by default, since
        it's high-volume and vLLM handles it fine at no per-call cost.
      - evaluation_target: higher-stakes reasoning (trade/position
        validation, ad-hoc chat) - online by default, for a stronger model.

    See apps.llm.services.llm_router.get_llm_client_for_task(), which reads
    these fields and falls back to the other tier if the assigned one isn't
    currently reachable/configured.
    """

    TASK_TARGET_CHOICES = [
        ('local', 'Local (self-hosted vLLM)'),
        ('online', 'Online (cloud)'),
    ]

    ONLINE_PROVIDER_CHOICES = [
        ('openai', 'OpenAI (ChatGPT)'),
        ('anthropic', 'Claude (Anthropic)'),
    ]

    online_provider = models.CharField(max_length=20, choices=ONLINE_PROVIDER_CHOICES, default='openai')

    understanding_target = models.CharField(max_length=10, choices=TASK_TARGET_CHOICES, default='local')
    evaluation_target = models.CharField(max_length=10, choices=TASK_TARGET_CHOICES, default='online')

    # Stored plainly, same convention as apps.core.models.CredentialStore - no
    # encryption layer exists elsewhere in this codebase for API keys either.
    openai_api_key = models.CharField(max_length=200, blank=True, help_text="OpenAI API key")
    openai_model = models.CharField(max_length=100, default='gpt-4o-mini')

    anthropic_api_key = models.CharField(max_length=200, blank=True, help_text="Anthropic (Claude) API key")
    anthropic_model = models.CharField(max_length=100, default='claude-opus-4-8')

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
        return (
            f"Understanding -> {self.get_understanding_target_display()}, "
            f"Evaluation -> {self.get_evaluation_target_display()} "
            f"(online vendor: {self.get_online_provider_display()})"
        )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
