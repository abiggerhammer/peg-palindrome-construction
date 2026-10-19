"""Literal deterministic multihead, multitape Turing-machine core.

A transition reads one symbol under each head.  Several heads may share a tape;
when they coincide the interpreter verifies that their writes agree.  The table
is finite and concrete after wildcard expansion, and every head moves by at
most one square per step.

This model matches the one used in the Fischer--Paterson technical report and
in the real-time multihead simulation papers.  It is an intermediate audit
model: a later generic transformation replaces every multihead tape by
ordinary one-head tapes without changing the input/output timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Hashable, Iterable, Mapping, Sequence

from flat_tm import Shift


@dataclass(frozen=True)
class MultiheadAction:
    next_state: Hashable
    writes: tuple[str, ...]
    moves: tuple[Shift, ...]


@dataclass
class MultiheadConfiguration:
    state: Hashable
    tapes: list[dict[int, str]]
    heads: list[int]
    steps: int = 0

    def clone(self) -> "MultiheadConfiguration":
        return MultiheadConfiguration(
            self.state,
            [dict(tape) for tape in self.tapes],
            list(self.heads),
            self.steps,
        )


@dataclass(frozen=True)
class MultiheadSchema:
    state: Hashable
    reads: tuple[str | None, ...]
    next_state: Hashable
    writes: tuple[str | None, ...]
    moves: tuple[Shift, ...]


@dataclass(frozen=True)
class FlatMultiheadMachine:
    blank: str
    tape_alphabets: tuple[tuple[str, ...], ...]
    head_to_tape: tuple[int, ...]
    states: tuple[Hashable, ...]
    halting_states: frozenset[Hashable]
    delta: Mapping[tuple[Hashable, tuple[str, ...]], MultiheadAction]
    schemata: tuple[MultiheadSchema, ...] = ()

    @property
    def head_count(self) -> int:
        return len(self.head_to_tape)

    @property
    def tape_count(self) -> int:
        return len(self.tape_alphabets)

    def scanned(self, config: MultiheadConfiguration) -> tuple[str, ...]:
        return tuple(
            config.tapes[tape].get(config.heads[head], self.blank)
            for head, tape in enumerate(self.head_to_tape)
        )

    def step(self, config: MultiheadConfiguration) -> None:
        if config.state in self.halting_states:
            raise RuntimeError("cannot step halted multihead machine")
        reads = self.scanned(config)
        key = (config.state, reads)
        try:
            action = self.delta[key]
        except KeyError as exc:
            raise RuntimeError(f"missing multihead transition for {key!r}") from exc

        writes_by_cell: dict[tuple[int, int], str] = {}
        for head, symbol in enumerate(action.writes):
            tape = self.head_to_tape[head]
            cell = (tape, config.heads[head])
            old = writes_by_cell.get(cell)
            if old is not None and old != symbol:
                raise RuntimeError(("conflicting coincident writes", cell, old, symbol))
            writes_by_cell[cell] = symbol

        for (tape, position), symbol in writes_by_cell.items():
            if symbol == self.blank:
                config.tapes[tape].pop(position, None)
            else:
                config.tapes[tape][position] = symbol
        for head, move in enumerate(action.moves):
            config.heads[head] += int(move)
        config.state = action.next_state
        config.steps += 1

    def run(self, config: MultiheadConfiguration, *, max_steps: int = 1_000_000) -> int:
        start = config.steps
        while config.state not in self.halting_states:
            if config.steps - start >= max_steps:
                raise TimeoutError((config.state, self.scanned(config), config.heads))
            self.step(config)
        return config.steps - start


class MultiheadTableBuilder:
    def __init__(
        self,
        *,
        blank: str,
        tape_alphabets: Sequence[Sequence[str]],
        head_to_tape: Sequence[int],
    ):
        self.blank = blank
        self.tape_alphabets = tuple(tuple(a) for a in tape_alphabets)
        self.head_to_tape = tuple(head_to_tape)
        self.head_alphabets = tuple(
            self.tape_alphabets[tape] for tape in self.head_to_tape
        )
        self.delta: dict[tuple[Hashable, tuple[str, ...]], MultiheadAction] = {}
        self.states: set[Hashable] = set()
        self.schemata: list[MultiheadSchema] = []

    def add(
        self,
        state: Hashable,
        reads: Sequence[str | None],
        next_state: Hashable,
        writes: Sequence[str | None],
        moves: Sequence[Shift],
    ) -> None:
        h = len(self.head_to_tape)
        if len(reads) != h or len(writes) != h or len(moves) != h:
            raise ValueError("wrong head arity")
        schema = MultiheadSchema(
            state, tuple(reads), next_state, tuple(writes), tuple(moves)
        )
        if schema not in self.schemata:
            self.schemata.append(schema)
        choices = [
            self.head_alphabets[i] if value is None else (value,)
            for i, value in enumerate(reads)
        ]
        for concrete in product(*choices):
            concrete_writes = tuple(
                concrete[i] if value is None else value
                for i, value in enumerate(writes)
            )
            key = (state, tuple(concrete))
            action = MultiheadAction(next_state, concrete_writes, tuple(moves))
            old = self.delta.get(key)
            if old is not None and old != action:
                raise ValueError(f"overlapping transition {key!r}: {old!r} vs {action!r}")
            self.delta[key] = action
        self.states.add(state)
        self.states.add(next_state)

    def build(self, *, halting_states: Iterable[Hashable]) -> FlatMultiheadMachine:
        halting = frozenset(halting_states)
        self.states.update(halting)
        return FlatMultiheadMachine(
            blank=self.blank,
            tape_alphabets=self.tape_alphabets,
            head_to_tape=self.head_to_tape,
            states=tuple(sorted(self.states, key=repr)),
            halting_states=halting,
            delta=dict(self.delta),
            schemata=tuple(self.schemata),
        )
