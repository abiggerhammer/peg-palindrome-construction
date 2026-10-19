from itertools import product
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bounded_delay_macro_compiler import (
    BoundedDelayMachine,
    DelayAction,
    DelayRow,
    compile_small_bounded_delay_to_peg,
    run_bounded_delay,
)
from realtime_mtm import Move


def crossing_machine() -> BoundedDelayMachine:
    # One primitive step per physical symbol, but a two-cell macro block.  Zeros
    # walk right and reject; ones walk left and accept.  This exercises aligned
    # block crossings and both persistent stack directions.
    alphabet = ("_", "X")
    return BoundedDelayMachine(
        input_alphabet=("0", "1"),
        tape_alphabets=(alphabet,),
        blank="_",
        states=("q",),
        boundary_states=frozenset({"q"}),
        initial_state="q",
        initial_output=1,
        rows=(
            DelayRow(
                "q", "0", (None,),
                DelayAction("q", ("X",), (Move.RIGHT,), emit=0),
            ),
            DelayRow(
                "q", "1", (None,),
                DelayAction("q", (None,), (Move.LEFT,), emit=1),
            ),
        ),
        delay_bound=1,
    )


def two_step_machine() -> BoundedDelayMachine:
    alphabet = ("_", "X")
    return BoundedDelayMachine(
        input_alphabet=("0", "1"),
        tape_alphabets=(alphabet,),
        blank="_",
        states=("q", "r0", "r1"),
        boundary_states=frozenset({"q"}),
        initial_state="q",
        initial_output=0,
        rows=(
            DelayRow("q", "0", (None,), DelayAction("r0", ("X",), (Move.RIGHT,))),
            DelayRow("q", "1", (None,), DelayAction("r1", (None,), (Move.LEFT,))),
            DelayRow("r0", None, (None,), DelayAction("q", (None,), (Move.STAY,), emit=0)),
            DelayRow("r1", None, (None,), DelayAction("q", ("X",), (Move.STAY,), emit=1)),
        ),
        delay_bound=2,
    )


def test_block_macro_compiler_crosses_aligned_blocks():
    machine = crossing_machine()
    grammar = compile_small_bounded_delay_to_peg(
        machine, block_size=2, max_transitions=20_000
    )
    for length in range(6):
        for bits in product("01", repeat=length):
            word = "".join(bits)
            assert grammar.recognize(word[::-1]) == run_bounded_delay(machine, word), word


def test_block_macro_compiler_closes_two_primitive_steps():
    machine = two_step_machine()
    # Block size equals the certified delay.  The literal expansion is larger,
    # so keep the test words short while still crossing both boundaries.
    grammar = compile_small_bounded_delay_to_peg(
        machine, block_size=2, max_transitions=60_000
    )
    for length in range(5):
        for bits in product("01", repeat=length):
            word = "".join(bits)
            assert grammar.recognize(word[::-1]) == run_bounded_delay(machine, word), word
