# Phase 3: File Splitting Plan

## Overview
Split 3 large files into focused, maintainable modules:
- `api_views.py` (3,180 lines) → 6 modules
- `kotak_neo.py` (1,917 lines) → 7 modules
- `breeze.py` (1,496 lines) → 7 modules

---

## 1. api_views.py Splitting Strategy (3,180 lines)

### Current Structure Analysis
**Total Functions:** 22 functions
**Categories Identified:**
1. Position sizing & P&L (2 functions, ~280 lines)
2. Order placement (2 functions, ~450 lines)
3. Margin data (1 function, ~60 lines)
4. Trade suggestions (5 functions, ~800 lines)
5. Position management (5 functions, ~1,300 lines)
6. Contract/utility queries (5 functions, ~290 lines)
7. Execution control (2 functions, ~100 lines)

### New Structure
```
apps/trading/api/
├── __init__.py                    # Exports all views
├── position_sizing.py             # Position sizing calculations
├── order_views.py                 # Order placement & status
├── margin_views.py                # Margin data fetching
├── suggestion_views.py            # Trade suggestion CRUD
├── position_management_views.py   # Position close/manage
├── contract_views.py              # Contract details, lot sizes
└── execution_views.py             # Execution control
```

### Function Mapping

**position_sizing.py:**
- `calculate_position_sizing()` (line 35)
- `calculate_pnl_scenarios()` (line 312)
- `analyze_position_averaging()` (line 3017)

**order_views.py:**
- `place_futures_order()` (line 371)
- `check_order_status()` (line 754)
- `cancel_order_placement()` (line 2961)

**margin_views.py:**
- `get_margin_data()` (line 842)

**suggestion_views.py:**
- `get_suggestion_details()` (line 907)
- `get_trade_suggestions()` (line 980)
- `update_suggestion_status()` (line 1075)
- `update_suggestion_parameters()` (line 1169)
- `get_execution_progress()` (line 1516)

**position_management_views.py:**
- `get_active_positions()` (line 1691)
- `get_position_details()` (line 2046)
- `close_position()` (line 2123)
- `close_live_position()` (line 2378)
- `get_close_position_progress()` (line 2914)

**contract_views.py:**
- `get_option_premiums()` (line 1428)
- `get_contract_details()` (line 1559)
- `get_lot_size()` (line 1642)

**execution_views.py:**
- `create_execution_control()` (line 1341)
- `cancel_execution()` (line 1387)

---

## 2. kotak_neo.py Splitting Strategy (1,917 lines)

### Current Structure Analysis
**Categories:**
- Authentication & client management
- Data fetching (limits, positions)
- Order placement
- Symbol mapping
- LTP quotes
- Batch operations

### New Structure
```
apps/brokers/integrations/neo/
├── __init__.py                # Exports main functions
├── client.py                  # Core client & auth (~200 lines)
├── data_fetcher.py            # Fetch limits/positions (~150 lines)
├── order_manager.py           # Order placement (~250 lines)
├── symbol_mapper.py           # Symbol mapping (~200 lines)
├── quotes.py                  # LTP fetching (~120 lines)
├── batch_orders.py            # Batch operations (~730 lines)
└── utils.py                   # Neo-specific utilities (~100 lines)
```

### Function Distribution

**client.py:**
- `_get_authenticated_client()`
- Authentication management
- Session token handling

**data_fetcher.py:**
- `fetch_and_save_kotak_neo_data()`
- Limit and position fetching

**order_manager.py:**
- `place_option_order()`
- `place_futures_order()`
- `square_off_position()`

**symbol_mapper.py:**
- `map_symbol_to_kotak()`
- `map_kotak_to_symbol()`
- Symbol conversion functions

**quotes.py:**
- `get_ltp_for_positions()`
- Quote fetching logic

**batch_orders.py:**
- `place_strangle_with_legs()`
- `place_short_strangle_with_neo()`
- All batch order logic

**utils.py:**
- Helper functions
- Constants
- Shared utilities

---

## 3. breeze.py Splitting Strategy (1,496 lines)

