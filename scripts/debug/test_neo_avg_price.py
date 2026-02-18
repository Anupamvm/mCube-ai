#!/usr/bin/env python
"""
Test script to calculate correct average price from Neo transaction report using FIFO logic.

This script:
1. Fetches current positions from Neo API
2. Fetches trade report (today's trades) from Neo API
3. Shows raw data for analysis
4. Calculates correct weighted average price using FIFO for partial exits
"""
import os
import sys
import django

# Setup Django - compute project root relative to this script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from decimal import Decimal
from datetime import datetime
from apps.brokers.integrations.kotak_neo import (
    _get_authenticated_client,
    _parse_float,
)


def fetch_and_analyze():
    """Fetch Neo data and analyze for correct avg price calculation."""

    print("=" * 80)
    print("NEO POSITION & TRANSACTION ANALYSIS")
    print("=" * 80)

    try:
        client = _get_authenticated_client()
        print("\n✅ Neo client authenticated successfully\n")
    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
        return

    # ═══════════════════════════════════════════════════════════════════════════
    # FETCH POSITIONS
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("1. POSITIONS API RESPONSE")
    print("=" * 80)

    try:
        positions_resp = client.positions()
        raw_positions = positions_resp.get('data', [])

        print(f"\nTotal positions: {len(raw_positions)}")

        for i, p in enumerate(raw_positions):
            print(f"\n--- Position {i+1} ---")
            print(f"  Symbol: {p.get('sym')}")
            print(f"  Trading Symbol: {p.get('trdSym')}")
            print(f"  Lot Size: {p.get('lotSz')}")
            print(f"  Stock Price (LTP): {p.get('stkPrc')}")
            print(f"  CF Buy Qty: {p.get('cfBuyQty')}")
            print(f"  CF Sell Qty: {p.get('cfSellQty')}")
            print(f"  FL Buy Qty (today): {p.get('flBuyQty')}")
            print(f"  FL Sell Qty (today): {p.get('flSellQty')}")
            print(f"  CF Buy Amt: {p.get('cfBuyAmt')}")
            print(f"  CF Sell Amt: {p.get('cfSellAmt')}")
            print(f"  Buy Amt (today): {p.get('buyAmt')}")
            print(f"  Sell Amt (today): {p.get('sellAmt')}")

            # Calculate MTM avg (what broker shows - WRONG for multi-day positions)
            buy_qty = int(p.get('cfBuyQty', 0)) + int(p.get('flBuyQty', 0))
            sell_qty = int(p.get('cfSellQty', 0)) + int(p.get('flSellQty', 0))
            buy_amt = _parse_float(p.get('cfBuyAmt', 0)) + _parse_float(p.get('buyAmt', 0))
            sell_amt = _parse_float(p.get('cfSellAmt', 0)) + _parse_float(p.get('sellAmt', 0))
            net_qty = buy_qty - sell_qty

            mtm_avg = buy_amt / buy_qty if buy_qty > 0 else 0

            print(f"\n  [Calculated from positions API]:")
            print(f"  Net Qty: {net_qty} shares")
            print(f"  MTM Avg (WRONG for carry-forward): {mtm_avg:.2f}")

    except Exception as e:
        print(f"\n❌ Error fetching positions: {e}")
        import traceback
        traceback.print_exc()

    # ═══════════════════════════════════════════════════════════════════════════
    # FETCH TRADE REPORT (TODAY'S TRADES)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("2. TRADE REPORT API RESPONSE (Today's Trades)")
    print("=" * 80)

    try:
        trade_resp = client.trade_report()
        raw_trades = []

        if isinstance(trade_resp, dict) and 'Error' not in trade_resp:
            raw_trades = trade_resp.get('data', [])
            if not isinstance(raw_trades, list):
                raw_trades = []

        print(f"\nTotal trades today: {len(raw_trades)}")

        # Group trades by symbol
        trades_by_symbol = {}
        for t in raw_trades:
            tsym = t.get('trdSym', '')
            sym = t.get('sym', '')
            if not tsym:
                continue

            if tsym not in trades_by_symbol:
                trades_by_symbol[tsym] = {'buys': [], 'sells': [], 'sym': sym}

            filled_qty = int(float(t.get('fldQty', 0) or 0))
            avg_prc = _parse_float(t.get('avgPrc', 0))
            trans_type = t.get('trnsTp', '')
            fill_date = t.get('flDt', '')
            fill_time = t.get('flTm', '')
            order_no = t.get('nOrdNo', '')

            trade_info = {
                'qty': filled_qty,
                'price': avg_prc,
                'date': fill_date,
                'time': fill_time,
                'order_no': order_no,
            }

            if trans_type == 'B':
                trades_by_symbol[tsym]['buys'].append(trade_info)
            elif trans_type == 'S':
                trades_by_symbol[tsym]['sells'].append(trade_info)

        for tsym, data in trades_by_symbol.items():
            print(f"\n--- {tsym} ({data['sym']}) ---")

            if data['buys']:
                print(f"\n  BUYS:")
                total_buy_qty = 0
                total_buy_value = 0
                for b in data['buys']:
                    print(f"    {b['date']} {b['time']}: {b['qty']} @ {b['price']:.2f} (Order: {b['order_no']})")
                    total_buy_qty += b['qty']
                    total_buy_value += b['qty'] * b['price']
                print(f"    Total: {total_buy_qty} shares, Value: {total_buy_value:.2f}")
                if total_buy_qty > 0:
                    print(f"    Weighted Avg Buy: {total_buy_value/total_buy_qty:.2f}")

            if data['sells']:
                print(f"\n  SELLS:")
                total_sell_qty = 0
                total_sell_value = 0
                for s in data['sells']:
                    print(f"    {s['date']} {s['time']}: {s['qty']} @ {s['price']:.2f} (Order: {s['order_no']})")
                    total_sell_qty += s['qty']
                    total_sell_value += s['qty'] * s['price']
                print(f"    Total: {total_sell_qty} shares, Value: {total_sell_value:.2f}")
                if total_sell_qty > 0:
                    print(f"    Weighted Avg Sell: {total_sell_value/total_sell_qty:.2f}")

        if not trades_by_symbol:
            print("\nNo trades today. Position is pure carry-forward from previous days.")

    except Exception as e:
        print(f"\n❌ Error fetching trade report: {e}")
        import traceback
        traceback.print_exc()

    # ═══════════════════════════════════════════════════════════════════════════
    # CHECK ORDER HISTORY FOR MORE DETAILS
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("3. ORDER REPORT API RESPONSE")
    print("=" * 80)

    try:
        order_resp = client.order_report()
        raw_orders = []

        if isinstance(order_resp, dict) and 'Error' not in order_resp:
            raw_orders = order_resp.get('data', [])
            if not isinstance(raw_orders, list):
                raw_orders = []

        print(f"\nTotal orders: {len(raw_orders)}")

        # Show executed orders
        executed_orders = [o for o in raw_orders if o.get('ordSt') == 'complete']
        print(f"Executed orders: {len(executed_orders)}")

        for o in executed_orders:
            print(f"\n  {o.get('trdSym')}: {o.get('trnsTp')} {o.get('fldQty')} @ {o.get('avgPrc')}")
            print(f"    Order ID: {o.get('nOrdNo')}, Status: {o.get('ordSt')}")
            print(f"    Time: {o.get('ordDtTm')}")

    except Exception as e:
        print(f"\n❌ Error fetching order report: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # CHECK APP'S POSITION MODEL
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("4. APP'S POSITION MODEL (Source of Truth)")
    print("=" * 80)

    try:
        from apps.positions.models import Position, POSITION_STATUS_OPEN

        open_positions = Position.objects.filter(status=POSITION_STATUS_OPEN)
        print(f"\nOpen positions in app DB: {open_positions.count()}")

        for pos in open_positions:
            print(f"\n  Instrument: {pos.instrument}")
            print(f"  Direction: {pos.direction}")
            print(f"  Quantity (lots): {pos.quantity}")
            print(f"  Lot Size: {pos.lot_size}")
            print(f"  Entry Price: {pos.entry_price}")
            print(f"  Original Entry Price: {pos.original_entry_price}")
            print(f"  Current Price: {pos.current_price}")
            print(f"  Averaging Count: {pos.averaging_count}")
            print(f"  Created: {pos.created_at}")

    except Exception as e:
        print(f"\n❌ Error fetching app positions: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # CHECK BROKER POSITION HISTORY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("5. BROKER POSITION HISTORY (Last 5 records)")
    print("=" * 80)

    try:
        from apps.brokers.models import BrokerPosition

        # Get last 5 NIFTY positions
        broker_positions = BrokerPosition.objects.filter(
            broker='KOTAK',
            symbol__icontains='NIFTY'
        ).order_by('-fetched_at')[:5]

        print(f"\nRecent BrokerPosition records:")

        for bp in broker_positions:
            print(f"\n  {bp.fetched_at}:")
            print(f"    Symbol: {bp.symbol}")
            print(f"    Trading Symbol: {bp.trading_symbol}")
            print(f"    Net Qty: {bp.net_quantity}")
            print(f"    Lot Size: {bp.lot_size}")
            print(f"    Average Price: {bp.average_price}")
            print(f"    LTP: {bp.ltp}")
            print(f"    Unrealized P&L: {bp.unrealized_pnl}")

    except Exception as e:
        print(f"\n❌ Error fetching broker position history: {e}")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print("""
NOTES:
- The 'positions' API returns MTM-settled values that reset daily
- cfBuyAmt/cfBuyQty is yesterday's settlement price, NOT original entry
- trade_report() only shows TODAY's trades
- For correct avg price, we need the original entry trades from when position was opened
- Use app's Position model entry_price as source of truth
- For partial exits, use FIFO: first lots bought are first lots sold
    """)


if __name__ == '__main__':
    fetch_and_analyze()
