"""Mechanical one-head-per-tape table for Fischer--Paterson Algorithm Y.

The only shared source tape left after duplicating the frozen pattern is the
unary-Delta append/read unit.  This module lowers that unit to ten physical
stack tapes plus two unary-counter tapes.  Every emitted row is one ordinary
one-cell multitape TM step.  Whole-stack assignments in the imperative
Hood--Melville description become one of twelve finite role permutations;
stack reset abandons the old epoch behind a fresh bottom marker in two steps.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Hashable

from flat_tm import Shift
from fp_algorithm_y_multihead import (
    A, B, C, D, S, T, U, BLANK, HALT as SOURCE_HALT,
    MACHINE as SOURCE, initial_configuration as source_initial,
)
from algorithm_y_append_read import delta_blocks_from_word
from strict_stack_queue import RotationPhase, StrictStackQueue
from symbolic_tm import (
    ReadAtom, SymbolicConfiguration, SymbolicMultitapeMachine,
    SymbolicTableBuilder,
)

# Ordinary tapes.
PAT_A, PAT_B, TS, TT, TU = range(5)
STACK_BASE = 5
STACK_COUNT = 10  # left, front, and eight queue-role physical stacks
OK_TAPE = STACK_BASE + STACK_COUNT
BUDGET_TAPE = OK_TAPE + 1
TAPE_COUNT = BUDGET_TAPE + 1

# Physical stack indices within STACK_BASE..
LEFT_PHYS = 0
FRONT_PHYS = 1
QUEUE_PHYS_BASE = 2

ROLES = ("f1", "f2", "rear", "fwork", "fp", "rold", "rp1", "rp2")
ROLE_INDEX = {name: i for i, name in enumerate(ROLES)}
IDENTITY_MAPPING = tuple(range(8))

BOTTOM = "B"
COUNTER_ONE = "1"
VALUE_SYMBOLS = (BLANK, "#", "0", "1")
ENCODE = {value: f"v{value}" for value in VALUE_SYMBOLS}
DECODE = {encoded: value for value, encoded in ENCODE.items()}
STACK_ALPHABET = (BLANK, BOTTOM) + tuple(ENCODE.values())
COUNTER_ALPHABET = (BLANK, BOTTOM, COUNTER_ONE)

ALL_STAY = (Shift.STAY,) * TAPE_COUNT
HALT_TASK = ("HALT",)
DISPATCH_TASK = ("DISPATCH",)
RETURN_TASK = ("RETURN",)
ERROR_STATE = "Y_OTM_ERROR"


@dataclass(frozen=True)
class YState:
    source: Hashable
    current: str
    phase: str
    mapping: tuple[int, ...]
    task: tuple
    h0: str | None = None
    h1: str | None = None


def _phase_name(phase: RotationPhase | str) -> str:
    return phase.name if isinstance(phase, RotationPhase) else phase


def _queue_phys(state: YState, role: str) -> int:
    return QUEUE_PHYS_BASE + state.mapping[ROLE_INDEX[role]]


def _stack_phys(state: YState, role: str) -> int:
    if role == "left":
        return LEFT_PHYS
    if role == "front":
        return FRONT_PHYS
    return _queue_phys(state, role)


def _stack_tape(state: YState, role: str) -> int:
    return STACK_BASE + _stack_phys(state, role)


def _counter_tape(name: str) -> int:
    return OK_TAPE if name == "ok" else BUDGET_TAPE


def _set_hold(state: YState, slot: int, value: str | None) -> YState:
    return replace(state, **({"h0": value} if slot == 0 else {"h1": value}))


def _with_task(state: YState, task: tuple) -> YState:
    return replace(state, task=task)


def _swap_mapping(mapping: tuple[int, ...], *pairs: tuple[str, str]) -> tuple[int, ...]:
    result = list(mapping)
    for left, right in pairs:
        i, j = ROLE_INDEX[left], ROLE_INDEX[right]
        result[i], result[j] = result[j], result[i]
    return tuple(result)


def _reads_at(tape: int, atom: ReadAtom) -> tuple[ReadAtom, ...]:
    values: list[ReadAtom] = [None] * TAPE_COUNT
    values[tape] = atom
    return tuple(values)


def _writes_at(tape: int, symbol: str | None) -> tuple[str | None, ...]:
    values: list[str | None] = [None] * TAPE_COUNT
    values[tape] = symbol
    return tuple(values)


def _moves_at(tape: int, move: Shift) -> tuple[Shift, ...]:
    values = [Shift.STAY] * TAPE_COUNT
    values[tape] = move
    return tuple(values)


def _merge_reads(*parts: tuple[ReadAtom, ...]) -> tuple[ReadAtom, ...]:
    result: list[ReadAtom] = [None] * TAPE_COUNT
    for part in parts:
        for i, atom in enumerate(part):
            if atom is None:
                continue
            if result[i] is not None and result[i] != atom:
                raise ValueError((i, result[i], atom))
            result[i] = atom
    return tuple(result)


def _source_atom_accepts(atom: str | None, symbol: str) -> bool:
    return atom is None or atom == symbol


class _Generator:
    def __init__(self) -> None:
        tape_alphabets = (
            SOURCE.tape_alphabets[0], SOURCE.tape_alphabets[0],
            SOURCE.tape_alphabets[2], SOURCE.tape_alphabets[3], SOURCE.tape_alphabets[4],
        ) + (STACK_ALPHABET,) * STACK_COUNT + (COUNTER_ALPHABET, COUNTER_ALPHABET)
        self.builder = SymbolicTableBuilder(tape_alphabets, BLANK)
        self.pending: deque[YState] = deque()
        self.seen: set[YState] = set()
        self.halting: set[YState] = set()
        self.source_by_state: dict[Hashable, list] = {}
        for schema in SOURCE.schemata:
            self.source_by_state.setdefault(schema.state, []).append(schema)

    def discover(self, state: Hashable) -> None:
        if isinstance(state, YState) and state not in self.seen:
            self.seen.add(state)
            self.pending.append(state)

    def add(
        self, state: YState, reads: tuple[ReadAtom, ...], next_state: Hashable,
        writes: tuple[str | None, ...] | None = None,
        moves: tuple[Shift, ...] | None = None,
    ) -> None:
        self.builder.add(
            state, reads, next_state,
            writes if writes is not None else (None,) * TAPE_COUNT,
            moves if moves is not None else ALL_STAY,
        )
        self.discover(next_state)

    def noop(self, state: YState, next_state: Hashable) -> None:
        self.add(state, (None,) * TAPE_COUNT, next_state)

    def primitive_push(self, state: YState, role: str, value: str, cont: tuple) -> None:
        tape = _stack_tape(state, role)
        next_state = _with_task(state, ("PUSH_WRITE", role, value, cont))
        self.add(state, (None,) * TAPE_COUNT, next_state, moves=_moves_at(tape, Shift.RIGHT))

    def primitive_push_write(self, state: YState, role: str, value: str, cont: tuple) -> None:
        tape = _stack_tape(state, role)
        self.add(
            state, _reads_at(tape, BLANK), _with_task(state, cont),
            writes=_writes_at(tape, ENCODE[value]),
        )

    def primitive_pop(
        self, state: YState, role: str, slot: int,
        empty_cont: tuple, value_cont: tuple,
    ) -> None:
        tape = _stack_tape(state, role)
        self.add(state, _reads_at(tape, BOTTOM), _with_task(state, empty_cont))
        for encoded, value in DECODE.items():
            next_state = _with_task(_set_hold(state, slot, value), value_cont)
            self.add(
                state, _reads_at(tape, encoded), next_state,
                writes=_writes_at(tape, BLANK), moves=_moves_at(tape, Shift.LEFT),
            )

    def primitive_reset(self, state: YState, role: str, cont: tuple) -> None:
        tape = _stack_tape(state, role)
        self.add(
            state, (None,) * TAPE_COUNT,
            _with_task(state, ("RESET_WRITE", role, cont)),
            moves=_moves_at(tape, Shift.RIGHT),
        )

    def primitive_reset_write(self, state: YState, role: str, cont: tuple) -> None:
        tape = _stack_tape(state, role)
        self.add(
            state, _reads_at(tape, BLANK), _with_task(state, cont),
            writes=_writes_at(tape, BOTTOM),
        )

    def primitive_inc(self, state: YState, name: str, cont: tuple) -> None:
        tape = _counter_tape(name)
        self.add(
            state, (None,) * TAPE_COUNT,
            _with_task(state, ("INC_WRITE", name, cont)),
            moves=_moves_at(tape, Shift.RIGHT),
        )

    def primitive_inc_write(self, state: YState, name: str, cont: tuple) -> None:
        tape = _counter_tape(name)
        self.add(
            state, _reads_at(tape, BLANK), _with_task(state, cont),
            writes=_writes_at(tape, COUNTER_ONE),
        )

    def primitive_dec(
        self, state: YState, name: str, zero_cont: tuple, nonzero_cont: tuple
    ) -> None:
        tape = _counter_tape(name)
        self.add(state, _reads_at(tape, BOTTOM), _with_task(state, zero_cont))
        self.add(
            state, _reads_at(tape, COUNTER_ONE), _with_task(state, nonzero_cont),
            writes=_writes_at(tape, BLANK), moves=_moves_at(tape, Shift.LEFT),
        )

    def generate_dispatch(self, state: YState) -> None:
        if state.source == SOURCE_HALT:
            halt = _with_task(state, HALT_TASK)
            self.noop(state, halt)
            self.halting.add(halt)
            return
        for schema in self.source_by_state.get(state.source, ()):  # exact symbolic source rows
            if not _source_atom_accepts(schema.reads[C], state.current):
                continue
            if not _source_atom_accepts(schema.reads[D], BLANK):
                continue
            reads: list[ReadAtom] = [None] * TAPE_COUNT
            for logical, tape in ((A, PAT_A), (B, PAT_B), (S, TS), (T, TT), (U, TU)):
                reads[tape] = schema.reads[logical]
            writes: list[str | None] = [None] * TAPE_COUNT
            moves: list[Shift] = [Shift.STAY] * TAPE_COUNT
            for logical, tape in ((A, PAT_A), (B, PAT_B), (S, TS), (T, TT), (U, TU)):
                writes[tape] = schema.writes[logical]
                moves[tape] = schema.moves[logical]

            c_write = schema.writes[C]
            if c_write is not None and c_write != state.current:
                raise AssertionError((schema, state.current))
            d_write = schema.writes[D]
            ops: list[tuple] = []
            if d_write is not None and d_write != BLANK:
                if schema.moves[D] is not Shift.RIGHT:
                    raise AssertionError(schema)
                ops.append(("APPEND", d_write))
            elif schema.moves[D] is not Shift.STAY:
                raise AssertionError(schema)
            if schema.moves[C] is Shift.LEFT:
                ops.append(("LEFT",))
            elif schema.moves[C] is Shift.RIGHT:
                ops.append(("RIGHT",))
            elif schema.moves[C] is not Shift.STAY:
                raise AssertionError(schema)

            next_control = replace(
                state, source=schema.next_state,
                task=("OPS", tuple(ops)) if ops else RETURN_TASK,
            )
            self.add(state, tuple(reads), next_control, tuple(writes), tuple(moves))

    def generate(self, state: YState) -> None:  # noqa: C901 - explicit microprogram dispatcher
        task = state.task
        tag = task[0]
        if tag == "HALT":
            self.halting.add(state)
            return
        if tag == "DISPATCH":
            self.generate_dispatch(state)
            return
        if tag == "RETURN":
            next_task = HALT_TASK if state.source == SOURCE_HALT else DISPATCH_TASK
            target = _with_task(state, next_task)
            self.noop(state, target)
            if next_task == HALT_TASK:
                self.halting.add(target)
            return
        if tag == "OPS":
            ops = task[1]
            if not ops:
                self.noop(state, _with_task(state, RETURN_TASK))
                return
            first, rest = ops[0], ops[1:]
            cont = ("OPS", rest)
            if first[0] == "APPEND":
                self.noop(state, _with_task(state, ("Q_SNOC", first[1], cont)))
            elif first[0] == "LEFT":
                self.noop(state, _with_task(state, ("ZIP_LEFT", cont)))
            elif first[0] == "RIGHT":
                self.noop(state, _with_task(state, ("ZIP_RIGHT", cont)))
            else:
                raise AssertionError(first)
            return

        # Physical primitives.
        if tag == "PUSH_MOVE":
            _, role, value, cont = task
            self.primitive_push(state, role, value, cont); return
        if tag == "PUSH_WRITE":
            _, role, value, cont = task
            self.primitive_push_write(state, role, value, cont); return
        if tag == "POP":
            _, role, slot, empty_cont, value_cont = task
            self.primitive_pop(state, role, slot, empty_cont, value_cont); return
        if tag == "RESET_MOVE":
            _, role, cont = task
            self.primitive_reset(state, role, cont); return
        if tag == "RESET_WRITE":
            _, role, cont = task
            self.primitive_reset_write(state, role, cont); return
        if tag == "INC_MOVE":
            _, name, cont = task
            self.primitive_inc(state, name, cont); return
        if tag == "INC_WRITE":
            _, name, cont = task
            self.primitive_inc_write(state, name, cont); return
        if tag == "DEC":
            _, name, zero_cont, nonzero_cont = task
            self.primitive_dec(state, name, zero_cont, nonzero_cont); return

        # Zipper operations.
        if tag == "ZIP_LEFT":
            cont = task[1]
            self.noop(state, _with_task(state, ("PUSH_MOVE", "front", state.current,
                                                  ("ZIP_LEFT_POP", cont)))); return
        if tag == "ZIP_LEFT_POP":
            cont = task[1]
            self.noop(state, _with_task(state, ("POP", "left", 0,
                                                  ("ZIP_SET_CURRENT", BLANK, cont),
                                                  ("ZIP_SET_H0_CURRENT", cont)))); return
        if tag == "ZIP_SET_CURRENT":
            _, value, cont = task
            self.noop(state, _with_task(replace(state, current=value), cont)); return
        if tag == "ZIP_SET_H0_CURRENT":
            cont = task[1]
            assert state.h0 is not None
            self.noop(state, _with_task(replace(state, current=state.h0), cont)); return
        if tag == "ZIP_RIGHT":
            cont = task[1]
            self.noop(state, _with_task(state, ("PUSH_MOVE", "left", state.current,
                                                  ("ZIP_RIGHT_CHOOSE", cont)))); return
        if tag == "ZIP_RIGHT_CHOOSE":
            cont = task[1]
            front_tape = _stack_tape(state, "front")
            self.add(
                state, _reads_at(front_tape, BOTTOM),
                _with_task(state, ("ZIP_RIGHT_QUEUE", cont)),
            )
            for encoded in DECODE:
                self.add(
                    state, _reads_at(front_tape, encoded),
                    _with_task(state, ("POP", "front", 0, ("ERROR",),
                                            ("ZIP_SET_H0_CURRENT", cont))),
                )
            return
        if tag == "ZIP_RIGHT_QUEUE":
            cont = task[1]
            tape = _stack_tape(state, "f1")
            self.add(
                state, _reads_at(tape, BOTTOM),
                _with_task(replace(state, current=BLANK), cont),
            )
            for encoded, value in DECODE.items():
                # Queue values are only 0/1, but accepting the finite value
                # alphabet makes the table total over valid stack encodings.
                target = _with_task(replace(state, current=value), ("Q_TAIL", cont))
                self.add(state, _reads_at(tape, encoded), target)
            return

        # Queue public operations and two-tick schedule.
        if tag == "Q_SNOC":
            _, value, cont = task
            self.noop(state, _with_task(state, ("PUSH_MOVE", "rear", value,
                                                  ("Q_CONSUME", True, 2, cont)))); return
        if tag == "Q_TAIL":
            cont = task[1]
            self.noop(state, _with_task(state, ("POP", "f1", 0, ("ERROR",),
                                                  ("Q_TAIL_AFTER_F1", cont)))); return
        if tag == "Q_TAIL_AFTER_F1":
            cont = task[1]
            if state.phase == "IDLE":
                nxt = ("POP", "f2", 0, ("ERROR",), ("Q_CONSUME", True, 2, cont))
            elif state.phase == "REVERSING":
                nxt = ("DEC", "ok", ("ERROR",), ("Q_CONSUME", True, 2, cont))
            else:
                nxt = ("Q_INVALIDATE_APP", cont)
            self.noop(state, _with_task(state, nxt)); return
        if tag == "Q_INVALIDATE_APP":
            cont = task[1]
            tape = OK_TAPE
            self.add(
                state, _reads_at(tape, BOTTOM),
                _with_task(state, ("POP", "rp1", 0, ("ERROR",),
                                        ("Q_INVALIDATE_APP_RP2", cont))),
            )
            self.add(
                state, _reads_at(tape, COUNTER_ONE),
                _with_task(state, ("DEC", "ok", ("ERROR",),
                                        ("Q_CONSUME", True, 2, cont))),
            )
            return
        if tag == "Q_INVALIDATE_APP_RP2":
            cont = task[1]
            self.noop(state, _with_task(state, ("POP", "rp2", 0, ("ERROR",),
                                                  ("Q_CONSUME", True, 2, cont)))); return
        if tag == "Q_CONSUME":
            _, allow_start, ticks, cont = task
            tape = BUDGET_TAPE
            if state.phase == "IDLE":
                if allow_start:
                    self.add(
                        state, _reads_at(tape, BOTTOM),
                        _with_task(state, ("Q_START", ticks, cont)),
                    )
                else:
                    self.add(state, _reads_at(tape, BOTTOM), ERROR_STATE)
                self.add(
                    state, _reads_at(tape, COUNTER_ONE),
                    _with_task(state, ("DEC", "budget", ("ERROR",),
                                            ("Q_RUN_TICKS", ticks, cont))),
                )
            else:
                self.add(state, _reads_at(tape, BOTTOM), ERROR_STATE)
                self.add(
                    state, _reads_at(tape, COUNTER_ONE),
                    _with_task(state, ("DEC", "budget", ("ERROR",),
                                            ("Q_RUN_TICKS", ticks, cont))),
                )
            return
        if tag == "Q_START":
            _, ticks, cont = task
            new_mapping = _swap_mapping(
                state.mapping, ("fwork", "f2"), ("rold", "rear")
            )
            target = replace(
                state, phase="REVERSING", mapping=new_mapping,
                task=("Q_RUN_TICKS", ticks, cont),
            )
            reads = _merge_reads(
                _reads_at(_stack_tape(state, "fwork"), BOTTOM),
                _reads_at(_stack_tape(state, "rold"), BOTTOM),
                _reads_at(OK_TAPE, BOTTOM), _reads_at(BUDGET_TAPE, BOTTOM),
            )
            self.add(state, reads, target); return
        if tag == "Q_RUN_TICKS":
            _, ticks, cont = task
            if ticks == 0:
                self.noop(state, _with_task(state, cont))
            else:
                self.noop(state, _with_task(state, ("Q_TICK", ("Q_RUN_TICKS", ticks - 1, cont))))
            return
        if tag == "Q_TICK":
            cont = task[1]
            if state.phase == "IDLE":
                self.noop(state, _with_task(state, cont)); return
            if state.phase == "REVERSING":
                tape = _stack_tape(state, "fwork")
                self.add(
                    state, _reads_at(tape, BOTTOM),
                    _with_task(state, ("POP", "rold", 1, ("ERROR",),
                                            ("Q_REV_LAST_AFTER_Y", cont))),
                )
                for encoded in DECODE:
                    self.add(
                        state, _reads_at(tape, encoded),
                        _with_task(state, ("POP", "fwork", 0, ("ERROR",),
                                                ("Q_REV_AFTER_X", cont))),
                    )
                return
            # APPENDING
            self.add(
                state, _reads_at(OK_TAPE, BOTTOM),
                _with_task(state, ("RESET_MOVE", "fp", ("Q_FINALIZE_SWAP", cont))),
            )
            self.add(
                state, _reads_at(OK_TAPE, COUNTER_ONE),
                _with_task(state, ("POP", "fp", 0, ("ERROR",),
                                        ("Q_APP_AFTER_X", cont))),
            )
            return
        if tag == "Q_REV_AFTER_X":
            cont = task[1]
            self.noop(state, _with_task(state, ("POP", "rold", 1, ("ERROR",),
                                                  ("Q_REV_PUSH_FP", cont)))); return
        if tag == "Q_REV_PUSH_FP":
            cont = task[1]; assert state.h0 is not None
            self.noop(state, _with_task(state, ("PUSH_MOVE", "fp", state.h0,
                                                  ("Q_REV_PUSH_RP1", cont)))); return
        if tag == "Q_REV_PUSH_RP1":
            cont = task[1]; assert state.h1 is not None
            self.noop(state, _with_task(state, ("PUSH_MOVE", "rp1", state.h1,
                                                  ("Q_REV_PUSH_RP2", cont)))); return
        if tag == "Q_REV_PUSH_RP2":
            cont = task[1]; assert state.h1 is not None
            self.noop(state, _with_task(state, ("PUSH_MOVE", "rp2", state.h1,
                                                  ("INC_MOVE", "ok",
                                                   ("INC_MOVE", "budget",
                                                    ("INC_MOVE", "budget", cont)))))); return
        if tag == "Q_REV_LAST_AFTER_Y":
            cont = task[1]
            tape = _stack_tape(state, "rold")
            assert state.h1 is not None
            target = ("PUSH_MOVE", "rp1", state.h1, ("Q_REV_LAST_RP2", cont))
            self.add(state, _reads_at(tape, BOTTOM), _with_task(state, target)); return
        if tag == "Q_REV_LAST_RP2":
            cont = task[1]; assert state.h1 is not None
            target = _with_task(
                replace(state, phase="APPENDING"),
                ("PUSH_MOVE", "rp2", state.h1,
                 ("INC_MOVE", "budget", cont)),
            )
            self.noop(state, target); return
        if tag == "Q_APP_AFTER_X":
            cont = task[1]; assert state.h0 is not None
            self.noop(state, _with_task(state, ("PUSH_MOVE", "rp1", state.h0,
                                                  ("Q_APP_RP2", cont)))); return
        if tag == "Q_APP_RP2":
            cont = task[1]; assert state.h0 is not None
            self.noop(state, _with_task(state, ("PUSH_MOVE", "rp2", state.h0,
                                                  ("DEC", "ok", ("ERROR",), cont)))); return
        if tag == "Q_FINALIZE_SWAP":
            cont = task[1]
            mapping = _swap_mapping(
                state.mapping, ("f1", "rp1"), ("f2", "rp2")
            )
            target = replace(
                state, phase="IDLE", mapping=mapping,
                task=("RESET_MOVE", "rp1",
                      ("RESET_MOVE", "rp2",
                       ("RESET_MOVE", "fwork",
                        ("RESET_MOVE", "rold", cont)))),
            )
            self.noop(state, target); return

        if tag == "ERROR":
            self.noop(state, ERROR_STATE); return
        raise AssertionError(("unknown task", task))

    def build(self) -> SymbolicMultitapeMachine:
        seeds = [
            YState("Y_TEST_MOVE", "0", "IDLE", IDENTITY_MAPPING, DISPATCH_TASK),
            YState(SOURCE_HALT, "0", "IDLE", IDENTITY_MAPPING, HALT_TASK),
        ]
        for seed in seeds:
            self.discover(seed)
        while self.pending:
            self.generate(self.pending.popleft())
        self.builder.states.add(ERROR_STATE)
        return self.builder.build(self.halting | {ERROR_STATE})


def _write(word: str) -> dict[int, str]:
    return {i: ch for i, ch in enumerate(word) if ch != BLANK}


def _initial_stack_tape(values: list[str]) -> tuple[dict[int, str], int]:
    tape = {0: BOTTOM}
    for i, value in enumerate(values, 1):
        tape[i] = ENCODE[value]
    return tape, len(values)


def _initial_counter_tape(value: int) -> tuple[dict[int, str], int]:
    tape = {0: BOTTOM}
    for i in range(1, value + 1):
        tape[i] = COUNTER_ONE
    return tape, value


def initial_configuration(pattern: str) -> SymbolicConfiguration:
    old = source_initial(pattern)
    if old.state == SOURCE_HALT:
        task = HALT_TASK
    else:
        task = DISPATCH_TASK
    state = YState(old.state, "0", "IDLE", IDENTITY_MAPPING, task)
    tapes: list[dict[int, str]] = [dict(old.tapes[0]), dict(old.tapes[0])]
    heads = [old.heads[A], old.heads[B]]
    for logical in (S, T, U):
        tape_index = SOURCE.head_to_tape[logical]
        tapes.append(dict(old.tapes[tape_index]))
        heads.append(old.heads[logical])

    stack_values: list[list[str]] = [
        ["#"], [],             # zipper left/front
        ["1"], ["1"], ["0"], [], [], [], [], [],  # queue physical identity
    ]
    for values in stack_values:
        tape, head = _initial_stack_tape(values)
        tapes.append(tape); heads.append(head)
    for value in (0, 0):
        tape, head = _initial_counter_tape(value)
        tapes.append(tape); heads.append(head)
    assert len(tapes) == TAPE_COUNT
    return SymbolicConfiguration(state, tapes, heads)


def _read_stack(config: SymbolicConfiguration, physical: int) -> list[str]:
    tape_index = STACK_BASE + physical
    tape, head = config.tapes[tape_index], config.heads[tape_index]
    values: list[str] = []
    pos = head
    while tape.get(pos, BLANK) != BOTTOM:
        token = tape.get(pos, BLANK)
        if token not in DECODE:
            raise AssertionError((physical, pos, token, config.state))
        values.append(DECODE[token])
        pos -= 1
    values.reverse()
    return values


def _read_counter(config: SymbolicConfiguration, tape_index: int) -> int:
    tape, head = config.tapes[tape_index], config.heads[tape_index]
    if tape.get(head, BLANK) == BOTTOM:
        return 0
    count = 0
    pos = head
    while tape.get(pos, BLANK) == COUNTER_ONE:
        count += 1; pos -= 1
    if tape.get(pos, BLANK) != BOTTOM:
        raise AssertionError((tape_index, pos, tape.get(pos, BLANK)))
    return count


def materialize_delta(config: SymbolicConfiguration) -> tuple[str, ...]:
    state = config.state
    assert isinstance(state, YState)
    left = _read_stack(config, LEFT_PHYS)
    front = _read_stack(config, FRONT_PHYS)
    queue_stacks = {
        role: _read_stack(config, QUEUE_PHYS_BASE + state.mapping[ROLE_INDEX[role]])
        for role in ROLES
    }
    queue = StrictStackQueue(
        f1=queue_stacks["f1"], f2=queue_stacks["f2"], rear=queue_stacks["rear"],
        fwork=queue_stacks["fwork"], fp=queue_stacks["fp"], rold=queue_stacks["rold"],
        rp1=queue_stacks["rp1"], rp2=queue_stacks["rp2"],
        phase=RotationPhase[state.phase],
        ok=_read_counter(config, OK_TAPE),
        budget=_read_counter(config, BUDGET_TAPE),
    )
    return tuple(left) + (state.current,) + tuple(reversed(front)) + queue.to_tuple()


@dataclass(frozen=True)
class OrdinaryYResult:
    blocks: tuple[int, ...]
    microsteps: int
    source_steps: int
    states: int
    rows: int


_MACHINE: SymbolicMultitapeMachine | None = None


def machine() -> SymbolicMultitapeMachine:
    global _MACHINE
    if _MACHINE is None:
        _MACHINE = _Generator().build()
    return _MACHINE


def run_algorithm_y_ordinary(pattern: str, max_steps: int = 10_000_000) -> OrdinaryYResult:
    m = machine()
    config = initial_configuration(pattern)
    if config.state not in m.halting_states:
        m.run(config, max_steps=max_steps)
    if config.state == ERROR_STATE:
        raise AssertionError(("ordinary machine entered error", pattern, config))
    word = "".join(materialize_delta(config))
    return OrdinaryYResult(
        delta_blocks_from_word(word), config.steps, config.source_dispatches,
        len(m.states), len(m.rows),
    )


def export_table(path: str | Path = "generated/algorithm_y_ordinary_table.json.gz") -> None:
    """Export the complete sparse table using numeric state IDs.

    The JSON is gzip-compressed because its 198,751 rows are highly repetitive.
    State names are deliberately omitted: a TM transition table is fully defined
    by its numeric states, initial state, halting set, alphabets, and rows.
    """
    import gzip
    m = machine()
    state_ids = {state: i for i, state in enumerate(m.states)}

    def atom_json(atom):
        if atom is None:
            return None
        if isinstance(atom, frozenset):
            return sorted(atom)
        return atom

    normal_initial = YState("Y_TEST_MOVE", "0", "IDLE", IDENTITY_MAPPING, DISPATCH_TASK)
    singleton_initial = YState(SOURCE_HALT, "0", "IDLE", IDENTITY_MAPPING, HALT_TASK)
    data = {
        "format": "sparse ordinary multitape TM v1",
        "semantics": "Each row is one simultaneous one-cell transition; null reads are finite-alphabet wildcards and null writes preserve the scanned symbol.",
        "blank": m.blank,
        "tapes": m.tape_count,
        "states": len(m.states),
        "rows": len(m.rows),
        "maximum_microsteps_per_algorithm_y_step": maximum_microsteps_per_source_step(m),
        "initial_states": {
            "pattern_length_at_least_2": state_ids[normal_initial],
            "pattern_length_1": state_ids[singleton_initial],
        },
        "error_state": state_ids[ERROR_STATE],
        "halting_states": sorted(state_ids[s] for s in m.halting_states),
        "tape_alphabets": m.tape_alphabets,
        "rows_data": [
            [
                state_ids[row.state],
                [atom_json(a) for a in row.reads],
                state_ids[row.action.next_state],
                list(row.action.writes),
                [int(x) for x in row.action.moves],
            ]
            for row in m.rows
        ],
    }
    payload = json.dumps(data, separators=(",", ":")).encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wb", compresslevel=9) as out:
            out.write(payload)
    else:
        path.write_bytes(payload)


def export_summary(path: str | Path = "generated/algorithm_y_ordinary_summary.json") -> None:
    m = machine()
    data = {
        "model": "ordinary one-head-per-tape TM",
        "tapes": m.tape_count,
        "states": len(m.states),
        "sparse_rows": len(m.rows),
        "halting_states": len(m.halting_states),
        "source_schemata": len(SOURCE.schemata),
        "source_concrete_rows": len(SOURCE.delta),
        "maximum_microsteps_per_algorithm_y_step": maximum_microsteps_per_source_step(m),
        "queue_role_permutations": 12,
        "stack_reset": "fresh bottom-marker epoch; two ordinary TM steps",
        "operational_callbacks": False,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def maximum_microsteps_per_source_step(m: SymbolicMultitapeMachine | None = None) -> int:
    """Return an exact graph-theoretic bound for one Algorithm-Y source step.

    A source step begins with a DISPATCH row and ends on the next DISPATCH or
    HALT control.  Error branches encode violated representation invariants and
    are excluded.  The generated microprogram is acyclic between boundaries;
    this routine verifies that fact while finding the longest path.
    """
    m = machine() if m is None else m
    successors: dict[Hashable, set[Hashable]] = {}
    for row in m.rows:
        successors.setdefault(row.state, set()).add(row.action.next_state)
    memo: dict[Hashable, int] = {}
    visiting: set[Hashable] = set()
    neg = -10**9

    def distance(state: Hashable) -> int:
        if state == ERROR_STATE:
            return neg
        if isinstance(state, YState) and state.task in (DISPATCH_TASK, HALT_TASK):
            return 0
        if state in memo:
            return memo[state]
        if state in visiting:
            raise AssertionError(("microprogram cycle", state))
        visiting.add(state)
        values = [distance(nxt) for nxt in successors.get(state, ())]
        visiting.remove(state)
        valid = [value for value in values if value > neg]
        if not valid:
            memo[state] = neg
        else:
            memo[state] = 1 + max(valid)
        return memo[state]

    bound = 0
    for state, nexts in successors.items():
        if isinstance(state, YState) and state.task == DISPATCH_TASK:
            for nxt in nexts:
                value = distance(nxt)
                if value > neg:
                    bound = max(bound, 1 + value)  # include dispatch row
    return bound


if __name__ == "__main__":
    export_table()
    export_summary()
    for sample in ("0", "00", "0100000", "01100110", "01@10"):
        print(sample, run_algorithm_y_ordinary(sample))
