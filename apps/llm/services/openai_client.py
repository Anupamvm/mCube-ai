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

logger = logging.getLogger(__name__)


class OpenAIClient:
    """
    Client for OpenAI's cloud ChatGPT API.

    Configuration (checked in this order):
        apps.llm.models.LLMProviderConfig.openai_api_key / openai_model -
            set from the /llm/models/ UI, takes priority so the key can be
            entered and changed at runtime without an env var / restart.
        OPENAI_API_KEY / OPENAI_MODEL env vars - fallback for local/dev use.
    """

    def __init__(self):
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

    def is_enabled(self) -> bool:
        """Check if OpenAI client is enabled (API key configured)."""
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
