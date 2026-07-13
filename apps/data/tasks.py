"""
Celery tasks for automated data fetching and processing

Schedule these tasks with Celery Beat for continuous data updates
"""

from celery import shared_task
from django.utils import timezone

from .providers.trendlyne import get_all_trendlyne_data
from .importers import TrendlyneDataImporter, ContractStockDataImporter
from .broker_integration import ScheduledDataUpdater
from .signals import SignalGenerator

# Import TaskLogger and task guard
from apps.core.utils.task_logger import TaskLogger
from apps.core.utils.decorators import task_enabled_guard
from apps.alerts.services.telegram_client import send_telegram_notification


@shared_task(name='fetch_trendlyne_data', bind=True, max_retries=3)
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
            'error_type': type(e).__name__,
            'retry': self.request.retries,
        })
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=int(60 * (2 ** self.request.retries)))
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


@shared_task(name='process_oi_intelligence', bind=True)
@task_enabled_guard('process-oi-intelligence')
def process_oi_intelligence_task(self):
    """
    Process OI Intelligence for all F&O stocks (Daily ~9:15 AM, after import_trendlyne_data)

    Captures daily OI snapshots, computes momentum scores and pattern analysis,
    and saves OIIntelligence records used by the futures analysis engine.
    """
    task_logger = TaskLogger(
        task_name='process_oi_intelligence',
        task_category='data',
        task_id=self.request.id
    )

    task_logger.start("Starting OI Intelligence processing")

    try:
        from apps.data.services.oi_intelligence_engine import run_daily_oi_intelligence

        task_logger.step('processing', "Running OI intelligence engine for all F&O stocks")
        result = run_daily_oi_intelligence()

        msg = (
            f"OI Intelligence complete — "
            f"Processed: {result['processed']} | Skipped: {result['errors']} | "
            f"Total: {result['total']}"
        )
        task_logger.success(msg, context=result)

        send_telegram_notification(
            f"📊 *OI Intelligence Engine*\n"
            f"✅ Processed: {result['processed']} stocks\n"
            f"⚠️ Skipped: {result['errors']} stocks\n"
            f"📅 Date: {timezone.localdate()}"
        )

        return {"status": "success", **result}

    except Exception as e:
        task_logger.failure("OI Intelligence processing failed", error=e)
        return {"status": "error", "error": str(e)}


@shared_task(name='update_live_market_data', bind=True, max_retries=3)
@task_enabled_guard('update-live-market-data')
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
        logger.failure("Error updating live market data", error=e, context={'retry': self.request.retries})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=int(30 * (2 ** self.request.retries)))
        return {"status": "error", "error": str(e)}


@shared_task(name='update_pre_market_data', bind=True, max_retries=3)
@task_enabled_guard('update-pre-market-data')
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
        logger.failure("Error updating pre-market data", error=e, context={'retry': self.request.retries})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=int(30 * (2 ** self.request.retries)))
        return {"status": "error", "error": str(e)}


