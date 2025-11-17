# LLM Integration Guide

This guide explains how to use the LLM-powered intelligence system in mCube Trading Platform.

## Overview

The LLM system provides AI-powered analysis and decision support through:

1. **News Processing**: Automatically analyze news with sentiment extraction
2. **RAG Queries**: Ask questions about stocks using semantic search
3. **Trade Validation**: LLM validates trades based on market intelligence
4. **Knowledge Base**: Stores and retrieves market information efficiently

## Architecture

```
┌─────────────────┐
│  News Sources   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│ News Processor  │─────▶│  NewsArticle │
│  - Sentiment    │      │    Model     │
│  - Summary      │      └──────────────┘
│  - Insights     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│ Embedding Gen   │─────▶│ KnowledgeBase│
│   (Ollama)      │      │    Model     │
└────────┬────────┘      └──────────────┘
         │
         ▼
┌─────────────────┐
│  Vector Store   │
│   (ChromaDB)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│   RAG System    │◀────▶│ Trade        │
│  - Query        │      │ Validator    │
│  - Generate     │      └──────────────┘
└─────────────────┘
```

## Quick Start

### 1. Setup (First Time)

```bash
# Install Ollama (if not already installed)
# Visit: https://ollama.ai/download

# Download and import a model
python manage.py manage_models --quick-setup

# Test the system
python manage.py test_llm
```

### 2. Environment Variables

Add to `.env`:

```env
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=deepseek-coder-6.7b

# Optional: Ollama settings
OLLAMA_TIMEOUT=120
OLLAMA_TEMPERATURE=0.7
```

## Core Components

### 1. Ollama LLM Client

Direct interface to Ollama for text generation and embeddings.

**Import**:
```python
from apps.llm.services.ollama_client import get_ollama_client, generate_embedding
```

**Usage**:
```python
# Get client
client = get_ollama_client()

# Check if available
if client.is_enabled():
    # Generate text
    success, response, metadata = client.generate(
        prompt="Analyze this news: ...",
        temperature=0.3
    )

    # Generate embedding
    success, embedding = generate_embedding("Text to embed")
```

**Features**:
- Text completion
- Chat conversations
- Embedding generation
- JSON extraction
- Streaming support

### 2. Vector Store (ChromaDB)

Stores embeddings for semantic search.

**Import**:
```python
from apps.llm.services.vector_store import get_vector_store
```

**Usage**:
```python
store = get_vector_store()

# Add documents
store.add_documents(
    collection_name='my_collection',
    documents=['Doc 1', 'Doc 2'],
    embeddings=[emb1, emb2],
    metadatas=[{'type': 'news'}, {'type': 'news'}],
    ids=['id1', 'id2']
)

# Query
results = store.query(
    collection_name='my_collection',
    query_embeddings=[query_embedding],
    n_results=5
)
```

**Collections**:
- `knowledge`: General knowledge base
- `news`: News articles
- `investor_calls`: Earnings transcripts

### 3. News Processor

Processes news articles with LLM analysis.

**Import**:
```python
from apps.llm.services.news_processor import get_news_processor, process_news_article
```

**Basic Usage**:
```python
success, article = process_news_article(
    title="RELIANCE Reports Strong Q4",
    content="Full article text...",
    source="Economic Times",
    symbols=["RELIANCE"]
)

if success:
    print(f"Sentiment: {article.sentiment_label}")
    print(f"Summary: {article.llm_summary}")
    print(f"Insights: {article.key_insights}")
```

**Advanced Usage**:
```python
processor = get_news_processor()

# Process single article
success, article, message = processor.process_article(
    title="Market Update",
    content="...",
    source="Bloomberg",
    url="https://...",
    published_at=datetime.now(),
    symbols=["NIFTY", "RELIANCE"],
    author="John Doe"
)

# Batch processing
articles = [
    {'title': '...', 'content': '...', 'source': '...'},
    {'title': '...', 'content': '...', 'source': '...'},
]

success_count, error_count, errors = processor.batch_process_articles(articles)
```

**What it does**:
1. Analyzes sentiment (VERY_POSITIVE to VERY_NEGATIVE)
2. Generates concise summary
3. Extracts key trading insights
4. Creates embeddings for semantic search
5. Stores in database and vector store

### 4. RAG System

Query knowledge base with context-aware responses.

**Import**:
```python
from apps.llm.services.rag_system import (
    get_rag_system,
    ask_question,
    get_symbol_analysis
)
```

