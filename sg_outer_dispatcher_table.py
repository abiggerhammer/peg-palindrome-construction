"""Literal finite dispatcher for one Seiferas--Galil input symbol.

This is the first half of the final outer microprogram.  It performs, one
ordinary registered-component call or one direct one-cell control transition at
a time:

1. append the new bit to all six retained history cursors;
2. advance/test the B, B', LEFT, LEFT', BG and BGL cursor groups;
3. decrement the signed predictability counter ``k``;
4. select one of the six SG update cases through the published 16-entry finite
   decision table.

The dispatcher stops at a case-entry state.  Case bodies are linked separately,
so this module can be exhaustively differential-tested over snapshots from the
existing all-ordinary audit executor before the larger worker orchestration is
added.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable, Iterator, Mapping, Sequence

import history_zipper_ordinary_tm as hz
from flat_tm import Shift
from sg_controller import sg_control_table
from sg_zero_ratio import UpdateCase
from sparse_registered_linker import (
    SparseAction,
    SparseRegisteredFabric,
    SparseRow,
    SymbolicAdapter,
)
from unary_counter_ordinary_tm import (
    BOTTOM,
    ERROR as COUNTER_ERROR,
    ONE,
    READY as COUNTER_READY,
    command_state as counter_command_state,
    machine as counter_machine,
)

# Controller IDs are deliberately stable and live in the reserved 0..8191 range.
READ0 = 0
READ1 = 1
CAPTURE0 = 2
CAPTURE1 = 3
APPEND_B = 4
APPEND_BP = 5
APPEND_LB = 6
APPEND_LBP = 7
APPEND_BG = 8
APPEND_BGL = 9
ADVANCE_LB = 10
COMPARE_LB = 11
ADVANCE_LBP = 12
COMPARE_LBP = 13
ADVANCE_BGL = 14
ADVANCE_B = 15
ADVANCE_BP = 16
ADVANCE_BG = 17
MAYBE_DEC_K = 18
K_DEC_DISPATCH = 19
K_DEC_AFTER_POS = 20
K_DEC_SET_NEG = 21
K_DEC_DONE = 22
DISPATCH = 23
CASE_ENTRY = {
    UpdateCase.ONE_BOTH_SURVIVE: 30,
    UpdateCase.TWO_BOTH_FAIL: 31,
    UpdateCase.THREE_SECOND_SURVIVES: 32,
    UpdateCase.FOUR_FIRST_SURVIVES: 33,
    UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES: 34,
    UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS: 35,
}
ERROR = 63

CONTROLLER_STATES_USED = tuple(sorted({
    READ0, READ1, CAPTURE0, CAPTURE1,
    APPEND_B, APPEND_BP, APPEND_LB, APPEND_LBP, APPEND_BG, APPEND_BGL,
    ADVANCE_LB, COMPARE_LB, ADVANCE_LBP, COMPARE_LBP, ADVANCE_BGL,
    ADVANCE_B, ADVANCE_BP, ADVANCE_BG, MAYBE_DEC_K, K_DEC_DISPATCH,
    K_DEC_AFTER_POS, K_DEC_SET_NEG, K_DEC_DONE, DISPATCH, ERROR,
    *CASE_ENTRY.values(),
}))

MID_BEFORE = "B"
MID_AT = "A"
MID_AFTER = "X"
LEFT_EXACT = "E"
LEFT_AT = "A"
LEFT_AFTER1 = "1"
LEFT_AFTER2 = "2"
KNOWN = "K"
UNKNOWN = "U"
YES = "1"
NO = "0"
SIGN_NEG = "N"
SIGN_ZERO = "Z"
SIGN_POS = "P"

HISTORY_ORDER = ("B", "BP", "LB", "LBP", "BG", "BGL")


@dataclass(frozen=True)
class DispatcherBuild:
    rows: tuple[SparseRow, ...]
    state_names: Mapping[int, str]


def _direct(
    state: int,
    next_state: int,
    *,
    reads: Mapping[int, object] = {},
    writes: Mapping[int, object] = {},
    moves: Mapping[int, int] = {},
) -> SparseRow:
    return SparseRow(
        state,
        tuple(sorted(reads.items())),
        SparseAction(
            next_state,
            tuple(sorted(writes.items())),
            tuple(sorted(moves.items())),
        ),
    )


def _history_adapter(fabric: SparseRegisteredFabric, name: str) -> SymbolicAdapter:
    adapter = fabric.layout(name).adapter
    if not isinstance(adapter, SymbolicAdapter):
        raise TypeError((name, type(adapter)))
    return adapter


def _history_call_rows(
    fabric: SparseRegisteredFabric,
    *,
    caller: int,
    name: str,
    command: str,
    continuation: int,
) -> tuple[SparseRow, ...]:
    adapter = _history_adapter(fabric, name)

    def entry(qid: int) -> int:
        state = adapter.id_to_state[qid]
        return adapter.state_to_id[hz.as_command_state(state, command)]

    return tuple(fabric.call_rows(
        caller_state=caller,
        component=name,
        continuation_state=continuation,
        entry_transform=entry,
        allowed_local_states=adapter.ready_state_ids,
    ))


def _counter_call_rows(
    fabric: SparseRegisteredFabric,
    *,
    caller: int,
    name: str,
    command: str,
    continuation: int,
) -> tuple[SparseRow, ...]:
    adapter = fabric.layout(name).adapter
    if not isinstance(adapter, SymbolicAdapter):
        raise TypeError((name, type(adapter)))
    entry_id = adapter.state_to_id[counter_command_state(command)]
    return tuple(fabric.call_rows(
        caller_state=caller,
        component=name,
        continuation_state=continuation,
        entry_transform=lambda _q: entry_id,
        allowed_local_states=adapter.ready_state_ids,
    ))


def _current_symbol_rows(
    fabric: SparseRegisteredFabric,
    *,
    state: int,
    component: str,
    next_state: int,
    output_tape: int,
) -> Iterator[SparseRow]:
    """Compare a ready history core's finite ``current`` field with INPUT."""
    adapter = _history_adapter(fabric, component)
    register = fabric.layout(component).register_tape
    input_tape = fabric.extra_tapes["INPUT"]
    for qid in adapter.ready_state_ids:
        core = adapter.id_to_state[qid]
        current = core.current
        if current not in ("0", "1", "#", "_"):
            raise AssertionError(current)
        for bit in ("0", "1"):
            yield _direct(
                state, next_state,
                reads={register: fabric.layout(component).qsymbol(qid), input_tape: bit},
                writes={output_tape: YES if current == bit else NO},
            )


