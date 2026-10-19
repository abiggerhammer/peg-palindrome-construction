"""Constant-time SG case bodies and source-output interface.

Case 1 needs no invariant repair.  Case 4 drops the failed second midpoint and
starts a fresh retained Lemma-3.3 background.  This module lowers both paths to
registered ordinary component calls, including true fresh-epoch resets of the
three background history zippers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Mapping

import history_zipper_ordinary_tm as hz
from sg_outer_dispatcher_table import (
    CASE_ENTRY,
    KNOWN,
    LEFT_EXACT,
    NO,
    SIGN_ZERO,
    UNKNOWN,
    YES,
    _counter_call_rows,
    _direct,
    _history_adapter,
    _history_call_rows,
)
from sg_zero_ratio import UpdateCase
from sparse_registered_linker import SparseAction, SparseRegisteredFabric, SparseRow

OUT_CHECK = 100
OUT_INSPECT = 101
OUT_RESTORE = 102
OUT_DONE = 103
SOURCE_DONE_0 = 110
SOURCE_DONE_1 = 111

C4_INIT = 120
C4_FRESH_K = 121
C4_FRESH_BG_RETURN = 122
C4_RESET_CURRENT = 123
C4_RESET_LAG = 124
C4_RESET_COPY = 125

STATE_NAMES = {
    OUT_CHECK: "OUT_CHECK",
    OUT_INSPECT: "OUT_INSPECT",
    OUT_RESTORE: "OUT_RESTORE",
    OUT_DONE: "OUT_DONE",
    SOURCE_DONE_0: "SOURCE_DONE_0",
    SOURCE_DONE_1: "SOURCE_DONE_1",
    C4_INIT: "C4_INIT",
    C4_FRESH_K: "C4_FRESH_K",
    C4_FRESH_BG_RETURN: "C4_FRESH_BG_RETURN",
    C4_RESET_CURRENT: "C4_RESET_CURRENT",
    C4_RESET_LAG: "C4_RESET_LAG",
    C4_RESET_COPY: "C4_RESET_COPY",
}


@dataclass(frozen=True)
class ConstantCaseBuild:
    rows: tuple[SparseRow, ...]
    state_names: Mapping[int, str]


def _current_is_sentinel_rows(
    fabric: SparseRegisteredFabric,
    *,
    state: int,
    component: str,
    next_state: int,
) -> Iterator[SparseRow]:
    adapter = _history_adapter(fabric, component)
    register = fabric.layout(component).register_tape
    output = fabric.extra_tapes["OUTPUT"]
    for qid in adapter.ready_state_ids:
        core = adapter.id_to_state[qid]
        yield _direct(
            state,
            next_state,
            reads={register: fabric.layout(component).qsymbol(qid)},
            writes={output: YES if core.current == "#" else NO},
        )


def build_constant_case_rows(fabric: SparseRegisteredFabric) -> ConstantCaseBuild:
    t = fabric.extra_tapes
    rows: list[SparseRow] = []

    # Case 1: no data movement; proceed directly to prefix output.
    rows.append(_direct(CASE_ENTRY[UpdateCase.ONE_BOTH_SURVIVE], OUT_CHECK))

    # Case 4: B survives, B' fails.  Keep the stale B'/LEFT' heads for the
    # later paid return, but mark the second unknown and start fresh epochs for
    # k, BG_RETURN, and the three retained Lemma-3.3 history cursors.
    rows.append(_direct(
        CASE_ENTRY[UpdateCase.FOUR_FIRST_SURVIVES],
        C4_FRESH_K,
        writes={
            t["SECOND"]: UNKNOWN,
            t["LAZY_MODE"]: "C",  # COPY
            t["COPY_NEEDED"]: YES,
            t["K_SIGN"]: SIGN_ZERO,
            t["L33_PHASE"]: "I",
        },
    ))
    rows.extend(_counter_call_rows(
        fabric,
        caller=C4_FRESH_K,
        name="K_MAG",
        command="FRESH_ZERO",
        continuation=C4_FRESH_BG_RETURN,
    ))
    rows.extend(_counter_call_rows(
        fabric,
        caller=C4_FRESH_BG_RETURN,
        name="BG_RETURN",
        command="FRESH_ZERO",
        continuation=C4_RESET_CURRENT,
    ))
    rows.extend(_history_call_rows(
        fabric,
        caller=C4_RESET_CURRENT,
        name="L33_CURRENT",
        command="RESET",
        continuation=C4_RESET_LAG,
    ))
    rows.extend(_history_call_rows(
        fabric,
        caller=C4_RESET_LAG,
        name="L33_LAG",
        command="RESET",
        continuation=C4_RESET_COPY,
    ))
    rows.extend(_history_call_rows(
        fabric,
        caller=C4_RESET_COPY,
        name="L33_COPY",
        command="RESET",
        continuation=OUT_CHECK,
    ))

    # Acceptance is encoded by LEFT(B) reaching the history sentinel after a
    # temporary one-cell move.  The cursor is restored before source completion.
    rows.append(_direct(
        OUT_CHECK,
        SOURCE_DONE_0,
        reads={t["LB_REL"]: frozenset(("A", "1", "2"))},
        writes={t["OUTPUT"]: NO},
    ))
    rows.extend(_history_call_rows(
        fabric,
        caller=OUT_CHECK,
        name="LB",
        command="LEFT",
        continuation=OUT_INSPECT,
    ))
    n = len(_history_adapter(fabric, "LB").ready_state_ids)
    left_rows = rows[-n:]
    del rows[-n:]
    for row in left_rows:
        rows.append(SparseRow(
            row.state,
            row.reads + ((t["LB_REL"], LEFT_EXACT),),
            row.action,
        ))
    rows.extend(_current_is_sentinel_rows(
        fabric,
        state=OUT_INSPECT,
        component="LB",
        next_state=OUT_RESTORE,
    ))
    rows.extend(_history_call_rows(
        fabric,
        caller=OUT_RESTORE,
        name="LB",
        command="RIGHT",
        continuation=OUT_DONE,
    ))
    rows.append(_direct(
        OUT_DONE,
        SOURCE_DONE_0,
        reads={t["OUTPUT"]: NO},
    ))
    rows.append(_direct(
        OUT_DONE,
        SOURCE_DONE_1,
        reads={t["OUTPUT"]: YES},
    ))

    return ConstantCaseBuild(tuple(rows), STATE_NAMES)
