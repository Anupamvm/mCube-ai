"""
LLM Provider Router

Resolves a provider name to the corresponding LLM client singleton, so
callers can pick 'vllm', 'ollama', 'openai', or 'anthropic' without
importing each client module directly.

Task-based routing (get_llm_client_for_task): two tiers can be configured
and active at the same time - Local (self-hosted vLLM, just one) and
Online (exactly one cloud vendor at a time, OpenAI or Anthropic). Instead
of one global switch, each call site is classified as either 'understanding'
(news/report comprehension - sentiment, summaries, insights, RAG Q&A) or
'evaluation' (higher-stakes reasoning - trade/position validation, ad-hoc
chat), and apps.llm.models.LLMProviderConfig says which tier serves each
task type. See that model's docstring for the full rationale.
"""

import logging
import os

from apps.llm.services.vllm_client import get_vllm_client
from apps.llm.services.ollama_client import get_ollama_client
from apps.llm.services.openai_client import get_openai_client
from apps.llm.services.anthropic_client import get_anthropic_client

logger = logging.getLogger(__name__)

VALID_PROVIDERS = ('vllm', 'ollama', 'openai', 'anthropic')


def get_llm_client(provider: str = None):
    """
    Get an LLM client by provider name.

    Args:
        provider: 'vllm', 'ollama', 'openai', or 'anthropic'. Defaults to the
            LLM_DEFAULT_PROVIDER env var, falling back to 'vllm'.

    Returns:
        A client instance exposing generate(prompt, system, temperature, max_tokens)
        -> (success, text, metadata) and is_enabled().
    """
    provider = (provider or os.getenv('LLM_DEFAULT_PROVIDER', 'vllm')).lower()

    if provider not in VALID_PROVIDERS:
        logger.warning(f"Unknown LLM provider '{provider}', falling back to 'vllm'")
        provider = 'vllm'

    if provider == 'ollama':
        return get_ollama_client()
    if provider == 'openai':
        return get_openai_client()
    if provider == 'anthropic':
        return get_anthropic_client()
    return get_vllm_client()


TASK_TARGET_FIELDS = {
    'understanding': 'understanding_target',
    'evaluation': 'evaluation_target',
}


def get_online_client():
    """Get whichever cloud vendor is currently configured as the Online tier."""
    try:
        from apps.llm.models import LLMProviderConfig
        online_provider = LLMProviderConfig.get_settings().online_provider
    except Exception:
        logger.warning("Could not read LLMProviderConfig, defaulting to openai", exc_info=True)
        online_provider = 'openai'

    if online_provider == 'anthropic':
        return get_anthropic_client()
    return get_openai_client()


def get_llm_client_for_task(task: str):
    """
    Get whichever LLM client should handle a given task type right now.

    Args:
        task: 'understanding' (news/report comprehension) or 'evaluation'
            (trade/position validation, ad-hoc chat) - see
            apps.llm.models.LLMProviderConfig for the full task/tier model.

    Returns:
        The client for whichever tier (local vLLM / online OpenAI-or-Claude)
        LLMProviderConfig assigns to this task. If that tier isn't currently
        enabled (e.g. online target but no API key set yet, or vLLM down),
        falls back to the other tier so a routing misconfiguration doesn't
        hard-fail the caller - the caller's own is_enabled() check still
        reports accurately either way.
    """
    field = TASK_TARGET_FIELDS.get(task)
    if field is None:
        logger.warning(f"Unknown LLM task type '{task}', defaulting to 'local'")
        target = 'local'
    else:
        try:
            from apps.llm.models import LLMProviderConfig
            target = getattr(LLMProviderConfig.get_settings(), field)
        except Exception:
            logger.warning(f"Could not read LLMProviderConfig for task '{task}', defaulting to 'local'", exc_info=True)
            target = 'local'

    def _client_for(tier):
        return get_online_client() if tier == 'online' else get_vllm_client()

    client = _client_for(target)
    if not client.is_enabled():
        fallback_target = 'online' if target == 'local' else 'local'
        fallback_client = _client_for(fallback_target)
        if fallback_client.is_enabled():
            logger.warning(
                f"Task '{task}' is routed to '{target}' but it's not enabled - "
                f"falling back to '{fallback_target}' for this call"
            )
            return fallback_client
    return client
