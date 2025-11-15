"""
Ollama LLM Client Service

This service handles communication with local Ollama LLM server for:
- Text generation and completion
- Embeddings generation
- Trade validation
- News analysis
- Sentiment extraction
"""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple
import requests
import json

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Client for interacting with Ollama LLM server

    Configuration:
        OLLAMA_HOST: Ollama server URL (default: http://localhost:11434)
        OLLAMA_MODEL: Default model to use (default: deepseek-coder:33b)
    """

    def __init__(self):
        """Initialize Ollama client"""
        self.host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.default_model = os.getenv('OLLAMA_MODEL', 'deepseek-coder:33b')

        # Verify connection
        self.enabled = self._check_connection()

    def _check_connection(self) -> bool:
        """Check if Ollama server is accessible"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                logger.info(f"Ollama server connected at {self.host}")
                return True
            else:
                logger.warning(f"Ollama server returned {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Ollama server not accessible: {str(e)}")
            return False

    def is_enabled(self) -> bool:
        """Check if Ollama client is enabled"""
        return self.enabled

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Tuple[bool, str, Dict]:
        """
        Generate text completion using Ollama

        Args:
            prompt: User prompt
            model: Model to use (default: self.default_model)
            system: System prompt/context
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream response

        Returns:
            Tuple[bool, str, Dict]: (success, response_text, metadata)
        """
        if not self.enabled:
            return False, "", {"error": "Ollama not enabled"}

        model = model or self.default_model

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": temperature,
            }
        }

        if system:
            payload["system"] = system

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        try:
            start_time = time.time()

            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=300  # 5 minutes for long generations
            )

            if response.status_code != 200:
                error_msg = f"Ollama API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, "", {"error": error_msg}

            result = response.json()
            response_text = result.get('response', '')
            processing_time = int((time.time() - start_time) * 1000)

            metadata = {
                "model": model,
                "processing_time_ms": processing_time,
                "tokens_generated": len(response_text.split()),  # Rough estimate
                "done": result.get('done', False)
            }

            logger.info(f"Ollama generation successful ({processing_time}ms)")
            return True, response_text, metadata

        except Exception as e:
            error_msg = f"Error calling Ollama: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, "", {"error": error_msg}

    def generate_embedding(
        self,
        text: str,
        model: Optional[str] = None
    ) -> Tuple[bool, List[float], Dict]:
        """
        Generate text embedding using Ollama

        Args:
            text: Text to embed
            model: Model to use (default: self.default_model)

        Returns:
            Tuple[bool, List[float], Dict]: (success, embedding_vector, metadata)
        """
        if not self.enabled:
            return False, [], {"error": "Ollama not enabled"}

        model = model or self.default_model

        payload = {
            "model": model,
            "prompt": text
        }

        try:
            start_time = time.time()

            response = requests.post(
                f"{self.host}/api/embeddings",
                json=payload,
                timeout=60
            )

            if response.status_code != 200:
                error_msg = f"Ollama embedding error: {response.status_code}"
                logger.error(error_msg)
                return False, [], {"error": error_msg}

            result = response.json()
            embedding = result.get('embedding', [])
            processing_time = int((time.time() - start_time) * 1000)

            metadata = {
                "model": model,
                "processing_time_ms": processing_time,
                "embedding_dim": len(embedding)
            }

            logger.debug(f"Embedding generated ({processing_time}ms, dim={len(embedding)})")
            return True, embedding, metadata

        except Exception as e:
            error_msg = f"Error generating embedding: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, [], {"error": error_msg}

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> Tuple[bool, str, Dict]:
        """
        Chat completion with conversation history

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use
            temperature: Sampling temperature

        Returns:
            Tuple[bool, str, Dict]: (success, response, metadata)
        """
        if not self.enabled:
            return False, "", {"error": "Ollama not enabled"}

        model = model or self.default_model

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }

        try:
            start_time = time.time()

            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=300
            )

            if response.status_code != 200:
                error_msg = f"Ollama chat error: {response.status_code}"
                logger.error(error_msg)
                return False, "", {"error": error_msg}

            result = response.json()
            message = result.get('message', {})
            response_text = message.get('content', '')
            processing_time = int((time.time() - start_time) * 1000)

            metadata = {
                "model": model,
                "processing_time_ms": processing_time,
                "role": message.get('role', 'assistant')
            }

            logger.info(f"Chat response received ({processing_time}ms)")
            return True, response_text, metadata

        except Exception as e:
            error_msg = f"Error in chat: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, "", {"error": error_msg}

    def extract_json_from_response(self, response: str) -> Optional[Dict]:
        """
        Extract JSON from LLM response

        Handles cases where LLM wraps JSON in markdown code blocks

        Args:
            response: LLM response text

        Returns:
            Optional[Dict]: Parsed JSON or None
        """
        try:
            # Try direct JSON parse
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract from code block
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end != -1:
                    json_str = response[start:end].strip()
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass

            # Try to find any JSON-like structure
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                json_str = response[start:end+1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

            logger.warning("Could not extract JSON from response")
            return None

    def list_models(self) -> List[str]:
        """
        List available Ollama models

        Returns:
            List[str]: List of model names
        """
        if not self.enabled:
            return []

        try:
            response = requests.get(f"{self.host}/api/tags", timeout=10)
            if response.status_code == 200:
                result = response.json()
                models = [m.get('name') for m in result.get('models', [])]
                return models
            return []
        except Exception as e:
            logger.error(f"Error listing models: {str(e)}")
            return []


# Global instance
_ollama_client = None


def get_ollama_client() -> OllamaClient:
    """Get or create global Ollama client instance"""
    global _ollama_client

    if _ollama_client is None:
        _ollama_client = OllamaClient()

    return _ollama_client


# Convenience functions

def generate_text(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7
) -> Tuple[bool, str]:
    """
    Generate text using Ollama (convenience function)

    Args:
        prompt: User prompt
        system: System prompt
        temperature: Sampling temperature

    Returns:
        Tuple[bool, str]: (success, response_text)
    """
    client = get_ollama_client()
    success, response, _ = client.generate(prompt, system=system, temperature=temperature)
    return success, response


def generate_embedding(text: str) -> Tuple[bool, List[float]]:
    """
    Generate embedding (convenience function)

    Args:
        text: Text to embed

    Returns:
        Tuple[bool, List[float]]: (success, embedding_vector)
    """
    client = get_ollama_client()
    success, embedding, _ = client.generate_embedding(text)
    return success, embedding
