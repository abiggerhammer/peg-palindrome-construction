"""Pause/resume wrapper for large sparse ordinary-TM components.

A component's finite control state is stored as one symbol on a dedicated
state-register tape whenever the outer controller is running.  Servicing one
component transition takes exactly two ordinary transitions:

1. ``LOAD`` reads the register symbol and enters ``ACTIVE(q)``;
2. ``ACTIVE(q)`` executes one component row, writes ``q'`` back to the
   register, and returns to ``LOAD``.

This replaces the Cartesian product between a large worker table and its
surrounding SG controller by a sum of their state sets.  The state-register
alphabet is large but finite, and every generated row reads and rewrites that
register explicitly, so sparse PEG compilation never expands it as a wildcard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Hashable, Iterable, Sequence

from flat_tm import Shift

ReadAtom = Hashable | frozenset[Hashable] | None


@dataclass(frozen=True)
class ServiceAction:
    next_state: Hashable
    writes: tuple[Hashable | None, ...]
    moves: tuple[Shift, ...]


@dataclass(frozen=True)
class ServiceRow:
    state: Hashable
    reads: tuple[ReadAtom, ...]
    action: ServiceAction

    def matches(self, scanned: Sequence[Hashable]) -> bool:
        for atom, value in zip(self.reads, scanned):
            if atom is None:
                continue
            if isinstance(atom, frozenset):
                if value not in atom:
                    return False
            elif atom != value:
                return False
        return True


@dataclass(frozen=True)
class Active:
    component_state: Hashable


LOAD = ("REGISTERED_SERVICE", "LOAD")
RETURN = ("REGISTERED_SERVICE", "RETURN")
ERROR = ("REGISTERED_SERVICE", "ERROR")
REGISTER_BLANK = ("REGISTERED_SERVICE", "BLANK")


@dataclass
class RegisteredConfiguration:
    state: Hashable
    tapes: list[dict[int, Hashable]]
    heads: list[int]
    steps: int = 0

    def scanned(self, blank: Hashable) -> tuple[Hashable, ...]:
        return tuple(t.get(h, blank) for t, h in zip(self.tapes, self.heads))


class RegisteredComponentService:
    """Lazy ordinary table for one pausable component.

    ``outgoing`` returns sparse component rows with attributes compatible with
    checkpoint_ordinary_tm.SparseRow or symbolic_tm.SymbolicRow.  Sparse-map
    rows are normalized by ``normalize_row`` supplied by the caller.
    """

    def __init__(
        self,
        *,
        tape_alphabets: Sequence[Sequence[Hashable]],
        blank: Hashable,
        outgoing: Callable[[Hashable], Iterable[object]],
        normalize_row: Callable[[object], tuple[tuple[ReadAtom, ...], Hashable, tuple[Hashable | None, ...], tuple[Shift, ...]]],
        ready_states: Iterable[Hashable],
    ) -> None:
        self.component_alphabets = tuple(tuple(a) for a in tape_alphabets)
        self.blank = blank
        self.outgoing = outgoing
        self.normalize_row = normalize_row
        self.ready_states = frozenset(ready_states)
        self.component_tapes = len(self.component_alphabets)
        self.register_tape = self.component_tapes

    def load_row(self, component_state: Hashable) -> ServiceRow:
        reads: list[ReadAtom] = [None] * (self.component_tapes + 1)
        reads[self.register_tape] = component_state
        writes: list[Hashable | None] = [None] * (self.component_tapes + 1)
        moves = [Shift.STAY] * (self.component_tapes + 1)
        next_state = RETURN if component_state in self.ready_states else Active(component_state)
        return ServiceRow(LOAD, tuple(reads), ServiceAction(next_state, tuple(writes), tuple(moves)))

    def active_rows(self, component_state: Hashable) -> tuple[ServiceRow, ...]:
        result: list[ServiceRow] = []
        for source in self.outgoing(component_state):
            reads0, next_component, writes0, moves0 = self.normalize_row(source)
            if len(reads0) != self.component_tapes:
                raise ValueError("component row has wrong arity")
            reads = tuple(reads0) + (component_state,)
            writes = tuple(writes0) + (next_component,)
            moves = tuple(moves0) + (Shift.STAY,)
            result.append(ServiceRow(
                Active(component_state), reads,
                ServiceAction(LOAD, writes, moves),
            ))
        return tuple(result)

    def outgoing_rows(self, state: Hashable, scanned_register: Hashable | None = None) -> tuple[ServiceRow, ...]:
        if state == LOAD:
            if scanned_register is None:
                raise ValueError("LOAD requires the scanned register symbol")
            return (self.load_row(scanned_register),)
        if isinstance(state, Active):
            return self.active_rows(state.component_state)
        return ()

    def wrap_configuration(
        self,
        *,
        component_state: Hashable,
        tapes: Sequence[dict[int, Hashable]],
        heads: Sequence[int],
        steps: int = 0,
    ) -> RegisteredConfiguration:
        if len(tapes) != self.component_tapes or len(heads) != self.component_tapes:
            raise ValueError("wrong component configuration arity")
        return RegisteredConfiguration(
            LOAD,
            [dict(t) for t in tapes] + [{0: component_state}],
            list(heads) + [0],
            steps,
        )

    def component_state(self, config: RegisteredConfiguration) -> Hashable:
        return config.tapes[self.register_tape].get(config.heads[self.register_tape], REGISTER_BLANK)

    def step(self, config: RegisteredConfiguration) -> None:
        scanned = config.scanned(self.blank)
        register = scanned[self.register_tape]
        rows = self.outgoing_rows(config.state, register if config.state == LOAD else None)
        matches = [r for r in rows if r.matches(scanned)]
        if not matches:
            raise RuntimeError(("missing registered-service row", config.state, scanned))
        row = matches[0]
        if any(other.action != row.action for other in matches[1:]):
            raise RuntimeError(("conflicting registered-service rows", config.state, scanned))
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

    def service_one_component_step(self, config: RegisteredConfiguration) -> None:
        if config.state != LOAD:
            raise ValueError(config.state)
        self.step(config)
        if config.state == RETURN:
            return
        self.step(config)
        if config.state != LOAD:
            raise AssertionError(config.state)
