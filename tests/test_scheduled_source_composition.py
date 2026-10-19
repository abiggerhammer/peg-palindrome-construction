from itertools import product

from predictability_scheduler import schedule_trace_via_compact
from sparse_registered_linker import SparseAction, SparseRow
from scheduled_source_composition import (
    BOUNDED_DELAY_TRANSITIONS,
    BUFFER_CALL_ROWS,
    BUFFER_SERVICE_ROWS,
    CLOCK_ROWS,
    LAGGED_SOURCE_SELECT_ROWS,
    SCHEDULED_STATES,
    SCHEDULED_TOTAL_ROWS,
    SCHEDULED_WORK_TAPES,
    SOURCE_ACTIVE_START,
    SOURCE_DONE_0,
    SOURCE_STATE_BITS,
    SOURCE_Q_START,
    SOURCE_STEP_COMPOSITION_BOUND,
    SMALL_CONTROLLER_ROWS,
    changed_source_state_bits,
    certificate_dict,
    iter_buffer_call_rows,
    iter_buffer_service_rows,
    iter_clock_rows,
    iter_equal_completion_rows,
    iter_lagged_source_select_rows,
    lift_source_row,
    schedule_trace_via_composition,
    source_state_bits,
)


def test_public_composition_constants():
    cert = certificate_dict()
    assert SOURCE_STATE_BITS == 21
    assert SOURCE_STEP_COMPOSITION_BOUND == 117
    assert BOUNDED_DELAY_TRANSITIONS == 416_945_810_716
    assert SCHEDULED_WORK_TAPES == 295
    assert SCHEDULED_STATES == 1_653_051
    assert SCHEDULED_TOTAL_ROWS == 8_305_403
    assert cert["source_row_product_factor"] == 1
    assert cert["transformed_source_rows"] == 6_502_172


def test_source_state_bit_updates_are_exact():
    samples = (0, 1, 110, 111, 262143, 461838, 99227, 1_562_425)
    for old in samples:
        for new in samples:
            bits = list(source_state_bits(old))
            for tape, value in changed_source_state_bits(old, new):
                bits[tape - SOURCE_Q_START] = value
            assert tuple(bits) == source_state_bits(new)


def test_literal_non_source_row_family_counts():
    assert sum(1 for _ in iter_buffer_service_rows()) == BUFFER_SERVICE_ROWS
    assert sum(1 for _ in iter_buffer_call_rows()) == BUFFER_CALL_ROWS
    assert sum(1 for _ in iter_lagged_source_select_rows()) == LAGGED_SOURCE_SELECT_ROWS
    assert sum(1 for _ in iter_equal_completion_rows()) == 2
    assert sum(1 for _ in iter_clock_rows()) == CLOCK_ROWS
    assert BUFFER_CALL_ROWS + LAGGED_SOURCE_SELECT_ROWS + 1 + 2 + CLOCK_ROWS == SMALL_CONTROLLER_ROWS


def test_source_row_lift_is_one_for_one_and_preserves_source_action():
    original = SparseRow(
        state=42,
        reads=((0, "x"), (17, frozenset(("a", "b")))),
        action=SparseAction(73, ((2, "z"),), ((3, 1),)),
    )
    lifted = lift_source_row(original)
    assert lifted.state == SOURCE_ACTIVE_START + 42
    assert lifted.reads == original.reads
    assert lifted.action.moves == original.action.moves
    assert (2, "z") in lifted.action.writes

    done = SparseRow(73, (), SparseAction(SOURCE_DONE_0))
    lifted_done = lift_source_row(done)
    assert lifted_done.action.next_state != lifted.action.next_state
    assert any(value == 0 for _, value in lifted_done.action.writes)


def test_factored_composition_matches_compact_scheduler_exhaustively():
    for n in range(1, 5):
        for work in product(range(1, 8), repeat=n):
            for outputs in product((0, 1), repeat=n):
                try:
                    composed = schedule_trace_via_composition(work, outputs, c=2)
                    reference = tuple(schedule_trace_via_compact(work, outputs, c=2))
                except AssertionError:
                    # Finite traces ending with the physical head ahead do not
                    # include enough trailing source positions to observe catch-up.
                    continue
                assert composed.events == reference
                assert all(
                    interval.ordinary_transitions <= BOUNDED_DELAY_TRANSITIONS
                    for interval in composed.intervals
                )


def test_slow_trace_uses_fifo_and_stays_within_small_instance_bound():
    work = [9, 1, 1, 1, 1]
    outputs = [0, 0, 1, 0, 1]
    trace = schedule_trace_via_composition(work, outputs, c=2)
    assert [e.output for e in trace.events] == outputs
    assert any(i.speculative for i in trace.intervals)
    assert any(i.lagged_completions for i in trace.intervals)
    local_bound = 214 + 4 * 117
    assert max(i.ordinary_transitions for i in trace.intervals) <= local_bound


def test_actual_dispatcher_and_constant_source_rows_lift_one_for_one():
    from build_outer_service_fabric import build_fabric
    from sg_outer_dispatcher_table import build_dispatcher_rows
    from sg_outer_constant_cases import build_constant_case_rows
    from scheduled_source_composition import COMPLETE, CLOCK

    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constant = build_constant_case_rows(fabric)
    lifted_dispatcher = tuple(lift_source_row(row) for row in dispatcher.rows)
    lifted_constant = tuple(lift_source_row(row) for row in constant.rows)
    assert len(lifted_dispatcher) == len(dispatcher.rows) == 35_541
    assert len(lifted_constant) == len(constant.rows) == 7_615
    assert all(row.action.next_state == CLOCK for row in lifted_dispatcher)
    assert sum(row.action.next_state == COMPLETE for row in lifted_constant) == 3
