"""Ordinary one-head-per-tape table for a strict append/read zipper.

This is the input-history terminal used by the final palindrome construction.
It reuses the already audited Hood--Melville queue microprogram from
``algorithm_y_ordinary_tm`` and projects away Algorithm Y's five unrelated
source tapes.  The resulting machine has twelve ordinary tapes:

* zipper left and front stacks;
* eight physical queue-role stacks;
* unary ``ok`` and ``budget`` counters.

The symbol under the logical read head, the queue phase, and the finite role
permutation live in finite control.  Four externally selectable entry tasks are
available: append 0, append 1, move left, and move right.  Every table row is
one simultaneous one-cell ordinary-TM transition.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import gzip
import json
from pathlib import Path
from typing import Hashable, Iterable

import algorithm_y_ordinary_tm as y
from flat_tm import Shift
from strict_append_read_zipper import StrictAppendReadZipper
from strict_stack_queue import RotationPhase, StrictStackQueue
from symbolic_tm import (
    SymbolicAction,
    SymbolicConfiguration,
    SymbolicMultitapeMachine,
    SymbolicRow,
    SymbolicTableBuilder,
)

# Project Algorithm Y's storage tapes 5..16 onto terminal tapes 0..11.
SOURCE_PREFIX = y.STACK_BASE
TAPE_COUNT = y.TAPE_COUNT - SOURCE_PREFIX
STACK_COUNT = y.STACK_COUNT
OK_TAPE = y.OK_TAPE - SOURCE_PREFIX
BUDGET_TAPE = y.BUDGET_TAPE - SOURCE_PREFIX

BLANK = y.BLANK
BOTTOM = y.BOTTOM
COUNTER_ONE = y.COUNTER_ONE
STACK_ALPHABET = y.STACK_ALPHABET
COUNTER_ALPHABET = y.COUNTER_ALPHABET
VALUE_SYMBOLS = y.VALUE_SYMBOLS
ENCODE = y.ENCODE
DECODE = y.DECODE
IDENTITY_MAPPING = y.IDENTITY_MAPPING
ROLES = y.ROLES
ROLE_INDEX = y.ROLE_INDEX
QUEUE_PHYS_BASE = y.QUEUE_PHYS_BASE
LEFT_PHYS = y.LEFT_PHYS
FRONT_PHYS = y.FRONT_PHYS

COMMANDS = ("APPEND0", "APPEND1", "LEFT", "RIGHT", "RESET")
READY_TASK = ("ZIP_READY",)
ERROR_STATE = "ZIP_OTM_ERROR"


def command_task(command: str) -> tuple:
    if command == "APPEND0":
        return ("OPS", (("APPEND", "0"),))
    if command == "APPEND1":
        return ("OPS", (("APPEND", "1"),))
    if command == "LEFT":
        return ("OPS", (("LEFT",),))
    if command == "RIGHT":
        return ("OPS", (("RIGHT",),))
    if command == "RESET":
        return ("ZIP_RESET_MOVE",)
    raise ValueError(command)


def as_command_state(core: y.YState, command: str) -> y.YState:
    if core.task != READY_TASK:
        raise ValueError(("not a ready zipper core", core))
    return replace(core, task=command_task(command))


class _TerminalGenerator(y._Generator):
    """Reuse the queue/zipper task expander, with RETURN as a subroutine exit."""

    def __init__(self) -> None:
        super().__init__()
        self.ready: set[y.YState] = set()
        self._seeded_cores: set[tuple] = set()

    @staticmethod
    def _core_key(state: y.YState) -> tuple:
        return (
            state.source,
            state.current,
            state.phase,
            state.mapping,
            state.h0,
            state.h1,
        )

    def _seed_commands(self, ready: y.YState) -> None:
        key = self._core_key(ready)
        if key in self._seeded_cores:
            return
        self._seeded_cores.add(key)
        for command in COMMANDS:
            self.discover(as_command_state(ready, command))

    def generate(self, state: y.YState) -> None:  # noqa: C901
        tag = state.task[0]
        if tag == "ZIP_RESET_MOVE":
            nxt = replace(state, task=("ZIP_RESET_WRITE",))
            reads = [None] * y.TAPE_COUNT
            writes = [None] * y.TAPE_COUNT
            moves = [Shift.STAY] * y.TAPE_COUNT
            for tape in range(SOURCE_PREFIX, y.TAPE_COUNT):
                moves[tape] = Shift.RIGHT
            self.builder.add(state, reads, nxt, writes, moves)
            self.discover(nxt)
            return
        if tag == "ZIP_RESET_WRITE":
            ready = replace(
                state,
                current="#",
                phase="IDLE",
                mapping=IDENTITY_MAPPING,
                task=READY_TASK,
                h0=None,
                h1=None,
            )
            reads = [None] * y.TAPE_COUNT
            writes = [None] * y.TAPE_COUNT
            moves = [Shift.STAY] * y.TAPE_COUNT
            for tape in range(SOURCE_PREFIX, y.TAPE_COUNT):
                reads[tape] = BLANK
                writes[tape] = BOTTOM
            self.builder.add(state, reads, ready, writes, moves)
            self.ready.add(ready)
            self._seed_commands(ready)
            return
        if tag == "RETURN":
            ready = replace(state, task=READY_TASK)
            self.noop(state, ready)
            self.ready.add(ready)
            self._seed_commands(ready)
            return
        if tag == "ZIP_READY":
            self.ready.add(state)
            self._seed_commands(state)
            return
        if tag in {"DISPATCH", "HALT"}:
            raise AssertionError(("terminal zipper reached Algorithm-Y task", state))
        super().generate(state)

    def build_terminal(self) -> SymbolicMultitapeMachine:
        # Empty-history and sentinel-history starts cover every finite core that
        # can subsequently arise; command exits recursively seed all commands
        # for their resulting core.
        for current in VALUE_SYMBOLS:
            ready = y.YState("ZIP", current, "IDLE", IDENTITY_MAPPING, READY_TASK)
            self.discover(ready)
        while self.pending:
            self.generate(self.pending.popleft())
        self.builder.states.add(ERROR_STATE)
        full = self.builder.build(self.ready | {ERROR_STATE})
        return _project_storage_machine(full, self.ready)


def _project_storage_machine(
    full: SymbolicMultitapeMachine,
    ready_states: Iterable[Hashable],
) -> SymbolicMultitapeMachine:
    alphabets = full.tape_alphabets[SOURCE_PREFIX:]
    builder = SymbolicTableBuilder(alphabets, full.blank)
    for row in full.rows:
        builder.add(
            row.state,
            row.reads[SOURCE_PREFIX:],
            row.action.next_state,
            row.action.writes[SOURCE_PREFIX:],
            row.action.moves[SOURCE_PREFIX:],
        )
    return builder.build(set(ready_states) | {ERROR_STATE})


_MACHINE: SymbolicMultitapeMachine | None = None


def machine() -> SymbolicMultitapeMachine:
    global _MACHINE
    if _MACHINE is None:
        _MACHINE = _TerminalGenerator().build_terminal()
    return _MACHINE


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


def configuration_from_zipper(
    zipper: StrictAppendReadZipper[str],
) -> SymbolicConfiguration:
    q = zipper.queue
    state = y.YState(
        "ZIP",
        zipper.current,
        q.phase.name,
        IDENTITY_MAPPING,
        READY_TASK,
    )
    values = [
        list(zipper.left),
        list(zipper.front),
        list(q.f1),
        list(q.f2),
        list(q.rear),
        list(q.fwork),
        list(q.fp),
        list(q.rold),
        list(q.rp1),
        list(q.rp2),
    ]
    tapes: list[dict[int, str]] = []
    heads: list[int] = []
    for stack in values:
        tape, head = _initial_stack_tape(stack)
        tapes.append(tape)
        heads.append(head)
    for counter in (q.ok, q.budget):
        tape, head = _initial_counter_tape(counter)
        tapes.append(tape)
        heads.append(head)
    return SymbolicConfiguration(state, tapes, heads)


def initial_configuration(
    cells: Iterable[str] = ("#",),
    *,
    reader: int = 0,
    blank: str = BLANK,
) -> SymbolicConfiguration:
    data = tuple(cells)
    if not data:
        raise ValueError("history zipper requires at least one represented cell")
    zipper = StrictAppendReadZipper.from_cells(
        data, reader=reader, writer=len(data), blank=blank
    )
    return configuration_from_zipper(zipper)


def start_command(config: SymbolicConfiguration, command: str) -> None:
    state = config.state
    if not isinstance(state, y.YState) or state.task != READY_TASK:
        raise ValueError(("zipper is not ready", state))
    config.state = as_command_state(state, command)


def run_command(
    config: SymbolicConfiguration,
    command: str,
    *,
    max_steps: int = 100_000,
) -> int:
    start_command(config, command)
    return machine().run(config, max_steps=max_steps)



def maximum_microsteps_per_command() -> dict[str, int]:
    """Exact longest non-error path from each command entry to READY.

    The finite command microprogram is acyclic between READY boundaries.
    This routine verifies acyclicity and computes the graph-theoretic maxima;
    it does not sample runtime configurations.
    """
    m = machine()
    ready = set(m.halting_states) - {ERROR_STATE}
    successors: dict[Hashable, set[Hashable]] = {}
    for item in m.rows:
        successors.setdefault(item.state, set()).add(item.action.next_state)
    memo: dict[Hashable, int] = {}
    visiting: set[Hashable] = set()
    neg = -10**9

    def distance(state: Hashable) -> int:
        if state == ERROR_STATE:
            return neg
        if state in ready:
            return 0
        if state in memo:
            return memo[state]
        if state in visiting:
            raise AssertionError(("command microprogram cycle", state))
        visiting.add(state)
        values = [distance(nxt) for nxt in successors.get(state, ())]
        visiting.remove(state)
        valid = [value for value in values if value > neg]
        memo[state] = neg if not valid else 1 + max(valid)
        return memo[state]

    result: dict[str, int] = {}
    for command in COMMANDS:
        values = [distance(as_command_state(core, command)) for core in ready]
        result[command] = max(values)
    return result

def current_symbol(config: SymbolicConfiguration) -> str:
    state = config.state
    if not isinstance(state, y.YState):
        raise ValueError(state)
    return state.current


def _read_stack(config: SymbolicConfiguration, physical: int) -> list[str]:
    tape, head = config.tapes[physical], config.heads[physical]
    out: list[str] = []
    pos = head
    while tape.get(pos, BLANK) != BOTTOM:
        token = tape.get(pos, BLANK)
        if token not in DECODE:
            raise AssertionError((physical, pos, token, config.state))
        out.append(DECODE[token])
        pos -= 1
    out.reverse()
    return out


def _read_counter(config: SymbolicConfiguration, tape_index: int) -> int:
    tape, head = config.tapes[tape_index], config.heads[tape_index]
    if tape.get(head, BLANK) == BOTTOM:
        return 0
    count = 0
    pos = head
    while tape.get(pos, BLANK) == COUNTER_ONE:
        count += 1
        pos -= 1
    if tape.get(pos, BLANK) != BOTTOM:
        raise AssertionError((tape_index, pos, tape.get(pos, BLANK)))
    return count


def materialize(config: SymbolicConfiguration) -> tuple[str, ...]:
    state = config.state
    if not isinstance(state, y.YState):
        raise ValueError(state)
    queue_stacks = {
        role: _read_stack(
            config,
            QUEUE_PHYS_BASE + state.mapping[ROLE_INDEX[role]],
        )
        for role in ROLES
    }
    queue = StrictStackQueue(
        f1=queue_stacks["f1"],
        f2=queue_stacks["f2"],
        rear=queue_stacks["rear"],
        fwork=queue_stacks["fwork"],
        fp=queue_stacks["fp"],
        rold=queue_stacks["rold"],
        rp1=queue_stacks["rp1"],
        rp2=queue_stacks["rp2"],
        phase=RotationPhase[state.phase],
        ok=_read_counter(config, OK_TAPE),
        budget=_read_counter(config, BUDGET_TAPE),
    )
    return (
        tuple(_read_stack(config, LEFT_PHYS))
        + (state.current,)
        + tuple(reversed(_read_stack(config, FRONT_PHYS)))
        + queue.to_tuple()
    )


def export_table(path: str | Path = "generated/history_zipper_ordinary_table.json.gz") -> dict:
    m = machine()
    states = list(m.states)
    ids = {state: i for i, state in enumerate(states)}

    def atom_json(atom):
        if atom is None:
            return None
        if isinstance(atom, frozenset):
            return sorted(atom)
        return atom

    ready = [state for state in states if isinstance(state, y.YState) and state.task == READY_TASK]
    entries = {
        repr((state.current, state.phase, state.mapping, state.h0, state.h1)): {
            command: ids[as_command_state(state, command)] for command in COMMANDS
        }
        for state in ready
    }
    data = {
        "format": "sparse ordinary multitape TM v1",
        "component": "strict append/read history zipper",
        "semantics": "Each row is one simultaneous one-cell transition; null reads wildcard and null writes preserve.",
        "blank": m.blank,
        "tapes": m.tape_count,
        "states": len(states),
        "rows": len(m.rows),
        "error_state": ids[ERROR_STATE],
        "ready_states": sorted(ids[state] for state in ready),
        "entry_states_by_ready_core": entries,
        "tape_alphabets": m.tape_alphabets,
        "rows_data": [
            [
                ids[row.state],
                [atom_json(atom) for atom in row.reads],
                ids[row.action.next_state],
                list(row.action.writes),
                [int(move) for move in row.action.moves],
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
    return {key: value for key, value in data.items() if key not in {"rows_data", "entry_states_by_ready_core"}}


if __name__ == "__main__":
    print(export_table())
