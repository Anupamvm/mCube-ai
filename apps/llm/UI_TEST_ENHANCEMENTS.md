# LLM Test UI Enhancements

## Overview
Enhanced the system test page (`http://127.0.0.1:8000/system/test/`) with detailed test descriptions and individual trigger buttons for each LLM test.

## What Was Added

### 1. Detailed Test Descriptions
Every LLM test now includes:
- **Visual test name** with emoji icon (e.g., "🔌 vLLM Server Connection")
- **Inline description** explaining what the test does
- **Success/failure indicators** (✓ pass, ✗ fail, ⊘ skip, ⚠ warning)
- **Contextual information** about what success means

### 2. Individual Test Triggers
Each test has its own "Run Test" button that:
- Tests can be triggered individually without refreshing the entire page
- Immediate feedback via JSON response
- Auto-reload after successful test execution
- CSRF-protected POST requests

### 3. New Test Trigger Endpoints
Created dedicated URLs for each test type:
- `/llm/test/connection/` - Test vLLM server connection
- `/llm/test/generation/` - Test text generation
- `/llm/test/sentiment/` - Test sentiment analysis
- `/llm/test/summarization/` - Test text summarization
- `/llm/test/insights/` - Test insight extraction
- `/llm/test/rag/` - Test question answering (RAG)
- `/llm/test/performance/` - Test response time
- `/llm/test/all/` - Run all tests at once

## How to Use

### Viewing Test Details

1. **Start the server:**
   ```bash
   python manage.py runserver
   ```

2. **Navigate to system test page:**
   ```
   http://127.0.0.1:8000/system/test/
   ```

3. **Find the "LLM Integration" section** - scroll down to see all 13 tests

### Understanding Each Test

Each test now displays:

```
🔌 vLLM Server Connection                           [🔄 Test Connection]
✓ Connected to http://27.107.134.179:8000/v1 | Model: hugging-quants...

Tests: Connection to vLLM server.
Success means: Your 70B Llama model is accessible and ready.
```

The description box (in light blue) explains:
- **What it tests** - The specific capability being verified
- **How it works** - The technical process
- **What success means** - Interpretation of results
- **Expected output** - What you should see

### Triggering Individual Tests

Click any **"🔄 Test Connection"** or **"🔄 Run Test"** button to:

1. **Trigger that specific test** without running all tests
2. **See immediate feedback** - button shows "Running..." during execution
3. **View results** - page reloads with updated test status
4. **Get detailed output** - JSON response with full details

### Test Descriptions

#### 🔌 Test 1: vLLM Server Connection
**Description:**
- Tests: Connection to vLLM server running your AI model
- How: Connects to http://27.107.134.179:8000/v1 and verifies availability
- Success means: Your 70B Llama model is accessible and ready to process requests
- If fails: Check if vLLM server is running, network connectivity, firewall settings

#### 💬 Test 2: Text Generation
**Description:**
- Tests: Basic text generation capability (foundation of all AI responses)
- How: Sends simple math question "What is 2+2?" with low temperature for deterministic response
- Success means: LLM can understand prompts and generate coherent text
- Look for: Correct answer processed in under 1 second

#### 🗨️ Test 3: Chat Completion
**Description:**
- Tests: Multi-turn conversation capability with system instructions
- How: Sets system context "You are a helpful assistant" and tests message formatting
- Success means: LLM can maintain context, follow instructions, participate in conversations
- Real-world use: Powers the chat interface for interactive AI assistance

#### 😊 Test 4: Sentiment Analysis
**Description:**
- Tests: Ability to detect and quantify sentiment in financial text
- How: Analyzes "The stock market rallied..." and returns structured JSON with label, score, confidence
- Success means: LLM correctly identifies positive sentiment with high confidence
- Real-world use: Analyzes news and investor calls to gauge market sentiment

