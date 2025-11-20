# ICICI Direct SecurityMaster Usage Guide

## Overview

ICICI Direct provides SecurityMaster files that contain complete instrument details for all tradable securities. These files are **updated daily at 8:00 AM IST** and are essential for placing orders with the correct instrument codes.

## Download Location

SecurityMaster files are available at:
```
https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip
```

The ZIP file contains the following master files:
- `FONSEScripMaster.txt` - Futures & Options on NSE
- `NSEScripMaster.txt` - Cash market NSE
- `BSEScripMaster.txt` - Cash market BSE
- `FOBSEScripMaster.txt` - Futures & Options on BSE
- `CDNSEScripMaster.txt` - Currency derivatives NSE

## File Format

All SecurityMaster files are CSV files with the following key fields:

| Field | Description | Example |
|-------|-------------|---------|
| `Token` | Instrument code/token used by ICICI APIs | 50066 |
| `InstrumentName` | Type of instrument | FUTSTK |
| `ShortName` | Short name for stock code | STABAN |
| `ExchangeCode` | Stock symbol | SBIN |
| `ExpiryDate` | Expiry date in DD-MMM-YYYY format | 30-Dec-2025 |
| `LotSize` | Lot size for the contract | 750 |
| `CompanyName` | Full company name | STATE BANK OF INDIA |

## Key Insight: Stock Code vs Symbol

**IMPORTANT:** For futures/options, ICICI Breeze API requires the `ShortName` field (NOT the `ExchangeCode`).

Example for SBIN December 2025 Futures:
- ❌ **WRONG:** `stock_code = 'SBIN'` (This is the ExchangeCode)
- ✅ **CORRECT:** `stock_code = 'STABAN'` (This is the ShortName)

## SBIN December 2025 Futures Details

From SecurityMaster file `FONSEScripMaster.txt`:

```
Token: 50066
InstrumentName: FUTSTK
ShortName: STABAN
ExchangeCode: SBIN
ExpiryDate: 30-Dec-2025
LotSize: 750
CompanyName: STATE BANK OF INDIA
```

## Usage in place_sbin_orders.py

The script now includes a `get_instrument_from_security_master()` function that:

1. Reads the SecurityMaster file
2. Searches for the instrument by symbol and expiry
3. Extracts the correct `stock_code` (ShortName) and other details
4. Uses these details for order placement

### Example:

```python
# Get instrument details from SecurityMaster
instrument = get_instrument_from_security_master('SBIN', '30-Dec-2025')

if instrument:
    stock_code = instrument['short_name']  # 'STABAN'
    instrument_token = instrument['token']  # '50066'
    lot_size = instrument['lot_size']      # 750

    # Use in Breeze API order
    order_params = {
        'stock_code': stock_code,  # Use 'STABAN', not 'SBIN'
        'exchange_code': 'NFO',
        'product': 'futures',
        'action': 'buy',
        'quantity': str(lot_size * 10),  # 7500
        'expiry_date': '30-Dec-2025',
        # ... other params
    }
```

## Testing

Use `test_security_master.py` to verify SecurityMaster parsing:

```bash
python test_security_master.py
```

Expected output:
```
✅ FOUND SBIN FUTURES CONTRACT!
Token (Instrument Code): 50066
Short Name (stock_code): STABAN
Company Name: STATE BANK OF INDIA
Lot Size: 750
Expiry Date: 30-Dec-2025
```

## Daily Update Routine

1. **Download SecurityMaster daily at 8:00 AM IST**
   ```bash
   cd ~/Downloads
   curl -O https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip
   unzip -o SecurityMaster.zip -d SecurityMaster/
   ```

2. **Verify the update**
   ```bash
   ls -lh ~/Downloads/SecurityMaster/
   ```

3. **Check file timestamp**
   The files should be dated with today's date if downloaded after 8 AM IST.

## Automation Script

You can create a cron job or systemd timer to download SecurityMaster daily:

```bash
# Add to crontab (runs at 8:15 AM IST daily)
15 8 * * * cd ~/Downloads && curl -O https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip && unzip -o SecurityMaster.zip -d SecurityMaster/
```

## Common Issues

### Issue 1: File Not Found
**Error:** `SecurityMaster file not found`

**Solution:** Download the latest SecurityMaster file:
```bash
cd ~/Downloads
mkdir -p SecurityMaster
cd SecurityMaster
curl -O https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip
unzip -o SecurityMaster.zip
```

### Issue 2: Instrument Not Found
**Error:** `No matching instrument found in SecurityMaster`

**Possible reasons:**
- Contract may have expired
- Expiry date format is incorrect (should be DD-MMM-YYYY)
- Symbol name is incorrect
- SecurityMaster file is outdated

**Solution:**
- Verify the expiry date format
- Check if the contract exists on NSE
- Download the latest SecurityMaster file

### Issue 3: Order Rejection with "Invalid Stock Code"
**Error from Breeze API:** `Invalid stock code`

**Reason:** Using `ExchangeCode` instead of `ShortName`

**Solution:** Always use `ShortName` from SecurityMaster as the `stock_code` parameter.

## Reference Links

- ICICI Direct SecurityMaster: https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip
- NSE Derivatives: https://www.nseindia.com/market-data/live-equity-market
- ICICI Breeze API Docs: https://api.icicidirect.com/apiuser/home

## Notes

1. SecurityMaster files are **very large** (FONSE is ~24MB). Parsing may take a few seconds.
2. Always use the latest SecurityMaster file (downloaded after 8 AM IST on trading days).
3. For options, the `StrikePrice` and `OptionType` fields are also important.
4. The `Token` field is unique for each instrument and expiry combination.
5. Lot sizes can change - always use SecurityMaster data rather than hardcoded values.
