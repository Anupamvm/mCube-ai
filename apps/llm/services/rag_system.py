"""
RAG (Retrieval Augmented Generation) System

This service combines vector search with LLM generation to provide
intelligent, context-aware responses based on stored knowledge.

Features:
- Semantic search across knowledge base
- Context retrieval with relevance ranking
- LLM-powered answer generation with citations
- Multi-document synthesis
- Trade-specific query handling
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from apps.llm.services.ollama_client import get_ollama_client, generate_embedding
from apps.llm.services.vector_store import get_vector_store, COLLECTION_KNOWLEDGE, COLLECTION_NEWS
from apps.data.models import NewsArticle, InvestorCall, KnowledgeBase

logger = logging.getLogger(__name__)


class RAGSystem:
    """
    RAG system for intelligent knowledge retrieval and generation
    """

    def __init__(self):
        """Initialize RAG system"""
        self.llm_client = get_ollama_client()
        self.vector_store = get_vector_store()

    def query(
        self,
        question: str,
        collection_name: str = COLLECTION_KNOWLEDGE,
        n_results: int = 5,
        metadata_filter: Optional[Dict] = None,
        temperature: float = 0.3
    ) -> Tuple[bool, str, List[Dict]]:
        """
        Query knowledge base and generate answer

        Args:
            question: User question
            collection_name: Collection to search
            n_results: Number of context documents to retrieve
            metadata_filter: Metadata filter for search
            temperature: LLM temperature

        Returns:
            Tuple[bool, str, List[Dict]]: (success, answer, sources)
        """
        if not self.llm_client.is_enabled():
            return False, "LLM not available", []

        if not self.vector_store.is_enabled():
            return False, "Vector store not available", []

        try:
            # Generate embedding for question
            success, query_embedding = generate_embedding(question)

            if not success:
                return False, "Failed to generate query embedding", []

            # Retrieve relevant contexts
            results = self.vector_store.query(
                collection_name,
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=metadata_filter
            )

            if not results or not results.get('documents'):
                return False, "No relevant information found", []

            # Extract documents and metadata
            documents = results['documents'][0]
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]

            # Build context from retrieved documents
            context = self._build_context(documents, metadatas, distances)

            # Generate answer using LLM
            answer = self._generate_answer(question, context, temperature)

            # Prepare sources
            sources = self._prepare_sources(documents, metadatas, distances)

            logger.info(f"RAG query completed: {len(documents)} contexts, answer length: {len(answer)}")
            return True, answer, sources

        except Exception as e:
            error_msg = f"RAG query error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg, []

    def _build_context(
        self,
        documents: List[str],
        metadatas: List[Dict],
        distances: List[float]
    ) -> str:
        """Build context string from retrieved documents"""
        context_parts = []

        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances), 1):
            # Add source info
            source = meta.get('source_type', 'Unknown')
            title = meta.get('title', 'Untitled')

            context_parts.append(f"[Source {i}: {source} - {title}]")
            context_parts.append(doc)
            context_parts.append("")  # Empty line

        return "\n".join(context_parts)

    def _generate_answer(
        self,
        question: str,
        context: str,
        temperature: float
    ) -> str:
        """Generate answer using LLM with context"""
        system_prompt = """You are an expert stock market analyst and trading advisor.
Answer questions based solely on the provided context.
If the context doesn't contain enough information, clearly state that.
Provide specific, actionable insights when possible.
Cite sources when making claims."""

        prompt = f"""Context:
{context}

Question: {question}

