# LLM Module Architecture

## Overview
The LLM module integrates AI capabilities into mCube Trading System by **reusing existing database models** from `apps.data.models`. No redundant models were created.

## Existing Models (REUSED)

### 1. NewsArticle Model (`apps/data/models.py`)
**Purpose**: Store news articles with LLM-powered analysis

**Fields for LLM Integration**:
- `llm_summary` - AI-generated summary
- `key_insights` - Extracted key points (JSON)
- `sentiment_score` - Sentiment analysis (-1 to 1)
- `sentiment_label` - POSITIVE/NEUTRAL/NEGATIVE
- `sentiment_confidence` - Confidence score
- `market_impact` - HIGH/MEDIUM/LOW
- `embedding_stored` - Flag for vector storage
- `embedding_id` - ChromaDB reference
- `processed` - Processing status
- `processed_at` - Processing timestamp

**LLM Operations**:
```python
# Analyze news article
vllm_client = get_vllm_client()
sentiment_data, _ = vllm_client.analyze_sentiment(article.content)
summary, _ = vllm_client.summarize(article.content)
insights, _ = vllm_client.extract_insights(article.content)

# Update article
article.sentiment_label = sentiment_data['label']
article.llm_summary = summary
article.key_insights = insights
article.processed = True
article.save()
```

### 2. InvestorCall Model (`apps/data/models.py`)
**Purpose**: Store investor call transcripts with AI analysis

**Fields for LLM Integration**:
- `executive_summary` - AI-generated summary
- `key_highlights` - Key points (JSON)
- `financial_metrics` - Extracted financial data (JSON)
- `management_tone` - POSITIVE/NEUTRAL/NEGATIVE
- `outlook` - Future guidance text
- `concerns_raised` - Risk factors (JSON)
- `trading_signal` - BULLISH/NEUTRAL/BEARISH
- `confidence_score` - Signal confidence
- `embedding_stored` - Flag for vector storage
- `embedding_id` - ChromaDB reference
- `processed` - Processing status

**LLM Operations**:
```python
# Analyze investor call
summary, _ = vllm_client.summarize(call.transcript, max_length=200)
sentiment, _ = vllm_client.analyze_sentiment(call.transcript)
insights, _ = vllm_client.extract_insights(call.transcript)

# Update call
call.executive_summary = summary
call.key_highlights = insights
call.management_tone = sentiment['label']
call.processed = True
call.save()
```

### 3. KnowledgeBase Model (`apps/data/models.py`)
**Purpose**: Store processed chunks for RAG (Retrieval Augmented Generation)

**Fields**:
- `source_type` - NEWS/CALL/REPORT/MANUAL
- `source_id` - FK to original document
- `content_chunk` - Text chunk for retrieval
- `chunk_index` - Position in document
- `metadata` - Additional context (JSON)
- `symbols` - Related stock symbols (JSON)
- `embedding_id` - ChromaDB vector ID
- `times_retrieved` - Usage tracking
- `relevance_score` - Average relevance

**LLM Operations**:
```python
# RAG query
relevant_chunks = KnowledgeBase.objects.filter(
    content_chunk__icontains=question
)[:3]

context = "\n\n".join([chunk.content_chunk for chunk in relevant_chunks])
answer, _ = vllm_client.answer_question(question, context)
```

### 4. Other Reused Models

#### MarketData (`apps/data/models.py`)
- OHLCV data for context in LLM queries
- No modifications needed

#### ContractData (`apps/data/models.py`)
- F&O contract information
- Used for providing context to LLM

#### Event (`apps/data/models.py`)
- Economic calendar events
- Referenced in LLM analysis

## LLM-Specific Components (NEW)

### 1. vLLM Client (`apps/llm/services/vllm_client.py`)
**Purpose**: Interface to vLLM server using OpenAI-compatible API

**Features**:
- Chat completions
- Text generation
- Sentiment analysis
- Summarization
- Insight extraction
- Question answering (RAG)

