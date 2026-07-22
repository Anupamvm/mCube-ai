"""
Shared text-analysis helpers built purely on top of generate().

Extracted from VLLMClient so OpenAIClient gets the same
analyze_sentiment/summarize/extract_insights/answer_question behavior -
these methods never touched anything vLLM-specific, they just call
self.generate(), so duplicating them per-provider would only invite drift.
Any class mixing this in must provide generate(prompt, system, temperature,
max_tokens) -> (success, text, metadata).
"""

import json
import logging
from typing import Dict, List, Tuple

from apps.llm.services.response_parsing import extract_json

logger = logging.getLogger(__name__)


class LLMTextAnalysisMixin:
    def analyze_sentiment(
        self,
        text: str
    ) -> Tuple[bool, Dict, Dict]:
        """
        Analyze sentiment of text.

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

        try:
            sentiment_data = extract_json(response)
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
        Generate a summary of the text.

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
        Extract key insights from text.

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

        try:
            insights = extract_json(response)
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
        Answer a question based on provided context (for RAG).

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
