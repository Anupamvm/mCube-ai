#!/usr/bin/env python
"""
Test SecurityMaster parsing for SBIN futures
"""
import csv
import os

def test_security_master_parsing():
    """Test reading SBIN December futures from SecurityMaster"""

    security_master_path = '/Users/anupammangudkar/Downloads/SecurityMaster/FONSEScripMaster.txt'
    symbol = 'SBIN'
    expiry_date = '30-Dec-2025'

    print(f"\n{'='*80}")
    print(f"TESTING SECURITY MASTER PARSING")
    print(f"{'='*80}")
    print(f"File: {security_master_path}")
    print(f"Looking for: {symbol} futures expiring {expiry_date}")
    print(f"{'='*80}\n")

    if not os.path.exists(security_master_path):
        print(f"❌ ERROR: File not found!")
        return

    try:
        with open(security_master_path, 'r') as f:
            reader = csv.DictReader(f)

            # Show header
            print("CSV Headers found:")
            if reader.fieldnames:
                for idx, field in enumerate(reader.fieldnames, 1):
                    print(f"  {idx}. {field}")
            print()

            # Search for SBIN
            found = False
            for row in reader:
                exchange_code = row.get('ExchangeCode', '').strip('"')
                expiry = row.get('ExpiryDate', '').strip('"')
                instrument_type = row.get('InstrumentName', '').strip('"')

                if (exchange_code == symbol and
                    expiry == expiry_date and
                    instrument_type == 'FUTSTK'):

                    found = True
                    token = row.get('Token', '').strip('"')
                    short_name = row.get('ShortName', '').strip('"')
                    company = row.get('CompanyName', '').strip('"')
                    lot_size = row.get('LotSize', '').strip('"')
                    expiry = row.get('ExpiryDate', '').strip('"')
                    inst_type = row.get('InstrumentName', '').strip('"')
                    exch_code = row.get('ExchangeCode', '').strip('"')

                    print(f"✅ FOUND SBIN FUTURES CONTRACT!")
                    print(f"{'─'*80}")
                    print(f"Token (Instrument Code): {token}")
                    print(f"Short Name (stock_code): {short_name}")
                    print(f"Company Name: {company}")
                    print(f"Lot Size: {lot_size}")
                    print(f"Expiry Date: {expiry}")
                    print(f"Instrument Type: {inst_type}")
                    print(f"Exchange Code: {exch_code}")
                    print(f"{'─'*80}\n")

                    print("✅ KEY INSIGHT:")
                    print(f"   For ICICI Breeze API, use:")
                    print(f"   - stock_code = '{short_name}' (NOT '{symbol}')")
                    print(f"   - Token/Instrument Code = {token}")
                    print(f"   - Lot Size = {lot_size}")
                    break

            if not found:
                print(f"❌ No matching contract found!")
                print(f"   Searched for: ExchangeCode='{symbol}', ExpiryDate='{expiry_date}', InstrumentName='FUTSTK'")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_security_master_parsing()
