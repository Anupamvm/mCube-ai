"""
LLM-based Trade Validator

This service uses LLM and RAG to validate proposed trades based on:
- Recent news and market sentiment
- Investor call insights
- Technical and fundamental analysis
- Risk assessment

Features:
- Multi-factor validation using RAG context
- Confidence scoring
- Detailed reasoning and rationale
- Risk identification
- Alternative suggestions
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

from apps.llm.services.ollama_client import get_ollama_client
from apps.llm.services.rag_system import get_rag_system
from apps.data.models import NewsArticle, InvestorCall

logger = logging.getLogger(__name__)


class TradeValidator:
    """
    LLM-powered trade validation system

    Validates trades by analyzing:
    - Recent news and sentiment
    - Investor call insights
    - Market conditions
    - Risk factors
    """

    def __init__(self):
        """Initialize trade validator"""
        self.llm_client = get_ollama_client()
        self.rag_system = get_rag_system()

    def validate_trade(
        self,
        symbol: str,
        direction: str,
        strategy_type: str = "OPTIONS",
        price_level: Optional[float] = None,
        quantity: Optional[int] = None,
        additional_context: Optional[str] = None
    ) -> Dict:
        """
        Validate a proposed trade using LLM and RAG

        Args:
            symbol: Stock symbol
            direction: LONG, SHORT, or NEUTRAL
            strategy_type: OPTIONS, FUTURES, CASH
            price_level: Entry price level (optional)
            quantity: Trade quantity (optional)
            additional_context: Any additional context (optional)

        Returns:
            Dict with validation results:
            {
                'approved': bool,
                'confidence': float (0-1),
                'reasoning': str,
                'risks': List[str],
                'opportunities': List[str],
                'alternative_suggestions': List[str],
                'market_sentiment': str,
                'llm_analysis': str,
                'sources_used': int
            }

        Example:
            >>> validator = TradeValidator()
            >>> result = validator.validate_trade("RELIANCE", "LONG", "OPTIONS")
            >>> print(f"Approved: {result['approved']}, Confidence: {result['confidence']}")
        """
        if not self.llm_client.is_enabled():
            return self._error_result("LLM not available")

        if not self.rag_system.vector_store.is_enabled():
            logger.warning("Vector store not available, using LLM-only validation")
            return self._validate_without_rag(symbol, direction, strategy_type, price_level, quantity)

        try:
            logger.info(f"Validating trade: {symbol} {direction} {strategy_type}")

            # Step 1: Gather context from RAG
            context = self._gather_context(symbol, direction, strategy_type)

            # Step 2: Build validation prompt
            prompt = self._build_validation_prompt(
                symbol, direction, strategy_type, price_level, quantity,
                additional_context, context
            )

            # Step 3: Get LLM validation
            success, llm_response, _ = self.llm_client.generate(
                prompt=prompt,
                system="You are an expert stock market analyst and risk manager. Provide thorough, balanced trade analysis.",
                temperature=0.3
            )

            if not success:
                return self._error_result(f"LLM generation failed: {llm_response}")

            # Step 4: Parse LLM response
            validation_result = self._parse_validation_response(
                llm_response, context['sources_count']
            )

            logger.info(f"Trade validation complete: {validation_result['approved']} "
                       f"(confidence: {validation_result['confidence']:.2f})")

            return validation_result

        except Exception as e:
            error_msg = f"Trade validation error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return self._error_result(error_msg)

    def _gather_context(
        self,
        symbol: str,
        direction: str,
        strategy_type: str
    ) -> Dict:
        """Gather context from RAG system"""
        context = {
            'news_sentiment': None,
            'recent_events': None,
            'investor_insights': None,
            'sources_count': 0
        }

        # Query recent news and sentiment
        question = f"""What is the recent sentiment and key news about {symbol}?
Focus on events from the last 30 days that would impact a {direction} {strategy_type} trade."""

        success, answer, sources = self.rag_system.query_about_symbol(
            symbol=symbol,
            question=question,
            days_back=30,
            n_results=10
        )

        if success:
            context['news_sentiment'] = answer
            context['sources_count'] = len(sources)

        # Query for investor call insights
        call_question = f"""What did management say in recent investor calls about {symbol}?
