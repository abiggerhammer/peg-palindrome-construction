from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bounded_delay_macro_compiler import (
    INITIAL_SCAFFOLD_STATE,
    compile_small_bounded_delay_to_scaffold,
)
from compile_sa_to_peg import compile_to_peg
from indexed_block_macro_expander import (
    INITIAL_STATE,
    SINK_STATE,
    FullNeighbourhood,
    TransitionIndex,
    base_neighbourhood,
    neighbourhood_expression,
    neighbourhood_name,
    normal_state,
    state_name,
    total_delta_plan,
    transition_expression,
)
from lmr_rule_expander import LMRNames, transition_expression as lmr_transition_expression
from peg import And, Not, Ref, SeqExpr
from scheduled_source_composition import ScheduledAction, ScheduledRow
from tests.test_bounded_delay_macro_compiler import crossing_machine


def _refs(expr):
    if isinstance(expr, Ref):
        return {expr.name}
    if isinstance(expr, (And, Not)):
        return _refs(expr.body)
    if isinstance(expr, SeqExpr):
        out = set()
        for part in expr.parts:
            out |= _refs(part)
        return out
    body = getattr(expr, "body", None)
    if body is not None:
        return _refs(body)
    alternatives = getattr(expr, "alternatives", ())
    out = set()
    for item in alternatives:
        out |= _refs(item)
    return out


def test_literal_backend_uses_unique_initial_state_and_exact_lmr_fold():
    automaton = compile_small_bounded_delay_to_scaffold(
        crossing_machine(), block_size=2, max_transitions=20_000
    )
    assert automaton.initial_state == INITIAL_SCAFFOLD_STATE
    assert all(t.next_state != INITIAL_SCAFFOLD_STATE for t in automaton.transitions)
    assert INITIAL_SCAFFOLD_STATE in automaton.accepting_states

    grammar = compile_to_peg(automaton)
    names = LMRNames.from_automaton(automaton)
    for index in (0, 1, len(automaton.transitions) - 1):
        assert grammar.rules[f"Transition_{index}"] == lmr_transition_expression(
            automaton, index, names
        )


def test_exact_neighbourhood_rule_mentions_every_present_and_missing_path():
    leaf = FullNeighbourhood({"kind": "leaf"}, (None, None))
    child = FullNeighbourhood({"kind": "child"}, (leaf, None))
    root = FullNeighbourhood({"kind": "root"}, (None, child))
    refs = _refs(neighbourhood_expression(root))
    assert "Path_0" in refs
    assert "Path_1" in refs
    assert "Path_1_0" in refs
    assert "Path_1_1" in refs
    assert neighbourhood_name(root).startswith("Neighbourhood_")


def _toy_rows():
    return iter((
        ScheduledRow(
            0, "0", (),
            ScheduledAction(0, writes=((0, "X"),), moves=((0, 1),), input_move=1, emit=0),
        ),
        ScheduledRow(
            0, "1", (),
            ScheduledAction(0, input_move=1, emit=1),
        ),
    ))


def test_executable_total_delta_oracle_handles_initial_and_sink_cases():
    base = base_neighbourhood(2)
    zero = total_delta_plan(
        TransitionIndex(INITIAL_STATE, "0", base),
        row_factory=_toy_rows,
        tape_count=1,
        blank="_",
        initial_boundary_state=0,
        initial_output=1,
        block_size=2,
        delay_bound=1,
    )
    assert zero["kind"] == "canonical"
    assert zero["next_state"] == normal_state(0, 0)
    assert zero["label"]["output"] == 0
    assert zero["primitive_steps"] == 1

    one = total_delta_plan(
        TransitionIndex(INITIAL_STATE, "1", base),
        row_factory=_toy_rows,
        tape_count=1,
        blank="_",
        initial_boundary_state=0,
        initial_output=1,
        block_size=2,
        delay_bound=1,
    )
    assert one["next_state"] == normal_state(0, 1)
    assert one["label"]["output"] == 1

    unreachable = total_delta_plan(
        TransitionIndex(normal_state(0, 0), "0", base),
        row_factory=_toy_rows,
        tape_count=1,
        blank="_",
        initial_boundary_state=0,
        initial_output=1,
        block_size=2,
        delay_bound=1,
    )
    assert unreachable["kind"] == "sink_completion"
    assert unreachable["next_state"] == SINK_STATE


def test_indexed_transition_is_the_standard_lmr_abbreviation():
    base = base_neighbourhood(2)
    index = TransitionIndex(INITIAL_STATE, "0", base)
    refs = _refs(transition_expression(index))
    assert state_name(INITIAL_STATE) in refs
    assert neighbourhood_name(base) in refs
