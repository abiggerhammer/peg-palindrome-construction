"""Eliminate shared *read-only* tape units by exact duplication.

The only reason a read-only tape needs several logical heads is independent
positioning.  Giving each head an identical private copy of the tape is an
exact, zero-slowdown transformation.  This module performs that transformation
on :class:`flat_multihead.FlatMultiheadMachine` tables and their configurations.

It deliberately refuses to duplicate a shared tape if any logical head can
change a scanned cell.  Writable shared units are reported explicitly for the
next storage-lowering stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

from flat_multihead import (
    FlatMultiheadMachine,
    MultiheadAction,
    MultiheadConfiguration,
)
from flat_tm import FlatAction, FlatConfiguration, FlatMultitapeMachine


@dataclass(frozen=True)
class TapeCopy:
    """One physical tape created from an original source tape."""

    new_tape: int
    old_tape: int
    owner_head: int | None  # None means the original shared unit was retained.


@dataclass(frozen=True)
class ReadonlySplitResult:
    machine: FlatMultiheadMachine
    copies: tuple[TapeCopy, ...]
    old_to_new_tapes: tuple[tuple[int, ...], ...]
    remaining_shared_tapes: tuple[int, ...]

    def transform_configuration(
        self, old_machine: FlatMultiheadMachine, config: MultiheadConfiguration
    ) -> MultiheadConfiguration:
        if len(config.tapes) != old_machine.tape_count:
            raise ValueError("configuration belongs to a different machine")

        new_tapes: list[dict[int, str]] = [dict() for _ in self.copies]
        for copy in self.copies:
            new_tapes[copy.new_tape] = dict(config.tapes[copy.old_tape])

        # Logical head numbering is unchanged.  Only head_to_tape changed.
        return MultiheadConfiguration(
            state=config.state,
            tapes=new_tapes,
            heads=list(config.heads),
            steps=config.steps,
        )


def heads_on_tape(machine: FlatMultiheadMachine, tape: int) -> tuple[int, ...]:
    return tuple(i for i, t in enumerate(machine.head_to_tape) if t == tape)


def tape_is_read_only(machine: FlatMultiheadMachine, tape: int) -> bool:
    """Return true iff every head on ``tape`` preserves its scanned symbol."""

    relevant = set(heads_on_tape(machine, tape))
    for (state, reads), action in machine.delta.items():
        del state
        for head in relevant:
            if action.writes[head] != reads[head]:
                return False
    return True


def split_readonly_shared_tapes(
    machine: FlatMultiheadMachine,
) -> ReadonlySplitResult:
    """Duplicate every read-only tape that carries more than one head.

    Writable shared tapes are retained as shared units.  The source transition
    table does not need to change: reads, writes, and moves remain indexed by
    logical head, and the interpreter already maps each head through the new
    ``head_to_tape`` tuple.
    """

    new_alphabets: list[tuple[str, ...]] = []
    copies: list[TapeCopy] = []
    old_to_new: list[list[int]] = [[] for _ in range(machine.tape_count)]
    new_head_to_tape = [-1] * machine.head_count
    remaining_shared: list[int] = []

    for old_tape in range(machine.tape_count):
        heads = heads_on_tape(machine, old_tape)
        if len(heads) > 1 and tape_is_read_only(machine, old_tape):
            for head in heads:
                new_tape = len(new_alphabets)
                new_alphabets.append(machine.tape_alphabets[old_tape])
                copies.append(TapeCopy(new_tape, old_tape, head))
                old_to_new[old_tape].append(new_tape)
                new_head_to_tape[head] = new_tape
        else:
            new_tape = len(new_alphabets)
            new_alphabets.append(machine.tape_alphabets[old_tape])
            copies.append(TapeCopy(new_tape, old_tape, None))
            old_to_new[old_tape].append(new_tape)
            for head in heads:
                new_head_to_tape[head] = new_tape
            if len(heads) > 1:
                remaining_shared.append(new_tape)

    assert all(t >= 0 for t in new_head_to_tape)
    lowered = FlatMultiheadMachine(
        blank=machine.blank,
        tape_alphabets=tuple(new_alphabets),
        head_to_tape=tuple(new_head_to_tape),
        states=machine.states,
        halting_states=machine.halting_states,
        delta=dict(machine.delta),
    )
    return ReadonlySplitResult(
        machine=lowered,
        copies=tuple(copies),
        old_to_new_tapes=tuple(tuple(x) for x in old_to_new),
        remaining_shared_tapes=tuple(remaining_shared),
    )


def to_flat_multitape(machine: FlatMultiheadMachine) -> FlatMultitapeMachine:
    """Convert an unshared multihead table to the ordinary flat-TM model."""

    if len(set(machine.head_to_tape)) != machine.head_count:
        raise ValueError("machine still has a shared tape unit")
    if machine.tape_count != machine.head_count:
        raise ValueError("unreferenced or multiply referenced physical tape")

    # Reorder physical tapes into logical-head order.  This keeps transition
    # tuple order unchanged and makes every head exactly one ordinary tape.
    alphabet: list[str] = []
    for head in range(machine.head_count):
        tape = machine.head_to_tape[head]
        for symbol in machine.tape_alphabets[tape]:
            if symbol not in alphabet:
                alphabet.append(symbol)

    delta: dict[tuple[Hashable, tuple[str, ...]], FlatAction] = {}
    for key, action in machine.delta.items():
        delta[key] = FlatAction(action.next_state, action.writes, action.moves)

    return FlatMultitapeMachine(
        alphabet=tuple(alphabet),
        blank=machine.blank,
        tape_count=machine.head_count,
        states=machine.states,
        halting_states=machine.halting_states,
        delta=delta,
    )


def to_flat_configuration(
    machine: FlatMultiheadMachine, config: MultiheadConfiguration
) -> FlatConfiguration:
    """Convert a configuration after all shared tapes have been removed."""

    if len(set(machine.head_to_tape)) != machine.head_count:
        raise ValueError("machine still has a shared tape unit")
    tapes = [dict(config.tapes[machine.head_to_tape[h]]) for h in range(machine.head_count)]
    return FlatConfiguration(config.state, tapes, list(config.heads), config.steps)


def append_read_unit_signature(
    machine: FlatMultiheadMachine, tape: int
) -> dict[str, object]:
    """Audit whether a two-head unit has one reader and one append-only writer.

    This is the exact residual unit in Fischer--Paterson Algorithm Y after the
    read-only pattern tape is duplicated.  The function does not perform its
    simulation; it proves the structural preconditions needed by the next
    specialized SR-unit compiler.
    """

    heads = heads_on_tape(machine, tape)
    if len(heads) != 2:
        raise ValueError("append/read audit requires exactly two heads")

    stats = []
    for head in heads:
        preserves = True
        writes_nonblank_only_on_blank = True
        moves = set()
        ever_changes = False
        for (_, reads), action in machine.delta.items():
            read = reads[head]
            write = action.writes[head]
            move = action.moves[head]
            moves.add(int(move))
            if write != read:
                preserves = False
                ever_changes = True
                if not (read == machine.blank and write != machine.blank):
                    writes_nonblank_only_on_blank = False
        stats.append(
            {
                "head": head,
                "preserves": preserves,
                "ever_changes": ever_changes,
                "writes_nonblank_only_on_blank": writes_nonblank_only_on_blank,
                "moves": tuple(sorted(moves)),
            }
        )

    readers = [s for s in stats if s["preserves"]]
    writers = [
        s
        for s in stats
        if s["ever_changes"]
        and s["writes_nonblank_only_on_blank"]
        and set(s["moves"]).issubset({0, 1})
    ]
    return {
        "tape": tape,
        "heads": heads,
        "head_stats": tuple(stats),
        "reader_heads": tuple(s["head"] for s in readers),
        "append_writer_heads": tuple(s["head"] for s in writers),
        "is_append_read_unit": len(readers) == 1 and len(writers) == 1,
    }
