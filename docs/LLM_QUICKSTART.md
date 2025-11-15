# LLM System - Quick Start Guide

**AI-Powered Trading Intelligence for mCube Platform**

## What's Included

The LLM system adds intelligent analysis to your trading platform:

- **News Processing**: Auto-analyze news with sentiment and insights
- **RAG Queries**: Ask questions about stocks and get context-aware answers
- **Trade Validation**: LLM validates trades based on market intelligence
- **Knowledge Base**: Semantic search across news and investor calls

## 5-Minute Setup

### Step 1: Install Ollama

```bash
# macOS
brew install ollama

# Or download from https://ollama.ai/download
```

### Step 2: Download a Model

```bash
# Quick setup (recommended) - Downloads DeepSeek 6.7B (~3.8GB)
python manage.py manage_models --quick-setup

# Or manual setup
python manage.py manage_models --list-recommended
python manage.py manage_models --download \
    TheBloke/deepseek-coder-6.7B-instruct-GGUF \
    deepseek-coder-6.7b-instruct.Q4_K_M.gguf
```

### Step 3: Configure Environment

Add to `.env`:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=deepseek-coder-6.7b
```

### Step 4: Test Everything

```bash
python manage.py test_llm
```

That's it! If all tests pass, you're ready to go.

## Quick Examples

### Process News

```bash
# Process demo news
python manage.py fetch_news --demo --limit 5

# Process with symbols filter
python manage.py fetch_news --demo --symbols RELIANCE,TCS
```

### Ask Questions (RAG)

```python
from apps.llm.services.rag_system import ask_question

success, answer, sources = ask_question(
    "What is the sentiment on RELIANCE?",
    n_results=5
)

print(answer)
```

### Validate Trades

```python
from apps.llm.services.trade_validator import validate_trade

result = validate_trade(
    symbol="RELIANCE",
    direction="LONG",
    strategy_type="OPTIONS"
)

if result['approved']:
    print(f"Approved with {result['confidence']:.0%} confidence")
    print(result['reasoning'])
```

### Process Your Own News

```python
from apps.llm.services.news_processor import process_news_article

success, article = process_news_article(
    title="Your news title",
    content="Full article content...",
    source="Economic Times",
    symbols=["RELIANCE"]
)

print(f"Sentiment: {article.sentiment_label}")
print(f"Summary: {article.llm_summary}")
```

## Components Overview

### 1. Ollama Client (`apps/llm/services/ollama_client.py`)
- Text generation
- Embeddings
- Chat completions
- JSON extraction

### 2. Vector Store (`apps/llm/services/vector_store.py`)
- ChromaDB integration
- Semantic search
- Document storage

### 3. News Processor (`apps/llm/services/news_processor.py`)
- Sentiment analysis
- Summary generation
- Key insights extraction
- Auto-embedding

### 4. RAG System (`apps/llm/services/rag_system.py`)
- Question answering
- Symbol analysis
- Market sentiment
- Stock comparison

### 5. Trade Validator (`apps/llm/services/trade_validator.py`)
- Entry validation
- Exit validation
- Risk analysis
- LLM reasoning

## Data Flow

```
News Source
    ↓
News Processor
    ├─→ Sentiment Analysis
    ├─→ Summary Generation
    ├─→ Insights Extraction
    └─→ Embedding Generation
    ↓
Database (NewsArticle)
    ↓
Vector Store (ChromaDB)
    ↓
RAG System
    ├─→ Question Answering
    ├─→ Symbol Analysis
    └─→ Trade Validation
```

## Directory Structure

```
apps/llm/
├── services/
│   ├── ollama_client.py      # LLM interface
│   ├── vector_store.py        # Vector database
│   ├── rag_system.py          # RAG queries
│   ├── trade_validator.py     # Trade validation
│   ├── news_processor.py      # News analysis
│   └── model_manager.py       # Model downloads

apps/data/models.py
├── NewsArticle                # Processed news
├── InvestorCall               # Earnings calls
└── KnowledgeBase              # Knowledge chunks

apps/core/management/commands/
├── manage_models.py           # Model management
├── test_llm.py                # Testing
└── fetch_news.py              # News fetching

models/
├── gguf/                      # Downloaded models
├── ollama/                    # Ollama configs
└── metadata.json              # Model tracking

chroma_db/                     # Vector database
```

## Management Commands

### Model Management
```bash
# List recommended models
python manage.py manage_models --list-recommended

# Download a model
python manage.py manage_models --download REPO_ID FILENAME

# Import to Ollama
python manage.py manage_models --import-to-ollama FILE.gguf MODEL_NAME

# Quick setup
python manage.py manage_models --quick-setup

# List local models
python manage.py manage_models --list-local
```

### Testing
```bash
# Full test
python manage.py test_llm

# Quick test
python manage.py test_llm --quick

# Test specific component
python manage.py test_llm --component ollama
python manage.py test_llm --component rag
python manage.py test_llm --component validator
```

### News Processing
```bash
# Demo data
python manage.py fetch_news --demo --limit 10

# With symbol filter
python manage.py fetch_news --demo --symbols RELIANCE,TCS --limit 5
```

## Integration with Trading System

### Position Entry with Validation

```python
from apps.llm.services.trade_validator import validate_trade

