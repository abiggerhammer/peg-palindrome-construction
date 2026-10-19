"""Reusable ordinary checkpoint table with monotone fresh epochs.

The one-shot 63-tape checkpoint table is retained verbatim.  This module adds
one launch/control tape and an explicit producer-paid retirement microprogram.
The one-shot DONE state is RESULT_READY: output axes remain intact there until
the caller consumes them.  A RETIRE request performs all variable cleanup and
ends in clean READY.  From clean READY, a new request enters the one-shot
initial state in exactly one checkpoint transition.

Successive checkpoint words may extend the previous word.  Pattern tapes are
overwritten in place; all candidate axes are explicitly cleared through the old
end marker; and each Fischer--Paterson stack/counter receives a fresh bottom-
marker epoch without traversing or erasing its old contents.

The three source tapes are input terminals.  A surrounding online controller
may append the newly arrived symbols and move the launch marker.  The helper
``extend_source`` performs exactly that terminal update for differential tests;
it is not part of a checkpoint transition.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import gzip
import json
from pathlib import Path
from typing import Hashable

import checkpoint_ordinary_tm as cp
from algorithm_y_ordinary_tm import BOTTOM, ENCODE

CONTROL_TAPE = cp.TAPE_COUNT
TAPE_COUNT = cp.TAPE_COUNT + 1
REQUEST = "R"
RETIRE = "C"
CONTROL_ALPHABET = (cp.BLANK, REQUEST, RETIRE)

AXES = (
    cp.PERIOD_TAPE, cp.FULL_TAPE, cp.PARTIAL_TAPE,
    cp.OUT1_TAPE, cp.OUT2_TAPE, cp.CANDIDATE_TAPE,
)
PATTERNS = cp.PATTERN_TAPES


@dataclass(frozen=True)
class ResetState:
    tag: str
    index: int = 0
    run: str = ""
    local: int = 0
    sub: int = 0


RESULT_READY = cp.DONE
READY = "CHECKPOINT_REUSABLE_READY"
ERROR = cp.ERROR


def tape_alphabets() -> tuple[tuple[str, ...], ...]:
    return cp.tape_alphabets() + (CONTROL_ALPHABET,)


def _alphabet_without(tape: int, symbol: str) -> frozenset[str]:
    return frozenset(set(tape_alphabets()[tape]) - {symbol})


def _lift(item: cp.SparseRow) -> cp.SparseRow:
    # Sparse rows omit every irrelevant tape, so the old 63-tape row already
    # has precisely the right meaning over the added control tape.
    return item


def _next_axis_rewind(index: int, second: bool = False) -> Hashable:
    if index + 1 < len(AXES):
        return ResetState("AXIS_REWIND2" if second else "AXIS_REWIND1", index + 1)
    if second:
        return ResetState("PATTERN_REWIND", 0)
    return ResetState("AXIS_CLEAR_START")


def _next_pattern(index: int) -> Hashable:
    if index + 1 < len(PATTERNS):
        return ResetState("PATTERN_REWIND", index + 1)
    return ResetState("SOURCE_FWD_TO_END", 0)


def _work_items() -> tuple[tuple[str, int], ...]:
    # Local Algorithm-Y tapes 2..16.  Pattern tapes 0,1 are reset separately.
    return tuple((run, local) for run in cp.RUN_NAMES for local in range(2, 17))


WORK_ITEMS = _work_items()


def _next_work(index: int) -> Hashable:
    if index + 1 < len(WORK_ITEMS):
        run, local = WORK_ITEMS[index + 1]
        return ResetState("WORK_RESET", index + 1, run, local, 0)
    return READY


def _initial_stack_value(local: int) -> str | None:
    # Algorithm-Y ordinary local tapes 5..14 are physical stacks.
    return {
        5: ENCODE["#"],  # zipper left
        7: ENCODE["1"],  # queue f1
        8: ENCODE["1"],  # queue f2
        9: ENCODE["0"],  # queue rear
    }.get(local)


def reset_rows(state: ResetState) -> tuple[cp.SparseRow, ...]:  # noqa: C901
    tag = state.tag

    if tag in {"AXIS_REWIND1", "AXIS_REWIND2"}:
        tape = AXES[state.index]
        nxt = _next_axis_rewind(state.index, second=(tag == "AXIS_REWIND2"))
        return (
            cp.row(state, nxt, reads={tape: cp.MARK}),
            cp.row(state, state, reads={tape: _alphabet_without(tape, cp.MARK)}, moves={tape: -1}),
        )

    if tag == "AXIS_CLEAR_START":
        return (cp.row(state, ResetState("AXIS_CLEAR"), moves={t: 1 for t in AXES}),)

    if tag == "AXIS_CLEAR":
        clear = {t: cp.BLANK for t in AXES}
        nonend = frozenset((cp.BLANK, cp.VALID))
        return (
            cp.row(
                state, state, reads={cp.PARTIAL_TAPE: nonend},
                writes=clear, moves={t: 1 for t in AXES},
            ),
            cp.row(
                state, ResetState("AXIS_REWIND2", 0),
                reads={cp.PARTIAL_TAPE: cp.AXIS_END}, writes=clear,
            ),
        )

    if tag == "PATTERN_REWIND":
        tape = PATTERNS[state.index]
        return (
            cp.row(state, ResetState("PATTERN_CLEAR_START", state.index), reads={tape: cp.SENTINEL}),
            cp.row(state, state, reads={tape: _alphabet_without(tape, cp.SENTINEL)}, moves={tape: -1}),
        )

    if tag == "PATTERN_CLEAR_START":
        tape = PATTERNS[state.index]
        return (cp.row(state, ResetState("PATTERN_CLEAR", state.index), moves={tape: 1}),)

    if tag == "PATTERN_CLEAR":
        tape = PATTERNS[state.index]
        # The prepared pattern epoch is contiguous and ends in END.  Erase it
        # cell by cell, then return to the retained sentinel.
        nonend = frozenset(set(tape_alphabets()[tape]) - {cp.END, cp.SENTINEL, cp.BLANK})
        return (
            cp.row(state, state, reads={tape: nonend}, writes={tape: cp.BLANK}, moves={tape: 1}),
            cp.row(state, ResetState("PATTERN_REWIND_FINAL", state.index),
                   reads={tape: cp.END}, writes={tape: cp.BLANK}),
        )

    if tag == "PATTERN_REWIND_FINAL":
        tape = PATTERNS[state.index]
        return (
            cp.row(state, ResetState("PATTERN_STEP", state.index), reads={tape: cp.SENTINEL}),
            cp.row(state, state, reads={tape: _alphabet_without(tape, cp.SENTINEL)}, moves={tape: -1}),
        )

    if tag == "PATTERN_STEP":
        tape = PATTERNS[state.index]
        return (cp.row(state, _next_pattern(state.index), moves={tape: 1}),)

    if tag == "SOURCE_FWD_TO_END":
        tape = (cp.SRC_FWD, cp.SRC_FWD2)[state.index]
        if state.index == 0:
            nxt: Hashable = ResetState("SOURCE_FWD_TO_END", 1)
        else:
            nxt = ResetState("SOURCE_REV_TO_SENTINEL")
        return (
            cp.row(state, nxt, reads={tape: cp.END}),
            cp.row(state, state, reads={tape: _alphabet_without(tape, cp.END)}, moves={tape: 1}),
        )

    if tag == "SOURCE_REV_TO_SENTINEL":
        tape = cp.SRC_REV
        run, local = WORK_ITEMS[0]
        return (
            cp.row(state, ResetState("WORK_RESET", 0, run, local, 0),
                   reads={tape: cp.SENTINEL}),
            cp.row(state, state, reads={tape: _alphabet_without(tape, cp.SENTINEL)}, moves={tape: -1}),
        )

    if tag == "WORK_RESET":
        tape = cp.y_global_tape(state.run, state.local)
        local = state.local

        # S,T,U: find the first blank to the right of the old contiguous epoch,
        # write a fresh source marker, and leave the head one cell to its right.
        if 2 <= local <= 4:
            if state.sub == 0:
                return (
                    cp.row(state, ResetState(tag, state.index, state.run, local, 1),
                           reads={tape: cp.BLANK}, writes={tape: cp.MARK}),
                    cp.row(state, state, reads={tape: _alphabet_without(tape, cp.BLANK)}, moves={tape: 1}),
                )
            return (cp.row(state, _next_work(state.index), moves={tape: 1}),)

        # Physical stacks and unary counters end with their head at the current
        # top.  One right move reaches virgin blank; a new bottom marker starts
        # an epoch.  Four stacks then receive their fixed initial top value.
        if 5 <= local <= 16:
            initial = _initial_stack_value(local)
            if state.sub == 0:
                return (cp.row(
                    state, ResetState(tag, state.index, state.run, local, 1), moves={tape: 1}
                ),)
            if state.sub == 1:
                nxt = (
                    ResetState(tag, state.index, state.run, local, 2)
                    if initial is not None else _next_work(state.index)
                )
                return (cp.row(state, nxt, reads={tape: cp.BLANK}, writes={tape: BOTTOM}),)
            if state.sub == 2:
                return (cp.row(
                    state, ResetState(tag, state.index, state.run, local, 3), moves={tape: 1}
                ),)
            if state.sub == 3:
                assert initial is not None
                return (cp.row(
                    state, _next_work(state.index), reads={tape: cp.BLANK}, writes={tape: initial}
                ),)
        raise AssertionError(state)

    raise AssertionError(state)


def outgoing_rows(state: Hashable) -> tuple[cp.SparseRow, ...]:
    if state == ERROR:
        return ()
    if state == RESULT_READY:
        # The result axes remain intact until the caller has consumed them.
        # RETIRE charges all cleanup to the completed request and ends in
        # READY, where the next request can start in one transition.
        return (cp.row(
            state, ResetState("AXIS_REWIND1", 0),
            reads={CONTROL_TAPE: RETIRE}, writes={CONTROL_TAPE: cp.BLANK},
        ),)
    if state == READY:
        return (cp.row(
            state, cp.INITIAL,
            reads={CONTROL_TAPE: REQUEST}, writes={CONTROL_TAPE: cp.BLANK},
        ),)
    if isinstance(state, ResetState):
        return reset_rows(state)
    return tuple(_lift(item) for item in cp.outgoing_rows(state))


@dataclass
class ReusableCheckpointConfiguration:
    state: Hashable
    tapes: list[dict[int, str]]
    heads: list[int]
    word: str
    steps: int = 0

    def scanned(self) -> tuple[str, ...]:
        return tuple(self.tapes[i].get(self.heads[i], cp.BLANK) for i in range(TAPE_COUNT))


def initial_configuration(word: str) -> ReusableCheckpointConfiguration:
    old = cp.initial_configuration(word)
    tapes = [dict(t) for t in old.tapes] + [{}]
    heads = list(old.heads) + [0]
    return ReusableCheckpointConfiguration(old.state, tapes, heads, word)


def step(config: ReusableCheckpointConfiguration) -> None:
    if config.state == ERROR:
        raise RuntimeError("cannot step error state")
    scanned = config.scanned()
    matches = [r for r in outgoing_rows(config.state) if r.matches(scanned)]
    if not matches:
        raise RuntimeError(("missing reusable row", config.state, scanned))
    first = matches[0]
    if any(other.action != first.action for other in matches[1:]):
        raise RuntimeError(("conflicting reusable rows", config.state, scanned, matches))
    for tape, symbol in first.action.writes:
        pos = config.heads[tape]
        if symbol == cp.BLANK:
            config.tapes[tape].pop(pos, None)
        else:
            config.tapes[tape][pos] = symbol
    for tape, move in first.action.moves:
        config.heads[tape] += move
    config.state = first.action.next_state
    config.steps += 1


def run_to_result(config: ReusableCheckpointConfiguration, max_steps: int = 100_000_000) -> int:
    start = config.steps
    while config.state != RESULT_READY:
        if config.steps - start >= max_steps:
            raise TimeoutError((config.state, config.steps, config.scanned()))
        step(config)
    return config.steps - start


def run_to_ready(config: ReusableCheckpointConfiguration, max_steps: int = 100_000_000) -> int:
    """Finish an already-requested retirement and reach clean READY."""
    start = config.steps
    while config.state != READY:
        if config.steps - start >= max_steps:
            raise TimeoutError((config.state, config.steps, config.scanned()))
        step(config)
    return config.steps - start


def result(config: ReusableCheckpointConfiguration) -> cp.OrdinaryCheckpointResult:
    if config.state != RESULT_READY:
        raise ValueError("checkpoint result is not available")
    gaps = cp.marker_positions(config, cp.OUT1_TAPE) + cp.marker_positions(config, cp.OUT2_TAPE)
    candidates = cp.marker_positions(config, cp.CANDIDATE_TAPE)
    return cp.OrdinaryCheckpointResult(
        tuple(sorted(gaps)), candidates[0] if candidates else None, config.steps
    )


def extend_source(config: ReusableCheckpointConfiguration, new_word: str) -> None:
    """Update the three source terminals to a monotone extension for tests."""
    if not new_word.startswith(config.word) or len(new_word) <= len(config.word):
        raise ValueError((config.word, new_word))
    old_end = len(config.word) + 1
    suffix = new_word[len(config.word):]
    for tape_index in (cp.SRC_FWD, cp.SRC_REV, cp.SRC_FWD2):
        tape = config.tapes[tape_index]
        if tape.get(old_end) != cp.END:
            raise AssertionError((tape_index, old_end, tape.get(old_end)))
        tape.pop(old_end)
        for offset, symbol in enumerate(suffix):
            tape[old_end + offset] = symbol
        tape[old_end + len(suffix)] = cp.END
    # Terminal-side source preparation installs the one-shot entry heads.
    # This helper is explicitly outside the checkpoint transition relation;
    # retained controllers perform the same positioning one cell at a time.
    config.heads[cp.SRC_FWD] = 1
    config.heads[cp.SRC_FWD2] = 1
    config.heads[cp.SRC_REV] = len(new_word)
    config.word = new_word


def request_retire(config: ReusableCheckpointConfiguration) -> None:
    """Consume the current result and enter producer-paid cleanup."""
    if config.state != RESULT_READY:
        raise ValueError("checkpoint result is not available")
    config.tapes[CONTROL_TAPE][config.heads[CONTROL_TAPE]] = RETIRE
    step(config)


def retire_result(config: ReusableCheckpointConfiguration, max_steps: int = 100_000_000) -> int:
    start = config.steps
    request_retire(config)
    run_to_ready(config, max_steps=max_steps)
    return config.steps - start


def request_extended(config: ReusableCheckpointConfiguration, new_word: str) -> None:
    """Install an extended source epoch and start from clean READY."""
    if config.state != READY:
        raise ValueError("checkpoint is not clean-ready")
    extend_source(config, new_word)
    config.tapes[CONTROL_TAPE][config.heads[CONTROL_TAPE]] = REQUEST
    step(config)  # consume request and enter the one-shot initial state


def launch_extended(config: ReusableCheckpointConfiguration, new_word: str) -> int:
    start = config.steps
    request_extended(config, new_word)
    run_to_result(config)
    return config.steps - start


def enumerate_reachable() -> tuple[list[Hashable], int]:
    states: list[Hashable] = []
    seen: set[Hashable] = {cp.INITIAL}
    queue = deque([cp.INITIAL])
    rows = 0
    while queue:
        state = queue.popleft()
        states.append(state)
        outgoing = outgoing_rows(state)
        rows += len(outgoing)
        for item in outgoing:
            nxt = item.action.next_state
            if nxt not in seen:
                seen.add(nxt); queue.append(nxt)
    return states, rows


def _atom_json(atom: cp.ReadAtom):
    return sorted(atom) if isinstance(atom, frozenset) else atom


def export_table(path: str | Path = "generated/checkpoint_reusable_table.json.gz") -> dict:
    states, row_count = enumerate_reachable()
    ids = {state: i for i, state in enumerate(states)}
    metadata = {
        "format": "sparse-map reusable ordinary multitape TM v1",
        "semantics": "one simultaneous one-cell transition; omitted reads wildcard, writes preserve, moves stay",
        "blank": cp.BLANK,
        "c": 16,
        "tapes": TAPE_COUNT,
        "states": len(states),
        "rows": row_count,
        "initial_state": ids[cp.INITIAL],
        "ready_state": ids[READY],
        "ready_states": [ids[RESULT_READY], ids[READY]],
        "result_ready_state": ids[RESULT_READY],
        "clean_ready_state": ids[READY],
        "error_state": ids[ERROR],
        "control_tape": CONTROL_TAPE,
        "launch_symbol": REQUEST,
        "tape_alphabets": tape_alphabets(),
    }
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wb") as out:
        out.write((json.dumps(metadata, separators=(",", ":"))[:-1] + ',"rows_data":[').encode())
        first = True
        for state in states:
            for item in outgoing_rows(state):
                payload = [
                    ids[item.state], [[t, _atom_json(a)] for t, a in item.reads],
                    ids[item.action.next_state], [[t, s] for t, s in item.action.writes],
                    [[t, m] for t, m in item.action.moves],
                ]
                if not first: out.write(b",")
                first = False
                out.write(json.dumps(payload, separators=(",", ":")).encode())
        out.write(b"]}")
    return metadata


if __name__ == "__main__":
    cfg = initial_configuration("0")
    run_to_result(cfg)
    print("0", result(cfg))
    retire_result(cfg)
    for word in ("00", "0000", "000000000000000", "0000000000000000"):
        launch_extended(cfg, word)
        print(word, result(cfg))
        retire_result(cfg)
