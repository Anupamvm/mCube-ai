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

# Import TaskLogger
from apps.core.utils.task_logger import TaskLogger


@shared_task(name='fetch_trendlyne_data', bind=True)
def fetch_trendlyne_data(self):
    """
    Fetch data from Trendlyne (Daily - 8:30 AM)

    Fetches:
    - Market snapshot
    - F&O data
    - Analyst consensus (21 CSVs)
    """
    # Initialize logger
    logger = TaskLogger(
        task_name='fetch_trendlyne_data',
        task_category='data',
        task_id=self.request.id
    )

    logger.start("Starting Trendlyne data fetch", context={
        'source': 'Trendlyne',
        'data_types': ['Market Snapshot', 'F&O Data', 'Analyst Consensus']
    })

    try:
        logger.step('fetching', "Calling Trendlyne API to fetch all data")
        success = get_all_trendlyne_data()

        if success:
            logger.success("Trendlyne data fetched successfully", context={
                'status': 'success',
                'timestamp': timezone.now().isoformat()
            })
            return {"status": "success", "timestamp": timezone.now().isoformat()}
        else:
            logger.error('fetch_failed', "Trendlyne data fetch returned False")
            return {"status": "failed", "timestamp": timezone.now().isoformat()}

    except Exception as e:
        logger.failure("Error fetching Trendlyne data", error=e, context={
            'error_type': type(e).__name__
        })
        return {"status": "error", "error": str(e)}


