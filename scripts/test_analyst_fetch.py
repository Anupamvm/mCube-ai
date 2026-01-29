#!/usr/bin/env python
"""
Test script for Trendlyne analyst data fetching.

Usage:
    python scripts/test_analyst_fetch.py HDFCBANK
    python scripts/test_analyst_fetch.py RELIANCE
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from apps.data.providers.trendlyne import TrendlyneProvider


def test_analyst_fetch(symbol: str, save_to_db: bool = True):
    """Test fetching analyst data for a symbol"""
    print(f"\n{'='*60}")
    print(f"Testing analyst data fetch for: {symbol}")
    print(f"{'='*60}\n")

    try:
        with TrendlyneProvider(headless=False) as provider:  # headless=False to see what's happening
            print("[1] Initializing Chrome driver...")
            provider.init_driver()

            print("[2] Logging into Trendlyne...")
            login_result = provider.login()
            print(f"    Login result: {login_result}")

            if not login_result:
                print("    ERROR: Login failed!")
                return

            print(f"\n[3] Fetching price target for {symbol}...")
            price_target = provider.fetch_analyst_price_target(symbol)

            print("\n    Price Target Results:")
            print(f"    - Success: {price_target.get('success')}")
            print(f"    - Current Price: {price_target.get('current_price')}")
            print(f"    - Avg Target Price: {price_target.get('avg_target_price')}")
            print(f"    - Upside %: {price_target.get('upside_pct')}")
            print(f"    - Analyst Count: {price_target.get('analyst_count')}")
            print(f"    - Strong Buy: {price_target.get('strong_buy_count')}")
            print(f"    - Buy: {price_target.get('buy_count')}")
            print(f"    - Hold: {price_target.get('hold_count')}")
            print(f"    - Sell: {price_target.get('sell_count')}")
            print(f"    - Strong Sell: {price_target.get('strong_sell_count')}")
            print(f"    - Trendlyne ID: {price_target.get('trendlyne_id')}")
            print(f"    - Source URL: {price_target.get('source_url')}")

            # Check if data was found
            has_data = price_target.get('avg_target_price') or price_target.get('analyst_count', 0) > 0
            if has_data:
                print("\n    ✅ Price target data was successfully scraped!")
            else:
                print("\n    ⚠️ No price target data found - page structure may have changed")
                print("    Check the debug HTML file saved in apps/data/tldata/debug_html/")

            print(f"\n[4] Fetching analyst reports for {symbol}...")
            reports = provider.fetch_analyst_reports(
                symbol=symbol,
                trendlyne_id=price_target.get('trendlyne_id'),
                months_back=3,
                download_pdfs=False
            )

            print("\n    Reports Results:")
            print(f"    - Success: {reports.get('success')}")
            print(f"    - Reports Found: {reports.get('count', 0)}")

            if reports.get('reports'):
                for i, report in enumerate(reports['reports'][:5]):  # Show first 5
                    print(f"\n    Report {i+1}:")
                    print(f"      - Date: {report.get('report_date')}")
                    print(f"      - Author: {report.get('author')}")
                    print(f"      - Target: {report.get('target_price')}")
                    print(f"      - Recommendation: {report.get('recommendation_type')}")
            else:
                print("    No reports found.")

            # Save to database if requested
            if save_to_db and has_data:
                print(f"\n[5] Saving data to database...")
                from apps.data.models import AnalystPriceTarget, AnalystReport

                # Save price target
                trendlyne_id = price_target.get('trendlyne_id')
                pt_obj, created = AnalystPriceTarget.objects.update_or_create(
                    nse_code=symbol,
                    defaults={
                        'symbol': symbol,
                        'trendlyne_id': trendlyne_id,
                        'stock_name': symbol,
                        'current_price': price_target.get('current_price'),
                        'avg_target_price': price_target.get('avg_target_price'),
                        'upside_pct': price_target.get('upside_pct'),
                        'analyst_count': price_target.get('analyst_count', 0),
                        'strong_buy_count': price_target.get('strong_buy_count', 0),
                        'buy_count': price_target.get('buy_count', 0),
                        'hold_count': price_target.get('hold_count', 0),
                        'sell_count': price_target.get('sell_count', 0),
                        'strong_sell_count': price_target.get('strong_sell_count', 0),
                        'source_url': price_target.get('source_url', ''),
                        'scrape_success': True,
                    }
                )
                print(f"    ✅ Price target {'created' if created else 'updated'} in database (ID: {pt_obj.id})")

                # Save reports
                reports_saved = 0
                for report in reports.get('reports', []):
                    if report.get('report_date'):
                        try:
                            AnalystReport.objects.update_or_create(
                                symbol=symbol,
                                report_date=report.get('report_date'),
                                author=report.get('author', '')[:200],
                                defaults={
                                    'nse_code': symbol,
                                    'trendlyne_id': trendlyne_id,
                                    'ltp_at_report': report.get('ltp_at_report'),
                                    'target_price': report.get('target_price'),
                                    'upside_pct': report.get('upside_pct'),
                                    'recommendation_type': report.get('recommendation_type', 'UNKNOWN'),
                                    'pdf_url': report.get('pdf_url', ''),
                                }
                            )
                            reports_saved += 1
                        except Exception as e:
                            print(f"    Warning: Could not save report: {e}")

                print(f"    ✅ Saved {reports_saved} analyst reports to database")
                print(f"\n    Now try the Verify Trade button in the UI for {symbol}!")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_analyst_fetch.py <SYMBOL> [--no-save]")
        print("Example: python scripts/test_analyst_fetch.py HDFCBANK")
        print("         python scripts/test_analyst_fetch.py HDFCBANK --no-save")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    save_to_db = '--no-save' not in sys.argv

    test_analyst_fetch(symbol, save_to_db=save_to_db)
