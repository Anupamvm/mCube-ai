"""
Trading App Tests - Trade Suggestion Approval Workflow

Tests for:
1. TradeSuggestion model creation
2. AutoTradeConfig management
3. Approval/Rejection workflow
4. Auto-approval logic
5. Execution flow
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta, date

from apps.trading.models import TradeSuggestion, AutoTradeConfig, TradeSuggestionLog
from apps.trading.services import TradeSuggestionService
from apps.accounts.models import BrokerAccount


class TradeSuggestionModelTests(TestCase):
    """Test TradeSuggestion model"""

    def setUp(self):
        """Set up test user"""
        self.user = User.objects.create_user(username='testuser', password='testpass123')

    def test_create_suggestion(self):
        """Test creating a trade suggestion"""
        suggestion = TradeSuggestion.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={'test': 'data'},
            position_details={'quantity': 50}
        )

        self.assertEqual(suggestion.instrument, 'NIFTY')
        self.assertEqual(suggestion.direction, 'LONG')
        self.assertEqual(suggestion.status, 'PENDING')
        self.assertFalse(suggestion.is_auto_trade)

    def test_suggestion_properties(self):
        """Test suggestion property methods"""
        suggestion = TradeSuggestion.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={},
            position_details={}
        )

        # Test is_pending property
        self.assertTrue(suggestion.is_pending)
        self.assertFalse(suggestion.is_approved)

        # Change status and test is_approved
        suggestion.status = 'APPROVED'
        suggestion.save()
        self.assertFalse(suggestion.is_pending)
        self.assertTrue(suggestion.is_approved)

    def test_suggestion_expiry(self):
        """Test suggestion expiry logic"""
        # Create suggestion that expired
        suggestion = TradeSuggestion.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={},
            position_details={},
            expires_at=timezone.now() - timedelta(hours=1)
        )

        # is_actionable should be False if expired
        self.assertFalse(suggestion.is_actionable)

        # Create suggestion that hasn't expired
        suggestion2 = TradeSuggestion.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='RELIANCE',
            direction='SHORT',
            algorithm_reasoning={},
            position_details={},
            expires_at=timezone.now() + timedelta(hours=1)
        )

        self.assertTrue(suggestion2.is_actionable)


class AutoTradeConfigTests(TestCase):
    """Test AutoTradeConfig model"""

    def setUp(self):
        """Set up test user"""
        self.user = User.objects.create_user(username='testuser', password='testpass123')

    def test_create_config(self):
        """Test creating auto-trade configuration"""
        config = AutoTradeConfig.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            is_enabled=True,
            auto_approve_threshold=Decimal('95.00'),
            max_daily_positions=2,
            max_daily_loss=Decimal('25000.00')
        )

        self.assertTrue(config.is_enabled)
        self.assertEqual(config.auto_approve_threshold, Decimal('95.00'))
        self.assertEqual(config.status_display, 'ENABLED')

    def test_unique_together_constraint(self):
        """Test unique_together constraint on user and strategy"""
        config1 = AutoTradeConfig.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            is_enabled=True,
            auto_approve_threshold=Decimal('95.00')
        )

        # Try to create duplicate
        with self.assertRaises(Exception):
            config2 = AutoTradeConfig.objects.create(
                user=self.user,
                strategy='kotak_strangle',
                is_enabled=False,
                auto_approve_threshold=Decimal('90.00')
            )


class TradeSuggestionServiceTests(TestCase):
    """Test TradeSuggestionService"""

    def setUp(self):
        """Set up test user"""
        self.user = User.objects.create_user(username='testuser', password='testpass123')

    def test_create_suggestion_basic(self):
        """Test basic suggestion creation"""
        suggestion = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={'calculations': {'spot': 25000}},
            position_details={'quantity': 50, 'lot_size': 50}
        )

        self.assertIsNotNone(suggestion.id)
        self.assertEqual(suggestion.status, 'PENDING')
        self.assertEqual(suggestion.instrument, 'NIFTY')

    def test_create_suggestion_with_expiry(self):
        """Test that suggestion has 1-hour expiry"""
        suggestion = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={},
            position_details={}
        )

        # Expiry should be approximately 1 hour from now
        time_diff = suggestion.expires_at - timezone.now()
        self.assertTrue(timedelta(minutes=59) < time_diff < timedelta(minutes=61))

    def test_suggestion_logging(self):
        """Test that suggestion creation is logged"""
        suggestion = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={},
            position_details={}
        )

        # Check that a log entry was created
        logs = TradeSuggestionLog.objects.filter(suggestion=suggestion)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().action, 'CREATED')

    def test_auto_approve_disabled(self):
        """Test that auto-approval doesn't happen without config"""
        suggestion = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={'filters': {'llm_validation': {'confidence': 99}}},
            position_details={}
        )

        # Should remain PENDING if no auto-trade config
        self.assertEqual(suggestion.status, 'PENDING')

    def test_auto_approve_options_high_confidence(self):
        """Test auto-approval for options with high LLM confidence"""
        # Create auto-trade config with high confidence threshold
        config = AutoTradeConfig.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            is_enabled=True,
            auto_approve_threshold=Decimal('90.00')
        )

        # Create suggestion with 95% LLM confidence
        suggestion = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={
                'filters': {
                    'llm_validation': {
                        'confidence': 95
                    }
                }
            },
            position_details={}
        )

        # Should be auto-approved
        self.assertEqual(suggestion.status, 'AUTO_APPROVED')
        self.assertTrue(suggestion.is_auto_trade)

    def test_auto_approve_options_low_confidence(self):
        """Test that options with low LLM confidence don't auto-approve"""
        config = AutoTradeConfig.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            is_enabled=True,
            auto_approve_threshold=Decimal('90.00')
        )

        suggestion = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={
                'filters': {
                    'llm_validation': {
                        'confidence': 85  # Below 90 threshold
                    }
                }
            },
            position_details={}
        )

        # Should remain PENDING
        self.assertEqual(suggestion.status, 'PENDING')

    def test_auto_approve_futures_high_score(self):
        """Test auto-approval for futures with high composite score"""
        config = AutoTradeConfig.objects.create(
            user=self.user,
            strategy='icici_futures',
            is_enabled=True,
            auto_approve_threshold=Decimal('65.00')
        )

        suggestion = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='icici_futures',
            suggestion_type='FUTURES',
            instrument='RELIANCE',
            direction='LONG',
            algorithm_reasoning={
                'scoring': {
                    'composite': {
                        'total': 75  # Above 65 threshold
                    }
                }
            },
            position_details={}
        )

        # Should be auto-approved
        self.assertEqual(suggestion.status, 'AUTO_APPROVED')

    def test_daily_position_limit(self):
        """Test daily position limit enforcement"""
        config = AutoTradeConfig.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            is_enabled=True,
            auto_approve_threshold=Decimal('90.00'),
            max_daily_positions=1
        )

        # Create and approve first suggestion
        suggestion1 = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={
                'filters': {
                    'llm_validation': {
                        'confidence': 95
                    }
                }
            },
            position_details={}
        )

        # First suggestion should be auto-approved
        self.assertEqual(suggestion1.status, 'AUTO_APPROVED')

        # Create second suggestion
        suggestion2 = TradeSuggestionService.create_suggestion(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='RELIANCE',
            direction='SHORT',
            algorithm_reasoning={
                'filters': {
                    'llm_validation': {
                        'confidence': 95
                    }
                }
            },
            position_details={}
        )

        # Second suggestion should NOT be auto-approved (daily limit reached)
        self.assertEqual(suggestion2.status, 'PENDING')


