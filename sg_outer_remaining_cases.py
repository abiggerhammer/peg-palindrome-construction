"""Ordinary-table bodies for SG cases 2, 3, 5, and 6.

This module is built in deliberately small, testable layers.  The first layer
implemented here is the shared RECOVER subprogram used by cases 2 and 6.  It
contains no host-level cursor arithmetic or checkpoint result decoding: active
suffixes are copied cell by cell into fresh checkpoint source epochs, the
registered checkpoint table is run, and its unary result axes are scanned while
moving the six retained history cursors and ordinary unary counters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Mapping

import checkpoint_ordinary_tm as cp
import checkpoint_reusable_tm as reusable
from sg_outer_constant_cases import OUT_CHECK, C4_FRESH_K
from sg_outer_dispatcher_table import (
    CASE_ENTRY,
    KNOWN,
    LEFT_AFTER1,
    LEFT_AFTER2,
    LEFT_AT,
    LEFT_EXACT,
    MID_AFTER,
    MID_AT,
    MID_BEFORE,
    NO,
    SIGN_NEG,
    SIGN_POS,
    SIGN_ZERO,
    UNKNOWN,
    YES,
    _counter_call_rows,
    _direct,
    _history_adapter,
    _history_call_rows,
    _history_has_right_rows,
)
from sg_zero_ratio import UpdateCase
from sparse_registered_linker import (
    JsonSparseAdapter,
    SparseAction,
    SparseRegisteredFabric,
    SparseRow,
)
from unary_counter_ordinary_tm import BOTTOM, ONE
from construction_constants import background_clock_shape, background_steps_per_input




def _checkpoint_result_ready_id(adapter: JsonSparseAdapter) -> int:
    value = adapter.result_ready_state_id
    if value is None:
        raise AssertionError("checkpoint table lacks result_ready_state")
    return int(value)


def _checkpoint_clean_ready_id(adapter: JsonSparseAdapter) -> int:
    return int(adapter.clean_ready_state_id)


def _checkpoint_retire_entry_id(adapter: JsonSparseAdapter) -> int:
    result_ready = _checkpoint_result_ready_id(adapter)
    rows = adapter.rows_for_state(result_ready)
    if len(rows) != 1:
        raise AssertionError((result_ready, len(rows)))
    return int(rows[0].next_state_id)


@dataclass(frozen=True)
class DeferredCheckpointCall:
    state: int
    continuation: int
    mode: str  # "single_step" or "run_to_result"


@dataclass(frozen=True)
class RemainingCaseBuild:
    rows: tuple[SparseRow, ...]
    state_names: Mapping[int, str]
    deferred_checkpoint_calls: tuple[DeferredCheckpointCall, ...] = ()

    def iter_rows(self, fabric: SparseRegisteredFabric) -> Iterator[SparseRow]:
        yield from self.rows
        for spec in self.deferred_checkpoint_calls:
            if spec.mode == "run_to_result":
                layout = fabric.layout("CHECKPOINT")
                adapter = layout.adapter
                allowed = tuple(
                    q for q in range(adapter.state_count)
                    if q not in adapter.ready_state_ids
                    and q not in adapter.error_state_ids
                )
                yield from fabric.call_rows(
                    caller_state=spec.state,
                    component="CHECKPOINT",
                    continuation_state=spec.continuation,
                    entry_transform=lambda q: q,
                    allowed_local_states=allowed,
                )
            elif spec.mode == "single_step":
                yield from _checkpoint_single_step_row_iterator(
                    fabric, spec.state, spec.continuation
                )
            else:
                raise ValueError(spec.mode)


class _Builder:
    def __init__(self, fabric: SparseRegisteredFabric, start: int = 200) -> None:
        self.fabric = fabric
        self.rows: list[SparseRow] = []
        self.names: dict[int, str] = {}
        self.deferred_checkpoint_calls: list[DeferredCheckpointCall] = []
        self.next_state = start

    def state(self, name: str) -> int:
        q = self.next_state
        self.next_state += 1
        if q >= 262144:
            raise OverflowError(q)
        self.names[q] = name
        return q

    def direct(self, state: int, nxt: int, **kwargs) -> None:
        self.rows.append(_direct(state, nxt, **kwargs))

    def history_call(self, state: int, name: str, command: str, nxt: int) -> None:
        self.rows.extend(_history_call_rows(
            self.fabric, caller=state, name=name, command=command,
            continuation=nxt,
        ))

    def counter_call(self, state: int, name: str, command: str, nxt: int) -> None:
        self.rows.extend(_counter_call_rows(
            self.fabric, caller=state, name=name, command=command,
            continuation=nxt,
        ))

    def guarded_history_call(
        self,
        state: int,
        name: str,
        command: str,
        nxt: int,
        *,
        reads: Mapping[int, object] = {},
        writes: Mapping[int, object] = {},
    ) -> None:
        for row in _history_call_rows(
            self.fabric, caller=state, name=name, command=command,
            continuation=nxt,
        ):
            self.rows.append(SparseRow(
                row.state,
                row.reads + tuple(sorted(reads.items())),
                SparseAction(
                    row.action.next_state,
                    row.action.writes + tuple(sorted(writes.items())),
                    row.action.moves,
                ),
            ))

    # ---------------------------------------------------------------
    # History relation primitives.

    def mid_left(self, state: int, name: str, rel_name: str, nxt: int) -> None:
        t = self.fabric.extra_tapes
        rel = t[rel_name]
        self.direct(state, nxt, reads={rel: MID_AFTER}, writes={rel: MID_AT})
        self.direct(state, nxt, reads={rel: MID_AT}, writes={rel: MID_BEFORE})
        self.guarded_history_call(
            state, name, "LEFT", nxt,
            reads={rel: MID_BEFORE},
        )

    def left_left(self, state: int, name: str, rel_name: str, nxt: int) -> None:
        t = self.fabric.extra_tapes
        rel = t[rel_name]
        self.direct(state, nxt, reads={rel: LEFT_AFTER2}, writes={rel: LEFT_AFTER1})
        self.direct(state, nxt, reads={rel: LEFT_AFTER1}, writes={rel: LEFT_AT})
        self.direct(state, nxt, reads={rel: LEFT_AT}, writes={rel: LEFT_EXACT})
        self.guarded_history_call(
            state, name, "LEFT", nxt,
            reads={rel: LEFT_EXACT},
        )

    def mid_right(self, state: int, name: str, rel_name: str, nxt: int) -> None:
        t = self.fabric.extra_tapes
        rel = t[rel_name]
        # AT -> AFTER is a finite relation update.
        self.direct(state, nxt, reads={rel: MID_AT}, writes={rel: MID_AFTER})
        # BEFORE branches on whether a real history cell remains to the right.
        move = self.state(f"{self.names.get(state, state)}_{name}_MID_RIGHT_MOVE")
        for row in _history_has_right_rows(
            self.fabric, state=state, component=name,
            if_yes=move, if_no=nxt,
        ):
            if row.action.next_state == nxt:
                self.rows.append(SparseRow(
                    row.state,
                    row.reads + ((rel, MID_BEFORE),),
                    SparseAction(nxt, row.action.writes + ((rel, MID_AT),), row.action.moves),
                ))
            else:
                self.rows.append(SparseRow(
                    row.state,
                    row.reads + ((rel, MID_BEFORE),),
                    row.action,
                ))
        self.guarded_history_call(
            move, name, "RIGHT", nxt,
            reads={rel: MID_BEFORE},
        )

    def left_right(self, state: int, name: str, rel_name: str, nxt: int) -> None:
        t = self.fabric.extra_tapes
        rel = t[rel_name]
        self.direct(state, nxt, reads={rel: LEFT_AT}, writes={rel: LEFT_AFTER1})
        self.direct(state, nxt, reads={rel: LEFT_AFTER1}, writes={rel: LEFT_AFTER2})
        move = self.state(f"{self.names.get(state, state)}_{name}_LEFT_RIGHT_MOVE")
        for row in _history_has_right_rows(
            self.fabric, state=state, component=name,
            if_yes=move, if_no=nxt,
        ):
            if row.action.next_state == nxt:
                self.rows.append(SparseRow(
                    row.state,
                    row.reads + ((rel, LEFT_EXACT),),
                    SparseAction(nxt, row.action.writes + ((rel, LEFT_AT),), row.action.moves),
                ))
            else:
                self.rows.append(SparseRow(
                    row.state,
                    row.reads + ((rel, LEFT_EXACT),),
                    row.action,
                ))
        self.guarded_history_call(
            move, name, "RIGHT", nxt,
            reads={rel: LEFT_EXACT},
        )

    # ---------------------------------------------------------------
    # Counter and checkpoint helpers.

    def counter_data_tape(self, name: str) -> int:
        return self.fabric.layout(name).tape_start

    def fresh_counter(self, state: int, name: str, nxt: int) -> None:
        self.counter_call(state, name, "FRESH_ZERO", nxt)

    def copy_history_current_to_tapes(
        self, state: int, history: str, local_tapes: tuple[int, ...], nxt: int,
        *, moves: Mapping[int, int] = {},
    ) -> None:
        layout = self.fabric.layout(history)
        adapter = _history_adapter(self.fabric, history)
        register = layout.register_tape
        cp_layout = self.fabric.layout("CHECKPOINT")
        for qid in adapter.ready_state_ids:
            core = adapter.id_to_state[qid]
            if core.current not in ("0", "1"):
                continue
            writes = {
                cp_layout.tape_start + local: core.current for local in local_tapes
            }
            self.direct(
                state, nxt,
                reads={register: layout.qsymbol(qid)},
                writes=writes,
                moves={cp_layout.tape_start + local: amount for local, amount in moves.items()},
            )

    def checkpoint_request_call(self, state: int, nxt: int) -> None:
        layout = self.fabric.layout("CHECKPOINT")
        adapter = layout.adapter
        if not isinstance(adapter, JsonSparseAdapter):
            raise TypeError(type(adapter))
        ready = _checkpoint_clean_ready_id(adapter)
        start_rows = [r for r in adapter.rows_for_state(ready)]
        if len(start_rows) != 1:
            raise AssertionError((ready, len(start_rows)))
        start = start_rows[0]
        entry = start.next_state_id
        generated = self.fabric.call_rows(
            caller_state=state,
            component="CHECKPOINT",
            continuation_state=nxt,
            entry_transform=lambda _q: entry,
            allowed_local_states=(ready,),
        )
        control = layout.tape_start + reusable.CONTROL_TAPE
        for row in generated:
            self.rows.append(SparseRow(
                row.state,
                row.reads,
                SparseAction(
                    row.action.next_state,
                    row.action.writes + ((control, cp.BLANK),),
                    row.action.moves,
                ),
            ))

    # ---------------------------------------------------------------
    # Signed K operations.

    def signed_inc(self, state: int, nxt: int, label: str) -> None:
        t = self.fabric.extra_tapes
        after_neg = self.state(f"{label}_AFTER_NEG_DEC")
        set_pos = self.state(f"{label}_SET_POS")
        self.guarded_counter_call(state, "K_MAG", "INC", nxt,
                                  reads={t["K_SIGN"]: SIGN_POS})
        self.guarded_counter_call(state, "K_MAG", "INC", set_pos,
                                  reads={t["K_SIGN"]: SIGN_ZERO})
        self.guarded_counter_call(state, "K_MAG", "DEC", after_neg,
                                  reads={t["K_SIGN"]: SIGN_NEG})
        self.direct(set_pos, nxt, writes={t["K_SIGN"]: SIGN_POS})
        data = self.counter_data_tape("K_MAG")
        self.direct(after_neg, nxt, reads={data: BOTTOM}, writes={t["K_SIGN"]: SIGN_ZERO})
        self.direct(after_neg, nxt, reads={data: ONE}, writes={t["K_SIGN"]: SIGN_NEG})

    def signed_dec(self, state: int, nxt: int, label: str) -> None:
        t = self.fabric.extra_tapes
        after_pos = self.state(f"{label}_AFTER_POS_DEC")
        set_neg = self.state(f"{label}_SET_NEG")
        self.guarded_counter_call(state, "K_MAG", "INC", nxt,
                                  reads={t["K_SIGN"]: SIGN_NEG})
        self.guarded_counter_call(state, "K_MAG", "INC", set_neg,
                                  reads={t["K_SIGN"]: SIGN_ZERO})
        self.guarded_counter_call(state, "K_MAG", "DEC", after_pos,
                                  reads={t["K_SIGN"]: SIGN_POS})
        self.direct(set_neg, nxt, writes={t["K_SIGN"]: SIGN_NEG})
        data = self.counter_data_tape("K_MAG")
        self.direct(after_pos, nxt, reads={data: BOTTOM}, writes={t["K_SIGN"]: SIGN_ZERO})
        self.direct(after_pos, nxt, reads={data: ONE}, writes={t["K_SIGN"]: SIGN_POS})

    def guarded_counter_call(
        self, state: int, name: str, command: str, nxt: int,
        *, reads: Mapping[int, object] = {}, writes: Mapping[int, object] = {},
    ) -> None:
        for row in _counter_call_rows(
            self.fabric, caller=state, name=name, command=command,
            continuation=nxt,
        ):
            self.rows.append(SparseRow(
                row.state,
                row.reads + tuple(sorted(reads.items())),
                SparseAction(
                    row.action.next_state,
                    row.action.writes + tuple(sorted(writes.items())),
                    row.action.moves,
                ),
            ))


# ---------------------------------------------------------------------------
# Shared RECOVER program.


def _emit_align_second(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    gap = b.counter_data_tape("GAP")
    loop = b.state(f"{prefix}_ALIGN_LOOP")
    bp_left = b.state(f"{prefix}_ALIGN_BP_LEFT")
    lbp_left1 = b.state(f"{prefix}_ALIGN_LBP_LEFT1")
    lbp_left2 = b.state(f"{prefix}_ALIGN_LBP_LEFT2")
    dec = b.state(f"{prefix}_ALIGN_GAP_DEC")
    fresh_k = b.state(f"{prefix}_ALIGN_FRESH_K")
    b.direct(entry, loop)
    b.direct(loop, fresh_k, reads={gap: BOTTOM})
    b.direct(loop, bp_left, reads={gap: ONE})
    b.mid_left(bp_left, "BP", "BP_REL", lbp_left1)
    b.left_left(lbp_left1, "LBP", "LBP_REL", lbp_left2)
    b.left_left(lbp_left2, "LBP", "LBP_REL", dec)
    b.counter_call(dec, "GAP", "DEC", loop)
    b.counter_call(fresh_k, "K_MAG", "FRESH_ZERO", nxt)
    # Set finite sign in the call row's continuation state.
    t = b.fabric.extra_tapes
    # The continuation itself performs the sign write in one direct row so the
    # caller can be shared by case 6 as well.
    sign_done = b.state(f"{prefix}_ALIGN_SIGN_ZERO")
    # Redirect the just-created fresh call from nxt to sign_done is cumbersome;
    # instead insert a one-state shim by replacing the last call rows.
    count = len(b.fabric.layout("K_MAG").adapter.ready_state_ids)
    call_rows = b.rows[-count:]
    del b.rows[-count:]
    for row in call_rows:
        b.rows.append(SparseRow(row.state, row.reads, SparseAction(
            row.action.next_state,
            tuple((tape, val) for tape, val in row.action.writes if tape != t["K_SIGN"]),
            row.action.moves,
        )))
    # The call still returns to nxt; write sign as part of the call action.
    for i in range(len(b.rows) - count, len(b.rows)):
        row = b.rows[i]
        b.rows[i] = SparseRow(row.state, row.reads, SparseAction(
            row.action.next_state,
            row.action.writes + ((t["K_SIGN"], SIGN_ZERO),),
            row.action.moves,
        ))
    del b.names[sign_done]


def _emit_fresh_checkpoint_sources(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    layout = b.fabric.layout("CHECKPOINT")
    gf = layout.tape_start + cp.SRC_FWD
    gr = layout.tape_start + cp.SRC_REV
    gf2 = layout.tape_start + cp.SRC_FWD2
    move = b.state(f"{prefix}_SRC_FRESH_MOVE")
    write = b.state(f"{prefix}_SRC_FRESH_WRITE")
    # READY invariant: FWD/FWD2 scan END, REV scans the current sentinel.
    b.direct(entry, move, reads={gf: cp.END, gf2: cp.END, gr: cp.SENTINEL},
             moves={gf: 1, gf2: 1, gr: -1})
    b.direct(move, write, reads={gf: cp.BLANK, gf2: cp.BLANK, gr: cp.BLANK},
             writes={gf: cp.SENTINEL, gf2: cp.SENTINEL, gr: cp.END})
    b.direct(write, nxt, moves={gf: 1, gf2: 1})


def _emit_copy_active_suffix(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    layout = b.fabric.layout("CHECKPOINT")
    gf = layout.tape_start + cp.SRC_FWD
    gr = layout.tape_start + cp.SRC_REV
    gf2 = layout.tape_start + cp.SRC_FWD2
    length = b.counter_data_tape("LENGTH")
    restore = b.counter_data_tape("RESTORE")

    fresh_len = b.state(f"{prefix}_COPY_FRESH_LENGTH")
    fresh_restore = b.state(f"{prefix}_COPY_FRESH_RESTORE")
    write_fwd = b.state(f"{prefix}_COPY_WRITE_FWD")
    inc_len = b.state(f"{prefix}_COPY_INC_LENGTH")
    inc_restore = b.state(f"{prefix}_COPY_INC_RESTORE")
    has_right = b.state(f"{prefix}_COPY_HAS_RIGHT")
    move_b = b.state(f"{prefix}_COPY_MOVE_B")
    finish_fwd = b.state(f"{prefix}_COPY_FINISH_FWD")
    rev_move = b.state(f"{prefix}_REV_MOVE")
    rev_write = b.state(f"{prefix}_REV_WRITE")
    rev_dec = b.state(f"{prefix}_REV_DEC")
    rev_after = b.state(f"{prefix}_REV_AFTER_DEC")
    rev_b_left = b.state(f"{prefix}_REV_B_LEFT")
    rev_sentinel_move = b.state(f"{prefix}_REV_SENTINEL_MOVE")
    rev_sentinel_write = b.state(f"{prefix}_REV_SENTINEL_WRITE")
    rev_to_end = b.state(f"{prefix}_REV_TO_END")
    rev_step_left = b.state(f"{prefix}_REV_STEP_LEFT")
    fwd0_rewind = b.state(f"{prefix}_FWD0_REWIND")
    fwd1_rewind = b.state(f"{prefix}_FWD1_REWIND")

    b.counter_call(entry, "LENGTH", "FRESH_ZERO", fresh_len)
    b.counter_call(fresh_len, "RESTORE", "FRESH_ZERO", write_fwd)
    b.copy_history_current_to_tapes(
        write_fwd, "B", (cp.SRC_FWD, cp.SRC_FWD2), inc_len,
        moves={cp.SRC_FWD: 1, cp.SRC_FWD2: 1},
    )
    b.counter_call(inc_len, "LENGTH", "INC", inc_restore)
    b.counter_call(inc_restore, "RESTORE", "INC", has_right)
    for row in _history_has_right_rows(
        b.fabric, state=has_right, component="B",
        if_yes=move_b, if_no=finish_fwd,
    ):
        b.rows.append(row)
    b.history_call(move_b, "B", "RIGHT", write_fwd)
    b.direct(finish_fwd, rev_move, writes={gf: cp.END, gf2: cp.END})

    # Build the reverse source epoch from right to left while restoring B.
    b.direct(rev_move, rev_write, moves={gr: -1})
    b.copy_history_current_to_tapes(rev_write, "B", (cp.SRC_REV,), rev_dec)
    b.counter_call(rev_dec, "RESTORE", "DEC", rev_after)
    b.direct(rev_after, rev_sentinel_move, reads={restore: BOTTOM})
    b.direct(rev_after, rev_b_left, reads={restore: ONE})
    b.history_call(rev_b_left, "B", "LEFT", rev_move)
    b.direct(rev_sentinel_move, rev_sentinel_write, moves={gr: -1})
    b.direct(rev_sentinel_write, rev_to_end, reads={gr: cp.BLANK}, writes={gr: cp.SENTINEL})
    b.direct(rev_to_end, rev_step_left, reads={gr: cp.END})
    b.direct(rev_to_end, rev_to_end,
             reads={gr: frozenset((cp.SENTINEL, "0", "1"))}, moves={gr: 1})
    b.direct(rev_step_left, fwd0_rewind, moves={gr: -1})
    b.direct(fwd0_rewind, fwd1_rewind, reads={gf: cp.SENTINEL}, moves={gf: 1})
    b.direct(fwd0_rewind, fwd0_rewind,
             reads={gf: frozenset(("0", "1", cp.END))}, moves={gf: -1})
    b.direct(fwd1_rewind, nxt, reads={gf2: cp.SENTINEL}, moves={gf2: 1})
    b.direct(fwd1_rewind, fwd1_rewind,
             reads={gf2: frozenset(("0", "1", cp.END))}, moves={gf2: -1})


def _emit_copy_counter_preserving(
    b: _Builder, entry: int, source: str, target: str, nxt: int, prefix: str,
) -> None:
    source_tape = b.counter_data_tape(source)
    fresh = b.state(f"{prefix}_FRESH_{target}")
    loop = b.state(f"{prefix}_COPY_LOOP")
    inc = b.state(f"{prefix}_COPY_INC")
    restore_move = b.state(f"{prefix}_RESTORE_MOVE")
    restore_check = b.state(f"{prefix}_RESTORE_CHECK")
    restore_finish = b.state(f"{prefix}_RESTORE_FINISH")
    b.counter_call(entry, target, "FRESH_ZERO", loop)
    b.direct(loop, restore_move, reads={source_tape: BOTTOM})
    b.direct(loop, inc, reads={source_tape: ONE}, moves={source_tape: -1})
    b.counter_call(inc, target, "INC", loop)
    b.direct(restore_move, restore_check, moves={source_tape: 1})
    b.direct(restore_check, restore_move, reads={source_tape: ONE})
    b.direct(restore_check, restore_finish, reads={source_tape: cp.BLANK})
    b.direct(restore_finish, nxt, moves={source_tape: -1})
    del b.names[fresh]


def _emit_rewind_axis(b: _Builder, entry: int, local_tape: int, nxt: int, prefix: str) -> None:
    tape = b.fabric.layout("CHECKPOINT").tape_start + local_tape
    b.direct(entry, nxt, reads={tape: cp.MARK})
    b.direct(entry, entry,
             reads={tape: frozenset(set(cp.tape_alphabets()[local_tape]) - {cp.MARK})},
             moves={tape: -1})


def _emit_bp_right_unit(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    s1 = b.state(f"{prefix}_BP_RIGHT")
    s2 = b.state(f"{prefix}_LBP_RIGHT1")
    s3 = b.state(f"{prefix}_LBP_RIGHT2")
    b.direct(entry, s1)
    b.mid_right(s1, "BP", "BP_REL", s2)
    b.left_right(s2, "LBP", "LBP_REL", s3)
    b.left_right(s3, "LBP", "LBP_REL", nxt)


def _emit_b_right_unit(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    states = [b.state(f"{prefix}_{name}") for name in (
        "B_RIGHT", "BG_RIGHT", "LB_RIGHT1", "LB_RIGHT2", "BGL_RIGHT1", "BGL_RIGHT2"
    )]
    b.direct(entry, states[0])
    b.mid_right(states[0], "B", "B_REL", states[1])
    b.mid_right(states[1], "BG", "BG_REL", states[2])
    b.left_right(states[2], "LB", "LB_REL", states[3])
    b.left_right(states[3], "LB", "LB_REL", states[4])
    b.left_right(states[4], "BGL", "BGL_REL", states[5])
    b.left_right(states[5], "BGL", "BGL_REL", nxt)


def _emit_scan_out2(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    axis = b.fabric.layout("CHECKPOINT").tape_start + cp.OUT2_TAPE
    scan = b.counter_data_tape("SCAN")
    rewound = b.state(f"{prefix}_OUT2_REWOUND")
    loop = b.state(f"{prefix}_OUT2_LOOP")
    move_axis = b.state(f"{prefix}_OUT2_MOVE_AXIS")
    advance = b.state(f"{prefix}_OUT2_ADVANCE")
    gap_inc = b.state(f"{prefix}_OUT2_GAP_INC")
    scan_dec = b.state(f"{prefix}_OUT2_SCAN_DEC")
    inspect = b.state(f"{prefix}_OUT2_INSPECT")
    automatic = b.state(f"{prefix}_OUT2_AUTOMATIC")
    auto_gap = b.state(f"{prefix}_OUT2_AUTO_GAP")
    _emit_copy_counter_preserving(b, entry, "LENGTH", "SCAN", rewound, f"{prefix}_LEN")
    _emit_rewind_axis(b, rewound, cp.OUT2_TAPE, loop, f"{prefix}_RW")
    b.direct(loop, automatic, reads={scan: BOTTOM})
    b.direct(loop, move_axis, reads={scan: ONE})
    b.direct(move_axis, advance, moves={axis: 1})
    _emit_bp_right_unit(b, advance, gap_inc, f"{prefix}_UNIT")
    b.counter_call(gap_inc, "GAP", "INC", scan_dec)
    b.counter_call(scan_dec, "SCAN", "DEC", inspect)
    b.direct(inspect, nxt, reads={axis: cp.GAP})
    b.direct(inspect, loop, reads={axis: cp.BLANK})
    _emit_bp_right_unit(b, automatic, auto_gap, f"{prefix}_AUTO_UNIT")
    b.counter_call(auto_gap, "GAP", "INC", nxt)


def _emit_scan_out1(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    axis = b.fabric.layout("CHECKPOINT").tape_start + cp.OUT1_TAPE
    scan = b.counter_data_tape("SCAN")
    rewound = b.state(f"{prefix}_OUT1_REWOUND")
    loop = b.state(f"{prefix}_OUT1_LOOP")
    move_axis = b.state(f"{prefix}_OUT1_MOVE_AXIS")
    advance = b.state(f"{prefix}_OUT1_ADVANCE")
    gap_dec = b.state(f"{prefix}_OUT1_GAP_DEC")
    scan_dec = b.state(f"{prefix}_OUT1_SCAN_DEC")
    inspect = b.state(f"{prefix}_OUT1_INSPECT")
    _emit_copy_counter_preserving(b, entry, "LENGTH", "SCAN", rewound, f"{prefix}_LEN")
    _emit_rewind_axis(b, rewound, cp.OUT1_TAPE, loop, f"{prefix}_RW")
    b.direct(loop, move_axis, reads={scan: ONE})
    b.direct(move_axis, advance, moves={axis: 1})
    _emit_b_right_unit(b, advance, gap_dec, f"{prefix}_UNIT")
    b.counter_call(gap_dec, "GAP", "DEC", scan_dec)
    b.counter_call(scan_dec, "SCAN", "DEC", inspect)
    b.direct(inspect, nxt, reads={axis: cp.GAP})
    b.direct(inspect, loop, reads={axis: cp.BLANK, scan: ONE})
    # OUT1 must exist within the active length.  No row for blank with SCAN=0.


def _emit_recompute_k(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    t = b.fabric.extra_tapes
    gap = b.counter_data_tape("GAP")
    scan = b.counter_data_tape("SCAN")  # n-d1 remains after OUT1 discovery.
    fresh = b.state(f"{prefix}_K_FRESH")
    gap_loop = b.state(f"{prefix}_GAP_LOOP")
    gap_ops = [b.state(f"{prefix}_GAP_INC_{i}") for i in range(16)]
    gap_restore_move = b.state(f"{prefix}_GAP_RESTORE_MOVE")
    gap_restore_check = b.state(f"{prefix}_GAP_RESTORE_CHECK")
    gap_restore_finish = b.state(f"{prefix}_GAP_RESTORE_FINISH")
    scan_loop = b.state(f"{prefix}_SCAN_SUB_LOOP")
    scan_dec = b.state(f"{prefix}_SCAN_DEC")

    b.counter_call(entry, "K_MAG", "FRESH_ZERO", fresh)
    b.direct(fresh, gap_loop, writes={t["K_SIGN"]: SIGN_ZERO})
    b.direct(gap_loop, gap_restore_move, reads={gap: BOTTOM})
    b.direct(gap_loop, gap_ops[0], reads={gap: ONE}, moves={gap: -1})
    for i, state in enumerate(gap_ops):
        next_state = gap_loop if i == 15 else gap_ops[i + 1]
        b.signed_inc(state, next_state, f"{prefix}_ADD_{i}")
    b.direct(gap_restore_move, gap_restore_check, moves={gap: 1})
    b.direct(gap_restore_check, gap_restore_move, reads={gap: ONE})
    b.direct(gap_restore_check, gap_restore_finish, reads={gap: cp.BLANK})
    b.direct(gap_restore_finish, scan_loop, moves={gap: -1})
    b.direct(scan_loop, nxt, reads={scan: BOTTOM})
    sub = b.state(f"{prefix}_SCAN_SIGNED_DEC")
    b.direct(scan_loop, sub, reads={scan: ONE})
    b.signed_dec(sub, scan_dec, f"{prefix}_SUB")
    b.counter_call(scan_dec, "SCAN", "DEC", scan_loop)


def _emit_checkpoint_retire_call(
    b: _Builder, entry: int, nxt: int, prefix: str,
) -> None:
    """Consume RESULT_READY and run producer-paid cleanup to clean READY."""
    del prefix
    layout = b.fabric.layout("CHECKPOINT")
    adapter = layout.adapter
    if not isinstance(adapter, JsonSparseAdapter):
        raise TypeError(type(adapter))
    result_ready = _checkpoint_result_ready_id(adapter)
    retire_entry = _checkpoint_retire_entry_id(adapter)
    generated = b.fabric.call_rows(
        caller_state=entry,
        component="CHECKPOINT",
        continuation_state=nxt,
        entry_transform=lambda _q: retire_entry,
        allowed_local_states=(result_ready,),
    )
    control = layout.tape_start + reusable.CONTROL_TAPE
    for row in generated:
        b.rows.append(SparseRow(
            row.state,
            row.reads,
            SparseAction(
                row.action.next_state,
                row.action.writes + ((control, cp.BLANK),),
                row.action.moves,
            ),
        ))


def _emit_recover(
    b: _Builder, entry: int, nxt: int, prefix: str, *, align: bool,
) -> None:
    aligned = b.state(f"{prefix}_ALIGNED")
    source_fresh = b.state(f"{prefix}_SOURCE_FRESH")
    copied = b.state(f"{prefix}_COPIED")
    checkpoint_done = b.state(f"{prefix}_CHECKPOINT_DONE")
    out2_done = b.state(f"{prefix}_OUT2_DONE")
    out1_done = b.state(f"{prefix}_OUT1_DONE")
    cleanup_done = b.state(f"{prefix}_CLEANUP_DONE")
    if align:
        _emit_align_second(b, entry, aligned, prefix)
    else:
        b.direct(entry, aligned)
    _emit_fresh_checkpoint_sources(b, aligned, source_fresh, prefix)
    _emit_copy_active_suffix(b, source_fresh, copied, prefix)
    b.checkpoint_request_call(copied, checkpoint_done)
    _emit_scan_out2(b, checkpoint_done, out2_done, prefix)
    _emit_scan_out1(b, out2_done, out1_done, prefix)
    _emit_checkpoint_retire_call(b, out1_done, cleanup_done, f"{prefix}_RETIRE")
    _emit_recompute_k(b, cleanup_done, nxt, prefix)



def _emit_promote_second(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    """Move the live B/BG groups to B' while recording the old gap."""
    gap = b.counter_data_tape("GAP")
    fresh_radius = b.state(f"{prefix}_FRESH_RADIUS")
    loop = b.state(f"{prefix}_LOOP")
    move = b.state(f"{prefix}_MOVE_UNIT")
    gap_dec = b.state(f"{prefix}_GAP_DEC")
    radius_inc = b.state(f"{prefix}_RADIUS_INC")
    b.counter_call(entry, "RADIUS", "FRESH_ZERO", fresh_radius)
    b.direct(fresh_radius, loop)
    b.direct(loop, nxt, reads={gap: BOTTOM})
    b.direct(loop, move, reads={gap: ONE})
    _emit_b_right_unit(b, move, gap_dec, f"{prefix}_UNIT")
    b.counter_call(gap_dec, "GAP", "DEC", radius_inc)
    b.counter_call(radius_inc, "RADIUS", "INC", loop)


