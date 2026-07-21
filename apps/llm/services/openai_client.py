"""
OpenAI (ChatGPT) Client Service

Cloud counterpart to VLLMClient - same OpenAI SDK, pointed at the real
OpenAI API instead of a self-hosted vLLM server.
"""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple
from openai import OpenAI

from apps.llm.services.llm_text_analysis import LLMTextAnalysisMixin

logger = logging.getLogger(__name__)


class OpenAIClient(LLMTextAnalysisMixin):
    """
    Client for OpenAI's cloud ChatGPT API.

    Configuration (checked in this order):
        apps.llm.models.LLMProviderConfig.openai_api_key / openai_model -
            set from the /llm/models/ UI, takes priority so the key can be
            entered and changed at runtime without an env var / restart.
        OPENAI_API_KEY / OPENAI_MODEL env vars - fallback for local/dev use.
    """

    # How often a long-running process (Django, Celery worker/beat, Telegram
    # bot) re-reads LLMProviderConfig for a changed key/model. Each of those
    # is a separate process with its own cached OpenAIClient singleton, so a
    # switch made from the /llm/models/ UI (possibly on another device) only
    # calls reset_openai_client() in whichever process served that request -
    # every other process would otherwise keep using stale credentials until
    # restarted. Mirrors VLLMClient.MODEL_RECHECK_SECONDS.
    CONFIG_RECHECK_SECONDS = 30

    def __init__(self):
        self._load_config()
        self._last_config_check = time.time()

    def _load_config(self):
        api_key = ''
        model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        try:
            from apps.llm.models import LLMProviderConfig
            cfg = LLMProviderConfig.get_settings()
            api_key = cfg.openai_api_key or os.getenv('OPENAI_API_KEY', '')
            model = cfg.openai_model or model
        except Exception:
            # DB may not be migrated/reachable yet (e.g. during migrate itself) - fall back to env.
            api_key = os.getenv('OPENAI_API_KEY', '')

        self.api_key = api_key
        self.model = model
        self.request_timeout = float(os.getenv('OPENAI_TIMEOUT', '60'))

        self.enabled = bool(self.api_key)
        self.client = OpenAI(api_key=self.api_key, timeout=self.request_timeout) if self.enabled else None

        if not self.enabled:
            logger.warning("No OpenAI API key configured (LLMProviderConfig or OPENAI_API_KEY) - OpenAIClient disabled")

    def _refresh_if_stale(self):
        """Re-read LLMProviderConfig at most every CONFIG_RECHECK_SECONDS and
        reconnect if the key/model changed - see class docstring."""
        if time.time() - self._last_config_check < self.CONFIG_RECHECK_SECONDS:
            return
        self._last_config_check = time.time()

        try:
            from apps.llm.models import LLMProviderConfig
            cfg = LLMProviderConfig.get_settings()
            new_key = cfg.openai_api_key or os.getenv('OPENAI_API_KEY', '')
            new_model = cfg.openai_model or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        except Exception:
            return

        if new_key != self.api_key or new_model != self.model:
            logger.info("OpenAI config changed (key/model updated elsewhere) - reconnecting client")
            self._load_config()

    def is_enabled(self) -> bool:
        """Check if OpenAI client is enabled (re-verifies periodically - see CONFIG_RECHECK_SECONDS)."""
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
        Chat completion with conversation history

        Returns:
            Tuple[bool, str, Dict]: (success, response_text, metadata)
        """
        self._refresh_if_stale()
        if not self.enabled:
            return False, "", {"error": "OpenAI client not enabled (missing OPENAI_API_KEY)"}

        try:
            start_time = time.time()

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )

            processing_time = int((time.time() - start_time) * 1000)

            if response.choices:
                response_text = response.choices[0].message.content

                metadata = {
                    "model": self.model,
                    "processing_time_ms": processing_time,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                    },
                    "finish_reason": response.choices[0].finish_reason
                }

                logger.info(f"OpenAI chat successful ({processing_time}ms, {metadata['usage']['total_tokens']} tokens)")
                return True, response_text, metadata
            else:
                error_msg = "No response from OpenAI"
                logger.error(error_msg)
                return False, "", {"error": error_msg}

        except Exception as e:
            error_msg = f"Error calling OpenAI: {str(e)}"
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
        Generate text completion using OpenAI

        Returns:
            Tuple[bool, str, Dict]: (success, response_text, metadata)
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        return self.chat(messages, temperature=temperature, max_tokens=max_tokens)


# Global instance
_openai_client = None


def get_openai_client() -> OpenAIClient:
    """Get or create global OpenAIClient instance"""
    global _openai_client

    if _openai_client is None:
        _openai_client = OpenAIClient()

    return _openai_client


def reset_openai_client() -> None:
    """Drop the cached instance so the next get_openai_client() re-reads the
    API key/model - call this right after saving a new key from the UI."""
    global _openai_client
    _openai_client = None
