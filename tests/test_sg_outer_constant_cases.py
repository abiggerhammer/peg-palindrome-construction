from copy import deepcopy
from itertools import product

import history_zipper_ordinary_tm as hz
from ordinary_unary_counter import Sign
from sg_outer_constant_cases import (
    SOURCE_DONE_0,
    SOURCE_DONE_1,
    build_constant_case_rows,
)
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
from sg_zero_ratio import UpdateCase
from sparse_registered_linker import (
    LazySparseFabricInterpreter,
    SparseFabricConfiguration,
    SparseRegisteredFabric,
    SymbolicAdapter,
)
from unary_counter_ordinary_tm import (
    BOTTOM,
    ERROR,
    ONE,
    READY,
    machine as counter_machine,
)

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
    "L33_PHASE": ("_", "I"),
}


def _fabric():
    hm = hz.machine()
    histories = tuple(
        SymbolicAdapter(
            name, hm,
            frozenset(hm.halting_states - {hz.ERROR_STATE}),
            frozenset((hz.ERROR_STATE,)),
        )
        for name in (
            "B", "BP", "LB", "LBP", "BG", "BGL",
            "L33_CURRENT", "L33_LAG", "L33_COPY",
        )
    )
    cm = counter_machine()
    counters = tuple(
        SymbolicAdapter(name, cm, frozenset((READY,)), frozenset((ERROR,)))
        for name in ("K_MAG", "BG_RETURN")
    )
    return SparseRegisteredFabric(
        histories + counters,
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


def _put_component(fabric, tapes, heads, name, config):
    layout = fabric.layout(name)
    adapter = layout.adapter
    for local in range(len(adapter.tape_alphabets)):
        tapes[layout.tape_start + local] = dict(config.tapes[local])
        heads[layout.tape_start + local] = config.heads[local]
    tapes[layout.register_tape][0] = layout.qsymbol(adapter.state_to_id[config.state])


def _counter_config(counter):
    from symbolic_tm import SymbolicConfiguration
    return SymbolicConfiguration(READY, [dict(counter.tape)], [counter.head])


def _configuration(fabric, source, bit):
    tapes = [dict() for _ in range(fabric.tape_count)]
    heads = [0] * fabric.tape_count
    for name in ("B", "BP", "LB", "LBP", "BG", "BGL"):
        _put_component(fabric, tapes, heads, name, source.cursors[name])
    # Deliberately dirty retained histories; case 4 must abandon them in two
    # ordinary RESET transitions each.
    for name in ("L33_CURRENT", "L33_LAG", "L33_COPY"):
        dirty = hz.initial_configuration(tuple("#01011"), reader=3)
        _put_component(fabric, tapes, heads, name, dirty)
    _put_component(fabric, tapes, heads, "K_MAG", _counter_config(source.k.magnitude))
    from ordinary_unary_counter import UnaryCounter
    dirty_counter = UnaryCounter.zero()
    for _ in range(5):
        dirty_counter.increment()
    _put_component(fabric, tapes, heads, "BG_RETURN", _counter_config(dirty_counter))

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
        "LAZY_MODE": "N",
        "COPY_NEEDED": NO,
        "OUTPUT": NO,
        "L33_PHASE": "I",
    }
    for name, value in values.items():
        tapes[fabric.extra_tapes[name]][0] = value
    return SparseFabricConfiguration(READ0 if bit == "0" else READ1, tapes, heads)


def _component_materialize(fabric, config, name):
    from symbolic_tm import SymbolicConfiguration
    layout = fabric.layout(name)
    adapter = layout.adapter
    local_tapes = [
        dict(config.tapes[layout.tape_start + i])
        for i in range(len(adapter.tape_alphabets))
    ]
    local_heads = [
        config.heads[layout.tape_start + i]
        for i in range(len(adapter.tape_alphabets))
    ]
    symbol = config.tapes[layout.register_tape][0]
    qid = int(symbol.rsplit("q", 1)[1])
    state = adapter.id_to_state[qid]
    return SymbolicConfiguration(state, local_tapes, local_heads)


def _find_snapshot(case):
    for length in range(10):
        for bits in product("01", repeat=length):
            prefix = "".join(bits)
            source = OrdinarySGOuterIncremental(audit=True, background_work_budget=200000)
            for ch in prefix:
                source.append(ch)
            for bit in "01":
                record = deepcopy(source).append(bit)
                if record.case is case:
                    return source, bit, record
    raise AssertionError(case)


def test_case1_and_case4_complete_to_source_output():
    fabric = _fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constants = build_constant_case_rows(fabric)
    interpreter = LazySparseFabricInterpreter(
        fabric, dispatcher.rows + constants.rows
    )

    for case in (
        UpdateCase.ONE_BOTH_SURVIVE,
        UpdateCase.FOUR_FIRST_SURVIVES,
    ):
        source, bit, expected = _find_snapshot(case)
        config = _configuration(fabric, source, bit)
        for _ in range(2_000_000):
            if config.state in (SOURCE_DONE_0, SOURCE_DONE_1):
                break
            interpreter.step(config)
        else:
            raise TimeoutError((case, config.state))
        actual_output = config.state == SOURCE_DONE_1
        assert actual_output == expected.output
        if case is UpdateCase.FOUR_FIRST_SURVIVES:
            t = fabric.extra_tapes
            assert config.tapes[t["SECOND"]][0] == UNKNOWN
            assert config.tapes[t["LAZY_MODE"]][0] == "C"
            assert config.tapes[t["COPY_NEEDED"]][0] == "1"
            assert config.tapes[t["K_SIGN"]][0] == SIGN_ZERO
            for name in ("L33_CURRENT", "L33_LAG", "L33_COPY"):
                assert hz.materialize(_component_materialize(fabric, config, name)) == ("#",)
            bg = _component_materialize(fabric, config, "BG_RETURN")
            layout = fabric.layout("BG_RETURN")
            assert bg.tapes[0].get(bg.heads[0]) == BOTTOM
