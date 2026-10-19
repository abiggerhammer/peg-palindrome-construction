from copy import deepcopy
from itertools import product

import checkpoint_reusable_tm as reusable
import history_zipper_ordinary_tm as hz
from build_outer_service_fabric import build_fabric
from ordinary_unary_counter import Sign, UnaryCounter
from sg_outer_constant_cases import SOURCE_DONE_0, SOURCE_DONE_1, build_constant_case_rows
from sg_outer_dispatcher_table import (
    KNOWN, LEFT_AFTER1, LEFT_AFTER2, LEFT_AT, LEFT_EXACT,
    MID_AFTER, MID_AT, MID_BEFORE, NO, READ0, READ1,
    SIGN_NEG, SIGN_POS, SIGN_ZERO, UNKNOWN, build_dispatcher_rows,
)
from sg_outer_incremental import OrdinarySGOuterIncremental
from sg_outer_ordinary import LeftRelation, MidRelation
from sg_outer_remaining_cases import build_remaining_case_rows
from sg_zero_ratio import UpdateCase
from sparse_registered_linker import LazySparseFabricInterpreter, SparseFabricConfiguration
from symbolic_tm import SymbolicConfiguration
from unary_counter_ordinary_tm import READY


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


def _put_symbolic(fabric, tapes, heads, name, config):
    layout = fabric.layout(name)
    adapter = layout.adapter
    for local in range(len(adapter.tape_alphabets)):
        tapes[layout.tape_start + local] = dict(config.tapes[local])
        heads[layout.tape_start + local] = config.heads[local]
    tapes[layout.register_tape][0] = layout.qsymbol(adapter.state_to_id[config.state])


def _put_counter(fabric, tapes, heads, name, counter):
    cfg = SymbolicConfiguration(READY, [dict(counter.tape)], [counter.head])
    _put_symbolic(fabric, tapes, heads, name, cfg)


def _configuration(fabric, source, bit):
    tapes = [dict() for _ in range(fabric.tape_count)]
    heads = [0] * fabric.tape_count
    for name in ("B", "BP", "LB", "LBP", "BG", "BGL"):
        _put_symbolic(fabric, tapes, heads, name, source.cursors[name])
    for name in ("L33_CURRENT", "L33_LAG", "L33_COPY"):
        _put_symbolic(fabric, tapes, heads, name, hz.initial_configuration(("#",), reader=0))

    counter_values = {
        "GAP": source.gap,
        "K_MAG": source.k.magnitude,
        "BG_RETURN": source.bg_return,
    }
    for name in (
        "RADIUS", "QUOTA", "LENGTH", "RESTORE", "CANDIDATE",
        "TARGET", "SCRATCH", "SCAN", "CLOCK",
    ):
        counter_values[name] = UnaryCounter.zero()
    for name, counter in counter_values.items():
        _put_counter(fabric, tapes, heads, name, counter)

    checkpoint = reusable.initial_configuration("0")
    reusable.run_to_result(checkpoint)
    reusable.retire_result(checkpoint)
    layout = fabric.layout("CHECKPOINT")
    adapter = layout.adapter
    for local in range(len(adapter.tape_alphabets)):
        tapes[layout.tape_start + local] = dict(checkpoint.tapes[local])
        heads[layout.tape_start + local] = checkpoint.heads[local]
    tapes[layout.register_tape][0] = layout.qsymbol(adapter.clean_ready_state_id)

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


def _counter_value(fabric, config, name):
    layout = fabric.layout(name)
    pos = config.heads[layout.tape_start]
    count = 0
    tape = config.tapes[layout.tape_start]
    while tape.get(pos, "_") == "1":
        count += 1
        pos -= 1
    assert tape.get(pos, "_") == "#"
    return count


def _find_case2_snapshots(limit=2):
    found = []
    for length in range(10):
        for bits in product("01", repeat=length):
            source = OrdinarySGOuterIncremental(audit=True, background_work_budget=200000)
            for ch in bits:
                source.append(ch)
            for bit in "01":
                expected_machine = deepcopy(source)
                record = expected_machine.append(bit)
                if record.case is UpdateCase.TWO_BOTH_FAIL:
                    found.append((deepcopy(source), bit, expected_machine, record))
                    if len(found) >= limit:
                        return found
    return found


def _signed_counter_value(fabric, config, name="K_MAG", sign_tape="K_SIGN"):
    value = _counter_value(fabric, config, name)
    sign = config.tapes[fabric.extra_tapes[sign_tape]][0]
    if sign == SIGN_NEG:
        return -value
    if sign == SIGN_ZERO:
        assert value == 0
        return 0
    assert sign == SIGN_POS
    return value


