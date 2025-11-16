# Risk & Reward Metrics - Enhanced Trade Suggestions

## Overview

Every trade suggestion now includes comprehensive risk/reward analysis, profit/loss projections, and support/resistance levels. This allows you to make quick, informed decisions about whether to approve a trade.

## What You'll See in Every Suggestion

### 1. Max Profit Potential Card
Shows the maximum profit you can make on this trade.

**For Options (Short Strangle)**
- Maximum profit = Total premium collected
- Displayed as: ₹XXX (absolute value) + XX.X% (% return on margin)
- Profitable range shows the price zone where trade stays profitable

Example:
```
Max Profit Potential
₹42,500
142.3% on margin

Profitable range: 23,500 to 24,500
```

**For Futures (Directional Trade)**
- Maximum profit = (Target price - Entry price) × Quantity
- Displayed with margin-adjusted percentage returns

Example:
```
Max Profit Potential
₹50,000
12.5% on margin (assuming ₹400K margin)
```

### 2. Risk Analysis Card
Shows maximum loss and risk/reward ratio.

**For Options**
- Max loss is typically limited to 1% move beyond breakeven
- Max loss = Margin × (1 - buffer percentage)

**For Futures**
- Max loss = (Entry price - Stop loss) × Quantity
- Risk/Reward Ratio shows how much you gain vs lose
  - 1:2 means you risk ₹1 to make ₹2
  - 1:3 means you risk ₹1 to make ₹3

Example:
```
Risk Analysis
Max Loss: ₹40,000

Risk/Reward Ratio
1 : 1.25
```

### 3. Support & Resistance Card
Shows nearest support and resistance levels and distances.

- **Resistance**: Nearest price above current where selling pressure may increase
- **Support**: Nearest price below current where buying pressure may increase
- Distance shown both in absolute (₹) and percentage (%)

Example:
```
Support & Resistance
Resistance: 24,500 (1.2% away)
Support: 23,800 (0.8% away)
```

These levels help you understand:
- At what price levels trend may reverse
- Where to watch for breakouts
- How much room trade has to move

## Profit/Loss Scenarios Table

Detailed table showing what happens at different price moves.

### For Futures Trades (LONG/SHORT)
Shows profit/loss at specific percentage moves:

| Price Move | Target Price | Profit/Loss | % Return | Status |
|-----------|--------------|------------|----------|--------|
| Neutral (0%) | 1,000 | ₹0 | 0% | Breakeven |
| +2% Move | 1,020 | +₹40,000 | +12.5% | Profit |
| -2% Move (SL) | 980 | -₹40,000 | -12.5% | Loss (SL Hit) |
| +5% Move | 1,050 | +₹100,000 | +31.3% | Profit |
| -5% Move | 950 | -₹40,000 | -12.5% | Loss (SL) |
| -10% Move | 900 | -₹40,000 | -12.5% | Loss (SL) |

**What this tells you:**
- At 2% move in your favor, you profit ₹40,000
- At 2% move against you, stop-loss triggers and you lose ₹40,000
- Even larger moves beyond SL don't increase loss (SL protects you)
- Risk/Reward ratio is 1:1 (equal risk to reward)

### For Options Trades (Short Strangle)
Shows profit/loss as price moves up or down:

At current price: Maximum profit (premium collected)
- At +1%: Still near max profit (slightly less)
- At +2%: Small loss as call loses value
- At +5%: Larger loss (call becomes ITM)
- At +10%: Large loss (deep ITM call)

Similarly for downside moves (put side).

**What this tells you:**
- Best case: Price stays within profitable range = max profit
- Worst case: Price breaks out far beyond strikes = limited loss (managed by SL)
- Most likely: Price stays in profitable range = partial to full profit

## How to Use These Metrics for Quick Decision Making

### Green Flags (Good Trades)
1. ✅ **Good Risk/Reward Ratio**
   - At least 1:1 (risk ₹1 to make ₹1)
   - Ideally 1:2 or better (risk ₹1 to make ₹2+)
   - Look at the Risk/Reward card

2. ✅ **Profit Still Possible at Small Adverse Moves**
   - Trade still profitable if market moves 1-2% against you
   - Check the scenarios table

