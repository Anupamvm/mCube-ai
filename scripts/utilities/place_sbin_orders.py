#!/usr/bin/env python
"""
Place SBIN December futures orders in batches of 10 lots
Using instrument codes from ICICI SecurityMaster file
"""
import os
import sys
import django
import time
import csv
from decimal import Decimal
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.brokers.integrations.breeze import get_breeze_client, get_nfo_margin
from apps.positions.models import Position
from apps.orders.models import Order
from apps.accounts.models import BrokerAccount
from apps.core.constants import POSITION_STATUS_ACTIVE
from apps.data.models import ContractData
from apps.brokers.utils.security_master import get_futures_instrument

def place_sbin_batch_orders():
    """
    Place SBIN December futures orders
    - Total: 40 lots
    - Batch size: 10 lots each
    - Wait: 10 seconds between batches
    """

    # Check if market is open
    from datetime import datetime
    import pytz

    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)

    # Market hours: 9:15 AM - 3:30 PM IST (Mon-Fri)
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    is_weekday = now.weekday() < 5  # Mon=0, Fri=4
    is_market_hours = market_open <= now <= market_close

    print(f"\n{'='*80}")
    print(f"MARKET STATUS CHECK")
    print(f"{'='*80}")
    print(f"Current Time (IST): {now.strftime('%A, %B %d, %Y - %I:%M:%S %p')}")
    print(f"Market Hours: 9:15 AM - 3:30 PM IST (Mon-Fri)")
    print(f"Is Weekday: {'✅ Yes' if is_weekday else '❌ No (Weekend)'}")
    print(f"Is Market Hours: {'✅ Yes' if is_market_hours else '❌ No'}")
    print(f"Market Status: {'🟢 OPEN' if (is_weekday and is_market_hours) else '🔴 CLOSED'}")
    print(f"{'='*80}\n")

    if not is_weekday:
        print("❌ ERROR: Market is closed (Weekend)")
        print("Please run this script on a weekday (Monday-Friday)")
        return

    if not is_market_hours:
        if now < market_open:
            time_to_open = (market_open - now).total_seconds() / 60
            print(f"❌ ERROR: Market hasn't opened yet")
            print(f"Market opens in {int(time_to_open)} minutes at 9:15 AM IST")
        else:
            print(f"❌ ERROR: Market is closed for the day")
            print(f"Market closed at 3:30 PM IST")
            print(f"Please run this script tomorrow between 9:15 AM - 3:30 PM IST")
        return

    # Configuration
    symbol = 'SBIN'
    expiry_str = '30-Dec-2025'
    direction = 'LONG'
    total_lots = 20
    batch_size = 10
    batches = total_lots // batch_size

    print(f"\n{'='*80}")
    print(f"SBIN FUTURES ORDER PLACEMENT")
    print(f"{'='*80}")
    print(f"Symbol: {symbol}")
    print(f"Expiry: {expiry_str}")
    print(f"Direction: {direction}")
    print(f"Total Lots: {total_lots}")
    print(f"Batch Size: {batch_size} lots")
    print(f"Number of Batches: {batches}")
    print(f"{'='*80}\n")

    # Get instrument details from SecurityMaster
    print(f"\n{'='*80}")
    print(f"READING SECURITY MASTER FILE")
    print(f"{'='*80}")
    print(f"Searching for: {symbol}, Expiry: {expiry_str}, Type: FUTURE")

    instrument = get_futures_instrument(symbol, expiry_str)
    if not instrument:
        print(f"❌ ERROR: Could not get instrument details from SecurityMaster")
        print(f"Please ensure SecurityMaster file is downloaded from:")
        print(f"https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip")
        return

    print(f"\n✅ Instrument Found:")
    print(f"  Token (Instrument Code): {instrument['token']}")
    print(f"  Short Name: {instrument['short_name']}")
    print(f"  Company: {instrument['company_name']}")
    print(f"  Lot Size: {instrument['lot_size']}")
    print(f"  Expiry: {instrument['expiry_date']}")
    print(f"{'='*80}\n")

    # Use instrument data from SecurityMaster
    stock_code = instrument['short_name']  # STABAN for SBIN
    instrument_token = instrument['token']  # Token/instrument code
    lot_size = instrument['lot_size']

    # Get contract info for pricing
    contract = ContractData.objects.filter(
        symbol=symbol,
        option_type='FUTURE',
        expiry='2025-12-30'  # December expiry
    ).first()

    if contract:
        entry_price = float(contract.price)
    else:
        print(f"⚠️  WARNING: Contract not found in database, using fallback price")
        entry_price = 900.0  # Fallback price

    print(f"Contract Details:")
    print(f"  Stock Code: {stock_code}")
    print(f"  Instrument Token: {instrument_token}")
    print(f"  Lot Size: {lot_size}")
    print(f"  Current Price: ₹{entry_price:,.2f}")
    print(f"  Total Quantity per batch: {batch_size * lot_size}")
    print(f"\n")

    # Get broker account
    broker_account = BrokerAccount.objects.filter(broker='ICICI', is_active=True).first()
    if not broker_account:
        print("❌ ERROR: No active ICICI broker account found")
        return

    # Initialize Breeze
    breeze = get_breeze_client()

    # Check margin
    margin_data = get_nfo_margin()
    if margin_data:
        available_margin = float(margin_data.get('cash_limit', 0))
        used_margin = float(margin_data.get('amount_allocated', 0))
        actual_available = available_margin - used_margin
        total_margin_needed = entry_price * lot_size * total_lots * 0.12

        print(f"Margin Check:")
        print(f"  Total Available: ₹{available_margin:,.2f}")
        print(f"  Used: ₹{used_margin:,.2f}")
        print(f"  Free: ₹{actual_available:,.2f}")
        print(f"  Needed for 40 lots: ₹{total_margin_needed:,.2f}")
        print(f"  Status: {'✅ Sufficient' if total_margin_needed < actual_available else '❌ Insufficient'}")
        print(f"\n")

    # Place orders in batches
    successful_orders = []
    failed_orders = []

    for batch_num in range(1, batches + 1):
        print(f"\n{'─'*80}")
        print(f"Batch {batch_num}/{batches} - Placing order for {batch_size} lots ({batch_size * lot_size} quantity)")
        print(f"{'─'*80}")

        quantity = batch_size * lot_size

        # Order parameters - using stock_code from SecurityMaster
        order_params = {
            'stock_code': stock_code,  # Use STABAN from SecurityMaster, not SBIN
            'exchange_code': 'NFO',
            'product': 'futures',
            'action': 'buy',
            'order_type': 'market',
            'quantity': str(quantity),
            'price': '0',
            'validity': 'day',
            'stoploss': '0',
            'disclosed_quantity': '0',
            'expiry_date': expiry_str,
            'right': 'others',
            'strike_price': '0'
        }

        print(f"\nOrder Parameters:")
        for key, value in order_params.items():
            print(f"  {key}: {value}")

        try:
            # Place order via Breeze
            print(f"\n⏳ Placing order via Breeze API...")
            order_response = breeze.place_order(**order_params)

            print(f"\n📥 Breeze API Response:")
            print(f"  Status: {order_response.get('Status')}")
            print(f"  Success: {order_response.get('Success')}")
            print(f"  Error: {order_response.get('Error')}")

            if order_response and order_response.get('Status') == 200:
                order_data = order_response.get('Success', {})
                order_id = order_data.get('order_id', 'UNKNOWN')

                print(f"\n✅ Order Placed Successfully!")
                print(f"  Order ID: {order_id}")

                # Create Position record
                position = Position.objects.create(
                    account=broker_account,
                    strategy_type='MANUAL_FUTURES',
                    instrument=symbol,
                    direction=direction,
                    quantity=batch_size,
                    lot_size=lot_size,
                    entry_price=Decimal(str(entry_price)),
                    current_price=Decimal(str(entry_price)),
                    stop_loss=Decimal('0.00'),
                    target=Decimal('0.00'),
                    expiry_date='2025-12-30',
                    margin_used=Decimal(str(entry_price * lot_size * batch_size * 0.12)),
                    entry_value=Decimal(str(entry_price * lot_size * batch_size)),
                    status=POSITION_STATUS_ACTIVE,
                    averaging_count=0,
                    original_entry_price=Decimal(str(entry_price))
                )

                # Create Order record
                order = Order.objects.create(
                    account=broker_account,
                    position=position,
                    broker_order_id=order_id,
                    instrument=symbol,
                    order_type='MARKET',
                    direction=direction,
                    quantity=quantity,
                    price=Decimal(str(entry_price)),
                    exchange='NFO',
                    status='PENDING'
                )

                successful_orders.append({
                    'batch': batch_num,
                    'order_id': order_id,
                    'lots': batch_size,
                    'quantity': quantity,
                    'position_id': position.id,
                    'order_record_id': order.id
                })

                print(f"  Position ID: {position.id}")
                print(f"  Order Record ID: {order.id}")

            else:
                error_msg = order_response.get('Error', 'Unknown error') if order_response else 'API call failed'
                print(f"\n❌ Order Failed!")
                print(f"  Error: {error_msg}")
                print(f"  Full Response: {order_response}")

                failed_orders.append({
                    'batch': batch_num,
                    'error': error_msg,
                    'response': order_response
                })

        except Exception as e:
            print(f"\n❌ Exception occurred!")
            print(f"  Error: {str(e)}")
            import traceback
            traceback.print_exc()

            failed_orders.append({
                'batch': batch_num,
                'error': str(e),
                'response': None
            })

        # Wait before next batch (except for last batch)
        if batch_num < batches:
            print(f"\n⏸️  Waiting 10 seconds before next batch...")
            time.sleep(10)

    # Summary
    print(f"\n\n{'='*80}")
    print(f"ORDER PLACEMENT SUMMARY")
    print(f"{'='*80}")
    print(f"Total Batches: {batches}")
    print(f"Successful: {len(successful_orders)}")
    print(f"Failed: {len(failed_orders)}")
    print(f"\n")

    if successful_orders:
        print(f"✅ Successful Orders:")
        for order in successful_orders:
            print(f"  Batch {order['batch']}: Order ID {order['order_id']} - {order['lots']} lots ({order['quantity']} qty)")

    if failed_orders:
        print(f"\n❌ Failed Orders:")
        for order in failed_orders:
            print(f"  Batch {order['batch']}: {order['error']}")

    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    place_sbin_batch_orders()
