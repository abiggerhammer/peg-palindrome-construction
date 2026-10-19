"""Algorithm Y over the strict stack-only append/read representation."""

from __future__ import annotations

from dataclasses import dataclass

from flat_tm import Shift
from fp_algorithm_y_multihead import (
    A, B, BLANK, C, D, HALT, MACHINE, S, T, U, initial_configuration,
)
from algorithm_y_append_read import delta_blocks_from_word
from strict_append_read_zipper import StrictAppendReadZipper


@dataclass
class StrictAlgorithmYConfiguration:
    state: object
    patterns: tuple[dict[int, str], dict[int, str]]
    pattern_heads: list[int]
    delta: StrictAppendReadZipper[str]
    counters: list[dict[int, str]]
    counter_heads: list[int]
    source_steps: int = 0
    maximum_storage_primitives_per_source_step: int = 0

    @staticmethod
    def initial(pattern: str) -> "StrictAlgorithmYConfiguration":
        old = initial_configuration(pattern)
        data = tuple(old.tapes[1].get(i, BLANK) for i in range(old.heads[D]))
        return StrictAlgorithmYConfiguration(
            old.state,
            (dict(old.tapes[0]), dict(old.tapes[0])),
            [old.heads[A], old.heads[B]],
            StrictAppendReadZipper.from_cells(
                data, reader=old.heads[C], writer=old.heads[D], blank=BLANK
            ),
            [dict(old.tapes[2]), dict(old.tapes[3]), dict(old.tapes[4])],
            [old.heads[S], old.heads[T], old.heads[U]],
            old.steps,
        )

    def scanned(self) -> tuple[str, ...]:
        return (
            self.patterns[0].get(self.pattern_heads[0], BLANK),
            self.patterns[1].get(self.pattern_heads[1], BLANK),
            self.delta.reader_symbol,
            self.delta.writer_symbol,
            self.counters[0].get(self.counter_heads[0], BLANK),
            self.counters[1].get(self.counter_heads[1], BLANK),
            self.counters[2].get(self.counter_heads[2], BLANK),
        )

    def step(self) -> None:
        reads = self.scanned()
        action = MACHINE.delta[(self.state, reads)]
        before = self.delta.primitive_steps + self.delta.queue.primitive_steps

        for logical, private in ((A, 0), (B, 1)):
            assert action.writes[logical] == reads[logical]
            self.pattern_heads[private] += int(action.moves[logical])

        assert action.writes[C] == reads[C]
        if action.writes[D] != reads[D]:
            assert reads[D] == BLANK and action.moves[D] is Shift.RIGHT
            self.delta.append(action.writes[D])
        else:
            assert action.moves[D] is Shift.STAY

        if action.moves[C] is Shift.LEFT:
            self.delta.move_left()
        elif action.moves[C] is Shift.RIGHT:
            self.delta.move_right()

        after = self.delta.primitive_steps + self.delta.queue.primitive_steps
        self.maximum_storage_primitives_per_source_step = max(
            self.maximum_storage_primitives_per_source_step, after - before
        )

        for logical in (S, T, U):
            i = logical - S
            pos = self.counter_heads[i]
            write = action.writes[logical]
            if write == BLANK:
                self.counters[i].pop(pos, None)
            else:
                self.counters[i][pos] = write
            self.counter_heads[i] += int(action.moves[logical])

        self.state = action.next_state
        self.source_steps += 1

    def run(self, max_steps: int = 1_000_000) -> None:
        while self.state != HALT:
            if self.source_steps >= max_steps:
                raise TimeoutError(self.state)
            self.step()

    def delta_word(self) -> str:
        return "".join(self.delta.materialize())


@dataclass(frozen=True)
class StrictAlgorithmYResult:
    blocks: tuple[int, ...]
    source_steps: int
    max_storage_primitives: int


def run_algorithm_y_strict(pattern: str) -> StrictAlgorithmYResult:
    c = StrictAlgorithmYConfiguration.initial(pattern)
    c.run()
    return StrictAlgorithmYResult(
        delta_blocks_from_word(c.delta_word()),
        c.source_steps,
        c.maximum_storage_primitives_per_source_step,
    )