#### 📝 Test 5: Text Summarization
**Description:**
- Tests: Ability to condense long text into concise summaries
- How: Provides 3-sentence RELIANCE Q4 paragraph, requests ~30 word summary
- Success means: LLM extracts and compresses key information while maintaining accuracy
- Real-world use: Summarizes lengthy articles, calls, and reports for quick review

#### 💡 Test 6: Insight Extraction
**Description:**
- Tests: Ability to identify and extract key insights from financial data
- How: Provides TCS paragraph with multiple data points, extracts top 3 insights
- Success means: LLM identifies most important points (15% growth, new deals, attrition)
- Real-world use: Automatically extracts trading-relevant insights for quick decisions

#### ❓ Test 7: Question Answering (RAG)
**Description:**
- Tests: Retrieval-Augmented Generation - answering from context
- How: Provides RELIANCE Q4 context, asks "What was the net profit?"
- Success means: LLM correctly cites "Rs 19,299 crore" from provided context
- Real-world use: Powers knowledge base search with contextual answers

#### 📰 Test 8: News Articles (LLM Ready)
**Description:**
- Tests: Database integration for NewsArticle model
- Shows: Total articles, processed articles, articles with sentiment
- Success means: NewsArticle model properly set up with all LLM fields
- Fields: llm_summary, key_insights, sentiment_label, sentiment_score, processed

#### 📞 Test 9: Investor Calls (LLM Ready)
**Description:**
- Tests: Database integration for InvestorCall model
- Shows: Total calls, processed calls, calls with summaries
- Success means: InvestorCall model integrated with LLM capabilities
- Fields: executive_summary, key_highlights, management_tone, trading_signal

#### 📚 Test 10: Knowledge Base (RAG Storage)
**Description:**
- Tests: KnowledgeBase model for RAG document chunks
- Shows: Total chunks, breakdown by source (NEWS/CALL/REPORT)
- Success means: RAG system has processed documents into searchable chunks
- How it works: Long documents split into chunks for efficient retrieval

#### 📊 Test 11: LLM Trade Validations
**Description:**
- Tests: LLMValidation model storing AI-powered trade analysis
- Shows: Total validations, most recent symbol analyzed
- Success means: System can track LLM recommendations and performance
- Use case: LLM validates trades based on market data, news, sentiment

#### 📋 Test 12: LLM Prompt Templates
**Description:**
- Tests: LLMPrompt model storing reusable prompt templates
- Shows: Total templates, number of active templates
- Success means: System has predefined prompts for common tasks
- Why it matters: Consistent prompts = consistent AI responses and better tracking

#### ⚡ Test 13: LLM Performance
**Description:**
- Tests: Response time and latency of AI model
- How: Sends simple "Say hello" prompt and measures total time
- Evaluation: Good (<1s), Acceptable (<2s), Slow (>2s)
- Success means: LLM responds fast enough for real-time trading decisions
- Note: First request may be slower (cold start)

## Technical Details

### Files Created/Modified

**New Files:**
1. `apps/llm/test_descriptions.py` - Detailed descriptions for each test
2. `apps/llm/test_views.py` - Individual test trigger endpoints
3. `apps/llm/UI_TEST_ENHANCEMENTS.md` - This documentation

**Modified Files:**
1. `apps/llm/urls.py` - Added test trigger URLs
2. `apps/core/views.py` - Enhanced test_llm() function with descriptions and trigger buttons
3. `templates/core/system_test.html` - Added description display and skip status styling

### Test Trigger Flow

```
User clicks "Run Test" button
    ↓
POST request to /llm/test/{test_name}/
    ↓
test_views.trigger_{test_name}_test() executes
    ↓
Returns JSON response:
{
    "success": true/false,
    "status": "pass/fail/skip/warning",
    "message": "Test result message",
    "details": { ... additional data ... }
}
    ↓
Page reloads to show updated results
```

### API Response Format

All test triggers return consistent JSON:

```json
{
  "success": true,
  "status": "pass",
  "message": "✓ Connected to http://27.107.134.179:8000/v1 | Model: Meta-Llama-3.1-70B...",
  "details": {
    "base_url": "http://27.107.134.179:8000/v1",
    "model": "hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4"
  }
}
```

## Benefits

### For Understanding
- ✅ **Clear explanations** of what each test does
- ✅ **Visual feedback** with icons and status indicators
- ✅ **Inline descriptions** - no need to read external docs
- ✅ **Expected outcomes** documented for each test

### For Testing
- ✅ **Individual triggers** - test specific features without full reload
- ✅ **Quick feedback** - see results immediately
- ✅ **Detailed output** - JSON response with all details
- ✅ **Auto-refresh** - page updates with latest results

### For Confidence
- ✅ **13 comprehensive tests** covering all LLM capabilities
- ✅ **Real test data** - uses actual prompts and responses
- ✅ **Performance metrics** - token counts, response times
- ✅ **Database verification** - confirms models are properly integrated

## Example Usage Scenarios

### Scenario 1: Verify LLM is Working
1. Navigate to `/system/test/`
2. Look for "LLM Integration" section
3. Check if "🔌 vLLM Server Connection" shows ✓
4. If ✗, click "🔄 Test Connection" to retry
5. Review description to understand the issue

### Scenario 2: Test Sentiment Analysis
1. Find "😊 Sentiment Analysis" test
2. Read description to understand what it tests
3. Click "🔄 Run Test" to execute
4. Check result: Should show POSITIVE with high confidence
5. Review detailed JSON response

### Scenario 3: Check Performance
1. Find "⚡ LLM Performance" test
2. Note current response time
3. Click "🔄 Run Test" to measure again
4. Compare: Good (<1s), Acceptable (<2s), Slow (>2s)
5. If slow, check vLLM server load

### Scenario 4: Verify Database Integration
1. Check tests 8-10 (News, Calls, Knowledge Base)
2. See counts of documents in database
3. Verify processed counts are increasing
4. Confirm LLM fields are being populated

## Troubleshooting

### Test Shows "Skip"
- **Reason:** vLLM server not connected
- **Fix:** Check Test 1 (Connection) first
- **Action:** Click "🔄 Test Connection" to retry

### Test Shows "Fail"
- **Reason:** Test execution failed
- **Details:** Check message for error details
- **Action:** Click "🔄 Run Test" to retry
- **Help:** Review description for common issues

### Slow Performance
- **Normal:** First request is slower (cold start)
- **Improve:** Subsequent requests are faster
- **Check:** vLLM server load and resources
- **Action:** Click "🔄 Run Test" again

### No Trigger Button
- **Reason:** Some tests are info-only (like database counts)
- **Note:** Tests 8-12 show statistics, no trigger needed
- **Alternative:** Add documents via admin/API to see changes

## Next Steps

After all tests pass:

1. **Use the Chat Interface:**
   - Go to `/llm/chat/`
   - Ask complex market questions
   - Verify intelligent responses

2. **Process Documents:**
   - Add news articles via Django admin
   - Use `/llm/api/analyze/` to process
   - Check sentiment, summary, insights

3. **Build RAG Workflows:**
   - Add documents to knowledge base
   - Use `/llm/api/ask/` for Q&A
   - Verify contextual answers

4. **Monitor Performance:**
   - Regularly check performance test
   - Track response times
   - Optimize if needed

## Summary

✅ **13 comprehensive tests** - All LLM capabilities covered
✅ **Detailed descriptions** - Understand what each test does
✅ **Individual triggers** - Test features independently
✅ **Visual feedback** - Icons, colors, status indicators
✅ **Real-time results** - Immediate test execution
✅ **Complete documentation** - Know what success means

**Access Now:** `http://127.0.0.1:8000/system/test/` → Scroll to "LLM Integration" section