def test_case2_shared_recover_matches_incremental_model():
    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constants = build_constant_case_rows(fabric)
    remaining = build_remaining_case_rows(fabric, background_budget=8, include_case5=False, include_case6=False)
    interpreter = LazySparseFabricInterpreter(
        fabric, dispatcher.rows + constants.rows + remaining.rows,
        deferred_checkpoint_calls=remaining.deferred_checkpoint_calls,
    )
    snapshots = _find_case2_snapshots()
    assert snapshots
    for source, bit, expected, record in snapshots:
        config = _configuration(fabric, source, bit)
        for _ in range(2_000_000):
            if config.state in (SOURCE_DONE_0, SOURCE_DONE_1):
                break
            interpreter.step(config)
        else:
            raise TimeoutError((source.word, bit, config.state))
        t = fabric.extra_tapes
        assert (config.state == SOURCE_DONE_1) == record.output
        assert config.tapes[t["SECOND"]][0] == KNOWN
        assert config.tapes[t["B_REL"]][0] == _mid(expected.b_rel)
        assert config.tapes[t["BP_REL"]][0] == _mid(expected.bp_rel)
        assert config.tapes[t["BG_REL"]][0] == _mid(expected.bg_rel)
        assert config.tapes[t["LB_REL"]][0] == _left(expected.lb_rel)
        assert config.tapes[t["LBP_REL"]][0] == _left(expected.lbp_rel)
        assert config.tapes[t["BGL_REL"]][0] == _left(expected.bgl_rel)
        assert _counter_value(fabric, config, "GAP") == expected.gap.value()
        assert _signed_counter_value(fabric, config) == expected.k.value()


def _find_case3_snapshots():
    # Minimal representatives of the at-end and full-recovery branches.
    cases = (("", "0"), ("00", "0"))
    result = []
    for word, bit in cases:
        source = OrdinarySGOuterIncremental(audit=True, background_work_budget=200000)
        for ch in word:
            source.append(ch)
        expected = deepcopy(source)
        record = expected.append(bit)
        assert record.case is UpdateCase.THREE_SECOND_SURVIVES
        result.append((source, bit, expected, record))
    return result


def test_case3_promotion_and_subpaths_match_incremental_model():
    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constants = build_constant_case_rows(fabric)
    remaining = build_remaining_case_rows(fabric, background_budget=8, include_case5=False, include_case6=False)
    interpreter = LazySparseFabricInterpreter(
        fabric, dispatcher.rows + constants.rows + remaining.rows,
        deferred_checkpoint_calls=remaining.deferred_checkpoint_calls,
    )
    snapshots = _find_case3_snapshots()
    assert snapshots
    for source, bit, expected, record in snapshots:
        config = _configuration(fabric, source, bit)
        for _ in range(5_000_000):
            if config.state in (SOURCE_DONE_0, SOURCE_DONE_1):
                break
            interpreter.step(config)
        else:
            name = remaining.state_names.get(config.state)
            raise TimeoutError((source.word, bit, config.state, name))
        t = fabric.extra_tapes
        assert (config.state == SOURCE_DONE_1) == record.output
        assert config.tapes[t["SECOND"]][0] == (KNOWN if expected.bp is not None else UNKNOWN)
        assert config.tapes[t["B_REL"]][0] == _mid(expected.b_rel)
        assert config.tapes[t["BP_REL"]][0] == _mid(expected.bp_rel)
        assert config.tapes[t["BG_REL"]][0] == _mid(expected.bg_rel)
        assert config.tapes[t["LB_REL"]][0] == _left(expected.lb_rel)
        assert config.tapes[t["LBP_REL"]][0] == _left(expected.lbp_rel)
        assert config.tapes[t["BGL_REL"]][0] == _left(expected.bgl_rel)
        assert _counter_value(fabric, config, "GAP") == expected.gap.value()
        assert _signed_counter_value(fabric, config) == expected.k.value()


def test_rebuilt_all_six_case_bodies_repeated_sequence():
    word = "0011000"
    expected_cases = [3, 1, 2, 1, 4, 5, 6]
    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constants = build_constant_case_rows(fabric)
    remaining = build_remaining_case_rows(
        fabric, background_budget=8, include_case5=True, include_case6=True
    )
    interpreter = LazySparseFabricInterpreter(
        fabric, dispatcher.rows + constants.rows + remaining.rows,
        deferred_checkpoint_calls=remaining.deferred_checkpoint_calls,
    )
    seed = OrdinarySGOuterIncremental(audit=True, background_work_budget=8)
    config = _configuration(fabric, seed, word[0])
    seen = []
    for index, bit in enumerate(word):
        if index:
            config.state = READ0 if bit == "0" else READ1
        for _ in range(30_000_000):
            if config.state in (SOURCE_DONE_0, SOURCE_DONE_1):
                break
            interpreter.step(config)
        else:
            raise TimeoutError((index, bit, config.state, remaining.state_names.get(config.state)))
        case = int(config.tapes[fabric.extra_tapes["CASE"]][0])
        seen.append(case)
        prefix = word[: index + 1]
        assert (config.state == SOURCE_DONE_1) == (
            len(prefix) % 2 == 0 and prefix == prefix[::-1]
        )
        # Whenever the second midpoint is known, the two unary values are the
        # exact mathematical invariant, independent of background pacing.
        second = config.tapes[fabric.extra_tapes["SECOND"]][0]
        if second == KNOWN:
            from sg_zero_ratio import b3_pair
            bval, bpval = b3_pair(prefix)
            assert _counter_value(fabric, config, "GAP") == bpval - bval
            assert _signed_counter_value(fabric, config) == 16 * (bpval - bval) - (len(prefix) - bval)
    assert seen == expected_cases


