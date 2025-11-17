# Trade Approval System - Complete Implementation Guide

## Overview

The Trade Approval System is a comprehensive workflow that transforms mCube AI from a testing platform into a production trading system with built-in transparency and user control. When algorithms generate trade suggestions, they no longer execute directly—instead, they create **trade suggestions** that require human approval before execution.

## Key Features

### 1. Algorithm Transparency
Every trade suggestion includes **complete algorithm reasoning**:
- Full calculation details (spot prices, VIX, deltas, premiums, etc.)
- Filter results (which filters passed/failed and why)
- Scoring breakdowns (composite scores from OI, sector, technical analysis)
- LLM validation details (confidence scores and reasoning)
- Position parameters and risk metrics

### 2. Approval Workflow
```
PENDING → APPROVED → EXECUTED
   ↓
AUTO_APPROVED → EXECUTED
   ↓
REJECTED
```

- **Manual Approval**: User reviews algorithm reasoning and explicitly approves/rejects
- **Auto-Approval**: Based on user configuration, suggestions meeting thresholds auto-approve
- **Risk Controls**: Daily position limits, maximum loss limits, special rules for weekends/high VIX

### 3. Audit Trail
Every action is logged with:
- Who approved/rejected and when
- Reasoning for rejection
- Auto-trade vs manual approval
- All status changes with timestamps

## System Architecture

### Database Models

#### TradeSuggestion
Stores trade suggestions with complete algorithm analysis.

```python
class TradeSuggestion(models.Model):
    user                    # User owning the account
    strategy                # kotak_strangle or icici_futures
    suggestion_type         # OPTIONS or FUTURES
    instrument              # NIFTY, RELIANCE, etc.
    direction               # LONG, SHORT, NEUTRAL
    algorithm_reasoning     # Complete analysis as JSON
    position_details        # Sizing parameters as JSON
    status                  # PENDING, APPROVED, AUTO_APPROVED, REJECTED, EXECUTED, EXPIRED, CANCELLED
    approved_by             # User who approved (null if pending/auto)
    approval_timestamp      # When approval happened
    approval_notes          # Notes or rejection reason
    is_auto_trade          # Was this auto-approved?
    executed_position      # Links to Position after execution
    created_at              # Suggestion creation time
    expires_at              # 1-hour expiry for pending suggestions
```

#### AutoTradeConfig
Per-user, per-strategy auto-approval configuration.

```python
class AutoTradeConfig(models.Model):
    user                        # User who owns this config
    strategy                    # kotak_strangle or icici_futures
    is_enabled                  # Global on/off switch
    auto_approve_threshold      # Min confidence/score for auto-approval
    max_daily_positions         # Daily position limit (default: 1)
    max_daily_loss              # Daily loss limit (default: ₹25,000)
    require_human_on_weekend    # Block auto-trade on weekends
    require_human_on_high_vix   # Block auto-trade when VIX > threshold
    vix_threshold               # VIX level (default: 18)
```

#### TradeSuggestionLog
Audit trail for all suggestion actions.

```python
class TradeSuggestionLog(models.Model):
    suggestion          # ForeignKey to TradeSuggestion
    action              # CREATED, APPROVED, AUTO_APPROVED, REJECTED, EXECUTED, EXPIRED
    user                # Who performed the action (null for system)
    notes               # Detailed notes
    created_at          # Timestamp
```

### Services Layer

#### TradeSuggestionService

**create_suggestion()**
- Entry point for strategy algorithms
- Receives algorithm reasoning and position details
- Creates TradeSuggestion in PENDING status
- Checks auto-approval criteria
- Auto-approves if thresholds met
- Returns suggestion object for logging

```python
suggestion = TradeSuggestionService.create_suggestion(
    user=account.user,
    strategy='kotak_strangle',
    suggestion_type='OPTIONS',
    instrument='NIFTY',
    direction='LONG',
    algorithm_reasoning={...},  # Complete analysis
    position_details={...}      # Sizing params
)
```

**should_auto_approve()**
- Evaluates auto-approval criteria
- For Options: Checks LLM confidence ≥ threshold
- For Futures: Checks composite score ≥ threshold
- Enforces daily position limit
- Returns boolean decision

**auto_approve()**
- Updates suggestion to AUTO_APPROVED status
- Sets approved_by to user (system approval)
- Records approval timestamp
- Creates audit log

### Formatters

**OptionsSuggestionFormatter**
Converts OptionsAlgorithmCalculator output into suggestion format:
- title, summary, calculations, filters, final_decision

**FuturesSuggestionFormatter**
Converts FuturesAlgorithmCalculator output into suggestion format:
- title, summary, scoring, llm_validation, final_decision

## API Endpoints

