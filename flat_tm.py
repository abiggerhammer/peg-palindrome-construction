"""Small explicit deterministic multitape Turing-machine core.

This module is intentionally lower-level than ``realtime_mtm.py``.  A machine
here performs ordinary one-cell microsteps and may run for an arbitrary number
of steps before halting.  It is used to audit the cell-by-cell lowering of the
Fischer--Paterson unary-Delta tape operations.

Transitions are a literal finite table keyed by ``(state, scanned_symbols)``;
there are no callbacks or unbounded macro actions in the interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from itertools import product
from typing import Hashable, Iterable, Mapping, Sequence


class Shift(IntEnum):
    LEFT = -1
    STAY = 0
    RIGHT = 1


@dataclass(frozen=True)
class FlatAction:
    next_state: Hashable
    writes: tuple[str, ...]
    moves: tuple[Shift, ...]


@dataclass
class FlatConfiguration:
    state: Hashable
    tapes: list[dict[int, str]]
    heads: list[int]
    steps: int = 0

    def clone(self) -> "FlatConfiguration":
        return FlatConfiguration(
            state=self.state,
            tapes=[dict(tape) for tape in self.tapes],
            heads=list(self.heads),
            steps=self.steps,
        )


@dataclass(frozen=True)
class FlatMultitapeMachine:
    alphabet: tuple[str, ...]
    blank: str
    tape_count: int
    states: tuple[Hashable, ...]
    halting_states: frozenset[Hashable]
    delta: Mapping[tuple[Hashable, tuple[str, ...]], FlatAction]

    def __post_init__(self) -> None:
        if self.blank not in self.alphabet:
            raise ValueError("blank outside alphabet")
        for (state, reads), action in self.delta.items():
            if state not in self.states:
                raise ValueError(f"unknown state {state!r}")
            if len(reads) != self.tape_count:
                raise ValueError("wrong read arity")
            if len(action.writes) != self.tape_count or len(action.moves) != self.tape_count:
                raise ValueError("wrong action arity")
            if any(symbol not in self.alphabet for symbol in reads + action.writes):
                raise ValueError("symbol outside alphabet")
            if action.next_state not in self.states:
                raise ValueError(f"unknown next state {action.next_state!r}")

    def scanned(self, config: FlatConfiguration) -> tuple[str, ...]:
        return tuple(
            config.tapes[i].get(config.heads[i], self.blank)
            for i in range(self.tape_count)
        )

    def step(self, config: FlatConfiguration) -> None:
        if config.state in self.halting_states:
            raise RuntimeError("cannot step a halted machine")
        reads = self.scanned(config)
        key = (config.state, reads)
        try:
            action = self.delta[key]
        except KeyError as exc:
            raise RuntimeError(f"missing flat transition for {key!r}") from exc

        # Simultaneous writes and moves.
        for tape_index, symbol in enumerate(action.writes):
            position = config.heads[tape_index]
            if symbol == self.blank:
                config.tapes[tape_index].pop(position, None)
            else:
                config.tapes[tape_index][position] = symbol
        for tape_index, move in enumerate(action.moves):
            config.heads[tape_index] += int(move)
        config.state = action.next_state
        config.steps += 1

    def run(self, config: FlatConfiguration, *, max_steps: int = 1_000_000) -> int:
        start = config.steps
        while config.state not in self.halting_states:
            if config.steps - start >= max_steps:
                raise TimeoutError((config.state, self.scanned(config)))
            self.step(config)
        return config.steps - start


class TableBuilder:
    """Expand wildcard transition patterns into a literal finite table."""

    def __init__(self, alphabet: Sequence[str], tape_count: int):
        self.alphabet = tuple(alphabet)
        self.tape_count = tape_count
        self.delta: dict[tuple[Hashable, tuple[str, ...]], FlatAction] = {}
        self.states: set[Hashable] = set()

    def add(
        self,
        state: Hashable,
        reads: Sequence[str | None],
        next_state: Hashable,
        writes: Sequence[str | None],
        moves: Sequence[Shift],
    ) -> None:
        if len(reads) != self.tape_count:
            raise ValueError("wrong read pattern arity")
        if len(writes) != self.tape_count or len(moves) != self.tape_count:
            raise ValueError("wrong action arity")
        choices: list[Iterable[str]] = [
            self.alphabet if symbol is None else (symbol,) for symbol in reads
        ]
        for concrete in product(*choices):
            concrete_writes = tuple(
                concrete[i] if symbol is None else symbol
                for i, symbol in enumerate(writes)
            )
            key = (state, tuple(concrete))
            action = FlatAction(next_state, concrete_writes, tuple(moves))
            old = self.delta.get(key)
            if old is not None and old != action:
                raise ValueError(f"overlapping transition {key!r}: {old!r} vs {action!r}")
            self.delta[key] = action
        self.states.add(state)
        self.states.add(next_state)

    def build(self, *, blank: str, halting_states: Iterable[Hashable]) -> FlatMultitapeMachine:
        halting = frozenset(halting_states)
        self.states.update(halting)
        return FlatMultitapeMachine(
            alphabet=self.alphabet,
            blank=blank,
            tape_count=self.tape_count,
            states=tuple(sorted(self.states, key=repr)),
            halting_states=halting,
            delta=dict(self.delta),
        )
