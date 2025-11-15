"""
Celery tasks for automated data fetching and processing

Schedule these tasks with Celery Beat for continuous data updates
"""

from celery import shared_task
from django.utils import timezone

from .trendlyne import get_all_trendlyne_data
from .importers import TrendlyneDataImporter, ContractStockDataImporter
from .broker_integration import ScheduledDataUpdater, MarketDataUpdater
from .signals import SignalGenerator


@shared_task(name='fetch_trendlyne_data')
def fetch_trendlyne_data():
    """
    Fetch data from Trendlyne (Daily - 8:30 AM)

    Fetches:
    - Market snapshot
    - F&O data
    - Analyst consensus (21 CSVs)
    """
    print("Starting Trendlyne data fetch...")

    try:
        success = get_all_trendlyne_data()

        if success:
            print("✅ Trendlyne data fetched successfully")
            return {"status": "success", "timestamp": timezone.now().isoformat()}
        else:
            print("❌ Trendlyne data fetch failed")
            return {"status": "failed", "timestamp": timezone.now().isoformat()}

    except Exception as e:
        print(f"❌ Error fetching Trendlyne data: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name='import_trendlyne_data')
def import_trendlyne_data():
    """
    Import Trendlyne CSV files into database (Daily - 9:00 AM)

    Should run after fetch_trendlyne_data
    """
    print("Starting Trendlyne data import...")

    try:
        importer = TrendlyneDataImporter()
        stock_importer = ContractStockDataImporter()

        # Import market snapshot
        market_result = importer.import_market_snapshot()
        print(f"Market snapshot: {market_result.get('updated', 0)} stocks updated")

        # Import F&O data
        fno_result = importer.import_fno_data()
        print(f"F&O data: {fno_result.get('updated', 0)} contracts updated")

        # Calculate stock-level metrics
        stock_result = stock_importer.calculate_and_save_stock_fno_data()
        print(f"Stock F&O metrics: {stock_result.get('updated', 0)} stocks updated")

        # Import forecaster data
        forecaster_results = importer.import_forecaster_data()
        print(f"Forecaster data: {len(forecaster_results)} files imported")

        return {
            "status": "success",
            "market_snapshot": market_result,
            "fno_data": fno_result,
            "stock_metrics": stock_result,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error importing Trendlyne data: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name='update_live_market_data')
def update_live_market_data():
    """
    Update live market data from broker API (Every 5 minutes during market hours)

    Updates:
    - Current prices
    - Live volume
    - Current OI
    - Greeks
    """
    print("Updating live market data...")

    try:
        stats = ScheduledDataUpdater.update_live_fno_data()

        print(f"✅ Live data updated: {stats}")
        return {
            "status": "success",
            "stats": stats,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error updating live data: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name='update_pre_market_data')
def update_pre_market_data():
    """
    Update data before market opens (8:30 AM)

    Fetches latest data for Nifty 50 stocks
    """
    print("Updating pre-market data...")

    try:
        stats = ScheduledDataUpdater.update_pre_market_data()

        print(f"✅ Pre-market data updated: {stats}")
        return {
            "status": "success",
            "stats": stats,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error updating pre-market data: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name='update_post_market_data')
def update_post_market_data():
    """
    Update data after market closes (3:30 PM)

    Full update of all stocks and F&O contracts
    """
    print("Updating post-market data...")

    try:
        stats = ScheduledDataUpdater.update_post_market_data()

        print(f"✅ Post-market data updated: {stats}")
        return {
            "status": "success",
            "stats": stats,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error updating post-market data: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name='generate_daily_signals')
def generate_daily_signals(min_confidence: float = 70):
    """
    Generate trading signals (Daily - 9:15 AM)

    Scans all stocks and generates high-confidence signals
    """
    print("Generating daily trading signals...")

    try:
        generator = SignalGenerator()
        opportunities = generator.scan_for_opportunities(min_confidence=min_confidence)

        signals_summary = []
        for signal in opportunities[:10]:  # Top 10
            signals_summary.append({
                'symbol': signal.symbol,
                'signal': signal.signal.name,
                'confidence': signal.confidence,
                'action': signal.recommended_action
            })

        print(f"✅ Generated {len(opportunities)} signals")

        # You can send notifications here
        # send_telegram_notification(signals_summary)

        return {
            "status": "success",
            "total_signals": len(opportunities),
            "high_confidence_signals": len([s for s in opportunities if s.confidence >= 80]),
            "top_signals": signals_summary,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error generating signals: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name='scan_for_opportunities')
def scan_for_opportunities_task():
    """
    Scan for trading opportunities (Every hour during market hours)

    Quick scan for new setups
    """
    print("Scanning for opportunities...")

    try:
        generator = SignalGenerator()
        opportunities = generator.scan_for_opportunities(min_confidence=75)

        print(f"✅ Found {len(opportunities)} opportunities")
        return {
            "status": "success",
            "count": len(opportunities),
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        print(f"❌ Error scanning opportunities: {e}")
        return {"status": "error", "error": str(e)}


# Celery Beat Schedule
"""
Add to your settings.py or celeryconfig.py:

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Trendlyne data fetch (Daily 8:30 AM)
    'fetch-trendlyne-daily': {
        'task': 'fetch_trendlyne_data',
        'schedule': crontab(hour=8, minute=30),
    },

    # Import Trendlyne data (Daily 9:00 AM)
    'import-trendlyne-daily': {
        'task': 'import_trendlyne_data',
        'schedule': crontab(hour=9, minute=0),
    },

    # Pre-market update (Daily 8:30 AM)
    'pre-market-update': {
        'task': 'update_pre_market_data',
        'schedule': crontab(hour=8, minute=30, day_of_week='1-5'),  # Mon-Fri
    },

    # Live market data (Every 5 minutes during market hours)
    'live-market-update': {
        'task': 'update_live_market_data',
        'schedule': crontab(minute='*/5', hour='9-15', day_of_week='1-5'),
    },

    # Post-market update (Daily 3:30 PM)
    'post-market-update': {
        'task': 'update_post_market_data',
        'schedule': crontab(hour=15, minute=30, day_of_week='1-5'),
    },

    # Generate signals (Daily 9:15 AM)
    'generate-daily-signals': {
        'task': 'generate_daily_signals',
        'schedule': crontab(hour=9, minute=15, day_of_week='1-5'),
    },

    # Scan opportunities (Hourly during market hours)
    'scan-opportunities': {
        'task': 'scan_for_opportunities',
        'schedule': crontab(minute=0, hour='9-15', day_of_week='1-5'),
    },
}
"""
