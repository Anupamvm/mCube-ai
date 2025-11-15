## Trendlyne Trading Integration Guide

This guide shows how to integrate Trendlyne data into your core trading logic for both Futures and Options trades.

## 🎯 Overview

Your trading system now uses:
- **Open Interest (OI)** analysis for buildup patterns
- **Volume** surge detection
- **DMA** (Daily Moving Averages) trends
- **Trendlyne Scores** (Durability, Valuation, Momentum)
- **Technical Indicators** (RSI, MACD, Support/Resistance)
- **Institutional Holdings** patterns

## 📁 What Was Built

### 1. Data Importers (`apps/data/importers.py`)
- `TrendlyneDataImporter` - Imports CSV files into Django models
- `ContractStockDataImporter` - Calculates stock-level F&O metrics

### 2. Analyzers (`apps/data/analyzers.py`)
- `TrendlyneScoreAnalyzer` - Analyzes Trendlyne proprietary scores
- `OpenInterestAnalyzer` - PCR ratio, OI buildup, max pain
- `VolumeAnalyzer` - Volume surges, delivery percentage
- `DMAAnalyzer` - DMA crossovers, trend detection
- `TechnicalIndicatorAnalyzer` - RSI, MACD, support/resistance
- `HoldingPatternAnalyzer` - Institutional holdings

### 3. Signal Generators (`apps/data/signals.py`)
- `SignalGenerator` - Combines all indicators for trading signals
- `OptionsStrategyRecommender` - Recommends best options strategy

### 4. Validators (`apps/data/validators.py`)
- `TradeValidator` - Validates trades before execution
- `RiskValidator` - Position sizing and sector concentration

### 5. Management Commands
- `import_trendlyne_data` - Import CSV data
- `generate_signals` - Generate trading signals
- `validate_trade` - Validate a specific trade

## 🚀 Quick Start

### Step 1: Fetch Trendlyne Data

```bash
# Fetch all data from Trendlyne
curl -X POST http://localhost:8000/api/data/trendlyne/fetch/
```

This will download:
- F&O data (all contracts)
- Market snapshot
- 21 analyst consensus CSV files

### Step 2: Import Data into Database

```bash
# Import all data
python manage.py import_trendlyne_data --type all

# Or import specific types
python manage.py import_trendlyne_data --type market_snapshot
python manage.py import_trendlyne_data --type fno
python manage.py import_trendlyne_data --type forecaster
```

### Step 3: Generate Trading Signals

```bash
# Scan all stocks for opportunities
python manage.py generate_signals --min-confidence 60

# Generate signal for specific stock
python manage.py generate_signals --symbol RELIANCE --expiry 28-NOV-2024

# Generate only futures signals
python manage.py generate_signals --symbol TATASTEEL --trade-type futures

# Generate only options signals
python manage.py generate_signals --symbol HDFCBANK --trade-type options
```

### Step 4: Validate a Trade

```bash
# Validate futures long
python manage.py validate_trade INFY FUTURES_LONG --expiry 28-NOV-2024

# Validate futures short
python manage.py validate_trade ICICIBANK FUTURES_SHORT

# Validate call option purchase
python manage.py validate_trade RELIANCE CALL_BUY --strike 2800 --expiry 28-NOV-2024

# Validate put option purchase
python manage.py validate_trade TCS PUT_BUY --strike 3500 --expiry 28-NOV-2024
```

## 💻 Programmatic Usage

### Example 1: Generate Futures Signal

```python
from apps.data.signals import SignalGenerator

generator = SignalGenerator()

# Generate futures signal
signal = generator.generate_futures_signal('RELIANCE', '28-NOV-2024')

print(f"Signal: {signal.signal.name}")
print(f"Confidence: {signal.confidence}%")
print(f"Action: {signal.recommended_action}")

print("\nReasons:")
for reason in signal.reasons:
    print(f"  - {reason}")

print("\nMetrics:")
if 'trendlyne_scores' in signal.metrics:
    scores = signal.metrics['trendlyne_scores']
    print(f"  Durability: {scores['durability']}")
    print(f"  Valuation: {scores['valuation']}")
    print(f"  Momentum: {scores['momentum']}")

if 'oi_buildup' in signal.metrics:
    oi = signal.metrics['oi_buildup']
    print(f"  OI Buildup: {oi['buildup_type']}")
    print(f"  Sentiment: {oi['sentiment']}")
```

