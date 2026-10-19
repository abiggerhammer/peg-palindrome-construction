"""Cell-by-cell Fischer--Paterson unary-Delta tape operations.

The logical ``DeltaCursor`` in :mod:`fp_delta` records a whole block traversal
as one Python operation.  This module replaces those traversals by a literal
finite four-tape Turing-machine table.  Its states and tape alphabet are
independent of the pattern and of every counter value.

Tapes
-----
``Y``
    ``# 0 1^Delta(-1) 0 1^Delta(0) ... 0``.  Head C scans the delimiter
    immediately before the block indexed by the current logical position.
``S``
    ``# 1^lambda(p)`` with the head on the first blank to the right.
``T`` and ``U``
    Empty scratch unary counters.  They are used to copy ``S`` without losing
    it before a backpointer walk.

The finite program has two entry states, ``ADV_START`` and ``BACK_START``, and
one halt state.  Every transition moves each head by at most one cell.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable

from flat_tm import FlatConfiguration, FlatMultitapeMachine, Shift, TableBuilder
from fp_delta import delta_blocks, failure_positions, jump_length

BLANK = "_"
MARK = "#"
ZERO = "0"
ONE = "1"
ALPHABET = (BLANK, MARK, ZERO, ONE)

Y, S, T, U = range(4)
HALT = "HALT"
ADV_START = "ADV_START"
BACK_START = "BACK_START"


def _same() -> tuple[None, None, None, None]:
    return (None, None, None, None)


def build_delta_primitive_machine() -> FlatMultitapeMachine:
    b = TableBuilder(ALPHABET, 4)
    stay = Shift.STAY

    # ADVANCE: C moves through one Delta block.  Each unary 1 crossed is
    # appended to S; the next zero delimiter is the new C position.
    b.add(
        ADV_START,
        (ZERO, BLANK, None, None),
        "ADV_SCAN",
        _same(),
        (Shift.RIGHT, stay, stay, stay),
    )
    b.add(
        "ADV_SCAN",
        (ONE, BLANK, None, None),
        "ADV_SCAN",
        (None, ONE, None, None),
        (Shift.RIGHT, Shift.RIGHT, stay, stay),
    )
    b.add(
        "ADV_SCAN",
        (ZERO, BLANK, None, None),
        HALT,
        _same(),
        (stay, stay, stay, stay),
    )

    # BACKPOINTER, phase 1: copy S to both T and U while scanning S left.
    b.add(
        BACK_START,
        (ZERO, BLANK, BLANK, BLANK),
        "BACK_COPY",
        _same(),
        (stay, Shift.LEFT, stay, stay),
    )
    b.add(
        "BACK_COPY",
        (None, ONE, BLANK, BLANK),
        "BACK_COPY",
        (None, None, ONE, ONE),
        (stay, Shift.LEFT, Shift.RIGHT, Shift.RIGHT),
    )
    b.add(
        "BACK_COPY",
        (None, MARK, BLANK, BLANK),
        "BACK_RESTORE_PREP",
        _same(),
        (stay, stay, stay, Shift.LEFT),
    )

    # Restore the S head to its conventional right-blank position, consuming U.
    b.add(
        "BACK_RESTORE_PREP",
        (None, None, None, ONE),
        "BACK_RESTORE_PREP",
        (None, None, None, BLANK),
        (stay, Shift.RIGHT, stay, Shift.LEFT),
    )
    b.add(
        "BACK_RESTORE_PREP",
        (None, ONE, None, MARK),
        "BACK_MOVE_PREP",
        _same(),
        (Shift.LEFT, Shift.RIGHT, Shift.LEFT, Shift.RIGHT),
    )

    # C now scans the cell immediately left of its old delimiter.  T scans its
    # last 1.  Cross exactly lambda(p) block delimiters.  Every Delta-tape 1
    # crossed removes one 1 from S, thereby changing lambda(p) to lambda(P(p)).
    b.add(
        "BACK_MOVE_PREP",
        (ONE, BLANK, ONE, BLANK),
        "BACK_ERASE_S",
        _same(),
        (stay, Shift.LEFT, stay, stay),
    )
    b.add(
        "BACK_MOVE_PREP",
        (ZERO, BLANK, ONE, BLANK),
        "BACK_CONSUME_BOUNDARY",
        (None, None, BLANK, None),
        (stay, stay, Shift.LEFT, stay),
    )
    b.add(
        "BACK_ERASE_S",
        (ONE, ONE, ONE, BLANK),
        "BACK_MOVE_PREP",
        (None, BLANK, None, None),
        (Shift.LEFT, stay, stay, stay),
    )
    b.add(
        "BACK_CONSUME_BOUNDARY",
        (ZERO, BLANK, MARK, BLANK),
        "BACK_CLEAN_T",
        _same(),
        (stay, stay, Shift.RIGHT, stay),
    )
    b.add(
        "BACK_CONSUME_BOUNDARY",
        (ZERO, BLANK, ONE, BLANK),
        "BACK_MOVE_PREP",
        _same(),
        (Shift.LEFT, stay, stay, stay),
    )
    b.add(
        "BACK_CLEAN_T",
        (ZERO, BLANK, BLANK, BLANK),
        HALT,
        _same(),
        (stay, stay, stay, stay),
    )

    return b.build(blank=BLANK, halting_states=(HALT,))


MACHINE = build_delta_primitive_machine()


def _write_word(word: str) -> dict[int, str]:
    return {i: symbol for i, symbol in enumerate(word) if symbol != BLANK}


def delta_layout(pattern: str) -> tuple[str, list[int]]:
    """Return Y contents and delimiter positions for logical p=-1..n-1."""

    blocks = delta_blocks(pattern)
    chars = [MARK]
    delimiters: list[int] = []
    for amount in blocks:
        delimiters.append(len(chars))
        chars.append(ZERO)
        chars.extend(ONE for _ in range(amount))
    delimiters.append(len(chars))  # p=n-1, after the last stored Delta block
    chars.append(ZERO)
    assert len(delimiters) == len(pattern) + 1
    return "".join(chars), delimiters


def make_configuration(pattern: str, position: int, operation: str) -> FlatConfiguration:
    if not (-1 <= position < len(pattern)):
        raise ValueError(position)
    y_word, delimiters = delta_layout(pattern)
    jump = 0 if position < 0 else jump_length(pattern, position)
    s_word = MARK + ONE * jump
    state = {"advance": ADV_START, "backpointer": BACK_START}[operation]
    return FlatConfiguration(
        state=state,
        tapes=[
            _write_word(y_word),
            _write_word(s_word),
            _write_word(MARK),
            _write_word(MARK),
        ],
        heads=[delimiters[position + 1], len(s_word), 1, 1],
    )


def unary_count(config: FlatConfiguration, tape: int) -> int:
    position = 1
    total = 0
    while config.tapes[tape].get(position, BLANK) == ONE:
        total += 1
        position += 1
    return total


def logical_position(pattern: str, config: FlatConfiguration) -> int:
    _, delimiters = delta_layout(pattern)
    try:
        index = delimiters.index(config.heads[Y])
    except ValueError as exc:
        raise AssertionError((pattern, config.heads[Y], delimiters)) from exc
    return index - 1


@dataclass(frozen=True)
class PrimitiveResult:
    operation: str
    old_position: int
    new_position: int
    microsteps: int
    old_jump: int
    new_jump: int


def run_primitive(pattern: str, position: int, operation: str) -> PrimitiveResult:
    config = make_configuration(pattern, position, operation)
    old_jump = unary_count(config, S)
    steps = MACHINE.run(config)
    new_position = logical_position(pattern, config)
    new_jump = unary_count(config, S)
    assert unary_count(config, T) == 0
    assert unary_count(config, U) == 0
    assert config.heads[S] == new_jump + 1
    assert config.heads[T] == 1 and config.heads[U] == 1
    return PrimitiveResult(
        operation,
        position,
        new_position,
        steps,
        old_jump,
        new_jump,
    )


class MicroDeltaCursor:
    """Persistent runner for the flat primitive table.

    An operation may be paused after any microstep and resumed later.  This is
    the exact facility needed by Galil's delayed ``C,S`` update.
    """

    def __init__(self, pattern: str, position: int = -1):
        self.pattern = pattern
        self.position = position
        self.config: FlatConfiguration | None = None
        self.operation: str | None = None
        self.total_microsteps = 0

    @property
    def busy(self) -> bool:
        return self.config is not None

    def start(self, operation: str) -> None:
        if self.busy:
            raise RuntimeError("primitive already running")
        self.operation = operation
        self.config = make_configuration(self.pattern, self.position, operation)

    def tick(self) -> bool:
        """Execute one cell step; return true exactly when the operation halts."""

        if self.config is None or self.operation is None:
            raise RuntimeError("no primitive running")
        MACHINE.step(self.config)
        self.total_microsteps += 1
        if self.config.state != HALT:
            return False
        new_position = logical_position(self.pattern, self.config)
        expected = (
            self.position + 1
            if self.operation == "advance"
            else failure_positions(self.pattern)[self.position]
        )
        assert new_position == expected
        self.position = new_position
        self.config = None
        self.operation = None
        return True

    def run_to_halt(self) -> int:
        before = self.total_microsteps
        while not self.tick():
            pass
        return self.total_microsteps - before


@dataclass(frozen=True)
class DeferredMatchStep:
    symbol: str
    full_match: bool
    matched_length: int
    microsteps: int
    backpointers: int
    pending_advances: int


class DeferredDeltaKMPMatcher:
    """Galil-style delayed ``C,S`` updates with cell-level unary walks.

    Pattern comparisons use the logical KMP position.  The physical unary-Delta
    cursor may lag during a run of successful matches.  Only a fixed number of
    primitive microsteps is spent after each match.  On a mismatch the updater
    catches up before any failure-link walk, exactly as in Galil Section 4.
    """

    def __init__(self, pattern: str, *, match_budget: int = 2):
        if not pattern:
            raise ValueError("pattern must be nonempty")
        if match_budget < 0:
            raise ValueError(match_budget)
        self.pattern = pattern
        self.failure = failure_positions(pattern)
        self.logical_position = -1
        self.physical = MicroDeltaCursor(pattern)
        self.pending_advances = 0
        self.match_budget = match_budget
        self.microsteps = 0

    def _start_pending_if_needed(self) -> None:
        if not self.physical.busy and self.pending_advances:
            self.physical.start("advance")

    def _tick_updater(self) -> None:
        self._start_pending_if_needed()
        if not self.physical.busy:
            return
        operation = self.physical.operation
        finished = self.physical.tick()
        self.microsteps += 1
        if finished and operation == "advance":
            self.pending_advances -= 1
            assert self.pending_advances >= 0

    def _spend_budget(self, amount: int) -> None:
        for _ in range(amount):
            if not self.pending_advances and not self.physical.busy:
                break
            self._tick_updater()

    def _catch_up(self) -> None:
        while self.pending_advances or self.physical.busy:
            self._tick_updater()
        assert self.physical.position == self.logical_position

    def _backpointer(self) -> int:
        self._catch_up()
        if self.logical_position < 0:
            raise RuntimeError("sentinel has no backpointer")
        self.physical.start("backpointer")
        before = self.microsteps
        while self.physical.busy:
            self._tick_updater()
        self.logical_position = self.physical.position
        return self.microsteps - before

    def feed(self, symbol: str, *, force_after_match: bool = True) -> DeferredMatchStep:
        if len(symbol) != 1:
            raise ValueError(symbol)
        before = self.microsteps
        backpointers = 0

        while (
            self.logical_position >= 0
            and self.pattern[self.logical_position + 1] != symbol
        ):
            self._backpointer()
            backpointers += 1

        if self.pattern[self.logical_position + 1] == symbol:
            self.logical_position += 1
            self.pending_advances += 1
            self._spend_budget(self.match_budget)

        full = self.logical_position == len(self.pattern) - 1
        matched_length = self.logical_position + 1
        if full and force_after_match:
            self._backpointer()
            backpointers += 1

        return DeferredMatchStep(
            symbol=symbol,
            full_match=full,
            matched_length=matched_length,
            microsteps=self.microsteps - before,
            backpointers=backpointers,
            pending_advances=self.pending_advances,
        )


def delta_layout_from_blocks(blocks: list[int]) -> tuple[str, list[int]]:
    """Build a Delta tape from already constructed blocks only.

    ``blocks[j]`` denotes ``Delta(j-1)``.  The trailing delimiter represents
    logical position ``len(blocks)-1`` and permits the next successful advance.
    """

    if not blocks or any(value < 0 for value in blocks):
        raise ValueError(blocks)
    chars = [MARK]
    delimiters: list[int] = []
    for amount in blocks:
        delimiters.append(len(chars))
        chars.append(ZERO)
        chars.extend(ONE for _ in range(amount))
    delimiters.append(len(chars))
    chars.append(ZERO)
    return "".join(chars), delimiters


def make_configuration_from_blocks(
    blocks: list[int], position: int, operation: str
) -> FlatConfiguration:
    max_position = len(blocks) - 1
    if not (-1 <= position <= max_position):
        raise ValueError((blocks, position))
    if operation == "advance" and position >= max_position:
        raise ValueError("no constructed Delta block to cross")
    y_word, delimiters = delta_layout_from_blocks(blocks)
    jump = 0 if position < 0 else sum(blocks[: position + 1])
    s_word = MARK + ONE * jump
    state = {"advance": ADV_START, "backpointer": BACK_START}[operation]
    return FlatConfiguration(
        state=state,
        tapes=[
            _write_word(y_word),
            _write_word(s_word),
            _write_word(MARK),
            _write_word(MARK),
        ],
        heads=[delimiters[position + 1], len(s_word), 1, 1],
    )


def logical_position_from_blocks(blocks: list[int], config: FlatConfiguration) -> int:
    _, delimiters = delta_layout_from_blocks(blocks)
    return delimiters.index(config.heads[Y]) - 1


def run_primitive_blocks(
    blocks: list[int], position: int, operation: str
) -> PrimitiveResult:
    config = make_configuration_from_blocks(blocks, position, operation)
    old_jump = unary_count(config, S)
    steps = MACHINE.run(config)
    new_position = logical_position_from_blocks(blocks, config)
    new_jump = unary_count(config, S)
    expected_position = position + 1 if operation == "advance" else position - old_jump
    assert new_position == expected_position
    expected_jump = 0 if new_position < 0 else sum(blocks[: new_position + 1])
    assert new_jump == expected_jump
    assert config.heads[S] == new_jump + 1
    return PrimitiveResult(
        operation,
        position,
        new_position,
        steps,
        old_jump,
        new_jump,
    )


@dataclass(frozen=True)
class FailureBuildResult:
    pattern: str
    failure: tuple[int, ...]
    blocks: tuple[int, ...]
    primitive_microsteps: int
    block_write_steps: int
    backpointer_count: int


def build_failure_delta_micro(pattern: str) -> FailureBuildResult:
    """Construct ``P`` and unary-Delta blocks from left to right.

    Only already constructed Delta blocks and character comparisons are used.
    No call to :func:`failure_positions` or :func:`delta_blocks` occurs inside
    the construction.  Backpointer and successful-advance movements are run
    through the literal cell-level table above.
    """

    if not pattern:
        raise ValueError("pattern must be nonempty")

    failure = [-1]
    blocks = [1]  # Delta(-1)=1 because P(-1)=P(0)=-1.
    primitive_steps = 0
    write_steps = 2  # one unary 1 and the following delimiter
    backpointers = 0

    for i in range(1, len(pattern)):
        p = failure[i - 1]
        new_block = 0

        while p >= 0 and pattern[p + 1] != pattern[i]:
            move = run_primitive_blocks(blocks, p, "backpointer")
            primitive_steps += move.microsteps
            backpointers += 1
            new_block += move.old_jump
            p = move.new_position

        if pattern[p + 1] == pattern[i]:
            move = run_primitive_blocks(blocks, p, "advance")
            primitive_steps += move.microsteps
            p = move.new_position
        else:
            assert p == -1
            new_block += 1

        failure.append(p)
        blocks.append(new_block)
        write_steps += new_block + 1

    return FailureBuildResult(
        pattern=pattern,
        failure=tuple(failure),
        blocks=tuple(blocks),
        primitive_microsteps=primitive_steps,
        block_write_steps=write_steps,
        backpointer_count=backpointers,
    )
