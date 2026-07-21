"""
vLLM Client Service using OpenAI-compatible API

This service handles communication with vLLM server for:
- Text generation and completion
- Chat completions
- Document analysis
- Sentiment extraction
"""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple
from openai import OpenAI

logger = logging.getLogger(__name__)


class VLLMClient:
    """
    Client for interacting with vLLM server using OpenAI-compatible API

    Configuration:
        VLLM_HOST: vLLM server URL (tries public then local IP automatically)
        VLLM_MODEL: Model name (default: hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4)
        VLLM_API_KEY: API key if required (default: not-needed)

    The client automatically tries multiple URLs in order:
    1. Public IP (27.107.134.179) - works from external networks
    2. Local IP (192.168.1.32) - works from same network
    """

    # Default URLs to try in order (public first, then local)
    DEFAULT_URLS = [
        'http://27.107.134.179:8000/v1',  # Public IP
        'http://192.168.1.32:8000/v1',     # Local IP
    ]

    # Short timeout just for probing which candidate URL is reachable
    CONNECT_TIMEOUT = 10.0

    # How often a long-running process (Django, Celery worker/beat, Telegram bot)
    # re-verifies which model the server is actually serving. The GPU-server update
    # agent can switch models out from under any of these at any time - without this,
    # a process that connected before a switch would keep requesting the old model
    # name for its entire lifetime (until restarted).
    MODEL_RECHECK_SECONDS = 30

    def __init__(self):
        """Initialize vLLM client with automatic URL fallback"""
        self.api_key = os.getenv('VLLM_API_KEY', 'not-needed')
        # Real generation on a 70B model can take a while; keep this well above CONNECT_TIMEOUT
        self.request_timeout = float(os.getenv('VLLM_TIMEOUT', '120'))
        # Only used if the server can't tell us what it's actually serving
        self._fallback_model = os.getenv('VLLM_MODEL', 'hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4')
        self.model = self._fallback_model

        # If VLLM_HOST is explicitly set, use only that URL
        explicit_host = os.getenv('VLLM_HOST')
        self._urls_to_try = [explicit_host] if explicit_host else self.DEFAULT_URLS

        self.base_url = None
        self.client = None
        self.enabled = False
        self._last_recheck = 0.0

        self._connect()

    def _connect(self):
        """(Re)establish a connection, discovering whichever model the server is currently serving."""
        for url in self._urls_to_try:
            logger.info(f"Trying vLLM server at {url}...")
            try:
                probe_client = OpenAI(
                    base_url=url,
                    api_key=self.api_key,
                    timeout=self.CONNECT_TIMEOUT
                )
                served_model = self._discover_served_model(probe_client)
                if served_model:
                    self.base_url = url
                    self.model = served_model
                    # Separate client with a longer timeout for actual generation requests
                    self.client = OpenAI(
                        base_url=url,
                        api_key=self.api_key,
                        timeout=self.request_timeout
                    )
                    self.enabled = True
                    logger.info(f"Successfully connected to vLLM at {url} (serving {served_model})")
                    return
            except Exception as e:
                logger.warning(f"Failed to connect to {url}: {str(e)}")
                continue
            finally:
                # Set at completion, not start: a connect attempt against an
                # unreachable server can itself take longer than
                # MODEL_RECHECK_SECONDS (SDK-level retries + a fallback probe
                # per URL). Stamping this at the start let every _refresh_if_stale()
                # call made by a caller that hit this same slow path immediately
                # see itself as "stale" again and kick off another full
                # multi-URL connect attempt - e.g. system_test_page() calls
                # is_enabled() 5x while testing vLLM, which serialized into 5+
                # minutes of blocking retries with the server down.
                self._last_recheck = time.time()

        logger.warning("Could not connect to any vLLM server")
        self.enabled = False
        if not self.base_url:
            # Set defaults for error reporting
            self.base_url = self._urls_to_try[0] if self._urls_to_try else 'not-configured'
            self.client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.request_timeout)

    def _refresh_if_stale(self):
        """Re-verify (at most every MODEL_RECHECK_SECONDS) that we're still talking to
        whatever model the server is currently serving, reconnecting if it changed or
        if we were previously unreachable. Cheap - just a GET /v1/models."""
        if time.time() - self._last_recheck < self.MODEL_RECHECK_SECONDS:
            return

        if self.enabled and self.client:
            self._last_recheck = time.time()
            served_model = self._discover_served_model(self.client)
            if served_model and served_model != self.model:
                logger.info(f"vLLM now serving '{served_model}' (was '{self.model}') - switching client to match")
                self.model = served_model
            elif not served_model:
                logger.warning("vLLM server became unreachable")
                self.enabled = False
        else:
            self._connect()

    def _discover_served_model(self, client: OpenAI) -> Optional[str]:
        """Ask the server which model it's actually serving.

        vLLM serves exactly one model per instance, but the model name can change
        any time someone uses the update agent to switch models - so we must ask
        the server rather than trust a locally configured name, or every request
        would target a model that's no longer running.
        """
        try:
            models = client.models.list()
            model_ids = [m.id for m in models.data]
            if model_ids:
                return model_ids[0]
        except Exception:
            pass

        # Fallback: /v1/models unavailable for some reason - probe with a real
        # completion using the locally configured model name.
        try:
            response = client.chat.completions.create(
                model=self._fallback_model,
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=5,
                temperature=0.1
            )
            if response and response.choices:
                return self._fallback_model
        except Exception:
            pass
        return None

    def is_enabled(self) -> bool:
        """Check if vLLM client is enabled (re-verifies periodically - see MODEL_RECHECK_SECONDS)"""
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

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream response (not implemented yet)

        Returns:
            Tuple[bool, str, Dict]: (success, response_text, metadata)
        """
        self._refresh_if_stale()
        if not self.enabled:
            return False, "", {"error": "vLLM not enabled"}

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

                logger.info(f"vLLM chat successful ({processing_time}ms, {metadata['usage']['total_tokens']} tokens)")
                return True, response_text, metadata
            else:
                error_msg = "No response from vLLM"
                logger.error(error_msg)
                return False, "", {"error": error_msg}

        except Exception as e:
            error_msg = f"Error calling vLLM: {str(e)}"
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
        Generate text completion using vLLM

        Args:
            prompt: User prompt
            system: System prompt/context
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns:
            Tuple[bool, str, Dict]: (success, response_text, metadata)
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        return self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def analyze_sentiment(
        self,
        text: str
    ) -> Tuple[bool, Dict, Dict]:
        """
        Analyze sentiment of text using vLLM

        Args:
            text: Text to analyze

        Returns:
            Tuple[bool, Dict, Dict]: (success, sentiment_data, metadata)
            sentiment_data contains: label, score, confidence
        """
        system_prompt = """You are a financial sentiment analysis expert.