### Suggestion Management
- `GET /trading/suggestions/` - List pending/approved suggestions
- `GET /trading/suggestion/<id>/` - View full suggestion with reasoning
- `POST /trading/suggestion/<id>/approve/` - Approve suggestion
- `POST /trading/suggestion/<id>/reject/` - Reject with reason
- `GET /trading/suggestion/<id>/execute/` - Confirm execution details
- `POST /trading/suggestion/<id>/confirm/` - Execute and create position
- `GET /trading/history/` - Historical view of all suggestions

### Configuration
- `GET/POST /trading/config/auto-trade/` - Manage auto-trade settings per strategy

## Views

### suggestions_list.html
- Summary cards: pending, ready, auto-approved, total counts
- Table view with status badges, direction colors, action buttons
- Quick approve/reject modals
- Links to detail views and history

### suggestion_detail.html
- Trade summary (strategy, type, instrument, direction, times)
- Position details (quantity, lot size, entry price, SL/target, margin)
- Expandable algorithm reasoning section
  - Calculations breakdown
  - Filters & validation results
  - Scoring breakdown (OI/Sector/Technical)
  - LLM validation details
  - Final decision reasoning
- Approval history timeline
- Approve/Reject buttons with confirmation

### execute_confirmation.html
- Final confirmation before execution
- Risk analysis (max loss, margin required)
- Approval information (auto vs manual, who/when)
- Pre-execution checklist (4 mandatory checkboxes)
- Execute button (only enabled after all checks)
- JavaScript confirmation dialog

### auto_trade_config.html
- Separate card for each strategy
- Enable/disable toggle
- Threshold configuration (LLM % or composite score)
- Risk controls (daily positions, max loss)
- Special rules (weekend, high VIX)
- How-it-works section with current process flow

### suggestion_history.html
- Filter by status (PENDING, APPROVED, REJECTED, etc.)
- Timeline view of all suggestions
- Summary statistics (total, pending, executed, rejected)
- Expandable details with approval info
- Quick access to detail views

## Strategy Integration

### Kotak Strangle (kotak_strangle.py)

Previous Flow:
```
Entry Filters → Expiry → Strikes → Position Sizing → create_position() → Position
```

New Flow:
```
Entry Filters → Expiry → Strikes → Position Sizing → TradeSuggestionService.create_suggestion()
                                                           ↓
                                                    TradeSuggestion (PENDING)
                                                           ↓
                                    [Auto-approved if LLM confidence ≥ threshold]
                                                           ↓
                                    User Reviews & Approves (or rejects)
                                                           ↓
                                         confirm_execution() → Position
```

Algorithm reasoning includes:
- Spot price, VIX, days to expiry
- Strike distance calculation with VIX adjustment
- All filter results (passed/failed)
- Premium details (call, put, total collected)
- Position sizing (margin usage, quantity)

### ICICI Futures (icici_futures.py)

Previous Flow:
```
Screening → OI Analysis → Sector Analysis → Technical → Composite Scoring → LLM Validation
→ Position Sizing → create_position() → Position
```

New Flow:
```
[Same pipeline through LLM validation] → TradeSuggestionService.create_suggestion()
                                              ↓
                                       TradeSuggestion (PENDING)
                                              ↓
                               [Auto-approved if composite score ≥ threshold]
                                              ↓
                            User Reviews & Approves (or rejects)
                                              ↓
                                  confirm_execution() → Position
```

Algorithm reasoning includes:
- OI analysis with buildup signal and PCR
- Sector analysis verdict and alignment
- Technical analysis (Trendlyne, DMA, volume)
- Composite scoring breakdown
- LLM validation with confidence %
- Risk metrics (max loss, expected profit)

## Configuration Examples

### Conservative (Manual Review All)
```python
AutoTradeConfig(
    is_enabled=False,  # Requires manual approval for all
    auto_approve_threshold=99.99
)
```

### Moderate (Auto-Approve Only High Confidence)
```python
AutoTradeConfig(
    is_enabled=True,
    auto_approve_threshold=Decimal('95.00'),  # For options: 95% LLM confidence
    max_daily_positions=2,
    max_daily_loss=Decimal('50000.00')
)
```

### Aggressive (Auto-Approve Most)
```python
AutoTradeConfig(
    is_enabled=True,
    auto_approve_threshold=Decimal('70.00'),  # For futures: 70 composite score
    max_daily_positions=5,
    max_daily_loss=Decimal('100000.00'),
    require_human_on_high_vix=False  # Auto-trade even at high VIX
)
```

## Testing

Comprehensive test suite with 17 tests:

### Model Tests
- Creating suggestions
- Suggestion properties (is_pending, is_approved)
- Expiry logic

### Configuration Tests
- Creating auto-trade configs
- Unique constraint enforcement

### Service Tests
- Basic suggestion creation
- 1-hour expiry validation
- Suggestion logging
- Auto-approval disabled (no config)
- Auto-approval with high LLM confidence (options)
- Auto-approval with low confidence rejection
- Auto-approval with high composite score (futures)
- Daily position limit enforcement

