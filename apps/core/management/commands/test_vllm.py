"""
Test vLLM System

This command tests the vLLM client and its capabilities:
- Connection and model availability
- Text generation
- Chat completions
- Sentiment analysis
- Summarization
- Insight extraction

Usage:
    python manage.py test_vllm
    python manage.py test_vllm --quick  # Skip detailed tests
"""

from django.core.management.base import BaseCommand

from apps.llm.services.vllm_client import get_vllm_client


class Command(BaseCommand):
    help = 'Test vLLM system components'

    def add_arguments(self, parser):
        parser.add_argument(
            '--quick',
            action='store_true',
            help='Run quick tests only'
        )

    def handle(self, *args, **options):
        self.quick = options['quick']

        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('vLLM SYSTEM TEST'))
        self.stdout.write('=' * 80)
        self.stdout.write('')

        all_passed = True

        # Test connection
        if not self.test_connection():
            all_passed = False
            self.stdout.write(self.style.ERROR('\nConnection failed. Skipping other tests.'))
            return

        # Test text generation
        if not self.test_text_generation():
            all_passed = False

        # Test chat completion
        if not self.test_chat_completion():
            all_passed = False

        if not self.quick:
            # Test sentiment analysis
            if not self.test_sentiment_analysis():
                all_passed = False

            # Test summarization
            if not self.test_summarization():
                all_passed = False

            # Test insight extraction
            if not self.test_insight_extraction():
                all_passed = False

        # Final summary
        self.stdout.write('')
        self.stdout.write('=' * 80)
        if all_passed:
            self.stdout.write(self.style.SUCCESS('ALL TESTS PASSED'))
        else:
            self.stdout.write(self.style.ERROR('SOME TESTS FAILED'))
        self.stdout.write('=' * 80)

    def test_connection(self):
        """Test vLLM connection"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 1: vLLM CONNECTION'))
        self.stdout.write('-' * 80)

        client = get_vllm_client()

        self.stdout.write('Checking vLLM connection...')
        if not client.is_enabled():
            self.stdout.write(self.style.ERROR('  FAILED: vLLM not available'))
            self.stdout.write(f'  Base URL: {client.base_url}')
            self.stdout.write(f'  Model: {client.model}')
            self.stdout.write('')
            self.stdout.write('  Troubleshooting:')
            self.stdout.write('  1. Is vLLM server running?')
            self.stdout.write('  2. Check VLLM_HOST and VLLM_MODEL in .env')
            self.stdout.write(f'  3. Try: curl {client.base_url}/models')
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: vLLM connected'))
        self.stdout.write(f'  Base URL: {client.base_url}')
        self.stdout.write(f'  Model: {client.model}')

        return True

    def test_text_generation(self):
        """Test text generation"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 2: TEXT GENERATION'))
        self.stdout.write('-' * 80)

        client = get_vllm_client()

        self.stdout.write('Testing text generation...')
        success, response, metadata = client.generate(
            prompt="What is the capital of India? Answer in one sentence.",
            temperature=0.1,
            max_tokens=50
        )

        if not success:
            self.stdout.write(self.style.ERROR(f'  FAILED: {response}'))
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Text generation working'))
        self.stdout.write(f'  Response: {response}')
        self.stdout.write(f'  Tokens used: {metadata["usage"]["total_tokens"]}')
        self.stdout.write(f'  Processing time: {metadata["processing_time_ms"]}ms')

        return True

    def test_chat_completion(self):
        """Test chat completion"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 3: CHAT COMPLETION'))
        self.stdout.write('-' * 80)

        client = get_vllm_client()

        self.stdout.write('Testing chat completion...')
        messages = [
            {"role": "system", "content": "You are a helpful financial assistant."},
            {"role": "user", "content": "What are blue chip stocks? Explain in 2 sentences."}
        ]

        success, response, metadata = client.chat(
            messages=messages,
            temperature=0.3,
            max_tokens=100
        )

        if not success:
            self.stdout.write(self.style.ERROR(f'  FAILED: {response}'))
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Chat completion working'))
        self.stdout.write(f'  Response: {response}')
        self.stdout.write(f'  Tokens used: {metadata["usage"]["total_tokens"]}')

        return True

    def test_sentiment_analysis(self):
        """Test sentiment analysis"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 4: SENTIMENT ANALYSIS'))
        self.stdout.write('-' * 80)

        client = get_vllm_client()

        test_text = """RELIANCE Industries reported strong Q4 results with net profit rising 12%
year-on-year. The company announced ambitious expansion plans and increased dividend payout.
Analysts are bullish on the stock."""

        self.stdout.write('Testing sentiment analysis...')
        success, sentiment, metadata = client.analyze_sentiment(test_text)

        if not success:
            self.stdout.write(self.style.ERROR(f'  FAILED: {sentiment}'))
            self.stdout.write(f'  Metadata: {metadata}')
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Sentiment analysis working'))
        self.stdout.write(f'  Label: {sentiment.get("label")}')
        self.stdout.write(f'  Score: {sentiment.get("score")}')
        self.stdout.write(f'  Confidence: {sentiment.get("confidence")}')

        return True

    def test_summarization(self):
        """Test summarization"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 5: SUMMARIZATION'))
        self.stdout.write('-' * 80)

        client = get_vllm_client()

        test_text = """RELIANCE Industries Ltd reported strong Q4 FY24 results with net profit
rising 12% year-on-year to Rs 19,299 crore. Revenue from operations increased 8% to Rs 2.35 lakh crore.
The company announced plans to expand its retail footprint and invest in green energy initiatives.
The board recommended a dividend of Rs 9 per share. Management expressed confidence in maintaining
growth momentum in the upcoming fiscal year. The telecom business showed robust subscriber additions
while the petrochemicals segment benefited from higher margins."""

        self.stdout.write('Testing summarization...')
        success, summary, metadata = client.summarize(test_text, max_length=50)

        if not success:
            self.stdout.write(self.style.ERROR(f'  FAILED: {summary}'))
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Summarization working'))
        self.stdout.write(f'  Summary: {summary}')
        self.stdout.write(f'  Original length: {len(test_text.split())} words')
        self.stdout.write(f'  Summary length: {len(summary.split())} words')

        return True

    def test_insight_extraction(self):
        """Test insight extraction"""
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('TEST 6: INSIGHT EXTRACTION'))
        self.stdout.write('-' * 80)

        client = get_vllm_client()

        test_text = """TCS reported strong quarterly earnings with revenue growth of 15% YoY.
The company added 10 new large deals worth over $100M each. Attrition rate decreased to 12%
from 18% last quarter. Management guided for double-digit growth in FY25. The BFSI vertical
showed particular strength with 20% growth. Cloud transformation deals are driving pipeline."""

        self.stdout.write('Testing insight extraction...')
        success, insights, metadata = client.extract_insights(test_text, num_insights=3)

        if not success:
            self.stdout.write(self.style.ERROR(f'  FAILED: {insights}'))
            self.stdout.write(f'  Metadata: {metadata}')
            return False

        self.stdout.write(self.style.SUCCESS('  PASSED: Insight extraction working'))
        self.stdout.write(f'  Extracted {len(insights)} insights:')
        for i, insight in enumerate(insights, 1):
            self.stdout.write(f'    {i}. {insight}')

        return True