### Example 2: Validate Trade Before Execution

```python
from apps.data.validators import TradeValidator

validator = TradeValidator()

# Validate futures long
result = validator.validate_futures_long('INFY', '28-NOV-2024')

if result.approved:
    print(f"✅ TRADE APPROVED (Confidence: {result.confidence}%)")
    print("\nReasons:")
    for reason in result.reasons:
        print(f"  {reason}")
else:
    print(f"❌ TRADE REJECTED (Confidence: {result.confidence}%)")
    print("\nWarnings:")
    for warning in result.warnings:
        print(f"  {warning}")
```

### Example 3: Scan for Opportunities

```python
from apps.data.signals import SignalGenerator

generator = SignalGenerator()

# Find all high-confidence opportunities
opportunities = generator.scan_for_opportunities(min_confidence=70)

print(f"Found {len(opportunities)} opportunities:\n")

for signal in opportunities:
    print(f"{signal.symbol} - {signal.signal.name} ({signal.confidence}%)")
    print(f"  {signal.recommended_action}")
    print()
```

### Example 4: Analyze Open Interest

```python
from apps.data.analyzers import OpenInterestAnalyzer

oi_analyzer = OpenInterestAnalyzer()

# Get PCR ratio
pcr_data = oi_analyzer.get_pcr_ratio('NIFTY')
print(f"PCR (OI): {pcr_data['pcr_oi']:.2f}")
print(f"Interpretation: {pcr_data['interpretation']}")

# Analyze OI buildup
buildup = oi_analyzer.analyze_oi_buildup('RELIANCE', '28-NOV-2024')
print(f"Buildup Type: {buildup['buildup_type']}")
print(f"Sentiment: {buildup['sentiment']}")

# Get strike distribution
strikes = oi_analyzer.get_strike_distribution('BANKNIFTY', '20-NOV-2024')
print(f"Max Call OI Strike: {strikes['max_call_oi_strike']}")
print(f"Max Put OI Strike: {strikes['max_put_oi_strike']}")
print(f"Resistance: {strikes['resistance_level']}")
print(f"Support: {strikes['support_level']}")

# Find max pain
max_pain = oi_analyzer.find_max_pain('NIFTY', '28-NOV-2024')
print(f"Max Pain: {max_pain}")
```

### Example 5: Volume Analysis

```python
from apps.data.analyzers import VolumeAnalyzer

volume_analyzer = VolumeAnalyzer()

# Check for volume surge
surge = volume_analyzer.analyze_volume_surge('TATASTEEL')
print(f"Volume Surge Level: {surge['surge_level']}")
print(f"Volume Ratio (Week): {surge['volume_ratio_week']:.2f}x")
print(f"Is Surge: {surge['is_surge']}")

# Analyze delivery percentage
delivery = volume_analyzer.analyze_delivery_percentage('RELIANCE')
print(f"Delivery %: {delivery['delivery_pct']:.1f}%")
print(f"Strength: {delivery['strength']}")
print(f"Is Strong Hands: {delivery['is_strong_hands']}")
```

### Example 6: DMA Trend Analysis

```python
from apps.data.analyzers import DMAAnalyzer

dma_analyzer = DMAAnalyzer()

# Get DMA position
dma_position = dma_analyzer.get_dma_position('INFY')
print(f"Trend: {dma_position['trend']}")
print(f"Above DMAs: {dma_position['above_dma_count']}/{dma_position['total_dmas']}")
print(f"Golden Cross: {dma_position['golden_cross']}")
print(f"Death Cross: {dma_position['death_cross']}")

# Detect DMA crossovers
crossovers = dma_analyzer.detect_dma_crossover('TCS')
for signal in crossovers['signals']:
    print(f"{signal['type']}: {signal['dmas']} - {signal['signal']}")
```

## 🔄 Integration with Your Strategy

### Modify Your Strategy to Use Trendlyne Data