def _emit_counter_multiple(
    b: _Builder, entry: int, source: str, target: str, factor: int,
    nxt: int, prefix: str,
) -> None:
    source_tape = b.counter_data_tape(source)
    loop = b.state(f"{prefix}_LOOP")
    ops = [b.state(f"{prefix}_INC_{i}") for i in range(factor)]
    restore_move = b.state(f"{prefix}_RESTORE_MOVE")
    restore_check = b.state(f"{prefix}_RESTORE_CHECK")
    restore_finish = b.state(f"{prefix}_RESTORE_FINISH")
    b.counter_call(entry, target, "FRESH_ZERO", loop)
    b.direct(loop, restore_move, reads={source_tape: BOTTOM})
    b.direct(loop, ops[0], reads={source_tape: ONE}, moves={source_tape: -1})
    for i, state in enumerate(ops):
        b.counter_call(state, target, "INC", loop if i == factor - 1 else ops[i + 1])
    b.direct(restore_move, restore_check, moves={source_tape: 1})
    b.direct(restore_check, restore_move, reads={source_tape: ONE})
    b.direct(restore_check, restore_finish, reads={source_tape: cp.BLANK})
    b.direct(restore_finish, nxt, moves={source_tape: -1})


def _emit_copy_active_suffix_quota(
    b: _Builder, entry: int, nxt: int, prefix: str,
) -> None:
    """Copy at most QUOTA active symbols and leave B restored."""
    layout = b.fabric.layout("CHECKPOINT")
    gf = layout.tape_start + cp.SRC_FWD
    gr = layout.tape_start + cp.SRC_REV
    gf2 = layout.tape_start + cp.SRC_FWD2
    restore = b.counter_data_tape("RESTORE")
    quota = b.counter_data_tape("QUOTA")

    fresh_len = b.state(f"{prefix}_FRESH_LENGTH")
    fresh_restore = b.state(f"{prefix}_FRESH_RESTORE")
    write_fwd = b.state(f"{prefix}_WRITE_FWD")
    inc_len = b.state(f"{prefix}_INC_LENGTH")
    inc_restore = b.state(f"{prefix}_INC_RESTORE")
    dec_quota = b.state(f"{prefix}_DEC_QUOTA")
    after_quota = b.state(f"{prefix}_AFTER_QUOTA")
    has_right = b.state(f"{prefix}_HAS_RIGHT")
    move_b = b.state(f"{prefix}_MOVE_B")
    finish_fwd = b.state(f"{prefix}_FINISH_FWD")
    rev_move = b.state(f"{prefix}_REV_MOVE")
    rev_write = b.state(f"{prefix}_REV_WRITE")
    rev_dec = b.state(f"{prefix}_REV_DEC")
    rev_after = b.state(f"{prefix}_REV_AFTER")
    rev_b_left = b.state(f"{prefix}_REV_B_LEFT")
    sent_move = b.state(f"{prefix}_SENT_MOVE")
    sent_write = b.state(f"{prefix}_SENT_WRITE")
    to_end = b.state(f"{prefix}_TO_END")
    step_left = b.state(f"{prefix}_STEP_LEFT")
    fwd0_rewind = b.state(f"{prefix}_FWD0_REWIND")
    fwd1_rewind = b.state(f"{prefix}_FWD1_REWIND")

    b.counter_call(entry, "LENGTH", "FRESH_ZERO", fresh_len)
    b.counter_call(fresh_len, "RESTORE", "FRESH_ZERO", write_fwd)
    b.copy_history_current_to_tapes(
        write_fwd, "B", (cp.SRC_FWD, cp.SRC_FWD2), inc_len,
        moves={cp.SRC_FWD: 1, cp.SRC_FWD2: 1},
    )
    b.counter_call(inc_len, "LENGTH", "INC", inc_restore)
    b.counter_call(inc_restore, "RESTORE", "INC", dec_quota)
    b.counter_call(dec_quota, "QUOTA", "DEC", after_quota)
    b.direct(after_quota, finish_fwd, reads={quota: BOTTOM})
    b.direct(after_quota, has_right, reads={quota: ONE})
    for row in _history_has_right_rows(
        b.fabric, state=has_right, component="B",
        if_yes=move_b, if_no=finish_fwd,
    ):
        b.rows.append(row)
    b.history_call(move_b, "B", "RIGHT", write_fwd)
    b.direct(finish_fwd, rev_move, writes={gf: cp.END, gf2: cp.END})
    b.direct(rev_move, rev_write, moves={gr: -1})
    b.copy_history_current_to_tapes(rev_write, "B", (cp.SRC_REV,), rev_dec)
    b.counter_call(rev_dec, "RESTORE", "DEC", rev_after)
    b.direct(rev_after, sent_move, reads={restore: BOTTOM})
    b.direct(rev_after, rev_b_left, reads={restore: ONE})
    b.history_call(rev_b_left, "B", "LEFT", rev_move)
    b.direct(sent_move, sent_write, moves={gr: -1})
    b.direct(sent_write, to_end, reads={gr: cp.BLANK}, writes={gr: cp.SENTINEL})
    b.direct(to_end, step_left, reads={gr: cp.END})
    b.direct(to_end, to_end,
             reads={gr: frozenset((cp.SENTINEL, "0", "1"))}, moves={gr: 1})
    b.direct(step_left, fwd0_rewind, moves={gr: -1})
    b.direct(fwd0_rewind, fwd1_rewind, reads={gf: cp.SENTINEL}, moves={gf: 1})
    b.direct(fwd0_rewind, fwd0_rewind,
             reads={gf: frozenset(("0", "1", cp.END))}, moves={gf: -1})
    b.direct(fwd1_rewind, nxt, reads={gf2: cp.SENTINEL}, moves={gf2: 1})
    b.direct(fwd1_rewind, fwd1_rewind,
             reads={gf2: frozenset(("0", "1", cp.END))}, moves={gf2: -1})


