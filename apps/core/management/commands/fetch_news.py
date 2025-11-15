"""
Fetch News Command

This command fetches news from various sources and processes them with LLM.

News Sources (to be integrated):
- NewsAPI (newsapi.org)
- Alpha Vantage News
- Financial Modeling Prep
- Custom RSS feeds
- Web scraping (with proper permissions)

Usage:
    python manage.py fetch_news --source newsapi --limit 10
    python manage.py fetch_news --symbols RELIANCE,TCS --limit 5
    python manage.py fetch_news --demo  # Use demo data

Note: This is a template. You need to:
1. Sign up for news API services
2. Add API keys to .env
3. Implement the fetcher for your chosen source
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta

from apps.llm.services.news_processor import get_news_processor


class Command(BaseCommand):
    help = 'Fetch and process news articles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            type=str,
            default='demo',
            choices=['newsapi', 'alphavantage', 'demo'],
            help='News source to fetch from'
        )

        parser.add_argument(
            '--symbols',
            type=str,
            help='Comma-separated list of symbols to fetch news for'
        )

        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Number of articles to fetch'
        )

        parser.add_argument(
            '--demo',
            action='store_true',
            help='Use demo data instead of real API'
        )

    def handle(self, *args, **options):
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('NEWS FETCHER'))
        self.stdout.write('=' * 80)
        self.stdout.write('')

        source = options['source']
        symbols = options['symbols'].split(',') if options['symbols'] else []
        limit = options['limit']
        use_demo = options['demo'] or source == 'demo'

        if use_demo:
            self.fetch_demo_news(symbols, limit)
        elif source == 'newsapi':
            self.fetch_from_newsapi(symbols, limit)
        elif source == 'alphavantage':
            self.fetch_from_alphavantage(symbols, limit)

    def fetch_demo_news(self, symbols, limit):
        """Fetch demo/sample news for testing"""
        self.stdout.write(self.style.WARNING('Using demo data'))
        self.stdout.write('-' * 80)

        # Demo news articles
        demo_articles = [
            {
                'title': 'RELIANCE Industries Reports Record Quarterly Profits',
                'content': '''RELIANCE Industries Ltd has reported record quarterly profits,
beating analyst estimates. The conglomerate's net profit rose 15% year-on-year to Rs 20,000 crore
in Q4 FY24. Revenue from the retail segment grew 25%, while petrochemicals showed steady performance.
The company announced a dividend of Rs 10 per share and plans to invest Rs 75,000 crore in green
energy projects over the next three years. Management expressed confidence in maintaining growth
momentum driven by consumer demand and digital services expansion.''',
                'source': 'Demo - Financial Express',
                'url': 'https://demo.example.com/reliance-profits',
                'published_at': timezone.now() - timedelta(hours=2),
                'symbols': ['RELIANCE'],
                'author': 'Demo Author'
            },
            {
                'title': 'TCS Wins Major Cloud Migration Contract Worth $500 Million',
                'content': '''Tata Consultancy Services (TCS) has secured a major cloud migration
contract worth USD 500 million from a Fortune 100 client. The 5-year deal involves migrating legacy
systems to cloud infrastructure and implementing AI-driven automation. TCS will deploy over 2,000
consultants on the project. The company's shares rose 3% on the news. Analysts view this as validation
of TCS's cloud and digital transformation capabilities. The deal is expected to contribute significantly
to revenue growth in FY25.''',
                'source': 'Demo - Economic Times',
                'url': 'https://demo.example.com/tcs-contract',
                'published_at': timezone.now() - timedelta(hours=5),
                'symbols': ['TCS'],
                'author': 'Demo Reporter'
            },
            {
                'title': 'NIFTY Hits All-Time High on Strong FII Inflows',
                'content': '''The NIFTY 50 index touched a new all-time high of 21,500 today,
driven by strong foreign institutional investor (FII) inflows. Banking, IT, and auto sectors led
the rally. FIIs have pumped in Rs 15,000 crore in the past week amid positive global cues and
strong domestic earnings. Market breadth was positive with 42 stocks advancing for every 8 declining.
Analysts expect the rally to continue supported by robust economic fundamentals and corporate earnings
growth. However, they advise caution at elevated valuations.''',
                'source': 'Demo - Moneycontrol',
                'url': 'https://demo.example.com/nifty-high',
                'published_at': timezone.now() - timedelta(hours=1),
                'symbols': ['NIFTY'],
                'author': 'Market Desk'
            },
            {
                'title': 'INFOSYS Announces Rs 10,000 Crore Share Buyback',
                'content': '''Infosys has announced a share buyback program worth Rs 10,000 crore
at a price of Rs 1,850 per share, representing a 15% premium to current market price. The buyback
will benefit shareholders and demonstrates management's confidence in the company's long-term
prospects. The IT major also reaffirmed its FY25 revenue growth guidance of 12-14% in constant
currency terms. CEO Salil Parekh highlighted strong deal pipeline and improving demand environment.
The stock traded 2% higher following the announcement.''',
                'source': 'Demo - Business Standard',
                'url': 'https://demo.example.com/infosys-buyback',
                'published_at': timezone.now() - timedelta(hours=4),
                'symbols': ['INFY'],
                'author': 'Corporate Correspondent'
            },
            {
                'title': 'RBI Keeps Repo Rate Unchanged at 6.5%, Maintains Accommodative Stance',
                'content': '''The Reserve Bank of India (RBI) kept the repo rate unchanged at 6.5%
for the sixth consecutive policy meeting, in line with market expectations. The central bank
maintained its accommodative stance while focusing on growth and inflation management. Governor
Shaktikanta Das noted that inflation is trending towards the 4% target while growth remains robust.
The decision was unanimous. Markets reacted positively with banking stocks rallying on hopes of
sustained liquidity support. The RBI also announced measures to deepen corporate bond markets.''',
                'source': 'Demo - Mint',
                'url': 'https://demo.example.com/rbi-policy',
                'published_at': timezone.now() - timedelta(hours=3),
                'symbols': ['NIFTY', 'BANKNIFTY'],
                'author': 'Economics Editor'
            }
        ]

        # Filter by symbols if specified
        if symbols:
            demo_articles = [
                article for article in demo_articles
                if any(sym in article['symbols'] for sym in symbols)
            ]

        # Limit number of articles
        demo_articles = demo_articles[:limit]

        # Process articles
        self.process_articles(demo_articles)

    def fetch_from_newsapi(self, symbols, limit):
        """
        Fetch from NewsAPI (newsapi.org)

        Setup:
        1. Sign up at https://newsapi.org/
        2. Get API key
        3. Add to .env: NEWSAPI_KEY=your_key_here
        """
        self.stdout.write(self.style.ERROR('NewsAPI integration not implemented yet'))
        self.stdout.write('')
        self.stdout.write('To implement NewsAPI:')
        self.stdout.write('1. Sign up at https://newsapi.org/')
        self.stdout.write('2. Add NEWSAPI_KEY to .env')
        self.stdout.write('3. Install: pip install newsapi-python')
        self.stdout.write('4. Implement fetch logic below')
        self.stdout.write('')

        """
        # Example implementation (uncomment when ready):

        import os
        from newsapi import NewsApiClient

        api_key = os.getenv('NEWSAPI_KEY')
        if not api_key:
            self.stdout.write(self.style.ERROR('NEWSAPI_KEY not found in .env'))
            return

        newsapi = NewsApiClient(api_key=api_key)

        # Build query
        if symbols:
            query = ' OR '.join(symbols)
        else:
            query = 'stock market India OR Nifty OR Sensex'

        # Fetch articles
        response = newsapi.get_everything(
            q=query,
            language='en',
            sort_by='publishedAt',
            page_size=limit
        )

        # Convert to our format
        articles = []
        for article in response['articles']:
            articles.append({
                'title': article['title'],
                'content': article['description'] + '\\n\\n' + (article['content'] or ''),
                'source': article['source']['name'],
                'url': article['url'],
                'published_at': datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00')),
                'symbols': symbols,  # You might want to extract this from content
                'author': article.get('author', '')
            })

        self.process_articles(articles)
        """

    def fetch_from_alphavantage(self, symbols, limit):
        """
        Fetch from Alpha Vantage

        Setup:
        1. Sign up at https://www.alphavantage.co/
        2. Get API key
        3. Add to .env: ALPHAVANTAGE_KEY=your_key_here
        """
        self.stdout.write(self.style.ERROR('Alpha Vantage integration not implemented yet'))
        self.stdout.write('')
        self.stdout.write('To implement Alpha Vantage:')
        self.stdout.write('1. Sign up at https://www.alphavantage.co/')
        self.stdout.write('2. Add ALPHAVANTAGE_KEY to .env')
        self.stdout.write('3. Implement fetch logic below')
        self.stdout.write('')

        """
        # Example implementation (uncomment when ready):

        import os
        import requests

        api_key = os.getenv('ALPHAVANTAGE_KEY')
        if not api_key:
            self.stdout.write(self.style.ERROR('ALPHAVANTAGE_KEY not found in .env'))
            return

        articles = []

        for symbol in symbols or ['RELIANCE.BSE']:
            # Alpha Vantage News & Sentiment API
            url = f'https://www.alphavantage.co/query'
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': symbol,
                'apikey': api_key,
                'limit': limit
            }

            response = requests.get(url, params=params)
            data = response.json()

            for item in data.get('feed', [])[:limit]:
                articles.append({
                    'title': item['title'],
                    'content': item['summary'],
                    'source': item['source'],
                    'url': item['url'],
                    'published_at': datetime.strptime(item['time_published'], '%Y%m%dT%H%M%S'),
                    'symbols': [symbol],
                    'author': item.get('authors', [''])[0]
                })

        self.process_articles(articles)
        """

    def process_articles(self, articles):
        """Process fetched articles with LLM"""
        if not articles:
            self.stdout.write(self.style.WARNING('No articles to process'))
            return

        self.stdout.write('')
        self.stdout.write(f'Processing {len(articles)} articles...')
        self.stdout.write('-' * 80)

        processor = get_news_processor()

        success_count, error_count, errors = processor.batch_process_articles(articles)

        # Summary
        self.stdout.write('')
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS(f'Processing complete'))
        self.stdout.write(f'  Success: {success_count}')
        self.stdout.write(f'  Errors: {error_count}')
        self.stdout.write('=' * 80)

        if errors:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('Errors encountered:'))
            for error in errors[:5]:  # Show first 5 errors
                self.stdout.write(f'  - {error}')
            if len(errors) > 5:
                self.stdout.write(f'  ... and {len(errors) - 5} more')

        self.stdout.write('')
        self.stdout.write('Next steps:')
        self.stdout.write('  1. Test RAG queries: python manage.py test_llm --component rag')
        self.stdout.write('  2. Validate trades: python manage.py test_llm --component validator')
        self.stdout.write('  3. Query knowledge: from apps.llm.services.rag_system import ask_question')
