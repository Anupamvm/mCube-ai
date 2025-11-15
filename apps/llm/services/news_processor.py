"""
News Processor Service

This service processes news articles with LLM analysis:
- Fetches news from various sources
- Analyzes sentiment using LLM
- Extracts key insights and summaries
- Generates embeddings for semantic search
- Stores in database and vector store

Features:
- Multi-source news aggregation
- LLM-powered sentiment analysis
- Key insights extraction
- Semantic chunking for RAG
- Automatic embedding generation
"""

import logging
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.data.models import NewsArticle, KnowledgeBase
from apps.llm.services.ollama_client import get_ollama_client, generate_embedding
from apps.llm.services.vector_store import get_vector_store, COLLECTION_NEWS, COLLECTION_KNOWLEDGE

logger = logging.getLogger(__name__)


class NewsProcessor:
    """
    Processes news articles with LLM analysis and stores them for RAG
    """

    def __init__(self):
        """Initialize news processor"""
        self.llm_client = get_ollama_client()
        self.vector_store = get_vector_store()

    def process_article(
        self,
        title: str,
        content: str,
        source: str,
        url: Optional[str] = None,
        published_at: Optional[datetime] = None,
        symbols: Optional[List[str]] = None,
        author: Optional[str] = None
    ) -> Tuple[bool, Optional[NewsArticle], str]:
        """
        Process a single news article with LLM analysis

        Args:
            title: Article title
            content: Full article content
            source: News source
            url: Article URL
            published_at: Publication datetime
            symbols: Related stock symbols
            author: Article author

        Returns:
            Tuple[bool, Optional[NewsArticle], str]: (success, article, message)

        Example:
            >>> processor = NewsProcessor()
            >>> success, article, msg = processor.process_article(
            ...     title="RELIANCE reports strong Q4 earnings",
            ...     content="Full article text...",
            ...     source="Economic Times",
            ...     symbols=["RELIANCE"]
            ... )
        """
        if not self.llm_client.is_enabled():
            return False, None, "LLM not available for news processing"

        try:
            logger.info(f"Processing article: {title[:50]}...")

            # Step 1: Analyze sentiment
            sentiment_result = self._analyze_sentiment(title, content)

            # Step 2: Generate summary
            summary = self._generate_summary(content)

            # Step 3: Extract key insights
            insights = self._extract_insights(content, symbols or [])

            # Step 4: Determine sentiment score and label
            sentiment_score = sentiment_result.get('score', 0.0)
            sentiment_label = sentiment_result.get('label', 'NEUTRAL')

            # Step 5: Save to database
            with transaction.atomic():
                article = NewsArticle.objects.create(
                    title=title,
                    content=content,
                    source=source,
                    url=url or '',
                    published_at=published_at or timezone.now(),
                    author=author or '',
                    symbols=symbols or [],
                    sentiment_score=sentiment_score,
                    sentiment_label=sentiment_label,
                    llm_summary=summary,
                    key_insights=insights,
                    embedding_stored=False
                )

                logger.info(f"Article saved: {article.id}")

            # Step 6: Generate and store embeddings
            embedding_success = self._store_embeddings(article)

            if embedding_success:
                article.embedding_stored = True
                article.save(update_fields=['embedding_stored'])

            logger.info(f"Article processed successfully: {article.id}")
            return True, article, f"Article processed with {sentiment_label} sentiment"

        except Exception as e:
            error_msg = f"Error processing article: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, None, error_msg

    def _analyze_sentiment(self, title: str, content: str) -> Dict:
        """Analyze sentiment of article using LLM"""

        prompt = f"""Analyze the sentiment of this news article for stock trading.

Title: {title}

Content: {content[:1500]}

Provide sentiment analysis in this format:
SENTIMENT: [VERY_POSITIVE/POSITIVE/NEUTRAL/NEGATIVE/VERY_NEGATIVE]
SCORE: [Value from -1.0 to 1.0, where -1 is very bearish, 0 is neutral, 1 is very bullish]
REASONING: [Brief explanation]

Consider:
- Impact on stock prices
- Market implications
- Investor sentiment
- Business fundamentals mentioned
"""

        success, response, _ = self.llm_client.generate(
            prompt=prompt,
            temperature=0.2
        )

        if not success:
            logger.warning("Sentiment analysis failed, using neutral")
            return {'score': 0.0, 'label': 'NEUTRAL'}

        # Parse response
        sentiment_label = 'NEUTRAL'
        sentiment_score = 0.0

        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('SENTIMENT:'):
                sentiment_label = line.split(':', 1)[1].strip()
            elif line.startswith('SCORE:'):
                try:
                    score_str = line.split(':', 1)[1].strip()
                    sentiment_score = float(score_str)
                except ValueError:
                    pass

        return {
            'label': sentiment_label,
            'score': sentiment_score,
            'analysis': response
        }

    def _generate_summary(self, content: str) -> str:
        """Generate concise summary of article"""

        prompt = f"""Summarize this news article in 2-3 sentences, focusing on key facts and market impact:

{content[:2000]}

Provide a concise summary that captures:
- Main event or announcement
- Key financial/business implications
- Expected market impact

Summary:"""

        success, summary, _ = self.llm_client.generate(
            prompt=prompt,
            temperature=0.3
        )

        if not success:
            logger.warning("Summary generation failed")
            return content[:200]

        return summary.strip()

    def _extract_insights(self, content: str, symbols: List[str]) -> List[str]:
        """Extract key trading insights from article"""

        symbols_str = ", ".join(symbols) if symbols else "the mentioned stocks"

        prompt = f"""Extract 3-5 key trading insights from this news article about {symbols_str}:

{content[:2000]}

Provide insights as a bulleted list. Each insight should be:
- Specific and actionable
- Relevant for trading decisions
- Based on facts from the article

Key Insights:
-"""

        success, response, _ = self.llm_client.generate(
            prompt=prompt,
            temperature=0.3
        )

        if not success:
            return []

        # Parse insights
        insights = []
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                insight = line.lstrip('- ').strip()
                if insight:
                    insights.append(insight)

        return insights[:5]  # Limit to 5 insights

    def _store_embeddings(self, article: NewsArticle) -> bool:
        """Generate and store embeddings for article"""

        if not self.vector_store.is_enabled():
            logger.warning("Vector store not available, skipping embeddings")
            return False

        try:
            # Create chunks for embedding
            chunks = self._chunk_article(article)

            if not chunks:
                return False

            documents = []
            embeddings = []
            metadatas = []
            ids = []

            for i, chunk in enumerate(chunks):
                # Generate embedding
                success, embedding = generate_embedding(chunk['text'])

                if not success:
                    logger.warning(f"Failed to generate embedding for chunk {i}")
                    continue

                chunk_id = f"news_{article.id}_chunk_{i}"

                documents.append(chunk['text'])
                embeddings.append(embedding)
                metadatas.append({
                    'source_type': 'news',
                    'article_id': article.id,
                    'title': article.title,
                    'source': article.source,
                    'published_at': article.published_at.isoformat(),
                    'symbols': json.dumps(article.symbols),
                    'sentiment': article.sentiment_label,
                    'sentiment_score': article.sentiment_score,
                    'chunk_type': chunk['type'],
                    'url': article.url
                })
                ids.append(chunk_id)

            # Store in vector database
            if documents:
                self.vector_store.add_documents(
                    collection_name=COLLECTION_NEWS,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    ids=ids
                )

                # Also create KnowledgeBase entries
                for i, chunk in enumerate(chunks):
                    chunk_id = f"news_{article.id}_chunk_{i}"
                    KnowledgeBase.objects.create(
                        source_type='news',
                        source_id=article.id,
                        title=article.title,
                        content_chunk=chunk['text'],
                        embedding_id=chunk_id,
                        metadata={
                            'source': article.source,
                            'symbols': article.symbols,
                            'sentiment': article.sentiment_label,
                            'chunk_type': chunk['type']
                        }
                    )

                article.embedding_id = f"news_{article.id}"
                article.save(update_fields=['embedding_id'])

                logger.info(f"Stored {len(documents)} embeddings for article {article.id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error storing embeddings: {str(e)}", exc_info=True)
            return False

    def _chunk_article(self, article: NewsArticle) -> List[Dict]:
        """
        Chunk article into smaller pieces for embedding

        Returns chunks with different types:
        - title_summary: Title + summary
        - insights: Key insights
        - full: Full content (if short)
        """
        chunks = []

        # Chunk 1: Title + Summary
        title_summary = f"{article.title}\n\n{article.llm_summary}"
        chunks.append({
            'type': 'title_summary',
            'text': title_summary
        })

        # Chunk 2: Key Insights
        if article.key_insights:
            insights_text = f"{article.title}\n\nKey Insights:\n"
            insights_text += "\n".join([f"- {insight}" for insight in article.key_insights])
            chunks.append({
                'type': 'insights',
                'text': insights_text
            })

        # Chunk 3: Full content (if reasonably sized)
        if len(article.content) < 2000:
            chunks.append({
                'type': 'full',
                'text': f"{article.title}\n\n{article.content}"
            })
        else:
            # Split long articles into paragraphs
            paragraphs = article.content.split('\n\n')
            for i, para in enumerate(paragraphs[:3]):  # Limit to first 3 paragraphs
                if para.strip():
                    chunks.append({
                        'type': f'paragraph_{i+1}',
                        'text': f"{article.title}\n\n{para}"
                    })

        return chunks

    def batch_process_articles(
        self,
        articles: List[Dict]
    ) -> Tuple[int, int, List[str]]:
        """
        Process multiple articles in batch

        Args:
            articles: List of article dicts with title, content, source, etc.

        Returns:
            Tuple[int, int, List[str]]: (success_count, error_count, error_messages)
        """
        success_count = 0
        error_count = 0
        errors = []

        logger.info(f"Processing {len(articles)} articles in batch")

        for i, article_data in enumerate(articles, 1):
            try:
                success, article, message = self.process_article(**article_data)

                if success:
                    success_count += 1
                    logger.info(f"[{i}/{len(articles)}] Processed: {article_data['title'][:50]}")
                else:
                    error_count += 1
                    errors.append(f"{article_data['title'][:50]}: {message}")
                    logger.error(f"[{i}/{len(articles)}] Failed: {message}")

            except Exception as e:
                error_count += 1
                error_msg = f"{article_data.get('title', 'Unknown')[:50]}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"[{i}/{len(articles)}] Exception: {error_msg}")

        logger.info(f"Batch processing complete: {success_count} success, {error_count} errors")
        return success_count, error_count, errors

    def reprocess_embeddings(self, article_id: int) -> bool:
        """
        Reprocess embeddings for an existing article

        Args:
            article_id: NewsArticle ID

        Returns:
            bool: Success status
        """
        try:
            article = NewsArticle.objects.get(id=article_id)

            # Delete existing embeddings
            if article.embedding_id:
                KnowledgeBase.objects.filter(
                    source_type='news',
                    source_id=article_id
                ).delete()

            # Regenerate
            success = self._store_embeddings(article)

            if success:
                article.embedding_stored = True
                article.save(update_fields=['embedding_stored'])

            return success

        except NewsArticle.DoesNotExist:
            logger.error(f"Article {article_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error reprocessing embeddings: {str(e)}", exc_info=True)
            return False


# Global instance
_news_processor = None


def get_news_processor() -> NewsProcessor:
    """Get or create global NewsProcessor instance"""
    global _news_processor

    if _news_processor is None:
        _news_processor = NewsProcessor()

    return _news_processor


# Convenience functions

def process_news_article(
    title: str,
    content: str,
    source: str,
    **kwargs
) -> Tuple[bool, Optional[NewsArticle]]:
    """
    Process a news article (convenience function)

    Args:
        title: Article title
        content: Article content
        source: News source
        **kwargs: Additional parameters

    Returns:
        Tuple[bool, Optional[NewsArticle]]: (success, article)

    Example:
        >>> success, article = process_news_article(
        ...     title="Market Update",
        ...     content="Markets rallied today...",
        ...     source="Bloomberg",
        ...     symbols=["NIFTY"]
        ... )
    """
    processor = get_news_processor()
    success, article, message = processor.process_article(title, content, source, **kwargs)
    return success, article