def _emit_scan_next_out1(
    b: _Builder, entry: int, limit: str, found: int, missing: int, prefix: str,
) -> None:
    axis = b.fabric.layout("CHECKPOINT").tape_start + cp.OUT1_TAPE
    scan = b.counter_data_tape("SCAN")
    rewound = b.state(f"{prefix}_REWOUND")
    loop = b.state(f"{prefix}_LOOP")
    move_axis = b.state(f"{prefix}_MOVE_AXIS")
    advance = b.state(f"{prefix}_ADVANCE")
    gap_inc = b.state(f"{prefix}_GAP_INC")
    scan_dec = b.state(f"{prefix}_SCAN_DEC")
    inspect = b.state(f"{prefix}_INSPECT")
    _emit_copy_counter_preserving(b, entry, limit, "SCAN", rewound, f"{prefix}_LIMIT")
    _emit_rewind_axis(b, rewound, cp.OUT1_TAPE, loop, f"{prefix}_RW")
    b.direct(loop, missing, reads={scan: BOTTOM})
    b.direct(loop, move_axis, reads={scan: ONE})
    b.direct(move_axis, advance, moves={axis: 1})
    _emit_bp_right_unit(b, advance, gap_inc, f"{prefix}_UNIT")
    b.counter_call(gap_inc, "GAP", "INC", scan_dec)
    b.counter_call(scan_dec, "SCAN", "DEC", inspect)
    b.direct(inspect, found, reads={axis: cp.GAP})
    b.direct(inspect, loop, reads={axis: cp.BLANK, scan: ONE})
    b.direct(inspect, missing, reads={axis: cp.BLANK, scan: BOTTOM})


