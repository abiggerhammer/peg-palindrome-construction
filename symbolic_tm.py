"""Sparse one-cell ordinary multitape Turing-machine tables.

A row is a conventional TM transition schema with finite symbol sets or a
wildcard in read positions.  Wildcards are only presentation shorthand: each
row denotes the finite family of concrete transitions obtained by expanding
against the corresponding tape alphabet.  Every row performs exactly one
ordinary simultaneous read/write/move step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Hashable, Iterable, Sequence

from flat_tm import Shift

ReadAtom = str | FrozenSet[str] | None


@dataclass(frozen=True)
class SymbolicAction:
    next_state: Hashable
    writes: tuple[str | None, ...]  # None means preserve scanned symbol.
    moves: tuple[Shift, ...]


@dataclass(frozen=True)
class SymbolicRow:
    state: Hashable
    reads: tuple[ReadAtom, ...]
    action: SymbolicAction

    def matches(self, scanned: Sequence[str]) -> bool:
        for atom, symbol in zip(self.reads, scanned):
            if atom is None:
                continue
            if isinstance(atom, frozenset):
                if symbol not in atom:
                    return False
            elif symbol != atom:
                return False
        return True


@dataclass
class SymbolicConfiguration:
    state: Hashable
    tapes: list[dict[int, str]]
    heads: list[int]
    steps: int = 0
    source_dispatches: int = 0

    def clone(self) -> "SymbolicConfiguration":
        return SymbolicConfiguration(
            self.state, [dict(t) for t in self.tapes], list(self.heads),
            self.steps, self.source_dispatches
        )


@dataclass(frozen=True)
class SymbolicMultitapeMachine:
    tape_alphabets: tuple[tuple[str, ...], ...]
    blank: str
    states: tuple[Hashable, ...]
    halting_states: frozenset[Hashable]
    rows: tuple[SymbolicRow, ...]

    def __post_init__(self) -> None:
        if any(self.blank not in alphabet for alphabet in self.tape_alphabets):
            raise ValueError("blank missing from a tape alphabet")
        n = len(self.tape_alphabets)
        by_state: dict[Hashable, list[SymbolicRow]] = {}
        for row in self.rows:
            if len(row.reads) != n:
                raise ValueError("wrong read arity")
            if len(row.action.writes) != n or len(row.action.moves) != n:
                raise ValueError("wrong action arity")
            by_state.setdefault(row.state, []).append(row)
        object.__setattr__(self, "_by_state", by_state)

    @property
    def tape_count(self) -> int:
        return len(self.tape_alphabets)

    def scanned(self, config: SymbolicConfiguration) -> tuple[str, ...]:
        return tuple(
            config.tapes[i].get(config.heads[i], self.blank)
            for i in range(self.tape_count)
        )

    def matching_rows(self, state: Hashable, scanned: Sequence[str]) -> list[SymbolicRow]:
        return [r for r in self._by_state.get(state, ()) if r.matches(scanned)]

    def step(self, config: SymbolicConfiguration) -> None:
        if config.state in self.halting_states:
            raise RuntimeError("cannot step halted symbolic machine")
        scanned = self.scanned(config)
        matches = self.matching_rows(config.state, scanned)
        if not matches:
            raise RuntimeError(("missing symbolic transition", config.state, scanned))
        row = matches[0]
        if any(other.action != row.action for other in matches[1:]):
            raise RuntimeError(("conflicting symbolic transitions", config.state, scanned, matches))
        for i, value in enumerate(row.action.writes):
            write = scanned[i] if value is None else value
            position = config.heads[i]
            if write == self.blank:
                config.tapes[i].pop(position, None)
            else:
                config.tapes[i][position] = write
        for i, move in enumerate(row.action.moves):
            config.heads[i] += int(move)
        config.state = row.action.next_state
        config.steps += 1
        if getattr(row.state, "task", None) == ("DISPATCH",):
            config.source_dispatches += 1

    def run(self, config: SymbolicConfiguration, max_steps: int = 10_000_000) -> int:
        start = config.steps
        while config.state not in self.halting_states:
            if config.steps - start >= max_steps:
                raise TimeoutError((config.state, self.scanned(config)))
            self.step(config)
        return config.steps - start

    def audit_determinism(self) -> None:
        """Exhaustively audit row overlap per state over finite alphabets.

        This can be costly for many tapes, so it enumerates only symbols that
        occur in row atoms plus one representative wildcard value per tape.
        """
        from itertools import product

        for state, rows in self._by_state.items():
            choices: list[set[str]] = [set() for _ in self.tape_alphabets]
            for row in rows:
                for i, atom in enumerate(row.reads):
                    if atom is None:
                        choices[i].update(self.tape_alphabets[i])
                    elif isinstance(atom, frozenset):
                        choices[i].update(atom)
                    else:
                        choices[i].add(atom)
            # Avoid full Cartesian explosion when rows are sparse: pairwise
            # overlap of cubes is sufficient.
            for i, first in enumerate(rows):
                for second in rows[i + 1:]:
                    if _patterns_overlap(first.reads, second.reads, self.tape_alphabets):
                        if first.action != second.action:
                            raise AssertionError(("conflicting symbolic rows", state, first, second))


def _atom_set(atom: ReadAtom, alphabet: Sequence[str]) -> set[str]:
    if atom is None:
        return set(alphabet)
    if isinstance(atom, frozenset):
        return set(atom)
    return {atom}


def _patterns_overlap(
    left: Sequence[ReadAtom], right: Sequence[ReadAtom],
    alphabets: Sequence[Sequence[str]],
) -> bool:
    return all(
        _atom_set(a, alphabet) & _atom_set(b, alphabet)
        for a, b, alphabet in zip(left, right, alphabets)
    )


class SymbolicTableBuilder:
    def __init__(self, tape_alphabets: Sequence[Sequence[str]], blank: str):
        self.tape_alphabets = tuple(tuple(a) for a in tape_alphabets)
        self.blank = blank
        self.rows: list[SymbolicRow] = []
        self._row_set: set[SymbolicRow] = set()
        self.states: set[Hashable] = set()

    def add(
        self, state: Hashable, reads: Sequence[ReadAtom], next_state: Hashable,
        writes: Sequence[str | None], moves: Sequence[Shift]
    ) -> None:
        row = SymbolicRow(
            state, tuple(reads), SymbolicAction(next_state, tuple(writes), tuple(moves))
        )
        if row not in self._row_set:
            self._row_set.add(row)
            self.rows.append(row)
        self.states.add(state)
        self.states.add(next_state)

    def build(self, halting_states: Iterable[Hashable]) -> SymbolicMultitapeMachine:
        halting = frozenset(halting_states)
        self.states.update(halting)
        machine = SymbolicMultitapeMachine(
            self.tape_alphabets, self.blank,
            tuple(sorted(self.states, key=repr)), halting, tuple(self.rows)
        )
        return machine