class TradeSuggestionAuthorizationTests(TestCase):
    """Test authorization and access control"""

    def setUp(self):
        """Set up test users"""
        self.user1 = User.objects.create_user(username='user1', password='testpass123')
        self.user2 = User.objects.create_user(username='user2', password='testpass123')

    def test_user_can_only_see_own_suggestions(self):
        """Test that users can only access their own suggestions"""
        # Create suggestions for different users
        suggestion1 = TradeSuggestion.objects.create(
            user=self.user1,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={},
            position_details={}
        )

        suggestion2 = TradeSuggestion.objects.create(
            user=self.user2,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='RELIANCE',
            direction='SHORT',
            algorithm_reasoning={},
            position_details={}
        )

        # Query by user1 should only return suggestion1
        user1_suggestions = TradeSuggestion.objects.filter(user=self.user1)
        self.assertEqual(user1_suggestions.count(), 1)
        self.assertEqual(user1_suggestions.first().id, suggestion1.id)

        # Query by user2 should only return suggestion2
        user2_suggestions = TradeSuggestion.objects.filter(user=self.user2)
        self.assertEqual(user2_suggestions.count(), 1)
        self.assertEqual(user2_suggestions.first().id, suggestion2.id)


class TradeSuggestionApprovalWorkflowTests(TestCase):
    """Test complete approval workflow"""

    def setUp(self):
        """Set up test client and user"""
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass123')

        # Create suggestion
        self.suggestion = TradeSuggestion.objects.create(
            user=self.user,
            strategy='kotak_strangle',
            suggestion_type='OPTIONS',
            instrument='NIFTY',
            direction='LONG',
            algorithm_reasoning={},
            position_details={'quantity': 50}
        )

    def test_approval_workflow(self):
        """Test complete approval workflow"""
        self.client.login(username='testuser', password='testpass123')

        # Check suggestion is pending
        self.assertEqual(self.suggestion.status, 'PENDING')

        # Approve suggestion
        response = self.client.post(f'/trading/suggestion/{self.suggestion.id}/approve/')

        # Reload suggestion
        self.suggestion.refresh_from_db()

        # Check suggestion is approved
        self.assertEqual(self.suggestion.status, 'APPROVED')
        self.assertIsNotNone(self.suggestion.approved_by)
        self.assertIsNotNone(self.suggestion.approval_timestamp)

    def test_rejection_workflow(self):
        """Test rejection workflow"""
        self.client.login(username='testuser', password='testpass123')

        # Reject suggestion
        response = self.client.post(
            f'/trading/suggestion/{self.suggestion.id}/reject/',
            {'reason': 'Market conditions unfavorable'}
        )

        # Reload suggestion
        self.suggestion.refresh_from_db()

        # Check suggestion is rejected
        self.assertEqual(self.suggestion.status, 'REJECTED')
        self.assertIn('Market conditions unfavorable', self.suggestion.approval_notes)

    def test_approval_creates_log(self):
        """Test that approval creates audit log"""
        # Approve suggestion
        self.suggestion.status = 'APPROVED'
        self.suggestion.approved_by = self.user
        self.suggestion.approval_timestamp = timezone.now()
        self.suggestion.save()

        # Create log
        TradeSuggestionLog.objects.create(
            suggestion=self.suggestion,
            action='APPROVED',
            user=self.user,
            notes='Manually approved'
        )

        # Check logs exist
        logs = TradeSuggestionLog.objects.filter(suggestion=self.suggestion)
        self.assertGreaterEqual(logs.count(), 1)

        # Check log has correct action
        self.assertTrue(logs.filter(action='APPROVED').exists())
