## Level 2 Deep-Dive Analysis System - Implementation Guide

## Overview

The Level 2 Deep-Dive Analysis system has been successfully implemented to provide comprehensive fundamental and technical analysis for futures trading decisions. This system works as a **post-filter analysis tool** that ONLY analyzes stocks that have PASSED the Level 1 filtering system.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Trading Flow                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Level 1 (Automatic)                                         │
│     └─> Futures Algorithm (9-step analysis)                     │
│         └─> Output: PASS/FAIL verdict                           │
│                                                                  │
│  2. Level 2 (Manual Trigger) - ONLY for PASSED stocks          │
│     └─> Deep-Dive Analysis (ASYNC with Fresh Data)             │
│         ├─> Fetch fresh Trendlyne data (60-120s)               │
│         ├─> Fundamental Analysis                                │
│         ├─> Valuation Analysis                                  │
│         ├─> Institutional Behavior                              │
│         ├─> Technical Deep-Dive                                 │
│         ├─> Risk Assessment                                     │
│         └─> Comprehensive Report with Recommendations           │
│                                                                  │
│  3. Human Decision                                              │
│     └─> Review report → Execute/Modify/Reject trade            │
│                                                                  │
│  4. Trade Tracking                                              │
│     └─> Record decisions and outcomes                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components Implemented

### 1. Data Aggregation Layer
**File:** `apps/trading/data_aggregator.py`

**Class:** `TrendlyneDataAggregator`

**Purpose:** Aggregates all available Trendlyne data for a stock

**Data Sources:**
- `TLStockData` - 80+ fundamental and technical fields
- `ContractStockData` - F&O aggregated metrics
- `ContractData` - Individual contract data
- Forecaster CSVs - 21 analyst consensus files

**Key Method:**
```python
aggregator = TrendlyneDataAggregator('RELIANCE')
data = aggregator.fetch_all_data()
```

### 2. Analysis Components

#### a) Financial Performance Analyzer
**File:** `apps/trading/level2_analyzers.py`

**Class:** `FinancialPerformanceAnalyzer`

**Analyzes:**
- Profitability (ROE, ROA, margins)
- Revenue quality and growth
- Earnings quality and surprises
- Cash flow strength
- Balance sheet health (Piotroski score)

#### b) Valuation Deep-Dive
**File:** `apps/trading/level2_analyzers.py`

**Class:** `ValuationDeepDive`

**Analyzes:**
- Absolute valuation (P/E, PEG, P/B)
- Historical context (3yr, 5yr averages)
- Relative valuation vs sector/industry
- Valuation percentiles

#### c) Institutional Behavior Analyzer
**File:** `apps/trading/level2_analyzers_part2.py`

**Class:** `InstitutionalBehaviorAnalyzer`

**Analyzes:**
- Promoter holding trends and pledging
- FII/DII activity and flows
- Mutual fund accumulation/distribution
- F&O positioning (PCR, OI buildup, MWPL)
- Smart money indicators

#### d) Technical Deep-Dive
**File:** `apps/trading/level2_analyzers_part2.py`

**Class:** `TechnicalDeepDive`

**Analyzes:**
- Trend analysis (moving averages, alignment)
- Support/resistance levels
- Momentum indicators (RSI, MACD, MFI, ADX)
- Volatility metrics (ATR, Beta)
- Volume and delivery patterns

#### e) Risk Assessment
**File:** `apps/trading/level2_analyzers_part2.py`

**Class:** `RiskAssessment`

**Analyzes:**
- Market risk (beta, volatility)
- Fundamental risks
- Technical risks
- Overall risk scoring and grading

### 3. Report Generator
**File:** `apps/trading/level2_report_generator.py`

**Class:** `Level2ReportGenerator`

**Generates:**
- Executive summary with conviction score (0-100)
- Detailed analysis across all dimensions
- Trading recommendations (entry, stop-loss, targets)
- Decision matrix (bullish/bearish factors)
- Key monitorables and catalysts

**Usage:**
```python
generator = Level2ReportGenerator(
    symbol='RELIANCE',
    expiry_date='2024-01-25',
    level1_results={...}
)
report = generator.generate_report()
```

### 4. Database Model
**File:** `apps/data/models.py`

**Model:** `DeepDiveAnalysis`

**Fields:**
- Basic info (symbol, expiry, level1_score)
- Report data (complete JSON report)
- Decision tracking (EXECUTED/MODIFIED/REJECTED/PENDING)
- Trade tracking (entry, exit, P&L)
- Performance metadata (conviction_score, risk_grade)

**Methods:**
```python
deep_dive.mark_executed(entry_price=2850, lot_size=100)
deep_dive.close_trade(exit_price=2920)
# Automatically calculates P&L
```

### 5. API Endpoints
**File:** `apps/trading/views_level2.py`

**Endpoints:**

