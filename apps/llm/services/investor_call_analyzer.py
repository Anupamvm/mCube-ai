"""
Investor/Earnings Call Transcript Analyzer

Analyzes earnings call transcripts (sourced from Trendlyne's mirror of the
BSE-filed "Earnings Call Transcript" PDF) using an LLM to extract:
- Executive summary and key highlights
- Management tone (POSITIVE/NEUTRAL/NEGATIVE)
- Trading signal (BULLISH/NEUTRAL/BEARISH) with confidence
- Forward outlook and concerns raised

Feeds apps.data.models.InvestorCall, which EnhancedFuturesAnalyzer's
_score_investor_calls() already reads (a 10-point scoring component that
silently defaulted to a neutral score whenever the table was empty).
"""

import logging
from typing import Dict, Optional

from apps.llm.services.response_parsing import extract_json

logger = logging.getLogger(__name__)


def analyze_earnings_call(transcript_text: str, symbol: str, call_date: Optional[str] = None) -> Dict:
    """
    Analyze an earnings call transcript for management tone and trading signal.

    Args:
        transcript_text: Extracted transcript text (already truncated to a
            reasonable size by the caller - see extract_pdf_text_truncated)
        symbol: Stock symbol
        call_date: Optional call date string, used only for prompt context

    Returns:
        Dict with:
            - success: bool
            - executive_summary: str
            - key_highlights: List[str] (up to 5)
            - management_tone: POSITIVE/NEUTRAL/NEGATIVE
            - outlook: str
            - concerns_raised: List[str] (up to 5)
            - trading_signal: BULLISH/NEUTRAL/BEARISH
            - confidence_score: float (0-1)
    """
    from apps.llm.services.llm_router import get_llm_client_for_task

    llm_client = get_llm_client_for_task('understanding')

    empty_result = {
        'success': False,
        'executive_summary': '',
        'key_highlights': [],
        'management_tone': None,
        'outlook': '',
        'concerns_raised': [],
        'trading_signal': None,
        'confidence_score': None,
    }

    if not llm_client.is_enabled():
        logger.warning("LLM not available for earnings call analysis")
        return {**empty_result, 'error': 'LLM not available'}

    if not transcript_text or len(transcript_text.strip()) < 200:
        logger.warning(f"Insufficient transcript text for {symbol}")
        return {**empty_result, 'error': 'Insufficient transcript text'}

    max_chars = 12000
    if len(transcript_text) > max_chars:
        transcript_text = transcript_text[:max_chars] + "\n[...]"

    context = f"Stock: {symbol}" + (f" | Call date: {call_date}" if call_date else "")

    prompt = f"""Analyze this earnings call transcript and extract trading-relevant signals.

{context}

TRANSCRIPT:
{transcript_text}

Return ONLY valid JSON (no markdown):
{{"executive_summary": "<2-3 sentence summary>", "key_highlights": ["<point 1>", "<point 2>", "<point 3>", "<point 4>", "<point 5>"], "management_tone": "<POSITIVE|NEUTRAL|NEGATIVE>", "outlook": "<1-2 sentence forward guidance summary>", "concerns_raised": ["<concern 1>", "<concern 2>"], "trading_signal": "<BULLISH|NEUTRAL|BEARISH>", "confidence_score": <0.0 to 1.0>}}

Base management_tone on how management characterized results and guidance. Base trading_signal on whether the call content supports a bullish, neutral, or bearish near-term stance. confidence_score reflects how clear/unambiguous the signal is."""

    try:
        # Same lesson as get_quick_report_summary(): the served model emits a
        # <think>...</think> block before the JSON answer that alone can run
        # several hundred tokens, so the budget must cover both.
        success, response, _ = llm_client.generate(
            prompt=prompt,
            system="You are a financial analyst specializing in earnings call analysis. Return only valid JSON.",
            temperature=0.3,
            max_tokens=2000
        )

        if not success:
            return {**empty_result, 'error': 'LLM call failed'}

        data = extract_json(response)

        return {
            'success': True,
            'executive_summary': data.get('executive_summary', ''),
            'key_highlights': data.get('key_highlights', [])[:5],
            'management_tone': (data.get('management_tone') or 'NEUTRAL').upper(),
            'outlook': data.get('outlook', ''),
            'concerns_raised': data.get('concerns_raised', [])[:5],
            'trading_signal': (data.get('trading_signal') or 'NEUTRAL').upper(),
            'confidence_score': float(data.get('confidence_score', 0.5)),
        }

    except Exception as e:
        logger.warning(f"Failed to parse earnings call analysis for {symbol}: {e}")
        return {**empty_result, 'error': str(e)}
