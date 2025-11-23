"""
LLM Test Descriptions

Detailed descriptions for each LLM test to help users understand what's being tested
"""

TEST_DESCRIPTIONS = {
    'vllm_connection': {
        'name': 'vLLM Server Connection',
        'description': '''
            <strong>What it tests:</strong> Verifies connection to the vLLM server running your AI model.
            <br><br>
            <strong>How it works:</strong>
            <ul>
                <li>Connects to http://27.107.134.179:8000/v1</li>
                <li>Attempts to initialize the OpenAI-compatible client</li>
                <li>Verifies the server responds and is ready to accept requests</li>
            </ul>
            <br>
            <strong>What success means:</strong> Your 70B parameter Llama model is accessible and ready to process requests.
            <br><br>
            <strong>If it fails:</strong> Check if the vLLM server is running, network connectivity, or firewall settings.
        ''',
        'expected_output': 'Server URL and model name (hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4)'
    },

    'text_generation': {
        'name': 'Text Generation',
        'description': '''
            <strong>What it tests:</strong> Basic text generation capability - the foundation of all AI responses.
            <br><br>
            <strong>How it works:</strong>
            <ul>
                <li>Sends a simple math question: "What is 2+2?"</li>
                <li>Uses low temperature (0.1) for deterministic response</li>
                <li>Limited to 10 tokens for quick execution</li>
                <li>Measures response time and token usage</li>
            </ul>
            <br>
            <strong>What success means:</strong> The LLM can understand prompts and generate coherent text responses.
            <br><br>
            <strong>What to look for:</strong> Response should be "4" or "The answer is 4", processed in under 1 second.
        ''',
        'expected_output': 'Correct answer with token count (typically 50-60 tokens) and response time (<500ms)'
    },

    'chat_completion': {
        'name': 'Chat Completion',
        'description': '''
            <strong>What it tests:</strong> Multi-turn conversation capability with system instructions.
            <br><br>
            <strong>How it works:</strong>
            <ul>
                <li>Sets up system context: "You are a helpful assistant"</li>
                <li>Sends user message asking for confirmation phrase</li>
                <li>Tests if LLM can follow system instructions</li>
                <li>Verifies proper message formatting</li>
            </ul>
            <br>
            <strong>What success means:</strong> The LLM can maintain context, follow instructions, and participate in conversations.
            <br><br>
            <strong>Real-world use:</strong> This is how the chat interface works - essential for interactive AI assistance.
        ''',
        'expected_output': 'Natural language response confirming the test passed, with token count'
    },

    'sentiment_analysis': {
        'name': 'Sentiment Analysis',
        'description': '''
            <strong>What it tests:</strong> Ability to detect and quantify sentiment in financial text.
            <br><br>
            <strong>How it works:</strong>
            <ul>
                <li>Provides sample text: "The stock market rallied today with strong gains across all sectors"</li>
                <li>Asks LLM to analyze sentiment and return structured JSON</li>
                <li>Expects: label (POSITIVE/NEUTRAL/NEGATIVE), score (-1 to 1), confidence (0 to 1)</li>
            </ul>
            <br>
            <strong>What success means:</strong> LLM correctly identifies positive sentiment with high confidence.
            <br><br>
            <strong>Real-world use:</strong> Analyzes news articles and investor calls to gauge market sentiment and trading opportunities.
        ''',
        'expected_output': 'Label: POSITIVE, Score: 0.7-0.9, Confidence: 0.85-0.95'
    },

    'summarization': {
        'name': 'Text Summarization',
        'description': '''
            <strong>What it tests:</strong> Ability to condense long text into concise summaries.
            <br><br>
            <strong>How it works:</strong>
            <ul>
                <li>Provides 3-sentence paragraph about RELIANCE Q4 results</li>
                <li>Asks for summary in ~30 words</li>
                <li>Checks if key information is preserved</li>
                <li>Verifies summary is actually shorter than original</li>
            </ul>
            <br>
            <strong>What success means:</strong> LLM can extract and compress key information while maintaining accuracy.
            <br><br>
            <strong>Real-world use:</strong> Summarizes lengthy news articles, earnings calls, and research reports for quick review.
        ''',
        'expected_output': 'Concise summary (20-35 words) highlighting revenue growth and contracts'
    },

    'insight_extraction': {
        'name': 'Insight Extraction',
        'description': '''
            <strong>What it tests:</strong> Ability to identify and extract key insights from financial data.
            <br><br>
            <strong>How it works:</strong>
            <ul>
                <li>Provides paragraph about TCS with multiple data points (revenue, deals, attrition, guidance)</li>
                <li>Asks LLM to extract top 3 insights in structured format</li>
                <li>Expects JSON array of insight strings</li>
            </ul>
            <br>
            <strong>What success means:</strong> LLM identifies the most important points: 15% growth, new deals, reduced attrition.
            <br><br>
            <strong>Real-world use:</strong> Automatically extracts trading-relevant insights from documents for quick decision-making.
        ''',
        'expected_output': 'Array of 3 insights like ["15% revenue growth", "10 new $100M+ deals", "Attrition improved to 12%"]'
    },

    'question_answering': {
        'name': 'Question Answering (RAG)',
        'description': '''
            <strong>What it tests:</strong> Retrieval-Augmented Generation - answering questions based on provided context.
            <br><br>
            <strong>How it works:</strong>
            <ul>
                <li>Provides context: RELIANCE Q4 profit and dividend information</li>
                <li>Asks specific question: "What was the net profit?"</li>
                <li>LLM must extract answer from context, not use general knowledge</li>
                <li>Uses low temperature (0.1) for factual accuracy</li>
            </ul>
            <br>
            <strong>What success means:</strong> LLM correctly cites "Rs 19,299 crore" from the provided context.
            <br><br>
            <strong>Real-world use:</strong> Powers the knowledge base search - users ask questions, LLM answers using your document database.
        ''',
        'expected_output': 'Answer mentioning "Rs 19,299 crore" or "19,299 crore net profit"'
    },

    'news_articles': {
        'name': 'News Articles (LLM Ready)',
        'description': '''
            <strong>What it tests:</strong> Database integration for NewsArticle model with LLM analysis fields.
            <br><br>
            <strong>What it checks:</strong>
            <ul>
                <li>Total news articles in database</li>
                <li>Number processed by LLM (with summaries/sentiment)</li>
                <li>Number with sentiment analysis completed</li>
            </ul>
            <br>
            <strong>What success means:</strong> NewsArticle model is properly set up with all LLM fields.
            <br><br>
            <strong>Database fields checked:</strong> llm_summary, key_insights, sentiment_label, sentiment_score, processed
        ''',
        'expected_output': 'Counts: Total articles, Processed articles, Articles with sentiment'
    },

    'investor_calls': {
        'name': 'Investor Calls (LLM Ready)',
        'description': '''
            <strong>What it tests:</strong> Database integration for InvestorCall model with LLM analysis fields.
            <br><br>
            <strong>What it checks:</strong>
            <ul>
                <li>Total investor call transcripts in database</li>
                <li>Number processed by LLM</li>
                <li>Number with AI-generated executive summaries</li>
            </ul>
            <br>
            <strong>What success means:</strong> InvestorCall model is properly integrated with LLM capabilities.
            <br><br>
            <strong>Database fields checked:</strong> executive_summary, key_highlights, management_tone, trading_signal, processed
        ''',
        'expected_output': 'Counts: Total calls, Processed calls, Calls with summaries'
    },

    'knowledge_base': {
        'name': 'Knowledge Base (RAG Storage)',
        'description': '''
            <strong>What it tests:</strong> KnowledgeBase model for Retrieval-Augmented Generation document chunks.
            <br><br>
            <strong>What it checks:</strong>
            <ul>
                <li>Total knowledge chunks stored</li>
                <li>Breakdown by source type (NEWS, CALL, REPORT)</li>
                <li>Verifies chunks are linked to original documents</li>
            </ul>
            <br>
            <strong>What success means:</strong> RAG system has processed documents into searchable chunks.
            <br><br>
            <strong>How it works:</strong> Long documents are split into chunks, each stored separately for efficient retrieval during Q&A.
        ''',
        'expected_output': 'Total chunks and breakdown: "Total: 500 | News: 350 | Calls: 150"'
    },

    'trade_validations': {
        'name': 'LLM Trade Validations',
        'description': '''
            <strong>What it tests:</strong> LLMValidation model that stores AI-powered trade analysis.
            <br><br>
            <strong>What it checks:</strong>
            <ul>
                <li>Total trade validations performed by LLM</li>
                <li>Most recent symbol analyzed</li>
                <li>Historical record of AI recommendations</li>
            </ul>
            <br>
            <strong>What success means:</strong> System can track LLM's trade recommendations and performance over time.
            <br><br>
            <strong>Use case:</strong> Before executing trades, LLM validates the decision based on market data, news, and sentiment.
        ''',
        'expected_output': 'Count of validations and latest symbol: "Found 12 validations | Latest: RELIANCE"'
    },

    'prompt_templates': {
        'name': 'LLM Prompt Templates',
        'description': '''
            <strong>What it tests:</strong> LLMPrompt model that stores reusable prompt templates.
            <br><br>
            <strong>What it checks:</strong>
            <ul>
                <li>Total prompt templates configured</li>
                <li>Number of active (enabled) templates</li>
                <li>Template versioning system</li>
            </ul>
            <br>
            <strong>What success means:</strong> System has predefined prompts for common tasks (sentiment, summary, validation).
            <br><br>
            <strong>Why it matters:</strong> Consistent prompts lead to consistent AI responses and better performance tracking.
        ''',
        'expected_output': 'Template counts: "Total: 5 | Active: 3"'
    },

    'performance': {
        'name': 'LLM Performance',
        'description': '''
            <strong>What it tests:</strong> Response time and latency of the AI model.
            <br><br>
            <strong>How it works:</strong>
            <ul>
                <li>Sends simple prompt: "Say hello"</li>
                <li>Measures total time from request to response</li>
                <li>Evaluates: Good (<1s), Acceptable (<2s), Slow (>2s)</li>
            </ul>
            <br>
            <strong>What success means:</strong> LLM responds fast enough for real-time trading decisions.
            <br><br>
            <strong>Performance impact:</strong> Fast responses enable interactive chat, real-time news analysis, and quick trade validations.
            <br><br>
            <strong>Note:</strong> First request may be slower (cold start), subsequent requests are faster.
        ''',
        'expected_output': 'Response time in ms with quality rating: "450ms | Good" or "1800ms | Acceptable"'
    },
}

def get_test_description(test_key):
    """Get description for a test"""
    return TEST_DESCRIPTIONS.get(test_key, {
        'name': 'Unknown Test',
        'description': 'No description available',
        'expected_output': 'N/A'
    })
