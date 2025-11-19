# mCube AI Trading System - Documentation Index

**Last Updated:** November 19, 2025

Welcome to the mCube AI Trading System documentation! This guide helps you navigate all available documentation organized by category.

---

## 📚 Quick Navigation

| Category | Description | Go To |
|----------|-------------|-------|
| 🚀 **Getting Started** | Setup, installation, credentials | [setup/](#-setup--configuration) |
| 🏦 **Brokers** | Broker integrations (ICICI, Kotak) | [brokers/](#-broker-integration) |
| 📊 **Trading** | Trade approval, validation, workflows | [trading/](#-trade-management) |
| 🔄 **Celery Tasks** | Background tasks, schedules | [celery/](#-celery--background-tasks) |
| 📈 **Trendlyne** | Data integration, parsing | [trendlyne/](#-trendlyne-integration) |
| 💬 **Telegram** | Bot setup, commands | [telegram/](#-telegram-bot) |
| 🤖 **LLM/AI** | AI models, embeddings | [llm/](#-llm-integration) |
| 🏗️ **Architecture** | Code structure, design patterns | [architecture/](#-architecture--core-systems) |
| 🧪 **Testing** | Test pages, monitoring | [testing/](#-testing) |
| 🔧 **Troubleshooting** | Common issues, fixes | [troubleshooting/](#-troubleshooting) |
| 📋 **Status Reports** | Implementation status, updates | [status-reports/](#-implementation-status) |
| 📡 **API** | Authentication, endpoints | [api/](#-api--authentication) |
| 🧮 **Algorithms** | Trading algorithms, formulas | [algorithms/](#-algorithms--trading-strategies) |
| ✨ **Features** | Feature implementations | [features/](#-feature-implementations) |
| 🐛 **Fixes** | Bug fixes and debugging | [fixes/](#-bug-fixes--debugging) |
| 🔌 **Integrations** | Third-party integrations | [integrations/](#-third-party-integrations) |
| 🎨 **Design** | System design documents | [design/](#-system-design) |
| 📄 **Root Docs** | Main project documents | [root/](#-root-documents) |

---

## 🚀 Getting Started

### New Users Start Here:

1. **📖 Read First:** [architecture/QUICK_START.md](architecture/QUICK_START.md)
2. **⚙️ Setup System:** [setup/SETUP_GUIDE.md](setup/SETUP_GUIDE.md)
3. **🔑 Configure Credentials:** [setup/CREDENTIAL_SETUP_GUIDE.md](setup/CREDENTIAL_SETUP_GUIDE.md)
4. **🏦 Setup Brokers:** [brokers/QUICKSTART_BROKERS.md](brokers/QUICKSTART_BROKERS.md)
5. **💬 Setup Telegram:** [telegram/TELEGRAM_BOT_SETUP.md](telegram/TELEGRAM_BOT_SETUP.md)
6. **🧪 Test System:** [testing/TEST_PAGE_SETUP.md](testing/TEST_PAGE_SETUP.md)

---

## 📖 Documentation by Category

### 🏗️ Architecture & Core Systems
Located in: `docs/architecture/`

- **[QUICK_START.md](architecture/QUICK_START.md)** - Quick start guide
- **[DOCS_1_CODE_STRUCTURE.md](architecture/DOCS_1_CODE_STRUCTURE.md)** - Code organization
- **[URL_CONFIGURATION.md](architecture/URL_CONFIGURATION.md)** - URL routing
- **[BACKGROUND_TASKS_INTEGRATION.md](architecture/BACKGROUND_TASKS_INTEGRATION.md)** - Task integration
- **[GRACEFUL_ERROR_HANDLING.md](architecture/GRACEFUL_ERROR_HANDLING.md)** - Error handling
- **[LOGGING_AND_ERROR_HANDLING.md](architecture/LOGGING_AND_ERROR_HANDLING.md)** - Logging setup
- **[INDIAN_FORMATTING_IMPLEMENTATION.md](architecture/INDIAN_FORMATTING_IMPLEMENTATION.md)** - ₹ formatting
- **[DOCUMENTATION_INDEX.md](architecture/DOCUMENTATION_INDEX.md)** - Docs index
- **[DOCUMENTATION_ACCESS.md](architecture/DOCUMENTATION_ACCESS.md)** - Access control
- **[VISUAL_GUIDE.md](architecture/VISUAL_GUIDE.md)** - Visual guides
- **[URL_AUDIT_COMPLETE.md](architecture/URL_AUDIT_COMPLETE.md)** - URL audit

---

### 🚀 Setup & Configuration
Located in: `docs/setup/`

- **[SETUP_GUIDE.md](setup/SETUP_GUIDE.md)** - Complete setup guide
- **[SETUP_COMPLETE.md](setup/SETUP_COMPLETE.md)** - Setup completion checklist
- **[DOCS_2_SETUP_CONFIGURATION.md](setup/DOCS_2_SETUP_CONFIGURATION.md)** - Configuration guide
- **[CREDENTIALS_REFERENCE.md](setup/CREDENTIALS_REFERENCE.md)** - Credentials overview
- **[CREDENTIAL_SETUP_GUIDE.md](setup/CREDENTIAL_SETUP_GUIDE.md)** - Step-by-step credentials
- **[CREDENTIALS_STATUS.md](setup/CREDENTIALS_STATUS.md)** - Credentials status
- **[LIVE_CREDENTIALS.md](setup/LIVE_CREDENTIALS.md)** - Live credentials info
- **[CELERY_SETUP.md](setup/CELERY_SETUP.md)** - Celery configuration

---

### 🏦 Broker Integration
Located in: `docs/brokers/`

- **[README_BROKERS.md](brokers/README_BROKERS.md)** - Brokers overview
- **[QUICKSTART_BROKERS.md](brokers/QUICKSTART_BROKERS.md)** - Quick start guide
- **[BROKER_QUICK_REFERENCE.md](brokers/BROKER_QUICK_REFERENCE.md)** - Quick reference
- **[BROKER_INTEGRATION_SUMMARY.md](brokers/BROKER_INTEGRATION_SUMMARY.md)** - Integration details
- **[ORDER_PLACEMENT_IMPLEMENTATION.md](brokers/ORDER_PLACEMENT_IMPLEMENTATION.md)** - Order execution

---

### 📊 Trade Management
Located in: `docs/trading/`

- **[README_TRADE_APPROVAL.md](trading/README_TRADE_APPROVAL.md)** - Trade approval system
- **[TRADE_APPROVAL_SYSTEM.md](trading/TRADE_APPROVAL_SYSTEM.md)** - Approval workflow
- **[FUTURE_TRADE_VALIDATION.md](trading/FUTURE_TRADE_VALIDATION.md)** - Futures validation
- **[OPTIMIZED_STRANGLE_WORKFLOW.md](trading/OPTIMIZED_STRANGLE_WORKFLOW.md)** - Strangle workflow
- **[RISK_REWARD_METRICS.md](trading/RISK_REWARD_METRICS.md)** - Risk calculations

---

### 🔄 Celery & Background Tasks
Located in: `docs/celery/`

- **[CELERY_TASKS_REFERENCE.md](celery/CELERY_TASKS_REFERENCE.md)** ⭐ Complete task reference (19 tasks)
- **[SCHEDULE_UPDATES_SUMMARY.md](celery/SCHEDULE_UPDATES_SUMMARY.md)** Recent schedule updates

---

### 📈 Trendlyne Integration
Located in: `docs/trendlyne/`

- **[README_TRENDLYNE.md](trendlyne/README_TRENDLYNE.md)** - Overview
- **[TRENDLYNE_INTEGRATION.md](trendlyne/TRENDLYNE_INTEGRATION.md)** - Integration guide
- **[TRENDLYNE_SETUP_COMPLETE.md](trendlyne/TRENDLYNE_SETUP_COMPLETE.md)** - Setup checklist
- **[TRENDLYNE_DATA_FIX.md](trendlyne/TRENDLYNE_DATA_FIX.md)** - Data fixes
- **[TRENDLYNE_INTEGRATION_SUMMARY.md](trendlyne/TRENDLYNE_INTEGRATION_SUMMARY.md)** - Summary
- **[TRENDLYNE_WORKFLOW_UPDATE.md](trendlyne/TRENDLYNE_WORKFLOW_UPDATE.md)** - Workflow updates
- **[TRENDLYNE_DATA_TRIGGERS.md](trendlyne/TRENDLYNE_DATA_TRIGGERS.md)** - Data triggers
- **[TRENDLYNE_TRADING_INTEGRATION.md](trendlyne/TRENDLYNE_TRADING_INTEGRATION.md)** - Trading integration
- **[COMPREHENSIVE_TRENDLYNE_PARSER.md](trendlyne/COMPREHENSIVE_TRENDLYNE_PARSER.md)** - Parser details
- **[TRENDLYNE_DATA_MANAGEMENT.md](trendlyne/TRENDLYNE_DATA_MANAGEMENT.md)** - Data management

---

### 💬 Telegram Bot
Located in: `docs/telegram/`

- **[TELEGRAM_BOT_GUIDE.md](telegram/TELEGRAM_BOT_GUIDE.md)** - Complete guide
- **[TELEGRAM_BOT_SETUP.md](telegram/TELEGRAM_BOT_SETUP.md)** - Setup instructions
- **[TELEGRAM_BOT_WORKING.md](telegram/TELEGRAM_BOT_WORKING.md)** - How it works
- **[TELEGRAM_INTEGRATION_EXAMPLES.md](telegram/TELEGRAM_INTEGRATION_EXAMPLES.md)** - Code examples

---

### 🤖 LLM Integration
Located in: `docs/llm/`

- **[LLM_QUICKSTART.md](llm/LLM_QUICKSTART.md)** - Quick start
- **[LLM_MODEL_SETUP.md](llm/LLM_MODEL_SETUP.md)** - Model setup
- **[LLM_INTEGRATION.md](llm/LLM_INTEGRATION.md)** - Integration guide

---

### 🧪 Testing
Located in: `docs/testing/`

- **[TEST_PAGE_SETUP.md](testing/TEST_PAGE_SETUP.md)** - Test page setup
- **[TEST_PAGE_TRIGGER_BUTTONS.md](testing/TEST_PAGE_TRIGGER_BUTTONS.md)** - Trigger buttons
- **[TEST_PAGE_UPDATE_SUMMARY.md](testing/TEST_PAGE_UPDATE_SUMMARY.md)** - Update summary
- **[DOCS_3_RUN_TEST_MONITOR.md](testing/DOCS_3_RUN_TEST_MONITOR.md)** - Test monitoring
- **[SYSTEM_TEST_DISPLAY_EXAMPLES.md](testing/SYSTEM_TEST_DISPLAY_EXAMPLES.md)** - Display examples

---

### 🔧 Troubleshooting
Located in: `docs/troubleshooting/`

- **[NUMPY_COMPATIBILITY_FIX.md](troubleshooting/NUMPY_COMPATIBILITY_FIX.md)** - NumPy 2.0 compatibility fix

---

### 📋 Implementation Status
Located in: `docs/status-reports/` and `docs/implementation/`

**Status Reports:**
- **[status-reports/IMPLEMENTATION_STATUS_REPORT.md](status-reports/IMPLEMENTATION_STATUS_REPORT.md)** - Implementation status
- **[status-reports/UPDATED_STATUS_REPORT.md](status-reports/UPDATED_STATUS_REPORT.md)** - Latest updates

**Implementation Guides:**
- **[implementation/IMPLEMENTATION_CHECKLIST.md](implementation/IMPLEMENTATION_CHECKLIST.md)** - Checklist
- **[implementation/IMPLEMENTATION_COMPLETE.md](implementation/IMPLEMENTATION_COMPLETE.md)** - Completion status
- **[implementation/IMPLEMENTATION_GUIDE.md](implementation/IMPLEMENTATION_GUIDE.md)** - Guide
- **[implementation/FIXES_SUMMARY.md](implementation/FIXES_SUMMARY.md)** - Bug fixes
- **[implementation/TEMPLATE_FIXES_SUMMARY.md](implementation/TEMPLATE_FIXES_SUMMARY.md)** - Template fixes
- **[implementation/ENHANCEMENT_SUMMARY.md](implementation/ENHANCEMENT_SUMMARY.md)** - Enhancements

---

### 📡 API & Authentication
Located in: `docs/api/`

- **[API_ENDPOINTS_REFERENCE.md](api/API_ENDPOINTS_REFERENCE.md)** - Endpoint reference
- **[AUTHENTICATION_GUIDE.md](api/AUTHENTICATION_GUIDE.md)** - Auth guide
- **[AUTHENTICATION_FLOW_UPDATE.md](api/AUTHENTICATION_FLOW_UPDATE.md)** - Auth flow details

---

### 🧮 Algorithms & Trading Strategies
Located in: `docs/algorithms/`

- **[ALGORITHM_IMPROVEMENTS_REAL_DATA.md](algorithms/ALGORITHM_IMPROVEMENTS_REAL_DATA.md)** - Real data improvements
- **[FUTURES_ALGORITHM_50PERCENT_RULE.md](algorithms/FUTURES_ALGORITHM_50PERCENT_RULE.md)** - 50% margin rule
- **[FUTURES_ALGORITHM_POSITION_SIZING.md](algorithms/FUTURES_ALGORITHM_POSITION_SIZING.md)** - Position sizing algorithm
- **[TRADE_SUGGESTION_SYSTEM.md](algorithms/TRADE_SUGGESTION_SYSTEM.md)** - Trade suggestion system

---

### ✨ Feature Implementations
Located in: `docs/features/`

- **[BACKGROUND_TASK_LOGGING.md](features/BACKGROUND_TASK_LOGGING.md)** - Background task logging
- **[FUTURES_50_PERCENT_MARGIN_FIX.md](features/FUTURES_50_PERCENT_MARGIN_FIX.md)** - Futures margin feature
- **[FUTURES_COMPLETE_IMPLEMENTATION.md](features/FUTURES_COMPLETE_IMPLEMENTATION.md)** - Complete futures implementation
- **[FUTURES_POSITION_SIZING.md](features/FUTURES_POSITION_SIZING.md)** - Futures position sizing
- **[FUTURES_SUGGESTION_TRACKING.md](features/FUTURES_SUGGESTION_TRACKING.md)** - Suggestion tracking
- **[LOT_CALCULATIONS_FEATURE.md](features/LOT_CALCULATIONS_FEATURE.md)** - Lot calculations
- **[MARGINS_FEATURE_IMPLEMENTATION.md](features/MARGINS_FEATURE_IMPLEMENTATION.md)** - Margins feature
- **[NIFTY_STRANGLE_ENHANCEMENTS_COMPLETE.md](features/NIFTY_STRANGLE_ENHANCEMENTS_COMPLETE.md)** - Strangle enhancements
- **[NIFTY_STRANGLE_IMPLEMENTATION.md](features/NIFTY_STRANGLE_IMPLEMENTATION.md)** - Strangle implementation
- **[NIFTY_STRANGLE_PHASE1_COMPLETE.md](features/NIFTY_STRANGLE_PHASE1_COMPLETE.md)** - Strangle Phase 1
- **[POSITION_SIZING_COMPLETE.md](features/POSITION_SIZING_COMPLETE.md)** - Position sizing complete
- **[POSITION_SIZING_IMPLEMENTATION.md](features/POSITION_SIZING_IMPLEMENTATION.md)** - Position sizing
- **[POSITION_SIZING_REDESIGN.md](features/POSITION_SIZING_REDESIGN.md)** - Position sizing redesign
- **[POSITION_SUMMARY_REFRESH.md](features/POSITION_SUMMARY_REFRESH.md)** - Position summary
- **[SUPPORT_RESISTANCE_IMPLEMENTATION.md](features/SUPPORT_RESISTANCE_IMPLEMENTATION.md)** - Support/Resistance

---

### 🐛 Bug Fixes & Debugging
Located in: `docs/fixes/`

- **[DEBUGGING_STRANGLE_BUTTON.md](fixes/DEBUGGING_STRANGLE_BUTTON.md)** - Strangle button debug
- **[ERROR_VERIFICATION_REPORT.md](fixes/ERROR_VERIFICATION_REPORT.md)** - Error verification
- **[IMPORT_FIX_CREDENTIALSTORE.md](fixes/IMPORT_FIX_CREDENTIALSTORE.md)** - Import fix
- **[MODULE_IMPORT_FIX.md](fixes/MODULE_IMPORT_FIX.md)** - Module import fix
- **[PSYCHOLOGICAL_LEVELS_FIX.md](fixes/PSYCHOLOGICAL_LEVELS_FIX.md)** - Psychological levels fix
- **[STRANGLE_UI_FIX_SUMMARY.md](fixes/STRANGLE_UI_FIX_SUMMARY.md)** - Strangle UI fixes
- **[SYNTAX_ERROR_FIX_FINAL.md](fixes/SYNTAX_ERROR_FIX_FINAL.md)** - Syntax error fix
- **[TAKE_TRADE_BUTTON_FIX.md](fixes/TAKE_TRADE_BUTTON_FIX.md)** - Take trade button fix
- **[TAKE_TRADE_DEBUG.md](fixes/TAKE_TRADE_DEBUG.md)** - Take trade debugging
- **[TEST_JS_FIX.md](fixes/TEST_JS_FIX.md)** - JavaScript fix
- **[VIEW_DETAILS_FIX.md](fixes/VIEW_DETAILS_FIX.md)** - View details fix
- **[VIX_FIX.md](fixes/VIX_FIX.md)** - VIX fix
- **[ZERO_LOTS_FIX.md](fixes/ZERO_LOTS_FIX.md)** - Zero lots fix

---

### 🔌 Third-Party Integrations
Located in: `docs/integrations/`

- **[BREEZE_MARGIN_FIX.md](integrations/BREEZE_MARGIN_FIX.md)** - Breeze margin integration
- **[BREEZE_SESSION_TOKEN_RENEWAL.md](integrations/BREEZE_SESSION_TOKEN_RENEWAL.md)** - Breeze session renewal
- **[HISTORICAL_DATA_AND_VIX_FIX.md](integrations/HISTORICAL_DATA_AND_VIX_FIX.md)** - Historical data & VIX

---

### 🎨 System Design
Located in: `docs/design/`

- **[mcube-ai.design.md](design/mcube-ai.design.md)** - Complete system design document
- **[COMPREHENSIVE_DATA_INTEGRATION_STATUS.md](design/COMPREHENSIVE_DATA_INTEGRATION_STATUS.md)** - Data integration status

---

### 📄 Root Documents
Located in: `docs/root/`

- **[INSTALL.md](root/INSTALL.md)** - Installation guide
- **[PROJECT_README.md](root/PROJECT_README.md)** - Main project README

---

## 📊 Documentation by Role

### For Traders

**Essential Reading:**
- [Trading System Overview](trading/README_TRADE_APPROVAL.md)
- [Telegram Bot Guide](telegram/TELEGRAM_BOT_GUIDE.md)
- [Risk/Reward Metrics](trading/RISK_REWARD_METRICS.md)
- [Broker Quick Reference](brokers/BROKER_QUICK_REFERENCE.md)

**Trading Workflows:**
- [Strangle Strategy](trading/OPTIMIZED_STRANGLE_WORKFLOW.md)
- [Futures Validation](trading/FUTURE_TRADE_VALIDATION.md)
- [Trade Approval](trading/TRADE_APPROVAL_SYSTEM.md)

---

### For Developers

**Essential Reading:**
- [Code Structure](architecture/DOCS_1_CODE_STRUCTURE.md)
- [Quick Start Guide](architecture/QUICK_START.md)
- [URL Configuration](architecture/URL_CONFIGURATION.md)
- [Error Handling](architecture/GRACEFUL_ERROR_HANDLING.md)

**Development Guides:**
- [Celery Tasks Reference](celery/CELERY_TASKS_REFERENCE.md)
- [LLM Integration](llm/LLM_INTEGRATION.md)
- [API Endpoints](api/API_ENDPOINTS_REFERENCE.md)
- [Background Tasks](architecture/BACKGROUND_TASKS_INTEGRATION.md)

---

### For System Administrators

**Essential Reading:**
- [Setup Guide](setup/SETUP_GUIDE.md)
- [Celery Setup](setup/CELERY_SETUP.md)
- [Credentials Management](setup/CREDENTIALS_REFERENCE.md)

**Operations:**
- [Celery Tasks Reference](celery/CELERY_TASKS_REFERENCE.md)
- [Schedule Updates](celery/SCHEDULE_UPDATES_SUMMARY.md)
- [Test Monitoring](testing/DOCS_3_RUN_TEST_MONITOR.md)

---

## 📊 Recent Updates

### November 19, 2025
- ✅ **Major Documentation Reorganization**
  - Created 7 new categories: algorithms, features, fixes, integrations, design, root
  - Moved 38 root-level .md files to appropriate folders
  - Updated documentation index with all new categories
  - Improved documentation discoverability and organization

### November 17, 2025
- ✅ Reorganized documentation structure
- ✅ Updated Celery task schedules
- ✅ Fixed NumPy 2.0 compatibility
- ✅ Added comprehensive Celery tasks reference
- ✅ Created schedule updates summary

### Latest Documents
1. [Complete System Design](design/mcube-ai.design.md) - Comprehensive system design document
2. [Futures Complete Implementation](features/FUTURES_COMPLETE_IMPLEMENTATION.md) - Full futures trading system
3. [Algorithm Improvements](algorithms/ALGORITHM_IMPROVEMENTS_REAL_DATA.md) - Real data-based improvements

---

## 🎯 Common Tasks

### Setup Tasks
- [ ] Initial system setup → [setup/SETUP_GUIDE.md](setup/SETUP_GUIDE.md)
- [ ] Configure credentials → [setup/CREDENTIAL_SETUP_GUIDE.md](setup/CREDENTIAL_SETUP_GUIDE.md)
- [ ] Setup Celery → [setup/CELERY_SETUP.md](setup/CELERY_SETUP.md)
- [ ] Setup Telegram bot → [telegram/TELEGRAM_BOT_SETUP.md](telegram/TELEGRAM_BOT_SETUP.md)

### Development Tasks
- [ ] Understand code structure → [architecture/DOCS_1_CODE_STRUCTURE.md](architecture/DOCS_1_CODE_STRUCTURE.md)
- [ ] Add new API endpoint → [api/API_ENDPOINTS_REFERENCE.md](api/API_ENDPOINTS_REFERENCE.md)
- [ ] Create Celery task → [celery/CELERY_TASKS_REFERENCE.md](celery/CELERY_TASKS_REFERENCE.md)
- [ ] Integrate LLM model → [llm/LLM_INTEGRATION.md](llm/LLM_INTEGRATION.md)

### Operations Tasks
- [ ] Monitor Celery tasks → [celery/CELERY_TASKS_REFERENCE.md](celery/CELERY_TASKS_REFERENCE.md)
- [ ] Update task schedules → [celery/SCHEDULE_UPDATES_SUMMARY.md](celery/SCHEDULE_UPDATES_SUMMARY.md)
- [ ] Troubleshoot issues → [troubleshooting/](troubleshooting/)
- [ ] Run system tests → [testing/TEST_PAGE_SETUP.md](testing/TEST_PAGE_SETUP.md)

---

## 📞 Quick Links

| What You Need | Where To Find It |
|---------------|-----------------|
| Setup from scratch | [setup/SETUP_GUIDE.md](setup/SETUP_GUIDE.md) |
| Quick start guide | [architecture/QUICK_START.md](architecture/QUICK_START.md) |
| Broker integration | [brokers/QUICKSTART_BROKERS.md](brokers/QUICKSTART_BROKERS.md) |
| Celery tasks | [celery/CELERY_TASKS_REFERENCE.md](celery/CELERY_TASKS_REFERENCE.md) |
| Telegram bot | [telegram/TELEGRAM_BOT_GUIDE.md](telegram/TELEGRAM_BOT_GUIDE.md) |
| Trade workflows | [trading/README_TRADE_APPROVAL.md](trading/README_TRADE_APPROVAL.md) |
| API reference | [api/API_ENDPOINTS_REFERENCE.md](api/API_ENDPOINTS_REFERENCE.md) |
| Troubleshooting | [troubleshooting/](troubleshooting/) |

---

## 🔄 Contributing to Documentation

When adding new documentation:

1. **Choose the right folder:**
   - **Algorithms & strategies** → `algorithms/`
   - **API docs** → `api/`
   - **Architecture docs** → `architecture/`
   - **Broker integrations** → `brokers/`
   - **Background tasks** → `celery/`
   - **System design** → `design/`
   - **Feature implementations** → `features/`
   - **Bug fixes & debugging** → `fixes/`
   - **Implementation guides** → `implementation/`
   - **Third-party integrations** → `integrations/`
   - **LLM/AI** → `llm/`
   - **Main project docs** → `root/`
   - **Setup guides** → `setup/`
   - **Status reports** → `status-reports/`
   - **Telegram bot** → `telegram/`
   - **Testing** → `testing/`
   - **Trading workflows** → `trading/`
   - **Trendlyne data** → `trendlyne/`
   - **Troubleshooting** → `troubleshooting/`

2. **Follow naming convention:**
   - Use `UPPERCASE_WITH_UNDERSCORES.md`
   - Be descriptive

3. **Update this index:**
   - Add your document to the relevant category
   - Update "Recent Updates" section

---

## 📁 Documentation Folder Structure

```
docs/
├── algorithms/          # Trading algorithms and strategies (4 docs)
├── api/                 # API endpoints and authentication (3 docs)
├── architecture/        # System architecture and design (11 docs)
├── brokers/             # Broker integrations (5 docs)
├── celery/              # Background tasks and schedules (2 docs)
├── design/              # System design documents (2 docs)
├── features/            # Feature implementations (15 docs)
├── fixes/               # Bug fixes and debugging (13 docs)
├── implementation/      # Implementation guides (6 docs)
├── integrations/        # Third-party integrations (3 docs)
├── llm/                 # LLM/AI integration (3 docs)
├── root/                # Main project documents (2 docs)
├── setup/               # Setup and configuration (8 docs)
├── status-reports/      # Status and progress reports (2 docs)
├── telegram/            # Telegram bot (4 docs)
├── testing/             # Testing documentation (5 docs)
├── trading/             # Trading workflows (5 docs)
├── trendlyne/           # Trendlyne integration (10 docs)
└── troubleshooting/     # Troubleshooting guides (1 doc)
```

---

**Documentation Version:** 3.0
**Last Major Update:** November 19, 2025
**Total Documents:** 103
**Total Categories:** 19
**Status:** ✅ Complete & Organized
