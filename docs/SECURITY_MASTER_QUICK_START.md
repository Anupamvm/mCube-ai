# SecurityMaster Integration - Quick Start Guide

## 🚀 Quick Setup (5 Minutes)

### Step 1: Download SecurityMaster
```bash
cd ~/Downloads
mkdir -p SecurityMaster
curl -O https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip
unzip -o SecurityMaster.zip -d SecurityMaster/
```

### Step 2: Verify Installation
```bash
cd /Users/anupammangudkar/PyProjects/mCube-ai
python test_security_master.py
```

Expected output:
```
✅ FOUND SBIN FUTURES CONTRACT!
Token (Instrument Code): 50066
Short Name (stock_code): STABAN
Lot Size: 750
```

### Step 3: Test Order Placement (Optional)
```bash
# Only during market hours (9:15 AM - 3:30 PM IST, Mon-Fri)
python place_sbin_orders.py
```

## 📋 Key Concepts

### What is SecurityMaster?
- CSV files with **all tradable instruments** on NSE/BSE
- Updated **daily at 8:00 AM IST** by ICICI Direct
- Contains **correct instrument codes, lot sizes, and metadata**

### Why Do We Need It?

**The Problem:**
```python
# This FAILS - 'SBIN' is the ExchangeCode, not the stock_code
order_params = {'stock_code': 'SBIN'}  # ❌ WRONG
```

**The Solution:**
```python
# SecurityMaster tells us: SBIN → STABAN (stock_code)
instrument = get_futures_instrument('SBIN', '30-Dec-2025')
order_params = {'stock_code': instrument['short_name']}  # ✅ CORRECT
```

## 🎯 Usage Examples

### Example 1: Place SBIN Futures Order
```python
from apps.brokers.integrations.breeze import place_futures_order_with_security_master

response = place_futures_order_with_security_master(
    symbol='SBIN',
    expiry_date='30-Dec-2025',
    action='buy',
    lots=10
)

if response['Status'] == 200:
    print(f"✅ Order ID: {response['Success']['order_id']}")
    print(f"Stock Code Used: {response['security_master']['stock_code']}")
else:
    print(f"❌ Error: {response['Error']}")
```

### Example 2: Get Instrument Details Only
```python
from apps.brokers.utils.security_master import get_futures_instrument

instrument = get_futures_instrument('NIFTY', '27-Nov-2025')

if instrument:
    print(f"Token: {instrument['token']}")
    print(f"Stock Code: {instrument['short_name']}")
    print(f"Lot Size: {instrument['lot_size']}")
```

### Example 3: Place NIFTY Option Order
```python
from apps.brokers.integrations.breeze import place_option_order_with_security_master

response = place_option_order_with_security_master(
    symbol='NIFTY',
    expiry_date='27-Nov-2025',
    strike_price=24500,
    option_type='CE',
    action='sell',
    lots=2
)
```

## 🎨 UI Updates

### Order Success Response
The UI now shows:

```
✅ Order Placed Successfully!
Order ID: 202511201234567
Status: PENDING

Order Details:
Symbol: SBIN
Stock Code: STABAN
Direction: LONG
Quantity: 7500 (10 lots × 750)
Entry Price: ₹900.00
Expiry: 30-DEC-2025

📋 SecurityMaster Info:
┌─────────────────────────────────────┐
│ Token: 50066                        │
│ Stock Code: STABAN                  │
│ Lot Size: 750                       │
│ Company: STATE BANK OF INDIA        │
└─────────────────────────────────────┘

📡 Breeze API Response (click to expand)
```

## 🔧 Configuration

### Default Path
```
/Users/anupammangudkar/Downloads/SecurityMaster/FONSEScripMaster.txt
```

### Custom Path (Optional)

**Option 1: Django Settings**
```python
# mcube_ai/settings.py
SECURITY_MASTER_PATH = '/custom/path/FONSEScripMaster.txt'
```

**Option 2: Environment Variable**
```bash
export SECURITY_MASTER_PATH='/custom/path/FONSEScripMaster.txt'
```

## 📅 Daily Updates

### Manual Update
```bash
cd ~/Downloads
curl -O https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip
unzip -o SecurityMaster.zip -d SecurityMaster/
```

### Automated Update (Recommended)
```bash
# Add to crontab (runs daily at 8:15 AM)
crontab -e

# Add this line:
15 8 * * * cd ~/Downloads && curl -O https://directlink.icicidirect.com/NewSecurityMaster/SecurityMaster.zip && unzip -o SecurityMaster.zip -d SecurityMaster/
```

## ⚠️ Common Issues

### 1. "File not found"
```
❌ ERROR: SecurityMaster file not found
```
**Fix:** Download SecurityMaster (see Step 1)

### 2. "Instrument not found"
```
❌ ERROR: No matching instrument found
```
**Fix:**
- Check expiry date format: `DD-MMM-YYYY` (e.g., `30-Dec-2025`)
- Verify contract exists on NSE
- Ensure SecurityMaster is recent

### 3. "Invalid stock code" from Breeze
```
❌ Breeze API Error: Invalid stock code
```
**Fix:** SecurityMaster lookup may have failed. Check logs.

## 📊 SBIN December 2025 Example

### SecurityMaster Entry
```
Token: 50066
InstrumentName: FUTSTK
ShortName: STABAN         ← This is the stock_code!
ExchangeCode: SBIN        ← This is NOT the stock_code!
ExpiryDate: 30-Dec-2025
LotSize: 750
CompanyName: STATE BANK OF INDIA
```

### Order Parameters
```python
{
    'stock_code': 'STABAN',     # ✅ From ShortName
    'exchange_code': 'NFO',
    'product': 'futures',
    'action': 'buy',
    'quantity': '7500',         # 10 lots × 750
    'expiry_date': '30-DEC-2025',
    'right': 'others',
    'strike_price': '0'
}
```

## 🧪 Testing Checklist

- [ ] SecurityMaster file downloaded
- [ ] `test_security_master.py` runs successfully
- [ ] Can fetch SBIN instrument details
- [ ] Order placement UI shows SecurityMaster info
- [ ] Breeze API response visible in UI
- [ ] Error messages include SecurityMaster details

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [SECURITY_MASTER_USAGE.md](../SECURITY_MASTER_USAGE.md) | Comprehensive usage guide |
| [SECURITY_MASTER_INTEGRATION.md](features/SECURITY_MASTER_INTEGRATION.md) | Technical integration details |
| This file | Quick start guide |

## 🆘 Need Help?

1. **Check logs:** `tail -f logs/django.log`
2. **Test parsing:** `python test_security_master.py`
3. **Verify file:** `ls -lh ~/Downloads/SecurityMaster/`
4. **Check UI:** Place test order and review full response

## 🎓 Key Takeaways

1. ✅ **Always use SecurityMaster** for instrument codes
2. ✅ **stock_code = ShortName**, NOT ExchangeCode
3. ✅ **Update SecurityMaster daily** (8 AM IST)
4. ✅ **UI shows full transparency** - order details, SecurityMaster, Breeze response
5. ✅ **Fallback mechanism** - uses ContractData if SecurityMaster fails

---

**Ready to place orders?** Start with `test_security_master.py` to verify everything works!