3. ✅ **Support/Resistance Not Too Close**
   - Support and resistance > 1% away
   - Gives room for market noise/volatility
   - Price doesn't immediately hit stop-loss

4. ✅ **High Max Profit Potential**
   - High absolute profit (₹ amount)
   - High percentage return on margin
   - Look at Max Profit card

### Red Flags (Risky Trades)
1. ❌ **Poor Risk/Reward Ratio**
   - Less than 1:1 (risk more than you can make)
   - Example: 1:0.5 means ₹1 risk to make only ₹0.50
   - **REJECT** these trades

2. ❌ **Support/Resistance Too Close**
   - Less than 1% away
   - Price will immediately test levels
   - May trigger stop-loss quickly
   - **CONSIDER REJECTING**

3. ❌ **Scenarios Show Loss at Small Adverse Moves**
   - Trading against you even at small moves
   - Indicates poor entry timing
   - **PROCEED WITH CAUTION**

4. ❌ **Max Profit is Minimal**
   - Less than 1% margin return
   - Not worth the risk
   - **CONSIDER REJECTING**

## Support & Resistance Explained

### Why They Matter
- **Resistance**: Levels where selling pressure (supply) stops price from going higher
- **Support**: Levels where buying pressure (demand) stops price from going lower

### How Algorithm Calculates Them
Uses multiple timeframes and technical indicators:
- 3-month high/low (immediate levels)
- 6-month high/low (intermediate levels)
- 52-week high/low (long-term levels)
- Bollinger Bands (volatility-adjusted)
- Moving averages (trend direction)
- Pivot points (mathematical levels)

### What to Look For
1. **At least 1% distance** from current price
2. **Multiple support/resistance levels** provide zone protection
3. **Alignment with technical levels** increases reliability
4. **Price not near key resistance/support** at entry

## Risk Calculator Formula Details

### Options Risk Calculation
```
Max Profit = Total Premium Collected × Quantity
Call Breakeven = Call Strike + Total Premium
Put Breakeven = Put Strike - Total Premium
Profitable Range = Put Breakeven to Call Breakeven

At any price:
- If between breakevens: Profit = (Max Profit) × (remaining premium %)
- If beyond breakeven: Loss = (distance beyond breakeven) × Quantity
```

### Futures Risk Calculation
```
For LONG trades:
- Profit = (Current Price - Entry Price) × Quantity
- Loss = (Entry Price - Stop Loss) × Quantity
- Risk/Reward = Max Profit / Max Loss

For SHORT trades:
- Profit = (Entry Price - Current Price) × Quantity
- Loss = (Stop Loss - Entry Price) × Quantity
- Risk/Reward = Max Profit / Max Loss
```

## Scenarios Breakdown

### 2% Move Scenario
- Tests if trade still profitable with small adverse move
- Market moves this much regularly (noise)
- If you lose money at 2% move, trade has poor setup

### 5% Move Scenario
- Significant market move
- If this hits your SL, stop-loss working as intended
- Should show your max loss capped at SL level

### 10% Move Scenario
- Very large move (rare unless gap-down/gap-up)
- Shows your stop-loss is holding
- Loss should be capped at SL level

## Quick Decision Checklist

Before approving any trade, scan these metrics:

```
□ Risk/Reward Ratio >= 1:1 ?
□ Support/Resistance > 1% away?
□ Max Profit >= 1% on margin?
□ Profitable even at 2% adverse move?
□ Algorithm confidence high (LLM score or composite score)?
□ Support/Resistance aligned with technical levels?
□ Current price not at resistance level?
```

**If ALL checked**: Strong trade, safe to approve
**If 5-6 checked**: Good trade, reasonable to approve
**If < 5 checked**: Weak setup, consider rejecting

## Understanding the Risk Ratios

### 1:1 Ratio (Equal Risk/Reward)
```
Risk ₹100 to make ₹100
- Need 50% win rate to break even
- Recommend for high-confidence trades only
```

### 1:2 Ratio (Good Risk/Reward)
```
Risk ₹100 to make ₹200
- Need only 33% win rate to break even
- Sweet spot for most trades
- Recommended minimum
```

### 1:3 Ratio (Excellent Risk/Reward)
```
Risk ₹100 to make ₹300
- Need only 25% win rate to break even
- Highly profitable in long run
- Target these trades
```