**Basic Usage**:
```python
# Ask any question
success, answer, sources = ask_question(
    "What is the sentiment on RELIANCE?",
    n_results=5
)

if success:
    print(f"Answer: {answer}")
    print(f"Used {len(sources)} sources")
```

**Symbol-Specific Queries**:
```python
rag = get_rag_system()

# Get analysis for a symbol
success, answer, sources = rag.query_about_symbol(
    symbol="TCS",
    question="What are the growth prospects?",
    days_back=30,
    n_results=10
)
```

**Market Sentiment**:
```python
# Overall market
success, sentiment = rag.get_market_sentiment(days_back=7)

# Sector-specific
success, sentiment = rag.get_market_sentiment(
    sector="IT",
    days_back=7
)
```

**Compare Stocks**:
```python
success, comparison = rag.compare_stocks(
    symbols=["RELIANCE", "TCS", "INFY"],
    aspect="fundamentals"  # or "technicals", "sentiment"
)
```

**Trade Ideas**:
```python
success, ideas = rag.get_trade_ideas(
    strategy_type="options",  # or "futures", "cash"
    risk_level="medium"       # or "low", "high"
)
```

### 5. Trade Validator

LLM-powered trade validation using market intelligence.

**Import**:
```python
from apps.llm.services.trade_validator import get_trade_validator, validate_trade
```

**Basic Usage**:
```python
result = validate_trade(
    symbol="RELIANCE",
    direction="LONG",
    strategy_type="OPTIONS"
)

if result['approved']:
    print(f"Trade approved with {result['confidence']:.0%} confidence")
    print(f"Reasoning: {result['reasoning']}")
else:
    print(f"Trade rejected")
    print(f"Risks: {result['risks']}")
```

**Detailed Validation**:
```python
validator = get_trade_validator()

result = validator.validate_trade(
    symbol="TCS",
    direction="LONG",
    strategy_type="OPTIONS",
    price_level=3500.0,
    quantity=100,
    additional_context="Breakout above resistance"
)

# Result structure
{
    'approved': True/False,
    'confidence': 0.0-1.0,
    'reasoning': 'Explanation...',
    'risks': ['Risk 1', 'Risk 2'],
    'opportunities': ['Opp 1', 'Opp 2'],
    'alternative_suggestions': ['Alt 1', 'Alt 2'],
    'market_sentiment': 'BULLISH/BEARISH/NEUTRAL',
    'llm_analysis': 'Full analysis...',
    'sources_used': 10
}
```

**Exit Validation**:
```python
should_exit, analysis = validator.should_exit_position(
    symbol="RELIANCE",
    direction="LONG",
    entry_price=2500.0,
    current_price=2650.0,
    pnl_percent=6.0,
    days_held=15
)

if should_exit:
    print(f"Exit recommended: {analysis}")
```

## Integration Examples

### With Position Entry

```python
from apps.positions.models import Position
from apps.llm.services.trade_validator import validate_trade

def create_position_with_validation(account, symbol, direction, strategy_type, **kwargs):
    """Create position after LLM validation"""

    # Validate with LLM
    result = validate_trade(
        symbol=symbol,
        direction=direction,
        strategy_type=strategy_type
    )

    # Check approval and confidence
    if not result['approved'] or result['confidence'] < 0.6:
        return {
            'success': False,
            'reason': result['reasoning'],
            'risks': result['risks']
        }

    # Create position
    position = Position.objects.create(
        account=account,
        symbol=symbol,
        direction=direction,
        strategy_type=strategy_type,
        **kwargs
    )

    # Store validation metadata
    position.metadata['llm_validation'] = {
        'approved': True,
        'confidence': result['confidence'],
        'sentiment': result['market_sentiment'],
        'reasoning': result['reasoning'],
        'validated_at': timezone.now().isoformat()
    }
    position.save()

    return {'success': True, 'position': position}
```

### With News Fetching

```python
from apps.llm.services.news_processor import get_news_processor

def fetch_and_process_news(source_api):
    """Fetch news from API and process with LLM"""

    processor = get_news_processor()

    # Fetch from your news source
    articles = source_api.fetch_latest(limit=10)

    # Process each article
    for article_data in articles:
        success, article, message = processor.process_article(
            title=article_data['title'],
            content=article_data['content'],
            source=article_data['source'],
            url=article_data['url'],
            published_at=article_data['published_at'],
            symbols=article_data.get('symbols', [])
        )

        if success:
            print(f"Processed: {article.title}")
            print(f"Sentiment: {article.sentiment_label}")
        else:
            print(f"Failed: {message}")
```

