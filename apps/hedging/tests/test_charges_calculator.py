"""
Known-answer tests for charges_calculator.py. Baseline figures below were
computed via this module itself using the rate table dated in
charges_calculator.RATES_AS_OF ("2025-04") — if you deliberately update
those rates, recompute and update this baseline in the same commit so a
rate change doesn't silently pass a stale regression test.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.hedging.services.charges_calculator import (
    calculate_option_sell_charges,
    calculate_option_transaction_charges,
)

PREMIUM = Decimal('4.80')
LOTS = 90
LOT_SIZE = 400


class ChargesCalculatorTests(SimpleTestCase):
    def test_sell_side_known_answer(self):
        result = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'SELL')
        self.assertEqual(result['turnover'], Decimal('172800.00'))
        self.assertEqual(result['brokerage'], Decimal('20.00'))
        self.assertEqual(result['stt'], Decimal('172.80'))
        self.assertEqual(result['exchange_txn_charges'], Decimal('60.53'))
        self.assertEqual(result['sebi_charges'], Decimal('0.02'))
        self.assertEqual(result['stamp_duty'], Decimal('0.00'))
        self.assertEqual(result['gst'], Decimal('14.50'))
        self.assertEqual(result['total_charges'], Decimal('267.84'))
        self.assertEqual(result['net_amount'], Decimal('172532.16'))

    def test_buy_side_known_answer(self):
        result = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'BUY')
        self.assertEqual(result['stt'], Decimal('0.00'))
        self.assertEqual(result['stamp_duty'], Decimal('5.18'))
        self.assertEqual(result['total_charges'], Decimal('100.23'))
        self.assertEqual(result['net_amount'], Decimal('172900.23'))

    def test_stt_only_on_sell_side(self):
        sell = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'SELL')
        buy = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'BUY')
        self.assertGreater(sell['stt'], 0)
        self.assertEqual(buy['stt'], Decimal('0.00'))

    def test_stamp_duty_only_on_buy_side(self):
        sell = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'SELL')
        buy = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'BUY')
        self.assertEqual(sell['stamp_duty'], Decimal('0.00'))
        self.assertGreater(buy['stamp_duty'], 0)

    def test_net_amount_is_turnover_minus_charges_on_sell(self):
        result = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'SELL')
        self.assertEqual(result['net_amount'], result['turnover'] - result['total_charges'])

    def test_net_amount_is_turnover_plus_charges_on_buy(self):
        result = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'BUY')
        self.assertEqual(result['net_amount'], result['turnover'] + result['total_charges'])

    def test_invalid_transaction_type_raises(self):
        with self.assertRaises(ValueError):
            calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'HOLD')

    def test_sell_convenience_wrapper_matches_general_function(self):
        wrapped = calculate_option_sell_charges(PREMIUM, LOTS, LOT_SIZE)
        general = calculate_option_transaction_charges(PREMIUM, LOTS, LOT_SIZE, 'SELL')
        self.assertEqual(wrapped, general)
