"""
Test LLM System

This command tests all components of the LLM system:
- Ollama connection and model availability
- Text generation
- Embedding generation
- Vector store functionality
- News processing
- RAG queries
- Trade validation

Usage:
    python manage.py test_llm
    python manage.py test_llm --quick  # Skip detailed tests
    python manage.py test_llm --component ollama  # Test specific component
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.llm.services.ollama_client import get_ollama_client, generate_embedding
from apps.llm.services.vector_store import get_vector_store
from apps.llm.services.rag_system import get_rag_system, ask_question
from apps.llm.services.trade_validator import get_trade_validator, validate_trade
from apps.llm.services.news_processor import get_news_processor
from apps.data.models import NewsArticle, KnowledgeBase


class Command(BaseCommand):
    help = 'Test LLM system components'

    def add_arguments(self, parser):
        parser.add_argument(
            '--quick',
            action='store_true',
            help='Run quick tests only'
        )

        parser.add_argument(
            '--component',
            type=str,
            choices=['ollama', 'vector', 'news', 'rag', 'validator', 'all'],
            default='all',
            help='Test specific component'
        )

    def handle(self, *args, **options):
        self.quick = options['quick']
        self.component = options['component']

        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('LLM SYSTEM TEST'))
        self.stdout.write('=' * 80)
        self.stdout.write('')

        all_passed = True

        # Test Ollama
        if self.component in ['all', 'ollama']:
            if not self.test_ollama():
                all_passed = False

        # Test Vector Store
        if self.component in ['all', 'vector']:
            if not self.test_vector_store():
                all_passed = False

        # Test News Processor
        if self.component in ['all', 'news']:
            if not self.test_news_processor():
                all_passed = False

        # Test RAG System
        if self.component in ['all', 'rag']:
            if not self.test_rag_system():
                all_passed = False

        # Test Trade Validator
        if self.component in ['all', 'validator']:
            if not self.test_trade_validator():
                all_passed = False

        # Final summary
        self.stdout.write('')
        self.stdout.write('=' * 80)
        if all_passed:
            self.stdout.write(self.style.SUCCESS('ALL TESTS PASSED'))
        else:
            self.stdout.write(self.style.ERROR('SOME TESTS FAILED'))
        self.stdout.write('=' * 80)

    def test_ollama(self):
        """Test Ollama LLM client"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 1: OLLAMA LLM CLIENT'))
        self.stdout.write('-' * 80)

        client = get_ollama_client()

        # Check connection
        self.stdout.write('Checking Ollama connection...')
        if not client.is_enabled():
            self.stdout.write(self.style.ERROR('  FAILED: Ollama not available'))
            self.stdout.write(f'  Host: {client.host}')
            self.stdout.write(f'  Model: {client.default_model}')
            self.stdout.write('')
            self.stdout.write('  Troubleshooting:')
            self.stdout.write('  1. Is Ollama running? Try: ollama serve')
            self.stdout.write('  2. Is the model loaded? Try: ollama list')
            self.stdout.write('  3. Check OLLAMA_HOST and OLLAMA_MODEL in .env')
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Ollama connected'))
        self.stdout.write(f'  Host: {client.host}')
        self.stdout.write(f'  Model: {client.default_model}')

        # Test text generation
        if not self.quick:
            self.stdout.write('')
            self.stdout.write('Testing text generation...')
            success, response, metadata = client.generate(
                prompt="What is 2+2? Answer in one sentence.",
                temperature=0.1
            )

            if not success:
                self.stdout.write(self.style.ERROR(f'  FAILED: {response}'))
                return False

            self.stdout.write(self.style.SUCCESS('  PASSED: Text generation working'))
            self.stdout.write(f'  Response: {response[:100]}...')
            self.stdout.write(f'  Tokens: {metadata.get("eval_count", "unknown")}')

        # Test embedding generation
        self.stdout.write('')
        self.stdout.write('Testing embedding generation...')
        success, embedding = generate_embedding("Test text for embedding")

        if not success:
            self.stdout.write(self.style.ERROR(f'  FAILED: {embedding}'))
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Embedding generation working'))
        self.stdout.write(f'  Embedding dimension: {len(embedding)}')

        return True

    def test_vector_store(self):
        """Test ChromaDB vector store"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 2: VECTOR STORE'))
        self.stdout.write('-' * 80)

        vector_store = get_vector_store()

        # Check connection
        self.stdout.write('Checking vector store...')
        if not vector_store.is_enabled():
            self.stdout.write(self.style.ERROR('  FAILED: Vector store not available'))
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Vector store available'))
        self.stdout.write(f'  Path: {vector_store.persist_directory}')

        # List collections
        collections = vector_store.list_collections()
        self.stdout.write(f'  Collections: {len(collections)}')
        for col in collections:
            self.stdout.write(f'    - {col}')

        if not self.quick:
            # Test add and query
            self.stdout.write('')
            self.stdout.write('Testing document storage and retrieval...')

            test_docs = [
                "RELIANCE stock is showing bullish momentum",
                "TCS reports strong quarterly earnings",
                "NIFTY breaks resistance at 18000"
            ]

            # Generate embeddings
            embeddings = []
            for doc in test_docs:
                success, emb = generate_embedding(doc)
                if success:
                    embeddings.append(emb)

            if len(embeddings) != len(test_docs):
                self.stdout.write(self.style.ERROR('  FAILED: Could not generate embeddings'))
                return False

            # Add to test collection
            try:
                vector_store.add_documents(
                    collection_name='test_collection',
                    documents=test_docs,
                    embeddings=embeddings,
                    metadatas=[{'type': 'test'} for _ in test_docs],
                    ids=[f'test_{i}' for i in range(len(test_docs))]
                )

                # Query
                success, query_emb = generate_embedding("Stock market news")
                if success:
                    results = vector_store.query(
                        collection_name='test_collection',
                        query_embeddings=[query_emb],
                        n_results=2
                    )

                    if results and results.get('documents'):
                        self.stdout.write(self.style.SUCCESS('  PASSED: Storage and retrieval working'))
                        self.stdout.write(f'  Retrieved {len(results["documents"][0])} documents')
                    else:
                        self.stdout.write(self.style.ERROR('  FAILED: No results from query'))
                        return False

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  FAILED: {str(e)}'))
                return False

        return True

    def test_news_processor(self):
        """Test news processor"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 3: NEWS PROCESSOR'))
        self.stdout.write('-' * 80)

        processor = get_news_processor()

        self.stdout.write('Processing sample news article...')

        sample_article = {
            'title': 'RELIANCE Industries Reports Strong Q4 Results',
            'content': '''RELIANCE Industries Ltd reported strong Q4 FY24 results with net profit
rising 12% year-on-year to Rs 19,299 crore. Revenue from operations increased 8% to Rs 2.35 lakh crore.
The company announced plans to expand its retail footprint and invest in green energy initiatives.
The board recommended a dividend of Rs 9 per share. Management expressed confidence in maintaining
growth momentum in the upcoming fiscal year.''',
            'source': 'Test Source',
            'symbols': ['RELIANCE'],
            'published_at': timezone.now()
        }

        success, article, message = processor.process_article(**sample_article)

        if not success:
            self.stdout.write(self.style.ERROR(f'  FAILED: {message}'))
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Article processed successfully'))
        self.stdout.write(f'  Article ID: {article.id}')
        self.stdout.write(f'  Sentiment: {article.sentiment_label} ({article.sentiment_score:.2f})')
        self.stdout.write(f'  Summary: {article.llm_summary[:100]}...')
        self.stdout.write(f'  Insights: {len(article.key_insights)}')

        if article.key_insights:
            for i, insight in enumerate(article.key_insights[:2], 1):
                self.stdout.write(f'    {i}. {insight[:80]}...')

        self.stdout.write(f'  Embeddings stored: {article.embedding_stored}')

        # Check if stored in KnowledgeBase
        kb_count = KnowledgeBase.objects.filter(
            source_type='news',
            source_id=article.id
        ).count()
        self.stdout.write(f'  Knowledge chunks: {kb_count}')

        return True

    def test_rag_system(self):
        """Test RAG query system"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 4: RAG QUERY SYSTEM'))
        self.stdout.write('-' * 80)

        # Check if we have any data
        news_count = NewsArticle.objects.count()
        kb_count = KnowledgeBase.objects.count()

        self.stdout.write(f'Data available:')
        self.stdout.write(f'  News articles: {news_count}')
        self.stdout.write(f'  Knowledge chunks: {kb_count}')

        if news_count == 0 and kb_count == 0:
            self.stdout.write(self.style.WARNING('  WARNING: No data available for RAG query'))
            self.stdout.write('  Skipping RAG test. Process some news first.')
            return True

        self.stdout.write('')
        self.stdout.write('Testing RAG query...')

        success, answer, sources = ask_question(
            "What is the recent news about RELIANCE?",
            n_results=3
        )

        if not success:
            self.stdout.write(self.style.ERROR(f'  FAILED: {answer}'))
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: RAG query working'))
        self.stdout.write(f'  Answer length: {len(answer)} chars')
        self.stdout.write(f'  Sources used: {len(sources)}')
        self.stdout.write('')
        self.stdout.write(f'  Answer preview:')
        self.stdout.write(f'  {answer[:200]}...')

        if sources:
            self.stdout.write('')
            self.stdout.write(f'  Top source:')
            top_source = sources[0]
            self.stdout.write(f'    Type: {top_source.get("source_type")}')
            self.stdout.write(f'    Title: {top_source.get("title", "")[:60]}')
            self.stdout.write(f'    Relevance: {top_source.get("relevance_score", 0):.2%}')

        return True

    def test_trade_validator(self):
        """Test trade validator"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 5: TRADE VALIDATOR'))
        self.stdout.write('-' * 80)

        # Check if we have data for validation
        news_count = NewsArticle.objects.count()

        if news_count == 0:
            self.stdout.write(self.style.WARNING('  WARNING: No news data available'))
            self.stdout.write('  Trade validator will work with limited context')

        self.stdout.write('Testing trade validation...')

        result = validate_trade(
            symbol='RELIANCE',
            direction='LONG',
            strategy_type='OPTIONS'
        )

        if 'error' in result:
            self.stdout.write(self.style.ERROR(f'  FAILED: {result["error"]}'))
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Trade validation working'))
        self.stdout.write(f'  Decision: {"APPROVED" if result["approved"] else "REJECTED"}')
        self.stdout.write(f'  Confidence: {result["confidence"]:.0%}')
        self.stdout.write(f'  Sentiment: {result["market_sentiment"]}')
        self.stdout.write(f'  Sources used: {result["sources_used"]}')
        self.stdout.write('')
        self.stdout.write(f'  Reasoning:')
        self.stdout.write(f'  {result["reasoning"][:200]}...')

        if result.get('risks'):
            self.stdout.write('')
            self.stdout.write(f'  Risks identified: {len(result["risks"])}')
            for i, risk in enumerate(result['risks'][:2], 1):
                self.stdout.write(f'    {i}. {risk[:80]}...')

        return True


    def _print_section_header(self, title):
        """Print formatted section header"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(title))
        self.stdout.write('-' * 80)
