"""Executable form of Galil's fast/slow predictability scheduler.

The source algorithm A is represented only by the amount of micro-work it
performs on each input symbol and the output bit it eventually emits.  This is
sufficient to audit the control schedule from Galil, *String Matching in Real
Time*, Section 2:

* in FAST mode the simulated and physical input heads coincide;
* if A has not finished the current symbol after ``2*c`` microsteps, B emits a
  speculative zero, advances its physical head, and enters SLOW mode;
* in SLOW mode B advances its physical head once every ``2*c`` simulation
  steps while A catches up; outputs of A for positions already passed are
  ignored; when A completes the position currently under the physical head,
  its real output is emitted and the machine returns to FAST mode.

Correctness of speculative zeroes is the theorem's predictability proof.  This
module makes the scheduler itself finite and executable; it does not attempt to
reprove that an arbitrary trace satisfies the predictability condition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Sequence




MAX_MATERIALIZED_SCHEDULER_C = 100_000


@dataclass(frozen=True)
class CountdownRow:
    """One sparse row of a fixed-width exact countdown clock.

    Bits are little-endian and live on fixed one-cell tapes. ``None`` is a
    wildcard / no-write entry.  Every positive bit vector matches exactly one
    row.  The value one is the tick row; it reloads the fixed period.
    """

    guard: tuple[int | None, ...]
    writes: tuple[int | None, ...]
    tick: bool


def _bits_le(value: int, width: int) -> tuple[int, ...]:
    return tuple((value >> i) & 1 for i in range(width))


def fixed_countdown_rows(period: int) -> tuple[CountdownRow, ...]:
    """Return a compact exact ``period``-step countdown table.

    The table has ``2*bit_length(period)-1`` rows.  A multitape transition can
    inspect and update all fixed bit tapes in parallel, so one countdown
    decrement is one ordinary transition.  The rows partition all positive
    counter values; zero is unreachable after initialization.
    """

    if not isinstance(period, int) or period <= 0:
        raise ValueError(period)
    width = period.bit_length()
    target = _bits_le(period, width)
    rows: list[CountdownRow] = []

    # Exact value one: emit a clock tick and reload the full period.
    rows.append(
        CountdownRow(
            guard=(1,) + (0,) * (width - 1),
            writes=target,
            tick=True,
        )
    )

    # Even values: locate the least significant one, set all lower zero bits
    # to one, clear that bit, and leave higher bits unchanged.
    for index in range(1, width):
        rows.append(
            CountdownRow(
                guard=(0,) * index + (1,) + (None,) * (width - index - 1),
                writes=(1,) * index + (0,) + (None,) * (width - index - 1),
                tick=False,
            )
        )

    # Odd values larger than one.  Partition them by the first higher one so
    # the exact-one row remains disjoint; decrementing only clears bit zero.
    for first_higher_one in range(1, width):
        rows.append(
            CountdownRow(
                guard=(1,)
                + (0,) * (first_higher_one - 1)
                + (1,)
                + (None,) * (width - first_higher_one - 1),
                writes=(0,) + (None,) * (width - 1),
                tick=False,
            )
        )
    return tuple(rows)


def _row_matches(row: CountdownRow, bits: tuple[int, ...]) -> bool:
    return all(expected is None or expected == actual for expected, actual in zip(row.guard, bits))


def countdown_step(
    bits: tuple[int, ...], rows: Sequence[CountdownRow]
) -> tuple[tuple[int, ...], bool]:
    """Execute one compact countdown transition."""

    matching = [row for row in rows if _row_matches(row, bits)]
    if len(matching) != 1:
        raise AssertionError((bits, len(matching)))
    row = matching[0]
    updated = tuple(
        old if write is None else write for old, write in zip(bits, row.writes)
    )
    return updated, row.tick


def compact_scheduler_spec(c: int) -> dict:
    """Return a compact, non-unrolled Galil scheduler specification."""

    if not isinstance(c, int) or c <= 0:
        raise ValueError(c)
    period = 2 * c
    rows = fixed_countdown_rows(period)
    return {
        "format": "Galil fast/slow compact countdown scheduler v1",
        "predictability_c": c,
        "source_step_period": period,
        "clock": {
            "encoding": "little-endian binary on fixed one-cell tapes",
            "width_bits": period.bit_length(),
            "initial_value": period,
            "initial_bits_le": list(_bits_le(period, period.bit_length())),
            "target_binary": f"{period:0{period.bit_length()}b}",
            "row_count": len(rows),
            "rows": [
                {
                    "guard_le": list(row.guard),
                    "writes_le": list(row.writes),
                    "tick": row.tick,
                }
                for row in rows
            ],
        },
        "control": {
            "modes": ["FAST", "SLOW"],
            "fast_completed": "emit source; advance both heads; reload clock; stay FAST",
            "fast_tick": "emit zero; advance physical head; reload clock; enter SLOW",
            "slow_completed_equal": "emit source; advance both heads; reload clock; enter FAST",
            "slow_other_tick": "emit zero; advance physical head; advance simulated head iff source completed; reload clock; stay SLOW",
            "slow_other_no_tick": "advance simulated head iff source completed; stay SLOW",
        },
        "materialized_unrolled_rows": 12 * c,
        "compact_clock_rows": len(rows),
    }

class Mode(Enum):
    FAST = auto()
    SLOW = auto()


@dataclass(frozen=True)
class SchedulerEvent:
    output_index: int
    output: int
    mode: Mode
    simulated_index: int
    speculative: bool


def schedule_trace(work: Sequence[int], outputs: Sequence[int], c: int) -> list[SchedulerEvent]:
    """Run Galil's scheduler on a finite abstract online computation trace.

    ``work[i]`` must be positive and is the number of source-machine microsteps
    needed to finish input position i.  The returned event list contains one
    output per input position.  An assertion fails when the finite trace ends
    before the simulated head can catch up; callers normally provide enough
    trailing positions to observe the whole schedule.
    """

    if c <= 0:
        raise ValueError(c)
    if len(work) != len(outputs):
        raise ValueError("work/output lengths differ")
    if any(w <= 0 for w in work):
        raise ValueError("work values must be positive")
    if any(o not in (0, 1) for o in outputs):
        raise ValueError("outputs must be bits")

    n = len(work)
    mode = Mode.FAST
    h1 = 0  # source algorithm's current input position
    h2 = 0  # physical head / next position whose output B owes
    remaining = work[0] if n else 0
    fast_spent = 0
    slow_clock = 0
    events: list[SchedulerEvent] = []

    while h2 < n:
        if h1 >= n:
            raise AssertionError("source trace ended before physical output head")

        # One source-machine microstep.
        remaining -= 1
        completed = remaining == 0

        if mode is Mode.FAST:
            fast_spent += 1
            if completed:
                assert h1 == h2
                events.append(
                    SchedulerEvent(h2, outputs[h1], Mode.FAST, h1, False)
                )
                h1 += 1
                h2 += 1
                if h1 < n:
                    remaining = work[h1]
                fast_spent = 0
                continue

            if fast_spent == 2 * c:
                # A has used the complete fast allowance without answering.
                events.append(SchedulerEvent(h2, 0, Mode.FAST, h1, True))
                h2 += 1
                mode = Mode.SLOW
                slow_clock = 0
                continue

        else:  # SLOW
            slow_clock += 1
            if completed:
                if h1 == h2:
                    # A has caught the physical head before the next speculative
                    # deadline.  Its genuine output is still owed.
                    events.append(
                        SchedulerEvent(h2, outputs[h1], Mode.SLOW, h1, False)
                    )
                    h1 += 1
                    h2 += 1
                    if h1 < n:
                        remaining = work[h1]
                    mode = Mode.FAST
                    fast_spent = 0
                    slow_clock = 0
                    continue

                # Output for this lagged position was already speculated.
                h1 += 1
                if h1 < n:
                    remaining = work[h1]
                else:
                    remaining = 0

            if slow_clock == 2 * c:
                events.append(SchedulerEvent(h2, 0, Mode.SLOW, h1, True))
                h2 += 1
                slow_clock = 0

    return events


def scheduled_bits(work: Sequence[int], outputs: Sequence[int], c: int) -> list[int]:
    return [event.output for event in schedule_trace(work, outputs, c)]


@dataclass(frozen=True)
class ControllerState:
    mode: Mode
    clock: int


@dataclass(frozen=True)
class ControllerAction:
    next_state: ControllerState
    emit: str  # "none", "source", or "zero"
    advance_physical: bool
    advance_simulated: bool


def scheduler_control_table(c: int) -> dict[tuple[ControllerState, bool, bool], ControllerAction]:
    """Return Galil's scheduler as a literal finite control table.

    Keys are ``(state, source_completed, heads_equal)``.  When ``emit`` is
    ``"source"`` the caller emits the source machine's just-produced bit.
    The table contains no unbounded counters: ``clock`` ranges over
    ``0..2*c-1`` and is part of finite control.
    """

    if c <= 0:
        raise ValueError(c)
    if c > MAX_MATERIALIZED_SCHEDULER_C:
        raise ValueError(
            f"c={c} would materialize {12*c:,} rows; use compact_scheduler_spec"
        )
    limit = 2 * c
    table: dict[tuple[ControllerState, bool, bool], ControllerAction] = {}

    for mode in Mode:
        for clock in range(limit):
            state = ControllerState(mode, clock)
            for completed in (False, True):
                for equal in (False, True):
                    if mode is Mode.FAST:
                        if not equal:
                            continue  # unreachable invariant violation
                        if completed:
                            action = ControllerAction(
                                ControllerState(Mode.FAST, 0),
                                "source",
                                True,
                                True,
                            )
                        elif clock + 1 == limit:
                            action = ControllerAction(
                                ControllerState(Mode.SLOW, 0),
                                "zero",
                                True,
                                False,
                            )
                        else:
                            action = ControllerAction(
                                ControllerState(Mode.FAST, clock + 1),
                                "none",
                                False,
                                False,
                            )
                    else:
                        if completed and equal:
                            action = ControllerAction(
                                ControllerState(Mode.FAST, 0),
                                "source",
                                True,
                                True,
                            )
                        elif clock + 1 == limit:
                            action = ControllerAction(
                                ControllerState(Mode.SLOW, 0),
                                "zero",
                                True,
                                completed,
                            )
                        else:
                            action = ControllerAction(
                                ControllerState(Mode.SLOW, clock + 1),
                                "none",
                                False,
                                completed,
                            )
                    table[(state, completed, equal)] = action
    return table


def schedule_trace_via_table(
    work: Sequence[int], outputs: Sequence[int], c: int
) -> list[SchedulerEvent]:
    """Independent execution of ``schedule_trace`` through the finite table."""

    if len(work) != len(outputs):
        raise ValueError("work/output lengths differ")
    if any(w <= 0 for w in work):
        raise ValueError("work values must be positive")
    table = scheduler_control_table(c)
    state = ControllerState(Mode.FAST, 0)
    h1 = h2 = 0
    remaining = work[0] if work else 0
    events: list[SchedulerEvent] = []

    while h2 < len(work):
        if h1 >= len(work):
            raise AssertionError("source trace ended before physical output head")
        remaining -= 1
        completed = remaining == 0
        equal = h1 == h2
        action = table[(state, completed, equal)]
        if action.emit != "none":
            bit = outputs[h1] if action.emit == "source" else 0
            event_h1 = h1 + (1 if action.emit == "zero" and action.advance_simulated else 0)
            events.append(
                SchedulerEvent(
                    output_index=h2,
                    output=bit,
                    mode=state.mode,
                    simulated_index=event_h1,
                    speculative=action.emit == "zero",
                )
            )
        if action.advance_simulated:
            h1 += 1
            remaining = work[h1] if h1 < len(work) else 0
        if action.advance_physical:
            h2 += 1
        state = action.next_state
    return events


def schedule_trace_via_compact(
    work: Sequence[int], outputs: Sequence[int], c: int
) -> list[SchedulerEvent]:
    """Execute Galil's schedule through the compact countdown rows.

    Unlike :func:`schedule_trace_via_table`, this executor does not allocate
    ``O(c)`` finite-control states and is therefore suitable for the proved
    production constant.
    """

    if c <= 0:
        raise ValueError(c)
    if len(work) != len(outputs):
        raise ValueError("work/output lengths differ")
    if any(w <= 0 for w in work):
        raise ValueError("work values must be positive")
    if any(o not in (0, 1) for o in outputs):
        raise ValueError("outputs must be bits")

    period = 2 * c
    rows = fixed_countdown_rows(period)
    clock = _bits_le(period, period.bit_length())
    mode = Mode.FAST
    h1 = h2 = 0
    remaining = work[0] if work else 0
    events: list[SchedulerEvent] = []

    while h2 < len(work):
        if h1 >= len(work):
            raise AssertionError("source trace ended before physical output head")
        remaining -= 1
        completed = remaining == 0
        equal = h1 == h2

        if mode is Mode.FAST and completed:
            if not equal:
                raise AssertionError("FAST mode head invariant")
            events.append(SchedulerEvent(h2, outputs[h1], Mode.FAST, h1, False))
            h1 += 1
            h2 += 1
            remaining = work[h1] if h1 < len(work) else 0
            clock = _bits_le(period, period.bit_length())
            continue

        if mode is Mode.SLOW and completed and equal:
            events.append(SchedulerEvent(h2, outputs[h1], Mode.SLOW, h1, False))
            h1 += 1
            h2 += 1
            remaining = work[h1] if h1 < len(work) else 0
            mode = Mode.FAST
            clock = _bits_le(period, period.bit_length())
            continue

        event_h1 = h1
        if completed:
            h1 += 1
            event_h1 = h1
            remaining = work[h1] if h1 < len(work) else 0

        clock, tick = countdown_step(clock, rows)
        if tick:
            events.append(
                SchedulerEvent(
                    output_index=h2,
                    output=0,
                    mode=mode,
                    simulated_index=event_h1,
                    speculative=True,
                )
            )
            h2 += 1
            if mode is Mode.FAST:
                mode = Mode.SLOW

    return events
