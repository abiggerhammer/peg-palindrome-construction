"""Factored ordinary composition of the corrected SG source with Galil's scheduler.

The certified SG source is already a deterministic one-head-per-tape ordinary
machine with 225 work tapes.  This module composes it with:

* one additional audited strict append/read history zipper, whose writer is
  the physical input head and whose reader is the simulated source head;
* a unary lag tape storing ``h2-h1``;
* a 21-bit fixed source-state register;
* the exact 32-bit Galil countdown;
* one pending-output bit and one mode bit.

No Cartesian source-state/countdown product is formed.  Every source row is
lifted once, every source state has one exact binary dispatch row, and the
countdown is shared.  The resulting object is a finite ordinary bounded-delay
input/output transducer.  The Hartmanis--Stearns fixed speedup is recorded
separately in :mod:`constant_speedup`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum, auto
from pathlib import Path
import json
from typing import Hashable, Iterable, Iterator, Sequence

import history_zipper_ordinary_tm as hz
from case14_predictability_bounds import HISTORY_APPEND, HISTORY_RIGHT
from flat_tm import Shift
from predictability_scheduler import (
    Mode,
    SchedulerEvent,
    fixed_countdown_rows,
    schedule_trace_via_compact,
)
from scheduler_parameters import GALIL_PREDICTABILITY_C, GALIL_SCHEDULER_PERIOD
from sparse_registered_linker import ReadAtom, SparseAction, SparseRow, SymbolicAdapter


# Certified source inventory.
SOURCE_STATES = 1_562_426
SOURCE_ROWS = 6_502_172
SOURCE_TAPES = 225
SOURCE_ENTRY_0 = 0
SOURCE_ENTRY_1 = 1
SOURCE_DONE_0 = 110
SOURCE_DONE_1 = 111
SOURCE_STATE_BITS = (SOURCE_STATES - 1).bit_length()

# Added ordinary work-tape layout.  The read-only input tape and one-way output
# tape are external and are not counted here.
BUFFER_DATA_START = SOURCE_TAPES
BUFFER_DATA_TAPES = 12
BUFFER_REGISTER_TAPE = BUFFER_DATA_START + BUFFER_DATA_TAPES
BUFFER_CONTINUATION_TAPE = BUFFER_REGISTER_TAPE + 1
SOURCE_Q_START = BUFFER_CONTINUATION_TAPE + 1
CLOCK_START = SOURCE_Q_START + SOURCE_STATE_BITS
CLOCK_WIDTH = GALIL_SCHEDULER_PERIOD.bit_length()
LAG_TAPE = CLOCK_START + CLOCK_WIDTH
PENDING_OUTPUT_TAPE = LAG_TAPE + 1
MODE_TAPE = PENDING_OUTPUT_TAPE + 1
SCHEDULED_WORK_TAPES = MODE_TAPE + 1

BLANK = "_"
LAG_BOTTOM = "#"
LAG_ONE = "1"
MODE_FAST = "F"
MODE_SLOW = "S"

# Small scheduler control.  Source and history-worker controls occupy disjoint
# state ranges below.
AWAIT_FAST = 0
AWAIT_SLOW = 1
DIRECT_AFTER_APPEND = 2
BUFFERED_AFTER_APPEND = 3
LAGGED_AFTER_RIGHT = 4
SOURCE_DISPATCH = 5
CLOCK = 6
COMPLETE = 7
ERROR = 8
CONTROLLER_STATE_RESERVE = 16

SOURCE_ACTIVE_START = CONTROLLER_STATE_RESERVE
BUFFER_LOAD_STATE = SOURCE_ACTIVE_START + SOURCE_STATES
BUFFER_ERROR_STATE = BUFFER_LOAD_STATE + 1
BUFFER_ACTIVE_START = BUFFER_ERROR_STATE + 1

_BUFFER_ADAPTER = SymbolicAdapter(
    "SCHED_INPUT",
    hz.machine(),
    frozenset(hz.machine().halting_states - {hz.ERROR_STATE}),
    frozenset((hz.ERROR_STATE,)),
)
BUFFER_STATES = _BUFFER_ADAPTER.state_count
BUFFER_ROWS = _BUFFER_ADAPTER.row_count
BUFFER_CONTINUE_STATE = BUFFER_ACTIVE_START + BUFFER_STATES
SCHEDULED_STATES = BUFFER_CONTINUE_STATE + 1
BUFFER_READY_IDS = tuple(sorted(_BUFFER_ADAPTER.ready_state_ids))
BUFFER_READY_BY_CURRENT = {
    symbol: tuple(
        qid
        for qid in BUFFER_READY_IDS
        if getattr(_BUFFER_ADAPTER.id_to_state[qid], "current", None) == symbol
    )
    for symbol in ("#", "_", "0", "1")
}

# Registered caller-to-continuation bounds proved earlier.  The scheduler adds
# lag movement and source-register writes to existing caller/continuation rows,
# so these do not lengthen the worker call itself.
DIRECT_READ_SETUP_BOUND = HISTORY_APPEND + HISTORY_RIGHT  # 214
BUFFERED_READ_SETUP_BOUND = HISTORY_APPEND + 1  # append, then write lag unit
NONCOMPLETING_SOURCE_STEP_BOUND = 3  # dispatch, source row, clock row
EQUAL_COMPLETING_SOURCE_STEP_BOUND = 3  # dispatch, source row, completion row
# The COMPLETE caller row both decrements lag and starts RIGHT, so HISTORY_RIGHT
# already includes it.
LAGGED_COMPLETING_SOURCE_STEP_BOUND = 2 + HISTORY_RIGHT + 1 + 1
SOURCE_STEP_COMPOSITION_BOUND = max(
    NONCOMPLETING_SOURCE_STEP_BOUND,
    EQUAL_COMPLETING_SOURCE_STEP_BOUND,
    LAGGED_COMPLETING_SOURCE_STEP_BOUND,
)

# At most L counted source steps occur after one physical read.  The setup is at
# most the direct APPEND+RIGHT route.  Output emission and input-head advance are
# included in the equal-completion or clock-tick row.
BOUNDED_DELAY_TRANSITIONS = (
    DIRECT_READ_SETUP_BOUND
    + GALIL_SCHEDULER_PERIOD * SOURCE_STEP_COMPOSITION_BOUND
)

# Exact row-family inventory.  Four registered continuations are used:
# DIRECT_AFTER_APPEND, SOURCE_DISPATCH, BUFFERED_AFTER_APPEND,
# LAGGED_AFTER_RIGHT.
BUFFER_CONTINUATIONS = (
    DIRECT_AFTER_APPEND,
    SOURCE_DISPATCH,
    BUFFERED_AFTER_APPEND,
    LAGGED_AFTER_RIGHT,
)
BUFFER_SERVICE_ROWS = BUFFER_STATES + BUFFER_ROWS + len(BUFFER_CONTINUATIONS)
BUFFER_CALL_SITES = 6  # four APPEND sites and two RIGHT sites
BUFFER_CALL_ROWS = BUFFER_CALL_SITES * len(BUFFER_READY_IDS)
LAGGED_SOURCE_SELECT_ROWS = len(BUFFER_READY_BY_CURRENT["0"]) + len(
    BUFFER_READY_BY_CURRENT["1"]
)
CLOCK_ROWS = len(fixed_countdown_rows(GALIL_SCHEDULER_PERIOD)) + 1  # split tick by mode
SOURCE_DISPATCH_ROWS = SOURCE_STATES - 2
SMALL_CONTROLLER_ROWS = (
    BUFFER_CALL_ROWS
    + LAGGED_SOURCE_SELECT_ROWS
    + 1  # BUFFERED_AFTER_APPEND
    + 2  # COMPLETE with pending output 0/1 when lag is zero
    + CLOCK_ROWS
)
SCHEDULED_TOTAL_ROWS = (
    SOURCE_ROWS
    + SOURCE_DISPATCH_ROWS
    + BUFFER_SERVICE_ROWS
    + SMALL_CONTROLLER_ROWS
)


@dataclass(frozen=True)
class ScheduledAction:
    next_state: int
    writes: tuple[tuple[int, Hashable], ...] = ()
    moves: tuple[tuple[int, int], ...] = ()
    input_move: int = 0
    emit: int | None = None


@dataclass(frozen=True)
class ScheduledRow:
    """One sparse row of the bounded-delay ordinary transducer.

    ``input_symbol=None`` means that the read-only input symbol is ignored.
    Work-tape reads/writes/moves have the same sparse semantics as
    :class:`sparse_registered_linker.SparseRow`.
    """

    state: int
    input_symbol: str | None
    reads: tuple[tuple[int, ReadAtom], ...]
    action: ScheduledAction


class ReadKind(Enum):
    DIRECT = auto()
    BUFFERED = auto()


@dataclass(frozen=True)
class CompositionInterval:
    input_index: int
    read_kind: ReadKind
    source_steps: int
    lagged_completions: int
    ordinary_transitions: int
    output: int
    speculative: bool
    ending_mode: Mode


@dataclass(frozen=True)
class CompositionTrace:
    events: tuple[SchedulerEvent, ...]
    intervals: tuple[CompositionInterval, ...]


@dataclass(frozen=True)
class CompositionCertificate:
    source_states: int
    source_rows: int
    source_tapes: int
    source_state_bits: int
    scheduler_predictability_c: int
    source_step_period: int
    countdown_width_bits: int
    compact_countdown_rows: int
    scheduled_work_tapes: int
    scheduled_states: int
    input_history_states: int
    input_history_rows: int
    input_history_ready_states: int
    input_history_append_bound: int
    input_history_right_bound: int
    direct_read_setup_bound: int
    buffered_read_setup_bound: int
    noncompleting_source_step_bound: int
    equal_completing_source_step_bound: int
    lagged_completing_source_step_bound: int
    uniform_source_step_composition_bound: int
    bounded_delay_transitions: int
    transformed_source_rows: int
    source_dispatch_rows: int
    buffer_service_rows: int
    buffer_call_rows: int
    lagged_source_select_rows: int
    small_controller_rows: int
    scheduled_total_rows: int
    source_row_product_factor: int


def source_state_bits(state: int) -> tuple[int, ...]:
    if not isinstance(state, int) or not 0 <= state < SOURCE_STATES:
        raise ValueError(state)
    return tuple((state >> i) & 1 for i in range(SOURCE_STATE_BITS))


def full_source_state_writes(state: int) -> tuple[tuple[int, int], ...]:
    return tuple((SOURCE_Q_START + i, bit) for i, bit in enumerate(source_state_bits(state)))


def changed_source_state_bits(old: int, new: int) -> tuple[tuple[int, int], ...]:
    """Sparse global-tape writes changing source-state register old -> new."""
    before = source_state_bits(old)
    after = source_state_bits(new)
    return tuple(
        (SOURCE_Q_START + i, bit)
        for i, (a, bit) in enumerate(zip(before, after))
        if a != bit
    )


def source_dispatch_row(state: int) -> ScheduledRow:
    if state in (SOURCE_DONE_0, SOURCE_DONE_1):
        raise ValueError("done states are handled by COMPLETE, not redispatched")
    reads = tuple((SOURCE_Q_START + i, bit) for i, bit in enumerate(source_state_bits(state)))
    return ScheduledRow(
        SOURCE_DISPATCH,
        None,
        reads,
        ScheduledAction(SOURCE_ACTIVE_START + state),
    )


def iter_source_dispatch_rows() -> Iterator[ScheduledRow]:
    for state in range(SOURCE_STATES):
        if state not in (SOURCE_DONE_0, SOURCE_DONE_1):
            yield source_dispatch_row(state)


def lift_source_row(row: SparseRow) -> ScheduledRow:
    """Lift one certified SG source row without multiplying it by clock states."""
    if not 0 <= row.state < SOURCE_STATES:
        raise ValueError(row.state)
    nxt = row.action.next_state
    if not 0 <= nxt < SOURCE_STATES:
        raise ValueError(nxt)
    writes = row.action.writes + changed_source_state_bits(row.state, nxt)
    target = CLOCK
    if nxt in (SOURCE_DONE_0, SOURCE_DONE_1):
        writes += ((PENDING_OUTPUT_TAPE, nxt - SOURCE_DONE_0),)
        target = COMPLETE
    return ScheduledRow(
        SOURCE_ACTIVE_START + row.state,
        None,
        row.reads,
        ScheduledAction(target, writes, row.action.moves),
    )


def _buffer_qsymbol(qid: int) -> str:
    return f"@SCHED_INPUT:q{qid}"


def _continuation_symbol(state: int) -> str:
    return f"@CONT:q{state}"


def _buffer_command_id(ready_id: int, command: str) -> int:
    ready = _BUFFER_ADAPTER.id_to_state[ready_id]
    return _BUFFER_ADAPTER.state_to_id[hz.as_command_state(ready, command)]


def _call_row(
    *,
    caller: int,
    ready_id: int,
    command: str,
    continuation: int,
    input_symbol: str | None = None,
    extra_reads: tuple[tuple[int, ReadAtom], ...] = (),
    extra_writes: tuple[tuple[int, Hashable], ...] = (),
    extra_moves: tuple[tuple[int, int], ...] = (),
) -> ScheduledRow:
    return ScheduledRow(
        caller,
        input_symbol,
        ((BUFFER_REGISTER_TAPE, _buffer_qsymbol(ready_id)),) + extra_reads,
        ScheduledAction(
            BUFFER_LOAD_STATE,
            (
                (BUFFER_REGISTER_TAPE, _buffer_qsymbol(_buffer_command_id(ready_id, command))),
                (BUFFER_CONTINUATION_TAPE, _continuation_symbol(continuation)),
            )
            + extra_writes,
            extra_moves,
        ),
    )


def iter_buffer_service_rows() -> Iterator[ScheduledRow]:
    # LOAD dispatch.
    for qid in range(BUFFER_STATES):
        if qid in _BUFFER_ADAPTER.error_state_ids:
            nxt = BUFFER_ERROR_STATE
        elif qid in _BUFFER_ADAPTER.ready_state_ids:
            nxt = BUFFER_CONTINUE_STATE
        else:
            nxt = BUFFER_ACTIVE_START + qid
        yield ScheduledRow(
            BUFFER_LOAD_STATE,
            None,
            ((BUFFER_REGISTER_TAPE, _buffer_qsymbol(qid)),),
            ScheduledAction(nxt),
        )

    # One lifted row per local history-worker row.
    for row in _BUFFER_ADAPTER.rows():
        reads = tuple((BUFFER_DATA_START + tape, atom) for tape, atom in row.reads)
        reads += ((BUFFER_REGISTER_TAPE, _buffer_qsymbol(row.state_id)),)
        writes = tuple((BUFFER_DATA_START + tape, value) for tape, value in row.writes)
        writes += ((BUFFER_REGISTER_TAPE, _buffer_qsymbol(row.next_state_id)),)
        moves = tuple((BUFFER_DATA_START + tape, move) for tape, move in row.moves)
        yield ScheduledRow(
            BUFFER_ACTIVE_START + row.state_id,
            None,
            reads,
            ScheduledAction(BUFFER_LOAD_STATE, writes, moves),
        )

    for continuation in BUFFER_CONTINUATIONS:
        yield ScheduledRow(
            BUFFER_CONTINUE_STATE,
            None,
            ((BUFFER_CONTINUATION_TAPE, _continuation_symbol(continuation)),),
            ScheduledAction(continuation),
        )


def iter_buffer_call_rows() -> Iterator[ScheduledRow]:
    # Read one physical input symbol in FAST mode: set the source entry state,
    # append the symbol, and then move the simulated reader right.
    for bit, command, entry in (("0", "APPEND0", SOURCE_ENTRY_0), ("1", "APPEND1", SOURCE_ENTRY_1)):
        for ready in BUFFER_READY_IDS:
            yield _call_row(
                caller=AWAIT_FAST,
                ready_id=ready,
                command=command,
                continuation=DIRECT_AFTER_APPEND,
                input_symbol=bit,
                extra_reads=((MODE_TAPE, MODE_FAST), (LAG_TAPE, LAG_BOTTOM)),
                extra_writes=full_source_state_writes(entry),
            )

    # Read ahead in SLOW mode.  Move the lag head onto a virgin cell now; the
    # continuation writes its unit after APPEND finishes.
    for bit, command in (("0", "APPEND0"), ("1", "APPEND1")):
        for ready in BUFFER_READY_IDS:
            yield _call_row(
                caller=AWAIT_SLOW,
                ready_id=ready,
                command=command,
                continuation=BUFFERED_AFTER_APPEND,
                input_symbol=bit,
                extra_reads=((MODE_TAPE, MODE_SLOW), (LAG_TAPE, frozenset((LAG_BOTTOM, LAG_ONE)))),
                extra_moves=((LAG_TAPE, int(Shift.RIGHT)),),
            )

    # Direct read: APPEND has returned; RIGHT reaches the just-appended bit.
    for ready in BUFFER_READY_IDS:
        yield _call_row(
            caller=DIRECT_AFTER_APPEND,
            ready_id=ready,
            command="RIGHT",
            continuation=SOURCE_DISPATCH,
        )

    # Lagged source completion: decrement lag in the same caller transition
    # that starts RIGHT to the next buffered symbol.
    for ready in BUFFER_READY_IDS:
        yield _call_row(
            caller=COMPLETE,
            ready_id=ready,
            command="RIGHT",
            continuation=LAGGED_AFTER_RIGHT,
            extra_reads=((LAG_TAPE, LAG_ONE),),
            extra_writes=((LAG_TAPE, BLANK),),
            extra_moves=((LAG_TAPE, int(Shift.LEFT)),),
        )


def buffered_after_append_row() -> ScheduledRow:
    return ScheduledRow(
        BUFFERED_AFTER_APPEND,
        None,
        ((LAG_TAPE, BLANK),),
        ScheduledAction(SOURCE_DISPATCH, ((LAG_TAPE, LAG_ONE),)),
    )


def iter_lagged_source_select_rows() -> Iterator[ScheduledRow]:
    for bit, entry in (("0", SOURCE_ENTRY_0), ("1", SOURCE_ENTRY_1)):
        for ready in BUFFER_READY_BY_CURRENT[bit]:
            yield ScheduledRow(
                LAGGED_AFTER_RIGHT,
                None,
                ((BUFFER_REGISTER_TAPE, _buffer_qsymbol(ready)),),
                ScheduledAction(CLOCK, full_source_state_writes(entry)),
            )


def iter_equal_completion_rows() -> Iterator[ScheduledRow]:
    reload_writes = tuple(
        (CLOCK_START + i, bit)
        for i, bit in enumerate(_bits_le(GALIL_SCHEDULER_PERIOD, CLOCK_WIDTH))
    )
    for bit in (0, 1):
        yield ScheduledRow(
            COMPLETE,
            None,
            ((LAG_TAPE, LAG_BOTTOM), (PENDING_OUTPUT_TAPE, bit)),
            ScheduledAction(
                AWAIT_FAST,
                reload_writes + ((MODE_TAPE, MODE_FAST),),
                input_move=1,
                emit=bit,
            ),
        )


def _bits_le(value: int, width: int) -> tuple[int, ...]:
    return tuple((value >> i) & 1 for i in range(width))


def iter_clock_rows() -> Iterator[ScheduledRow]:
    rows = fixed_countdown_rows(GALIL_SCHEDULER_PERIOD)
    for row in rows:
        reads = tuple(
            (CLOCK_START + i, atom)
            for i, atom in enumerate(row.guard)
            if atom is not None
        )
        writes = tuple(
            (CLOCK_START + i, value)
            for i, value in enumerate(row.writes)
            if value is not None
        )
        if not row.tick:
            yield ScheduledRow(CLOCK, None, reads, ScheduledAction(SOURCE_DISPATCH, writes))
            continue
        for mode in (MODE_FAST, MODE_SLOW):
            yield ScheduledRow(
                CLOCK,
                None,
                reads + ((MODE_TAPE, mode),),
                ScheduledAction(
                    AWAIT_SLOW,
                    writes + ((MODE_TAPE, MODE_SLOW),),
                    input_move=1,
                    emit=0,
                ),
            )


def iter_small_controller_rows() -> Iterator[ScheduledRow]:
    yield from iter_buffer_call_rows()
    yield buffered_after_append_row()
    yield from iter_lagged_source_select_rows()
    yield from iter_equal_completion_rows()
    yield from iter_clock_rows()


def _interval_cost(read_kind: ReadKind, steps: int, lagged: int) -> int:
    if steps <= 0 or lagged < 0 or lagged > steps:
        raise ValueError((steps, lagged))
    setup = DIRECT_READ_SETUP_BOUND if read_kind is ReadKind.DIRECT else BUFFERED_READ_SETUP_BOUND
    ordinary = setup + 3 * steps + (LAGGED_COMPLETING_SOURCE_STEP_BOUND - 3) * lagged
    assert ordinary <= setup + steps * SOURCE_STEP_COMPOSITION_BOUND
    assert ordinary <= BOUNDED_DELAY_TRANSITIONS
    return ordinary


def schedule_trace_via_composition(
    work: Sequence[int], outputs: Sequence[int], c: int
) -> CompositionTrace:
    """Execute the factored buffer/source/clock composition independently."""
    if c <= 0:
        raise ValueError(c)
    if len(work) != len(outputs):
        raise ValueError("work/output lengths differ")
    if any(w <= 0 for w in work):
        raise ValueError("work values must be positive")
    if any(o not in (0, 1) for o in outputs):
        raise ValueError("outputs must be bits")

    period = 2 * c
    n = len(work)
    mode = Mode.FAST
    h1 = 0
    remaining = work[0] if n else 0
    read_ahead: list[int] = []
    clock = period
    events: list[SchedulerEvent] = []
    intervals: list[CompositionInterval] = []

    for h2 in range(n):
        read_kind = ReadKind.DIRECT if mode is Mode.FAST else ReadKind.BUFFERED
        if read_kind is ReadKind.DIRECT:
            if h1 != h2 or read_ahead:
                raise AssertionError(("direct read invariant", h1, h2, read_ahead))
        else:
            read_ahead.append(h2)

        source_steps = 0
        lagged_completions = 0
        while True:
            if h1 >= n:
                raise AssertionError("source trace ended before physical output head")
            remaining -= 1
            source_steps += 1
            completed = remaining == 0
            equal = h1 == h2

            if completed and equal:
                events.append(SchedulerEvent(h2, outputs[h1], mode, h1, False))
                h1 += 1
                remaining = work[h1] if h1 < n else 0
                mode = Mode.FAST
                clock = period
                intervals.append(
                    CompositionInterval(
                        h2,
                        read_kind,
                        source_steps,
                        lagged_completions,
                        _interval_cost(read_kind, source_steps, lagged_completions),
                        outputs[h2],
                        False,
                        mode,
                    )
                )
                break

            if completed:
                if not read_ahead or read_ahead[0] != h1 + 1:
                    raise AssertionError(("FIFO/source invariant", h1, h2, read_ahead))
                read_ahead.pop(0)
                h1 += 1
                remaining = work[h1]
                lagged_completions += 1

            clock -= 1
            if clock == 0:
                events.append(SchedulerEvent(h2, 0, mode, h1, True))
                mode = Mode.SLOW
                clock = period
                intervals.append(
                    CompositionInterval(
                        h2,
                        read_kind,
                        source_steps,
                        lagged_completions,
                        _interval_cost(read_kind, source_steps, lagged_completions),
                        0,
                        True,
                        mode,
                    )
                )
                break

    result = CompositionTrace(tuple(events), tuple(intervals))
    reference = tuple(schedule_trace_via_compact(work, outputs, c))
    if result.events != reference:
        raise AssertionError((result.events, reference))
    return result


def certificate() -> CompositionCertificate:
    return CompositionCertificate(
        source_states=SOURCE_STATES,
        source_rows=SOURCE_ROWS,
        source_tapes=SOURCE_TAPES,
        source_state_bits=SOURCE_STATE_BITS,
        scheduler_predictability_c=GALIL_PREDICTABILITY_C,
        source_step_period=GALIL_SCHEDULER_PERIOD,
        countdown_width_bits=CLOCK_WIDTH,
        compact_countdown_rows=len(fixed_countdown_rows(GALIL_SCHEDULER_PERIOD)),
        scheduled_work_tapes=SCHEDULED_WORK_TAPES,
        scheduled_states=SCHEDULED_STATES,
        input_history_states=BUFFER_STATES,
        input_history_rows=BUFFER_ROWS,
        input_history_ready_states=len(BUFFER_READY_IDS),
        input_history_append_bound=HISTORY_APPEND,
        input_history_right_bound=HISTORY_RIGHT,
        direct_read_setup_bound=DIRECT_READ_SETUP_BOUND,
        buffered_read_setup_bound=BUFFERED_READ_SETUP_BOUND,
        noncompleting_source_step_bound=NONCOMPLETING_SOURCE_STEP_BOUND,
        equal_completing_source_step_bound=EQUAL_COMPLETING_SOURCE_STEP_BOUND,
        lagged_completing_source_step_bound=LAGGED_COMPLETING_SOURCE_STEP_BOUND,
        uniform_source_step_composition_bound=SOURCE_STEP_COMPOSITION_BOUND,
        bounded_delay_transitions=BOUNDED_DELAY_TRANSITIONS,
        transformed_source_rows=SOURCE_ROWS,
        source_dispatch_rows=SOURCE_DISPATCH_ROWS,
        buffer_service_rows=BUFFER_SERVICE_ROWS,
        buffer_call_rows=BUFFER_CALL_ROWS,
        lagged_source_select_rows=LAGGED_SOURCE_SELECT_ROWS,
        small_controller_rows=SMALL_CONTROLLER_ROWS,
        scheduled_total_rows=SCHEDULED_TOTAL_ROWS,
        source_row_product_factor=1,
    )


def certificate_dict() -> dict:
    data = asdict(certificate())
    data.update(
        {
            "format": "factored ordinary SG/Galil composition certificate v2",
            "status": "proved bounded-delay ordinary composition; fixed speedup imported separately",
            "source_done_states": [SOURCE_DONE_0, SOURCE_DONE_1],
            "source_entry_states": [SOURCE_ENTRY_0, SOURCE_ENTRY_1],
            "buffer_continuations": list(BUFFER_CONTINUATIONS),
            "row_families": {
                "source_lift": "one row per certified source row",
                "source_dispatch": "one exact 21-bit row per nonterminal source state",
                "history_service": "one registered load row per history state, one active row per history row, four continuation rows",
                "history_calls": "six call sites times 1268 reachable ready states",
                "clock": "62 non-tick rows plus the tick row split by FAST/SLOW mode",
            },
            "simulation_relation": {
                "source_tapes": "identical to source configuration",
                "source_q_bits": "little-endian encoding of source state",
                "input_history": "physical input prefix, reader at simulated h1, writer after physical h2",
                "lag": "unary h2-h1",
                "clock": "remaining source-step allowance in current physical interval",
                "mode": "Galil FAST/SLOW",
            },
        }
    )
    return data


def write_certificate(path: str | Path) -> dict:
    data = certificate_dict()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def audit_constants() -> None:
    assert SOURCE_STATE_BITS == 21
    assert CLOCK_WIDTH == 32
    assert len(BUFFER_READY_IDS) == 1268
    assert all(len(BUFFER_READY_BY_CURRENT[x]) == 317 for x in ("#", "_", "0", "1"))
    assert SOURCE_STEP_COMPOSITION_BOUND == 117
    assert DIRECT_READ_SETUP_BOUND == 214
    assert BUFFERED_READ_SETUP_BOUND == 102
    assert BOUNDED_DELAY_TRANSITIONS == 416_945_810_716
    assert CLOCK_ROWS == 64
    assert SCHEDULED_WORK_TAPES == 295
    assert BUFFER_SERVICE_ROWS == 232_498
    assert BUFFER_CALL_ROWS == 7_608
    assert LAGGED_SOURCE_SELECT_ROWS == 634
    assert SMALL_CONTROLLER_ROWS == 8_309
    assert SCHEDULED_TOTAL_ROWS == 8_305_403
    assert SCHEDULED_STATES == 1_653_051


audit_constants()


if __name__ == "__main__":
    print(json.dumps(certificate_dict(), indent=2, sort_keys=True))
