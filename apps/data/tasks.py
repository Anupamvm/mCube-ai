"""
Celery tasks for automated data fetching and processing

Schedule these tasks with Celery Beat for continuous data updates
"""

from celery import shared_task
from django.utils import timezone

from .providers.trendlyne import get_all_trendlyne_data
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


@shared_task(name='fetch_and_import_trendlyne_data', bind=True)
def fetch_and_import_trendlyne_data(self):
    """
    Combined task: Fetch AND import Trendlyne data in one go

    This task is used by the data freshness checker to ensure data
    is never older than 30 minutes. It runs the full cycle:
    1. Fetch data from Trendlyne
    2. Import into database
    3. Calculate stock-level metrics

    Returns:
        dict: Status with counts of imported records
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info("Starting combined Trendlyne fetch and import...")

    try:
        # Use management command for full cycle
        from django.core.management import call_command
        from io import StringIO

        output = StringIO()
        call_command('trendlyne_data_manager', '--full-cycle', stdout=output)

        logger.info(f"Trendlyne full cycle completed: {output.getvalue()}")

        # Get final statistics
        from apps.data.models import ContractData, ContractStockData, TLStockData

        stats = {
            'ContractData': ContractData.objects.count(),
            'ContractStockData': ContractStockData.objects.count(),
            'TLStockData': TLStockData.objects.count(),
        }

        logger.info(f"Trendlyne data updated - Stats: {stats}")

        return {
            "status": "success",
            "stats": stats,
            "timestamp": timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Trendlyne fetch and import failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name='fetch_analyst_reports_daily', bind=True)
def fetch_analyst_reports_daily(self):
    """
    Fetch analyst reports for all F&O stocks (Daily - 7:00 AM)

    Fetches analyst price targets and research reports for all stocks
    that have trendlyne_id in TLStockData. Downloads PDFs and triggers
    LLM analysis for new reports.
    """
    logger = TaskLogger(
        task_name='fetch_analyst_reports_daily',
        task_category='data',
        task_id=self.request.id
    )

    logger.start("Starting daily analyst reports fetch for F&O stocks")

    try:
        from apps.data.models import TLStockData, ContractStockData, AnalystPriceTarget, AnalystReport
        from apps.data.providers.trendlyne import TrendlyneProvider

        # Get F&O stocks with trendlyne_id
        fno_symbols = set(ContractStockData.objects.values_list('nse_code', flat=True))
        stocks_with_id = TLStockData.objects.filter(
            nsecode__in=fno_symbols,
            trendlyne_id__isnull=False
        ).values('nsecode', 'trendlyne_id', 'stock_name')

        logger.step('fetching', f"Found {len(stocks_with_id)} F&O stocks with trendlyne_id")

        results = {
            'processed': 0,
            'price_targets_saved': 0,
            'reports_saved': 0,
            'errors': []
        }

        with TrendlyneProvider() as provider:
            # Login once
            if not provider.login():
                logger.error('login_failed', "Could not login to Trendlyne")
                return {"status": "error", "error": "Trendlyne login failed"}

            for stock in stocks_with_id:
                try:
                    symbol = stock['nsecode']
                    trendlyne_id = stock['trendlyne_id']

                    logger.info('processing_stock', f"Processing {symbol} (ID: {trendlyne_id})")

                    # Fetch analyst data
                    data = provider.fetch_analyst_data(
                        symbol=symbol,
                        trendlyne_id=trendlyne_id,
                        months_back=3,
                        download_pdfs=True
                    )

                    if not data.get('success'):
                        results['errors'].append(f"{symbol}: {data.get('error', 'Unknown error')}")
                        continue

                    # Save price target
                    price_target_data = data.get('price_target', {})
                    if price_target_data.get('success'):
                        AnalystPriceTarget.objects.update_or_create(
                            nse_code=symbol,
                            defaults={
                                'symbol': symbol,
                                'trendlyne_id': trendlyne_id,
                                'stock_name': stock.get('stock_name', ''),
                                'current_price': price_target_data.get('current_price'),
                                'avg_target_price': price_target_data.get('avg_target_price'),
                                'upside_pct': price_target_data.get('upside_pct'),
                                'analyst_count': price_target_data.get('analyst_count', 0),
                                'strong_buy_count': price_target_data.get('strong_buy_count', 0),
                                'buy_count': price_target_data.get('buy_count', 0),
                                'hold_count': price_target_data.get('hold_count', 0),
                                'sell_count': price_target_data.get('sell_count', 0),
                                'strong_sell_count': price_target_data.get('strong_sell_count', 0),
                                'source_url': price_target_data.get('source_url', ''),
                                'scrape_success': True,
                            }
                        )
                        results['price_targets_saved'] += 1

                    # Save reports
                    reports_data = data.get('reports', {})
                    for report in reports_data.get('reports', []):
                        try:
                            AnalystReport.objects.update_or_create(
                                symbol=symbol,
                                report_date=report.get('report_date'),
                                author=report.get('author', '')[:200],
                                defaults={
                                    'nse_code': symbol,
                                    'trendlyne_id': trendlyne_id,
                                    'report_title': report.get('report_title', ''),
                                    'ltp_at_report': report.get('ltp_at_report'),
                                    'target_price': report.get('target_price'),
                                    'upside_pct': report.get('upside_pct'),
                                    'recommendation_type': report.get('recommendation_type', 'UNKNOWN'),
                                    'pdf_url': report.get('pdf_url', ''),
                                    'pdf_local_path': report.get('pdf_local_path', ''),
                                    'pdf_download_success': bool(report.get('pdf_local_path')),
                                }
                            )
                            results['reports_saved'] += 1
                        except Exception as report_error:
                            logger.warning('report_save_error', f"Error saving report for {symbol}: {report_error}")

                    results['processed'] += 1

                except Exception as stock_error:
                    results['errors'].append(f"{stock.get('nsecode')}: {str(stock_error)}")
                    logger.warning('stock_error', f"Error processing stock: {stock_error}")

        logger.success("Daily analyst reports fetch completed", context=results)
        return {"status": "success", **results, "timestamp": timezone.now().isoformat()}

    except Exception as e:
        logger.failure("Error in daily analyst reports fetch", error=e)
        return {"status": "error", "error": str(e)}


@shared_task(name='fetch_analyst_reports_for_stock', bind=True)
def fetch_analyst_reports_for_stock(self, symbol: str, nse_code: str = None):
    """
    Fetch analyst reports for a single stock (On-demand task)

    Used for on-demand refresh when data is stale during trade verification.

    Args:
        symbol: Stock symbol
        nse_code: NSE code (defaults to symbol)
    """
    import logging
    logger = logging.getLogger(__name__)

    nse_code = nse_code or symbol

    try:
        from apps.data.models import TLStockData, AnalystPriceTarget, AnalystReport
        from apps.data.providers.trendlyne import TrendlyneProvider

        logger.info(f"Fetching analyst reports for {symbol}")

        # Get trendlyne_id from TLStockData
        stock_data = TLStockData.objects.filter(nsecode__iexact=nse_code).first()
        trendlyne_id = stock_data.trendlyne_id if stock_data else None

        with TrendlyneProvider() as provider:
            if not provider.login():
                logger.error(f"Could not login to Trendlyne for {symbol}")
                return {"status": "error", "error": "Login failed"}

            data = provider.fetch_analyst_data(
                symbol=symbol,
                trendlyne_id=trendlyne_id,
                months_back=3,
                download_pdfs=True
            )

            if not data.get('success'):
                return {"status": "error", "error": data.get('error', 'Unknown error')}

            # Update trendlyne_id in TLStockData if we found it
            extracted_id = data.get('trendlyne_id')
            if extracted_id and stock_data and not stock_data.trendlyne_id:
                stock_data.trendlyne_id = extracted_id
                stock_data.save()
                logger.info(f"Updated trendlyne_id for {symbol}: {extracted_id}")

            # Save price target
            price_target_data = data.get('price_target', {})
            if price_target_data.get('success'):
                AnalystPriceTarget.objects.update_or_create(
                    nse_code=nse_code,
                    defaults={
                        'symbol': symbol,
                        'trendlyne_id': extracted_id,
                        'stock_name': stock_data.stock_name if stock_data else '',
                        'current_price': price_target_data.get('current_price'),
                        'avg_target_price': price_target_data.get('avg_target_price'),
                        'upside_pct': price_target_data.get('upside_pct'),
                        'analyst_count': price_target_data.get('analyst_count', 0),
                        'strong_buy_count': price_target_data.get('strong_buy_count', 0),
                        'buy_count': price_target_data.get('buy_count', 0),
                        'hold_count': price_target_data.get('hold_count', 0),
                        'sell_count': price_target_data.get('sell_count', 0),
                        'strong_sell_count': price_target_data.get('strong_sell_count', 0),
                        'source_url': price_target_data.get('source_url', ''),
                        'scrape_success': True,
                    }
                )

            # Save reports
            reports_saved = 0
            reports_data = data.get('reports', {})
            for report in reports_data.get('reports', []):
                try:
                    AnalystReport.objects.update_or_create(
                        symbol=symbol,
                        report_date=report.get('report_date'),
                        author=report.get('author', '')[:200],
                        defaults={
                            'nse_code': nse_code,
                            'trendlyne_id': extracted_id,
                            'report_title': report.get('report_title', ''),
                            'ltp_at_report': report.get('ltp_at_report'),
                            'target_price': report.get('target_price'),
                            'upside_pct': report.get('upside_pct'),
                            'recommendation_type': report.get('recommendation_type', 'UNKNOWN'),
                            'pdf_url': report.get('pdf_url', ''),
                            'pdf_local_path': report.get('pdf_local_path', ''),
                            'pdf_download_success': bool(report.get('pdf_local_path')),
                        }
                    )
                    reports_saved += 1
                except Exception as e:
                    logger.warning(f"Error saving report for {symbol}: {e}")

            logger.info(f"Fetched analyst data for {symbol}: 1 price target, {reports_saved} reports")
            return {
                "status": "success",
                "symbol": symbol,
                "price_target_saved": True,
                "reports_saved": reports_saved
            }

    except Exception as e:
        logger.error(f"Error fetching analyst reports for {symbol}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name='process_analyst_report_pdfs', bind=True)
def process_analyst_report_pdfs(self, limit: int = 50):
    """
    Process unprocessed analyst report PDFs with LLM (Daily - 7:30 AM)

    Extracts text from downloaded PDFs and runs LLM analysis.

    Args:
        limit: Maximum number of reports to process per run
    """
    logger = TaskLogger(
        task_name='process_analyst_report_pdfs',
        task_category='llm',
        task_id=self.request.id
    )

    logger.start(f"Processing up to {limit} unprocessed analyst report PDFs")

    try:
        from apps.data.models import AnalystReport
        from apps.llm.services.analyst_report_analyzer import get_analyst_report_analyzer

        # Get unprocessed reports with downloaded PDFs
        unprocessed = AnalystReport.objects.filter(
            llm_processed=False,
            pdf_download_success=True,
            pdf_local_path__isnull=False
        ).exclude(pdf_local_path='').order_by('-report_date')[:limit]

        logger.step('fetching', f"Found {unprocessed.count()} reports to process")

        analyzer = get_analyst_report_analyzer()
        results = {
            'processed': 0,
            'success': 0,
            'failed': 0,
            'errors': []
        }

        for report in unprocessed:
            try:
                logger.info('processing_report',
                           f"Processing {report.symbol} report by {report.author} ({report.report_date})")

                success = analyzer.analyze_and_save(report)

                results['processed'] += 1
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1

            except Exception as e:
                results['errors'].append(f"{report.symbol}: {str(e)}")
                results['failed'] += 1
                logger.warning('report_error', f"Error processing report {report.id}: {e}")

        logger.success("PDF processing completed", context=results)
        return {"status": "success", **results, "timestamp": timezone.now().isoformat()}

    except Exception as e:
        logger.failure("Error processing analyst report PDFs", error=e)
        return {"status": "error", "error": str(e)}


@shared_task(name='morning_data_sync', bind=True)
def morning_data_sync(self):
    """
    Complete morning data sync (Daily - 7:00 AM)

    Runs the full morning data synchronization sequence:
    1. Fetch and import Trendlyne data (market snapshot, F&O, forecaster)
    2. Fetch and process market news with LLM analysis

    This ensures all data is fresh before the trading day begins.
    """
    logger = TaskLogger(
        task_name='morning_data_sync',
        task_category='data',
        task_id=self.request.id
    )

    logger.start("Starting morning data sync - Trendlyne + Market News")

    results = {
        'trendlyne': None,
        'news': None,
        'timestamp': timezone.now().isoformat()
    }

    # ==========================================================================
    # STEP 1: Fetch and Import Trendlyne Data
    # ==========================================================================
    logger.step('trendlyne', "Step 1/2: Fetching and importing Trendlyne data")

    try:
        from django.core.management import call_command
        from io import StringIO
        from apps.data.models import ContractData, ContractStockData, TLStockData

        output = StringIO()
        call_command('trendlyne_data_manager', '--full-cycle', stdout=output)

        # Get statistics
        trendlyne_stats = {
            'ContractData': ContractData.objects.count(),
            'ContractStockData': ContractStockData.objects.count(),
            'TLStockData': TLStockData.objects.count(),
        }

        results['trendlyne'] = {
            'status': 'success',
            'stats': trendlyne_stats,
            'output': output.getvalue()[:500]
        }

        logger.info('trendlyne_complete', "Trendlyne data sync completed", context=trendlyne_stats)

    except Exception as e:
        results['trendlyne'] = {
            'status': 'error',
            'error': str(e)
        }
        logger.error('trendlyne_failed', f"Trendlyne sync failed: {e}")

    # ==========================================================================
    # STEP 2: Fetch and Process Market News
    # ==========================================================================
    logger.step('news', "Step 2/2: Fetching and processing market news")

    try:
        from apps.data.services.gnews_client import GNewsClient
        from apps.data.models import NewsArticle
        from apps.llm.services.news_processor import get_news_processor
        from datetime import datetime

        gnews_client = GNewsClient()

        # Check if GNews API is configured
        if not gnews_client.api_key:
            results['news'] = {
                'status': 'skipped',
                'reason': 'GNews API key not configured'
            }
            logger.warning('news_skipped', "GNews API key not configured, skipping news fetch")
        else:
            # Fetch market news
            news_result = gnews_client.fetch_market_news(
                max_results_per_keyword=5,
                use_cache=False
            )

            if not news_result.get('success'):
                results['news'] = {
                    'status': 'error',
                    'error': news_result.get('error', 'Unknown error')
                }
                logger.error('news_fetch_failed', f"News fetch failed: {news_result.get('error')}")
            else:
                articles = news_result.get('articles', [])
                news_processor = get_news_processor()

                news_stats = {
                    'fetched': len(articles),
                    'processed': 0,
                    'skipped': 0,
                    'errors': 0
                }

                for article in articles:
                    try:
                        url = article.get('url', '')
                        if url and NewsArticle.objects.filter(url=url).exists():
                            news_stats['skipped'] += 1
                            continue

                        published_at = None
                        if article.get('publishedAt'):
                            try:
                                published_at = datetime.fromisoformat(
                                    article['publishedAt'].replace('Z', '+00:00')
                                )
                            except (ValueError, AttributeError):
                                published_at = timezone.now()

                        success, _, _ = news_processor.process_article(
                            title=article.get('title', 'No Title'),
                            content=article.get('content') or article.get('description', ''),
                            source=article.get('source', {}).get('name', 'GNews'),
                            url=url,
                            published_at=published_at,
                            symbols=[],
                            author=None
                        )

                        if success:
                            news_stats['processed'] += 1
                        else:
                            news_stats['errors'] += 1

                    except Exception:
                        news_stats['errors'] += 1

                results['news'] = {
                    'status': 'success',
                    'stats': news_stats
                }

                logger.info('news_complete', "Market news processing completed", context=news_stats)

    except Exception as e:
        results['news'] = {
            'status': 'error',
            'error': str(e)
        }
        logger.error('news_failed', f"News processing failed: {e}")

    # ==========================================================================
    # Final Summary
    # ==========================================================================
    trendlyne_ok = results['trendlyne'] and results['trendlyne'].get('status') == 'success'
    news_ok = results['news'] and results['news'].get('status') in ['success', 'skipped']

    if trendlyne_ok and news_ok:
        logger.success("Morning data sync completed successfully", context={
            'trendlyne': results['trendlyne'].get('stats'),
            'news': results['news'].get('stats') if results['news'].get('status') == 'success' else results['news'].get('status')
        })
        results['status'] = 'success'
    else:
        logger.warning('partial_success', "Morning data sync completed with some errors")
        results['status'] = 'partial'

    return results


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

    # Fetch analyst reports (Daily 7:00 AM - before market opens)
    'fetch-analyst-reports-daily': {
        'task': 'fetch_analyst_reports_daily',
        'schedule': crontab(hour=7, minute=0, day_of_week='1-5'),
    },

    # Process analyst report PDFs with LLM (Daily 7:30 AM)
    'process-analyst-pdfs': {
        'task': 'process_analyst_report_pdfs',
        'schedule': crontab(hour=7, minute=30, day_of_week='1-5'),
    },
}
"""
