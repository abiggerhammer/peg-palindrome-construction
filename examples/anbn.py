from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compile_sa_to_peg import compile_to_peg
from scaffold import (
    Exists,
    Guard,
    LabelIs,
    Missing,
    SymbolicScaffoldingAutomaton,
    Target,
    Transition,
)


def build_anbn_automaton() -> SymbolicScaffoldingAutomaton:
    """A one-persistent-stack scaffolding automaton for 0^n 1^n.

    Its compiled PEG recognizes the reverse language 1^n 0^n. This example
    exercises push, pop, empty-stack detection, and an edge target whose path
    is permitted to become invalid (which correctly creates a missing edge).
    """

    START = "start"
    ZERO = "zero_nonempty"
    ONE = "one_nonempty"
    DONE = "one_empty"
    DEAD = "dead"

    base = Guard.all(LabelIs((), None))
    singleton = Guard.all(LabelIs((), "Z"), Missing((0,)))
    multiple = Guard.all(LabelIs((), "Z"), Exists((0,)))
    nonempty = Guard.all(LabelIs((), "Z"))
    empty = Guard.all(LabelIs((), "E"))
    any_guard = Guard.all()

    transitions = [
        Transition(START, "0", base, ZERO, "Z", (Target.none(),), "start-push"),
        Transition(START, "1", base, DEAD, "E", (Target.none(),), "bad-leading-one"),
        # Push a zero. The empty target path denotes the old top node.
        Transition(ZERO, "0", nonempty, ZERO, "Z", (Target.via(()),), "push-zero"),
        # Pop the first one.
        Transition(ZERO, "1", singleton, DONE, "E", (Target.none(),), "pop-last-zero"),
        Transition(ZERO, "1", multiple, ONE, "Z", (Target.via((0, 0)),), "pop-zero"),
        # Continue popping ones.
        Transition(ONE, "1", singleton, DONE, "E", (Target.none(),), "pop-final"),
        Transition(ONE, "1", multiple, ONE, "Z", (Target.via((0, 0)),), "pop-more"),
        # A zero after the one phase is fatal. We no longer need the stack.
        Transition(ONE, "0", nonempty, DEAD, "E", (Target.none(),), "zero-after-one"),
        # Any additional input after exact balance is fatal.
        Transition(DONE, "0", empty, DEAD, "E", (Target.none(),), "input-after-done-0"),
        Transition(DONE, "1", empty, DEAD, "E", (Target.none(),), "input-after-done-1"),
        # Dead state is absorbing and deliberately discards all work data.
        Transition(DEAD, "0", any_guard, DEAD, "E", (Target.none(),), "dead-0"),
        Transition(DEAD, "1", any_guard, DEAD, "E", (Target.none(),), "dead-1"),
    ]

    return SymbolicScaffoldingAutomaton(
        alphabet=("0", "1"),
        degree=1,
        radius=2,
        states=(START, ZERO, ONE, DONE, DEAD),
        initial_state=START,
        accepting_states=frozenset({START, DONE}),
        transitions=tuple(transitions),
    )


if __name__ == "__main__":
    automaton = build_anbn_automaton()
    grammar = compile_to_peg(automaton)
    out = ROOT / "generated_1n0n.peg"
    out.write_text(grammar.to_text(), encoding="utf-8")
    print(f"wrote {out}")
