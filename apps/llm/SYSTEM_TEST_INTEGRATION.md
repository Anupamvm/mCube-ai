# LLM System Test Integration

## Overview
Comprehensive vLLM tests have been added to the system test page at `http://127.0.0.1:8000/system/test/` to give you confidence that the LLM is working fine and responding smartly.

## Access the Tests
1. Start Django server: `python manage.py runserver`
2. Navigate to: `http://127.0.0.1:8000/system/test/`
3. Look for the **"LLM Integration"** section

## Test Coverage (13 Tests)

### 1. Infrastructure Tests

#### Test 1: vLLM Server Connection ✓
- **What it tests:** Connection to vLLM server at http://27.107.134.179:8000/v1
- **Success criteria:** Server responds and connection is established
- **Output:** Shows base URL and model name
- **Example:** `Connected to http://27.107.134.179:8000/v1 | Model: hugging-quants/Meta-Llama-3.1-70B...`

### 2. Core LLM Capabilities

#### Test 2: Text Generation ✓
- **What it tests:** Basic text generation with simple prompt
- **Test prompt:** "What is 2+2? Answer with just the number."
- **Success criteria:** Gets valid response with token count and processing time
- **Output:** Response text, token count, processing time in ms
- **Example:** `Response: "4" | 56 tokens in 438ms`

#### Test 3: Chat Completion ✓
- **What it tests:** Multi-turn conversation capability
- **Test prompt:** System prompt + "Say 'test passed' in one sentence."
- **Success criteria:** Chat API works with proper message format
- **Output:** Response text and token count
- **Example:** `Chat working | Response: "The test has successfully passed..." | 78 tokens`

### 3. AI Analysis Features

#### Test 4: Sentiment Analysis ✓
- **What it tests:** Ability to analyze sentiment of financial text
- **Test text:** "The stock market rallied today with strong gains across all sectors."
- **Success criteria:** Returns label (POSITIVE/NEUTRAL/NEGATIVE), score (-1 to 1), and confidence (0-1)
- **Output:** Sentiment label, score, and confidence
- **Example:** `Label: POSITIVE | Score: 0.85 | Confidence: 0.92`

#### Test 5: Text Summarization ✓
- **What it tests:** Ability to summarize long financial text
- **Test text:** RELIANCE Q4 results paragraph (3 sentences)
- **Success criteria:** Generates concise summary
- **Output:** Word count and summary preview
- **Example:** `Summary generated (25 words): "RELIANCE reported 15% revenue growth with multiple contracts..."`

#### Test 6: Insight Extraction ✓
- **What it tests:** Ability to extract key insights from text
- **Test text:** TCS earnings report with multiple data points
- **Success criteria:** Extracts 3 structured insights
- **Output:** Number of insights and first insight preview
- **Example:** `Extracted 3 insights | First: "Revenue growth of 15% YoY demonstrates strong..."`

#### Test 7: Question Answering (RAG) ✓
- **What it tests:** Retrieval-Augmented Generation capability
- **Test context:** RELIANCE Q4 profit and dividend information
- **Test question:** "What was the net profit?"
- **Success criteria:** Correctly answers based on context
- **Output:** Answer text
- **Example:** `Answer: "RELIANCE Industries reported Q4 net profit of Rs 19,299 crore..."`

### 4. Database Integration Tests

#### Test 8: News Articles (LLM Ready) ✓
- **What it tests:** NewsArticle model integration with LLM fields
- **Success criteria:** Shows total, processed, and sentiment-analyzed articles
- **Output:** Document statistics
- **Example:** `Total: 150 | Processed: 45 | With Sentiment: 40`

#### Test 9: Investor Calls (LLM Ready) ✓
- **What it tests:** InvestorCall model integration with LLM fields
- **Success criteria:** Shows total, processed, and summarized calls
- **Output:** Document statistics
- **Example:** `Total: 25 | Processed: 10 | With Summary: 10`

#### Test 10: Knowledge Base (RAG) ✓
- **What it tests:** KnowledgeBase model for RAG storage
- **Success criteria:** Shows total chunks and breakdown by source type
- **Output:** Chunk statistics
- **Example:** `Total Chunks: 500 | News: 350 | Calls: 150`

### 5. System Features Tests

#### Test 11: LLM Trade Validations ✓
- **What it tests:** LLMValidation model for trade decisions
- **Success criteria:** Shows validation count and latest symbol
- **Output:** Validation statistics
- **Example:** `Found 12 validations | Latest: RELIANCE`

#### Test 12: LLM Prompt Templates ✓
- **What it tests:** LLMPrompt model for reusable prompts
- **Success criteria:** Shows total and active prompt templates
- **Output:** Prompt statistics
- **Example:** `Total: 5 | Active: 3`

### 6. Performance Tests

#### Test 13: LLM Performance ✓
- **What it tests:** Response time and latency
- **Test:** Simple "Say hello" prompt
- **Success criteria:**
  - Good: < 1000ms
  - Acceptable: < 2000ms
  - Slow: > 2000ms