@shared_task(name='update_post_market_data', bind=True, max_retries=3)
@task_enabled_guard('update-post-market-data')
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
        logger.failure("Error updating post-market data", error=e, context={'retry': self.request.retries})
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=int(30 * (2 ** self.request.retries)))
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

        # Get ALL F&O stocks (including those without trendlyne_id)
        fno_symbols = set(ContractStockData.objects.values_list('nse_code', flat=True))
        all_fno_stocks = TLStockData.objects.filter(
            nsecode__in=fno_symbols
        ).values('nsecode', 'trendlyne_id', 'stock_name')

        stocks_with_id = [s for s in all_fno_stocks if s['trendlyne_id']]
        stocks_without_id = [s for s in all_fno_stocks if not s['trendlyne_id']]

        logger.step('fetching', f"Found {len(stocks_with_id)} F&O stocks with trendlyne_id, {len(stocks_without_id)} without")

        results = {
            'processed': 0,
            'price_targets_saved': 0,
            'reports_saved': 0,
            'errors': []
        }

        results['ids_discovered'] = 0

        with TrendlyneProvider() as provider:
            # Login once
            if not provider.login():
                logger.error('login_failed', "Could not login to Trendlyne")
                return {"status": "error", "error": "Trendlyne login failed"}

            # Process ALL F&O stocks (with and without trendlyne_id)
            # Stocks without ID will have it discovered via URL redirect
            all_stocks = list(stocks_with_id) + list(stocks_without_id)

            for stock in all_stocks:
                try:
                    symbol = stock['nsecode']
                    trendlyne_id = stock['trendlyne_id']  # May be None

                    logger.info('processing_stock', f"Processing {symbol} (ID: {trendlyne_id or 'discovering...'})")

                    # Fetch analyst data (will discover trendlyne_id if None)
                    data = provider.fetch_analyst_data(
                        symbol=symbol,
                        trendlyne_id=trendlyne_id,
                        months_back=3,
                        download_pdfs=True
                    )

                    if not data.get('success'):
                        results['errors'].append(f"{symbol}: {data.get('error', 'Unknown error')}")
                        continue

                    # Update trendlyne_id if discovered
                    extracted_id = data.get('trendlyne_id')
                    if extracted_id and not trendlyne_id:
                        try:
                            TLStockData.objects.filter(
                                nsecode__iexact=symbol,
                                trendlyne_id__isnull=True
                            ).update(trendlyne_id=extracted_id)
                            results['ids_discovered'] += 1
                            logger.info('id_discovered', f"Discovered trendlyne_id for {symbol}: {extracted_id}")
                        except Exception:
                            pass
                    # Use extracted_id for saving (fallback to original)
                    save_id = extracted_id or trendlyne_id

                    # Save price target
                    price_target_data = data.get('price_target', {})
                    if price_target_data.get('success'):
                        AnalystPriceTarget.objects.update_or_create(
                            nse_code=symbol,
                            defaults={
                                'symbol': symbol,
                                'trendlyne_id': save_id,
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
                                    'trendlyne_id': save_id,
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


@shared_task(name='sync_trendlyne_ids', bind=True)
def sync_trendlyne_ids(self):
    """
    Discover and sync trendlyne_ids for all F&O stocks (Daily - after data import)

    Visits Trendlyne stock list pages to extract trendlyne_ids from
    equity links (/equity/{id}/{SYMBOL}/) and updates TLStockData records.
    This is needed because the Excel/CSV data downloads don't include IDs.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from apps.data.models import TLStockData, ContractStockData
        from apps.data.providers.trendlyne import TrendlyneProvider

        # Check how many F&O stocks are missing IDs
        fno_symbols = set(ContractStockData.objects.values_list('nse_code', flat=True))
        missing_ids = TLStockData.objects.filter(
            nsecode__in=fno_symbols,
            trendlyne_id__isnull=True
        ).count()

        if missing_ids == 0:
            logger.info("[Sync IDs] All F&O stocks already have trendlyne_ids")
            return {"status": "success", "message": "All IDs already populated", "missing": 0}

        logger.info(f"[Sync IDs] {missing_ids} F&O stocks missing trendlyne_id, starting discovery...")

        with TrendlyneProvider(headless=True) as provider:
            provider.init_driver()
            if not provider.login():
                logger.error("[Sync IDs] Trendlyne login failed")
                return {"status": "error", "error": "Login failed"}

            # Discover IDs from stock list pages
            missing_symbols = list(TLStockData.objects.filter(
                nsecode__in=fno_symbols,
                trendlyne_id__isnull=True
            ).values_list('nsecode', flat=True))

            discovered = provider.discover_trendlyne_ids(symbols=missing_symbols)

            # Count how many were actually updated
            still_missing = TLStockData.objects.filter(
                nsecode__in=fno_symbols,
                trendlyne_id__isnull=True
            ).count()

            result = {
                "status": "success",
                "discovered": len(discovered),
                "previously_missing": missing_ids,
                "still_missing": still_missing,
                "updated": missing_ids - still_missing,
                "timestamp": timezone.now().isoformat()
            }
            logger.info(f"[Sync IDs] Complete: {result}")
            return result

    except Exception as e:
        logger.error(f"[Sync IDs] Error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name='morning_data_sync', bind=True)
@task_enabled_guard('morning-data-sync')
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
        send_telegram_notification(f"⚠️ *Morning Data Sync Failed*\n\nTrendlyne download/import failed — market data is stale.\n\n`{str(e)[:300]}`")

    # ==========================================================================
    # STEP 1b: Sync Trendlyne IDs (if step 1 succeeded)
    # ==========================================================================
    if results['trendlyne'] and results['trendlyne'].get('status') == 'success':
        try:
            logger.step('sync_ids', "Step 1b: Syncing trendlyne_ids for F&O stocks")
            id_result = sync_trendlyne_ids.apply()
            id_data = id_result.result if id_result else {}
            results['trendlyne_ids'] = id_data
            logger.info('ids_synced', f"Trendlyne IDs synced: {id_data.get('updated', 0)} updated, {id_data.get('still_missing', '?')} still missing")
        except Exception as e:
            results['trendlyne_ids'] = {'status': 'error', 'error': str(e)}
            logger.warning('ids_sync_failed', f"Trendlyne ID sync failed (non-critical): {e}")

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

                # Google News supplemental fetch (non-critical)
                try:
                    from apps.data.services.google_news_scraper import get_google_news_scraper
                    gn_result = get_google_news_scraper().fetch_market_news(max_results=20)
                    gn_articles = gn_result.get('articles', [])

                    gn_stats = {'fetched': len(gn_articles), 'processed': 0, 'skipped': 0, 'errors': 0}

                    for article in gn_articles:
                        try:
                            url = article.get('url', '')
                            if url and NewsArticle.objects.filter(url=url).exists():
                                gn_stats['skipped'] += 1
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
                                source=article.get('source', {}).get('name', 'GoogleNews'),
                                url=url,
                                published_at=published_at,
                                symbols=[],
                                author=None
                            )
                            if success:
                                gn_stats['processed'] += 1
                            else:
                                gn_stats['errors'] += 1
                        except Exception:
                            gn_stats['errors'] += 1

                    news_stats['google_news'] = gn_stats
                    logger.info('google_news_complete', "Google News processing completed", context=gn_stats)

                except Exception as e:
                    logger.warning(f"[MorningSync] Google News failed (non-critical): {e}")

                # Pre-fetch sector news for top 10 sectors so articles have LLM
                # sentiment scores by the time the 9:40 AM algorithm runs.
                try:
                    from apps.data.models import TLStockData, NewsArticle
                    from apps.data.services.gnews_client import get_gnews_client
                    from apps.llm.services.news_impact_analyzer import NewsImpactAnalyzer

                    top_sectors = list(
                        TLStockData.objects.exclude(sector_name__isnull=True)
                        .exclude(sector_name='')
                        .values_list('sector_name', flat=True)
                        .distinct()[:10]
                    )
                    gnews_sector = get_gnews_client()
                    analyzer = NewsImpactAnalyzer()
                    sector_fetched = 0

                    for sector in top_sectors:
                        try:
                            result = gnews_sector.fetch_industry_news(industry=sector, max_results=3)
                            for art in result.get('articles', []):
                                url = art.get('url', '')
                                if url and NewsArticle.objects.filter(url=url).exists():
                                    continue
                                content = art.get('content') or art.get('description', '')
                                # Run market impact analysis for sentiment score
                                impact = analyzer.analyze_market_article_impact(art)
                                source = art.get('source', {}).get('name', 'GNews')
                                from apps.llm.services.news_processor import _get_source_quality
                                na = NewsArticle.objects.create(
                                    title=art.get('title', ''),
                                    content=content,
                                    source=source,
                                    url=url,
                                    published_at=timezone.now(),
                                    news_type='INDUSTRY',
                                    sectors_mentioned=[sector],
                                    sentiment_score=impact.get('impact_score'),
                                    sentiment_label='POSITIVE' if (impact.get('impact_score') or 0) > 0.3 else (
                                        'NEGATIVE' if (impact.get('impact_score') or 0) < -0.3 else 'NEUTRAL'
                                    ),
                                    impact_reasoning=impact.get('reasoning', ''),
                                    source_quality_score=_get_source_quality(source),
                                    event_type=impact.get('event_type', ''),
                                )
                                sector_fetched += 1
                        except Exception:
                            pass

                    logger.info(f"[MorningSync] Sector news pre-fetched: {sector_fetched} articles across {len(top_sectors)} sectors")
                except Exception as e:
                    logger.warning(f"[MorningSync] Sector news pre-fetch failed (non-critical): {e}")

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
        tl_stats = results['trendlyne'].get('stats', {})
        news_stats = results['news'].get('stats', {}) if results['news'].get('status') == 'success' else {}
        logger.success("Morning data sync completed successfully", context={
            'trendlyne': tl_stats,
            'news': news_stats or results['news'].get('status')
        })
        gn_stats = news_stats.get('google_news', {})
        gn_line = f" | GNews: {gn_stats.get('processed', 0)} new" if gn_stats else ""
        send_telegram_notification(
            f"✅ *Morning Data Sync Complete*\n\n"
            f"F&O: {tl_stats.get('ContractData', '?')} | Stocks: {tl_stats.get('TLStockData', '?')}\n"
            f"News: {news_stats.get('processed', 0)} processed, {news_stats.get('skipped', 0)} skipped{gn_line}"
        )
        results['status'] = 'success'
    elif trendlyne_ok and not news_ok:
        logger.warning('partial_success', "Morning data sync completed with news errors")
        results['status'] = 'partial'
    else:
        logger.warning('partial_success', "Morning data sync completed with some errors")
        results['status'] = 'partial'

    return results


@shared_task(name='fetch_exchange_filings', bind=True)
@task_enabled_guard(['fetch-exchange-filings-morning', 'fetch-exchange-filings-midday', 'fetch-exchange-filings-eod'])
def fetch_exchange_filings(self):
    """
    Fetch NSE/BSE corporate announcements and store as NewsArticle records (3× daily).

    Runs at 7:30 AM, 12:00 PM, and 3:45 PM IST on weekdays.

    Stored articles get:
      - source_quality_score = 1.0 (exchange-grade authority)
      - news_type = 'STOCK'
      - event_type classified from filing subject
      - symbols_mentioned resolved via SymbolExtractor
      - sentiment_score populated via LLM (so futures algorithm can use them immediately)
    """
    logger = TaskLogger(
        task_name='fetch_exchange_filings',
        task_category='data',
        task_id=self.request.id
    )
    logger.start("Fetching NSE/BSE exchange filings")

    try:
        from apps.data.services.exchange_filings_client import get_exchange_filings_client
        stats = get_exchange_filings_client().fetch_and_store_all(hours_back=4)

        total_new = stats['nse'] + stats['bse']
        summary = (
            f"Exchange filings complete: NSE={stats['nse']}, BSE={stats['bse']}, "
            f"skipped={stats['skipped']}, errors={stats['errors']}"
        )
        logger.success(summary, context=stats)

        # Run LLM sentiment analysis on newly stored filings so they are immediately
        # usable by the futures algorithm (which skips articles with sentiment_score=None).
        scored = 0
        if total_new > 0:
            try:
                from apps.data.models import NewsArticle, ContractStockData
                from apps.llm.services.news_impact_analyzer import NewsImpactAnalyzer
                from datetime import timedelta

                analyzer = NewsImpactAnalyzer()
                cutoff = timezone.now() - timedelta(hours=4)

                # Build a symbol→name lookup for LLM context
                sym_to_name = dict(
                    ContractStockData.objects.values_list('nse_code', 'stock_name')
                )

                unscored = NewsArticle.objects.filter(
                    source__in=['NSE', 'BSE'],
                    news_type='STOCK',
                    published_at__gte=cutoff,
                    sentiment_score__isnull=True,
                ).order_by('-published_at')[:50]

                for article in unscored:
                    try:
                        symbols = article.symbols_mentioned or []
                        nse_sym = symbols[0] if symbols else ''
                        company = sym_to_name.get(nse_sym, nse_sym or article.source)

                        art_dict = {
                            'title': article.title,
                            'description': article.summary or '',
                            'content': article.content or article.summary or '',
                        }
                        result = analyzer.analyze_article_impact(
                            article=art_dict,
                            stock_symbol=nse_sym or 'MARKET',
                            stock_name=company,
                            trade_direction='LONG',  # LONG direction → positive score = bullish
                        )
                        score = result.get('impact_score')
                        if score is not None:
                            raw_label = result.get('impact_label', '')
                            # Map 5-value LLM label → 3-value DB choices
                            label = (
                                'POSITIVE' if raw_label in ('POSITIVE', 'HIGHLY_POSITIVE')
                                else 'NEGATIVE' if raw_label in ('NEGATIVE', 'HIGHLY_NEGATIVE')
                                else 'NEUTRAL'
                            )
                            article.sentiment_score = score
                            article.sentiment_label = label
                            article.impact_reasoning = result.get('reasoning', '')
                            # Preserve event_type from filing classification unless LLM gives a
                            # more specific one (LLM can upgrade REGULATORY → EARNINGS, etc.)
                            if result.get('event_type') and not article.event_type:
                                article.event_type = result['event_type']
                            article.already_priced_in = result.get('already_priced_in')
                            article.save(update_fields=[
                                'sentiment_score', 'sentiment_label',
                                'impact_reasoning', 'event_type', 'already_priced_in',
                            ])
                            scored += 1
                    except Exception as ex:
                        logger.warning('llm_score_failed', f"LLM scoring failed for filing {article.id}: {ex}")

                logger.info('llm_scoring_complete', f"LLM-scored {scored}/{total_new} new exchange filings")
            except Exception as e:
                logger.warning('llm_scoring_error', f"Exchange filings LLM scoring failed (non-critical): {e}")

        notification_parts = [f"📋 *Exchange Filings*: {total_new} new (NSE: {stats['nse']}, BSE: {stats['bse']})"]
        if scored > 0:
            notification_parts.append(f"🧠 Scored: {scored}")
        if total_new > 0:
            send_telegram_notification(" | ".join(notification_parts))

        stats['llm_scored'] = scored
        return stats

    except Exception as e:
        logger.error('failed', f"Exchange filings fetch failed: {e}")
        return {'status': 'error', 'error': str(e)}


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
