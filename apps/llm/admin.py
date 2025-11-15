from django.contrib import admin
from .models import LLMValidation, LLMPrompt


@admin.register(LLMValidation)
class LLMValidationAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'recommendation', 'confidence_score', 'human_approved', 'was_executed', 'created_at']
    list_filter = ['recommendation', 'human_approved', 'was_executed', 'outcome_correct']
    search_fields = ['symbol', 'reasoning']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(LLMPrompt)
class LLMPromptAdmin(admin.ModelAdmin):
    list_display = ['name', 'version', 'is_active', 'times_used', 'avg_confidence']
    list_filter = ['is_active']
    search_fields = ['name', 'purpose']
