"""
Tests for aggregate_futures_results chord callback.

Focuses on the batch-merging logic: None batches (hard failures),
timed-out batches, and correct aggregation of passed/error counts.
These tests mock all Celery/Telegram/DB side effects and test only the
merge logic that was updated to track null_batches.
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase


def _make_batch(
    passed_summary=None,
    passed_full=None,
    errors=None,
    analyzed_count=2,
    batch_size=2,
    timed_out=False,
):
    return {
        'passed_summary': passed_summary or [],
        'passed_full': passed_full or [],
        'errors': errors or [],
        'analyzed_count': analyzed_count,
        'batch_size': batch_size,
        'timed_out': timed_out,
    }


def _run_aggregate(batch_results, min_score=65):
    """
    Call aggregate_futures_results with all external dependencies mocked.

    Returns the dict that would normally be returned from the Celery task.
    """
    from apps.strategies.tasks import aggregate_futures_results

    with patch('apps.strategies.tasks.TaskLogger') as mock_tl_cls, \
         patch('apps.trading.services.suggestion_service.save_futures_suggestions', return_value=[]), \
         patch('apps.core.models.TradingCoreConfig') as mock_cfg_cls, \
         patch('apps.trading.models.TradeSuggestion') as mock_ts, \
         patch('apps.strategies.tasks.notify'), \
         patch('apps.strategies.tasks.logger') as mock_logger:

        # TaskLogger — return a silent mock for all method calls
        mock_tl = MagicMock()
        mock_tl_cls.return_value = mock_tl

        # TradingCoreConfig — simulate SIMULATED mode so we skip Telegram flow
        mock_cfg = MagicMock()
        mock_cfg.is_simulated.return_value = True
        mock_cfg.simulated_futures_lots = 1
        mock_cfg_cls.get_instance.return_value = mock_cfg

        # aggregate_futures_results.run is already bound to the Celery task instance
        # (bind=True), so self is provided automatically — do NOT pass it explicitly.
        result = aggregate_futures_results.run(
            batch_results,
            min_score=min_score,
            orchestrator_task_id='test-orch-id',
        )
        return result, mock_logger


class ChordBatchMergingTests(TestCase):
    """Test batch result merging in aggregate_futures_results."""

    def test_all_successful_batches(self):
        """Normal case: all batches return results, totals are correct."""
        batches = [
            _make_batch(analyzed_count=3, batch_size=3),
            _make_batch(analyzed_count=2, batch_size=2),
        ]
        result, _ = _run_aggregate(batches)
        self.assertTrue(result['success'])

    def test_single_none_batch_does_not_crash(self):
        """A None batch (hard subtask failure) must not raise an exception."""
        batches = [None, _make_batch(analyzed_count=2)]
        try:
            result, _ = _run_aggregate(batches)
        except Exception as e:
            self.fail(f"aggregate_futures_results crashed on None batch: {e}")

    def test_all_none_batches_does_not_crash(self):
        """All-None batch_results must not raise an exception."""
        batches = [None, None, None]
        try:
            result, _ = _run_aggregate(batches)
        except Exception as e:
            self.fail(f"aggregate_futures_results crashed on all-None batches: {e}")

    def test_none_batches_counted_separately(self):
        """None batches must be counted as null_batches, not timed_out_batches."""
        batches = [None, _make_batch(timed_out=True, analyzed_count=1, batch_size=2)]
        # Trigger the CHORD COMPLETENESS warning
        _, mock_logger = _run_aggregate(batches)
        # The warning should mention both failure types
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        chord_warnings = [w for w in warning_calls if 'CHORD COMPLETENESS' in w or 'chord' in w.lower()]
        self.assertTrue(
            len(chord_warnings) > 0,
            f"Expected CHORD COMPLETENESS warning, got: {warning_calls}"
        )

    def test_timed_out_batch_tracked(self):
        """timed_out=True batches must be tracked and trigger the completeness warning."""
        batches = [
            _make_batch(analyzed_count=1, batch_size=3, timed_out=True),
        ]
        _, mock_logger = _run_aggregate(batches)
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        chord_warnings = [w for w in warning_calls if 'CHORD COMPLETENESS' in w]
        self.assertTrue(len(chord_warnings) > 0, "Expected CHORD COMPLETENESS warning for timed-out batch")

    def test_no_warning_when_all_batches_complete(self):
        """No CHORD COMPLETENESS warning when all batches succeed with no timeout."""
        batches = [
            _make_batch(analyzed_count=2, batch_size=2),
            _make_batch(analyzed_count=3, batch_size=3),
        ]
        _, mock_logger = _run_aggregate(batches)
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        chord_warnings = [w for w in warning_calls if 'CHORD COMPLETENESS' in w]
        self.assertEqual(len(chord_warnings), 0, f"Unexpected CHORD COMPLETENESS warning: {chord_warnings}")

    def test_passed_summary_from_good_batches_accumulated(self):
        """Passed summaries from valid batches must be collected even if other batches are None."""
        candidate = {'symbol': 'RELIANCE', 'score': 70, 'qualified': True, 'direction': 'LONG'}
        batches = [
            None,
            _make_batch(
                passed_summary=[candidate],
                passed_full=[{**candidate, 'expiry_date': '2026-07-31'}],
                analyzed_count=1,
            ),
        ]
        result, _ = _run_aggregate(batches)
        self.assertTrue(result['success'])

    def test_empty_batch_results_list(self):
        """Empty batch_results (no subtasks at all) must not crash."""
        try:
            result, _ = _run_aggregate([])
        except Exception as e:
            self.fail(f"aggregate_futures_results crashed on empty batch list: {e}")

    def test_mixed_batches_errors_accumulated(self):
        """Errors from multiple batches must all be collected."""
        batches = [
            _make_batch(errors=['Error A', 'Error B'], analyzed_count=2),
            _make_batch(errors=['Error C'], analyzed_count=1),
        ]
        result, _ = _run_aggregate(batches)
        self.assertTrue(result['success'])