def _history_has_right_rows(
    fabric: SparseRegisteredFabric,
    *,
    state: int,
    component: str,
    if_yes: int,
    if_no: int,
) -> Iterator[SparseRow]:
    """Branch on the strict zipper's finite/front-stack right-data test."""
    adapter = _history_adapter(fabric, component)
    layout = fabric.layout(component)
    register = layout.register_tape
    for qid in adapter.ready_state_ids:
        core = adapter.id_to_state[qid]
        f1_physical = hz.QUEUE_PHYS_BASE + core.mapping[hz.ROLE_INDEX["f1"]]
        front_tape = layout.tape_start + hz.FRONT_PHYS
        f1_tape = layout.tape_start + f1_physical
        qsym = layout.qsymbol(qid)
        # Either nonbottom top means data to the right.  Stack alphabets have
        # only BOTTOM versus finitely many encoded value symbols at the head.
        nonbottom_front = frozenset(
            s for s in adapter.tape_alphabets[hz.FRONT_PHYS] if s != hz.BOTTOM
        )
        nonbottom_f1 = frozenset(
            s for s in adapter.tape_alphabets[f1_physical] if s != hz.BOTTOM
        )
        yield _direct(
            state, if_yes,
            reads={register: qsym, front_tape: nonbottom_front},
        )
        yield _direct(
            state, if_yes,
            reads={register: qsym, front_tape: hz.BOTTOM, f1_tape: nonbottom_f1},
        )
        yield _direct(
            state, if_no,
            reads={register: qsym, front_tape: hz.BOTTOM, f1_tape: hz.BOTTOM},
        )