### Less than 1:1 Ratio (Avoid)
```
Risk ₹100 to make only ₹50
- Need 67% win rate just to break even
- Not recommended unless very high confidence
- Avoid these trades
```

## Examples

### Example 1: Strong Futures Trade
```
Direction: LONG on NIFTY Futures
Entry: 24,100
Stop Loss: 23,950
Target: 24,350

Risk: 24,100 - 23,950 = 150 points
Reward: 24,350 - 24,100 = 250 points
Risk/Reward: 1 : 1.67 ✅ GOOD

Support at 23,900 (0.8% away) ✅ Good distance
Resistance at 24,350 (1.0% away) ✅ Good distance
Max Profit: ₹62,500 (12.5% on margin) ✅ GOOD

Decision: APPROVE ✅
```

### Example 2: Weak Options Trade
```
Strategy: Short Strangle
Call Strike: 24,500
Put Strike: 23,500
Call Premium: ₹50
Put Premium: ₹45
Total Premium: ₹95

Max Profit: ₹47,500 (47% on margin)
Profitable Range: 23,405 to 24,595

Support at 23,850 (0.2% away) ❌ TOO CLOSE
Resistance at 24,250 (0.1% away) ❌ TOO CLOSE
At 1% move: Still profitable but margin tight ⚠️

Decision: REJECT ❌
Reason: Support/resistance too close, price likely to test levels immediately
```

### Example 3: Moderate Futures Trade
```
Direction: SHORT on BANKNIFTY Futures
Entry: 45,200
Stop Loss: 45,450
Target: 44,950

Risk: 45,450 - 45,200 = 250 points
Reward: 45,200 - 44,950 = 250 points
Risk/Reward: 1 : 1.0 ⚠️ EQUAL RISK/REWARD

Support at 45,050 (0.3% away) ❌ Close
Resistance at 45,400 (0.4% away) ⚠️ Close
Max Profit: ₹15,000 (1.8% on margin) ⚠️ LOW

Decision: REJECT or WAIT ⚠️
Reason: Equal risk/reward + support/resistance too close. Wait for better setup.
```

## Integration with Decision Making

These metrics appear **before** you need to check algorithm reasoning. Use them to:

1. **First glance screening**: Do 60-second quick check
2. **Confidence building**: Understand risk before diving deeper
3. **Accountability**: Know exactly what you're risking
4. **Pattern recognition**: Over time, identify your best trade setups

## Tips for Maximum Effectiveness

1. **Always check Risk/Reward Ratio first** - This is your primary filter
2. **Never approve trades with poor ratios** - No matter how confident algorithm is
3. **Support/Resistance distance matters** - Minimum 1%, ideally 2-3%
4. **Review your rejections** - Look for patterns in trades you rejected vs accepted
5. **Track your profitability** - Did high-ratio trades do better than low-ratio?
6. **Adjust thresholds over time** - As you learn what works for you

## Common Questions

**Q: What if Risk/Reward is great but algorithm confidence is low?**
A: Use the high ratio to offset lower confidence. Can be good trade if other metrics align.

**Q: What if risk/reward is mediocre but support/resistance are far?**
A: Prefer trades with better risk/reward. S/R far is bonus, not substitute.

**Q: How do I know if ₹40,000 profit is "good"?**
A: Compare to your margin. If margin is ₹320K, that's 12.5% return = good.
If margin is ₹2M, that's only 2% = not great.

**Q: What if support/resistance are too close?**
A: Consider rejecting. Close levels mean trade will be tested immediately.
Your SL might get hit before profit target.

**Q: Can I approve a trade if only 4 of 6 checklist items are met?**
A: Yes, if the 4 are the most important: Risk/Reward, Distance, Confidence, Max Profit.
Trade carefully with lower conviction.

## Next Steps

1. **First trade**: Check all metrics carefully, note which ones were correct
2. **Track results**: Keep log of approved trades and which metrics predicted success
3. **Refine criteria**: Adjust thresholds based on your results
4. **Build confidence**: As you see metrics correlate with profits, make faster decisions

Remember: **These metrics are your trading checklist. Use them consistently for the best results.**
