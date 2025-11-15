"""
Management command to test all core business logic services

Usage:
    python manage.py test_services
    python manage.py test_services --verbose
"""

from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import BrokerAccount
from apps.positions.models import Position
from apps.strategies.models import StrategyConfig
from apps.risk.models import RiskLimit

# Import all services
from apps.accounts.services.margin_manager import (
    calculate_usable_margin,
    check_margin_availability,
    calculate_position_size,
    validate_margin_for_averaging,
)
from apps.positions.services.position_manager import (
    morning_check,
    create_position,
    update_position_price,
    close_position,
    get_position_summary,
    average_position,
)
from apps.positions.services.exit_manager import (
    check_exit_conditions,
    should_exit_position,
    get_recommended_exit_action,
)
from apps.core.services.expiry_selector import (
    select_expiry_for_options,
    select_expiry_for_futures,
    validate_expiry_for_strategy,
)
from apps.risk.services.risk_manager import (
    check_risk_limits,
    enforce_risk_limits,
    get_risk_status,
)


class Command(BaseCommand):
    help = 'Test all core business logic services with mock data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        self.verbose = options['verbose']

        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('TESTING mCube CORE BUSINESS LOGIC SERVICES'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))

        # Clean up any existing test data
        self.cleanup_test_data()

        # Run all tests
        self.test_1_setup_accounts()
        self.test_2_margin_manager()
        self.test_3_position_manager()
        self.test_4_exit_manager()
        self.test_5_expiry_selector()
        self.test_6_risk_manager()

        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('ALL TESTS COMPLETED SUCCESSFULLY ✅'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))

    def cleanup_test_data(self):
        """Clean up test data from previous runs"""
        self.stdout.write('\n🧹 Cleaning up test data...')

        BrokerAccount.objects.filter(account_name__startswith='TEST_').delete()
        Position.objects.filter(instrument__startswith='TEST_').delete()

        self.stdout.write(self.style.SUCCESS('✅ Cleanup complete\n'))

    def test_1_setup_accounts(self):
        """Test 1: Setup Test Accounts"""
        self.stdout.write(self.style.WARNING('\n' + '─'*80))
        self.stdout.write(self.style.WARNING('TEST 1: Setup Test Accounts'))
        self.stdout.write(self.style.WARNING('─'*80))

        # Create Kotak account (Options - ₹6 Crores)
        self.kotak_account = BrokerAccount.objects.create(
            broker='KOTAK',
            account_number='TEST_KOTAK_001',
            account_name='TEST_KOTAK_OPTIONS',
            allocated_capital=Decimal('60000000'),  # ₹6 Crores
            is_active=True,
            is_paper_trading=True,
            max_daily_loss=Decimal('200000'),  # ₹2 Lakhs
            max_weekly_loss=Decimal('500000'),  # ₹5 Lakhs
        )

        # Create Kotak strategy config
        StrategyConfig.objects.create(
            account=self.kotak_account,
            strategy_type='WEEKLY_NIFTY_STRANGLE',
            is_active=True,
            initial_margin_usage_pct=Decimal('50.00'),
            min_profit_pct_to_exit=Decimal('50.00'),
            base_delta_pct=Decimal('0.50'),
            min_days_to_expiry=1,
        )

        self.stdout.write(f'  ✅ Created Kotak account: ₹{self.kotak_account.allocated_capital:,.0f}')

        # Create ICICI account (Futures - ₹1.2 Crores)
        self.icici_account = BrokerAccount.objects.create(
            broker='ICICI',
            account_number='TEST_ICICI_001',
            account_name='TEST_ICICI_FUTURES',
            allocated_capital=Decimal('12000000'),  # ₹1.2 Crores
            is_active=True,
            is_paper_trading=True,
            max_daily_loss=Decimal('150000'),  # ₹1.5 Lakhs
            max_weekly_loss=Decimal('400000'),  # ₹4 Lakhs
        )

        # Create ICICI strategy config
        StrategyConfig.objects.create(
            account=self.icici_account,
            strategy_type='LLM_VALIDATED_FUTURES',
            is_active=True,
            initial_margin_usage_pct=Decimal('50.00'),
            min_profit_pct_to_exit=Decimal('50.00'),
            min_days_to_future_expiry=15,
            allow_averaging=True,
            max_average_attempts=2,
        )

        self.stdout.write(f'  ✅ Created ICICI account: ₹{self.icici_account.allocated_capital:,.0f}')

    def test_2_margin_manager(self):
        """Test 2: Margin Manager - 50% Rule"""
        self.stdout.write(self.style.WARNING('\n' + '─'*80))
        self.stdout.write(self.style.WARNING('TEST 2: Margin Manager - 50% MARGIN RULE'))
        self.stdout.write(self.style.WARNING('─'*80))

        # Test calculate_usable_margin
        margins = calculate_usable_margin(self.kotak_account)

        assert margins['total_capital'] == Decimal('60000000'), "Total capital mismatch"
        assert margins['available_margin'] == Decimal('60000000'), "Available margin mismatch"
        assert margins['usable_margin'] == Decimal('30000000'), "50% RULE FAILED!"
        assert margins['reserved_margin'] == Decimal('30000000'), "Reserve calculation failed"

        self.stdout.write(f"  ✅ 50% MARGIN RULE: Usable = ₹{margins['usable_margin']:,.0f} (50% of ₹{margins['available_margin']:,.0f})")

        # Test check_margin_availability
        is_available, msg = check_margin_availability(
            self.kotak_account,
            Decimal('25000000')  # ₹2.5 Cr (within 50% limit)
        )

        assert is_available == True, "Margin check failed for valid amount"
        self.stdout.write(f"  ✅ Margin availability check: PASSED")

        # Test margin check failure
        is_available, msg = check_margin_availability(
            self.kotak_account,
            Decimal('35000000')  # ₹3.5 Cr (exceeds 50% limit)
        )

        assert is_available == False, "Margin check should fail for amount > 50%"
        self.stdout.write(f"  ✅ Margin overflow protection: PASSED")

        # Test position sizing
        size_info = calculate_position_size(
            account=self.kotak_account,
            instrument_price=Decimal('100'),
            lot_size=50,
            margin_per_lot=Decimal('50000')
        )

        assert size_info['max_lots'] == 600, "Position sizing calculation failed"
        self.stdout.write(f"  ✅ Position sizing: {size_info['max_lots']} lots max")

        # Test averaging margin validation
        is_valid, msg, margin = validate_margin_for_averaging(
            self.kotak_account,
            Decimal('10000000'),
            averaging_attempt=1
        )

        assert is_valid == True, "1st averaging margin check failed"
        assert margin == Decimal('12000000'), "1st averaging should be 20% of available"
        self.stdout.write(f"  ✅ Averaging margin (1st attempt): ₹{margin:,.0f} (20% of available)")

    def test_3_position_manager(self):
        """Test 3: Position Manager - ONE POSITION RULE"""
        self.stdout.write(self.style.WARNING('\n' + '─'*80))
        self.stdout.write(self.style.WARNING('TEST 3: Position Manager - ONE POSITION RULE'))
        self.stdout.write(self.style.WARNING('─'*80))

        # Test morning_check with no position
        result = morning_check(self.kotak_account)

        assert result['action'] == 'EVALUATE_ENTRY', "Morning check failed - should allow entry"
        assert result['allow_new_entry'] == True, "Should allow new entry when no position exists"
        assert result['position'] is None, "Position should be None"

        self.stdout.write(f"  ✅ Morning check (no position): EVALUATE_ENTRY allowed")

        # Create a test position
        expiry = date.today() + timedelta(days=7)

        success, position, msg = create_position(
            account=self.kotak_account,
            strategy_type='WEEKLY_NIFTY_STRANGLE',
            instrument='TEST_NIFTY',
            direction='NEUTRAL',
            quantity=10,
            lot_size=50,
            entry_price=Decimal('100'),
            stop_loss=Decimal('200'),  # 100% loss for strangle
            target=Decimal('30'),  # 70% profit
            expiry_date=expiry,
            margin_used=Decimal('5000000'),
            call_strike=Decimal('24500'),
            put_strike=Decimal('23500'),
            premium_collected=Decimal('100')
        )

        assert success == True, "Position creation failed"
        assert position is not None, "Position object is None"
        self.stdout.write(f"  ✅ Position created: {position.instrument} {position.direction}")

        # Test morning_check with existing position (ONE POSITION RULE)
        result = morning_check(self.kotak_account)

        assert result['action'] == 'MONITOR', "ONE POSITION RULE VIOLATED!"
        assert result['allow_new_entry'] == False, "Should NOT allow entry when position exists"
        assert result['position'] == position, "Should return existing position"

        self.stdout.write(f"  ✅ ONE POSITION RULE: New entry BLOCKED (position exists)")

        # Test trying to create another position (should fail)
        success2, position2, msg2 = create_position(
            account=self.kotak_account,
            strategy_type='WEEKLY_NIFTY_STRANGLE',
            instrument='TEST_NIFTY2',
            direction='NEUTRAL',
            quantity=5,
            lot_size=50,
            entry_price=Decimal('100'),
            stop_loss=Decimal('200'),
            target=Decimal('30'),
            expiry_date=expiry,
            margin_used=Decimal('2000000'),
            premium_collected=Decimal('50')
        )

        assert success2 == False, "ONE POSITION RULE VIOLATED - Second position created!"
        self.stdout.write(f"  ✅ ONE POSITION RULE: Second position creation BLOCKED")

        # Test position price update
        update_success = update_position_price(position, Decimal('80'))
        assert update_success == True, "Position price update failed"

        position.refresh_from_db()
        assert position.current_price == Decimal('80'), "Price not updated"
        assert position.unrealized_pnl == Decimal('10000'), "P&L calculation wrong"  # (100-80) * 10 * 50

        self.stdout.write(f"  ✅ Position update: Price ₹100 → ₹80, P&L ₹{position.unrealized_pnl:,.0f}")

        # Test position summary
        summary = get_position_summary(position)
        assert summary['instrument'] == 'TEST_NIFTY', "Summary data incorrect"
        self.stdout.write(f"  ✅ Position summary generated: {summary['total_quantity']} units")

        # Store position for next test
        self.test_position = position

    def test_4_exit_manager(self):
        """Test 4: Exit Manager - Stop-loss, Target, 50% EOD Rule"""
        self.stdout.write(self.style.WARNING('\n' + '─'*80))
        self.stdout.write(self.style.WARNING('TEST 4: Exit Manager - EXIT RULES'))
        self.stdout.write(self.style.WARNING('─'*80))

        position = self.test_position

        # Test 1: Target hit
        update_position_price(position, Decimal('25'))  # Price below target (30)
        position.refresh_from_db()

        exit_check = check_exit_conditions(position)
        assert exit_check['should_exit'] == True, "Target exit check failed"
        assert exit_check['exit_reason'] == 'TARGET', "Exit reason should be TARGET"
        assert exit_check['is_mandatory'] == True, "Target exit should be mandatory"

        self.stdout.write(f"  ✅ Target check: EXIT triggered (price ₹{position.current_price} < target ₹{position.target})")

        # Reset price
        update_position_price(position, Decimal('80'))

        # Test 2: Stop-loss hit
        update_position_price(position, Decimal('210'))  # Price above SL (200)
        position.refresh_from_db()

        exit_check = check_exit_conditions(position)
        assert exit_check['should_exit'] == True, "Stop-loss exit check failed"
        assert exit_check['exit_reason'] == 'STOP_LOSS', "Exit reason should be STOP_LOSS"
        assert exit_check['is_mandatory'] == True, "SL exit should be mandatory"

        self.stdout.write(f"  ✅ Stop-loss check: EXIT triggered (price ₹{position.current_price} > SL ₹{position.stop_loss})")

        # Test 3: Close position
        success, msg = close_position(position, Decimal('90'), 'MANUAL')
        assert success == True, "Position close failed"

        position.refresh_from_db()
        assert position.status == 'CLOSED', "Position status not updated"
        assert position.exit_price == Decimal('90'), "Exit price not saved"
        assert position.realized_pnl == Decimal('5000'), "Realized P&L incorrect"  # (100-90) * 10 * 50

        self.stdout.write(f"  ✅ Position closed: Realized P&L ₹{position.realized_pnl:,.0f}")

        # Test 4: Verify morning_check now allows new entry
        result = morning_check(self.kotak_account)
        assert result['allow_new_entry'] == True, "Should allow entry after position closed"

        self.stdout.write(f"  ✅ ONE POSITION RULE reset: New entry allowed after close")

    def test_5_expiry_selector(self):
        """Test 5: Expiry Selector - 1-day/15-day Rules"""
        self.stdout.write(self.style.WARNING('\n' + '─'*80))
        self.stdout.write(self.style.WARNING('TEST 5: Expiry Selector - EXPIRY RULES'))
        self.stdout.write(self.style.WARNING('─'*80))

        # Test options expiry selection (1-day rule)
        expiry, details = select_expiry_for_options('NIFTY', min_days=1)

        assert expiry is not None, "Expiry selection failed"
        assert details['days_remaining'] >= 1, "1-DAY RULE VIOLATED for options!"

        self.stdout.write(
            f"  ✅ Options expiry: {expiry} "
            f"({details['days_remaining']} days, {details['expiry_type']})"
        )

        if details['skipped']:
            self.stdout.write(f"     Skipped current expiry - too close to expiry")

        # Test futures expiry selection (15-day rule)
        expiry, details = select_expiry_for_futures('RELIANCE', min_days=15)

        assert expiry is not None, "Futures expiry selection failed"
        assert details['days_remaining'] >= 15, "15-DAY RULE VIOLATED for futures!"

        self.stdout.write(
            f"  ✅ Futures expiry: {expiry} "
            f"({details['days_remaining']} days, {details['expiry_type']})"
        )

        if details['skipped']:
            self.stdout.write(f"     Skipped current expiry - too close to expiry")

        # Test expiry validation for strangle strategy
        test_expiry = date.today() + timedelta(days=5)
        is_valid, msg = validate_expiry_for_strategy(test_expiry, 'WEEKLY_NIFTY_STRANGLE')

        assert is_valid == True, "Expiry validation failed for strangle"
        self.stdout.write(f"  ✅ Strangle expiry validation: {msg}")

        # Test expiry validation for futures strategy
        test_expiry = date.today() + timedelta(days=20)
        is_valid, msg = validate_expiry_for_strategy(test_expiry, 'LLM_VALIDATED_FUTURES')

        assert is_valid == True, "Expiry validation failed for futures"
        self.stdout.write(f"  ✅ Futures expiry validation: {msg}")

    def test_6_risk_manager(self):
        """Test 6: Risk Manager - Circuit Breakers"""
        self.stdout.write(self.style.WARNING('\n' + '─'*80))
        self.stdout.write(self.style.WARNING('TEST 6: Risk Manager - RISK LIMITS & CIRCUIT BREAKERS'))
        self.stdout.write(self.style.WARNING('─'*80))

        # Test risk limits check (should pass with no positions)
        risk_check = check_risk_limits(self.icici_account)

        assert risk_check['all_clear'] == True, "Risk check failed with no positions"
        assert len(risk_check['breached_limits']) == 0, "No limits should be breached"

        self.stdout.write(f"  ✅ Risk check (no positions): {risk_check['message']}")

        # Test enforce_risk_limits
        allowed, msg = enforce_risk_limits(self.icici_account)

        assert allowed == True, "Should allow trading with no risks"
        self.stdout.write(f"  ✅ Risk enforcement: Trading allowed")

        # Test risk status
        status = get_risk_status(self.icici_account)

        assert status['account_active'] == True, "Account should be active"
        assert status['trading_allowed'] == True, "Trading should be allowed"
        assert status['active_circuit_breakers'] == 0, "No circuit breakers should be active"

        self.stdout.write(f"  ✅ Risk status: {status['message']}")
        self.stdout.write(f"     Active: {status['account_active']}, "
                         f"Trading: {status['trading_allowed']}, "
                         f"Breakers: {status['active_circuit_breakers']}")

        # Note: Full circuit breaker test would require creating losing positions
        # and simulating actual losses, which we'll skip for this basic test
        self.stdout.write(f"  ℹ️  Circuit breaker activation test skipped (requires actual losses)")