def test_case3_small_gap_uses_bounded_local_checkpoint():
    # At length 66, the old invariant is B=33, B'=35 and k=-1.  Appending
    # 1 is case 3 with a small old gap; the bounded 4d local scan finds the
    # next midpoint at 37.
    word = "0011" * 16 + "00"
    bit = "1"
    source = OrdinarySGOuterIncremental(audit=True, background_work_budget=8)
    for ch in word:
        source.append(ch)
    expected = deepcopy(source)
    record = expected.append(bit)
    assert record.case is UpdateCase.THREE_SECOND_SURVIVES
    assert (source.b, source.bp, source.k.value()) == (33, 35, -1)
    assert (expected.b, expected.bp, expected.k.value()) == (35, 37, 0)

    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constants = build_constant_case_rows(fabric)
    remaining = build_remaining_case_rows(fabric, background_budget=8)
    interpreter = LazySparseFabricInterpreter(
        fabric, dispatcher.rows + constants.rows + remaining.rows,
        deferred_checkpoint_calls=remaining.deferred_checkpoint_calls,
    )
    config = _configuration(fabric, source, bit)
    visited_local = False
    for _ in range(5_000_000):
        if config.state in (SOURCE_DONE_0, SOURCE_DONE_1):
            break
        name = remaining.state_names.get(config.state, "")
        visited_local |= name.startswith("C3_LOCAL")
        interpreter.step(config)
    else:
        raise TimeoutError((config.state, remaining.state_names.get(config.state)))

    assert visited_local
    assert config.state == SOURCE_DONE_0
    assert config.tapes[fabric.extra_tapes["SECOND"]][0] == KNOWN
    assert _counter_value(fabric, config, "GAP") == 2
    assert _signed_counter_value(fabric, config) == 0


def test_case5_search_is_paused_and_case6_resumes_checkpoint():
    # With a moderate audit budget, this sequence reaches an actual paused
    # checkpoint SEARCH in case 5.  The following case 6 must resume that
    # exact registered checkpoint state to READY before shared RECOVER.
    word = "0011000"
    budget = 1024
    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constants = build_constant_case_rows(fabric)
    remaining = build_remaining_case_rows(fabric, background_budget=budget)
    interpreter = LazySparseFabricInterpreter(
        fabric, dispatcher.rows + constants.rows + remaining.rows,
        deferred_checkpoint_calls=remaining.deferred_checkpoint_calls,
    )
    single_step = next(
        spec for spec in remaining.deferred_checkpoint_calls
        if spec.mode == "single_step"
    )
    run_to_result = next(
        spec for spec in remaining.deferred_checkpoint_calls
        if spec.mode == "run_to_result"
    )

    oracle = OrdinarySGOuterIncremental(
        audit=True, background_work_budget=budget
    )
    config = _configuration(fabric, oracle, word[0])
    saw_search_step = False
    saw_case6_resume = False
    for index, bit in enumerate(word):
        if index:
            config.state = READ0 if bit == "0" else READ1
        expected = oracle.append(bit)
        for _ in range(2_000_000):
            if config.state in (SOURCE_DONE_0, SOURCE_DONE_1):
                break
            phase = config.tapes[fabric.extra_tapes["L33_PHASE"]].get(0, "_")
            saw_search_step |= config.state == single_step.state and phase == "S"
            saw_case6_resume |= config.state == run_to_result.state
            interpreter.step(config)
        else:
            raise TimeoutError((index, config.state, remaining.state_names.get(config.state)))
        assert int(config.tapes[fabric.extra_tapes["CASE"]][0]) == expected.case.value
        assert (config.state == SOURCE_DONE_1) == expected.output

    assert saw_search_step
    assert saw_case6_resume
    assert config.tapes[fabric.extra_tapes["LAZY_MODE"]][0] == "N"
    assert config.tapes[fabric.extra_tapes["L33_PHASE"]][0] == "I"
