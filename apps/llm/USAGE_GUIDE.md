# LLM Module Usage Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Database Models Overview](#database-models-overview)
3. [Using the UI](#using-the-ui)
4. [Using the API](#using-the-api)
5. [Processing Documents](#processing-documents)
6. [Examples](#examples)

## Quick Start

### 1. Start Django Server
```bash
python manage.py runserver
```

### 2. Access LLM Dashboard
Navigate to: `http://localhost:8000/llm/`

### 3. Test vLLM Connection
```bash
python manage.py test_vllm --quick
```

## Database Models Overview

### All models are in `apps/data/models.py` - NO REDUNDANCY!

#### NewsArticle (Existing Model)
Stores news articles with AI analysis fields built-in.

**LLM-Enhanced Fields**:
```python
class NewsArticle(TimeStampedModel):
    # Basic fields
    title = CharField()
    content = TextField()
    source = CharField()
    published_at = DateTimeField()

    # LLM Analysis Fields (already exist!)
    llm_summary = TextField()              # AI-generated summary
    key_insights = JSONField()             # Extracted insights
    sentiment_score = FloatField()         # -1.0 to 1.0
    sentiment_label = CharField()          # POSITIVE/NEUTRAL/NEGATIVE
    sentiment_confidence = FloatField()    # 0.0 to 1.0
    market_impact = CharField()            # HIGH/MEDIUM/LOW

    # Vector storage
    embedding_stored = BooleanField()
    embedding_id = CharField()

    # Processing status
    processed = BooleanField()
    processed_at = DateTimeField()
```

#### InvestorCall (Existing Model)
Stores investor call transcripts with AI analysis.

**LLM-Enhanced Fields**:
```python
class InvestorCall(TimeStampedModel):
    # Basic fields
    company = CharField()
    symbol = CharField()
    transcript = TextField()
    call_date = DateField()

    # LLM Analysis Fields (already exist!)
    executive_summary = TextField()        # AI summary
    key_highlights = JSONField()           # Key points
    financial_metrics = JSONField()        # Extracted data
    management_tone = CharField()          # POSITIVE/NEUTRAL/NEGATIVE
    outlook = TextField()                  # Future guidance
    concerns_raised = JSONField()          # Risk factors
    trading_signal = CharField()           # BULLISH/NEUTRAL/BEARISH
    confidence_score = FloatField()

    # Processing status
    processed = BooleanField()
    processed_at = DateTimeField()
```

#### KnowledgeBase (Existing Model)
Stores processed chunks for RAG queries.

```python
class KnowledgeBase(TimeStampedModel):
    source_type = CharField()     # NEWS/CALL/REPORT/MANUAL
    source_id = IntegerField()    # ID of original document
    content_chunk = TextField()   # Text chunk
    symbols = JSONField()         # Related symbols
    embedding_id = CharField()    # Vector DB ID
    times_retrieved = IntegerField()
    relevance_score = FloatField()
```

## Using the UI

### Dashboard
`http://localhost:8000/llm/`

Shows:
- LLM connection status
- Document counts
- Recent processed documents
- Quick action buttons

### Chat Interface
`http://localhost:8000/llm/chat/`

Interactive AI assistant:
- Ask questions about markets
- Get document summaries
- Analyze trends
- Adjustable temperature (0-1)
- Adjustable max tokens (100-4000)

**Example Questions**:
- "What's the latest news about RELIANCE?"
- "Summarize the recent investor calls"
- "What are the key risks in the market?"

### News Articles
`http://localhost:8000/llm/news/`

Features:
- List all news articles
- Filter by source, symbol, processed status
- Search by title/content
- View detailed analysis

### Investor Calls
`http://localhost:8000/llm/calls/`

Features:
- List all investor calls
- Filter by symbol, call type
- Search transcripts
- View AI analysis

### Knowledge Search
`http://localhost:8000/llm/search/`

Search through processed knowledge:
- Full-text search
- View source documents
- See related symbols

## Using the API

### 1. Python Client

```python
from apps.llm.services.vllm_client import get_vllm_client
from apps.data.models import NewsArticle, InvestorCall

# Get vLLM client
client = get_vllm_client()

# Check connection
if client.is_enabled():
    print(f"Connected to {client.model}")
```

### 2. Analyze News Article

```python
# Get or create article
article = NewsArticle.objects.create(
    title="RELIANCE Reports Strong Q4 Results",
    content="RELIANCE Industries reported...",
    source="MoneyControl",
    published_at=timezone.now(),
    url="https://example.com/article"
)

# Analyze with AI
client = get_vllm_client()

# Sentiment Analysis
success, sentiment, metadata = client.analyze_sentiment(article.content)
if success:
    article.sentiment_label = sentiment['label']
    article.sentiment_score = sentiment['score']
    article.sentiment_confidence = sentiment['confidence']

# Generate Summary
success, summary, _ = client.summarize(article.content, max_length=150)
if success:
    article.llm_summary = summary

# Extract Insights
success, insights, _ = client.extract_insights(article.content, num_insights=5)
if success:
    article.key_insights = insights

# Mark as processed
article.processed = True
article.processed_at = timezone.now()
article.save()

print(f"Analysis complete!")
print(f"Sentiment: {article.sentiment_label}")
print(f"Summary: {article.llm_summary}")
print(f"Insights: {len(article.key_insights)} extracted")
```

### 3. Analyze Investor Call

```python
# Create investor call
call = InvestorCall.objects.create(
    company="RELIANCE Industries",
    symbol="RELIANCE",
    call_type="EARNINGS",
    call_date=date.today(),
    transcript="Management: We are pleased to announce...",
    quarter="Q4 FY24"
)

# Analyze
client = get_vllm_client()

# Summary
success, summary, _ = client.summarize(call.transcript, max_length=200)
call.executive_summary = summary

# Sentiment
success, sentiment, _ = client.analyze_sentiment(call.transcript)
call.management_tone = sentiment['label']
call.confidence_score = sentiment['confidence']

# Insights
success, highlights, _ = client.extract_insights(call.transcript, num_insights=5)
call.key_highlights = highlights

# Save
call.processed = True
call.processed_at = timezone.now()
call.save()
```

### 4. RAG Query (Question Answering)

```python
from apps.data.models import KnowledgeBase

# Find relevant knowledge
question = "What is RELIANCE's outlook for Q1 FY25?"

relevant = KnowledgeBase.objects.filter(
    Q(content_chunk__icontains="RELIANCE") &
    Q(content_chunk__icontains="outlook")
)[:3]

# Build context
context = "\n\n".join([kb.content_chunk for kb in relevant])

# Ask LLM
client = get_vllm_client()
success, answer, metadata = client.answer_question(question, context)

if success:
    print(f"Answer: {answer}")
    print(f"Tokens used: {metadata['usage']['total_tokens']}")
    print(f"Sources: {len(relevant)}")
```

### 5. Via HTTP API

#### Analyze Document
```bash
curl -X POST http://localhost:8000/llm/api/analyze/ \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=YOUR_SESSION" \
  -d '{
    "doc_type": "news",
    "doc_id": 1
  }'
```

Response:
```json
{
  "success": true,
  "sentiment": {
    "label": "POSITIVE",
    "score": 0.75,
    "confidence": 0.92
  },
  "summary": "RELIANCE Industries reported...",
  "insights": [
    "Net profit increased 12% YoY",
    "Revenue grew 8% to Rs 2.35 lakh crore",
    "Dividend of Rs 9 per share announced"
  ]
}
```

#### Ask Question (RAG)
```bash
curl -X POST http://localhost:8000/llm/api/ask/ \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=YOUR_SESSION" \
  -d '{
    "question": "What are the latest updates about RELIANCE?"
  }'
```

Response:
```json
{
  "success": true,
  "answer": "According to recent investor calls...",
  "sources": [
    {
      "title": "RELIANCE Q4 Results",
      "source_type": "NEWS"
    }
  ],
  "metadata": {
    "model": "Meta-Llama-3.1-70B",
    "processing_time_ms": 1250,
    "usage": {
      "total_tokens": 450
    }
  }
}
```

## Processing Documents

### Django Admin
1. Go to `http://localhost:8000/admin/`
2. Navigate to **Data** → **News articles** or **Investor calls**
3. Add new document
4. Use API or admin action to process with LLM

### Management Command
```python
# Create a custom command
# apps/llm/management/commands/process_documents.py

from django.core.management.base import BaseCommand
from apps.data.models import NewsArticle
from apps.llm.services.vllm_client import get_vllm_client

class Command(BaseCommand):
    def handle(self, *args, **options):
        client = get_vllm_client()

        # Process unprocessed news
        articles = NewsArticle.objects.filter(processed=False)[:10]

        for article in articles:
            # Analyze
            sentiment, _ = client.analyze_sentiment(article.content)
            summary, _ = client.summarize(article.content)
            insights, _ = client.extract_insights(article.content)

            # Update
            article.sentiment_label = sentiment['label']
            article.llm_summary = summary
            article.key_insights = insights
            article.processed = True
            article.save()

            self.stdout.write(f"Processed: {article.title}")
```

Run:
```bash
python manage.py process_documents
```

## Examples

### Example 1: Process Recent News
```python
from django.utils import timezone
from datetime import timedelta
from apps.data.models import NewsArticle
from apps.llm.services.vllm_client import get_vllm_client

# Get today's news
today = timezone.now().date()
articles = NewsArticle.objects.filter(
    published_at__date=today,
    processed=False
)

client = get_vllm_client()

for article in articles:
    print(f"Processing: {article.title}")

    # Analyze
    sentiment, _ = client.analyze_sentiment(article.content)
    summary, _ = client.summarize(article.content, max_length=100)
    insights, _ = client.extract_insights(article.content, num_insights=3)

    # Save
    article.sentiment_label = sentiment.get('label')
    article.sentiment_score = sentiment.get('score')
    article.llm_summary = summary
    article.key_insights = insights
    article.processed = True
    article.processed_at = timezone.now()
    article.save()

    print(f"  ✓ Sentiment: {article.sentiment_label}")
    print(f"  ✓ Insights: {len(article.key_insights)}")
```

### Example 2: Find Positive News for Symbol
```python
from apps.data.models import NewsArticle

# Find positive news about RELIANCE
positive_news = NewsArticle.objects.filter(
    symbols_mentioned__contains=['RELIANCE'],
    sentiment_label='POSITIVE',
    processed=True
).order_by('-published_at')[:5]

for article in positive_news:
    print(f"\n{article.title}")
    print(f"Sentiment: {article.sentiment_score:.2f}")
    print(f"Summary: {article.llm_summary}")
    print(f"Insights:")
    for insight in article.key_insights:
        print(f"  - {insight}")
```

### Example 3: Interactive Chat
```python
from apps.llm.services.vllm_client import get_vllm_client

client = get_vllm_client()
messages = []

while True:
    user_input = input("You: ")
    if user_input.lower() in ['exit', 'quit']:
        break

    messages.append({
        "role": "user",
        "content": user_input
    })

    success, response, metadata = client.chat(
        messages=messages,
        temperature=0.7
    )

    if success:
        print(f"AI: {response}")
        messages.append({
            "role": "assistant",
            "content": response
        })
    else:
        print(f"Error: {metadata.get('error')}")
```

### Example 4: Bulk Analysis
```python
from apps.data.models import NewsArticle, InvestorCall
from apps.llm.services.vllm_client import get_vllm_client
from django.db import transaction

def bulk_analyze_documents(doc_type='news', limit=50):
    """Process multiple documents efficiently"""
    client = get_vllm_client()

    if doc_type == 'news':
        docs = NewsArticle.objects.filter(processed=False)[:limit]
    else:
        docs = InvestorCall.objects.filter(processed=False)[:limit]

    processed_count = 0

    with transaction.atomic():
        for doc in docs:
            try:
                text = doc.content if doc_type == 'news' else doc.transcript

                # Analyze
                sentiment, _ = client.analyze_sentiment(text)
                summary, _ = client.summarize(text, max_length=150)
                insights, _ = client.extract_insights(text, num_insights=5)

                # Update fields based on type
                if doc_type == 'news':
                    doc.sentiment_label = sentiment.get('label')
                    doc.sentiment_score = sentiment.get('score')
                    doc.llm_summary = summary
                    doc.key_insights = insights
                else:
                    doc.management_tone = sentiment.get('label')
                    doc.confidence_score = sentiment.get('confidence')
                    doc.executive_summary = summary
                    doc.key_highlights = insights

                doc.processed = True
                doc.processed_at = timezone.now()
                doc.save()

                processed_count += 1
                print(f"Processed {processed_count}/{len(docs)}")

            except Exception as e:
                print(f"Error processing {doc.id}: {e}")
                continue

    return processed_count

# Usage
count = bulk_analyze_documents('news', limit=10)
print(f"Processed {count} documents")
```

## Configuration

### Environment Variables
```bash
# .env file
VLLM_HOST=http://27.107.134.179:8000/v1
VLLM_MODEL=hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4
VLLM_API_KEY=not-needed
```

### Django Settings
No additional settings needed! The LLM module uses existing database models from `apps.data`.

## Testing

```bash
# Test vLLM connection and features
python manage.py test_vllm

# Quick test
python manage.py test_vllm --quick

# Test specific component
python manage.py test_vllm --component sentiment
```

## Troubleshooting

### LLM Not Connected
1. Check if vLLM server is running
2. Verify `VLLM_HOST` in environment
3. Test with: `python manage.py test_vllm`

### Slow Processing
- Lower `max_tokens` parameter
- Increase `temperature` for faster responses
- Process in batches

### Memory Issues
- Process documents in smaller batches
- Use pagination in queries
- Clean up old processed data

## Summary

✅ **All models already exist in `apps/data/models.py`**
✅ **No redundant models created**
✅ **LLM analysis fields already in database**
✅ **Full UI and API available**
✅ **Ready to use immediately**

Access the dashboard at: `http://localhost:8000/llm/`