#### Generate Deep-Dive Analysis (ASYNC)
```http
POST /api/trading/futures/deep-dive/
Content-Type: application/json

{
    "symbol": "RELIANCE",
    "expiry_date": "2024-01-25",
    "level1_results": {
        "verdict": "PASS",
        "composite_score": 72,
        "direction": "LONG"
    }
}
```

**Response (Immediate):**
```json
{
    "success": true,
    "analysis_id": 123,
    "status": "PROCESSING",
    "message": "Deep-dive analysis initiated. Fetching fresh Trendlyne data...",
    "estimated_time": "60-120 seconds",
    "poll_url": "/api/trading/deep-dive/123/status/"
}
```

**Background Process:**
1. Fetches fresh Trendlyne data (all sources)
2. Runs comprehensive analysis across all dimensions
3. Generates report with conviction score
4. Stores in database with status='COMPLETED'

**Frontend should poll** `/api/trading/deep-dive/123/status/` every 3 seconds

#### Check Analysis Status (POLLING)
```http
GET /api/trading/deep-dive/123/status/
```

**Response (While Processing):**
```json
{
    "success": true,
    "analysis_id": 123,
    "status": "PROCESSING",
    "message": "Running comprehensive multi-factor analysis...",
    "progress": 66,
    "symbol": "RELIANCE",
    "expiry": "2024-01-25"
}
```

**Response (Completed):**
```json
{
    "success": true,
    "analysis_id": 123,
    "status": "COMPLETED",
    "conviction_score": 78,
    "risk_grade": "MODERATE",
    "completed_at": "2024-01-20T15:30:00Z",
    "report": {
        "metadata": {...},
        "executive_summary": {
            "one_line_verdict": "🟢 HIGH CONVICTION BUY - Score: 78/100",
            "conviction_score": 78,
            "key_strengths": [...],
            "key_concerns": [...],
            "recommended_action": "EXECUTE TRADE",
            "critical_levels": {...}
        },
        "detailed_analysis": {
            "fundamental_analysis": {...},
            "valuation_analysis": {...},
            "institutional_behavior": {...},
            "technical_analysis": {...},
            "risk_assessment": {...}
        },
        "trading_recommendation": {
            "entry_strategy": "Enter at market price (~₹2850)",
            "position_sizing": {...},
            "stop_loss": {...},
            "profit_targets": [...],
            "time_horizon": "3-7 days",
            "key_monitorables": [...]
        },
        "decision_matrix": {
            "bullish_factors": [...],
            "bearish_factors": [...],
            "key_risks": [...],
            "catalysts": [...]
        }
    }
}
```

#### Record Decision
```http
POST /api/trading/deep-dive/123/decision/
Content-Type: application/json

{
    "decision": "EXECUTED",
    "notes": "Strong setup, executing full position",
    "entry_price": 2850.50,
    "lot_size": 100
}
```

#### Close Trade
```http
POST /api/trading/deep-dive/123/close/
Content-Type: application/json

{
    "exit_price": 2920.75
}
```

**Response:**
```json
{
    "success": true,
    "analysis_id": 123,
    "entry_price": 2850.50,
    "exit_price": 2920.75,
    "pnl": 7025.00,
    "pnl_pct": 2.47
}
```

#### Get History
```http
GET /api/trading/deep-dive/history/?symbol=RELIANCE&decision=EXECUTED
```

#### Get Performance Metrics
```http
GET /api/trading/deep-dive/performance/
```

**Response:**
```json
{
    "success": true,
    "metrics": {
        "total_analyses": 50,
        "executed_trades": 35,
        "execution_rate": 70.0,
        "closed_trades": 30,
        "open_trades": 5,
        "win_rate": 66.67,
        "avg_win_pct": 3.2,
        "avg_loss_pct": -1.8,
        "total_pnl": 45250.50
    }
}
```

## Setup Instructions

### 1. Run Migrations
```bash
cd /Users/anupammangudkar/Projects/mCube-ai/mCube-ai
python manage.py makemigrations data
python manage.py migrate
```

### 2. Register URLs
Add to main `urls.py`:
```python
from django.urls import path, include

urlpatterns = [
    # ... existing patterns ...
    path('api/trading/', include('apps.trading.urls_level2')),
]
```

### 3. Register Model in Admin (Optional)
Add to `apps/data/admin.py`:
```python
from apps.data.models import DeepDiveAnalysis

@admin.register(DeepDiveAnalysis)
class DeepDiveAnalysisAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'expiry', 'user', 'decision', 'conviction_score', 'created_at']
    list_filter = ['decision', 'trade_executed', 'risk_grade']
    search_fields = ['symbol', 'user__username']
    readonly_fields = ['created_at', 'updated_at']
```

## Usage Flow

### For Frontend Integration