- **Output:** Response time with quality indicator
- **Example:** `Response time: 450ms | Good`

## Test Results Display

### Status Indicators
- **✓ PASS** (Green): Test completed successfully
- **✗ FAIL** (Red): Test failed with error message
- **⊘ SKIP** (Yellow): Test skipped (usually when vLLM not connected)
- **⚠ WARNING** (Orange): Test passed but with performance concerns

### Information Shown for Each Test
1. **Test Name:** What is being tested
2. **Status:** Pass/Fail/Skip/Warning
3. **Message:** Detailed result with metrics

## Example Output

When you visit the system test page, you'll see something like this in the **LLM Integration** section:

```
LLM Integration (13 tests, 13 passed)

✓ vLLM Server Connection
  Connected to http://27.107.134.179:8000/v1 | Model: hugging-quants/Meta-Llama-3.1-70B...

✓ Text Generation
  Response: "4" | 56 tokens in 438ms

✓ Chat Completion
  Chat working | Response: "The test has successfully passed..." | 78 tokens

✓ Sentiment Analysis
  Label: POSITIVE | Score: 0.85 | Confidence: 0.92

✓ Text Summarization
  Summary generated (25 words): "RELIANCE reported 15% revenue growth..."

✓ Insight Extraction
  Extracted 3 insights | First: "Revenue growth of 15% YoY..."

✓ Question Answering (RAG)
  Answer: "RELIANCE Industries reported Q4 net profit of Rs 19,299..."

✓ News Articles (LLM Ready)
  Total: 150 | Processed: 45 | With Sentiment: 40

✓ Investor Calls (LLM Ready)
  Total: 25 | Processed: 10 | With Summary: 10

✓ Knowledge Base (RAG)
  Total Chunks: 500 | News: 350 | Calls: 150

✓ LLM Trade Validations
  Found 12 validations | Latest: RELIANCE

✓ LLM Prompt Templates
  Total: 5 | Active: 3

✓ LLM Performance
  Response time: 450ms | Good
```

## What Each Test Proves

### Intelligence Tests
1. **Text Generation** → LLM can generate coherent responses
2. **Chat Completion** → LLM can handle conversations
3. **Sentiment Analysis** → LLM understands financial sentiment
4. **Summarization** → LLM can condense information
5. **Insight Extraction** → LLM can identify key points
6. **Question Answering** → LLM can answer based on context

### Data Integration Tests
7. **News Articles** → Database integration working
8. **Investor Calls** → Database integration working
9. **Knowledge Base** → RAG storage working

### System Tests
10. **Trade Validations** → Trade analysis feature ready
11. **Prompt Templates** → Template system working
12. **Performance** → System performance acceptable

### Infrastructure Test
13. **Server Connection** → vLLM server accessible and responding

## Confidence Indicators

After running these tests, you can be confident that:

✅ **LLM is connected** - Server connection test passes
✅ **LLM is smart** - All intelligence tests (sentiment, summary, insights, QA) pass
✅ **LLM is fast** - Performance test shows acceptable response times
✅ **LLM is integrated** - Database models working with LLM fields
✅ **LLM is production-ready** - All core features tested and working

## Troubleshooting

### If Tests Fail

**vLLM Server Connection fails:**
- Check if vLLM server is running at http://27.107.134.179:8000/v1
- Verify network connectivity
- Check environment variables (VLLM_HOST, VLLM_MODEL)

**Intelligence tests fail:**
- Check vLLM server connection first
- Verify model is loaded correctly
- Check vLLM server logs for errors

**Database tests show 0 documents:**
- Normal if no documents have been added yet
- Add test documents via Django admin or API
- Process documents using the LLM

**Performance test shows "Slow":**
- Normal for first request (cold start)
- Check vLLM server load
- May improve with subsequent requests

## Manual Verification

Beyond the automated tests, you can manually verify LLM intelligence by:

1. **Using the Chat Interface:**
   - Go to http://localhost:8000/llm/chat/
   - Ask complex questions about markets
   - Verify responses are coherent and relevant

2. **Processing a Document:**
   - Add a news article via Django admin
   - Use the analyze API to process it
   - Check sentiment, summary, and insights

3. **RAG Query:**
   - Add documents with knowledge
   - Use the search/ask API
   - Verify answers reference correct documents

## Next Steps

Once all tests pass, you can:
1. Start processing real documents
2. Use the chat interface for market analysis
3. Integrate LLM analysis into trading decisions
4. Build advanced RAG workflows
5. Create custom prompts for specific use cases

## Test Maintenance

The tests will automatically run every time you visit the system test page. They provide:
- **Real-time status** of LLM integration
- **Performance metrics** for monitoring
- **Document statistics** to track usage
- **Confidence** that the system is working

No manual test execution needed - just refresh the page!