### Current Structure Analysis
**Categories:**
- API client classes
- Authentication
- Quotes & VIX
- Margin fetching
- Option chain
- Historical data
- Order placement

### New Structure
```
apps/brokers/integrations/breeze/
├── __init__.py                # Exports main classes/functions
├── client.py                  # BreezeAPI, BreezeAPIClient (~200 lines)
├── auth.py                    # Authentication (~90 lines)
├── quotes.py                  # NIFTY quotes, VIX (~120 lines)
├── margin.py                  # Margin fetching (~160 lines)
├── option_chain.py            # Option chain data (~300 lines)
├── historical.py              # Historical data (~110 lines)
└── orders.py                  # Order placement (~270 lines)
```

### Function Distribution

**client.py:**
- `BreezeAPI` class
- `BreezeAPIClient` class
- Core client functionality

**auth.py:**
- `get_or_prompt_breeze_token()`
- `save_breeze_token()`
- `get_breeze_client()`

**quotes.py:**
- `get_nifty_quote()`
- `get_india_vix()`
- Quote-related functions

**margin.py:**
- `get_nfo_margin()`
- `fetch_and_save_breeze_data()`

**option_chain.py:**
- `get_all_nifty_expiry_dates()`
- `get_next_nifty_expiry()`
- `get_next_monthly_expiry()`
- `get_and_save_option_chain_quotes()`
- `fetch_and_save_nifty_option_chain_all_expiries()`

**historical.py:**
- `save_historical_price_record()`
- `get_nifty50_historical_days()`

**orders.py:**
- `place_futures_order_with_security_master()`
- `place_option_order_with_security_master()`
- All order placement logic

---

## Implementation Strategy

### Phase 3.1: Split api_views.py
1. Create `apps/trading/api/` directory
2. Create module files with proper imports
3. Move functions to appropriate modules
4. Update `__init__.py` to export all views
5. Update URL routing to use new module paths
6. Test all endpoints

### Phase 3.2: Split kotak_neo.py
1. Create `apps/brokers/integrations/neo/` directory
2. Extract authentication to `client.py`
3. Extract data fetching to `data_fetcher.py`
4. Extract orders to `order_manager.py`
5. Extract batch operations to `batch_orders.py`
6. Update imports in other files
7. Test Neo integration

### Phase 3.3: Split breeze.py
1. Create `apps/brokers/integrations/breeze/` directory
2. Extract client classes to `client.py`
3. Extract auth to `auth.py`
4. Extract option chain to `option_chain.py`
5. Extract orders to `orders.py`
6. Update imports in other files
7. Test Breeze integration

### Phase 3.4: Update & Test
1. Update all imports throughout codebase
2. Run Django checks
3. Run comprehensive tests
4. Verify backward compatibility
5. Update documentation

---

## Benefits of This Approach

### Maintainability
- ✅ Each file <500 lines (target <300)
- ✅ Single responsibility per module
- ✅ Easier to navigate and understand

### Testability
- ✅ Can test each module independently
- ✅ Mock dependencies more easily
- ✅ Clearer test organization

### Collaboration
- ✅ Less merge conflicts
- ✅ Easier code reviews
- ✅ Clear ownership of modules

### Performance
- ✅ Faster imports (only load what's needed)
- ✅ Better code splitting for production
- ✅ Easier to optimize individual modules

---

## Risk Mitigation

### Backward Compatibility
- ✅ Keep old imports working via `__init__.py`
- ✅ Gradual migration approach
- ✅ Deprecation warnings if needed

### Testing Strategy
- ✅ Test each module after creation
- ✅ Integration tests after all splits
- ✅ Verify all URLs still work

### Rollback Plan
- ✅ Git branch for each phase
- ✅ Keep old files until verified
- ✅ Can revert easily if issues arise

---

## Success Criteria

- [ ] All files <500 lines
- [ ] All imports working
- [ ] All tests passing
- [ ] Django system check passing
- [ ] URL routing working
- [ ] Backward compatibility maintained
- [ ] Documentation updated

---

**Ready to execute Phase 3.1: Split api_views.py**
