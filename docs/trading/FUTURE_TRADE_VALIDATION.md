# Future Trade Validation Feature

## Overview

The **Future Trade Validation** feature allows you to test the ICICI Futures trading strategy with live market data **without placing actual orders**. This provides complete transparency into the algorithm's decision-making process with step-by-step explanations.

## Access

Navigate to: **Broker Dashboard → Strategy Testing → 🎯 Validate Future Trade**

URL: `/brokers/validate-future-trade/`

## What It Does

The validation feature executes a complete dry-run of the ICICI Futures Strategy workflow:

### Step 1: Refresh Trendlyne Data
- Checks Trendlyne database for latest stock data
- Verifies data freshness and record count
- Shows when data was last updated

### Step 2: Connect to ICICI Breeze
- Authenticates with ICICI Breeze broker
- Fetches live account data (margin available, positions)
- Verifies account is active and ready for trading

### Step 3: Screen Futures Opportunities (Multi-Factor Analysis)
The algorithm runs comprehensive screening using three key factors:

#### A. Open Interest (OI) Analysis (40 points)
- **OI Buildup Type**: Identifies long buildup, short buildup, or covering patterns
- **PCR Ratio**: Put-Call Ratio for market sentiment
- **OI Changes**: Tracks significant changes in open interest

#### B. Sector Analysis (25 points)
- **3-Day Performance**: Recent sector momentum
- **7-Day Performance**: Short-term sector trend
- **21-Day Performance**: Medium-term sector trend
- **Alignment**: Checks if all timeframes show consistent direction

#### C. Technical Analysis (35 points)
- **RSI (Relative Strength Index)**: Momentum indicator (30-70 range ideal)
- **LTP vs 200 DMA**: Price position relative to long-term moving average
- **Volume Score**: Recent volume compared to average

**Total Score**: Sum of all three factors (max 100 points)

### Step 4: Top Candidate Analysis
Shows detailed breakdown of the highest-scoring opportunity:
- Symbol and direction (LONG/SHORT)
- Composite score breakdown by factor
- OI buildup pattern
- Sector performance across timeframes
- Technical indicator values

### Step 5: Trade Recommendation Summary
Explains the 7-step entry workflow that would be executed:

1. **Morning Position Check**: Verifies ONE POSITION RULE (account-level limit)
2. **Entry Timing**: Validates 09:15 AM - 3:00 PM trading window
3. **Expiry Selection**: Selects futures contract with 15+ days to expiry
4. **LLM Validation**: AI model validates trade with 70% confidence minimum
5. **Position Sizing**: Calculates quantity based on 50% margin usage
6. **Risk Checks**: Verifies daily/weekly loss limits
7. **Order Placement**: Creates order (SKIPPED in validation mode)

### Step 6: Sample Telegram Notification
Generates the exact Telegram message that would be sent in live trading, including:
- Trade details (symbol, direction, composite score)
- Multi-factor analysis breakdown
- Entry workflow steps
- Expected trade parameters
- Risk management details

## Key Features

### 🔍 Complete Transparency
Every decision point is explained with reasoning and data

### 🎯 Live Data Testing
Uses actual market data from ICICI Breeze and Trendlyne

### ⚠️ Safe Testing
**No actual orders are placed** - this is a validation-only mode

### 📊 Multi-Factor Scoring
See exactly how OI, Sector, and Technical factors contribute to the score

### 📱 Telegram Preview
View the exact notification message that would be sent

## Understanding the Output

### Status Indicators
- ✅ **Success (Green)**: Step completed successfully
- ⚠️ **Warning (Orange)**: Step completed with warnings or was skipped
- ❌ **Error (Red)**: Step failed
- 🔵 **In Progress (Blue)**: Step is currently running

### Composite Score Interpretation
- **80-100**: Excellent opportunity (all factors aligned)
- **60-79**: Good opportunity (most factors favorable)
- **40-59**: Moderate opportunity (mixed signals)
- **0-39**: Weak opportunity (unfavorable conditions)

