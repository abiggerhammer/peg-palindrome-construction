"""Block-macro scaffolding compiler for bounded-delay ordinary machines.

The direct real-time compiler in :mod:`sparse_realtime_mtm` assumes one
ordinary work-tape transition per input symbol.  This module handles a fixed
bounded number ``B`` of ordinary transitions per input symbol without first
materializing a Hartmanis--Stearns block machine.

Each work tape is partitioned into globally aligned blocks of ``B`` cells.  At
an input boundary the scaffold label stores, for each tape,

* the head offset inside the current block;
* the current block;
* the nearest block on the left and on the right (or ``EMPTY_BLOCK``).

The two scaffold edges for that tape point to the remaining left and right
block stacks.  During at most ``B`` ordinary transitions the head can inspect
only the current block and its two neighbours.  It cannot inspect both
neighbours and finish in either neighbour.  Hence one new scaffold node can
store every modified block, and radius two suffices for the persistent stack
update.

The concrete expansion routine is intended for small machines and proof tests.
The full palindrome compiler uses the same construction through the succinct
rule-family representation in :mod:`succinct_block_peg`.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import FrozenSet, Hashable, Iterable, Iterator, Sequence

from compile_sa_to_peg import compile_to_peg
from peg import Grammar
from realtime_mtm import Move
from scaffold import FieldIs, Guard, LabelIs, Missing, SymbolicScaffoldingAutomaton, Target, Transition

ReadAtom = Hashable | FrozenSet[Hashable] | None
EMPTY_BLOCK = "<EMPTY_BLOCK>"
INITIAL_SCAFFOLD_STATE = ("@INITIAL_SCAFFOLD_STATE",)


@dataclass(frozen=True)
class DelayAction:
    next_state: Hashable
    writes: tuple[Hashable | None, ...]
    moves: tuple[Move, ...]
    emit: int | None = None


@dataclass(frozen=True)
class DelayRow:
    state: Hashable
    input_symbol: str | None
    reads: tuple[ReadAtom, ...]
    action: DelayAction

    def matches(self, input_symbol: str | None, scanned: Sequence[Hashable]) -> bool:
        if self.input_symbol != input_symbol:
            return False
        for atom, actual in zip(self.reads, scanned):
            if atom is None:
                continue
            if isinstance(atom, frozenset):
                if actual not in atom:
                    return False
            elif atom != actual:
                return False
        return True


@dataclass(frozen=True)
class BoundedDelayMachine:
    input_alphabet: tuple[str, ...]
    tape_alphabets: tuple[tuple[Hashable, ...], ...]
    blank: Hashable
    states: tuple[Hashable, ...]
    boundary_states: frozenset[Hashable]
    initial_state: Hashable
    initial_output: int
    rows: tuple[DelayRow, ...]
    delay_bound: int

    def __post_init__(self) -> None:
        if self.delay_bound < 1:
            raise ValueError("delay_bound must be positive")
        if self.initial_state not in self.boundary_states:
            raise ValueError("initial state must be an input boundary")
        if self.initial_output not in (0, 1):
            raise ValueError("initial output must be a bit")
        if any(self.blank not in alphabet for alphabet in self.tape_alphabets):
            raise ValueError("blank missing from tape alphabet")
        arity = len(self.tape_alphabets)
        by_state: dict[Hashable, list[DelayRow]] = {}
        for row in self.rows:
            if len(row.reads) != arity:
                raise ValueError("wrong read arity")
            if len(row.action.writes) != arity or len(row.action.moves) != arity:
                raise ValueError("wrong action arity")
            by_state.setdefault(row.state, []).append(row)
        object.__setattr__(self, "_by_state", by_state)

    @property
    def tape_count(self) -> int:
        return len(self.tape_alphabets)

    def row_for(
        self,
        state: Hashable,
        input_symbol: str | None,
        scanned: Sequence[Hashable],
    ) -> DelayRow:
        matches = [
            row for row in self._by_state.get(state, ())
            if row.matches(input_symbol, scanned)
        ]
        if len(matches) != 1:
            raise RuntimeError(("expected one delay row", state, input_symbol, tuple(scanned), matches))
        return matches[0]

    def audit_determinism(self) -> None:
        for state, rows in self._by_state.items():
            for i, first in enumerate(rows):
                for second in rows[i + 1:]:
                    if first.input_symbol != second.input_symbol:
                        continue
                    if all(
                        _atom_values(a, alphabet) & _atom_values(b, alphabet)
                        for a, b, alphabet in zip(
                            first.reads, second.reads, self.tape_alphabets
                        )
                    ) and first.action != second.action:
                        raise AssertionError(("conflicting delay rows", state, first, second))


@dataclass(frozen=True)
class TapeNeighborhood:
    offset: int
    left_second: Hashable | str
    left_top: Hashable | str
    current: tuple[Hashable, ...]
    right_top: Hashable | str
    right_second: Hashable | str


@dataclass(frozen=True)
class IntervalResult:
    boundary_state: Hashable
    output: int
    neighborhoods: tuple[TapeNeighborhood, ...]
    head_regions: tuple[int, ...]  # -1, 0, +1 relative to old current block.
    steps: int


def _move_delta(move: Move) -> int:
    if move is Move.LEFT:
        return -1
    if move is Move.RIGHT:
        return 1
    return 0


def _atom_values(atom: ReadAtom, alphabet: Sequence[Hashable]) -> set[Hashable]:
    if atom is None:
        return set(alphabet)
    if isinstance(atom, frozenset):
        return set(atom)
    return {atom}


def _blank_block(machine: BoundedDelayMachine, tape: int, block_size: int) -> tuple[Hashable, ...]:
    return tuple(machine.blank for _ in range(block_size))


def _actual_block(value: Hashable | str, blank_block: tuple[Hashable, ...]) -> tuple[Hashable, ...]:
    if value == EMPTY_BLOCK:
        return blank_block
    if not isinstance(value, tuple):
        raise TypeError(value)
    return value


def simulate_interval(
    machine: BoundedDelayMachine,
    boundary_state: Hashable,
    input_symbol: str,
    neighborhoods: Sequence[TapeNeighborhood],
    *,
    block_size: int,
) -> IntervalResult:
    """Run one physical-input interval from a finite three-block neighbourhood."""

    if boundary_state not in machine.boundary_states:
        raise ValueError(boundary_state)
    if block_size < machine.delay_bound:
        raise ValueError("block_size must dominate the delay bound")
    if len(neighborhoods) != machine.tape_count:
        raise ValueError("wrong tape count")

    tapes: list[dict[int, Hashable]] = []
    heads: list[int] = []
    input_left: list[tuple[Hashable, ...]] = []
    input_right: list[tuple[Hashable, ...]] = []
    for tape, neighborhood in enumerate(neighborhoods):
        if not 0 <= neighborhood.offset < block_size:
            raise ValueError(neighborhood.offset)
        blank_block = _blank_block(machine, tape, block_size)
        left = _actual_block(neighborhood.left_top, blank_block)
        current = tuple(neighborhood.current)
        right = _actual_block(neighborhood.right_top, blank_block)
        if len(current) != block_size or len(left) != block_size or len(right) != block_size:
            raise ValueError("block width mismatch")
        store: dict[int, Hashable] = {}
        for base, block in ((-block_size, left), (0, current), (block_size, right)):
            for index, symbol in enumerate(block):
                if symbol != machine.blank:
                    store[base + index] = symbol
        tapes.append(store)
        heads.append(neighborhood.offset)
        input_left.append(left)
        input_right.append(right)

    state = boundary_state
    emitted: int | None = None
    steps = 0
    first = True
    while True:
        scanned = tuple(
            tapes[tape].get(heads[tape], machine.blank)
            for tape in range(machine.tape_count)
        )
        row = machine.row_for(state, input_symbol if first else None, scanned)
        first = False
        for tape, old in enumerate(scanned):
            write = old if row.action.writes[tape] is None else row.action.writes[tape]
            if write == machine.blank:
                tapes[tape].pop(heads[tape], None)
            else:
                tapes[tape][heads[tape]] = write
            heads[tape] += _move_delta(row.action.moves[tape])
            if not -block_size <= heads[tape] < 2 * block_size:
                raise AssertionError(
                    ("delay-bound head escaped three-block window", tape, heads[tape], steps)
                )
        if row.action.emit is not None:
            if emitted is not None:
                raise AssertionError("more than one output in one physical interval")
            if row.action.emit not in (0, 1):
                raise ValueError(row.action.emit)
            emitted = row.action.emit
        state = row.action.next_state
        steps += 1
        if state in machine.boundary_states:
            break
        if steps >= machine.delay_bound:
            raise TimeoutError(("interval exceeded certified delay", state, steps))

    if emitted is None:
        raise AssertionError("physical interval reached a boundary without an output")

    out_neighborhoods: list[TapeNeighborhood] = []
    regions: list[int] = []
    for tape, old in enumerate(neighborhoods):
        def block_at(base: int) -> tuple[Hashable, ...]:
            return tuple(
                tapes[tape].get(base + i, machine.blank) for i in range(block_size)
            )

        left = block_at(-block_size)
        current = block_at(0)
        right = block_at(block_size)
        head = heads[tape]
        if head < 0:
            region = -1
            offset = head + block_size
            # Reaching the left block leaves no time to visit the right block.
            if right != input_right[tape]:
                raise AssertionError("left-ending interval modified the right neighbour")
            new = TapeNeighborhood(
                offset=offset,
                left_second=old.left_second,
                left_top=old.left_second,
                current=left,
                right_top=current,
                right_second=old.right_top,
            )
        elif head >= block_size:
            region = 1
            offset = head - block_size
            # Reaching the right block leaves no time to visit the left block.
            if left != input_left[tape]:
                raise AssertionError("right-ending interval modified the left neighbour")
            new = TapeNeighborhood(
                offset=offset,
                left_second=old.left_top,
                left_top=current,
                current=right,
                right_top=old.right_second,
                right_second=old.right_second,
            )
        else:
            region = 0
            offset = head
            left_value: Hashable | str
            right_value: Hashable | str
            if old.left_top == EMPTY_BLOCK and left == _blank_block(machine, tape, block_size):
                left_value = EMPTY_BLOCK
            else:
                left_value = left
            if old.right_top == EMPTY_BLOCK and right == _blank_block(machine, tape, block_size):
                right_value = EMPTY_BLOCK
            else:
                right_value = right
            new = TapeNeighborhood(
                offset=offset,
                left_second=old.left_second,
                left_top=left_value,
                current=current,
                right_top=right_value,
                right_second=old.right_second,
            )
        out_neighborhoods.append(new)
        regions.append(region)

    return IntervalResult(state, emitted, tuple(out_neighborhoods), tuple(regions), steps)


@dataclass(frozen=True)
class _Layout:
    tape_count: int

    @property
    def output(self) -> int:
        return 0

    def offset(self, tape: int) -> int:
        return 1 + 4 * tape

    def current(self, tape: int) -> int:
        return 2 + 4 * tape

    def left_top(self, tape: int) -> int:
        return 3 + 4 * tape

    def right_top(self, tape: int) -> int:
        return 4 + 4 * tape

    @property
    def field_count(self) -> int:
        return 1 + 4 * self.tape_count


def _blocks(alphabet: Sequence[Hashable], block_size: int) -> tuple[tuple[Hashable, ...], ...]:
    return tuple(tuple(values) for values in product(alphabet, repeat=block_size))


def _side_options(blocks: Sequence[tuple[Hashable, ...]]):
    # (top, second).  EMPTY is canonical: it has no second node.
    yield EMPTY_BLOCK, EMPTY_BLOCK
    for top in blocks:
        yield top, EMPTY_BLOCK
        for second in blocks:
            yield top, second


def _guard_for_label(
    layout: _Layout,
    neighborhoods: Sequence[TapeNeighborhood],
) -> Guard:
    conditions = []
    for tape, neighborhood in enumerate(neighborhoods):
        left_edge = 2 * tape
        right_edge = left_edge + 1
        conditions.extend(
            (
                FieldIs((), layout.offset(tape), neighborhood.offset),
                FieldIs((), layout.current(tape), neighborhood.current),
                FieldIs((), layout.left_top(tape), neighborhood.left_top),
                FieldIs((), layout.right_top(tape), neighborhood.right_top),
            )
        )
        if neighborhood.left_second == EMPTY_BLOCK:
            conditions.append(Missing((left_edge,)))
        else:
            conditions.append(
                FieldIs((left_edge,), layout.left_top(tape), neighborhood.left_second)
            )
        if neighborhood.right_second == EMPTY_BLOCK:
            conditions.append(Missing((right_edge,)))
        else:
            conditions.append(
                FieldIs((right_edge,), layout.right_top(tape), neighborhood.right_second)
            )
    return Guard.all(*conditions)


def _edge_targets(
    old: Sequence[TapeNeighborhood],
    result: IntervalResult,
) -> tuple[Target, ...]:
    targets: list[Target] = []
    for tape, (before, after, region) in enumerate(
        zip(old, result.neighborhoods, result.head_regions)
    ):
        left_edge = 2 * tape
        right_edge = left_edge + 1
        if region == 0:
            left_target = (
                Target.none()
                if after.left_top == EMPTY_BLOCK
                else Target.via((left_edge,))
            )
            right_target = (
                Target.none()
                if after.right_top == EMPTY_BLOCK
                else Target.via((right_edge,))
            )
        elif region == 1:
            left_target = (
                Target.none()
                if before.left_top == EMPTY_BLOCK
                else Target.via(())
            )
            right_target = (
                Target.none()
                if after.right_top == EMPTY_BLOCK
                else Target.via((right_edge, right_edge))
            )
        elif region == -1:
            left_target = (
                Target.none()
                if after.left_top == EMPTY_BLOCK
                else Target.via((left_edge, left_edge))
            )
            right_target = (
                Target.none()
                if before.right_top == EMPTY_BLOCK
                else Target.via(())
            )
        else:  # pragma: no cover
            raise ValueError(region)
        targets.extend((left_target, right_target))
    return tuple(targets)


def _label(layout: _Layout, output: int, neighborhoods: Sequence[TapeNeighborhood]) -> tuple:
    fields: list[Hashable] = [output]
    for neighborhood in neighborhoods:
        fields.extend(
            (
                neighborhood.offset,
                neighborhood.current,
                neighborhood.left_top,
                neighborhood.right_top,
            )
        )
    if len(fields) != layout.field_count:
        raise AssertionError
    return tuple(fields)


def compile_small_bounded_delay_to_scaffold(
    machine: BoundedDelayMachine,
    *,
    block_size: int | None = None,
    max_transitions: int = 250_000,
) -> SymbolicScaffoldingAutomaton:
    """Expand the block construction for a small machine.

    This routine is deliberately guarded by ``max_transitions``.  The full
    palindrome construction is consumed by the succinct compiler and is never
    enumerated.
    """

    machine.audit_determinism()
    block_size = machine.delay_bound if block_size is None else block_size
    if block_size < machine.delay_bound:
        raise ValueError("block_size must dominate delay_bound")
    layout = _Layout(machine.tape_count)
    normal_states = tuple(
        (boundary, output)
        for boundary in machine.boundary_states
        for output in (0, 1)
    )
    # Loff--Moreira--Reis assume, without loss of generality, that the initial
    # state is never re-entered.  Keep that normalization literal here: the
    # unique initial scaffold state handles only the unlabeled base node, and
    # every first-symbol transition enters a normal boundary/output state.
    states = (INITIAL_SCAFFOLD_STATE,) + normal_states
    initial_state = INITIAL_SCAFFOLD_STATE
    accepting = frozenset(
        ([INITIAL_SCAFFOLD_STATE] if machine.initial_output == 1 else [])
        + [state for state in normal_states if state[1] == 1]
    )
    transitions: list[Transition] = []

    blank_neighborhoods = tuple(
        TapeNeighborhood(
            0,
            EMPTY_BLOCK,
            EMPTY_BLOCK,
            _blank_block(machine, tape, block_size),
            EMPTY_BLOCK,
            EMPTY_BLOCK,
        )
        for tape in range(machine.tape_count)
    )
    # First input symbol: the old scaffold top is the unlabeled base node.
    for symbol in machine.input_alphabet:
        result = simulate_interval(
            machine,
            machine.initial_state,
            symbol,
            blank_neighborhoods,
            block_size=block_size,
        )
        transitions.append(
            Transition(
                INITIAL_SCAFFOLD_STATE,
                symbol,
                Guard.all(LabelIs((), None)),
                (result.boundary_state, result.output),
                _label(layout, result.output, result.neighborhoods),
                _edge_targets(blank_neighborhoods, result),
                name=f"initial:{symbol}",
            )
        )

    per_tape_options = []
    for alphabet in machine.tape_alphabets:
        blocks = _blocks(alphabet, block_size)
        options = tuple(
            TapeNeighborhood(offset, left_second, left_top, current, right_top, right_second)
            for offset in range(block_size)
            for current in blocks
            for left_top, left_second in _side_options(blocks)
            for right_top, right_second in _side_options(blocks)
        )
        per_tape_options.append(options)

    estimated = (
        len(normal_states)
        * len(machine.input_alphabet)
        * _product(len(options) for options in per_tape_options)
        + len(machine.input_alphabet)
    )
    if estimated > max_transitions:
        raise ValueError(
            f"concrete macro expansion would create {estimated:,} transitions; "
            f"limit is {max_transitions:,}"
        )

    for state in normal_states:
        boundary, _old_output = state
        for symbol in machine.input_alphabet:
            for neighborhoods in product(*per_tape_options):
                result = simulate_interval(
                    machine,
                    boundary,
                    symbol,
                    neighborhoods,
                    block_size=block_size,
                )
                transitions.append(
                    Transition(
                        state,
                        symbol,
                        _guard_for_label(layout, neighborhoods),
                        (result.boundary_state, result.output),
                        _label(layout, result.output, result.neighborhoods),
                        _edge_targets(neighborhoods, result),
                        name=f"macro:{boundary!r}:{symbol}:{len(transitions)}",
                    )
                )

    return SymbolicScaffoldingAutomaton(
        alphabet=machine.input_alphabet,
        degree=2 * machine.tape_count,
        radius=2,
        states=states,
        initial_state=initial_state,
        accepting_states=accepting,
        transitions=tuple(transitions),
    )


def compile_small_bounded_delay_to_peg(
    machine: BoundedDelayMachine,
    *,
    block_size: int | None = None,
    max_transitions: int = 250_000,
) -> Grammar:
    return compile_to_peg(
        compile_small_bounded_delay_to_scaffold(
            machine,
            block_size=block_size,
            max_transitions=max_transitions,
        )
    )


def run_bounded_delay(machine: BoundedDelayMachine, text: str) -> bool:
    """Reference execution from blank tapes, accepting by the last output bit."""

    tapes = [dict() for _ in range(machine.tape_count)]
    heads = [0 for _ in range(machine.tape_count)]
    state = machine.initial_state
    output = machine.initial_output
    for symbol in text:
        first = True
        emitted = None
        steps = 0
        while True:
            scanned = tuple(
                tapes[tape].get(heads[tape], machine.blank)
                for tape in range(machine.tape_count)
            )
            row = machine.row_for(state, symbol if first else None, scanned)
            first = False
            for tape, old in enumerate(scanned):
                write = old if row.action.writes[tape] is None else row.action.writes[tape]
                if write == machine.blank:
                    tapes[tape].pop(heads[tape], None)
                else:
                    tapes[tape][heads[tape]] = write
                heads[tape] += _move_delta(row.action.moves[tape])
            if row.action.emit is not None:
                if emitted is not None:
                    raise AssertionError("multiple outputs")
                emitted = row.action.emit
            state = row.action.next_state
            steps += 1
            if state in machine.boundary_states:
                break
            if steps >= machine.delay_bound:
                raise TimeoutError
        if emitted is None:
            raise AssertionError("missing output")
        output = emitted
    return bool(output)


def _product(values: Iterable[int]) -> int:
    out = 1
    for value in values:
        out *= value
    return out
