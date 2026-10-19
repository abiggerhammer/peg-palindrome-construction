from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from itertools import product
from typing import Dict, Hashable, Mapping, Optional, Sequence, Tuple

from peg import ANY, EPS, FAIL, And, Grammar, Literal, Not, Ref, Star, choice, seq


class Move(str, Enum):
    LEFT = "L"
    STAY = "S"
    RIGHT = "R"


@dataclass(frozen=True)
class MTMAction:
    next_state: Hashable
    writes: Tuple[Hashable, ...]
    moves: Tuple[Move, ...]


@dataclass
class RealtimeMultitapeMachine:
    """Deterministic streaming multitape TM with one work-tape step per symbol.

    The input is supplied as a fresh symbol to the finite control at each step;
    it is not stored on an input tape unless the machine copies it to a work
    tape. All work tapes are two-way infinite and initially blank at cell zero.
    """

    input_alphabet: Tuple[str, ...]
    tape_alphabet: Tuple[Hashable, ...]
    blank: Hashable
    states: Tuple[Hashable, ...]
    initial_state: Hashable
    accepting_states: frozenset[Hashable]
    tape_count: int
    delta: Mapping[Tuple[Hashable, str, Tuple[Hashable, ...]], MTMAction]

    def __post_init__(self) -> None:
        if self.blank not in self.tape_alphabet:
            raise ValueError("blank must belong to tape alphabet")
        for key, action in self.delta.items():
            state, symbol, heads = key
            if state not in self.states:
                raise ValueError(f"unknown state {state!r}")
            if symbol not in self.input_alphabet:
                raise ValueError(f"unknown input symbol {symbol!r}")
            if len(heads) != self.tape_count:
                raise ValueError("wrong number of read symbols")
            if len(action.writes) != self.tape_count or len(action.moves) != self.tape_count:
                raise ValueError("wrong number of tape actions")
            if any(value not in self.tape_alphabet for value in heads + action.writes):
                raise ValueError("symbol outside tape alphabet")

    def run(self, text: str) -> bool:
        tapes: list[dict[int, Hashable]] = [dict() for _ in range(self.tape_count)]
        positions = [0] * self.tape_count
        state = self.initial_state
        for inp in text:
            heads = tuple(
                tapes[i].get(positions[i], self.blank) for i in range(self.tape_count)
            )
            key = (state, inp, heads)
            if key not in self.delta:
                raise RuntimeError(f"missing transition for {key!r}")
            action = self.delta[key]
            for i, written in enumerate(action.writes):
                if written == self.blank:
                    tapes[i].pop(positions[i], None)
                else:
                    tapes[i][positions[i]] = written
                if action.moves[i] is Move.LEFT:
                    positions[i] -= 1
                elif action.moves[i] is Move.RIGHT:
                    positions[i] += 1
            state = action.next_state
        return state in self.accepting_states


class _Names:
    def __init__(self, machine: RealtimeMultitapeMachine):
        self.machine = machine
        self.state_ids = {q: i for i, q in enumerate(machine.states)}
        self.sym_ids = {a: i for i, a in enumerate(machine.tape_alphabet)}
        self.values = ("<EMPTY>",) + machine.tape_alphabet
        self.value_ids = {a: i for i, a in enumerate(self.values)}

    def state(self, q: Hashable) -> str:
        return f"State_{self.state_ids[q]}"

    def head(self, tape: int, value: Hashable) -> str:
        return f"Head_{tape}_{self.sym_ids[value]}"

    def top(self, side: str, tape: int, value: Hashable) -> str:
        return f"{side}Top_{tape}_{self.value_ids[value]}"

    @staticmethod
    def path(path: Tuple[int, ...]) -> str:
        return "Path_eps" if not path else "Path_" + "_".join(map(str, path))


EMPTY = "<EMPTY>"


