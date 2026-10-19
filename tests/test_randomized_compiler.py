from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realtime_mtm import MTMAction, Move, RealtimeMultitapeMachine, compile_realtime_mtm_to_peg


def random_machine(seed: int, tape_count: int) -> RealtimeMultitapeMachine:
    rng = random.Random(seed)
    states = ("q0", "q1", "q2")
    tape_alphabet = ("_", "X")
    input_alphabet = ("0", "1")
    delta = {}

    for state in states:
        for inp in input_alphabet:
            for heads in itertools.product(tape_alphabet, repeat=tape_count):
                delta[(state, inp, tuple(heads))] = MTMAction(
                    next_state=rng.choice(states),
                    writes=tuple(rng.choice(tape_alphabet) for _ in range(tape_count)),
                    moves=tuple(rng.choice(tuple(Move)) for _ in range(tape_count)),
                )

    accepting = frozenset(q for q in states if rng.choice((False, True)))
    return RealtimeMultitapeMachine(
        input_alphabet=input_alphabet,
        tape_alphabet=tape_alphabet,
        blank="_",
        states=states,
        initial_state="q0",
        accepting_states=accepting,
        tape_count=tape_count,
        delta=delta,
    )


def test_random_total_machines_compile_correctly() -> None:
    # These are differential tests, not examples chosen to suit the compiler.
    # They exercise arbitrary combinations of writes, left/right moves, empty
    # stacks, revisiting old cells, multiple work tapes, and accepting states.
    for tape_count, seeds in ((1, range(8)), (2, range(4))):
        for seed in seeds:
            machine = random_machine(10_000 * tape_count + seed, tape_count)
            grammar = compile_realtime_mtm_to_peg(machine)
            for length in range(6):
                for bits in itertools.product("01", repeat=length):
                    text = "".join(bits)
                    assert grammar.recognize(text[::-1]) == machine.run(text), (
                        tape_count,
                        seed,
                        text,
                    )
