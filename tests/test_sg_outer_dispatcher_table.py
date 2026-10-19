from copy import deepcopy

import history_zipper_ordinary_tm as hz
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
    READ0,
    READ1,
    SIGN_NEG,
    SIGN_POS,
    SIGN_ZERO,
    UNKNOWN,
    build_dispatcher_rows,
)
from sg_outer_incremental import OrdinarySGOuterIncremental
from sg_outer_ordinary import LeftRelation, MidRelation
from sparse_registered_linker import (
    SparseFabricConfiguration,
    LazySparseFabricInterpreter,
    SparseRegisteredFabric,
    SymbolicAdapter,
)
from symbolic_tm import SymbolicConfiguration
from unary_counter_ordinary_tm import ERROR, READY, machine as counter_machine
from ordinary_unary_counter import Sign

CONTROL_TAPES = {
    "INPUT": ("_", "0", "1"),
    "SECOND": ("_", "K", "U"),
    "B_REL": ("_", "B", "A", "X"),
    "BP_REL": ("_", "B", "A", "X"),
    "BG_REL": ("_", "B", "A", "X"),
    "LB_REL": ("_", "E", "A", "1", "2"),
    "LBP_REL": ("_", "E", "A", "1", "2"),
    "BGL_REL": ("_", "E", "A", "1", "2"),
    "B_OK": ("_", "0", "1"),
    "BP_OK": ("_", "0", "1"),
    "GAP_LARGE": ("_", "0", "1"),
    "LAZY_MODE": ("_", "N", "C", "R", "U"),
    "COPY_NEEDED": ("_", "0", "1"),
    "K_SIGN": ("_", "N", "Z", "P"),
    "OUTPUT": ("_", "0", "1"),
    "CASE": ("_", "1", "2", "3", "4", "5", "6"),
}


def _fabric():
    hm = hz.machine()
    histories = tuple(
        SymbolicAdapter(
            name, hm,
            frozenset(hm.halting_states - {hz.ERROR_STATE}),
            frozenset((hz.ERROR_STATE,)),
        )
        for name in ("B", "BP", "LB", "LBP", "BG", "BGL")
    )
    cm = counter_machine()
    kmag = SymbolicAdapter("K_MAG", cm, frozenset((READY,)), frozenset((ERROR,)))
    return SparseRegisteredFabric(
        histories + (kmag,),
        controller_states=tuple(range(8192)),
        extra_tape_alphabets=CONTROL_TAPES,
    )


def _mid(value):
    return {
        MidRelation.BEFORE_END: MID_BEFORE,
        MidRelation.AT_END: MID_AT,
        MidRelation.AFTER_END: MID_AFTER,
    }[value]


def _left(value):
    return {
        LeftRelation.EXACT: LEFT_EXACT,
        LeftRelation.AT_END: LEFT_AT,
        LeftRelation.AFTER1: LEFT_AFTER1,
        LeftRelation.AFTER2: LEFT_AFTER2,
    }[value]


def _sign(value):
    return {Sign.NEGATIVE: SIGN_NEG, Sign.ZERO: SIGN_ZERO, Sign.POSITIVE: SIGN_POS}[value]


def _configuration(fabric, source, bit):
    tapes = [dict() for _ in range(fabric.tape_count)]
    heads = [0] * fabric.tape_count
    for name in ("B", "BP", "LB", "LBP", "BG", "BGL"):
        layout = fabric.layout(name)
        cfg = source.cursors[name]
        adapter = layout.adapter
        for local in range(layout.adapter.machine.tape_count):
            tapes[layout.tape_start + local] = dict(cfg.tapes[local])
            heads[layout.tape_start + local] = cfg.heads[local]
        qid = adapter.state_to_id[cfg.state]
        tapes[layout.register_tape][0] = layout.qsymbol(qid)
    layout = fabric.layout("K_MAG")
    tapes[layout.tape_start] = dict(source.k.magnitude.tape)
    heads[layout.tape_start] = source.k.magnitude.head
    adapter = layout.adapter
    tapes[layout.register_tape][0] = layout.qsymbol(adapter.state_to_id[READY])

    values = {
        "SECOND": KNOWN if source.bp is not None else UNKNOWN,
        "B_REL": _mid(source.b_rel),
        "BP_REL": _mid(source.bp_rel),
        "BG_REL": _mid(source.bg_rel),
        "LB_REL": _left(source.lb_rel),
        "LBP_REL": _left(source.lbp_rel),
        "BGL_REL": _left(source.bgl_rel),
        "K_SIGN": _sign(source.k.sign),
        "B_OK": NO,
        "BP_OK": NO,
        "GAP_LARGE": NO,
    }
    for name, value in values.items():
        tapes[fabric.extra_tapes[name]][0] = value
    return SparseFabricConfiguration(READ0 if bit == "0" else READ1, tapes, heads)


def test_dispatcher_selects_all_six_cases_from_real_snapshots():
    fabric = _fabric()
    build = build_dispatcher_rows(fabric)
    interpreter = LazySparseFabricInterpreter(fabric, build.rows)
    case_by_entry = {state: case for case, state in CASE_ENTRY.items()}

    # The corrected regression word reaches 3,1,2,1,4,5,6 in order.  Using
    # these fixed real snapshots avoids an exponential search whose case-5
    # audit work dominates the dispatcher test without adding coverage.
    snapshots = {}
    source = OrdinarySGOuterIncremental(audit=True, background_work_budget=8)
    prefix = ""
    for bit in "0011000":
        expected = deepcopy(source).append(bit).case
        snapshots.setdefault(expected, (deepcopy(source), bit, prefix))
        source.append(bit)
        prefix += bit
    assert set(snapshots) == set(CASE_ENTRY)

    for expected, (source, bit, prefix) in snapshots.items():
        config = _configuration(fabric, source, bit)
        for _ in range(2_000_000):
            if config.state in case_by_entry:
                break
            interpreter.step(config)
        else:
            raise TimeoutError((prefix, bit, config.state))
        actual = case_by_entry[config.state]
        assert actual is expected, (prefix, bit, actual, expected)
