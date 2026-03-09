# Kotak Neo Python SDK (v2 API)

- Package version: 2.0.0

## Authentication Flow

The v2 API uses a 2-step TOTP + MPIN login. No `consumer_secret`, OTP, or `session_init()` required.

### Step 1: TOTP Login (view token)

```
POST https://mis.kotaksecurities.com/login/1.0/tradeApiLogin
```

Headers: `Authorization: <access_token>`, `neo-fin-key: neotradeapi`

```python
from neo_api_client import NeoAPI

client = NeoAPI(consumer_key="<access_token>", environment='prod')

response = client.totp_login(
    mobile_number="+91XXXXXXXXXX",
    ucc="<client_code>",
    totp="<6_digit_totp>"
)
```

### Step 2: MPIN Validate (trade token + baseUrl)

```
POST https://mis.kotaksecurities.com/login/1.0/tradeApiValidate
```

```python
session = client.totp_validate(mpin="<6_digit_mpin>")
# session['data'] contains: token, sid, baseUrl, dataCenter, hsServerId
```

After this, all post-login APIs use the dynamic `baseUrl` returned in the response.

## Post-Login APIs

All post-login APIs use headers: `Auth: <session_token>`, `Sid: <session_sid>`, `neo-fin-key: neotradeapi`

### Orders

```python
# Place order
client.place_order(
    exchange_segment='nse_fo', product='NRML', price='0',
    order_type='MKT', quantity='50', validity='DAY',
    trading_symbol='NIFTY25MAR20000CE', transaction_type='B'
)

# Modify order
client.modify_order(order_id="<order_no>", price="100", quantity="50",
                    validity="DAY", order_type="L")

# Cancel order
client.cancel_order(order_id="<order_no>")
```

### Reports

```python
client.order_report()                    # Order book
client.order_history(order_id="<id>")    # Order history
client.trade_report()                    # Trade book
```

### Portfolio

```python
client.positions()   # Open positions
client.holdings()    # Portfolio holdings
client.limits(segment="ALL", exchange="ALL", product="ALL")  # Funds/limits
client.margin_required(...)  # Margin check for an order
```

### Market Data

Quotes and Scrip Master use `Authorization: <access_token>` only (no `Auth`/`Sid`/`neo-fin-key`).

```python
# Quotes
client.quotes(
    instrument_tokens=[{"exchange_segment": "nse_cm", "instrument_token": "11536"}],
    quote_type="ltp"
)

# Scrip master CSV files
client.scrip_master()
client.scrip_master(exchange_segment="nse_fo")

# Search scrip (local, from downloaded master)
client.search_scrip(exchange_segment="nse_fo", symbol="NIFTY")
```

### WebSocket

```python
client.on_message = lambda msg: print(msg)
client.on_error = lambda err: print(err)

# Market feed
client.subscribe(instrument_tokens=[...])
client.un_subscribe(instrument_tokens=[...])

# Order feed
client.subscribe_to_orderfeed()
```

## API Endpoints Reference

| Method | Endpoint | Auth |
|--------|----------|------|
| `totp_login` | `login/1.0/tradeApiLogin` | access_token |
| `totp_validate` | `login/1.0/tradeApiValidate` | access_token + view token |
| `place_order` | `quick/order/rule/ms/place` | session token |
| `modify_order` | `quick/order/vr/modify` | session token |
| `cancel_order` | `quick/order/cancel` | session token |
| `order_report` | `quick/user/orders` | session token |
| `order_history` | `quick/order/history` | session token |
| `trade_report` | `quick/user/trades` | session token |
| `positions` | `quick/user/positions` | session token |
| `holdings` | `portfolio/v1/holdings` | session token |
| `limits` | `quick/user/limits` | session token |
| `margin_required` | `quick/user/check-margin` | session token |
| `scrip_master` | `script-details/1.0/masterscrip/file-paths` | access_token |
| `quotes` | `script-details/1.0/quotes/neosymbol/...` | access_token |