Based on the above context, provide a comprehensive answer to the question.
Be specific and cite relevant information from the context."""

        success, answer, _ = self.llm_client.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=temperature
        )

        if not success:
            return "Failed to generate answer"

        return answer

    def _prepare_sources(
        self,
        documents: List[str],
        metadatas: List[Dict],
        distances: List[float]
    ) -> List[Dict]:
        """Prepare source citations"""
        sources = []

        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances), 1):
            sources.append({
                'rank': i,
                'relevance_score': 1.0 - min(dist, 1.0),  # Convert distance to similarity
                'source_type': meta.get('source_type', 'Unknown'),
                'title': meta.get('title', 'Untitled'),
                'snippet': doc[:200] + '...' if len(doc) > 200 else doc,
                'metadata': meta
            })

        return sources

    def query_about_symbol(
        self,
        symbol: str,
        question: Optional[str] = None,
        days_back: int = 30,
        n_results: int = 10
    ) -> Tuple[bool, str, List[Dict]]:
        """
        Query information about a specific stock symbol

        Args:
            symbol: Stock symbol
            question: Specific question (optional)
            days_back: Days to look back
            n_results: Number of results

        Returns:
            Tuple[bool, str, List[Dict]]: (success, answer, sources)
        """
        # Default question if none provided
        if not question:
            question = f"What is the recent news and sentiment about {symbol}? What are the key events and outlook?"

        # Filter by symbol and recent timeframe
        metadata_filter = {
            "symbols": {"$contains": symbol}
        }

        return self.query(
            question=question,
            collection_name=COLLECTION_KNOWLEDGE,
            n_results=n_results,
            metadata_filter=None,  # ChromaDB has limited filter support, need to post-filter
            temperature=0.3
        )

    def get_market_sentiment(
        self,
        sector: Optional[str] = None,
        days_back: int = 7
    ) -> Tuple[bool, str]:
        """
        Get overall market/sector sentiment

        Args:
            sector: Specific sector (optional)
            days_back: Days to analyze

        Returns:
            Tuple[bool, str]: (success, sentiment_analysis)
        """
        question = f"What is the overall market sentiment in the last {days_back} days?"
        if sector:
            question = f"What is the sentiment for the {sector} sector in the last {days_back} days?"

        success, answer, _ = self.query(
            question=question,
            collection_name=COLLECTION_NEWS,
            n_results=20,
            temperature=0.2
        )

        return success, answer

    def compare_stocks(
        self,
        symbols: List[str],
        aspect: str = "fundamentals"
    ) -> Tuple[bool, str]:
        """
        Compare multiple stocks

        Args:
            symbols: List of stock symbols
            aspect: What to compare (fundamentals, technicals, sentiment)

        Returns:
            Tuple[bool, str]: (success, comparison)
        """
        symbols_str = ", ".join(symbols)
        question = f"Compare {symbols_str} based on their {aspect}. Which looks more favorable for trading?"

        success, answer, _ = self.query(
            question=question,
            n_results=15,
            temperature=0.3
        )

        return success, answer

    def get_trade_ideas(
        self,
        strategy_type: str = "options",
        risk_level: str = "medium"
    ) -> Tuple[bool, str]:
        """
        Get trade ideas based on recent analysis

        Args:
            strategy_type: options, futures, cash
            risk_level: low, medium, high

        Returns:
            Tuple[bool, str]: (success, trade_ideas)
        """
        question = f"""Based on recent market analysis and news, suggest {strategy_type} trading opportunities
for {risk_level} risk tolerance. Include entry levels, targets, and rationale."""

        success, answer, _ = self.query(
            question=question,
            n_results=20,
            temperature=0.5
        )

        return success, answer


# Global instance
_rag_system = None


def get_rag_system() -> RAGSystem:
    """Get or create global RAG system instance"""
    global _rag_system

    if _rag_system is None:
        _rag_system = RAGSystem()

    return _rag_system


# Convenience functions

def ask_question(question: str, n_results: int = 5) -> Tuple[bool, str, List[Dict]]:
    """
    Ask a question to the RAG system (convenience function)

    Args:
        question: Question to ask
        n_results: Number of context documents

    Returns:
        Tuple[bool, str, List[Dict]]: (success, answer, sources)
    """
    rag = get_rag_system()
    return rag.query(question, n_results=n_results)


def get_symbol_analysis(symbol: str) -> Tuple[bool, str]:
    """
    Get analysis for a symbol (convenience function)

    Args:
        symbol: Stock symbol

    Returns:
        Tuple[bool, str]: (success, analysis)
    """
    rag = get_rag_system()
    success, answer, _ = rag.query_about_symbol(symbol)
    return success, answer