def _emit_signed_adjust_by_counter(
    b: _Builder, entry: int, source: str, factor: int,
    *, increment: bool, nxt: int, prefix: str,
) -> None:
    tape = b.counter_data_tape(source)
    loop = b.state(f"{prefix}_LOOP")
    ops = [b.state(f"{prefix}_OP_{i}") for i in range(factor)]
    restore_move = b.state(f"{prefix}_RESTORE_MOVE")
    restore_check = b.state(f"{prefix}_RESTORE_CHECK")
    restore_finish = b.state(f"{prefix}_RESTORE_FINISH")
    b.direct(entry, loop)
    b.direct(loop, restore_move, reads={tape: BOTTOM})
    b.direct(loop, ops[0], reads={tape: ONE}, moves={tape: -1})
    for i, state in enumerate(ops):
        target = loop if i == factor - 1 else ops[i + 1]
        if increment:
            b.signed_inc(state, target, f"{prefix}_INC_{i}")
        else:
            b.signed_dec(state, target, f"{prefix}_DEC_{i}")
    b.direct(restore_move, restore_check, moves={tape: 1})
    b.direct(restore_check, restore_move, reads={tape: ONE})
    b.direct(restore_check, restore_finish, reads={tape: cp.BLANK})
    b.direct(restore_finish, nxt, moves={tape: -1})