### Daily Market Analysis

```python
from apps.llm.services.rag_system import get_rag_system

def generate_daily_market_report():
    """Generate daily market analysis using RAG"""

    rag = get_rag_system()

    # Get overall sentiment
    success, market_sentiment = rag.get_market_sentiment(days_back=1)

    # Get trade ideas
    success, trade_ideas = rag.get_trade_ideas(
        strategy_type="options",
        risk_level="medium"
    )

    # Query specific sectors
    sectors = ["IT", "Banking", "Pharma"]
    sector_analysis = {}

    for sector in sectors:
        success, analysis = rag.get_market_sentiment(
            sector=sector,
            days_back=7
        )
        if success:
            sector_analysis[sector] = analysis

    # Compile report
    report = f"""
# Daily Market Report - {timezone.now().date()}

## Overall Market Sentiment
{market_sentiment}

## Sector Analysis
"""
    for sector, analysis in sector_analysis.items():
        report += f"\n### {sector}\n{analysis}\n"

    report += f"\n## Trade Ideas\n{trade_ideas}"

    return report
```

### Risk Management Integration

```python
from apps.llm.services.rag_system import ask_question

def check_position_risk(position):
    """Check position risk using LLM"""

    # Query recent news about the symbol
    question = f"""
    What are the current risks for holding a {position.direction} position in {position.symbol}?
    Entry: {position.entry_price}, Current: {position.current_price}
    """

    success, analysis, sources = ask_question(question, n_results=5)

    if not success:
        return None

    # Parse for risk keywords
    risk_keywords = ['risk', 'concern', 'warning', 'negative', 'bearish']
    has_risk = any(keyword in analysis.lower() for keyword in risk_keywords)

    return {
        'has_elevated_risk': has_risk,
        'analysis': analysis,
        'sources_count': len(sources),
        'checked_at': timezone.now()
    }
```

## Testing

### Run Full Test Suite

```bash
python manage.py test_llm
```

### Test Specific Components

```bash
# Test only Ollama
python manage.py test_llm --component ollama

# Test only RAG
python manage.py test_llm --component rag

# Test only validator
python manage.py test_llm --component validator

# Quick tests only
python manage.py test_llm --quick
```

## Data Models

### NewsArticle

Stores processed news articles.

**Fields**:
- `title`: Article title
- `content`: Full content
- `source`: News source
- `url`: Article URL
- `published_at`: Publication date
- `author`: Article author
- `symbols`: Related stock symbols (JSONField)
- `sentiment_score`: -1.0 to 1.0
- `sentiment_label`: VERY_POSITIVE to VERY_NEGATIVE
- `llm_summary`: LLM-generated summary
- `key_insights`: List of trading insights (JSONField)
- `embedding_stored`: Whether embeddings are stored
- `embedding_id`: Vector store ID

**Query Examples**:
```python
from apps.data.models import NewsArticle

# Get recent news for a symbol
recent_news = NewsArticle.objects.filter(
    symbols__contains="RELIANCE",
    published_at__gte=timezone.now() - timedelta(days=7)
).order_by('-published_at')

# Get positive news
positive_news = NewsArticle.objects.filter(
    sentiment_label__in=['POSITIVE', 'VERY_POSITIVE']
)

# Get news with embeddings
embedded_news = NewsArticle.objects.filter(embedding_stored=True)
```

### InvestorCall

Stores earnings call transcripts and analysis.

**Fields**:
- `company`: Company name
- `symbol`: Stock symbol
- `call_date`: Call date
- `quarter`: Fiscal quarter
- `year`: Fiscal year
- `call_type`: EARNINGS/CONFERENCE/ANALYST_MEET
- `transcript`: Full transcript
- `executive_summary`: LLM summary
- `key_points`: Important points (JSONField)
- `financial_metrics`: Extracted metrics (JSONField)
- `management_tone`: OPTIMISTIC/NEUTRAL/CAUTIOUS
- `trading_signal`: BULLISH/NEUTRAL/BEARISH
- `embedding_stored`: Whether embeddings are stored

### KnowledgeBase

Stores processed knowledge chunks with embeddings.

**Fields**:
- `source_type`: news/investor_call/research
- `source_id`: ID of source record
- `title`: Chunk title
- `content_chunk`: Text chunk
- `embedding_id`: Vector store ID
- `metadata`: Additional metadata (JSONField)
- `times_retrieved`: Usage counter

## Best Practices

### 1. Model Selection