def create_validated_position(account, symbol, direction, **kwargs):
    # Validate with LLM first
    result = validate_trade(symbol, direction, kwargs.get('strategy_type', 'OPTIONS'))

    if not result['approved'] or result['confidence'] < 0.6:
        return {
            'success': False,
            'reason': result['reasoning'],
            'llm_confidence': result['confidence']
        }

    # Create position
    position = Position.objects.create(
        account=account,
        symbol=symbol,
        direction=direction,
        **kwargs
    )

    # Store LLM analysis
    position.metadata['llm_validation'] = {
        'approved': True,
        'confidence': result['confidence'],
        'reasoning': result['reasoning'],
        'sentiment': result['market_sentiment']
    }
    position.save()

    return {'success': True, 'position': position}
```

### Risk Monitoring

```python
from apps.llm.services.rag_system import ask_question

def check_position_risk(position):
    question = f"""
    What are the current risks for {position.symbol}?
    Current position: {position.direction} at {position.entry_price}
    """

    success, analysis, sources = ask_question(question, n_results=5)

    if success:
        # Parse for high-risk indicators
        risk_keywords = ['risk', 'concern', 'warning', 'bearish']
        risk_score = sum(1 for kw in risk_keywords if kw in analysis.lower())

        return {
            'risk_score': risk_score,
            'analysis': analysis,
            'sources_count': len(sources)
        }
```

### Daily Market Brief

```python
from apps.llm.services.rag_system import get_rag_system

def generate_market_brief():
    rag = get_rag_system()

    # Overall sentiment
    _, market_sentiment = rag.get_market_sentiment(days_back=1)

    # Trade ideas
    _, trade_ideas = rag.get_trade_ideas(
        strategy_type="options",
        risk_level="medium"
    )

    return f"""
    Daily Market Brief - {timezone.now().date()}

    Market Sentiment:
    {market_sentiment}

    Trade Ideas:
    {trade_ideas}
    """
```

## Recommended Models

| Model | Size | RAM | Use Case |
|-------|------|-----|----------|
| **DeepSeek 6.7B** | 3.8GB | 8GB | General use (recommended) |
| Mistral 7B | 4.1GB | 8GB | Fast responses |
| DeepSeek 33B | 19GB | 24GB | Complex analysis |
| Llama 2 13B | 7.4GB | 12GB | Balanced performance |

Start with **DeepSeek 6.7B Q4_K_M** - best balance of quality and resource usage.

## Performance Tips

### 1. Use Smaller Models for Development
```env
OLLAMA_MODEL=deepseek-coder-6.7b  # Fast, low memory
```

### 2. Adjust Context Window
```env
OLLAMA_NUM_CTX=2048  # Smaller = faster (default: 4096)
```

### 3. Lower Temperature for Factual Tasks
```python
client.generate(prompt, temperature=0.2)  # More focused
```

### 4. Batch Process News
```python
processor.batch_process_articles(articles)  # More efficient
```

### 5. Enable GPU (if available)
- NVIDIA: Install CUDA toolkit (auto-detected by Ollama)
- Apple Silicon: Works automatically with Metal

## Troubleshooting

### "LLM not available"
1. Check Ollama is running: `ollama serve`
2. Verify model: `ollama list`
3. Check `.env` settings

### Slow responses
1. Use smaller model (6.7B vs 33B)
2. Reduce context: `OLLAMA_NUM_CTX=2048`
3. Use Q4_K_M quantization

### Out of memory
1. Use Q4_K_M quantization (not Q6_K)
2. Use smaller model
3. Close other applications

### Poor quality results
1. Use larger model (33B)
2. Improve prompts
3. Increase temperature slightly

## Next Steps

1. **Process Some News**
   ```bash
   python manage.py fetch_news --demo --limit 10
   ```

2. **Try RAG Queries**
   ```python
   from apps.llm.services.rag_system import ask_question
   success, answer, _ = ask_question("What's the sentiment on NIFTY?")
   ```

3. **Validate a Trade**
   ```python
   from apps.llm.services.trade_validator import validate_trade
   result = validate_trade("RELIANCE", "LONG", "OPTIONS")
   ```

4. **Integrate with Your System**
   - Add to position entry flow
   - Use for risk monitoring
   - Generate market briefs

## Documentation

- **Setup Guide**: `docs/LLM_MODEL_SETUP.md` - Detailed model setup
- **Integration Guide**: `docs/LLM_INTEGRATION.md` - Full API reference
- **This Guide**: `docs/LLM_QUICKSTART.md` - Quick start

## API Reference (Quick)

### RAG System
```python
from apps.llm.services.rag_system import ask_question, get_symbol_analysis

# Ask any question
success, answer, sources = ask_question("Question?")

# Symbol analysis
success, analysis = get_symbol_analysis("RELIANCE")
```

### Trade Validator
```python
from apps.llm.services.trade_validator import validate_trade

result = validate_trade(
    symbol="TCS",
    direction="LONG",
    strategy_type="OPTIONS"
)
# Returns: approved, confidence, reasoning, risks, etc.
```

### News Processor
```python
from apps.llm.services.news_processor import process_news_article

success, article = process_news_article(
    title="...",
    content="...",
    source="...",
    symbols=["RELIANCE"]
)
# Returns: article with sentiment, summary, insights
```

## Support

- Check logs: `tail -f logs/django.log`
- Test system: `python manage.py test_llm`
- Ollama docs: https://ollama.ai/
- HuggingFace: https://huggingface.co/

---

**Ready to go?** Start with `python manage.py test_llm` to verify everything works!
