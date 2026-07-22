"""
Anthropic (Claude) Client Service

Cloud counterpart to VLLMClient/OpenAIClient - talks to Claude via the
official Anthropic SDK instead of an OpenAI-compatible endpoint. Exposes the
same chat()/generate() interface (OpenAI-style messages in, (success, text,
metadata) out) used throughout this app, so it's a drop-in for
get_llm_client_for_task() callers without touching call sites.

temperature is deliberately never forwarded to the Anthropic API: Claude's
current-generation models (Opus 4.7+, Sonnet 5, Fable 5) reject temperature/
top_p/top_k outright (400 error), and since anthropic_model is admin-
configurable here, hardcoding support for one model generation would break
on another. Prompting is Anthropic's documented replacement for sampling
control on those models.
"""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple
from anthropic import Anthropic

from apps.llm.services.llm_text_analysis import LLMTextAnalysisMixin

logger = logging.getLogger(__name__)


class AnthropicClient(LLMTextAnalysisMixin):
    """
    Client for Anthropic's Claude API.

    Configuration (checked in this order):
        apps.llm.models.LLMProviderConfig.anthropic_api_key / anthropic_model -
            set from the /llm/models/ UI, takes priority so the key can be
            entered and changed at runtime without an env var / restart.
        ANTHROPIC_API_KEY / ANTHROPIC_MODEL env vars - fallback for local/dev use.
    """

    # Mirrors OpenAIClient.CONFIG_RECHECK_SECONDS - Django, Celery worker/beat,
    # and the Telegram bot are separate processes that each cache their own
    # client singleton, so this re-reads LLMProviderConfig periodically to
    # pick up a key/model change made (possibly from another device) without
    # needing a restart. See OpenAIClient for the full rationale.
    CONFIG_RECHECK_SECONDS = 30

    def __init__(self):
        self._load_config()
        self._last_config_check = time.time()

    def _load_config(self):
        api_key = ''
        model = os.getenv('ANTHROPIC_MODEL', 'claude-opus-4-8')
        try:
            from apps.llm.models import LLMProviderConfig
            cfg = LLMProviderConfig.get_settings()
            api_key = cfg.anthropic_api_key or os.getenv('ANTHROPIC_API_KEY', '')
            model = cfg.anthropic_model or model
        except Exception:
            # DB may not be migrated/reachable yet (e.g. during migrate itself) - fall back to env.
            api_key = os.getenv('ANTHROPIC_API_KEY', '')

        self.api_key = api_key
        self.model = model
        self.request_timeout = float(os.getenv('ANTHROPIC_TIMEOUT', '60'))

        self.enabled = bool(self.api_key)
        self.client = Anthropic(api_key=self.api_key, timeout=self.request_timeout) if self.enabled else None

        if not self.enabled:
            logger.warning("No Anthropic API key configured (LLMProviderConfig or ANTHROPIC_API_KEY) - AnthropicClient disabled")

    def _refresh_if_stale(self):
        """Re-read LLMProviderConfig at most every CONFIG_RECHECK_SECONDS and
        reconnect if the key/model changed - see class docstring."""
        if time.time() - self._last_config_check < self.CONFIG_RECHECK_SECONDS:
            return
        self._last_config_check = time.time()

        try:
            from apps.llm.models import LLMProviderConfig
            cfg = LLMProviderConfig.get_settings()
            new_key = cfg.anthropic_api_key or os.getenv('ANTHROPIC_API_KEY', '')
            new_model = cfg.anthropic_model or os.getenv('ANTHROPIC_MODEL', 'claude-opus-4-8')
        except Exception:
            return

        if new_key != self.api_key or new_model != self.model:
            logger.info("Anthropic config changed (key/model updated elsewhere) - reconnecting client")
            self._load_config()

    def is_enabled(self) -> bool:
        """Check if Anthropic client is enabled (re-verifies periodically - see CONFIG_RECHECK_SECONDS)."""
        self._refresh_if_stale()
        return self.enabled

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = 1000,
        stream: bool = False
    ) -> Tuple[bool, str, Dict]:
        """
        Chat completion with conversation history.

        `messages` follows the OpenAI role/content shape used throughout this
        codebase - translated here into Claude's system + messages split
        (Claude takes the system prompt as a separate top-level parameter,
        not as a message with role='system' in the list).

        Returns:
            Tuple[bool, str, Dict]: (success, response_text, metadata)
        """
        self._refresh_if_stale()
        if not self.enabled:
            return False, "", {"error": "Anthropic client not enabled (missing ANTHROPIC_API_KEY)"}

        system_parts = [m['content'] for m in messages if m.get('role') == 'system']
        system = "\n\n".join(system_parts) if system_parts else None
        claude_messages = [m for m in messages if m.get('role') != 'system']

        try:
            start_time = time.time()

            kwargs = {
                "model": self.model,
                "max_tokens": max_tokens or 1000,
                "messages": claude_messages,
            }
            if system:
                kwargs["system"] = system

            response = self.client.messages.create(**kwargs)

            processing_time = int((time.time() - start_time) * 1000)

            response_text = next((b.text for b in response.content if b.type == "text"), "")

            if response.stop_reason == "refusal":
                error_msg = "Claude declined the request (safety refusal)"
                logger.error(error_msg)
                return False, "", {"error": error_msg}

            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0

            metadata = {
                "model": self.model,
                "processing_time_ms": processing_time,
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                "finish_reason": response.stop_reason,
            }

            logger.info(f"Anthropic chat successful ({processing_time}ms, {metadata['usage']['total_tokens']} tokens)")
            return True, response_text, metadata

        except Exception as e:
            error_msg = f"Error calling Anthropic: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, "", {"error": error_msg}

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = 1000
    ) -> Tuple[bool, str, Dict]:
        """
        Generate text completion using Claude.

        Returns:
            Tuple[bool, str, Dict]: (success, response_text, metadata)
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        return self.chat(messages, temperature=temperature, max_tokens=max_tokens)


# Global instance
_anthropic_client = None


def get_anthropic_client() -> AnthropicClient:
    """Get or create global AnthropicClient instance"""
    global _anthropic_client

    if _anthropic_client is None:
        _anthropic_client = AnthropicClient()

    return _anthropic_client


def reset_anthropic_client() -> None:
    """Drop the cached instance so the next get_anthropic_client() re-reads the
    API key/model - call this right after saving a new key from the UI."""
    global _anthropic_client
    _anthropic_client = None
