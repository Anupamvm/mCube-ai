# LLM App Documentation

**Location**: `apps/llm/`

The LLM app integrates AI-powered trade validation using local LLM (Ollama) and RAG (Retrieval-Augmented Generation) for context-aware analysis.

---

## What This App Does

1. **Trade Validation** - AI validation of proposed trades
2. **News Processing** - Sentiment analysis of market news
3. **RAG System** - Knowledge-based query answering
4. **Vector Storage** - ChromaDB for semantic search
5. **LLM Integration** - Local Ollama for inference

---

## Files Overview

| File | Purpose |
|------|---------|
| `models.py` | LLMValidation, LLMPrompt models |
| `services/trade_validator.py` | Trade validation service |
| `services/news_processor.py` | News analysis and embedding |
| `services/rag_system.py` | RAG query system |
| `services/vector_store.py` | ChromaDB integration |
| `services/ollama_client.py` | Ollama LLM client |
| `services/model_manager.py` | Model download/management |

---

## Key Models

### LLMValidation

Records trade validation requests and outcomes.

```python
# Fields
symbol = CharField()               # Stock symbol
direction = CharField()            # LONG or SHORT
prompt = TextField()               # Prompt sent to LLM
context_data = JSONField()         # Market data, OI, sector info

# Response
raw_response = TextField()         # Raw LLM output
parsed_response = JSONField()      # Structured response
recommendation = CharField()       # LONG, SHORT, or AVOID
confidence_score = DecimalField()  # 0-100
reasoning = TextField()
risk_factors = JSONField()

# Model Info
model_used = CharField()           # Default: deepseek-coder:33b
processing_time_ms = IntegerField()

# Outcome Tracking
human_approved = BooleanField()    # Did human approve?
was_executed = BooleanField()      # Was trade taken?
actual_pnl = DecimalField()        # Actual P&L result
outcome_correct = BooleanField()   # Was LLM prediction correct?
```

### LLMPrompt

Reusable prompt templates.

```python
# Fields
name = CharField()                 # Prompt identifier
purpose = CharField()              # What this prompt does
template = TextField()             # Prompt with {placeholders}
is_active = BooleanField()
version = CharField()

# Stats
times_used = IntegerField()
avg_confidence = DecimalField()    # Average confidence of results
```

---

## Trade Validation

**File**: `services/trade_validator.py`

### Validating a Trade

```python
from apps.llm.services.trade_validator import validate_trade

result = validate_trade(
    symbol='RELIANCE',
    direction='LONG',
    strategy_type='FUTURES',
    price_level=3100,
    quantity=1,
    additional_context={'score': 75, 'sector': 'bullish'}
)

# Returns:
# {
#     'approved': True,
#     'confidence': 0.82,         # 82%
#     'reasoning': 'Strong OI buildup supports long...',
#     'risks': ['RSI near overbought'],
#     'opportunities': ['Sector momentum strong'],
#     'market_sentiment': 'BULLISH',
#     'sources_used': 5
# }
```

### Validation Flow

```
Trade Proposal (symbol, direction)
      ↓
1. Gather Context (RAG)
   ├── Recent news and sentiment
   ├── Investor call insights
   └── Market sentiment
      ↓
2. Build Validation Prompt
   - Include all context
   - Clear output format instructions
      ↓
3. Send to LLM (Ollama)
   - Model: deepseek-coder:33b
   - Temperature: 0.3 (consistent)
      ↓
4. Parse Response
   - Extract: DECISION, CONFIDENCE, REASONING
   - Extract: RISKS, OPPORTUNITIES
      ↓
5. Return Structured Result
   - approved: bool
   - confidence: float (0-1)
   - reasoning, risks, etc.
```

### Exit Validation

```python
from apps.llm.services.trade_validator import should_exit_position

result = should_exit_position(
    symbol='RELIANCE',
    direction='LONG',
    entry_price=3100,
    current_price=3180,
    pnl_percent=2.5,
    days_held=3
)

# Returns recommendation to exit or hold
```

---

## News Processing

**File**: `services/news_processor.py`

### Processing News Articles

```python
from apps.llm.services.news_processor import NewsProcessor

processor = NewsProcessor()

success, article, message = processor.process_article(
    title="RELIANCE Q3 Results Beat Estimates",
    content="Reliance Industries reported...",
    source="Economic Times",
    url="https://...",
    published_at=datetime.now(),
    symbols=['RELIANCE']
)
```

### Processing Pipeline

```
News Article Received
      ↓
1. Analyze Sentiment (LLM)
   - Score: -1 to +1
   - Label: POSITIVE, NEUTRAL, NEGATIVE
      ↓
2. Generate Summary (LLM)
   - 2-3 sentences
   - Focus on financial implications
      ↓
3. Extract Key Insights (LLM)
   - 3-5 actionable insights
   - Trading-relevant points
      ↓
4. Save to Database
   - NewsArticle record
      ↓
5. Generate Embeddings
   - Chunk article (title, insights, content)
   - Create embeddings for each chunk
   - Store in ChromaDB
   - Link to KnowledgeBase
```

### Batch Processing

```python
articles = [
    {'title': '...', 'content': '...', ...},
    {'title': '...', 'content': '...', ...},
]

success, errors, messages = processor.batch_process_articles(articles)
```

---

## RAG System

**File**: `services/rag_system.py`

### Querying the Knowledge Base