**Configuration**:
```python
VLLM_HOST = "http://27.107.134.179:8000/v1"
VLLM_MODEL = "hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4"
```

### 2. Views (`apps/llm/views.py`)
**Purpose**: UI endpoints for LLM features

**Endpoints**:
- `/llm/` - Dashboard (stats, recent docs)
- `/llm/chat/` - Interactive AI chat
- `/llm/news/` - List news articles
- `/llm/news/<id>/` - View news with analysis
- `/llm/calls/` - List investor calls
- `/llm/calls/<id>/` - View call with analysis
- `/llm/search/` - Search knowledge base
- `/llm/api/analyze/` - Analyze document via API
- `/llm/api/ask/` - RAG query via API

### 3. Templates
- `llm/dashboard.html` - Main dashboard
- `llm/chat.html` - AI chat interface

### 4. LLM-Specific Models (`apps/llm/models.py`)
These are for LLM **system management**, not data storage:

- `LLMPrompt` - Prompt templates (system use)
- `LLMValidation` - Trade validation logs (separate use case)

## Data Flow

### 1. Document Processing Flow
```
User uploads document
    ↓
Save to NewsArticle/InvestorCall (existing models)
    ↓
Process with vLLM:
  - Generate summary
  - Extract sentiment
  - Extract insights
    ↓
Update same record with LLM results
    ↓
Create KnowledgeBase chunks for RAG
```

### 2. RAG Query Flow
```
User asks question
    ↓
Search KnowledgeBase for relevant chunks
    ↓
Build context from chunks
    ↓
Query vLLM with context
    ↓
Return answer with sources
```

## No Redundancy!

✅ **NewsArticle** - Reused, extended with LLM fields
✅ **InvestorCall** - Reused, extended with LLM fields
✅ **KnowledgeBase** - Reused for RAG
✅ **MarketData** - Reused for context
✅ **Event** - Reused for context
✅ **ContractData** - Reused for F&O context

❌ **No duplicate models created**
❌ **No redundant storage**
❌ **All LLM analysis stored in existing models**

## Database Tables Used

From `apps/data/models.py`:
- `news_articles` - News with LLM analysis
- `investor_calls` - Calls with LLM analysis
- `knowledge_base` - RAG chunks
- `market_data` - Price data for context
- `events` - Calendar for context
- `contract_data` - F&O contracts

From `apps/llm/models.py`:
- `llm_prompts` - System prompt templates
- `llm_validations` - Trade validation history (separate feature)

## API Usage Example

```python
from apps.llm.services.vllm_client import get_vllm_client
from apps.data.models import NewsArticle

# Get client
client = get_vllm_client()

# Analyze news
article = NewsArticle.objects.get(id=1)

# Sentiment
success, sentiment, _ = client.analyze_sentiment(article.content)
article.sentiment_label = sentiment['label']
article.sentiment_score = sentiment['score']

# Summary
success, summary, _ = client.summarize(article.content, max_length=150)
article.llm_summary = summary

# Insights
success, insights, _ = client.extract_insights(article.content, num_insights=5)
article.key_insights = insights

# Mark as processed
article.processed = True
article.save()
```

## Migration Status

All required fields already exist in the database:
- ✅ `NewsArticle` - All LLM fields present
- ✅ `InvestorCall` - All LLM fields present
- ✅ `KnowledgeBase` - All fields present
- ✅ No new migrations needed for data storage

## Future Enhancements

1. **Vector Search** - Implement proper embedding search with ChromaDB/FAISS
2. **Batch Processing** - Process multiple documents in parallel
3. **Advanced RAG** - Hybrid search (vector + keyword)
4. **Document Upload** - UI for uploading PDFs, Word docs
5. **Research Reports** - Add ResearchReport model if needed
6. **Scheduled Analysis** - Celery tasks for automatic processing
