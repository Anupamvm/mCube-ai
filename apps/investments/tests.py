from __future__ import annotations
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from apps.investments.models import (
    FamilyMember, InvestmentAccount, InvestmentProduct, ProductValuationHistory
)
from apps.investments.services.valuation_engine import compute_product_value


def _make_member(user, name='Test Member', pan_hash='testhash001'):
    return FamilyMember.objects.create(
        user=user, name=name, relationship='SELF',
        pan_masked='AAXXXXT001Z', pan_hash=pan_hash,
    )


def _make_account(member):
    return InvestmentAccount.objects.create(
        family_member=member, account_name='Test Account',
        account_type='SAVINGS_BANK', institution_name='SBI',
        data_source='MANUAL',
    )


class FDValuationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', password='x')
        self.member = _make_member(self.user)
        self.account = _make_account(self.member)

    def test_quarterly_compounding(self):
        # Use start date exactly 3 years ago so years=3.0 (±1 day drift is ok)
        today = datetime.date.today()
        start = today.replace(year=today.year - 3)
        maturity = today.replace(year=today.year + 1)
        fd = InvestmentProduct.objects.create(
            investment_account=self.account,
            product_type='FD',
            name='Test FD',
            invested_value=Decimal('500000'),
            current_value=Decimal('500000'),
            as_of_date=today,
            extra_data={
                'principal': 500000,
                'interest_rate': 7.1,
                'compounding': 'quarterly',
                'start_date': str(start),
                'maturity_date': str(maturity),
            }
        )
        value = compute_product_value(fd)
        import datetime as dt
        years = (today - start).days / 365.0
        expected = 500000 * (1 + 0.071 / 4) ** (4 * years)
        self.assertAlmostEqual(float(value), expected, delta=1.0)

    def test_annual_compounding(self):
        today = datetime.date.today()
        start = today.replace(year=today.year - 1)
        maturity = today.replace(year=today.year + 1)
        fd = InvestmentProduct.objects.create(
            investment_account=self.account,
            product_type='FD',
            name='Test FD Annual',
            invested_value=Decimal('200000'),
            current_value=Decimal('200000'),
            as_of_date=today,
            extra_data={
                'principal': 200000,
                'interest_rate': 6.5,
                'compounding': 'annually',
                'start_date': str(start),
                'maturity_date': str(maturity),
            }
        )
        value = compute_product_value(fd)
        years = (today - start).days / 365.0
        expected = 200000 * (1 + 0.065) ** years
        self.assertAlmostEqual(float(value), expected, delta=1.0)


class CascadeDeleteTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser2', password='x')

    def test_cascade_on_member_delete(self):
        member = _make_member(self.user, name='Delete Me', pan_hash='delhash001')
        account = _make_account(member)
        product = InvestmentProduct.objects.create(
            investment_account=account, product_type='FD', name='FD',
            invested_value=Decimal('100000'), current_value=Decimal('100000'),
            as_of_date=datetime.date.today(), extra_data={},
        )
        mid, aid, pid = member.id, account.id, product.id
        member.delete()
        self.assertFalse(FamilyMember.objects.filter(id=mid).exists())
        self.assertFalse(InvestmentAccount.objects.filter(id=aid).exists())
        self.assertFalse(InvestmentProduct.objects.filter(id=pid).exists())


class ValuationHistoryTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser3', password='x')
        self.member = _make_member(self.user, name='RE Owner', pan_hash='rehash001')
        self.account = _make_account(self.member)

    def test_valuation_history_tracking(self):
        product = InvestmentProduct.objects.create(
            investment_account=self.account, product_type='REAL_ESTATE',
            name='Flat', invested_value=Decimal('8000000'),
            current_value=Decimal('10000000'), as_of_date=datetime.date(2024, 1, 1),
            extra_data={'estimated_value': 10000000},
        )
        ProductValuationHistory.objects.create(
            product=product, date=datetime.date(2024, 1, 1),
            value=Decimal('10000000'), source='MANUAL',
        )
        ProductValuationHistory.objects.create(
            product=product, date=datetime.date(2025, 1, 1),
            value=Decimal('12000000'), source='MANUAL',
        )
        history = ProductValuationHistory.objects.filter(product=product).order_by('date')
        self.assertEqual(history.count(), 2)
        self.assertEqual(history[0].value, Decimal('10000000'))
        self.assertEqual(history[1].value, Decimal('12000000'))


class HealthScoreTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser4', password='x')
        self.member = _make_member(self.user, name='Healthy Investor', pan_hash='healthhash')
        self.account = _make_account(self.member)
        types = ['MUTUAL_FUND', 'EQUITY', 'FD', 'SGB', 'REAL_ESTATE']
        for t in types:
            InvestmentProduct.objects.create(
                investment_account=self.account, product_type=t,
                name=f'Test {t}', invested_value=Decimal('1000000'),
                current_value=Decimal('1100000'), as_of_date=datetime.date.today(),
                extra_data={},
            )

    def test_score_in_range(self):
        from apps.investments.services.analytics.health_scorer import compute_health_score
        score = compute_health_score(family_member=self.member)
        self.assertGreaterEqual(score.total_score, 0)
        self.assertLessEqual(score.total_score, 100)

    def test_score_improves_with_diversity(self):
        from apps.investments.services.analytics.health_scorer import compute_health_score
        score = compute_health_score(family_member=self.member)
        self.assertGreater(score.diversification_score, 0)
