"""End-to-end audit of the SG source trace through Galil's scheduler.

This module does not replace the transition-table lowering.  It joins the two
already executable halves at their exact interface:

* :class:`sg_zero_ratio_machine.SGZeroRatioMachine` reports the number of
  primitive Algorithm-Y/background ticks spent after each source symbol;
* :func:`predictability_scheduler.schedule_trace_via_table` executes Galil's
  finite fast/slow controller on that source trace.

The result is useful for differential testing of synchronization and output
alignment before the finite tables are physically inlined.
"""

from __future__ import annotations

from dataclasses import dataclass

from construction_constants import scheduler_predictability_constant
from predictability_scheduler import (
    MAX_MATERIALIZED_SCHEDULER_C,
    SchedulerEvent,
    schedule_trace_via_compact,
    schedule_trace_via_table,
)
from sg_zero_ratio_machine import SGZeroRatioMachine, StepRecord


@dataclass(frozen=True)
class SGTrace:
    word: str
    work: tuple[int, ...]
    outputs: tuple[int, ...]
    records: tuple[StepRecord, ...]


def source_trace(
    word: str,
    *,
    c: int = 16,
    background_scan_backend: str = "algorithm_y_tape",
    lemma32_backend: str = "algorithm_y_tape",
    background_work_budget: int | None = None,
) -> SGTrace:
    machine = SGZeroRatioMachine(
        c=c,
        background_scan_backend=background_scan_backend,
        lemma32_backend=lemma32_backend,
        background_work_budget=background_work_budget,
    )
    work: list[int] = []
    outputs: list[int] = []
    records: list[StepRecord] = []
    for symbol in word:
        record = machine.append(symbol)
        records.append(record)
        # One finite-control step surrounds each reported worker tick.
        work.append(max(1, record.nominal_work) + 1)
        outputs.append(int(machine.accepts))
    return SGTrace(word, tuple(work), tuple(outputs), tuple(records))


def scheduled_trace(
    word: str,
    *,
    source_c: int = 16,
    scheduler_c: int | None = None,
    background_scan_backend: str = "algorithm_y_tape",
    lemma32_backend: str = "algorithm_y_tape",
    background_work_budget: int | None = None,
) -> tuple[SGTrace, tuple[SchedulerEvent, ...]]:
    trace = source_trace(
        word,
        c=source_c,
        background_scan_backend=background_scan_backend,
        lemma32_backend=lemma32_backend,
        background_work_budget=background_work_budget,
    )
    if scheduler_c is None:
        scheduler_c = scheduler_predictability_constant(source_c)
    executor = (
        schedule_trace_via_table
        if scheduler_c <= MAX_MATERIALIZED_SCHEDULER_C
        else schedule_trace_via_compact
    )
    events = tuple(executor(trace.work, trace.outputs, scheduler_c))
    return trace, events


def scheduled_outputs(
    word: str,
    *,
    source_c: int = 16,
    scheduler_c: int | None = None,
    background_scan_backend: str = "algorithm_y_tape",
    lemma32_backend: str = "algorithm_y_tape",
    background_work_budget: int | None = None,
) -> tuple[int, ...]:
    _, events = scheduled_trace(
        word,
        source_c=source_c,
        scheduler_c=scheduler_c,
        background_scan_backend=background_scan_backend,
        lemma32_backend=lemma32_backend,
        background_work_budget=background_work_budget,
    )
    return tuple(event.output for event in events)