def compile_realtime_mtm_to_peg(machine: RealtimeMultitapeMachine) -> Grammar:
    """Compile a real-time multitape machine to a PEG for its reverse language.

    This is a factored implementation of the zipper-stack scaffolding
    simulation. Instead of enumerating the Cartesian-product node-label
    alphabet, it emits one PEG nonterminal for each label field. That is merely
    a compact presentation of the same finite scaffolding automaton.
    """

    n = _Names(machine)
    degree = 2 * machine.tape_count
    radius = 2
    rules: dict[str, object] = {"EOF": Not(ANY), n.path(()): EPS}
    alternatives: dict[str, list] = defaultdict(list)

    # Initial finite control and blank/empty zipper snapshots at the PEG's EOF.
    alternatives[n.state(machine.initial_state)].append(Ref("EOF"))
    for tape in range(machine.tape_count):
        alternatives[n.head(tape, machine.blank)].append(Ref("EOF"))
        alternatives[n.top("L", tape, EMPTY)].append(Ref("EOF"))
        alternatives[n.top("R", tape, EMPTY)].append(Ref("EOF"))

    # Step-case predicates are indexed by concrete TM table entries. They inspect
    # only the previous state and the symbols under the work-tape heads.
    entries = list(machine.delta.items())
    step_names: list[str] = []
    for idx, ((state, inp, heads), action) in enumerate(entries):
        step = f"Step_{idx}"
        step_names.append(step)
        lit = Literal(inp)
        checks = [And(seq(lit, Ref(n.state(state))))]
        checks.extend(
            And(seq(lit, Ref(n.head(tape, value))))
            for tape, value in enumerate(heads)
        )
        rules[step] = seq(*checks)
        alternatives[n.state(action.next_state)].append(Ref(step))

    def after(inp: str, nonterminal: str):
        return And(seq(Literal(inp), Ref(nonterminal)))

    def with_step(step: str, *predicates):
        return seq(Ref(step), *predicates)

    # Emit field updates and edge-update cases for every machine transition.
    # edge_cases[e] contains (guard_expression, input_symbol, target_path|None).
    edge_cases: list[list[tuple[object, str, Optional[Tuple[int, ...]]]]] = [
        [] for _ in range(degree)
    ]

    for idx, ((state, inp, heads), action) in enumerate(entries):
        step = step_names[idx]
        for tape in range(machine.tape_count):
            left_edge = 2 * tape
            right_edge = left_edge + 1
            write = action.writes[tape]
            move = action.moves[tape]

            if move is Move.STAY:
                alternatives[n.head(tape, write)].append(Ref(step))
                for value in (EMPTY,) + machine.tape_alphabet:
                    alternatives[n.top("L", tape, value)].append(
                        with_step(step, after(inp, n.top("L", tape, value)))
                    )
                    alternatives[n.top("R", tape, value)].append(
                        with_step(step, after(inp, n.top("R", tape, value)))
                    )
                edge_cases[left_edge].append((Ref(step), inp, (left_edge,)))
                edge_cases[right_edge].append((Ref(step), inp, (right_edge,)))

            elif move is Move.RIGHT:
                # Push the written cell onto the left stack.
                alternatives[n.top("L", tape, write)].append(Ref(step))
                for value in machine.tape_alphabet:
                    edge_cases[left_edge].append(
                        (
                            with_step(step, after(inp, n.top("L", tape, value))),
                            inp,
                            (),
                        )
                    )
                # Pop the right stack. The new head is the old stack top;
                # the new stack top is the old stack's second symbol.
                alternatives[n.head(tape, machine.blank)].append(
                    with_step(step, after(inp, n.top("R", tape, EMPTY)))
                )
                for value in machine.tape_alphabet:
                    alternatives[n.head(tape, value)].append(
                        with_step(step, after(inp, n.top("R", tape, value)))
                    )
                alternatives[n.top("R", tape, EMPTY)].append(
                    with_step(step, Not(seq(Literal(inp), Ref(n.path((right_edge,))))))
                )
                for value in machine.tape_alphabet:
                    alternatives[n.top("R", tape, value)].append(
                        with_step(
                            step,
                            And(
                                seq(
                                    Literal(inp),
                                    Ref(n.path((right_edge,))),
                                    Ref(n.top("R", tape, value)),
                                )
                            ),
                        )
                    )
                edge_cases[right_edge].append(
                    (Ref(step), inp, (right_edge, right_edge))
                )

            elif move is Move.LEFT:
                # Pop the left stack. The new head is the old stack top;
                # the new stack top is the old stack's second symbol.
                alternatives[n.head(tape, machine.blank)].append(
                    with_step(step, after(inp, n.top("L", tape, EMPTY)))
                )
                for value in machine.tape_alphabet:
                    alternatives[n.head(tape, value)].append(
                        with_step(step, after(inp, n.top("L", tape, value)))
                    )
                alternatives[n.top("L", tape, EMPTY)].append(
                    with_step(step, Not(seq(Literal(inp), Ref(n.path((left_edge,))))))
                )
                for value in machine.tape_alphabet:
                    alternatives[n.top("L", tape, value)].append(
                        with_step(
                            step,
                            And(
                                seq(
                                    Literal(inp),
                                    Ref(n.path((left_edge,))),
                                    Ref(n.top("L", tape, value)),
                                )
                            ),
                        )
                    )
                edge_cases[left_edge].append((Ref(step), inp, (left_edge, left_edge)))

                # Push the written cell onto the right stack.
                alternatives[n.top("R", tape, write)].append(Ref(step))
                for value in machine.tape_alphabet:
                    edge_cases[right_edge].append(
                        (
                            with_step(step, after(inp, n.top("R", tape, value))),
                            inp,
                            (),
                        )
                    )
            else:
                raise ValueError(move)

    # Path recurrences for every path of length one or two.
    paths = [tuple(p) for length in (1, 2) for p in product(range(degree), repeat=length)]
    for path in paths:
        first, rest = path[0], path[1:]
        lhs = n.path(path)
        for guard, inp, target in edge_cases[first]:
            if target is None:
                continue
            alternatives[lhs].append(
                seq(
                    guard,
                    Literal(inp),
                    Ref(n.path(target)),
                    Ref(n.path(rest)),
                )
            )

    # Materialize finite-control, field, and path nonterminals.
    for state in machine.states:
        name = n.state(state)
        rules[name] = choice(*alternatives[name])
    for tape in range(machine.tape_count):
        for value in machine.tape_alphabet:
            name = n.head(tape, value)
            rules[name] = choice(*alternatives[name])
        for side in ("L", "R"):
            for value in (EMPTY,) + machine.tape_alphabet:
                name = n.top(side, tape, value)
                rules[name] = choice(*alternatives[name])
    for path in paths:
        name = n.path(path)
        rules[name] = choice(*alternatives[name])

    accepting = [Ref(n.state(q)) for q in machine.accepting_states]
    rules["AutomatonAccepts"] = seq(choice(*accepting), Star(ANY))
    return Grammar(rules=rules, start="AutomatonAccepts")
