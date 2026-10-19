"""Explicit multihead implementation of Fischer--Paterson Algorithm Y.

The technical report represents the KMP failure function by unary difference
blocks ``Delta(i)=1+P(i)-P(i+1)``.  Its Algorithm Y uses two heads A,B on the
pattern tape, two heads C,D on the Delta tape, and unary counters S,T.  This
module instantiates that description as a literal finite one-cell transition
table.

For clarity the already audited four-head C/S/T/U primitive is lifted into a
seven-head machine:

* A,B share the read-only pattern tape Z;
* C,D share the unary Delta tape Y;
* S,T,U have one tape/head apiece.

U is a convenience scratch counter used by our reversible copy/restore
microprogram.  It does not change the algorithmic invariant.
"""

from __future__ import annotations

from dataclasses import dataclass

from flat_multihead import (
    FlatMultiheadMachine,
    MultiheadConfiguration,
    MultiheadTableBuilder,
)
from flat_tm import Shift
from fp_delta import delta_blocks, failure_positions
from fp_delta_micro import (
    ADV_START,
    BACK_START,
    HALT as PRIMITIVE_HALT,
    MACHINE as PRIMITIVE,
)

BLANK = "_"
MARK = "#"
SENTINEL = "$"
SEP = "@"
END = "!"
ZERO = "0"
ONE = "1"

# Head indices.
A, B, C, D, S, T, U = range(7)
HEAD_TO_TAPE = (0, 0, 1, 1, 2, 3, 4)
TAPE_ALPHABETS = (
    (BLANK, SENTINEL, ZERO, ONE, SEP, END),
    (BLANK, MARK, ZERO, ONE),
    (BLANK, MARK, ONE),
    (BLANK, MARK, ONE),
    (BLANK, MARK, ONE),
)

HALT = "Y_HALT"
TEST_MOVE = "Y_TEST_MOVE"
TEST_COMPARE = "Y_TEST_COMPARE"
AFTER_ADV = "Y_AFTER_ADV"
AFTER_BACK = "Y_AFTER_BACK"
SENTINEL_ONE = "Y_SENTINEL_ONE"
SENTINEL_ZERO = "Y_SENTINEL_ZERO"
AFTER_SENTINEL = "Y_AFTER_SENTINEL"
AFTER_PEEK = "Y_AFTER_PEEK"
MISMATCH_RESTORE = "Y_MISMATCH_RESTORE"
MISMATCH_DECIDE = "Y_MISMATCH_DECIDE"


def _preserve() -> tuple[None, ...]:
    return (None,) * 7


