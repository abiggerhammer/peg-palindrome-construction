"""Finite one-cell transducer for the three Lemma-3.2 pattern streams.

For a frozen binary word ``a`` it writes, in linear time,

* ``a``;
* ``a @ reverse(a)``;
* ``reverse(a) @ a``.

The source tape has three read heads: one forward head for the first pass, one
backward head, and a second forward head for the final suffix pass.  Each
transition moves every head by at most one cell and the table is independent of
``a`` and its length.
"""

from __future__ import annotations

from dataclasses import dataclass

from flat_multihead import FlatMultiheadMachine, MultiheadConfiguration, MultiheadTableBuilder
from flat_tm import Shift

BLANK = "_"
LEFT = "$"
RIGHT = "!"
SEP = "@"
ZERO = "0"
ONE = "1"

F1, R, F2, WP, WPRE, WSUF = range(6)
HEAD_TO_TAPE = (0, 0, 0, 1, 2, 3)
TAPE_ALPHABETS = (
    (BLANK, LEFT, RIGHT, ZERO, ONE),
    (BLANK, ZERO, ONE),
    (BLANK, ZERO, ONE, SEP),
    (BLANK, ZERO, ONE, SEP),
)

COPY_FORWARD = "PREP_COPY_FORWARD"
WRITE_PREFIX_SEP = "PREP_WRITE_PREFIX_SEP"
COPY_REVERSE = "PREP_COPY_REVERSE"
WRITE_SUFFIX_SEP = "PREP_WRITE_SUFFIX_SEP"
COPY_SUFFIX_FORWARD = "PREP_COPY_SUFFIX_FORWARD"
HALT = "PREP_HALT"


def _same():
    return (None,) * 6


def build_machine() -> FlatMultiheadMachine:
    b = MultiheadTableBuilder(
        blank=BLANK,
        tape_alphabets=TAPE_ALPHABETS,
        head_to_tape=HEAD_TO_TAPE,
    )
    stay = (Shift.STAY,) * 6

    for symbol in (ZERO, ONE):
        b.add(
            COPY_FORWARD,
            (symbol, None, None, BLANK, BLANK, None),
            COPY_FORWARD,
            (None, None, None, symbol, symbol, None),
            (Shift.RIGHT, Shift.STAY, Shift.STAY,
             Shift.RIGHT, Shift.RIGHT, Shift.STAY),
        )
    b.add(
        COPY_FORWARD,
        (RIGHT, None, None, BLANK, BLANK, None),
        WRITE_PREFIX_SEP,
        _same(),
        stay,
    )
    b.add(
        WRITE_PREFIX_SEP,
        (None, None, None, None, BLANK, None),
        COPY_REVERSE,
        (None, None, None, None, SEP, None),
        (Shift.STAY, Shift.STAY, Shift.STAY,
         Shift.STAY, Shift.RIGHT, Shift.STAY),
    )

    for symbol in (ZERO, ONE):
        b.add(
            COPY_REVERSE,
            (None, symbol, None, None, BLANK, BLANK),
            COPY_REVERSE,
            (None, None, None, None, symbol, symbol),
            (Shift.STAY, Shift.LEFT, Shift.STAY,
             Shift.STAY, Shift.RIGHT, Shift.RIGHT),
        )
    b.add(
        COPY_REVERSE,
        (None, LEFT, None, None, BLANK, BLANK),
        WRITE_SUFFIX_SEP,
        _same(),
        stay,
    )
    b.add(
        WRITE_SUFFIX_SEP,
        (None, None, None, None, None, BLANK),
        COPY_SUFFIX_FORWARD,
        (None, None, None, None, None, SEP),
        (Shift.STAY, Shift.STAY, Shift.STAY,
         Shift.STAY, Shift.STAY, Shift.RIGHT),
    )

    for symbol in (ZERO, ONE):
        b.add(
            COPY_SUFFIX_FORWARD,
            (None, None, symbol, None, None, BLANK),
            COPY_SUFFIX_FORWARD,
            (None, None, None, None, None, symbol),
            (Shift.STAY, Shift.STAY, Shift.RIGHT,
             Shift.STAY, Shift.STAY, Shift.RIGHT),
        )
    b.add(
        COPY_SUFFIX_FORWARD,
        (None, None, RIGHT, None, None, BLANK),
        HALT,
        _same(),
        stay,
    )
    return b.build(halting_states={HALT})


MACHINE = build_machine()


def _write(word: str) -> dict[int, str]:
    return {i: ch for i, ch in enumerate(word) if ch != BLANK}


def initial_configuration(word: str) -> MultiheadConfiguration:
    if not word or any(ch not in (ZERO, ONE) for ch in word):
        raise ValueError("word must be a nonempty binary string")
    source = LEFT + word + RIGHT
    return MultiheadConfiguration(
        state=COPY_FORWARD,
        tapes=[_write(source), {}, {}, {}],
        heads=[1, len(word), 1, 0, 0, 0],
    )


def output_word(config: MultiheadConfiguration, tape: int, end: int) -> str:
    return "".join(config.tapes[tape].get(i, BLANK) for i in range(end))


@dataclass(frozen=True)
class PreparedPatterns:
    plain: str
    prefix: str
    suffix: str
    steps: int
    states: int
    transitions: int


def run_prepare(word: str) -> PreparedPatterns:
    config = initial_configuration(word)
    steps = MACHINE.run(config)
    plain = output_word(config, 1, config.heads[WP])
    prefix = output_word(config, 2, config.heads[WPRE])
    suffix = output_word(config, 3, config.heads[WSUF])
    assert plain == word
    assert prefix == word + SEP + word[::-1]
    assert suffix == word[::-1] + SEP + word
    return PreparedPatterns(
        plain, prefix, suffix, steps, len(MACHINE.states), len(MACHINE.delta)
    )


if __name__ == "__main__":
    for sample in ("0", "0110", "010001"):
        print(run_prepare(sample))