Analyze the sentiment of the given text and respond ONLY with a JSON object in this exact format:
{
  "label": "POSITIVE" or "NEUTRAL" or "NEGATIVE",
  "score": a number between -1.0 (very negative) and 1.0 (very positive),
  "confidence": a number between 0.0 and 1.0 indicating your confidence
}"""

        success, response, metadata = self.generate(
            prompt=text,
            system=system_prompt,
            temperature=0.1,
            max_tokens=100
        )

        if not success:
            return False, {}, metadata

        # Parse JSON response
        import json
        try:
            # Try to extract JSON from response
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            sentiment_data = json.loads(response)
            return True, sentiment_data, metadata
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse sentiment response: {response}")
            return False, {}, {"error": f"JSON parse error: {str(e)}"}

    def summarize(
        self,
        text: str,
        max_length: int = 200
    ) -> Tuple[bool, str, Dict]:
        """
        Generate a summary of the text

        Args:
            text: Text to summarize
            max_length: Maximum length of summary in words

        Returns:
            Tuple[bool, str, Dict]: (success, summary, metadata)
        """
        system_prompt = f"""You are a financial analysis expert.
Summarize the following text concisely in about {max_length} words or less.
Focus on key financial facts, numbers, and important insights."""

        return self.generate(
            prompt=text,
            system=system_prompt,
            temperature=0.3,
            max_tokens=int(max_length * 1.5)  # Roughly 1.5 tokens per word
        )

    def extract_insights(
        self,
        text: str,
        num_insights: int = 5
    ) -> Tuple[bool, List[str], Dict]:
        """
        Extract key insights from text

        Args:
            text: Text to analyze
            num_insights: Number of insights to extract

        Returns:
            Tuple[bool, List[str], Dict]: (success, insights_list, metadata)
        """
        system_prompt = f"""You are a financial analysis expert.
Extract the top {num_insights} key insights from the following text.
Respond ONLY with a JSON array of strings, each string being one insight.
Example: ["Insight 1", "Insight 2", "Insight 3"]"""

        success, response, metadata = self.generate(
            prompt=text,
            system=system_prompt,
            temperature=0.3,
            max_tokens=500
        )

        if not success:
            return False, [], metadata

        # Parse JSON response
        import json
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            insights = json.loads(response)
            if isinstance(insights, list):
                return True, insights, metadata
            else:
                logger.error(f"Insights response is not a list: {response}")
                return False, [], {"error": "Invalid response format"}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse insights response: {response}")
            return False, [], {"error": f"JSON parse error: {str(e)}"}

    def answer_question(
        self,
        question: str,
        context: str,
        temperature: float = 0.3
    ) -> Tuple[bool, str, Dict]:
        """
        Answer a question based on provided context (for RAG)

        Args:
            question: Question to answer
            context: Context information to use
            temperature: Sampling temperature

        Returns:
            Tuple[bool, str, Dict]: (success, answer, metadata)
        """
        system_prompt = """You are a financial analysis assistant.
Answer the question based ONLY on the provided context.
If the context doesn't contain enough information, say so.
Be concise and factual."""

        prompt = f"""Context:
{context}

Question: {question}

Answer:"""

        return self.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=temperature,
            max_tokens=500
        )


# Global instance
_vllm_client = None


def get_vllm_client() -> VLLMClient:
    """Get or create global vLLM client instance"""
    global _vllm_client

    if _vllm_client is None:
        _vllm_client = VLLMClient()

    return _vllm_client


# Convenience functions

def generate_text(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7
) -> Tuple[bool, str]:
    """
    Generate text using vLLM (convenience function)

    Args:
        prompt: User prompt
        system: System prompt
        temperature: Sampling temperature

    Returns:
        Tuple[bool, str]: (success, response_text)
    """
    client = get_vllm_client()
    success, response, _ = client.generate(prompt, system=system, temperature=temperature)
    return success, response


def chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.7
) -> Tuple[bool, str]:
    """
    Chat completion (convenience function)

    Args:
        messages: List of message dicts
        temperature: Sampling temperature

    Returns:
        Tuple[bool, str]: (success, response)
    """
    client = get_vllm_client()
    success, response, _ = client.chat(messages, temperature=temperature)
    return success, response
