"""Algorithm Y with its final shared tape replaced by an append/read zipper.

After read-only pattern-head duplication, Fischer--Paterson Algorithm Y has one
shared unit left: C is a read-only two-way cursor on the unary-Delta string and
D appends at its right end.  :class:`append_read_zipper.AppendReadZipper`
represents this unit by two ordinary stacks plus a strict real-time queue.

This module executes the original literal Algorithm-Y transition table against
that representation.  It is an exact differential bridge to the final
one-head-per-tape table: every source transition uses only a bounded number of
stack-top operations and at most four Hood--Melville rotation steps.
"""

from __future__ import annotations

from dataclasses import dataclass

from append_read_zipper import AppendReadZipper
from flat_tm import Shift
from fp_algorithm_y_multihead import (
    A,
    B,
    BLANK,
    C,
    D,
    HALT,
    MACHINE,
    MARK,
    S,
    SENTINEL,
    T,
    U,
    ZERO,
    initial_configuration,
)


@dataclass
class AlgorithmYAppendReadConfiguration:
    state: object
    pattern_tapes: tuple[dict[int, str], dict[int, str]]
    pattern_heads: list[int]
    delta: AppendReadZipper[str]
    counter_tapes: list[dict[int, str]]
    counter_heads: list[int]
    steps: int = 0
    max_rotation_steps_in_source_step: int = 0

    @staticmethod
    def initial(pattern: str) -> "AlgorithmYAppendReadConfiguration":
        old = initial_configuration(pattern)
        # Initial Delta content is #010, C=1 and D=4.
        delta_cells = tuple(old.tapes[1].get(i, BLANK) for i in range(old.heads[D]))
        return AlgorithmYAppendReadConfiguration(
            state=old.state,
            pattern_tapes=(dict(old.tapes[0]), dict(old.tapes[0])),
            pattern_heads=[old.heads[A], old.heads[B]],
            delta=AppendReadZipper.from_cells(
                delta_cells, reader=old.heads[C], writer=old.heads[D], blank=BLANK
            ),
            counter_tapes=[dict(old.tapes[2]), dict(old.tapes[3]), dict(old.tapes[4])],
            counter_heads=[old.heads[S], old.heads[T], old.heads[U]],
            steps=old.steps,
        )

    def _ordinary_read(self, index: int) -> str:
        if index == A:
            return self.pattern_tapes[0].get(self.pattern_heads[0], BLANK)
        if index == B:
            return self.pattern_tapes[1].get(self.pattern_heads[1], BLANK)
        if index == C:
            return self.delta.reader_symbol
        if index == D:
            return self.delta.writer_symbol
        ci = index - S
        return self.counter_tapes[ci].get(self.counter_heads[ci], BLANK)

    def scanned(self) -> tuple[str, ...]:
        return tuple(self._ordinary_read(i) for i in range(7))

    @staticmethod
    def _move(pos: int, shift: Shift) -> int:
        return pos + int(shift)

    def step(self) -> None:
        if self.state == HALT:
            raise RuntimeError("cannot step halted Algorithm Y")
        reads = self.scanned()
        action = MACHINE.delta[(self.state, reads)]

        # The duplicated pattern tapes are read-only.
        for logical, private in ((A, 0), (B, 1)):
            assert action.writes[logical] == reads[logical]
            self.pattern_heads[private] = self._move(
                self.pattern_heads[private], action.moves[logical]
            )

        # C preserves its symbol. D is either inert or appends one nonblank
        # symbol and moves right. Apply the append before the reader move;
        # because C<D this is equivalent to the simultaneous source action.
        assert action.writes[C] == reads[C]
        assert action.moves[D] in (Shift.STAY, Shift.RIGHT)
        before_rotations = self.delta.queue.rotation_steps
        if action.writes[D] != reads[D]:
            assert reads[D] == BLANK
            assert action.writes[D] != BLANK
            assert action.moves[D] is Shift.RIGHT
            self.delta = self.delta.append(action.writes[D])
        else:
            assert action.moves[D] is Shift.STAY

        if action.moves[C] is Shift.LEFT:
            self.delta = self.delta.move_left()
        elif action.moves[C] is Shift.RIGHT:
            self.delta = self.delta.move_right()
        elif action.moves[C] is not Shift.STAY:  # pragma: no cover
            raise AssertionError(action.moves[C])
        rotations = self.delta.queue.rotation_steps - before_rotations
        self.max_rotation_steps_in_source_step = max(
            self.max_rotation_steps_in_source_step, rotations
        )
        assert rotations <= 4

        # S,T,U are already ordinary one-head stack/counter tapes.
        for logical in (S, T, U):
            ci = logical - S
            pos = self.counter_heads[ci]
            write = action.writes[logical]
            if write == BLANK:
                self.counter_tapes[ci].pop(pos, None)
            else:
                self.counter_tapes[ci][pos] = write
            self.counter_heads[ci] = self._move(pos, action.moves[logical])

        self.state = action.next_state
        self.steps += 1

    def run(self, max_steps: int = 1_000_000) -> int:
        start = self.steps
        while self.state != HALT:
            if self.steps - start >= max_steps:
                raise TimeoutError((self.state, self.scanned()))
            self.step()
        return self.steps - start

    def delta_word(self) -> str:
        return "".join(self.delta.materialize())


def delta_blocks_from_word(word: str) -> tuple[int, ...]:
    if not word.startswith(MARK + ZERO) or not word.endswith(ZERO):
        raise AssertionError(word)
    runs = word[1:].split(ZERO)
    assert runs[0] == "" and runs[-1] == ""
    return tuple(len(run) for run in runs[1:-1])


@dataclass(frozen=True)
class AppendReadAlgorithmYResult:
    pattern: str
    blocks: tuple[int, ...]
    source_steps: int
    maximum_queue_rotation_steps: int


def run_algorithm_y_append_read(pattern: str) -> AppendReadAlgorithmYResult:
    config = AlgorithmYAppendReadConfiguration.initial(pattern)
    config.run()
    return AppendReadAlgorithmYResult(
        pattern,
        delta_blocks_from_word(config.delta_word()),
        config.steps,
        config.max_rotation_steps_in_source_step,
    )