What is the outlook and guidance?"""

        success, call_answer, call_sources = self.rag_system.query(
            question=call_question,
            n_results=5
        )

        if success:
            context['investor_insights'] = call_answer
            context['sources_count'] += len(call_sources)

        # Get overall market sentiment
        success, market_sentiment = self.rag_system.get_market_sentiment(days_back=7)
        if success:
            context['market_sentiment'] = market_sentiment

        return context

    def _build_validation_prompt(
        self,
        symbol: str,
        direction: str,
        strategy_type: str,
        price_level: Optional[float],
        quantity: Optional[int],
        additional_context: Optional[str],
        rag_context: Dict
    ) -> str:
        """Build comprehensive validation prompt"""

        prompt_parts = [
            f"# Trade Validation Request",
            f"",
            f"**Symbol**: {symbol}",
            f"**Direction**: {direction}",
            f"**Strategy**: {strategy_type}",
        ]

        if price_level:
            prompt_parts.append(f"**Entry Price**: {price_level}")

        if quantity:
            prompt_parts.append(f"**Quantity**: {quantity}")

        if additional_context:
            prompt_parts.extend([
                f"",
                f"**Additional Context**: {additional_context}"
            ])

        # Add RAG context
        prompt_parts.extend([
            f"",
            f"# Market Intelligence",
            f""
        ])

        if rag_context.get('news_sentiment'):
            prompt_parts.extend([
                f"## Recent News and Sentiment",
                rag_context['news_sentiment'],
                f""
            ])

        if rag_context.get('investor_insights'):
            prompt_parts.extend([
                f"## Investor Call Insights",
                rag_context['investor_insights'],
                f""
            ])

        if rag_context.get('market_sentiment'):
            prompt_parts.extend([
                f"## Overall Market Sentiment",
                rag_context['market_sentiment'],
                f""
            ])

        # Add validation instructions
        prompt_parts.extend([
            f"",
            f"# Your Task",
            f"",
            f"Based on the above information, validate this {direction} {strategy_type} trade on {symbol}.",
            f"",
            f"Provide your analysis in the following format:",
            f"",
            f"DECISION: [APPROVED/REJECTED/CONDITIONAL]",
            f"CONFIDENCE: [0-100]",
            f"",
            f"REASONING:",
            f"[2-3 sentences explaining your decision]",
            f"",
            f"RISKS:",
            f"- [Risk 1]",
            f"- [Risk 2]",
            f"- [Risk 3]",
            f"",
            f"OPPORTUNITIES:",
            f"- [Opportunity 1]",
            f"- [Opportunity 2]",
            f"",
            f"ALTERNATIVES:",
            f"- [Alternative suggestion 1]",
            f"- [Alternative suggestion 2]",
            f"",
            f"SENTIMENT: [BULLISH/BEARISH/NEUTRAL]",
            f"",
            f"Be specific and cite information from the market intelligence provided."
        ])

        return "\n".join(prompt_parts)

    def _parse_validation_response(
        self,
        llm_response: str,
        sources_count: int
    ) -> Dict:
        """Parse LLM validation response into structured format"""

        # Default result
        result = {
            'approved': False,
            'confidence': 0.0,
            'reasoning': '',
            'risks': [],
            'opportunities': [],
            'alternative_suggestions': [],
            'market_sentiment': 'UNKNOWN',
            'llm_analysis': llm_response,
            'sources_used': sources_count
        }

        lines = llm_response.split('\n')
        current_section = None

        for line in lines:
            line = line.strip()

            if not line:
                continue

            # Parse decision
            if line.startswith('DECISION:'):
                decision = line.split(':', 1)[1].strip().upper()
                result['approved'] = decision in ['APPROVED', 'CONDITIONAL']

            # Parse confidence
            elif line.startswith('CONFIDENCE:'):
                try:
                    confidence_str = line.split(':', 1)[1].strip()
                    confidence = float(confidence_str.rstrip('%'))
                    result['confidence'] = confidence / 100.0
                except ValueError:
                    result['confidence'] = 0.5  # Default to 50%

            # Parse sentiment
            elif line.startswith('SENTIMENT:'):
                result['market_sentiment'] = line.split(':', 1)[1].strip()

            # Section headers
            elif line.startswith('REASONING:'):
                current_section = 'reasoning'
            elif line.startswith('RISKS:'):
                current_section = 'risks'
            elif line.startswith('OPPORTUNITIES:'):
                current_section = 'opportunities'
            elif line.startswith('ALTERNATIVES:'):
                current_section = 'alternatives'

            # Section content
            elif line.startswith('-'):
                item = line.lstrip('- ').strip()
                if current_section == 'risks':
                    result['risks'].append(item)
                elif current_section == 'opportunities':
                    result['opportunities'].append(item)
                elif current_section == 'alternatives':
                    result['alternative_suggestions'].append(item)

            # Reasoning text
            elif current_section == 'reasoning':
                if result['reasoning']:
                    result['reasoning'] += ' ' + line
                else:
                    result['reasoning'] = line

        return result

    def _validate_without_rag(
        self,
        symbol: str,
        direction: str,
        strategy_type: str,
        price_level: Optional[float],
        quantity: Optional[int]
    ) -> Dict:
        """Fallback validation without RAG (LLM only)"""

        prompt = f"""Validate this trade based on general market principles and risk management:

Symbol: {symbol}
Direction: {direction}
Strategy: {strategy_type}
{"Entry Price: " + str(price_level) if price_level else ""}
{"Quantity: " + str(quantity) if quantity else ""}

Provide validation in this format:
DECISION: [APPROVED/REJECTED/CONDITIONAL]
CONFIDENCE: [0-100]
REASONING: [Your reasoning]
RISKS: [List of risks]

Note: This validation is based on general principles only, as no recent market data is available."""

        success, response, _ = self.llm_client.generate(
            prompt=prompt,
            temperature=0.3
        )

        if not success:
            return self._error_result("LLM validation failed")

        result = self._parse_validation_response(response, 0)
        result['warning'] = "Validated without recent market data (RAG unavailable)"

        return result

    def _error_result(self, error_message: str) -> Dict:
        """Return error result"""
        return {
            'approved': False,
            'confidence': 0.0,
            'reasoning': error_message,
            'risks': ['Validation system unavailable'],
            'opportunities': [],
            'alternative_suggestions': [],
            'market_sentiment': 'UNKNOWN',
            'llm_analysis': '',
            'sources_used': 0,
            'error': error_message
        }

    def validate_exit(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        current_price: float,
        pnl_percent: float,
        days_held: int
    ) -> Dict:
        """
        Validate whether to exit a position

        Args:
            symbol: Stock symbol
            direction: LONG/SHORT
            entry_price: Entry price
            current_price: Current market price
            pnl_percent: Current P&L percentage
            days_held: Days position has been held

        Returns:
            Dict with exit validation
        """

        additional_context = f"""
Current position details:
- Entry Price: {entry_price}
- Current Price: {current_price}
- P&L: {pnl_percent:.2f}%
- Days Held: {days_held}
"""

        question = f"""Should I exit my {direction} position in {symbol}?
{additional_context}

Consider:
- Recent news and sentiment changes
- Risk/reward from current level
- Whether to book profit/loss or hold
- Any upcoming events that might impact the position"""

        success, answer, sources = self.rag_system.query(
            question=question,
            n_results=8
        )

        if not success:
            return self._error_result("Exit validation failed")

        # Parse exit recommendation
        prompt = f"""Based on this analysis:

{answer}

Position Details:
{additional_context}

Should I exit this position now?

Provide recommendation in this format:
RECOMMENDATION: [EXIT/HOLD/PARTIAL_EXIT]
CONFIDENCE: [0-100]
REASONING: [Your reasoning]
SUGGESTED_ACTION: [Specific action to take]
"""

        llm_success, llm_response, _ = self.llm_client.generate(
            prompt=prompt,
            temperature=0.3
        )

        if not llm_success:
            return self._error_result("LLM exit analysis failed")

        return {
            'exit_recommended': 'EXIT' in llm_response,
            'analysis': answer,
            'llm_recommendation': llm_response,
            'sources_used': len(sources)
        }


# Global instance
_trade_validator = None


def get_trade_validator() -> TradeValidator:
    """Get or create global TradeValidator instance"""
    global _trade_validator

    if _trade_validator is None:
        _trade_validator = TradeValidator()

    return _trade_validator


# Convenience functions

def validate_trade(
    symbol: str,
    direction: str,
    strategy_type: str = "OPTIONS",
    **kwargs
) -> Dict:
    """
    Validate a trade (convenience function)

    Args:
        symbol: Stock symbol
        direction: LONG/SHORT/NEUTRAL
        strategy_type: OPTIONS/FUTURES/CASH
        **kwargs: Additional parameters

    Returns:
        Dict with validation results

    Example:
        >>> result = validate_trade("TCS", "LONG", "OPTIONS")
        >>> if result['approved']:
        ...     print(f"Trade approved with {result['confidence']:.0%} confidence")
    """
    validator = get_trade_validator()
    return validator.validate_trade(symbol, direction, strategy_type, **kwargs)


def should_exit_position(
    symbol: str,
    direction: str,
    entry_price: float,
    current_price: float,
    pnl_percent: float,
    days_held: int
) -> Tuple[bool, str]:
    """
    Check if position should be exited (convenience function)

    Args:
        symbol: Stock symbol
        direction: LONG/SHORT
        entry_price: Entry price
        current_price: Current price
        pnl_percent: P&L percentage
        days_held: Days held

    Returns:
        Tuple[bool, str]: (should_exit, reasoning)
    """
    validator = get_trade_validator()
    result = validator.validate_exit(
        symbol, direction, entry_price, current_price, pnl_percent, days_held
    )

    return result.get('exit_recommended', False), result.get('analysis', '')