```python
# In apps/strategies/your_strategy.py

from apps.data.signals import SignalGenerator
from apps.data.validators import TradeValidator
from apps.data.analyzers import OpenInterestAnalyzer, VolumeAnalyzer

class TrendlyneEnhancedStrategy:
    def __init__(self):
        self.signal_generator = SignalGenerator()
        self.validator = TradeValidator()
        self.oi_analyzer = OpenInterestAnalyzer()
        self.volume_analyzer = VolumeAnalyzer()

    def should_enter_futures_long(self, symbol, expiry):
        """
        Decision logic for futures long entry

        Uses:
        - Trendlyne scores
        - OI buildup
        - Volume surge
        - DMA trend
        """
        # Generate signal
        signal = self.signal_generator.generate_futures_signal(symbol, expiry)

        if signal.confidence < 60:
            return False, "Low confidence signal"

        if signal.signal.value < 4:  # Less than BUY
            return False, f"Signal not strong enough: {signal.signal.name}"

        # Validate trade
        validation = self.validator.validate_futures_long(symbol, expiry)

        if not validation.approved:
            return False, "Validation failed"

        return True, f"APPROVED: {signal.recommended_action}"

    def get_futures_position_size(self, symbol, account_size):
        """
        Calculate position size based on Trendlyne confidence

        Higher confidence = Larger position
        """
        signal = self.signal_generator.generate_futures_signal(symbol, 'CURRENT_MONTH')

        # Base position: 5% of account
        base_position_pct = 0.05

        # Adjust based on confidence
        if signal.confidence >= 80:
            multiplier = 1.5
        elif signal.confidence >= 70:
            multiplier = 1.2
        elif signal.confidence >= 60:
            multiplier = 1.0
        else:
            multiplier = 0.5

        position_size = account_size * base_position_pct * multiplier

        return position_size

    def should_exit_position(self, symbol, position_type):
        """
        Exit logic using Trendlyne data

        Exit if:
        - Momentum score drops
        - OI unwinding
        - RSI overbought/oversold reversal
        """
        from apps.data.analyzers import TrendlyneScoreAnalyzer, TechnicalIndicatorAnalyzer

        score_analyzer = TrendlyneScoreAnalyzer()
        technical_analyzer = TechnicalIndicatorAnalyzer()

        # Check momentum
        scores = score_analyzer.get_stock_scores(symbol)
        if scores and scores['momentum'] < 40:
            return True, "Momentum weakening"

        # Check RSI
        rsi_signal = technical_analyzer.get_rsi_signal(symbol)
        if position_type == 'LONG':
            if rsi_signal.get('is_overbought'):
                return True, "RSI overbought - Take profits"
        elif position_type == 'SHORT':
            if rsi_signal.get('is_oversold'):
                return True, "RSI oversold - Cover short"

        # Check OI buildup
        oi_buildup = self.oi_analyzer.analyze_oi_buildup(symbol, 'CURRENT_MONTH')
        if position_type == 'LONG' and oi_buildup.get('buildup_type') == 'LONG_UNWINDING':
            return True, "Long unwinding detected"

        return False, "Hold position"

    def get_options_strategy_recommendation(self, symbol):
        """
        Get best options strategy for current market conditions
        """
        from apps.data.signals import OptionsStrategyRecommender

        recommender = OptionsStrategyRecommender()
        recommendation = recommender.recommend_strategy(symbol, 'CURRENT_MONTH')

        return recommendation['recommended_strategy']
```

## 📊 Real Trading Workflow

### Complete Futures Trading Flow

```python
from apps.data.signals import SignalGenerator
from apps.data.validators import TradeValidator, RiskValidator

# 1. Scan for opportunities
generator = SignalGenerator()
opportunities = generator.scan_for_opportunities(min_confidence=70)

for signal in opportunities:
    symbol = signal.symbol

    # 2. Validate the trade
    validator = TradeValidator()
    validation = validator.validate_futures_long(symbol, '28-NOV-2024')

    if not validation.approved:
        print(f"❌ {symbol} rejected: {validation.warnings}")
        continue

    # 3. Check risk management
    account_size = 1000000  # 10 lakh
    position_value = 200000  # 2 lakh position

    size_ok, msg = RiskValidator.validate_position_sizing(
        account_size, position_value, max_position_pct=20
    )

    if not size_ok:
        print(f"❌ {symbol} position size rejected: {msg}")
        continue

    # 4. Execute trade
    print(f"✅ EXECUTE: {signal.recommended_action}")
    print(f"   Confidence: {signal.confidence}%")
    print(f"   Position Size: ₹{position_value:,.0f}")

    # Your broker API execution code here
    # execute_futures_trade(symbol, 'BUY', quantity, expiry)
```

### Complete Options Trading Flow

