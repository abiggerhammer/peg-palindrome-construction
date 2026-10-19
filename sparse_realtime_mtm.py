"""Sparse real-time ordinary multitape machines and direct PEG compilation.

Unlike :mod:`realtime_mtm`, rows may use finite read sets or wildcards on each
work tape.  The PEG compiler consumes those cubes directly: it never expands a
row into the Cartesian product of ignored tape symbols.  Dependence on a
preserved scanned symbol is handled locally, one tape at a time.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from typing import FrozenSet, Hashable, Iterable, Mapping, Optional, Sequence, Tuple

from peg import ANY, EPS, And, Grammar, Literal, Not, Ref, Star, choice, seq
from realtime_mtm import EMPTY, MTMAction, Move, RealtimeMultitapeMachine

ReadAtom = Hashable | FrozenSet[Hashable] | None


@dataclass(frozen=True)
class SparseRTAction:
    next_state: Hashable
    writes: tuple[Hashable | None, ...]  # None preserves scanned symbol.
    moves: tuple[Move, ...]


@dataclass(frozen=True)
class SparseRTRow:
    state: Hashable
    input_symbol: str
    reads: tuple[ReadAtom, ...]
    action: SparseRTAction

    def matches(self, symbol: str, scanned: Sequence[Hashable]) -> bool:
        if symbol != self.input_symbol:
            return False
        for atom, actual in zip(self.reads, scanned):
            if atom is None:
                continue
            if isinstance(atom, frozenset):
                if actual not in atom:
                    return False
            elif actual != atom:
                return False
        return True


@dataclass(frozen=True)
class SparseRealtimeMultitapeMachine:
    input_alphabet: tuple[str, ...]
    tape_alphabets: tuple[tuple[Hashable, ...], ...]
    blank: Hashable
    states: tuple[Hashable, ...]
    initial_state: Hashable
    accepting_states: frozenset[Hashable]
    rows: tuple[SparseRTRow, ...]

    def __post_init__(self) -> None:
        if any(self.blank not in alphabet for alphabet in self.tape_alphabets):
            raise ValueError("blank missing from a tape alphabet")
        by_key: dict[tuple[Hashable, str], list[SparseRTRow]] = {}
        n = len(self.tape_alphabets)
        for row in self.rows:
            if row.state not in self.states:
                raise ValueError(row.state)
            if row.input_symbol not in self.input_alphabet:
                raise ValueError(row.input_symbol)
            if len(row.reads) != n:
                raise ValueError("wrong read arity")
            if len(row.action.writes) != n or len(row.action.moves) != n:
                raise ValueError("wrong action arity")
            by_key.setdefault((row.state, row.input_symbol), []).append(row)
        object.__setattr__(self, "_by_key", by_key)

    @property
    def tape_count(self) -> int:
        return len(self.tape_alphabets)

    def run(self, text: str) -> bool:
        tapes: list[dict[int, Hashable]] = [dict() for _ in self.tape_alphabets]
        heads = [0] * self.tape_count
        state = self.initial_state
        for symbol in text:
            scanned = tuple(
                tapes[i].get(heads[i], self.blank) for i in range(self.tape_count)
            )
            matches = [
                row for row in self._by_key.get((state, symbol), ())
                if row.matches(symbol, scanned)
            ]
            if not matches:
                raise RuntimeError(("missing sparse real-time row", state, symbol, scanned))
            action = matches[0].action
            if any(row.action != action for row in matches[1:]):
                raise RuntimeError(("conflicting sparse real-time rows", state, symbol, scanned))
            for tape, old in enumerate(scanned):
                write = old if action.writes[tape] is None else action.writes[tape]
                position = heads[tape]
                if write == self.blank:
                    tapes[tape].pop(position, None)
                else:
                    tapes[tape][position] = write
                move = action.moves[tape]
                if move is Move.LEFT:
                    heads[tape] -= 1
                elif move is Move.RIGHT:
                    heads[tape] += 1
            state = action.next_state
        return state in self.accepting_states

    def audit_determinism(self) -> None:
        for key, rows in self._by_key.items():
            for index, first in enumerate(rows):
                for second in rows[index + 1 :]:
                    if all(
                        _atom_values(left, alphabet) & _atom_values(right, alphabet)
                        for left, right, alphabet in zip(
                            first.reads, second.reads, self.tape_alphabets
                        )
                    ) and first.action != second.action:
                        raise AssertionError(("conflicting rows", key, first, second))


def _atom_values(atom: ReadAtom, alphabet: Sequence[Hashable]) -> set[Hashable]:
    if atom is None:
        return set(alphabet)
    if isinstance(atom, frozenset):
        return set(atom)
    return {atom}


def from_concrete(machine: RealtimeMultitapeMachine) -> SparseRealtimeMultitapeMachine:
    rows = tuple(
        SparseRTRow(
            state,
            symbol,
            tuple(heads),
            SparseRTAction(action.next_state, tuple(action.writes), tuple(action.moves)),
        )
        for (state, symbol, heads), action in machine.delta.items()
    )
    return SparseRealtimeMultitapeMachine(
        machine.input_alphabet,
        (tuple(machine.tape_alphabet),) * machine.tape_count,
        machine.blank,
        machine.states,
        machine.initial_state,
        machine.accepting_states,
        rows,
    )


class _Names:
    def __init__(self, machine: SparseRealtimeMultitapeMachine):
        self.machine = machine
        self.state_ids = {state: i for i, state in enumerate(machine.states)}
        self.sym_ids = [
            {symbol: index for index, symbol in enumerate(alphabet)}
            for alphabet in machine.tape_alphabets
        ]
        self.value_ids = [
            {value: index for index, value in enumerate((EMPTY,) + tuple(alphabet))}
            for alphabet in machine.tape_alphabets
        ]

    def state(self, state: Hashable) -> str:
        return f"State_{self.state_ids[state]}"

    def head(self, tape: int, value: Hashable) -> str:
        return f"Head_{tape}_{self.sym_ids[tape][value]}"

    def top(self, side: str, tape: int, value: Hashable) -> str:
        return f"{side}Top_{tape}_{self.value_ids[tape][value]}"

    @staticmethod
    def path(path: tuple[int, ...]) -> str:
        return "Path_eps" if not path else "Path_" + "_".join(map(str, path))


def compile_sparse_realtime_mtm_to_peg(
    machine: SparseRealtimeMultitapeMachine,
) -> Grammar:
    """Compile directly from sparse read cubes to a PEG for the reverse language."""

    n = _Names(machine)
    degree = 2 * machine.tape_count
    rules: dict[str, object] = {"EOF": Not(ANY), n.path(()): EPS}
    alternatives: dict[str, list] = defaultdict(list)

    alternatives[n.state(machine.initial_state)].append(Ref("EOF"))
    for tape in range(machine.tape_count):
        alternatives[n.head(tape, machine.blank)].append(Ref("EOF"))
        alternatives[n.top("L", tape, EMPTY)].append(Ref("EOF"))
        alternatives[n.top("R", tape, EMPTY)].append(Ref("EOF"))

    step_names: list[str] = []
    for index, row in enumerate(machine.rows):
        step = f"Step_{index}"
        step_names.append(step)
        literal = Literal(row.input_symbol)
        checks = [And(seq(literal, Ref(n.state(row.state))))]
        for tape, atom in enumerate(row.reads):
            if atom is None:
                continue
            values = tuple(_atom_values(atom, machine.tape_alphabets[tape]))
            checks.append(
                And(seq(literal, choice(*(Ref(n.head(tape, value)) for value in values))))
            )
        rules[step] = seq(*checks)
        alternatives[n.state(row.action.next_state)].append(Ref(step))

    def after(symbol: str, nonterminal: str):
        return And(seq(Literal(symbol), Ref(nonterminal)))

    def with_step(step: str, *predicates):
        return seq(Ref(step), *predicates)

    edge_cases: list[list[tuple[object, str, tuple[int, ...]]]] = [
        [] for _ in range(degree)
    ]

    for index, row in enumerate(machine.rows):
        step = step_names[index]
        inp = row.input_symbol
        for tape, alphabet in enumerate(machine.tape_alphabets):
            left_edge = 2 * tape
            right_edge = left_edge + 1
            move = row.action.moves[tape]
            possible_old = tuple(_atom_values(row.reads[tape], alphabet))

            for old_head in possible_old:
                case = with_step(step, after(inp, n.head(tape, old_head)))
                write = old_head if row.action.writes[tape] is None else row.action.writes[tape]

                if move is Move.STAY:
                    alternatives[n.head(tape, write)].append(case)
                    for top in (EMPTY,) + tuple(alphabet):
                        alternatives[n.top("L", tape, top)].append(
                            seq(case, after(inp, n.top("L", tape, top)))
                        )
                        alternatives[n.top("R", tape, top)].append(
                            seq(case, after(inp, n.top("R", tape, top)))
                        )
                    edge_cases[left_edge].append((case, inp, (left_edge,)))
                    edge_cases[right_edge].append((case, inp, (right_edge,)))

                elif move is Move.RIGHT:
                    alternatives[n.top("L", tape, write)].append(case)
                    for top in alphabet:
                        edge_cases[left_edge].append(
                            (seq(case, after(inp, n.top("L", tape, top))), inp, ())
                        )

                    alternatives[n.head(tape, machine.blank)].append(
                        seq(case, after(inp, n.top("R", tape, EMPTY)))
                    )
                    for top in alphabet:
                        alternatives[n.head(tape, top)].append(
                            seq(case, after(inp, n.top("R", tape, top)))
                        )
                    alternatives[n.top("R", tape, EMPTY)].append(
                        seq(case, Not(seq(Literal(inp), Ref(n.path((right_edge,))))))
                    )
                    for top in alphabet:
                        alternatives[n.top("R", tape, top)].append(
                            seq(
                                case,
                                And(seq(
                                    Literal(inp),
                                    Ref(n.path((right_edge,))),
                                    Ref(n.top("R", tape, top)),
                                )),
                            )
                        )
                    edge_cases[right_edge].append((case, inp, (right_edge, right_edge)))

                elif move is Move.LEFT:
                    alternatives[n.head(tape, machine.blank)].append(
                        seq(case, after(inp, n.top("L", tape, EMPTY)))
                    )
                    for top in alphabet:
                        alternatives[n.head(tape, top)].append(
                            seq(case, after(inp, n.top("L", tape, top)))
                        )
                    alternatives[n.top("L", tape, EMPTY)].append(
                        seq(case, Not(seq(Literal(inp), Ref(n.path((left_edge,))))))
                    )
                    for top in alphabet:
                        alternatives[n.top("L", tape, top)].append(
                            seq(
                                case,
                                And(seq(
                                    Literal(inp),
                                    Ref(n.path((left_edge,))),
                                    Ref(n.top("L", tape, top)),
                                )),
                            )
                        )
                    edge_cases[left_edge].append((case, inp, (left_edge, left_edge)))

                    alternatives[n.top("R", tape, write)].append(case)
                    for top in alphabet:
                        edge_cases[right_edge].append(
                            (seq(case, after(inp, n.top("R", tape, top))), inp, ())
                        )
                else:  # pragma: no cover
                    raise ValueError(move)

    paths = [
        tuple(path)
        for length in (1, 2)
        for path in product(range(degree), repeat=length)
    ]
    for path in paths:
        first, rest = path[0], path[1:]
        lhs = n.path(path)
        for guard, inp, target in edge_cases[first]:
            alternatives[lhs].append(
                seq(guard, Literal(inp), Ref(n.path(target)), Ref(n.path(rest)))
            )

    for state in machine.states:
        rules[n.state(state)] = choice(*alternatives[n.state(state)])
    for tape, alphabet in enumerate(machine.tape_alphabets):
        for value in alphabet:
            rules[n.head(tape, value)] = choice(*alternatives[n.head(tape, value)])
        for side in ("L", "R"):
            for value in (EMPTY,) + tuple(alphabet):
                rules[n.top(side, tape, value)] = choice(
                    *alternatives[n.top(side, tape, value)]
                )
    for path in paths:
        rules[n.path(path)] = choice(*alternatives[n.path(path)])

    rules["AutomatonAccepts"] = seq(
        choice(*(Ref(n.state(state)) for state in machine.accepting_states)),
        Star(ANY),
    )
    return Grammar(rules=rules, start="AutomatonAccepts")