def _emit_update_k_after_promotion(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    add_gap = b.state(f"{prefix}_ADD_GAP")
    _emit_signed_adjust_by_counter(
        b, entry, "RADIUS", 15, increment=False, nxt=add_gap,
        prefix=f"{prefix}_SUB_RADIUS",
    )
    _emit_signed_adjust_by_counter(
        b, add_gap, "GAP", 16, increment=True, nxt=nxt,
        prefix=f"{prefix}_ADD_GAP",
    )


def _emit_start_lazy(b: _Builder, entry: int) -> None:
    t = b.fabric.extra_tapes
    b.direct(entry, C4_FRESH_K, writes={
        t["SECOND"]: UNKNOWN,
        t["LAZY_MODE"]: "C",
        t["COPY_NEEDED"]: YES,
        t["K_SIGN"]: SIGN_ZERO,
    })


def _emit_case3(b: _Builder) -> None:
    t = b.fabric.extra_tapes
    promoted = b.state("C3_PROMOTED")
    at_end_install = b.state("C3_AT_END_INSTALL")
    at_end_gap = b.state("C3_AT_END_GAP")
    at_end_k = b.state("C3_AT_END_K")
    full_fresh = b.state("C3_FULL_SOURCE_FRESH")
    full_copied = b.state("C3_FULL_COPIED")
    full_done = b.state("C3_FULL_DONE")
    full_found = b.state("C3_FULL_FOUND")
    full_clean = b.state("C3_FULL_CLEAN")
    local_quota = b.state("C3_LOCAL_BUILD_QUOTA")
    local_fresh = b.state("C3_LOCAL_SOURCE_FRESH")
    local_copied = b.state("C3_LOCAL_COPIED")
    local_done = b.state("C3_LOCAL_DONE")
    local_found = b.state("C3_LOCAL_FOUND")
    local_missing = b.state("C3_LOCAL_MISSING")
    local_found_clean = b.state("C3_LOCAL_FOUND_CLEAN")
    local_missing_clean = b.state("C3_LOCAL_MISSING_CLEAN")
    local_aligned = b.state("C3_LOCAL_ALIGNED")
    k_done = b.state("C3_K_DONE")

    _emit_promote_second(
        b, CASE_ENTRY[UpdateCase.THREE_SECOND_SURVIVES], promoted, "C3_PROMOTE"
    )
    b.direct(promoted, at_end_install, reads={t["B_REL"]: MID_AT})
    b.direct(promoted, full_fresh,
             reads={t["B_REL"]: MID_BEFORE, t["GAP_LARGE"]: YES})
    b.direct(promoted, local_quota,
             reads={t["B_REL"]: MID_BEFORE, t["GAP_LARGE"]: NO})

    _emit_bp_right_unit(b, at_end_install, at_end_gap, "C3_AT_END_UNIT")
    b.counter_call(at_end_gap, "GAP", "INC", at_end_k)
    _emit_update_k_after_promotion(b, at_end_k, k_done, "C3_AT_END_K")

    _emit_fresh_checkpoint_sources(b, full_fresh, full_copied, "C3_FULL")
    full_launch = b.state("C3_FULL_LAUNCH")
    # full_copied currently denotes the start of copying, not completion.
    _emit_copy_active_suffix(b, full_copied, full_launch, "C3_FULL")
    b.checkpoint_request_call(full_launch, full_done)
    full_missing = b.state("C3_FULL_MISSING_ERROR")
    _emit_scan_next_out1(
        b, full_done, "LENGTH", full_found, full_missing, "C3_FULL_SCAN"
    )
    _emit_checkpoint_retire_call(b, full_found, full_clean, "C3_FULL_RETIRE")
    _emit_update_k_after_promotion(b, full_clean, k_done, "C3_FULL_K")

    _emit_counter_multiple(
        b, local_quota, "RADIUS", "QUOTA", 4, local_fresh, "C3_LOCAL_QUOTA"
    )
    local_copy = b.state("C3_LOCAL_COPY")
    _emit_fresh_checkpoint_sources(b, local_fresh, local_copy, "C3_LOCAL")
    local_launch = b.state("C3_LOCAL_LAUNCH")
    _emit_copy_active_suffix_quota(b, local_copy, local_launch, "C3_LOCAL")
    b.checkpoint_request_call(local_launch, local_done)
    _emit_scan_next_out1(
        b, local_done, "RADIUS", local_found, local_missing, "C3_LOCAL_SCAN"
    )
    _emit_checkpoint_retire_call(b, local_found, local_found_clean, "C3_LOCAL_FOUND_RETIRE")
    _emit_update_k_after_promotion(b, local_found_clean, k_done, "C3_LOCAL_K")
    _emit_checkpoint_retire_call(b, local_missing, local_missing_clean, "C3_LOCAL_MISSING_RETIRE")
    _emit_align_second(b, local_missing_clean, local_aligned, "C3_LOCAL_RETURN")
    _emit_start_lazy(b, local_aligned)

    b.direct(k_done, OUT_CHECK, writes={
        t["SECOND"]: KNOWN,
        t["LAZY_MODE"]: "N",
        t["COPY_NEEDED"]: NO,
        t["L33_PHASE"]: L33_IDLE,
    })



L33_IDLE = "I"
L33_PHASES = {
    "TO_END0": "T0", "TO_END1": "T1", "TO_END2": "T2",
    "LAUNCH_COPY": "LC", "LAUNCH_WRITE": "LW",
    "SYNC_CURRENT": "SC", "SYNC_LAG": "SL",
    "REWIND_FWD0": "W0", "REWIND_FWD1": "W1", "REV_LEFT": "WV",
    "REQUEST": "Q",
    "SEARCH": "S", "CLEANUP_LAUNCH": "CL", "CLEANUP_CATCH": "CC",
    "RESULT_FRESH": "RF", "RESULT_CAND": "RC",
    "RESULT_SOURCE": "RS", "RESULT_ADVANCE": "RA", "RESULT_CHECK": "RK",
    "BUILD_CANDIDATE": "BC", "RESTORE_CANDIDATE": "BR",
    "TARGET_REWIND": "TR", "TARGET_SUBTRACT": "TS", "TARGET_INSPECT": "TX",
    "CATCH_GOOD": "CG", "CATCH_BAD": "CB",
    "FOLLOW_GOOD": "FG", "FOLLOW_BAD": "FB",
    "RETURN_CANDIDATE": "CR",
}


def _emit_append_input_to_histories(
    b: _Builder, entry: int, names: tuple[str, ...], nxt: int, prefix: str,
) -> None:
    t = b.fabric.extra_tapes
    states = [entry] + [b.state(f"{prefix}_APPEND_{i}") for i in range(1, len(names))]
    for i, name in enumerate(names):
        caller = states[i]
        continuation = nxt if i + 1 == len(names) else states[i + 1]
        for bit, command in (("0", "APPEND0"), ("1", "APPEND1")):
            b.guarded_history_call(
                caller, name, command, continuation,
                reads={t["INPUT"]: bit},
            )


def _emit_append_history_current_to_l33(
    b: _Builder, entry: int, source: str, nxt: int, prefix: str,
) -> None:
    """Append the source history's current 0/1 to all three L33 histories."""
    source_layout = b.fabric.layout(source)
    source_adapter = _history_adapter(b.fabric, source)
    choose0 = b.state(f"{prefix}_CHOOSE0")
    choose1 = b.state(f"{prefix}_CHOOSE1")
    for qid in source_adapter.ready_state_ids:
        core = source_adapter.id_to_state[qid]
        if core.current == "0":
            target = choose0
        elif core.current == "1":
            target = choose1
        else:
            continue
        b.direct(
            entry, target,
            reads={source_layout.register_tape: source_layout.qsymbol(qid)},
        )
    for state, command in ((choose0, "APPEND0"), (choose1, "APPEND1")):
        s2 = b.state(f"{prefix}_{command}_LAG")
        s3 = b.state(f"{prefix}_{command}_COPY")
        b.history_call(state, "L33_CURRENT", command, s2)
        b.history_call(s2, "L33_LAG", command, s3)
        b.history_call(s3, "L33_COPY", command, nxt)


def _emit_fresh_empty_checkpoint_epoch(
    b: _Builder, entry: int, nxt: int, prefix: str,
) -> None:
    layout = b.fabric.layout("CHECKPOINT")
    gf = layout.tape_start + cp.SRC_FWD
    gr = layout.tape_start + cp.SRC_REV
    gf2 = layout.tape_start + cp.SRC_FWD2
    move1 = b.state(f"{prefix}_MOVE1")
    write1 = b.state(f"{prefix}_WRITE1")
    move2 = b.state(f"{prefix}_MOVE2")
    write2 = b.state(f"{prefix}_WRITE2")
    final = b.state(f"{prefix}_FINAL")
    b.direct(entry, move1, reads={gf: cp.END, gf2: cp.END, gr: cp.SENTINEL},
             moves={gf: 1, gf2: 1, gr: -1})
    b.direct(move1, write1, reads={gf: cp.BLANK, gf2: cp.BLANK, gr: cp.BLANK},
             writes={gf: cp.SENTINEL, gf2: cp.SENTINEL, gr: cp.END})
    b.direct(write1, move2, moves={gf: 1, gf2: 1, gr: -1})
    b.direct(move2, write2, reads={gf: cp.BLANK, gf2: cp.BLANK, gr: cp.BLANK},
             writes={gf: cp.END, gf2: cp.END, gr: cp.SENTINEL})
    b.direct(write2, final, moves={gr: 1})
    b.direct(final, nxt, reads={gf: cp.END, gf2: cp.END, gr: cp.END})


def _emit_clock_build(
    b: _Builder, entry: int, budget: int, nxt: int, prefix: str,
) -> None:
    """Build the outer factor of the fixed case-5 work clock.

    The proved production budget is represented as a near-square product:
    unary CLOCK stores the outer factor and CLOCK_PHASE stores the finite
    radix digit.  Tiny explicit regression budgets use radix one.
    """
    if budget <= 0:
        raise ValueError(budget)
    phase_tape = b.fabric.extra_tapes.get("CLOCK_PHASE")
    if phase_tape is None:
        raise AssertionError("fabric lacks CLOCK_PHASE")
    if budget == background_steps_per_input():
        outer, radix, effective = background_clock_shape()
    else:
        outer, radix, effective = budget, 1, budget
    if effective < budget:
        raise AssertionError((budget, outer, radix, effective))
    fresh_done = b.state(f"{prefix}_FRESH_DONE")
    b.counter_call(entry, "CLOCK", "FRESH_ZERO", fresh_done)
    current = fresh_done
    for i in range(outer):
        target = b.state(f"{prefix}_INC_{i+1}")
        b.counter_call(current, "CLOCK", "INC", target)
        current = target
    b.direct(current, nxt, writes={phase_tape: "P0"})


def _emit_checkpoint_request_one_step(
    b: _Builder, entry: int, nxt: int, prefix: str,
) -> None:
    layout = b.fabric.layout("CHECKPOINT")
    adapter = layout.adapter
    if not isinstance(adapter, JsonSparseAdapter):
        raise TypeError(type(adapter))
    ready = _checkpoint_clean_ready_id(adapter)
    reset_rows = adapter.rows_for_state(ready)
    if len(reset_rows) != 1:
        raise AssertionError((ready, len(reset_rows)))
    reset = reset_rows[0]
    t = b.fabric.extra_tapes
    b.direct(
        entry, nxt,
        reads={layout.register_tape: layout.qsymbol(ready)},
        writes={
            layout.register_tape: layout.qsymbol(reset.next_state_id),
            layout.tape_start + reusable.CONTROL_TAPE: cp.BLANK,
            t["L33_PHASE"]: L33_PHASES["SEARCH"],
        },
    )


def _emit_checkpoint_begin_cleanup_direct(
    b: _Builder, entry: int, nxt: int, phase_symbol: str,
) -> None:
    layout = b.fabric.layout("CHECKPOINT")
    adapter = layout.adapter
    if not isinstance(adapter, JsonSparseAdapter):
        raise TypeError(type(adapter))
    result_ready = _checkpoint_result_ready_id(adapter)
    retire_entry = _checkpoint_retire_entry_id(adapter)
    b.direct(
        entry, nxt,
        reads={layout.register_tape: layout.qsymbol(result_ready)},
        writes={
            layout.register_tape: layout.qsymbol(retire_entry),
            layout.tape_start + reusable.CONTROL_TAPE: cp.BLANK,
            b.fabric.extra_tapes["L33_PHASE"]: phase_symbol,
        },
    )


def _checkpoint_single_step_row_iterator(
    fabric: SparseRegisteredFabric, state: int, nxt: int,
) -> Iterator[SparseRow]:
    layout = fabric.layout("CHECKPOINT")
    adapter = layout.adapter
    if not isinstance(adapter, JsonSparseAdapter):
        raise TypeError(type(adapter))
    phase = fabric.extra_tapes["L33_PHASE"]
    result_ready = _checkpoint_result_ready_id(adapter)
    clean_ready = _checkpoint_clean_ready_id(adapter)

    # SEARCH pauses at RESULT_READY so the retained result scan can consume
    # the output axes before retirement begins.
    yield _direct(
        state, nxt,
        reads={phase: L33_PHASES["SEARCH"],
               layout.register_tape: layout.qsymbol(result_ready)},
        writes={phase: L33_PHASES["RESULT_FRESH"]},
    )
    # Producer-paid cleanup has two finite continuations.
    gap_tape = fabric.layout("GAP").tape_start
    yield _direct(
        state, nxt,
        reads={phase: L33_PHASES["CLEANUP_LAUNCH"],
               layout.register_tape: layout.qsymbol(clean_ready),
               gap_tape: BOTTOM},
        writes={phase: L33_PHASES["TO_END0"]},
    )
    # A candidate that missed its target is impossible under the proved
    # production timing bound, but the source machine still recovers safely:
    # producer-paid cleanup is followed by incremental stale-head return.
    yield _direct(
        state, nxt,
        reads={phase: L33_PHASES["CLEANUP_LAUNCH"],
               layout.register_tape: layout.qsymbol(clean_ready),
               gap_tape: ONE},
        writes={phase: L33_PHASES["RETURN_CANDIDATE"]},
    )
    yield _direct(
        state, nxt,
        reads={phase: L33_PHASES["CLEANUP_CATCH"],
               layout.register_tape: layout.qsymbol(clean_ready)},
        writes={phase: L33_PHASES["CATCH_GOOD"]},
    )

    for row in adapter.rows():
        if row.state_id in adapter.ready_state_ids or row.state_id in adapter.error_state_ids:
            continue
        local_reads = {layout.tape_start + tape: atom for tape, atom in row.reads}
        local_writes = {layout.register_tape: layout.qsymbol(row.next_state_id)}
        local_writes.update({layout.tape_start + tape: value for tape, value in row.writes})
        local_moves = {layout.tape_start + tape: move for tape, move in row.moves}
        for phase_symbol in (
            L33_PHASES["SEARCH"],
            L33_PHASES["CLEANUP_LAUNCH"],
            L33_PHASES["CLEANUP_CATCH"],
        ):
            reads = {
                phase: phase_symbol,
                layout.register_tape: layout.qsymbol(row.state_id),
            }
            reads.update(local_reads)
            yield _direct(
                state, nxt, reads=reads,
                writes=local_writes, moves=local_moves,
            )


def _emit_checkpoint_single_step_rows(
    b: _Builder, state: int, nxt: int,
) -> None:
    b.deferred_checkpoint_calls.append(
        DeferredCheckpointCall(state, nxt, "single_step")
    )


def _emit_current_to_bit_scratch(
    b: _Builder, entry: int, history: str, nxt: int,
) -> None:
    layout = b.fabric.layout(history)
    adapter = _history_adapter(b.fabric, history)
    scratch = b.fabric.extra_tapes["B_OK"]
    for qid in adapter.ready_state_ids:
        current = adapter.id_to_state[qid].current
        if current in ("0", "1"):
            b.direct(entry, nxt, reads={layout.register_tape: layout.qsymbol(qid)},
                     writes={scratch: current})


def _emit_compare_lag_to_scratch(
    b: _Builder, entry: int, nxt: int,
) -> None:
    layout = b.fabric.layout("L33_LAG")
    adapter = _history_adapter(b.fabric, "L33_LAG")
    scratch = b.fabric.extra_tapes["B_OK"]
    result = b.fabric.extra_tapes["BP_OK"]
    for qid in adapter.ready_state_ids:
        current = adapter.id_to_state[qid].current
        for bit in ("0", "1"):
            # A non-input lag symbol is the partial-overlap region and imposes
            # no comparison, exactly as in the incremental audit machine.
            match = current not in ("0", "1") or current == bit
            b.direct(
                entry, nxt,
                reads={layout.register_tape: layout.qsymbol(qid), scratch: bit},
                writes={result: YES if match else NO},
            )


def _emit_install_candidate(b: _Builder, entry: int, prefix: str) -> None:
    """Finish a candidate whose B'/LEFT' heads were positioned in BUILD.

    Earlier code moved the retained heads by d only when the target prefix was
    reached.  That was an unbudgeted O(d) case-5 action.  BUILD now performs
    those moves incrementally and records d in GAP, so installation is finite.
    """
    t = b.fabric.extra_tapes
    fresh_k = b.state(f"{prefix}_FRESH_K")
    done = b.state(f"{prefix}_DONE")
    b.direct(entry, fresh_k)
    b.counter_call(fresh_k, "K_MAG", "FRESH_ZERO", done)
    b.direct(done, OUT_CHECK, writes={
        t["K_SIGN"]: SIGN_ZERO,
        t["SECOND"]: KNOWN,
        t["LAZY_MODE"]: "N",
        t["COPY_NEEDED"]: NO,
        t["L33_PHASE"]: L33_IDLE,
    })


def _emit_case5(b: _Builder, *, background_budget: int) -> None:  # noqa: C901
    t = b.fabric.extra_tapes
    phase_tape = t["L33_PHASE"]
    clock_phase = t["CLOCK_PHASE"]
    clock = b.counter_data_tape("CLOCK")
    gap = b.counter_data_tape("GAP")
    bgret = b.counter_data_tape("BG_RETURN")
    target = b.counter_data_tape("TARGET")
    candidate = b.counter_data_tape("CANDIDATE")
    cp_layout = b.fabric.layout("CHECKPOINT")
    gf = cp_layout.tape_start + cp.SRC_FWD
    gr = cp_layout.tape_start + cp.SRC_REV
    gf2 = cp_layout.tape_start + cp.SRC_FWD2
    cand_axis = cp_layout.tape_start + cp.CANDIDATE_TAPE

    entry = CASE_ENTRY[UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES]
    append_l33 = b.state("C5_APPEND_L33")
    after_append = b.state("C5_AFTER_APPEND")
    follow_dispatch = b.state("C5_FOLLOW_DISPATCH")
    clock_entry = b.state("C5_CLOCK_ENTRY")
    work = b.state("C5_WORK")
    work_dec = b.state("C5_WORK_DEC")
    work_after = b.state("C5_WORK_AFTER")

    # COPY mode sees the new symbol through BG. RETURN/RUN append it directly
    # to all retained Lemma-3.3 histories before any background work.
    b.direct(entry, clock_entry, reads={t["LAZY_MODE"]: "C"})
    b.direct(entry, append_l33, reads={t["LAZY_MODE"]: frozenset(("R", "U"))})
    _emit_append_input_to_histories(
        b, append_l33, ("L33_CURRENT", "L33_LAG", "L33_COPY"),
        after_append, "C5_INPUT",
    )
    b.direct(after_append, follow_dispatch,
             reads={phase_tape: frozenset((L33_PHASES["FOLLOW_GOOD"], L33_PHASES["FOLLOW_BAD"]))})
    b.direct(after_append, clock_entry,
             reads={phase_tape: frozenset(set(L33_PHASES.values()) - {
                 L33_PHASES["FOLLOW_GOOD"], L33_PHASES["FOLLOW_BAD"]
             })})

    # FOLLOW consumes exactly the newly appended symbol and does not spend the
    # background scan allowance in the same source-input iteration.
    follow_cur = b.state("C5_FOLLOW_CURRENT_RIGHT")
    follow_scratch = b.state("C5_FOLLOW_SCRATCH")
    follow_lag = b.state("C5_FOLLOW_LAG_RIGHT")
    follow_compare = b.state("C5_FOLLOW_COMPARE")
    follow_target = b.state("C5_FOLLOW_TARGET_DEC")
    follow_after = b.state("C5_FOLLOW_AFTER")
    b.direct(follow_dispatch, follow_cur, reads={target: ONE})
    b.direct(follow_dispatch, clock_entry, reads={target: BOTTOM},
             writes={phase_tape: L33_PHASES["RETURN_CANDIDATE"]})
    b.history_call(follow_cur, "L33_CURRENT", "RIGHT", follow_scratch)
    _emit_current_to_bit_scratch(b, follow_scratch, "L33_CURRENT", follow_lag)
    b.history_call(follow_lag, "L33_LAG", "RIGHT", follow_compare)
    _emit_compare_lag_to_scratch(b, follow_compare, follow_target)
    b.counter_call(follow_target, "TARGET", "DEC", follow_after)
    follow_emit = b.state("C5_FOLLOW_EMIT")
    for phase_symbol, good_before in (
        (L33_PHASES["FOLLOW_GOOD"], True),
        (L33_PHASES["FOLLOW_BAD"], False),
    ):
        for match in (YES, NO):
            good = good_before and match == YES
            b.direct(
                follow_after,
                follow_emit if good else OUT_CHECK,
                reads={phase_tape: phase_symbol, t["BP_OK"]: match, target: BOTTOM},
                writes={} if good else {phase_tape: L33_PHASES["RETURN_CANDIDATE"]},
            )
            b.direct(
                follow_after, OUT_CHECK,
                reads={phase_tape: phase_symbol, t["BP_OK"]: match, target: ONE},
                writes={phase_tape: L33_PHASES["FOLLOW_GOOD"] if good else L33_PHASES["FOLLOW_BAD"]},
            )
    _emit_install_candidate(b, follow_emit, "C5_FOLLOW_INSTALL")

    _emit_clock_build(b, clock_entry, background_budget, work, "C5_CLOCK")
    if background_budget == background_steps_per_input():
        _outer, radix, _effective = background_clock_shape()
    else:
        radix = 1
    if radix == 1:
        b.counter_call(work_dec, "CLOCK", "DEC", work_after)
    else:
        for i in range(radix - 1):
            b.direct(
                work_dec, work,
                reads={clock_phase: f"P{i}"},
                writes={clock_phase: f"P{i+1}"},
            )
        b.guarded_counter_call(
            work_dec, "CLOCK", "DEC", work_after,
            reads={clock_phase: f"P{radix-1}"},
        )
    b.direct(work_after, OUT_CHECK, reads={clock: BOTTOM})
    b.direct(work_after, work, reads={clock: ONE}, writes={clock_phase: "P0"})

    # ------------------------- COPY mode -------------------------
    copy_append = b.state("C5_COPY_APPEND")
    copy_append_done = b.state("C5_COPY_APPEND_DONE")
    copy_move_done = b.state("C5_COPY_MOVE_DONE")
    copy_check_right = b.state("C5_COPY_CHECK_RIGHT")
    copy_move_bg = b.state("C5_COPY_MOVE_BG")
    copy_inc_return = b.state("C5_COPY_INC_RETURN")
    b.direct(work, copy_append,
             reads={t["LAZY_MODE"]: "C", t["COPY_NEEDED"]: YES})
    b.direct(work, copy_check_right,
             reads={t["LAZY_MODE"]: "C", t["COPY_NEEDED"]: NO})
    _emit_append_history_current_to_l33(b, copy_append, "BG", copy_append_done, "C5_COPY")
    b.direct(copy_append_done, work_dec, writes={t["COPY_NEEDED"]: NO})
    for row in _history_has_right_rows(
        b.fabric, state=copy_check_right, component="BG",
        if_yes=copy_move_bg, if_no=work_dec,
    ):
        if row.action.next_state == work_dec:
            b.rows.append(SparseRow(
                row.state, row.reads,
                SparseAction(work_dec,
                             row.action.writes + ((t["LAZY_MODE"], "R"),),
                             row.action.moves),
            ))
        else:
            b.rows.append(row)
    b.mid_right(copy_move_bg, "BG", "BG_REL", copy_inc_return)
    b.counter_call(copy_inc_return, "BG_RETURN", "INC", copy_move_done)
    b.direct(copy_move_done, work_dec, writes={t["COPY_NEEDED"]: YES})

    # ------------------------- RETURN mode -----------------------
    ret_p = b.state("C5_RETURN_P")
    ret_l1 = b.state("C5_RETURN_L1")
    ret_l2 = b.state("C5_RETURN_L2")
    ret_gap = b.state("C5_RETURN_GAP")
    ret_bg = b.state("C5_RETURN_BG")
    ret_bgdec = b.state("C5_RETURN_BGDEC")
    ret_align_bp = b.state("C5_RETURN_ALIGN_BP")
    ret_align_lbp = b.state("C5_RETURN_ALIGN_LBP")
    ret_align_bg = b.state("C5_RETURN_ALIGN_BG")
    ret_fresh_cp = b.state("C5_RETURN_FRESH_CP")
    ret_started = b.state("C5_RETURN_STARTED")
    b.direct(work, ret_p, reads={t["LAZY_MODE"]: "R", gap: ONE})
    b.direct(work, ret_bg, reads={t["LAZY_MODE"]: "R", gap: BOTTOM, bgret: ONE})
    b.direct(work, ret_align_bp,
             reads={t["LAZY_MODE"]: "R", gap: BOTTOM, bgret: BOTTOM})
    b.mid_left(ret_p, "BP", "BP_REL", ret_l1)
    b.left_left(ret_l1, "LBP", "LBP_REL", ret_l2)
    b.left_left(ret_l2, "LBP", "LBP_REL", ret_gap)
    b.counter_call(ret_gap, "GAP", "DEC", work_dec)
    b.mid_left(ret_bg, "BG", "BG_REL", ret_bgdec)
    b.counter_call(ret_bgdec, "BG_RETURN", "DEC", work_dec)
    _emit_copy_relation(b, ret_align_bp, "B_REL", "BP_REL",
                        (MID_BEFORE, MID_AT, MID_AFTER), ret_align_lbp)
    _emit_copy_relation(b, ret_align_lbp, "LB_REL", "LBP_REL",
                        (LEFT_EXACT, LEFT_AT, LEFT_AFTER1, LEFT_AFTER2), ret_align_bg)
    _emit_copy_relation(b, ret_align_bg, "B_REL", "BG_REL",
                        (MID_BEFORE, MID_AT, MID_AFTER), ret_fresh_cp)
    _emit_fresh_empty_checkpoint_epoch(b, ret_fresh_cp, ret_started, "C5_BG_CP")
    b.direct(ret_started, work_dec, writes={
        t["LAZY_MODE"]: "U", phase_tape: L33_PHASES["TO_END0"]
    })

    # ------------------------- RUN launch ------------------------
    def phase_direct(symbol, target_state):
        b.direct(work, target_state,
                 reads={t["LAZY_MODE"]: "U", phase_tape: symbol})

    to0 = b.state("C5_TO_END0")
    to1 = b.state("C5_TO_END1")
    to2 = b.state("C5_TO_END2")
    phase_direct(L33_PHASES["TO_END0"], to0)
    phase_direct(L33_PHASES["TO_END1"], to1)
    phase_direct(L33_PHASES["TO_END2"], to2)
    for state, tape, next_phase in (
        (to0, gf, L33_PHASES["TO_END1"]),
        (to1, gf2, L33_PHASES["TO_END2"]),
        (to2, gr, L33_PHASES["LAUNCH_COPY"]),
    ):
        b.direct(state, work_dec, reads={tape: cp.END}, writes={phase_tape: next_phase})
        b.direct(state, work_dec,
                 reads={tape: frozenset((cp.SENTINEL, "0", "1"))}, moves={tape: 1})

    lc = b.state("C5_LAUNCH_COPY")
    lc_move = b.state("C5_LAUNCH_COPY_MOVE")
    phase_direct(L33_PHASES["LAUNCH_COPY"], lc)
    for row in _history_has_right_rows(
        b.fabric, state=lc, component="L33_COPY",
        if_yes=lc_move, if_no=work_dec,
    ):
        if row.action.next_state == work_dec:
            b.rows.append(SparseRow(
                row.state, row.reads,
                SparseAction(work_dec,
                    row.action.writes + (
                        (gf, cp.END), (gf2, cp.END), (gr, cp.END),
                        (phase_tape, L33_PHASES["SYNC_CURRENT"]),
                    ), row.action.moves),
            ))
        else:
            b.rows.append(row)
    b.history_call(lc_move, "L33_COPY", "RIGHT", work_dec)
    # The history move returns with phase changed so the next macro writes.
    # Amend those call rows to install LW.
    count = len(_history_adapter(b.fabric, "L33_COPY").ready_state_ids)
    for i in range(len(b.rows)-count, len(b.rows)):
        row=b.rows[i]
        b.rows[i]=SparseRow(row.state,row.reads,SparseAction(
            row.action.next_state,row.action.writes+((phase_tape,L33_PHASES["LAUNCH_WRITE"]),),row.action.moves))

    lw = b.state("C5_LAUNCH_WRITE")
    phase_direct(L33_PHASES["LAUNCH_WRITE"], lw)
    b.copy_history_current_to_tapes(
        lw, "L33_COPY", (cp.SRC_FWD, cp.SRC_REV, cp.SRC_FWD2), work_dec,
        moves={cp.SRC_FWD: 1, cp.SRC_REV: 1, cp.SRC_FWD2: 1},
    )
    # Add phase LC to each emitted direct row.
    adapter = _history_adapter(b.fabric, "L33_COPY")
    count = sum(1 for q in adapter.ready_state_ids if adapter.id_to_state[q].current in ("0","1"))
    for i in range(len(b.rows)-count, len(b.rows)):
        row=b.rows[i]
        b.rows[i]=SparseRow(row.state,row.reads,SparseAction(
            row.action.next_state,row.action.writes+((phase_tape,L33_PHASES["LAUNCH_COPY"]),),row.action.moves))

    sc = b.state("C5_SYNC_CURRENT")
    sc_move = b.state("C5_SYNC_CURRENT_MOVE")
    sl = b.state("C5_SYNC_LAG")
    sl_move = b.state("C5_SYNC_LAG_MOVE")
    phase_direct(L33_PHASES["SYNC_CURRENT"], sc)
    for row in _history_has_right_rows(b.fabric,state=sc,component="L33_CURRENT",if_yes=sc_move,if_no=work_dec):
        if row.action.next_state==work_dec:
            b.rows.append(SparseRow(row.state,row.reads,SparseAction(work_dec,row.action.writes+((phase_tape,L33_PHASES["SYNC_LAG"]),),row.action.moves)))
        else:b.rows.append(row)
    b.history_call(sc_move,"L33_CURRENT","RIGHT",work_dec)
    phase_direct(L33_PHASES["SYNC_LAG"], sl)
    for row in _history_has_right_rows(b.fabric,state=sl,component="L33_LAG",if_yes=sl_move,if_no=work_dec):
        if row.action.next_state==work_dec:
            b.rows.append(SparseRow(row.state,row.reads,SparseAction(work_dec,row.action.writes+((phase_tape,L33_PHASES["REWIND_FWD0"]),),row.action.moves)))
        else:b.rows.append(row)
    b.history_call(sl_move,"L33_LAG","RIGHT",work_dec)

    rw0 = b.state("C5_REWIND_FWD0")
    rw1 = b.state("C5_REWIND_FWD1")
    rv = b.state("C5_REV_LEFT")
    phase_direct(L33_PHASES["REWIND_FWD0"], rw0)
    b.direct(rw0, work_dec, reads={gf: cp.SENTINEL}, moves={gf: 1},
             writes={phase_tape: L33_PHASES["REWIND_FWD1"]})
    b.direct(rw0, work_dec,
             reads={gf: frozenset(("0", "1", cp.END))}, moves={gf: -1})
    phase_direct(L33_PHASES["REWIND_FWD1"], rw1)
    b.direct(rw1, work_dec, reads={gf2: cp.SENTINEL}, moves={gf2: 1},
             writes={phase_tape: L33_PHASES["REV_LEFT"]})
    b.direct(rw1, work_dec,
             reads={gf2: frozenset(("0", "1", cp.END))}, moves={gf2: -1})
    phase_direct(L33_PHASES["REV_LEFT"], rv)
    b.direct(rv, work_dec, reads={gr: cp.END}, moves={gr: -1},
             writes={phase_tape: L33_PHASES["REQUEST"]})

    request = b.state("C5_REQUEST")
    phase_direct(L33_PHASES["REQUEST"], request)
    _emit_checkpoint_request_one_step(b, request, work_dec, "C5_REQUEST")

    # One checkpoint transition per macro.
    _emit_checkpoint_single_step_rows(b, work, work_dec)

    # ------------------------- result scan -----------------------
    rf = b.state("C5_RESULT_FRESH")
    phase_direct(L33_PHASES["RESULT_FRESH"], rf)
    rf_done = b.state("C5_RESULT_FRESH_DONE")
    b.counter_call(rf,"CANDIDATE","FRESH_ZERO",rf_done)
    b.direct(rf_done,work_dec,writes={phase_tape:L33_PHASES["RESULT_CAND"]})
    rc = b.state("C5_RESULT_CAND")
    phase_direct(L33_PHASES["RESULT_CAND"], rc)
    b.direct(rc,work_dec,reads={cand_axis:cp.MARK},writes={phase_tape:L33_PHASES["RESULT_SOURCE"]})
    b.direct(rc,work_dec,reads={cand_axis:frozenset(set(cp.OUTPUT_ALPHABET)-{cp.MARK})},moves={cand_axis:-1})
    rs = b.state("C5_RESULT_SOURCE")
    phase_direct(L33_PHASES["RESULT_SOURCE"], rs)
    b.direct(rs,work_dec,reads={gf:cp.SENTINEL},writes={phase_tape:L33_PHASES["RESULT_ADVANCE"]})
    b.direct(rs,work_dec,reads={gf:frozenset(("0","1",cp.END))},moves={gf:-1})
    ra = b.state("C5_RESULT_ADVANCE")
    phase_direct(L33_PHASES["RESULT_ADVANCE"], ra)
    ra_inc = b.state("C5_RESULT_ADVANCE_INC")
    b.direct(ra,ra_inc,moves={cand_axis:1,gf:1})
    b.counter_call(ra_inc,"CANDIDATE","INC",work_dec)
    count=len(b.fabric.layout("CANDIDATE").adapter.ready_state_ids)
    for i in range(len(b.rows)-count,len(b.rows)):
        row=b.rows[i]; b.rows[i]=SparseRow(row.state,row.reads,SparseAction(row.action.next_state,row.action.writes+((phase_tape,L33_PHASES["RESULT_CHECK"]),),row.action.moves))
    rk = b.state("C5_RESULT_CHECK")
    phase_direct(L33_PHASES["RESULT_CHECK"],rk)
    rk_target=b.state("C5_RESULT_TARGET_FRESH")
    rk_cleanup=b.state("C5_RESULT_NO_CANDIDATE_CLEANUP")
    b.direct(rk,rk_target,reads={cand_axis:cp.GAP})
    b.counter_call(rk_target,"TARGET","FRESH_ZERO",work_dec)
    count=len(b.fabric.layout("TARGET").adapter.ready_state_ids)
    for i in range(len(b.rows)-count,len(b.rows)):
        row=b.rows[i]; b.rows[i]=SparseRow(row.state,row.reads,SparseAction(row.action.next_state,row.action.writes+((phase_tape,L33_PHASES["BUILD_CANDIDATE"]),),row.action.moves))
    b.direct(rk,rk_cleanup,reads={cand_axis:cp.BLANK,gf:cp.END})
    _emit_checkpoint_begin_cleanup_direct(
        b, rk_cleanup, work_dec, L33_PHASES["CLEANUP_LAUNCH"]
    )
    b.direct(rk,work_dec,reads={cand_axis:cp.BLANK,gf:frozenset(("0","1"))},writes={phase_tape:L33_PHASES["RESULT_ADVANCE"]})

    # Build 16d, lag 2d-1, and position the retained B' heads at B+d.
    # This makes installation at the exact target prefix constant-time.
    bc = b.state("C5_BUILD_CANDIDATE")
    bc_ops=[b.state(f"C5_BUILD_TARGET_{i}") for i in range(16)]
    bc_l1=b.state("C5_BUILD_LAG1"); bc_l2=b.state("C5_BUILD_LAG2")
    bc_bottom=b.state("C5_BUILD_BOTTOM")
    phase_direct(L33_PHASES["BUILD_CANDIDATE"],bc)
    b.direct(bc,bc_ops[0],reads={candidate:ONE},moves={candidate:-1})
    b.direct(bc,bc_bottom,reads={candidate:BOTTOM})
    for i,state in enumerate(bc_ops): b.counter_call(state,"TARGET","INC",bc_l1 if i==15 else bc_ops[i+1])
    b.history_call(bc_l1,"L33_LAG","LEFT",bc_l2)
    bc_move_bp=b.state("C5_BUILD_MOVE_BP")
    bc_gap_inc=b.state("C5_BUILD_GAP_INC")
    b.history_call(bc_l2,"L33_LAG","LEFT",bc_move_bp)
    _emit_bp_right_unit(b,bc_move_bp,bc_gap_inc,"C5_BUILD_BP")
    b.counter_call(bc_gap_inc,"GAP","INC",work_dec)
    # keep BC after the complete unit
    count=len(b.fabric.layout("GAP").adapter.ready_state_ids)
    for i in range(len(b.rows)-count,len(b.rows)):
        row=b.rows[i]; b.rows[i]=SparseRow(row.state,row.reads,SparseAction(row.action.next_state,row.action.writes+((phase_tape,L33_PHASES["BUILD_CANDIDATE"]),),row.action.moves))
    bc_right=b.state("C5_BUILD_COMPENSATE")
    b.history_call(bc_bottom,"L33_LAG","RIGHT",bc_right)
    b.direct(bc_right,work_dec,moves={candidate:1},writes={phase_tape:L33_PHASES["RESTORE_CANDIDATE"]})
    br=b.state("C5_RESTORE_CANDIDATE")
    phase_direct(L33_PHASES["RESTORE_CANDIDATE"],br)
    b.direct(br,work_dec,reads={candidate:ONE},moves={candidate:1})
    b.direct(br,work_dec,reads={candidate:cp.BLANK},moves={candidate:-1},writes={phase_tape:L33_PHASES["TARGET_REWIND"]})

    tr=b.state("C5_TARGET_REWIND")
    phase_direct(L33_PHASES["TARGET_REWIND"],tr)
    b.direct(tr,work_dec,reads={gf:cp.SENTINEL},writes={phase_tape:L33_PHASES["TARGET_SUBTRACT"]})
    b.direct(tr,work_dec,reads={gf:frozenset(("0","1",cp.END))},moves={gf:-1})
    ts=b.state("C5_TARGET_SUBTRACT")
    phase_direct(L33_PHASES["TARGET_SUBTRACT"],ts)
    b.direct(ts,work_dec,moves={gf:1},writes={phase_tape:L33_PHASES["TARGET_INSPECT"]})
    tx=b.state("C5_TARGET_INSPECT")
    tx_cleanup_catch=b.state("C5_TARGET_CLEANUP_CATCH")
    tx_cleanup_launch=b.state("C5_TARGET_CLEANUP_LAUNCH")
    phase_direct(L33_PHASES["TARGET_INSPECT"],tx)
    b.direct(tx,tx_cleanup_catch,reads={gf:cp.END})
    _emit_checkpoint_begin_cleanup_direct(
        b, tx_cleanup_catch, work_dec, L33_PHASES["CLEANUP_CATCH"]
    )
    b.direct(tx,tx_cleanup_launch,reads={gf:frozenset(("0","1")),target:BOTTOM})
    _emit_checkpoint_begin_cleanup_direct(
        b, tx_cleanup_launch, work_dec, L33_PHASES["CLEANUP_LAUNCH"]
    )
    txdec=b.state("C5_TARGET_DEC")
    b.direct(tx,txdec,reads={gf:frozenset(("0","1")),target:ONE})
    b.counter_call(txdec,"TARGET","DEC",work_dec)
    count=len(b.fabric.layout("TARGET").adapter.ready_state_ids)
    for i in range(len(b.rows)-count,len(b.rows)):
        row=b.rows[i]; b.rows[i]=SparseRow(row.state,row.reads,SparseAction(row.action.next_state,row.action.writes+((phase_tape,L33_PHASES["TARGET_SUBTRACT"]),),row.action.moves))

    # A rejected candidate returns the prepositioned B' heads incrementally
    # before the next checkpoint launch.  GAP is exactly the remaining return
    # distance, so case 6 can interrupt this phase safely.
    cr=b.state("C5_RETURN_CANDIDATE")
    cr_move=b.state("C5_RETURN_CANDIDATE_MOVE")
    cr_l1=b.state("C5_RETURN_CANDIDATE_L1")
    cr_l2=b.state("C5_RETURN_CANDIDATE_L2")
    cr_dec=b.state("C5_RETURN_CANDIDATE_DEC")
    phase_direct(L33_PHASES["RETURN_CANDIDATE"],cr)
    b.direct(cr,work_dec,reads={gap:BOTTOM},writes={phase_tape:L33_PHASES["TO_END0"]})
    b.direct(cr,cr_move,reads={gap:ONE})
    b.mid_left(cr_move,"BP","BP_REL",cr_l1)
    b.left_left(cr_l1,"LBP","LBP_REL",cr_l2)
    b.left_left(cr_l2,"LBP","LBP_REL",cr_dec)
    b.counter_call(cr_dec,"GAP","DEC",work_dec)
    count=len(b.fabric.layout("GAP").adapter.ready_state_ids)
    for i in range(len(b.rows)-count,len(b.rows)):
        row=b.rows[i]; b.rows[i]=SparseRow(row.state,row.reads,SparseAction(row.action.next_state,row.action.writes+((phase_tape,L33_PHASES["RETURN_CANDIDATE"]),),row.action.moves))

    # Catch-up current and lag to the live input end.
    catch=b.state("C5_CATCH")
    catch_cur=b.state("C5_CATCH_CUR")
    catch_scratch=b.state("C5_CATCH_SCRATCH")
    catch_lag=b.state("C5_CATCH_LAG")
    catch_compare=b.state("C5_CATCH_COMPARE")
    catch_dec=b.state("C5_CATCH_DEC")
    catch_after=b.state("C5_CATCH_AFTER")
    for phase_symbol in (L33_PHASES["CATCH_GOOD"],L33_PHASES["CATCH_BAD"]):
        b.direct(work,catch,reads={t["LAZY_MODE"]:"U",phase_tape:phase_symbol})
    # Branch has-right; no-right finalizes catch-up.
    catch_done=b.state("C5_CATCH_DONE")
    for row in _history_has_right_rows(b.fabric,state=catch,component="L33_CURRENT",if_yes=catch_cur,if_no=catch_done): b.rows.append(row)
    b.direct(catch_cur,work_dec,reads={target:BOTTOM},writes={phase_tape:L33_PHASES["RETURN_CANDIDATE"]})
    b.history_call(catch_cur,"L33_CURRENT","RIGHT",catch_scratch)
    # Guard history call by target ONE to avoid conflict with missed row.
    count=len(_history_adapter(b.fabric,"L33_CURRENT").ready_state_ids)
    call=b.rows[-count:]; del b.rows[-count:]
    for row in call:b.rows.append(SparseRow(row.state,row.reads+((target,ONE),),row.action))
    _emit_current_to_bit_scratch(b,catch_scratch,"L33_CURRENT",catch_lag)
    b.history_call(catch_lag,"L33_LAG","RIGHT",catch_compare)
    _emit_compare_lag_to_scratch(b,catch_compare,catch_dec)
    b.counter_call(catch_dec,"TARGET","DEC",catch_after)
    for phase_symbol,good_before in ((L33_PHASES["CATCH_GOOD"],True),(L33_PHASES["CATCH_BAD"],False)):
        for match in (YES,NO):
            good=good_before and match==YES
            b.direct(catch_after,work_dec,reads={phase_tape:phase_symbol,t["BP_OK"]:match},writes={phase_tape:L33_PHASES["CATCH_GOOD"] if good else L33_PHASES["CATCH_BAD"]})
    catch_emit=b.state("C5_CATCH_EMIT")
    for phase_symbol,good in ((L33_PHASES["CATCH_GOOD"],True),(L33_PHASES["CATCH_BAD"],False)):
        b.direct(catch_done,catch_emit if good else work_dec,reads={phase_tape:phase_symbol,target:BOTTOM},writes={} if good else {phase_tape:L33_PHASES["RETURN_CANDIDATE"]})
        b.direct(catch_done,work_dec,reads={phase_tape:phase_symbol,target:ONE},writes={phase_tape:L33_PHASES["FOLLOW_GOOD"] if good else L33_PHASES["FOLLOW_BAD"]})
    _emit_install_candidate(b,catch_emit,"C5_CATCH_INSTALL")

def _emit_checkpoint_run_to_ready(b: _Builder, entry: int, nxt: int, prefix: str) -> None:
    """Finish any paused job, discard its result, and reach clean READY."""
    layout = b.fabric.layout("CHECKPOINT")
    adapter = layout.adapter
    if not isinstance(adapter, JsonSparseAdapter):
        raise TypeError(type(adapter))
    result_ready = _checkpoint_result_ready_id(adapter)
    clean_ready = _checkpoint_clean_ready_id(adapter)
    arrived = b.state(f"{prefix}_RESULT_ARRIVED")

    # Already clean: no work remains.  Already at a stale result: retire it.
    b.direct(entry, nxt, reads={layout.register_tape: layout.qsymbol(clean_ready)})
    _emit_checkpoint_retire_call(b, entry, nxt, f"{prefix}_RETIRE_DIRECT")

    # An active one-shot or cleanup state runs until the next terminal state.
    b.deferred_checkpoint_calls.append(
        DeferredCheckpointCall(entry, arrived, "run_to_result")
    )
    b.direct(arrived, nxt, reads={layout.register_tape: layout.qsymbol(clean_ready)})
    _emit_checkpoint_retire_call(b, arrived, nxt, f"{prefix}_RETIRE_ARRIVED")


def _emit_copy_relation(
    b: _Builder, entry: int, source_name: str, target_name: str,
    alphabet: tuple[str, ...], nxt: int,
) -> None:
    t = b.fabric.extra_tapes
    for value in alphabet:
        b.direct(entry, nxt, reads={t[source_name]: value}, writes={t[target_name]: value})


def _emit_case6(b: _Builder) -> None:
    """Discard a stale lazy background, finish returns, and RECOVER."""
    t = b.fabric.extra_tapes
    gap = b.counter_data_tape("GAP")
    bgret = b.counter_data_tape("BG_RETURN")
    p_loop = b.state("C6_RETURN_P_LOOP")
    p_mid = b.state("C6_RETURN_P_MID")
    p_l1 = b.state("C6_RETURN_P_L1")
    p_l2 = b.state("C6_RETURN_P_L2")
    p_dec = b.state("C6_RETURN_P_DEC")
    bg_loop = b.state("C6_RETURN_BG_LOOP")
    bg_mid = b.state("C6_RETURN_BG_MID")
    bg_dec = b.state("C6_RETURN_BG_DEC")
    copy_bp_rel = b.state("C6_COPY_BP_REL")
    copy_lbp_rel = b.state("C6_COPY_LBP_REL")
    copy_bg_rel = b.state("C6_COPY_BG_REL")
    cp_finish = b.state("C6_CP_FINISH")
    recover_entry = b.state("C6_RECOVER_ENTRY")
    recover_done = b.state("C6_RECOVER_DONE")

    b.direct(CASE_ENTRY[UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS], p_loop)
    b.direct(p_loop, bg_loop, reads={gap: BOTTOM})
    b.direct(p_loop, p_mid, reads={gap: ONE})
    b.mid_left(p_mid, "BP", "BP_REL", p_l1)
    b.left_left(p_l1, "LBP", "LBP_REL", p_l2)
    b.left_left(p_l2, "LBP", "LBP_REL", p_dec)
    b.counter_call(p_dec, "GAP", "DEC", p_loop)

    b.direct(bg_loop, copy_bp_rel, reads={bgret: BOTTOM})
    b.direct(bg_loop, bg_mid, reads={bgret: ONE})
    b.mid_left(bg_mid, "BG", "BG_REL", bg_dec)
    b.counter_call(bg_dec, "BG_RETURN", "DEC", bg_loop)

    _emit_copy_relation(
        b, copy_bp_rel, "B_REL", "BP_REL",
        (MID_BEFORE, MID_AT, MID_AFTER), copy_lbp_rel,
    )
    _emit_copy_relation(
        b, copy_lbp_rel, "LB_REL", "LBP_REL",
        (LEFT_EXACT, LEFT_AT, LEFT_AFTER1, LEFT_AFTER2), copy_bg_rel,
    )
    _emit_copy_relation(
        b, copy_bg_rel, "B_REL", "BG_REL",
        (MID_BEFORE, MID_AT, MID_AFTER), cp_finish,
    )
    _emit_checkpoint_run_to_ready(b, cp_finish, recover_entry, "C6_CP")
    _emit_recover(b, recover_entry, recover_done, "C6_RECOVER", align=False)
    b.direct(recover_done, OUT_CHECK, writes={
        t["SECOND"]: KNOWN,
        t["LAZY_MODE"]: "N",
        t["COPY_NEEDED"]: NO,
        t["L33_PHASE"]: L33_IDLE,
    })

def build_remaining_case_rows(
    fabric: SparseRegisteredFabric,
    *,
    background_budget: int | None = None,
    include_case5: bool = True,
    include_case6: bool = True,
) -> RemainingCaseBuild:
    b = _Builder(fabric)
    c2_done = b.state("CASE2_RECOVER_DONE")
    _emit_recover(
        b, CASE_ENTRY[UpdateCase.TWO_BOTH_FAIL], c2_done,
        "C2_RECOVER", align=True,
    )
    t = fabric.extra_tapes
    b.direct(c2_done, OUT_CHECK, writes={
        t["SECOND"]: KNOWN,
        t["LAZY_MODE"]: "N",
        t["COPY_NEEDED"]: NO,
        t["L33_PHASE"]: L33_IDLE,
    })
    _emit_case3(b)
    if include_case5:
        _emit_case5(b, background_budget=(background_steps_per_input() if background_budget is None else background_budget))
    if include_case6:
        _emit_case6(b)
    return RemainingCaseBuild(tuple(b.rows), b.names, tuple(b.deferred_checkpoint_calls))