def build_dispatcher_rows(fabric: SparseRegisteredFabric) -> DispatcherBuild:  # noqa: C901
    t = fabric.extra_tapes
    rows: list[SparseRow] = []

    # Capture the input bit and the old sign of k (the paper's gap-large test
    # is made before k is decremented for the new RIGHT position).
    rows.append(_direct(READ0, CAPTURE0, writes={t["INPUT"]: "0"}))
    rows.append(_direct(READ1, CAPTURE1, writes={t["INPUT"]: "1"}))
    for state in (CAPTURE0, CAPTURE1):
        rows.append(_direct(
            state, APPEND_B,
            reads={t["K_SIGN"]: SIGN_POS},
            writes={t["GAP_LARGE"]: YES},
        ))
        rows.append(_direct(
            state, APPEND_B,
            reads={t["K_SIGN"]: frozenset((SIGN_ZERO, SIGN_NEG))},
            writes={t["GAP_LARGE"]: NO},
        ))

    # Six append/read zipper calls.
    chain = (
        (APPEND_B, "B", APPEND_BP),
        (APPEND_BP, "BP", APPEND_LB),
        (APPEND_LB, "LB", APPEND_LBP),
        (APPEND_LBP, "LBP", APPEND_BG),
        (APPEND_BG, "BG", APPEND_BGL),
        (APPEND_BGL, "BGL", ADVANCE_LB),
    )
    for caller, name, continuation in chain:
        rows.extend(_history_call_rows(
            fabric, caller=caller, name=name, command="APPEND0",
            continuation=continuation,
        ))
        # APPEND1 rows differ only by the INPUT control symbol.  Add the input
        # guard to the generated call cube and choose the corresponding entry.
        # Replace the unconditional APPEND0 rows with guarded 0 rows first.
        appended0 = rows[-len(_history_adapter(fabric, name).ready_state_ids):]
        del rows[-len(appended0):]
        for row in appended0:
            rows.append(SparseRow(
                row.state,
                row.reads + ((t["INPUT"], "0"),),
                row.action,
            ))
        for row in _history_call_rows(
            fabric, caller=caller, name=name, command="APPEND1",
            continuation=continuation,
        ):
            rows.append(SparseRow(
                row.state,
                row.reads + ((t["INPUT"], "1"),),
                row.action,
            ))

    # LEFT(B): branch on old B relation.  Movement commands are followed by a
    # finite current-symbol comparison.
    rows.append(_direct(
        ADVANCE_LB, COMPARE_LB,
        reads={t["B_REL"]: MID_AT, t["LB_REL"]: LEFT_AT},
        writes={t["LB_REL"]: LEFT_EXACT},
    ))
    rows.extend(_history_call_rows(
        fabric, caller=ADVANCE_LB, name="LB", command="LEFT",
        continuation=COMPARE_LB,
    ))
    # Guard the LEFT call by the only legal relation pair.
    n = len(_history_adapter(fabric, "LB").ready_state_ids)
    left_rows = rows[-n:]
    del rows[-n:]
    for row in left_rows:
        rows.append(SparseRow(
            row.state,
            row.reads + ((t["B_REL"], MID_BEFORE), (t["LB_REL"], LEFT_EXACT)),
            row.action,
        ))
    rows.extend(_history_call_rows(
        fabric, caller=ADVANCE_LB, name="LB", command="RIGHT",
        continuation=ADVANCE_LBP,
    ))
    right_rows = rows[-n:]
    del rows[-n:]
    for row in right_rows:
        rows.append(SparseRow(
            row.state,
            row.reads + ((t["B_REL"], MID_AFTER), (t["LB_REL"], LEFT_AFTER2)),
            SparseAction(
                row.action.next_state,
                row.action.writes + ((t["LB_REL"], LEFT_AT), (t["B_OK"], YES)),
                row.action.moves,
            ),
        ))
    rows.extend(_current_symbol_rows(
        fabric, state=COMPARE_LB, component="LB", next_state=ADVANCE_LBP,
        output_tape=t["B_OK"],
    ))

    # LEFT(B').
    rows.append(_direct(
        ADVANCE_LBP, COMPARE_LBP,
        reads={t["BP_REL"]: MID_AT, t["LBP_REL"]: LEFT_AT},
        writes={t["LBP_REL"]: LEFT_EXACT},
    ))
    rows.extend(_history_call_rows(
        fabric, caller=ADVANCE_LBP, name="LBP", command="LEFT",
        continuation=COMPARE_LBP,
    ))
    n = len(_history_adapter(fabric, "LBP").ready_state_ids)
    left_rows = rows[-n:]
    del rows[-n:]
    for row in left_rows:
        rows.append(SparseRow(
            row.state,
            row.reads + ((t["BP_REL"], MID_BEFORE), (t["LBP_REL"], LEFT_EXACT)),
            row.action,
        ))
    rows.extend(_history_call_rows(
        fabric, caller=ADVANCE_LBP, name="LBP", command="RIGHT",
        continuation=ADVANCE_BGL,
    ))
    right_rows = rows[-n:]
    del rows[-n:]
    for row in right_rows:
        rows.append(SparseRow(
            row.state,
            row.reads + ((t["BP_REL"], MID_AFTER), (t["LBP_REL"], LEFT_AFTER2)),
            SparseAction(
                row.action.next_state,
                row.action.writes + ((t["LBP_REL"], LEFT_AT), (t["BP_OK"], YES)),
                row.action.moves,
            ),
        ))
    rows.extend(_current_symbol_rows(
        fabric, state=COMPARE_LBP, component="LBP", next_state=ADVANCE_BGL,
        output_tape=t["BP_OK"],
    ))

    # BGL is maintained with LEFT(B) but does not perform a survival test.
    rows.append(_direct(
        ADVANCE_BGL, ADVANCE_B,
        reads={t["B_REL"]: MID_AT, t["BGL_REL"]: LEFT_AT},
        writes={t["BGL_REL"]: LEFT_EXACT},
    ))
    for command, relation, lrel, new_lrel in (
        ("LEFT", MID_BEFORE, LEFT_EXACT, LEFT_EXACT),
        ("RIGHT", MID_AFTER, LEFT_AFTER2, LEFT_AT),
    ):
        call = _history_call_rows(
            fabric, caller=ADVANCE_BGL, name="BGL", command=command,
            continuation=ADVANCE_B,
        )
        for row in call:
            rows.append(SparseRow(
                row.state,
                row.reads + ((t["B_REL"], relation), (t["BGL_REL"], lrel)),
                SparseAction(
                    row.action.next_state,
                    row.action.writes + ((t["BGL_REL"], new_lrel),),
                    row.action.moves,
                ),
            ))

    # Midpoint cursors B, B', BG after append.  BEFORE is a finite no-op;
    # AT/AFTER require one history RIGHT command and relation update.
    for pc, name, rel_tape, continuation in (
        (ADVANCE_B, "B", "B_REL", ADVANCE_BP),
        (ADVANCE_BP, "BP", "BP_REL", ADVANCE_BG),
        (ADVANCE_BG, "BG", "BG_REL", MAYBE_DEC_K),
    ):
        rows.append(_direct(
            pc, continuation,
            reads={t[rel_tape]: MID_BEFORE},
        ))
        for old, new in ((MID_AT, MID_BEFORE), (MID_AFTER, MID_AT)):
            call = _history_call_rows(
                fabric, caller=pc, name=name, command="RIGHT",
                continuation=continuation,
            )
            for row in call:
                rows.append(SparseRow(
                    row.state,
                    row.reads + ((t[rel_tape], old),),
                    SparseAction(
                        row.action.next_state,
                        row.action.writes + ((t[rel_tape], new),),
                        row.action.moves,
                    ),
                ))

    # Unknown-second executions ignore BP survival and do not decrement k.
    rows.append(_direct(
        MAYBE_DEC_K, DISPATCH,
        reads={t["SECOND"]: UNKNOWN},
        writes={t["BP_OK"]: NO},
    ))
    rows.append(_direct(
        MAYBE_DEC_K, K_DEC_DISPATCH,
        reads={t["SECOND"]: KNOWN},
    ))

    # Signed k := k-1, using K_MAG as a registered unary counter.
    rows.extend(_counter_call_rows(
        fabric, caller=K_DEC_DISPATCH, name="K_MAG", command="DEC",
        continuation=K_DEC_AFTER_POS,
    ))
    n = len(fabric.layout("K_MAG").adapter.ready_state_ids)
    dec_rows = rows[-n:]
    del rows[-n:]
    for row in dec_rows:
        rows.append(SparseRow(
            row.state,
            row.reads + ((t["K_SIGN"], SIGN_POS),),
            row.action,
        ))
    for sign, continuation in ((SIGN_ZERO, K_DEC_SET_NEG), (SIGN_NEG, K_DEC_DONE)):
        call = _counter_call_rows(
            fabric, caller=K_DEC_DISPATCH, name="K_MAG", command="INC",
            continuation=continuation,
        )
        for row in call:
            rows.append(SparseRow(
                row.state,
                row.reads + ((t["K_SIGN"], sign),),
                row.action,
            ))
    kmag_data = fabric.layout("K_MAG").tape_start
    rows.append(_direct(
        K_DEC_AFTER_POS, DISPATCH,
        reads={kmag_data: BOTTOM},
        writes={t["K_SIGN"]: SIGN_ZERO},
    ))
    rows.append(_direct(
        K_DEC_AFTER_POS, DISPATCH,
        reads={kmag_data: ONE},
        writes={t["K_SIGN"]: SIGN_POS},
    ))
    rows.append(_direct(
        K_DEC_SET_NEG, DISPATCH,
        writes={t["K_SIGN"]: SIGN_NEG},
    ))
    rows.append(_direct(K_DEC_DONE, DISPATCH))

    # The literal 16-entry SG controller.  Unavailable signals remain in the
    # key but are harmless finite redundancies, matching sg_controller.py.
    for (known, b_ok, bp_ok, large), action in sg_control_table().items():
        rows.append(_direct(
            DISPATCH,
            CASE_ENTRY[action.case],
            reads={
                t["SECOND"]: KNOWN if known else UNKNOWN,
                t["B_OK"]: YES if b_ok else NO,
                t["BP_OK"]: YES if bp_ok else NO,
                t["GAP_LARGE"]: YES if large else NO,
            },
            writes={t["CASE"]: str(action.case.value)},
        ))

    names = {
        READ0: "READ0", READ1: "READ1", CAPTURE0: "CAPTURE0", CAPTURE1: "CAPTURE1",
        APPEND_B: "APPEND_B", APPEND_BP: "APPEND_BP", APPEND_LB: "APPEND_LB",
        APPEND_LBP: "APPEND_LBP", APPEND_BG: "APPEND_BG", APPEND_BGL: "APPEND_BGL",
        ADVANCE_LB: "ADVANCE_LB", COMPARE_LB: "COMPARE_LB",
        ADVANCE_LBP: "ADVANCE_LBP", COMPARE_LBP: "COMPARE_LBP",
        ADVANCE_BGL: "ADVANCE_BGL", ADVANCE_B: "ADVANCE_B",
        ADVANCE_BP: "ADVANCE_BP", ADVANCE_BG: "ADVANCE_BG",
        MAYBE_DEC_K: "MAYBE_DEC_K", K_DEC_DISPATCH: "K_DEC_DISPATCH",
        K_DEC_AFTER_POS: "K_DEC_AFTER_POS", K_DEC_SET_NEG: "K_DEC_SET_NEG",
        K_DEC_DONE: "K_DEC_DONE", DISPATCH: "DISPATCH", ERROR: "ERROR",
        **{state: f"CASE_{case.value}" for case, state in CASE_ENTRY.items()},
    }
    return DispatcherBuild(tuple(rows), names)


def dispatcher_row_count(fabric: SparseRegisteredFabric) -> int:
    return len(build_dispatcher_rows(fabric).rows)
