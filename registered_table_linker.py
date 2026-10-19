"""Sum-composition of pausable ordinary-TM components.

Large worker controls are stored as symbols on dedicated state-register tapes.
The global finite control therefore contains only one copy of each component's
states, rather than a Cartesian product of all worker state sets.

A component microstep is serviced by three kinds of global states:

* ``Load(name)`` reads the component-state register;
* ``Active(name, q)`` executes one component row and writes ``q'`` back;
* ``Return(name)`` reads a shared continuation register and resumes the caller.

The linker emits ordinary sparse rows over a single disjoint tape layout.  Its
wildcards are finite presentation shorthand accepted by
``sparse_realtime_mtm``; every emitted row denotes one simultaneous one-cell
multitape transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Hashable, Iterable, Mapping, Sequence

from flat_tm import Shift
from symbolic_tm import SymbolicMultitapeMachine, SymbolicRow

ReadAtom = Hashable | frozenset[Hashable] | None


@dataclass(frozen=True)
class GlobalAction:
    next_state: Hashable
    writes: tuple[Hashable | None, ...]
    moves: tuple[Shift, ...]


@dataclass(frozen=True)
class GlobalRow:
    state: Hashable
    reads: tuple[ReadAtom, ...]
    action: GlobalAction

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
class Load:
    component: str


@dataclass(frozen=True)
class Active:
    component: str
    state_id: int


@dataclass(frozen=True)
class Return:
    component: str


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    machine: SymbolicMultitapeMachine
    ready_states: frozenset[Hashable]
    error_states: frozenset[Hashable] = frozenset()


@dataclass(frozen=True)
class ComponentLayout:
    spec: ComponentSpec
    tape_start: int
    register_tape: int
    state_to_id: Mapping[Hashable, int]
    id_to_state: tuple[Hashable, ...]

    @property
    def tape_count(self) -> int:
        return self.spec.machine.tape_count

    def state_symbol(self, state: Hashable) -> str:
        return f"@{self.spec.name}:q{self.state_to_id[state]}"

    def decode_symbol(self, symbol: str) -> Hashable:
        prefix = f"@{self.spec.name}:q"
        if not isinstance(symbol, str) or not symbol.startswith(prefix):
            raise ValueError((self.spec.name, symbol))
        return self.id_to_state[int(symbol[len(prefix):])]


class RegisteredTableLinker:
    def __init__(self, components: Sequence[ComponentSpec], *, blank: str = "_") -> None:
        self.blank = blank
        self.components = tuple(components)
        layouts: list[ComponentLayout] = []
        tape_alphabets: list[tuple[Hashable, ...]] = []
        cursor = 0
        for spec in self.components:
            if spec.machine.blank != blank:
                raise ValueError((spec.name, spec.machine.blank, blank))
            start = cursor
            tape_alphabets.extend(spec.machine.tape_alphabets)
            cursor += spec.machine.tape_count
            states = tuple(spec.machine.states)
            ids = {state: i for i, state in enumerate(states)}
            register = cursor
            register_alphabet = tuple(
                f"@{spec.name}:q{i}" for i in range(len(states))
            ) + (blank,)
            tape_alphabets.append(register_alphabet)
            cursor += 1
            layouts.append(ComponentLayout(spec, start, register, ids, states))
        self.layouts = tuple(layouts)
        self.by_name = {layout.spec.name: layout for layout in layouts}
        self.continuation_tape = cursor
        # Continuations are installed lazily once the outer program is known.
        self._continuations: set[Hashable] = set()
        tape_alphabets.append((blank,))
        self._base_alphabets = tape_alphabets

    @property
    def tape_count(self) -> int:
        return len(self._base_alphabets)

    def layout(self, name: str) -> ComponentLayout:
        return self.by_name[name]

    def register_continuations(self, continuations: Iterable[Hashable]) -> None:
        self._continuations.update(continuations)

    @staticmethod
    def continuation_symbol(state: Hashable) -> str:
        return "@CONT:" + repr(state)

    def tape_alphabets(self) -> tuple[tuple[Hashable, ...], ...]:
        alphabets = list(self._base_alphabets)
        alphabets[self.continuation_tape] = tuple(
            self.continuation_symbol(state)
            for state in sorted(self._continuations, key=repr)
        ) + (self.blank,)
        return tuple(alphabets)

    def _blank_reads(self) -> list[ReadAtom]:
        return [None] * self.tape_count

    def _blank_writes(self) -> list[Hashable | None]:
        return [None] * self.tape_count

    def _stay_moves(self) -> list[Shift]:
        return [Shift.STAY] * self.tape_count

    def call_rows(
        self,
        *,
        caller_state: Hashable,
        component: str,
        continuation: Hashable,
        entry_transform: Callable[[Hashable], Hashable],
        allowed_states: Iterable[Hashable] | None = None,
    ) -> tuple[GlobalRow, ...]:
        """Rows which install an entry state and call a registered component.

        ``entry_transform`` may depend on the paused component state.  This is
        needed by the history zipper, whose command-entry state retains its
        finite queue role permutation and current symbol.
        """

        layout = self.layout(component)
        self.register_continuations((continuation,))
        states = tuple(allowed_states or layout.spec.ready_states)
        rows: list[GlobalRow] = []
        for paused in states:
            entry = entry_transform(paused)
            if entry not in layout.state_to_id:
                raise ValueError((component, paused, entry))
            reads = self._blank_reads()
            writes = self._blank_writes()
            moves = self._stay_moves()
            reads[layout.register_tape] = layout.state_symbol(paused)
            writes[layout.register_tape] = layout.state_symbol(entry)
            writes[self.continuation_tape] = self.continuation_symbol(continuation)
            rows.append(GlobalRow(
                caller_state,
                tuple(reads),
                GlobalAction(Load(component), tuple(writes), tuple(moves)),
            ))
        return tuple(rows)

    def service_rows(self, component: str) -> tuple[GlobalRow, ...]:
        layout = self.layout(component)
        spec = layout.spec
        rows: list[GlobalRow] = []

        # LOAD dispatches through the finite state-register alphabet.
        for state in layout.id_to_state:
            reads = self._blank_reads()
            writes = self._blank_writes()
            moves = self._stay_moves()
            reads[layout.register_tape] = layout.state_symbol(state)
            if state in spec.error_states:
                next_state: Hashable = ("LINKER_ERROR", component, layout.state_to_id[state])
            elif state in spec.ready_states:
                next_state = Return(component)
            else:
                next_state = Active(component, layout.state_to_id[state])
            rows.append(GlobalRow(
                Load(component), tuple(reads),
                GlobalAction(next_state, tuple(writes), tuple(moves)),
            ))

        # ACTIVE executes one local component row.
        for source in spec.machine.rows:
            qid = layout.state_to_id[source.state]
            next_symbol = layout.state_symbol(source.action.next_state)
            reads = self._blank_reads()
            writes = self._blank_writes()
            moves = self._stay_moves()
            for local, atom in enumerate(source.reads):
                reads[layout.tape_start + local] = atom
            reads[layout.register_tape] = layout.state_symbol(source.state)
            for local, value in enumerate(source.action.writes):
                writes[layout.tape_start + local] = value
            writes[layout.register_tape] = next_symbol
            for local, move in enumerate(source.action.moves):
                moves[layout.tape_start + local] = move
            rows.append(GlobalRow(
                Active(component, qid), tuple(reads),
                GlobalAction(Load(component), tuple(writes), tuple(moves)),
            ))

        # RETURN resumes whichever finite continuation symbol the caller stored.
        for continuation in sorted(self._continuations, key=repr):
            reads = self._blank_reads()
            writes = self._blank_writes()
            moves = self._stay_moves()
            reads[self.continuation_tape] = self.continuation_symbol(continuation)
            rows.append(GlobalRow(
                Return(component), tuple(reads),
                GlobalAction(continuation, tuple(writes), tuple(moves)),
            ))
        return tuple(rows)

    def all_service_rows(self) -> tuple[GlobalRow, ...]:
        rows: list[GlobalRow] = []
        for layout in self.layouts:
            rows.extend(self.service_rows(layout.spec.name))
        return tuple(rows)

    def initial_tapes_and_heads(
        self,
        configurations: Mapping[str, object],
    ) -> tuple[list[dict[int, Hashable]], list[int]]:
        tapes = [dict() for _ in range(self.tape_count)]
        heads = [0] * self.tape_count
        for layout in self.layouts:
            config = configurations[layout.spec.name]
            if len(config.tapes) != layout.tape_count:
                raise ValueError((layout.spec.name, len(config.tapes), layout.tape_count))
            for local in range(layout.tape_count):
                tapes[layout.tape_start + local] = dict(config.tapes[local])
                heads[layout.tape_start + local] = config.heads[local]
            tapes[layout.register_tape][0] = layout.state_symbol(config.state)
        return tapes, heads


@dataclass
class LinkedConfiguration:
    state: Hashable
    tapes: list[dict[int, Hashable]]
    heads: list[int]
    steps: int = 0


class LinkedInterpreter:
    def __init__(self, linker: RegisteredTableLinker, rows: Sequence[GlobalRow]) -> None:
        self.linker = linker
        self.rows = tuple(rows)
        by_state: dict[Hashable, list[GlobalRow]] = {}
        for row in self.rows:
            by_state.setdefault(row.state, []).append(row)
        self.by_state = by_state

    def scanned(self, config: LinkedConfiguration) -> tuple[Hashable, ...]:
        return tuple(
            config.tapes[i].get(config.heads[i], self.linker.blank)
            for i in range(self.linker.tape_count)
        )

    def step(self, config: LinkedConfiguration) -> None:
        scanned = self.scanned(config)
        matches = [r for r in self.by_state.get(config.state, ()) if r.matches(scanned)]
        if not matches:
            raise RuntimeError(("missing linked row", config.state, scanned))
        action = matches[0].action
        if any(row.action != action for row in matches[1:]):
            raise RuntimeError(("conflicting linked rows", config.state, scanned))
        for tape, old in enumerate(scanned):
            value = old if action.writes[tape] is None else action.writes[tape]
            pos = config.heads[tape]
            if value == self.linker.blank:
                config.tapes[tape].pop(pos, None)
            else:
                config.tapes[tape][pos] = value
            config.heads[tape] += int(action.moves[tape])
        config.state = action.next_state
        config.steps += 1