@shared_task(name='import_trendlyne_data', bind=True)
def import_trendlyne_data(self):
    """
    Import Trendlyne CSV files into database (Daily - 9:00 AM)

    Should run after fetch_trendlyne_data
    """
    logger = TaskLogger(
        task_name='import_trendlyne_data',
        task_category='data',
        task_id=self.request.id
    )

    logger.start("Starting Trendlyne data import from CSV files")

    try:
        importer = TrendlyneDataImporter()
        stock_importer = ContractStockDataImporter()

        # Import market snapshot
        logger.step('market_snapshot', "Importing market snapshot data")
        market_result = importer.import_market_snapshot()
        logger.info('market_snapshot_complete',
                   f"Market snapshot import complete",
                   context={'stocks_updated': market_result.get('updated', 0)})

        # Import F&O data
        logger.step('fno_data', "Importing F&O data")
        fno_result = importer.import_fno_data()
        logger.info('fno_data_complete',
                   f"F&O data import complete",
                   context={'contracts_updated': fno_result.get('updated', 0)})

        # Calculate stock-level metrics
        logger.step('stock_metrics', "Calculating stock-level F&O metrics")
        stock_result = stock_importer.calculate_and_save_stock_fno_data()
        logger.info('stock_metrics_complete',
                   f"Stock metrics calculation complete",
                   context={'stocks_updated': stock_result.get('updated', 0)})

        # Import forecaster data
        logger.step('forecaster_data', "Importing forecaster data")
        forecaster_results = importer.import_forecaster_data()
        logger.info('forecaster_data_complete',
                   f"Forecaster data import complete",
                   context={'files_imported': len(forecaster_results)})

        logger.success("All Trendlyne data imported successfully", context={
            'market_snapshot_count': market_result.get('updated', 0),
            'fno_contracts_count': fno_result.get('updated', 0),
            'stock_metrics_count': stock_result.get('updated', 0),
            'forecaster_files_count': len(forecaster_results)
        })

        return {
            "status": "success",
            "market_snapshot": market_result,
            "fno_data": fno_result,
            "stock_metrics": stock_result,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        logger.failure("Error importing Trendlyne data", error=e)
        return {"status": "error", "error": str(e)}


@shared_task(name='update_live_market_data', bind=True)
def update_live_market_data(self):
    """
    Update live market data from broker API (Every 5 minutes during market hours)

    Updates:
    - Current prices
    - Live volume
    - Current OI
    - Greeks
    """
    logger = TaskLogger(
        task_name='update_live_market_data',
        task_category='data',
        task_id=self.request.id
    )

    logger.start("Updating live market data from broker API")

    try:
        logger.step('fetching', "Calling broker API to fetch live F&O data")
        stats = ScheduledDataUpdater.update_live_fno_data()

        logger.success("Live market data updated successfully", context={
            'stats': stats,
            'update_time': timezone.now().isoformat()
        })

        return {
            "status": "success",
            "stats": stats,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        logger.failure("Error updating live market data", error=e)
        return {"status": "error", "error": str(e)}


@shared_task(name='update_pre_market_data', bind=True)
def update_pre_market_data(self):
    """
    Update data before market opens (8:30 AM)

    Fetches latest data for Nifty 50 stocks
    """
    logger = TaskLogger(
        task_name='update_pre_market_data',
        task_category='data',
        task_id=self.request.id
    )

    logger.start("Updating pre-market data for Nifty 50 stocks")

    try:
        stats = ScheduledDataUpdater.update_pre_market_data()

        logger.success("Pre-market data updated successfully", context=stats if isinstance(stats, dict) else {'result': str(stats)})
        return {
            "status": "success",
            "stats": stats,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        logger.failure("Error updating pre-market data", error=e)
        return {"status": "error", "error": str(e)}


@shared_task(name='update_post_market_data', bind=True)
def update_post_market_data(self):
    """
    Update data after market closes (3:30 PM)

    Full update of all stocks and F&O contracts
    """
    logger = TaskLogger(
        task_name='update_post_market_data',
        task_category='data',
        task_id=self.request.id
    )

    logger.start("Updating post-market data - full refresh of all stocks and F&O")

    try:
        stats = ScheduledDataUpdater.update_post_market_data()

        logger.success("Post-market data updated successfully", context=stats if isinstance(stats, dict) else {'result': str(stats)})
        return {
            "status": "success",
            "stats": stats,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        logger.failure("Error updating post-market data", error=e)
        return {"status": "error", "error": str(e)}


@shared_task(name='generate_daily_signals', bind=True)
def generate_daily_signals(self, min_confidence: float = 70):
    """
    Generate trading signals (Daily - 9:15 AM)

    Scans all stocks and generates high-confidence signals
    """
    logger = TaskLogger(
        task_name='generate_daily_signals',
        task_category='analytics',
        task_id=self.request.id
    )

    logger.start(f"Generating daily trading signals (min confidence: {min_confidence}%)")

    try:
        logger.step('scanning', "Scanning all stocks for trading opportunities")
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

        high_confidence_count = len([s for s in opportunities if s.confidence >= 80])

        logger.success("Daily signals generated successfully", context={
            'total_signals': len(opportunities),
            'high_confidence_signals': high_confidence_count,
            'min_confidence_threshold': min_confidence
        })

        # You can send notifications here
        # send_telegram_notification(signals_summary)

        return {
            "status": "success",
            "total_signals": len(opportunities),
            "high_confidence_signals": high_confidence_count,
            "top_signals": signals_summary,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        logger.failure("Error generating signals", error=e)
        return {"status": "error", "error": str(e)}


@shared_task(name='scan_for_opportunities', bind=True)
def scan_for_opportunities_task(self):
    """
    Scan for trading opportunities (Every hour during market hours)

    Quick scan for new setups
    """
    logger = TaskLogger(
        task_name='scan_for_opportunities',
        task_category='analytics',
        task_id=self.request.id
    )

    logger.start("Scanning for new trading opportunities")

    try:
        generator = SignalGenerator()
        opportunities = generator.scan_for_opportunities(min_confidence=75)

        logger.success(f"Found {len(opportunities)} trading opportunities", context={
            'opportunities_count': len(opportunities),
            'min_confidence': 75
        })

        return {
            "status": "success",
            "count": len(opportunities),
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        logger.failure("Error scanning for opportunities", error=e)
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