```javascript
// 1. Run Level 1 Analysis
const level1Response = await fetch('/api/futures/analyze/', {
    method: 'POST',
    body: JSON.stringify({
        symbol: 'RELIANCE',
        expiry: '2024-01-25'
    })
});
const level1Data = await level1Response.json();

// 2. If PASSED, show "Deep-Dive" button
if (level1Data.verdict === 'PASS') {
    showDeepDiveButton();
}

// 3. When user clicks Deep-Dive button
async function runDeepDive() {
    const response = await fetch('/api/trading/futures/deep-dive/', {
        method: 'POST',
        body: JSON.stringify({
            symbol: 'RELIANCE',
            expiry_date: '2024-01-25',
            level1_results: level1Data
        })
    });
    const deepDiveData = await response.json();

    // Display comprehensive report
    displayDeepDiveReport(deepDiveData.report);
}

// 4. When user makes decision
async function executeTradeDecision(analysisId) {
    await fetch(`/api/trading/deep-dive/${analysisId}/decision/`, {
        method: 'POST',
        body: JSON.stringify({
            decision: 'EXECUTED',
            notes: 'Strong conviction based on fundamentals',
            entry_price: 2850.50,
            lot_size: 100
        })
    });
}

// 5. When closing trade
async function closeTrade(analysisId) {
    await fetch(`/api/trading/deep-dive/${analysisId}/close/`, {
        method: 'POST',
        body: JSON.stringify({
            exit_price: 2920.75
        })
    });
}
```

## Key Features

### 1. Comprehensive Analysis
- **80+ Trendlyne fields** analyzed
- **21 forecaster files** integrated
- **Multi-dimensional scoring** across 6 categories
- **Conviction score** (0-100) for decision confidence

### 2. Actionable Recommendations
- Specific entry strategy
- Position sizing based on conviction and risk
- Stop-loss levels (support + ATR based)
- Multiple profit targets
- Holding period suggestions
- Key monitorables

### 3. Decision Tracking
- Complete audit trail of all analyses
- Decision outcomes (executed/modified/rejected)
- Trade P&L tracking
- Performance metrics and analytics

### 4. Risk Management
- Multi-dimensional risk assessment
- Risk grading (LOW/MODERATE/HIGH/VERY HIGH)
- Position sizing adjustments based on risk
- Identification of key risks and concerns

## Report Structure

### Executive Summary
- One-line verdict with conviction score
- Top 5 strengths
- Top 5 concerns
- Recommended action
- Critical price levels

### Detailed Analysis
1. **Fundamental Analysis**
   - Profitability metrics and quality score
   - Revenue quality and momentum
   - Earnings quality and surprises
   - Cash flow analysis
   - Balance sheet strength

2. **Valuation Analysis**
   - Absolute valuation (P/E, PEG, P/B)
   - Historical context
   - Relative valuation vs sector/industry
   - Overall valuation assessment

3. **Institutional Behavior**
   - Promoter activity and confidence
   - FII/DII flows
   - Mutual fund activity
   - F&O positioning
   - Smart money signals

4. **Technical Analysis**
   - Trend analysis and MA alignment
   - Momentum indicators
   - Volatility metrics
   - Volume patterns
   - Support/resistance levels

5. **Risk Assessment**
   - Market risk
   - Fundamental risks
   - Technical risks
   - Overall risk score and grade

### Trading Recommendation
- Entry strategy
- Position sizing with rationale
- Stop-loss level and method
- Profit targets (multiple levels)
- Time horizon
- Key monitorables

### Decision Matrix
- Bullish factors (opportunities)
- Bearish factors (concerns)
- Key risks
- Potential catalysts

## Performance Tracking

The system tracks:
- Analysis count and execution rate
- Win rate and average returns
- Total P&L across all trades
- Decision breakdown
- Risk-adjusted returns

This allows for:
- Continuous improvement of the system
- Validation of conviction scoring
- Understanding of decision patterns
- Performance attribution analysis

## Next Steps

### Immediate Actions
1. Run migrations to create DeepDiveAnalysis table
2. Register Level 2 URLs in main URL configuration
3. Test API endpoints with sample data
4. Build UI components for report display

### Future Enhancements (Level 3)
- Machine learning models for pattern recognition
- Sentiment analysis from news and social media
- Market regime detection
- Automated parameter tuning
- Backtesting framework integration

## Support and Documentation

- **Main Plan:** See `FUTURES_DEEP_DIVE_ANALYSIS_PLAN.md` for complete design details
- **Code Location:** `apps/trading/level2_*.py` files
- **Models:** `apps/data/models.py` - `DeepDiveAnalysis` model
- **API Docs:** This file contains all endpoint specifications

## Summary

The Level 2 Deep-Dive Analysis system has been fully implemented and is ready for integration. It provides comprehensive analysis using ALL available Trendlyne data fields, generates actionable trading recommendations, and maintains a complete audit trail for performance tracking and continuous improvement.

The system is designed to work seamlessly with the existing Level 1 filtering system, acting as a powerful decision-support tool rather than an automated trading system, ensuring human oversight remains central to the trading process.