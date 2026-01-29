"""
Analyst Report Analyzer Service

Analyzes analyst research report PDFs using LLM to extract:
- Summary of key points
- Sentiment score (-1 to 1)
- Trade recommendation (BULLISH/NEUTRAL/BEARISH)
- Risk factors and positive catalysts
"""

import json
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AnalystReportAnalyzer:
    """
    Analyzes analyst research reports using LLM.

    Extracts structured insights from PDF text including:
    - llm_summary: Concise summary of the report
    - key_insights: List of key points
    - sentiment_score: Float from -1 (bearish) to 1 (bullish)
    - trade_recommendation: BULLISH, NEUTRAL, or BEARISH
    - risk_factors: List of identified risks
    - catalysts: List of positive catalysts
    """

    def __init__(self):
        """Initialize with vLLM client"""
        from apps.llm.services.vllm_client import get_vllm_client
        self.llm_client = get_vllm_client()

    def analyze_report(
        self,
        pdf_text: str,
        symbol: str,
        author: str,
        target_price: Optional[float] = None,
        current_price: Optional[float] = None,
        recommendation_type: Optional[str] = None
    ) -> Dict:
        """
        Analyze analyst report text using LLM.

        Args:
            pdf_text: Extracted text content from PDF
            symbol: Stock symbol
            author: Report author/brokerage
            target_price: Analyst's target price (if available)
            current_price: Current stock price (if available)
            recommendation_type: Analyst's recommendation (BUY/SELL/HOLD)

        Returns:
            Dict with analysis results:
                - success: bool
                - llm_summary: str
                - key_insights: List[str]
                - sentiment_score: float (-1 to 1)
                - trade_recommendation: str (BULLISH/NEUTRAL/BEARISH)
                - risk_factors: List[str]
                - catalysts: List[str]
        """
        if not self.llm_client.is_enabled():
            logger.warning("LLM not available for analyst report analysis")
            return self._default_result("LLM not available")

        if not pdf_text or len(pdf_text.strip()) < 100:
            logger.warning(f"Insufficient PDF text for {symbol} report by {author}")
            return self._default_result("Insufficient text content")

        # Truncate text if too long (aim for ~4000 tokens = ~16000 chars)
        max_chars = 15000
        if len(pdf_text) > max_chars:
            pdf_text = pdf_text[:max_chars] + "\n\n[Content truncated for analysis]"

        # Build context about the report
        context_parts = [f"Stock: {symbol}"]
        if author:
            context_parts.append(f"Brokerage/Analyst: {author}")
        if target_price:
            context_parts.append(f"Target Price: ₹{target_price:,.2f}")
        if current_price:
            context_parts.append(f"Current Price: ₹{current_price:,.2f}")
            if target_price:
                upside = ((target_price - current_price) / current_price) * 100
                context_parts.append(f"Implied Upside: {upside:.1f}%")
        if recommendation_type:
            context_parts.append(f"Analyst Recommendation: {recommendation_type}")

        context = "\n".join(context_parts)

        prompt = f"""You are a financial analyst reviewing a research report. Analyze the following report and extract key information.

REPORT CONTEXT:
{context}

REPORT CONTENT:
{pdf_text}

ANALYSIS TASK:
1. Summarize the key points in 2-3 sentences
2. List 3-5 key insights from the report
3. Assess overall sentiment (-1.0 = very bearish, 0 = neutral, 1.0 = very bullish)
4. Determine trade recommendation based on the report
5. List key risk factors mentioned
6. List positive catalysts mentioned

Return ONLY valid JSON (no markdown, no code blocks):
{{"llm_summary": "<2-3 sentence summary>", "key_insights": ["<insight 1>", "<insight 2>", ...], "sentiment_score": <-1.0 to 1.0>, "trade_recommendation": "<BULLISH|NEUTRAL|BEARISH>", "risk_factors": ["<risk 1>", "<risk 2>", ...], "catalysts": ["<catalyst 1>", "<catalyst 2>", ...]}}"""

        system_prompt = """You are a financial research analyst. Analyze the report objectively and extract structured insights.
Always respond with valid JSON only, no markdown formatting or code blocks."""

        try:
            success, response, metadata = self.llm_client.generate(
                prompt=prompt,
                system=system_prompt,
                temperature=0.3,
                max_tokens=800
            )

            if not success:
                logger.error(f"LLM analysis failed for {symbol} report by {author}")
                return self._default_result("LLM analysis failed")

            result = self._parse_llm_response(response)
            result['success'] = True

            logger.info(f"Analyzed {symbol} report by {author}: "
                       f"sentiment={result['sentiment_score']:.2f}, "
                       f"recommendation={result['trade_recommendation']}")

            return result

        except Exception as e:
            logger.error(f"Error analyzing report: {e}", exc_info=True)
            return self._default_result(f"Analysis error: {str(e)}")

    def _parse_llm_response(self, response: str) -> Dict:
        """Parse and validate LLM JSON response"""
        try:
            # Clean up response
            response = response.strip()

            # Remove markdown code blocks if present
            if response.startswith("```json"):
                response = response[7:]
            elif response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            # Parse JSON
            data = json.loads(response)

            # Validate and normalize sentiment score
            sentiment_score = float(data.get('sentiment_score', 0.0))
            sentiment_score = max(-1.0, min(1.0, sentiment_score))

            # Validate trade recommendation
            trade_rec = data.get('trade_recommendation', 'NEUTRAL').upper()
            if trade_rec not in ['BULLISH', 'NEUTRAL', 'BEARISH']:
                # Infer from sentiment
                if sentiment_score >= 0.3:
                    trade_rec = 'BULLISH'
                elif sentiment_score <= -0.3:
                    trade_rec = 'BEARISH'
                else:
                    trade_rec = 'NEUTRAL'

            return {
                'llm_summary': data.get('llm_summary', ''),
                'key_insights': data.get('key_insights', [])[:5],  # Limit to 5
                'sentiment_score': sentiment_score,
                'trade_recommendation': trade_rec,
                'risk_factors': data.get('risk_factors', [])[:5],
                'catalysts': data.get('catalysts', [])[:5],
            }

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {response[:200]}, error: {e}")
            return self._default_result("Failed to parse LLM response")

    def _default_result(self, reason: str) -> Dict:
        """Return default result when analysis fails"""
        return {
            'success': False,
            'llm_summary': '',
            'key_insights': [],
            'sentiment_score': 0.0,
            'trade_recommendation': 'NEUTRAL',
            'risk_factors': [],
            'catalysts': [],
            'error': reason
        }

    def analyze_and_save(self, report) -> bool:
        """
        Analyze report and save results to database.

        Args:
            report: AnalystReport model instance

        Returns:
            bool: True if analysis succeeded and was saved
        """
        from apps.data.utils.pdf_extractor import extract_pdf_text_truncated
        from django.utils import timezone

        try:
            # Extract PDF text if not already done
            if not report.pdf_content_text and report.pdf_local_path:
                success, text, metadata = extract_pdf_text_truncated(report.pdf_local_path)
                if success:
                    report.pdf_content_text = text

            if not report.pdf_content_text:
                logger.warning(f"No PDF content for report {report.id}")
                report.processing_error = "No PDF content available"
                report.save()
                return False

            # Get current price if available
            current_price = None
            try:
                from apps.data.models import TLStockData
                stock_data = TLStockData.objects.filter(nsecode=report.nse_code).first()
                if stock_data:
                    current_price = stock_data.current_price
            except Exception:
                pass

            # Analyze the report
            result = self.analyze_report(
                pdf_text=report.pdf_content_text,
                symbol=report.symbol,
                author=report.author,
                target_price=float(report.target_price) if report.target_price else None,
                current_price=current_price,
                recommendation_type=report.recommendation_type
            )

            if result['success']:
                report.llm_summary = result['llm_summary']
                report.key_insights = result['key_insights']
                report.sentiment_score = result['sentiment_score']
                report.trade_recommendation = result['trade_recommendation']
                report.risk_factors = result['risk_factors']
                report.catalysts = result['catalysts']
                report.llm_processed = True
                report.llm_processed_at = timezone.now()
                report.processing_error = ''
            else:
                report.processing_error = result.get('error', 'Unknown error')

            report.save()
            return result['success']

        except Exception as e:
            logger.error(f"Error in analyze_and_save for report {report.id}: {e}", exc_info=True)
            report.processing_error = str(e)
            report.save()
            return False