```python
from apps.llm.services.rag_system import RAGSystem

rag = RAGSystem()

success, answer, sources = rag.query(
    question="What is the sentiment on RELIANCE?",
    n_results=5
)

# Returns:
# - answer: LLM-generated answer based on context
# - sources: List of source documents with relevance
```

### RAG Flow

```
User Question
      ↓
1. Generate Query Embedding
      ↓
2. Search Vector Store (ChromaDB)
   - Find top-k relevant documents
   - Return with similarity scores
      ↓
3. Build Context
   - Format documents with source info
   - Include relevance indicators
      ↓
4. Generate Answer (LLM)
   - System: "You are an expert stock analyst"
   - Include context
   - Cite sources
      ↓
5. Return Answer + Sources
```

### Specialized Queries

```python
# Query about specific symbol
rag.query_about_symbol('RELIANCE')

# Query market sentiment
rag.get_market_sentiment(days=7)

# Query news specifically
rag.query_news("RELIANCE earnings")

# Query investor calls
rag.query_investor_calls("RELIANCE")
```

---

## Vector Store

**File**: `services/vector_store.py`

### ChromaDB Integration

```python
from apps.llm.services.vector_store import VectorStore

store = VectorStore()

# Add documents
store.add_documents(
    collection_name='knowledge',
    documents=['text1', 'text2'],
    embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...]],
    metadatas=[{'source': 'news'}, {'source': 'call'}],
    ids=['doc1', 'doc2']
)

# Search
results = store.query(
    collection_name='knowledge',
    query_embeddings=[[0.15, 0.25, ...]],
    n_results=5
)
```

### Collections

| Collection | Purpose |
|------------|---------|
| `knowledge` | General knowledge base |
| `news` | News articles |

---

## Ollama Client

**File**: `services/ollama_client.py`

### Using the LLM

```python
from apps.llm.services.ollama_client import OllamaClient

client = OllamaClient()

# Generate text
success, response, metadata = client.generate(
    prompt="Analyze this trade...",
    model="deepseek-coder:33b",
    system="You are a trading analyst",
    temperature=0.3,
    max_tokens=1000
)
```

### Configuration

```bash
# Environment variables
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=deepseek-coder:33b
```

### Embedding Generation

```python
# Generate embedding for text
embedding = client.generate_embedding("Some text to embed")
```

---

## Model Manager

**File**: `services/model_manager.py`

### Managing Models

```python
from apps.llm.services.model_manager import ModelManager

manager = ModelManager()

# Download model from HuggingFace
success, path = manager.download_from_huggingface(
    repo_id='TheBloke/Llama-2-7B-GGUF',
    filename='llama-2-7b.Q4_K_M.gguf',
    model_name='llama2-7b'
)
```

### Directory Structure

```
models/
├── gguf/              # Downloaded GGUF files
├── ollama/            # Ollama model files
└── metadata.json      # Model metadata
```

---

## LLM Prompt Templates

### Trade Validation Prompt

```
You are an expert stock market analyst. Evaluate this trade:

Symbol: {symbol}
Direction: {direction}
Entry Price: {price}
Quantity: {quantity}

CONTEXT:
{context}

Respond with:
DECISION: [APPROVED/REJECTED/CONDITIONAL]
CONFIDENCE: [0-100]
REASONING: [explanation]
RISKS: [list of risks]
OPPORTUNITIES: [list of opportunities]
SENTIMENT: [BULLISH/BEARISH/NEUTRAL]
```

### Sentiment Analysis Prompt

```
Analyze the sentiment of this news article:

Title: {title}
Content: {content}

Consider:
- Impact on stock price
- Market implications
- Investor sentiment

Respond with:
SENTIMENT: [VERY_POSITIVE/POSITIVE/NEUTRAL/NEGATIVE/VERY_NEGATIVE]
SCORE: [-1.0 to +1.0]
REASONING: [brief explanation]
```

---

## How to Study This App

1. **Start with `models.py`** - Understand LLMValidation structure
2. **Read `trade_validator.py`** - Core validation logic
3. **Study `news_processor.py`** - News pipeline
4. **Check `rag_system.py`** - RAG implementation
5. **Review `ollama_client.py`** - LLM integration

---

## Common Tasks for Developers

### Test LLM Connection

```python
from apps.llm.services.ollama_client import OllamaClient

client = OllamaClient()
if client.is_enabled():
    print("Ollama is connected")
else:
    print("Ollama is not available")
```

### Validate a Trade Manually

```python
from apps.llm.services.trade_validator import validate_trade

result = validate_trade(
    symbol='INFY',
    direction='LONG',
    strategy_type='FUTURES'
)
print(f"Approved: {result['approved']}, Confidence: {result['confidence']}")
```

### Process News Manually

```python
from apps.llm.services.news_processor import NewsProcessor

processor = NewsProcessor()
success, article, msg = processor.process_article(
    title="Test News",
    content="This is test content...",
    source="Manual",
    url="http://test.com",
    published_at=datetime.now()
)
```

---

## Key Features

1. **Local LLM** - Uses Ollama (no cloud API needed)
2. **RAG System** - Context-aware responses
3. **Vector Search** - Semantic similarity search
4. **News Integration** - Automatic sentiment analysis
5. **Outcome Tracking** - Measures LLM accuracy
6. **Prompt Templates** - Reusable, versioned prompts

---

## Dependencies

- **Ollama** - Must be running locally
- **ChromaDB** - Vector database (auto-created)
- **DeepSeek** - Default model (deepseek-coder:33b)

---

*For questions, check the code comments or ask the team.*
