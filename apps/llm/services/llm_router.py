"""
LLM Provider Router

Resolves a provider name to the corresponding LLM client singleton, so
callers can pick 'vllm', 'ollama', or 'openai' without importing each
client module directly. Existing direct callers (analyst_report_analyzer,
news_impact_analyzer, etc.) are unaffected - this is an additive entry
point for code that wants provider choice (e.g. apps.llmskill).
"""

import logging
import os

from apps.llm.services.vllm_client import get_vllm_client
from apps.llm.services.ollama_client import get_ollama_client
from apps.llm.services.openai_client import get_openai_client

logger = logging.getLogger(__name__)

VALID_PROVIDERS = ('vllm', 'ollama', 'openai')


def get_llm_client(provider: str = None):
    """
    Get an LLM client by provider name.

    Args:
        provider: 'vllm', 'ollama', or 'openai'. Defaults to the
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
    return get_vllm_client()


def get_active_llm_client(local_provider: str = 'vllm'):
    """
    Get whichever LLM client should serve requests right now, respecting the
    system-wide OpenAI override configured at /llm/models/.

    Args:
        local_provider: which client this call site normally uses ('vllm' or
            'ollama') when the system isn't overridden to OpenAI. Ignored
            when the override is active.

    Returns:
        The OpenAI client if apps.llm.models.LLMProviderConfig.active_provider
        is 'openai'; otherwise the caller's normal local provider, unchanged.
    """
    try:
        from apps.llm.models import LLMProviderConfig
        active = LLMProviderConfig.get_settings().active_provider
    except Exception:
        logger.warning("Could not read LLMProviderConfig, defaulting to local provider", exc_info=True)
        active = 'vllm'

    if active == 'openai':
        return get_openai_client()
    return get_llm_client(local_provider)