# Global instance
_analyst_report_analyzer = None


def get_analyst_report_analyzer() -> AnalystReportAnalyzer:
    """Get or create global AnalystReportAnalyzer instance"""
    global _analyst_report_analyzer

    if _analyst_report_analyzer is None:
        _analyst_report_analyzer = AnalystReportAnalyzer()

    return _analyst_report_analyzer


def analyze_analyst_report(
    pdf_text: str,
    symbol: str,
    author: str,
    target_price: Optional[float] = None,
    current_price: Optional[float] = None,
    recommendation_type: Optional[str] = None
) -> Dict:
    """
    Convenience function to analyze an analyst report.

    Args:
        pdf_text: Extracted text from PDF
        symbol: Stock symbol
        author: Report author/brokerage
        target_price: Analyst's target price
        current_price: Current stock price
        recommendation_type: Analyst's recommendation

    Returns:
        Dict with analysis results
    """
    analyzer = get_analyst_report_analyzer()
    return analyzer.analyze_report(
        pdf_text=pdf_text,
        symbol=symbol,
        author=author,
        target_price=target_price,
        current_price=current_price,
        recommendation_type=recommendation_type
    )


def get_quick_report_summary(
    pdf_text: str,
    symbol: str,
    author: str,
    target_price: Optional[float] = None,
    recommendation_type: Optional[str] = None
) -> Dict:
    """
    Get a quick 5-point summary of an analyst report.

    This is a lighter analysis for displaying brief summaries
    of multiple reports in the verification UI.

    Args:
        pdf_text: Extracted text from PDF
        symbol: Stock symbol
        author: Report author/brokerage
        target_price: Analyst's target price
        recommendation_type: Analyst's recommendation

    Returns:
        Dict with:
            - success: bool
            - summary_points: List of 5 bullet points
            - sentiment: BULLISH/NEUTRAL/BEARISH
    """
    from apps.llm.services.vllm_client import get_vllm_client

    llm_client = get_vllm_client()

    if not llm_client.is_enabled():
        logger.warning("LLM not available for quick summary")
        return {
            'success': False,
            'summary_points': [],
            'sentiment': 'NEUTRAL',
            'error': 'LLM not available'
        }

    if not pdf_text or len(pdf_text.strip()) < 100:
        logger.warning(f"Insufficient PDF text for quick summary of {symbol}")
        return {
            'success': False,
            'summary_points': [],
            'sentiment': 'NEUTRAL',
            'error': 'Insufficient text'
        }

    # Truncate for quick analysis
    max_chars = 8000
    if len(pdf_text) > max_chars:
        pdf_text = pdf_text[:max_chars] + "\n[...]"

    # Build context
    context_parts = [f"Stock: {symbol}", f"Analyst: {author}"]
    if target_price:
        context_parts.append(f"Target: ₹{target_price:,.0f}")
    if recommendation_type:
        context_parts.append(f"Rating: {recommendation_type}")
    context = " | ".join(context_parts)

    prompt = f"""Summarize this analyst research report in exactly 5 concise bullet points.

REPORT: {context}

CONTENT:
{pdf_text}

Return ONLY valid JSON (no markdown):
{{"summary_points": ["<point 1>", "<point 2>", "<point 3>", "<point 4>", "<point 5>"], "sentiment": "<BULLISH|NEUTRAL|BEARISH>"}}

Keep each point to 1 short sentence (max 15 words). Focus on: key thesis, target rationale, risks, catalysts, and overall stance."""

    try:
        success, response, _ = llm_client.generate(
            prompt=prompt,
            system="You are a financial analyst. Provide concise, actionable summaries. Return only valid JSON.",
            temperature=0.3,
            max_tokens=400
        )

        if not success:
            return {
                'success': False,
                'summary_points': [],
                'sentiment': 'NEUTRAL',
                'error': 'LLM call failed'
            }

        # Parse response
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()

        data = json.loads(response)

        return {
            'success': True,
            'summary_points': data.get('summary_points', [])[:5],
            'sentiment': data.get('sentiment', 'NEUTRAL').upper()
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse quick summary response: {e}")
        return {
            'success': False,
            'summary_points': [],
            'sentiment': 'NEUTRAL',
            'error': str(e)
        }


def get_quick_summaries_for_reports(reports: list, symbol: str, max_reports: int = 3) -> list:
    """
    Get quick summaries for multiple reports.

    Downloads PDFs on-demand if not already downloaded.

    Args:
        reports: List of AnalystReport model instances or dicts
        symbol: Stock symbol
        max_reports: Maximum number of reports to summarize (default: 3)

    Returns:
        List of dicts with report info and summary
    """
    from apps.data.utils.pdf_extractor import extract_pdf_text_truncated

    summaries = []

    for report in reports[:max_reports]:
        # Handle both model instances and dicts
        is_model = hasattr(report, 'author')
        if is_model:
            # Model instance
            author = report.author
            target_price = float(report.target_price) if report.target_price else None
            recommendation = report.recommendation_type
            report_date = report.report_date
            pdf_path = report.pdf_local_path
            pdf_text = report.pdf_content_text
            pdf_url = report.pdf_url
        else:
            # Dict
            author = report.get('author', 'Unknown')
            target_price = report.get('target_price')
            recommendation = report.get('recommendation_type', 'UNKNOWN')
            report_date = report.get('report_date')
            pdf_path = report.get('pdf_local_path')
            pdf_text = report.get('pdf_content_text')
            pdf_url = report.get('pdf_url')

        summary_data = {
            'author': author,
            'target_price': target_price,
            'recommendation': recommendation,
            'report_date': str(report_date) if report_date else None,
            'summary_points': [],
            'sentiment': 'NEUTRAL',
            'success': False
        }

        # Note: PDFs should be downloaded during verification flow with authenticated session
        # This is just a fallback check
        if not pdf_path and pdf_url:
            logger.debug(f"No local PDF for {author} - PDF should be downloaded during verification")

        # Step 2: Extract PDF text if not available
        if not pdf_text and pdf_path:
            try:
                success, text, _ = extract_pdf_text_truncated(pdf_path, max_chars=8000)
                if success:
                    pdf_text = text
                    if is_model:
                        # Cache extracted text in model
                        report.pdf_content_text = text
                        report.save(update_fields=['pdf_content_text'])
            except Exception as e:
                logger.warning(f"Could not extract PDF for {author}: {e}")

        # Step 3: Get quick summary if we have text
        if pdf_text:
            result = get_quick_report_summary(
                pdf_text=pdf_text,
                symbol=symbol,
                author=author,
                target_price=target_price,
                recommendation_type=recommendation
            )
            summary_data['summary_points'] = result.get('summary_points', [])
            summary_data['sentiment'] = result.get('sentiment', 'NEUTRAL')
            summary_data['success'] = result.get('success', False)
            if not result.get('success'):
                summary_data['error'] = result.get('error', 'LLM analysis failed')
        else:
            summary_data['error'] = 'No PDF content available'

        summaries.append(summary_data)

    return summaries


def _check_pdf_exists(pdf_path: str) -> bool:
    """
    Check if a valid PDF exists at the given path.

    Args:
        pdf_path: Path to check

    Returns:
        True if valid PDF exists, False otherwise
    """
    import os

    if not pdf_path or not os.path.exists(pdf_path):
        return False

    if os.path.getsize(pdf_path) < 5000:
        return False

    try:
        with open(pdf_path, 'rb') as f:
            return f.read(5) == b'%PDF-'
    except Exception:
        return False