### Workflow Tests
- Complete approval workflow (PENDING → APPROVED → EXECUTED)
- Rejection workflow with reason recording
- Audit log creation

### Authorization Tests
- User isolation (can only see own suggestions)

Run tests:
```bash
python manage.py test apps.trading.tests --verbosity=2
```

All 17 tests passing ✅

## Admin Interface

**TradeSuggestionAdmin**
- Color-coded status and direction badges
- Filter by status, strategy, user, date
- Search by user, instrument, strategy
- Expandable sections for algorithm reasoning (JSON display)
- Read-only audit logs
- Admin actions: approve, reject, mark expired
- Prevents manual suggestion creation (only via algorithm)

**AutoTradeConfigAdmin**
- Easily view and modify per-user configurations
- Color-coded enable/disable status
- Configure thresholds, daily limits, special rules

**TradeSuggestionLogAdmin**
- Read-only audit trail
- Filter by action, user, date
- Links to parent suggestion
- Colored action badges

## Migration Path

1. ✅ Create trading app models
2. ✅ Run migrations
3. ✅ Create admin configuration
4. ✅ Create UI templates
5. ✅ Integrate Kotak Strangle strategy
6. ✅ Integrate ICICI Futures strategy
7. ✅ Comprehensive testing

## Key User Flows

### User: Review Pending Suggestion
1. Go to `/trading/suggestions/`
2. See pending suggestion with status badges
3. Click "View Details"
4. See full algorithm reasoning with expandable sections
5. Review calculations, filters, scores, and decision rationale
6. Approve or Reject with optional reason

### User: Manual Approval Path
1. Suggestion created as PENDING
2. User clicks "Approve & Proceed"
3. Redirects to `/trading/suggestion/<id>/execute/`
4. Confirm pre-execution checklist
5. Click "Execute Trade Now"
6. Position created with status EXECUTED
7. Redirected to position detail page

### User: Configure Auto-Trade
1. Go to `/trading/config/auto-trade/`
2. For each strategy, toggle enable/disable
3. Set threshold (LLM % or composite score)
4. Configure risk limits (daily positions, max loss)
5. Optional: Set special rules (weekend, high VIX)
6. Save configuration

### Algorithm: Generate Suggestion
```python
# In strategy execution (kotak_strangle.py or icici_futures.py)

suggestion = TradeSuggestionService.create_suggestion(
    user=account.user,
    strategy='kotak_strangle',
    suggestion_type='OPTIONS',
    instrument='NIFTY',
    direction='LONG',
    algorithm_reasoning={...complete analysis...},
    position_details={...position params...}
)

# Returns:
# - If no config: PENDING (manual review needed)
# - If config enabled and threshold met: AUTO_APPROVED (executes if user allows)
# - If config enabled but threshold not met: PENDING (manual review needed)
```

## Important Notes

### Security
- All views are `@login_required`
- Users can only see/approve their own suggestions
- `@require_POST` on mutation endpoints
- CSRF protection on all forms

### Transparency
- All algorithm decisions are visible and explainable
- Users see exactly how the algorithm arrived at the recommendation
- Filter results show what passed and what failed

### Control
- Users can reject any suggestion at any time
- Even auto-approved suggestions can be reviewed and rejected
- Configuration can be changed at any time

### Auditability
- Every action (approve, reject, execute) is logged
- Who approved and when is recorded
- Rejection reasons are preserved
- System shows complete approval history

## Future Enhancements

1. **Notification System**: Alerts for pending suggestions, auto-approvals
2. **Webhook Integration**: Notify external systems of approvals
3. **Batch Operations**: Approve/reject multiple suggestions
4. **Analytics**: Track suggestion acceptance rates, auto-approval success rates
5. **ML Feedback**: Learn from user rejections to improve algorithm
6. **Role-Based Access**: Different approval levels (trader, risk manager, compliance)
7. **API for Third Parties**: Allow external review systems

## Troubleshooting

**Q: Why isn't my suggestion auto-approving?**
A: Check that:
1. AutoTradeConfig is created with `is_enabled=True`
2. Threshold is set correctly (LLM % for options, composite score for futures)
3. Daily position limit not exceeded
4. Actual confidence/score meets or exceeds threshold

**Q: How do I view my suggestion history?**
A: Go to `/trading/history/` to see all suggestions with full status and approval info.

**Q: Can I change thresholds after creating suggestions?**
A: Yes, any pending suggestions won't be affected (they were created with previous config). New suggestions will use new thresholds.

**Q: What happens to expired suggestions?**
A: They automatically expire after 1 hour in PENDING status. The system shows this in the suggestion list.

## Conclusion

The Trade Approval System transforms mCube AI from a testing platform into a production trading system with complete algorithm transparency, user control, and full auditability. Every trade suggestion includes the algorithm's complete reasoning, allowing users to understand and approve decisions before positions are created.
