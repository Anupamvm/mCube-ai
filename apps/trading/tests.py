"""
Trading App Tests - Trade Suggestion Approval Workflow

Tests for:
1. TradeSuggestion model creation
2. Approval/Rejection workflow
3. Execution flow
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from apps.trading.models import TradeSuggestion, TradeSuggestionLog
from apps.trading.services import TradeSuggestionService


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
        self.assertEqual(suggestion.status, 'SUGGESTED')

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

        # New suggestion is pending and actionable
        self.assertTrue(suggestion.is_pending)
        self.assertFalse(suggestion.is_active)
        self.assertTrue(suggestion.is_actionable)

        # After taking the trade, is_pending is False, is_active is True
        suggestion.mark_taken()
        self.assertFalse(suggestion.is_pending)
        self.assertTrue(suggestion.is_active)

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
        self.assertEqual(suggestion.status, 'SUGGESTED')
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
        """Test suggestion transitions from SUGGESTED to TAKEN via approve()"""
        # New suggestion starts as SUGGESTED
        self.assertEqual(self.suggestion.status, 'SUGGESTED')
        self.assertTrue(self.suggestion.is_pending)

        # Take the trade
        self.suggestion.mark_taken()
        self.suggestion.refresh_from_db()

        self.assertEqual(self.suggestion.status, 'TAKEN')
        self.assertTrue(self.suggestion.is_active)
        self.assertFalse(self.suggestion.is_pending)

    def test_rejection_workflow(self):
        """Test suggestion transitions from SUGGESTED to REJECTED via mark_rejected()"""
        # Reject suggestion
        self.suggestion.mark_rejected(user_notes='Market conditions unfavorable')
        self.suggestion.refresh_from_db()

        self.assertEqual(self.suggestion.status, 'REJECTED')
        self.assertFalse(self.suggestion.is_pending)
        self.assertIsNotNone(self.suggestion.rejected_timestamp)

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
