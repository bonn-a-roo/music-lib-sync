from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import threading

import pytest
from model.sync_result import DownloadError, SyncResult

pytestmark = pytest.mark.unit


def test_serialization_and_equality_compare_data_not_locks():
    first = SyncResult(success_count=2, notes=['kept'])
    first.add_failure('song', None, 'failed')
    second = SyncResult(success_count=2, failure_count=1,
                        errors=[DownloadError('song', None, 'failed')], notes=['kept'])
    assert first == second
    assert asdict(first) == {
        'success_count': 2, 'failure_count': 1, 'skipped_count': 0,
        'errors': [{'item_name': 'song', 'item_url': None, 'error_message': 'failed'}],
        'cancelled': False, 'notes': ['kept']}
    second.add_note('different')
    assert first != second


@pytest.mark.parametrize('success,failure,skipped,expected', [
    (3, 1, 20, 75.0), (2, 0, 50, 100.0), (0, 0, 12, 0.0), (0, 3, 1, 0.0)])
def test_success_rate_excludes_skipped(success, failure, skipped, expected):
    result = SyncResult(success_count=success, failure_count=failure, skipped_count=skipped)
    assert result.success_rate == expected
    assert result.total == success + failure + skipped
    assert result.has_failures is (failure > 0)


def test_concurrent_adds_and_merges_preserve_all_data():
    destination = SyncResult()
    source = SyncResult(cancelled=True)
    barrier = threading.Barrier(8)
    def add(worker):
        barrier.wait()
        for index in range(100):
            destination.add_success()
            destination.add_skipped(2)
            piece = SyncResult(success_count=1, cancelled=True)
            piece.add_failure(f'{worker}:{index}', None, 'error')
            piece.add_note(f'note {worker}:{index}')
            destination.merge(piece)
            source.add_success()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(8)))
    destination.merge(source)
    assert destination.success_count == 2400
    assert destination.failure_count == 800
    assert destination.skipped_count == 1600
    assert len({error.item_name for error in destination.errors}) == 800
    assert len(set(destination.notes)) == 800
    assert destination.cancelled is True
    assert source.success_count == 800


def test_reciprocal_merge_does_not_deadlock():
    first, second = SyncResult(success_count=1), SyncResult(skipped_count=2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(first.merge, second)
        b = pool.submit(second.merge, first)
        a.result(timeout=5)
        b.result(timeout=5)
    # Either merge snapshots before the other update, or includes that update.
    assert (first.total, second.total) in {(3, 3), (3, 5), (4, 3)}


def test_summary_includes_bounded_errors_notes_and_cancel():
    result = SyncResult(cancelled=True)
    result.add_success()
    result.add_skipped(3)
    for index in range(12):
        result.add_failure(f'song {index}', None, f'error {index}')
        result.add_note(f'playlist {index} skipped: not owned')
    summary = result.get_summary()
    assert 'cancelled' in summary.lower()
    assert '1 succeeded' in summary and '12 failed' in summary and '3 skipped' in summary
    assert 'song 9: error 9' in summary and 'song 10: error 10' not in summary
    assert 'playlist 9 skipped: not owned' in summary
    assert 'playlist 10 skipped: not owned' not in summary
    assert '... and 2 more' in summary


def test_merge_snapshots_errors_atomically_while_source_changes():
    source = SyncResult()
    barrier = threading.Barrier(2)
    def add_failures():
        barrier.wait()
        for index in range(2000):
            source.add_failure(str(index), None, 'error')
    def merge_snapshots():
        barrier.wait()
        for _ in range(100):
            snapshot = SyncResult()
            snapshot.merge(source)
            assert snapshot.failure_count == len(snapshot.errors)
            assert [error.item_name for error in snapshot.errors] == [
                str(index) for index in range(snapshot.failure_count)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        add = pool.submit(add_failures)
        merge = pool.submit(merge_snapshots)
        add.result(timeout=5)
        merge.result(timeout=5)
    assert source.failure_count == 2000
