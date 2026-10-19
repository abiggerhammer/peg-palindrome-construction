from itertools import product

from predictability_scheduler import (
    schedule_trace,
    schedule_trace_via_table,
    scheduler_control_table,
)


def test_scheduler_table_is_finite() -> None:
    table = scheduler_control_table(3)
    # FAST has only equal-head entries; SLOW has both equality possibilities.
    assert 0 < len(table) <= 2 * 3 * 2 * 2 * 2


def test_table_execution_matches_reference_schedule_exhaustively() -> None:
    for n in range(1, 5):
        for work in product(range(1, 7), repeat=n):
            # Restrict to traces satisfying the speculative-zero obligation:
            # all events emitted speculatively must correspond to source zeroes.
            for outputs in product((0, 1), repeat=n):
                try:
                    ref = schedule_trace(work, outputs, c=2)
                    tab = schedule_trace_via_table(work, outputs, c=2)
                except AssertionError:
                    continue
                assert tab == ref