- **Development/Testing**: DeepSeek 6.7B (low resource usage)
- **Production**: DeepSeek 33B (better accuracy) or Mistral 7B (faster)
- **High-Volume**: Consider GPU acceleration

### 2. News Processing

- Process news in batches for efficiency
- Set up cron job for regular processing
- Monitor sentiment distribution
- Archive old news to prevent database bloat

### 3. RAG Queries

- Use specific questions for better results
- Filter by date ranges when relevant
- Adjust `n_results` based on query complexity
- Cache frequent queries

### 4. Trade Validation

- Set minimum confidence threshold (e.g., 0.6)
- Always review LLM reasoning
- Use as decision support, not automation
- Log all validations for analysis

### 5. Performance

- Use embedding cache for repeated texts
- Batch process when possible
- Monitor Ollama memory usage
- Clean up old vector store collections

## Troubleshooting

### Ollama Not Available

**Error**: `LLM not available`

**Solutions**:
1. Check if Ollama is running: `ollama serve`
2. Verify model is loaded: `ollama list`
3. Check `OLLAMA_HOST` in `.env`
4. Test connection: `curl http://localhost:11434/api/tags`

### Slow Response Times

**Solutions**:
1. Use smaller model (Q4_K_M vs Q6_K)
2. Reduce context window: `OLLAMA_NUM_CTX=2048`
3. Enable GPU acceleration
4. Use faster model (Mistral vs DeepSeek 33B)

### Out of Memory

**Solutions**:
1. Use smaller quantization (Q4_K_M)
2. Use smaller model (6.7B vs 33B)
3. Increase system swap
4. Close other applications
5. Set `OLLAMA_NUM_CTX=2048` (default is 4096)

### Poor Quality Results

**Solutions**:
1. Use larger model (33B vs 6.7B)
2. Adjust temperature (lower = more focused)
3. Improve prompts with more context
4. Use higher quantization (Q6_K vs Q4_K_M)

### Vector Store Issues

**Error**: `Vector store not available`

**Solutions**:
1. Check `chroma_db/` directory exists
2. Verify write permissions
3. Check disk space
4. Delete and recreate: `rm -rf chroma_db/`

## Advanced Topics

### Custom Prompts

Customize system prompts for different use cases:

```python
client = get_ollama_client()

# Trading-focused
system_prompt = """You are a conservative stock market analyst.
Focus on risk management and capital preservation.
Always identify potential risks before opportunities."""

success, response, _ = client.generate(
    prompt="Analyze this trade: ...",
    system=system_prompt,
    temperature=0.2
)
```

### Multi-Model Strategy

Use different models for different tasks:

```python
# Fast model for sentiment
os.environ['OLLAMA_MODEL'] = 'mistral-7b'
sentiment = analyze_sentiment(text)

# Larger model for validation
os.environ['OLLAMA_MODEL'] = 'deepseek-coder-33b'
validation = validate_trade(symbol, direction)
```

### Embedding Cache

Cache embeddings for frequently used texts:

```python
from django.core.cache import cache

def get_cached_embedding(text):
    cache_key = f'embedding:{hash(text)}'
    embedding = cache.get(cache_key)

    if embedding is None:
        success, embedding = generate_embedding(text)
        if success:
            cache.set(cache_key, embedding, timeout=3600)

    return embedding
```

## Monitoring

### Track LLM Usage

```python
from apps.data.models import NewsArticle, KnowledgeBase

# News processing stats
total_news = NewsArticle.objects.count()
with_embeddings = NewsArticle.objects.filter(embedding_stored=True).count()
positive_news = NewsArticle.objects.filter(
    sentiment_label__in=['POSITIVE', 'VERY_POSITIVE']
).count()

print(f"Total news: {total_news}")
print(f"With embeddings: {with_embeddings}")
print(f"Positive sentiment: {positive_news}")

# Knowledge base stats
total_chunks = KnowledgeBase.objects.count()
news_chunks = KnowledgeBase.objects.filter(source_type='news').count()

print(f"Total knowledge chunks: {total_chunks}")
print(f"News chunks: {news_chunks}")
```

### Performance Metrics

Monitor in production:
- LLM response time
- Embedding generation time
- RAG query time
- Trade validation time
- Vector store query time

---

**Need Help?**
- Check Ollama docs: https://ollama.ai/
- Review logs: `tail -f logs/django.log`
- Test system: `python manage.py test_llm`
- Model setup: See `docs/LLM_MODEL_SETUP.md`
