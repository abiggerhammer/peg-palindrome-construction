"""Deterministic finite row enumerator used by the indexed PEG compiler.

The functions in this module are intentionally streaming.  They are the exact
compile-time oracle named by the full finite indexed PEG presentation.  Running
the whole stream is expensive but finite; no row family is assumed rather than
generated.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Hashable, Iterator

from background_bounds import background_steps_per_input
from build_outer_service_fabric import build_fabric
from scheduled_source_composition import (
    ScheduledRow,
    iter_buffer_service_rows,
    iter_small_controller_rows,
    iter_source_dispatch_rows,
    lift_source_row,
)
from sg_outer_constant_cases import build_constant_case_rows
from sg_outer_dispatcher_table import build_dispatcher_rows
from sg_outer_remaining_cases import build_remaining_case_rows
from sparse_registered_linker import SparseRow


@lru_cache(maxsize=1)
def registered_source_alphabets() -> tuple[tuple[Hashable, ...], ...]:
    """Return exact source-tape alphabets after all calls are registered.

    Continuation symbols are allocated while the controller row streams are
    traversed.  A bare ``build_fabric().tape_alphabets()`` is therefore too
    early and omits 2,444 continuation symbols.
    """

    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constant = build_constant_case_rows(fabric)
    remaining = build_remaining_case_rows(
        fabric, background_budget=background_steps_per_input()
    )
    # Building dispatcher/constant rows has already registered their calls;
    # the remaining family performs deferred registration during iteration.
    remaining_count = 0
    for _ in remaining.iter_rows(fabric):
        remaining_count += 1
    expected_controller = len(dispatcher.rows) + len(constant.rows) + remaining_count
    if expected_controller != 3_156_170:
        raise AssertionError(expected_controller)
    return fabric.tape_alphabets()


def iter_source_rows() -> Iterator[SparseRow]:
    """Enumerate the complete corrected ordinary SG source table once."""

    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constant = build_constant_case_rows(fabric)
    remaining = build_remaining_case_rows(
        fabric, background_budget=background_steps_per_input()
    )

    # Controller iteration registers every continuation used by the service
    # fabric.  Service rows are therefore emitted only after the controller
    # stream has been exhausted.
    yield from dispatcher.rows
    yield from constant.rows
    yield from remaining.iter_rows(fabric)
    yield from fabric.all_service_rows()


def iter_scheduled_rows() -> Iterator[ScheduledRow]:
    """Enumerate all 8,305,403 rows of the bounded-delay composition."""

    for row in iter_source_rows():
        yield lift_source_row(row)
    yield from iter_source_dispatch_rows()
    yield from iter_buffer_service_rows()
    yield from iter_small_controller_rows()