```python
from apps.data.signals import OptionsStrategyRecommender
from apps.data.analyzers import OpenInterestAnalyzer

# 1. Get strategy recommendation
recommender = OptionsStrategyRecommender()
strategy = recommender.recommend_strategy('RELIANCE', '28-NOV-2024')

print(f"Recommended Strategy: {strategy['recommended_strategy']['strategy']}")
print(f"Confidence: {strategy['recommended_strategy']['confidence']}%")
print(f"Reason: {strategy['recommended_strategy']['reason']}")

# 2. If directional strategy, find best strike
if strategy['recommended_strategy']['strategy'] in ['LONG_CALL', 'LONG_PUT']:
    oi_analyzer = OpenInterestAnalyzer()

    # Get strike distribution
    strikes = oi_analyzer.get_strike_distribution('RELIANCE', '28-NOV-2024')

    # For calls, avoid heavy resistance
    if strategy['recommended_strategy']['strategy'] == 'LONG_CALL':
        current_price = 2650  # Get from TLStockData
        strike = current_price + 50  # ATM or slightly OTM

        # Avoid if strike is at max call OI (heavy resistance)
        if strike == strikes['max_call_oi_strike']:
            strike += 50  # Go one strike higher

    # 3. Validate the options trade
    validator = TradeValidator()
    validation = validator.validate_options_call_buy('RELIANCE', strike, '28-NOV-2024')

    if validation.approved:
        print(f"✅ BUY {symbol} {strike}CE")
        # execute_options_trade(symbol, strike, 'CE', 'BUY', lots)
```

## 🔧 Integration with Broker APIs

### Example: ICICI Breeze Integration

```python
from apps.data.signals import SignalGenerator
from breeze_connect import BreezeConnect

# Initialize
generator = SignalGenerator()
breeze = BreezeConnect(api_key="YOUR_API_KEY")
breeze.generate_session(api_secret="YOUR_SECRET", session_token="YOUR_TOKEN")

# Get signal
signal = generator.generate_futures_signal('RELIANCE', '28-NOV-2024')

if signal.signal.value >= 4 and signal.confidence >= 70:
    # Place order via Breeze
    order = breeze.place_order(
        stock_code="RELIANCE",
        exchange_code="NFO",
        product="futures",
        action="buy",
        order_type="market",
        quantity=250,  # 1 lot
        expiry_date="28-Nov-2024"
    )
    print(f"Order placed: {order}")
```

## ⚙️ Automation with Celery

```python
# In apps/strategies/tasks.py

from celery import shared_task
from apps.data.trendlyne import get_all_trendlyne_data
from apps.data.importers import TrendlyneDataImporter
from apps.data.signals import SignalGenerator

@shared_task
def fetch_and_import_trendlyne_data():
    """Fetch and import Trendlyne data daily"""
    # Fetch data
    success = get_all_trendlyne_data()

    if success:
        # Import into database
        importer = TrendlyneDataImporter()
        importer.import_market_snapshot()
        importer.import_fno_data()
        importer.import_forecaster_data()

    return {"success": success}

@shared_task
def generate_daily_signals():
    """Generate trading signals every morning"""
    generator = SignalGenerator()
    opportunities = generator.scan_for_opportunities(min_confidence=70)

    # Send alerts for high-confidence opportunities
    for signal in opportunities[:5]:  # Top 5
        if signal.confidence >= 80:
            # Send notification
            pass

    return {"opportunities": len(opportunities)}

# In celery beat schedule:
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'fetch-trendlyne-daily': {
        'task': 'apps.strategies.tasks.fetch_and_import_trendlyne_data',
        'schedule': crontab(hour=8, minute=30),  # 8:30 AM daily
    },
    'generate-signals-daily': {
        'task': 'apps.strategies.tasks.generate_daily_signals',
        'schedule': crontab(hour=9, minute=0),  # 9:00 AM daily
    },
}
```

## 📈 Next Steps

1. ✅ Data models created
2. ✅ Importers built
3. ✅ Analyzers implemented
4. ✅ Signal generators ready
5. ✅ Validators created
6. ✅ Management commands available

**Now you can:**
1. Fetch Trendlyne data
2. Import into database
3. Generate trading signals
4. Validate trades
5. Integrate with your broker API
6. Automate with Celery

Your trading algorithm now has access to:
- 80+ stock metrics from Trendlyne
- OI analysis for futures and options
- Volume surge detection
- DMA trend analysis
- Comprehensive trade validation

**Ready to trade with data-driven decisions!** 🚀