### OI Buildup Types
- **Long Buildup**: Increasing OI + Rising Price → Bullish
- **Short Buildup**: Increasing OI + Falling Price → Bearish
- **Long Unwinding**: Decreasing OI + Falling Price → Bearish
- **Short Covering**: Decreasing OI + Rising Price → Bullish

### Sector Alignment
- **BULLISH**: All timeframes (3D, 7D, 21D) showing positive performance
- **BEARISH**: All timeframes showing negative performance
- **MIXED**: Inconsistent performance across timeframes
- **NEUTRAL**: No clear directional bias

## Sample Workflow

1. Click "🎯 Validate Future Trade" on Broker Dashboard
2. System automatically:
   - Checks Trendlyne data freshness
   - Connects to ICICI Breeze
   - Fetches live market data
   - Runs multi-factor screening
   - Analyzes top opportunities
3. View detailed results with step-by-step explanations
4. Review sample Telegram notification
5. Click "Run Validation Again" to test with updated data

## Use Cases

### 🧪 Strategy Testing
Test how the algorithm performs with current market conditions

### 📚 Learning
Understand how the multi-factor screening works

### 🔧 Debugging
Verify that all components (Trendlyne, ICICI, screening logic) are working correctly

### 📊 Performance Preview
See what trades would be suggested before enabling live trading

## Important Notes

### ⚠️ No Orders Placed
This feature **never places actual orders**. It only simulates the screening and validation process.

### 🕐 Market Hours
Works best during market hours (9:15 AM - 3:30 PM IST) when live data is available.

### 📊 Data Freshness
Results depend on Trendlyne data being up-to-date. Run `python manage.py populate_trendlyne` to refresh.

### 💰 Account Requirements
Requires active ICICI Breeze account configured in Django admin.

## Technical Details

### View Function
Location: `apps/brokers/views.py:validate_future_trade()`

### Template
Location: `apps/brokers/templates/brokers/validate_future_trade.html`

### URL Route
Path: `/brokers/validate-future-trade/`
Name: `brokers:validate_future_trade`

### Dependencies
- `apps.strategies.strategies.icici_futures.screen_futures_opportunities()`
- `apps.brokers.integrations.breeze.fetch_and_save_breeze_data()`
- `apps.data.models.TrendlyneData`
- `apps.core.models.BrokerAccount`

## Related Documentation
- [ICICI Futures Strategy](./ICICI_FUTURES_STRATEGY.md) - Complete strategy documentation
- [Broker Integration](../brokers/BROKER_INTEGRATION.md) - ICICI Breeze setup
- [Trendlyne Data](../trendlyne/TRENDLYNE_INTEGRATION.md) - Data source configuration

## Future Enhancements

Potential improvements to the validation feature:

1. **Historical Backtesting**: Run validation against historical data
2. **Custom Filters**: Allow adjusting scoring weights for testing
3. **Multiple Opportunities**: Show top 5-10 opportunities instead of just #1
4. **Performance Tracking**: Track validation results over time
5. **Paper Trading Integration**: Optionally place paper trades for validation
6. **Comparison Mode**: Compare results with different parameter sets

## Troubleshooting

### "No Trendlyne data found"
**Solution**: Run `python manage.py populate_trendlyne` to refresh data

### "No active ICICI account found"
**Solution**: Configure ICICI account in Django admin at `/admin/core/brokeraccount/`

### "Failed to connect to ICICI"
**Solution**: Check Breeze session token is valid. Login at `/brokers/breeze/login/`

### "No opportunities found"
**Possible reasons**:
- Market conditions don't meet screening criteria
- All stocks filtered out by minimum score threshold
- Trendlyne data is outdated
- No stocks showing favorable OI patterns

## Feedback

If you encounter issues or have suggestions for improvement, please document them or reach out to the development team.
