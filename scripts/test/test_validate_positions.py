#!/usr/bin/env python3
"""
Validate Neo and Breeze positions with P&L calculations
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/Users/anupammangudkar/PyProjects/mCube-ai')
os.environ['DJANGO_SETTINGS_MODULE'] = 'mcube_ai.settings'
django.setup()

from apps.brokers.integrations.kotak_neo import get_kotak_neo_client, get_ltp_from_neo
from apps.brokers.integrations.breeze import get_breeze_client

def test_neo_positions():
    """Test Neo positions with P&L calculations"""
    print("=" * 100)
    print("📊 NEO (KOTAK) POSITIONS")
    print("=" * 100)

    try:
        client = get_kotak_neo_client()
        resp = client.positions()
        positions = resp.get('data', [])

        print(f"\n✅ Found {len(positions)} positions\n")

        total_pnl = 0

        for idx, pos in enumerate(positions, 1):
            symbol = pos.get('trdSym')
            lot_sz = int(pos.get('lotSz', 1))

            # Quantities
            cf_buy_qty = int(pos.get('cfBuyQty', 0))
            cf_sell_qty = int(pos.get('cfSellQty', 0))
            fl_buy_qty = int(pos.get('flBuyQty', 0))
            fl_sell_qty = int(pos.get('flSellQty', 0))

            total_buy_qty = cf_buy_qty + fl_buy_qty
            total_sell_qty = cf_sell_qty + fl_sell_qty
            net_qty_shares = total_buy_qty - total_sell_qty
            net_qty_lots = net_qty_shares // lot_sz if lot_sz > 0 else 0

            if net_qty_lots == 0:
                continue

            # Amounts
            buy_amt = float(pos.get('cfBuyAmt', 0)) + float(pos.get('buyAmt', 0))
            sell_amt = float(pos.get('cfSellAmt', 0)) + float(pos.get('sellAmt', 0))

            # Average price (simple: Total Amt / Total Qty)
            if net_qty_lots > 0:  # LONG
                avg_price = buy_amt / total_buy_qty if total_buy_qty > 0 else 0
                direction = 'LONG'
            else:  # SHORT
                avg_price = sell_amt / total_sell_qty if total_sell_qty > 0 else 0
                direction = 'SHORT'

            # Get LTP
            ltp = get_ltp_from_neo(symbol)

            # Calculate P&L
            if net_qty_lots > 0:  # LONG
                unrealized_pnl = (ltp - avg_price) * net_qty_shares if ltp else 0
            else:  # SHORT
                unrealized_pnl = (avg_price - ltp) * abs(net_qty_shares) if ltp else 0

            total_pnl += unrealized_pnl

            print(f"\n{idx}. {symbol}")
            print(f"   Direction: {direction}")
            print(f"   Quantity: {abs(net_qty_lots)} lots ({abs(net_qty_shares)} shares)")
            print(f"   Average Price: ₹{avg_price:.2f}")
            print(f"   Current LTP: ₹{ltp:.2f}" if ltp else "   Current LTP: N/A")
            print(f"   Unrealized P&L: ₹{unrealized_pnl:,.2f}")
            print(f"   P&L %: {(unrealized_pnl / (avg_price * abs(net_qty_shares)) * 100):.2f}%" if avg_price > 0 else "   P&L %: N/A")

        print("\n" + "=" * 100)
        print(f"TOTAL UNREALIZED P&L: ₹{total_pnl:,.2f}")
        print("=" * 100)

    except Exception as e:
        print(f"\n❌ Error fetching Neo positions: {e}")
        import traceback
        traceback.print_exc()


def test_breeze_positions():
    """Test Breeze positions with P&L calculations"""
    print("\n\n" + "=" * 100)
    print("📊 BREEZE (ICICI) POSITIONS")
    print("=" * 100)

    try:
        breeze = get_breeze_client()
        resp = breeze.get_portfolio_positions()

        if not resp or resp.get('Status') != 200:
            print(f"\n❌ Breeze API error: {resp}")
            return

        positions = resp.get('Success', [])
        print(f"\n✅ Found {len(positions)} positions\n")

        total_pnl = 0
        position_count = 0

        for pos in positions:
            quantity = int(pos.get('quantity', 0))

            if quantity == 0:
                continue

            position_count += 1

            symbol = pos.get('stock_code', 'N/A')
            avg_price = float(pos.get('average_price', 0))
            ltp = float(pos.get('ltp', 0) or pos.get('price', 0))

            if quantity > 0:  # LONG
                unrealized_pnl = (ltp - avg_price) * quantity
                direction = 'LONG'
            else:  # SHORT
                unrealized_pnl = (avg_price - ltp) * abs(quantity)
                direction = 'SHORT'

            total_pnl += unrealized_pnl

            print(f"\n{position_count}. {symbol}")
            print(f"   Direction: {direction}")
            print(f"   Quantity: {abs(quantity)}")
            print(f"   Average Price: ₹{avg_price:.2f}")
            print(f"   Current LTP: ₹{ltp:.2f}")
            print(f"   Unrealized P&L: ₹{unrealized_pnl:,.2f}")
            print(f"   P&L %: {(unrealized_pnl / (avg_price * abs(quantity)) * 100):.2f}%" if avg_price > 0 else "   P&L %: N/A")

        print("\n" + "=" * 100)
        print(f"TOTAL UNREALIZED P&L: ₹{total_pnl:,.2f}")
        print("=" * 100)

    except Exception as e:
        print(f"\n❌ Error fetching Breeze positions: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_neo_positions()
    test_breeze_positions()

    print("\n\n" + "=" * 100)
    print("✅ VALIDATION COMPLETE")
    print("=" * 100)