def build_algorithm_y_machine() -> FlatMultiheadMachine:
    b = MultiheadTableBuilder(
        blank=BLANK,
        tape_alphabets=TAPE_ALPHABETS,
        head_to_tape=HEAD_TO_TAPE,
    )
    stay = (Shift.STAY,) * 7

    # At the beginning of a stage A scans z_p (or the left sentinel for p=-1)
    # and B scans z_i.  The comparison is z_{p+1} versus z_{i+1}.
    for symbol in (SENTINEL, ZERO, ONE, SEP):
        b.add(
            TEST_MOVE,
            (symbol, None, None, None, None, None, None),
            TEST_COMPARE,
            _preserve(),
            (Shift.RIGHT, Shift.RIGHT, Shift.STAY, Shift.STAY,
             Shift.STAY, Shift.STAY, Shift.STAY),
        )

    # Equal symbols execute case (1).  A and B are already in their next-stage
    # positions; the lifted ADV primitive updates C and S while D terminates the
    # newly constructed Delta block with a zero.
    for symbol in (ZERO, ONE, SEP):
        b.add(
            TEST_COMPARE,
            (symbol, symbol, None, None, None, None, None),
            ADV_START,
            _preserve(),
            stay,
        )
    for left in (ZERO, ONE, SEP):
        for right in (ZERO, ONE, SEP):
            if left == right:
                continue
            b.add(
                TEST_COMPARE,
                (left, right, None, None, None, None, None),
                MISMATCH_RESTORE,
                _preserve(),
                (Shift.LEFT, Shift.LEFT, Shift.STAY, Shift.STAY,
                 Shift.STAY, Shift.STAY, Shift.STAY),
            )

    # After restoring the stage heads, p=-1 is visible as A scanning the
    # sentinel.  Otherwise case (3) follows one failure link.
    b.add(
        MISMATCH_RESTORE,
        (SENTINEL, None, None, None, None, None, None),
        SENTINEL_ONE,
        _preserve(),
        stay,
    )
    for symbol in (ZERO, ONE, SEP):
        b.add(
            MISMATCH_RESTORE,
            (symbol, None, None, None, None, None, None),
            BACK_START,
            _preserve(),
            stay,
        )

    # Case (2): p=-1.  Append d+1 followed by the block delimiter, advance B,
    # and leave A,C,S fixed at their sentinel/zero configuration.
    b.add(
        SENTINEL_ONE,
        (SENTINEL, None, None, BLANK, None, None, None),
        SENTINEL_ZERO,
        (None, None, None, ONE, None, None, None),
        (Shift.STAY, Shift.RIGHT, Shift.STAY, Shift.RIGHT,
         Shift.STAY, Shift.STAY, Shift.STAY),
    )
    b.add(
        SENTINEL_ZERO,
        (SENTINEL, None, None, BLANK, None, None, None),
        AFTER_SENTINEL,
        (None, None, None, ZERO, None, None, None),
        (Shift.STAY, Shift.STAY, Shift.STAY, Shift.RIGHT,
         Shift.STAY, Shift.STAY, Shift.STAY),
    )

    # Lift every concrete C/S/T/U transition.  A,B,D are normally stationary.
    valid = [set(alpha) for alpha in TAPE_ALPHABETS]
    for (state, reads4), action4 in PRIMITIVE.delta.items():
        # Ignore concrete wildcard expansions containing symbols outside the
        # narrower counter alphabets used by this machine.
        c_read, s_read, t_read, u_read = reads4
        if s_read not in valid[2] or t_read not in valid[3] or u_read not in valid[4]:
            continue

        next_state = action4.next_state
        if next_state == PRIMITIVE_HALT:
            next_state = AFTER_ADV if state == "ADV_SCAN" else AFTER_BACK

        reads = (None, None, c_read, None, s_read, t_read, u_read)
        writes = (
            None,
            None,
            action4.writes[0],
            None,
            action4.writes[1],
            action4.writes[2],
            action4.writes[3],
        )
        moves = (
            Shift.STAY,
            Shift.STAY,
            action4.moves[0],
            Shift.STAY,
            action4.moves[1],
            action4.moves[2],
            action4.moves[3],
        )

        # ADV_START also closes the current Delta block at D.
        if state == ADV_START:
            reads = (None, None, c_read, BLANK, s_read, t_read, u_read)
            writes = list(writes)
            writes[D] = ZERO
            writes = tuple(writes)
            moves = list(moves)
            moves[D] = Shift.RIGHT
            moves = tuple(moves)

        # Each old-S boundary consumed by the backpointer is one unit of case
        # (3): A moves left and D appends one unary symbol to d.
        if (
            state == "BACK_MOVE_PREP"
            and c_read == ZERO
            and t_read == ONE
            and action4.next_state == "BACK_CONSUME_BOUNDARY"
        ):
            reads = list(reads)
            reads[D] = BLANK
            reads = tuple(reads)
            writes = list(writes)
            writes[D] = ONE
            writes = tuple(writes)
            moves = list(moves)
            moves[A] = Shift.LEFT
            moves[D] = Shift.RIGHT
            moves = tuple(moves)

        b.add(state, reads, next_state, writes, moves)

    # Peek one square to the right of B.  The explicit endmarker avoids
    # smuggling the pattern length into finite control.
    for state in (AFTER_ADV, AFTER_BACK, AFTER_SENTINEL):
        b.add(
            state,
            (None, None, None, None, None, None, None),
            AFTER_PEEK,
            _preserve(),
            (Shift.STAY, Shift.RIGHT, Shift.STAY, Shift.STAY,
             Shift.STAY, Shift.STAY, Shift.STAY),
        )
    b.add(
        AFTER_PEEK,
        (None, END, None, None, None, None, None),
        HALT,
        _preserve(),
        stay,
    )
    for symbol in (ZERO, ONE, SEP):
        b.add(
            AFTER_PEEK,
            (None, symbol, None, None, None, None, None),
            TEST_MOVE,
            _preserve(),
            (Shift.STAY, Shift.LEFT, Shift.STAY, Shift.STAY,
             Shift.STAY, Shift.STAY, Shift.STAY),
        )

    return b.build(halting_states={HALT})


MACHINE = build_algorithm_y_machine()


def _write(word: str) -> dict[int, str]:
    return {i: ch for i, ch in enumerate(word) if ch != BLANK}


def initial_configuration(pattern: str) -> MultiheadConfiguration:
    if not pattern:
        raise ValueError("pattern must be nonempty")
    if any(ch not in (ZERO, ONE, SEP) for ch in pattern):
        raise ValueError("pattern contains a symbol outside the fixed alphabet")
    z = SENTINEL + pattern + END
    # Delta(-1)=1 is present before the first computed stage.
    y = MARK + ZERO + ONE + ZERO
    state = HALT if len(pattern) == 1 else TEST_MOVE
    return MultiheadConfiguration(
        state=state,
        tapes=[_write(z), _write(y), _write(MARK), _write(MARK), _write(MARK)],
        heads=[0, 1, 1, len(y), 1, 1, 1],
    )


def blocks_from_configuration(config: MultiheadConfiguration) -> tuple[int, ...]:
    end = config.heads[D]
    chars = "".join(config.tapes[1].get(i, BLANK) for i in range(end))
    if not chars.startswith(MARK + ZERO):
        raise AssertionError(chars)
    body = chars[1:]
    if not body.endswith(ZERO):
        raise AssertionError((chars, config.heads))
    runs = body.split(ZERO)
    # Leading delimiter and trailing delimiter create empty outside fields.
    assert runs[0] == "" and runs[-1] == ""
    return tuple(len(run) for run in runs[1:-1])


def failure_from_blocks(blocks: tuple[int, ...]) -> tuple[int, ...]:
    p = -1
    result = []
    for delta in blocks:
        p = 1 + p - delta
        result.append(p)
    return tuple(result)


@dataclass(frozen=True)
class AlgorithmYResult:
    pattern: str
    failure: tuple[int, ...]
    blocks: tuple[int, ...]
    steps: int
    transition_count: int


def run_algorithm_y(pattern: str) -> AlgorithmYResult:
    config = initial_configuration(pattern)
    steps = MACHINE.run(config)
    blocks = blocks_from_configuration(config)
    failure = failure_from_blocks(blocks)
    assert blocks == tuple(delta_blocks(pattern))
    assert failure == tuple(failure_positions(pattern))
    return AlgorithmYResult(pattern, failure, blocks, steps, len(MACHINE.delta))


if __name__ == "__main__":
    for sample in ("0", "00", "0100000", "01100110", "01@10"):
        print(run_algorithm_y(sample))
