"""Ordinary one-head-per-tape checkpoint machine for SG Lemmas 3.2/3.3.

This table composes the six-copy pattern-preparation pass with three independent
copies of the already lowered Fischer--Paterson Algorithm-Y machine.  It marks
period candidates, intersects them with palindromic-prefix candidates, records
palindromic-suffix candidates, merges the first two distinct gaps, and marks the
special Lemma-3.3 candidate for a fixed integer ``c`` (16 by default).

The exported table uses sparse map rows.  Missing read positions are finite-
alphabet wildcards, missing writes preserve the scanned symbol, and missing
moves mean STAY.  Every row is still one ordinary simultaneous one-cell TM
transition.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import gzip
import json
from pathlib import Path
from typing import Hashable, Iterable, Iterator, Mapping

from algorithm_y_ordinary_tm import (
    BLANK,
    DISPATCH_TASK,
    ERROR_STATE as Y_ERROR,
    HALT_TASK,
    IDENTITY_MAPPING,
    YState,
    initial_configuration as y_initial_configuration,
    machine as y_machine,
)
from flat_tm import Shift
from fp_algorithm_y_multihead import AFTER_BACK, BACK_START, HALT as SOURCE_HALT

# ---------------------------------------------------------------------------
# Physical tape layout.

SRC_FWD, SRC_REV, SRC_FWD2 = range(3)
SRC_COUNT = 3
RUN_NAMES = ("PLAIN", "PREFIX", "SUFFIX")
RUN_INDEX = {name: i for i, name in enumerate(RUN_NAMES)}
RUN_WIDTH = 18  # pattern A, pattern B, helper-A, then Algorithm-Y local tapes 2..16


def run_base(run: str) -> int:
    return SRC_COUNT + RUN_INDEX[run] * RUN_WIDTH


def pat_a(run: str) -> int:
    return run_base(run)


def pat_b(run: str) -> int:
    return run_base(run) + 1


def helper_a(run: str) -> int:
    return run_base(run) + 2


def y_global_tape(run: str, local: int) -> int:
    if local == 0:
        return pat_a(run)
    if local == 1:
        return pat_b(run)
    if not 2 <= local < 17:
        raise ValueError(local)
    return run_base(run) + 3 + (local - 2)


AFTER_RUNS = SRC_COUNT + len(RUN_NAMES) * RUN_WIDTH
PERIOD_TAPE = AFTER_RUNS
FULL_TAPE = PERIOD_TAPE + 1
PARTIAL_TAPE = FULL_TAPE + 1
OUT1_TAPE = PARTIAL_TAPE + 1
OUT2_TAPE = OUT1_TAPE + 1
CANDIDATE_TAPE = OUT2_TAPE + 1
TAPE_COUNT = CANDIDATE_TAPE + 1

SENTINEL = "$"
END = "!"
SEP = "@"
MARK = "#"
PERIOD = "P"
VALID = "V"
AXIS_END = "E"
GAP = "G"

SOURCE_ALPHABET = (BLANK, SENTINEL, END, "0", "1")
PERIOD_ALPHABET = (BLANK, MARK, PERIOD)
FULL_ALPHABET = (BLANK, MARK, VALID)
PARTIAL_ALPHABET = (BLANK, MARK, VALID, AXIS_END)
OUTPUT_ALPHABET = (BLANK, MARK, GAP)


def tape_alphabets() -> tuple[tuple[str, ...], ...]:
    ym = y_machine()
    result: list[tuple[str, ...]] = [SOURCE_ALPHABET] * SRC_COUNT
    for _run in RUN_NAMES:
        result.extend((ym.tape_alphabets[0], ym.tape_alphabets[1], ym.tape_alphabets[0]))
        result.extend(ym.tape_alphabets[2:])
    result.extend(
        (PERIOD_ALPHABET, FULL_ALPHABET, PARTIAL_ALPHABET,
         OUTPUT_ALPHABET, OUTPUT_ALPHABET, OUTPUT_ALPHABET)
    )
    assert len(result) == TAPE_COUNT
    return tuple(result)


# ---------------------------------------------------------------------------
# Sparse rows and states.

ReadAtom = str | frozenset[str]


@dataclass(frozen=True)
class SparseAction:
    next_state: Hashable
    writes: tuple[tuple[int, str], ...] = ()
    moves: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class SparseRow:
    state: Hashable
    reads: tuple[tuple[int, ReadAtom], ...]
    action: SparseAction

    def matches(self, scanned: tuple[str, ...]) -> bool:
        for tape, atom in self.reads:
            symbol = scanned[tape]
            if isinstance(atom, frozenset):
                if symbol not in atom:
                    return False
            elif symbol != atom:
                return False
        return True


@dataclass(frozen=True)
class WrappedY:
    phase: str  # BUILD_PLAIN/PREFIX/SUFFIX or WALK_PLAIN/PREFIX/SUFFIX
    y: YState
    parity: int = 0


@dataclass(frozen=True)
class Control:
    tag: str
    run: str = ""
    y: YState | None = None
    parity: int = 0
    index: int = 0
    count: int = 0


DONE = "CHECKPOINT_DONE"
ERROR = "CHECKPOINT_ERROR"
INITIAL = Control("PREP_FORWARD")

NORMAL_Y_INITIAL = YState("Y_TEST_MOVE", "0", "IDLE", IDENTITY_MAPPING, DISPATCH_TASK)
SINGLETON_Y_HALT = YState(SOURCE_HALT, "0", "IDLE", IDENTITY_MAPPING, HALT_TASK)

NONEND_SOURCE = frozenset((SENTINEL, "0", "1"))
PATTERN_CHARS = frozenset(("0", "1", SEP))
PLAIN_CHARS = frozenset(("0", "1"))
NONPERIOD = frozenset((BLANK, MARK))
NONVALID = frozenset((BLANK, MARK))


def _sorted_items(values: Mapping[int, object]) -> tuple[tuple[int, object], ...]:
    return tuple(sorted(values.items()))


def row(
    state: Hashable,
    next_state: Hashable,
    *,
    reads: Mapping[int, ReadAtom] | None = None,
    writes: Mapping[int, str] | None = None,
    moves: Mapping[int, int | Shift] | None = None,
) -> SparseRow:
    move_items = tuple(
        (tape, int(move)) for tape, move in sorted((moves or {}).items()) if int(move) != 0
    )
    return SparseRow(
        state,
        _sorted_items(reads or {}),
        SparseAction(next_state, _sorted_items(writes or {}), move_items),
    )


def _force_back(meta: YState) -> YState:
    return replace(meta, source=BACK_START, task=DISPATCH_TASK)


def _is_walk_boundary(state: Hashable) -> bool:
    return isinstance(state, YState) and state.source == AFTER_BACK and state.task == DISPATCH_TASK


def _globalize_y_row(run: str, source_row, helper_move: bool) -> tuple[dict, dict, dict]:
    reads: dict[int, ReadAtom] = {}
    writes: dict[int, str] = {}
    moves: dict[int, int] = {}
    for local, atom in enumerate(source_row.reads):
        if atom is not None:
            reads[y_global_tape(run, local)] = atom
    for local, value in enumerate(source_row.action.writes):
        if value is not None:
            writes[y_global_tape(run, local)] = value
    for local, move in enumerate(source_row.action.moves):
        if int(move):
            moves[y_global_tape(run, local)] = int(move)
    if helper_move and int(source_row.action.moves[0]):
        moves[helper_a(run)] = int(source_row.action.moves[0])
    return reads, writes, moves


# ---------------------------------------------------------------------------
# Controller rows.

PATTERN_TAPES = tuple(
    tape
    for run in RUN_NAMES
    for tape in (pat_a(run), pat_b(run), helper_a(run))
)
B_TAPES = tuple(pat_b(run) for run in RUN_NAMES)
REWIND_TAPES = PATTERN_TAPES + (SRC_FWD, SRC_FWD2)


def _next_rewind(index: int) -> Hashable:
    if index + 1 < len(REWIND_TAPES):
        return Control("REWIND", index=index + 1)
    return Control("SET_B")


def controller_rows(state: Control) -> tuple[SparseRow, ...]:  # noqa: C901
    tag = state.tag
    rows: list[SparseRow] = []

    if tag == "PREP_FORWARD":
        targets = tuple(
            tape for run in ("PLAIN", "PREFIX")
            for tape in (pat_a(run), pat_b(run), helper_a(run))
        )
        for symbol in ("0", "1"):
            reads = {SRC_FWD: symbol, **{t: BLANK for t in targets}}
            writes = {t: symbol for t in targets}
            moves = {SRC_FWD: 1, PARTIAL_TAPE: 1, **{t: 1 for t in targets}}
            rows.append(row(state, state, reads=reads, writes=writes, moves=moves))
        reads = {SRC_FWD: END}
        writes = {
            **{t: END for t in (pat_a("PLAIN"), pat_b("PLAIN"), helper_a("PLAIN"))},
            **{t: SEP for t in (pat_a("PREFIX"), pat_b("PREFIX"), helper_a("PREFIX"))},
        }
        moves = {t: 1 for t in (pat_a("PREFIX"), pat_b("PREFIX"), helper_a("PREFIX"))}
        rows.append(row(state, Control("PREP_REVERSE"), reads=reads, writes=writes, moves=moves))
        return tuple(rows)

    if tag == "PREP_REVERSE":
        prefix = (pat_a("PREFIX"), pat_b("PREFIX"), helper_a("PREFIX"))
        suffix = (pat_a("SUFFIX"), pat_b("SUFFIX"), helper_a("SUFFIX"))
        for symbol in ("0", "1"):
            reads = {SRC_REV: symbol, **{t: BLANK for t in prefix + suffix}}
            writes = {t: symbol for t in prefix + suffix}
            moves = {SRC_REV: -1, **{t: 1 for t in prefix + suffix}}
            rows.append(row(state, state, reads=reads, writes=writes, moves=moves))
        writes = {**{t: END for t in prefix}, **{t: SEP for t in suffix}}
        moves = {t: 1 for t in suffix}
        rows.append(row(state, Control("PREP_SUFFIX"), reads={SRC_REV: SENTINEL}, writes=writes, moves=moves))
        return tuple(rows)

    if tag == "PREP_SUFFIX":
        suffix = (pat_a("SUFFIX"), pat_b("SUFFIX"), helper_a("SUFFIX"))
        for symbol in ("0", "1"):
            reads = {SRC_FWD2: symbol, **{t: BLANK for t in suffix}}
            rows.append(row(
                state, state, reads=reads, writes={t: symbol for t in suffix},
                moves={SRC_FWD2: 1, **{t: 1 for t in suffix}},
            ))
        rows.append(row(
            state, Control("PREP_AXIS_END"), reads={SRC_FWD2: END},
            writes={t: END for t in suffix}, moves={PARTIAL_TAPE: 1},
        ))
        return tuple(rows)

    if tag == "PREP_AXIS_END":
        rows.append(row(
            state, Control("REWIND", index=0), reads={PARTIAL_TAPE: BLANK},
            writes={PARTIAL_TAPE: AXIS_END}, moves={PARTIAL_TAPE: -1},
        ))
        return tuple(rows)

    if tag == "REWIND":
        tape = REWIND_TAPES[state.index]
        rows.append(row(state, _next_rewind(state.index), reads={tape: SENTINEL}))
        alphabet = set(tape_alphabets()[tape]) - {SENTINEL}
        rows.append(row(state, state, reads={tape: frozenset(alphabet)}, moves={tape: -1}))
        return tuple(rows)

    if tag == "SET_B":
        rows.append(row(state, Control("PLAIN_SINGLETON_MOVE"), moves={t: 1 for t in B_TAPES}))
        return tuple(rows)

    if tag == "PLAIN_SINGLETON_MOVE":
        return (row(state, Control("PLAIN_SINGLETON_PEEK"), moves={pat_b("PLAIN"): 1}),)

    if tag == "PLAIN_SINGLETON_PEEK":
        tape = pat_b("PLAIN")
        rows.append(row(state, Control("AFTER_BUILD", run="PLAIN", y=SINGLETON_Y_HALT),
                        reads={tape: END}, moves={tape: -1}))
        rows.append(row(state, WrappedY("BUILD_PLAIN", NORMAL_Y_INITIAL),
                        reads={tape: PLAIN_CHARS}, moves={tape: -1}))
        return tuple(rows)

    if tag == "AFTER_BUILD":
        assert state.y is not None
        if state.run == "PLAIN":
            return (row(state, Control("INIT_PLAIN_MOVE", run="PLAIN", y=state.y, parity=0)),)
        if state.run == "PREFIX":
            return (row(state, Control("REWIND_PERIOD", run="PREFIX", y=state.y)),)
        if state.run == "SUFFIX":
            return (row(state, Control("INIT_SUFFIX", run="SUFFIX", y=state.y, parity=0)),)
        raise AssertionError(state)

    if tag == "INIT_PLAIN_MOVE":
        return (row(state, Control("INIT_PLAIN_INSPECT", run=state.run, y=state.y,
                                   parity=state.parity), moves={helper_a("PLAIN"): 1}),)

    if tag == "INIT_PLAIN_INSPECT":
        helper = helper_a("PLAIN")
        rows.append(row(state, Control("MARK_PLAIN", run="PLAIN", y=state.y,
                                       parity=state.parity),
                        reads={helper: END}, moves={helper: -1}))
        moves = {PERIOD_TAPE: 1} if state.parity == 1 else {}
        rows.append(row(state, Control("INIT_PLAIN_MOVE", run="PLAIN", y=state.y,
                                       parity=state.parity ^ 1),
                        reads={helper: PLAIN_CHARS}, moves=moves))
        return tuple(rows)

    if tag == "MARK_PLAIN":
        assert state.y is not None
        a = pat_a("PLAIN")
        writes = {PERIOD_TAPE: PERIOD} if state.parity == 0 else {}
        rows.append(row(state, WrappedY("BUILD_PREFIX", NORMAL_Y_INITIAL),
                        reads={a: SENTINEL}, writes=writes))
        rows.append(row(state, WrappedY("WALK_PLAIN", _force_back(state.y), state.parity),
                        reads={a: PLAIN_CHARS}, writes=writes))
        return tuple(rows)

    if tag == "REWIND_PERIOD":
        rows.append(row(state, Control("INIT_PREFIX", run="PREFIX", y=state.y, parity=0),
                        reads={PERIOD_TAPE: MARK}))
        rows.append(row(state, state, reads={PERIOD_TAPE: frozenset((BLANK, PERIOD))},
                        moves={PERIOD_TAPE: -1}))
        return tuple(rows)

    if tag == "INIT_PREFIX":
        helper = helper_a("PREFIX")
        rows.append(row(state, Control("CHECK_PREFIX", run="PREFIX", y=state.y,
                                       parity=state.parity), reads={helper: SENTINEL}))
        moves = {helper: -1}
        if state.parity == 1:
            moves.update({PERIOD_TAPE: 1, FULL_TAPE: 1})
        rows.append(row(state, Control("INIT_PREFIX", run="PREFIX", y=state.y,
                                       parity=state.parity ^ 1),
                        reads={helper: PATTERN_CHARS}, moves=moves))
        return tuple(rows)

    if tag == "CHECK_PREFIX":
        assert state.y is not None
        a = pat_a("PREFIX")
        for a_atom, terminal in ((SENTINEL, True), (PATTERN_CHARS, False)):
            for p_atom, period_ok in ((PERIOD, True), (NONPERIOD, False)):
                writes = {FULL_TAPE: VALID} if state.parity == 0 and period_ok else {}
                if terminal:
                    nxt: Hashable = WrappedY("BUILD_SUFFIX", NORMAL_Y_INITIAL)
                else:
                    nxt = WrappedY("WALK_PREFIX", _force_back(state.y), state.parity)
                rows.append(row(state, nxt, reads={a: a_atom, PERIOD_TAPE: p_atom}, writes=writes))
        return tuple(rows)

    if tag == "INIT_SUFFIX":
        helper = helper_a("SUFFIX")
        rows.append(row(state, Control("CHECK_SUFFIX", run="SUFFIX", y=state.y,
                                       parity=state.parity), reads={helper: SENTINEL}))
        moves = {helper: -1}
        if state.parity == 1:
            moves[PARTIAL_TAPE] = -1
        rows.append(row(state, Control("INIT_SUFFIX", run="SUFFIX", y=state.y,
                                       parity=state.parity ^ 1),
                        reads={helper: PATTERN_CHARS}, moves=moves))
        return tuple(rows)

    if tag == "CHECK_SUFFIX":
        assert state.y is not None
        a = pat_a("SUFFIX")
        # At the sentinel the empty suffix is also the gap n, so it is marked
        # independently of parity.  For nonterminal borders, only even borders
        # contribute.
        rows.append(row(state, Control("REWIND_FULL"), reads={a: SENTINEL},
                        writes={PARTIAL_TAPE: VALID}))
        writes = {PARTIAL_TAPE: VALID} if state.parity == 0 else {}
        rows.append(row(state, WrappedY("WALK_SUFFIX", _force_back(state.y), state.parity),
                        reads={a: PATTERN_CHARS}, writes=writes))
        return tuple(rows)

    if tag == "REWIND_FULL":
        rows.append(row(state, Control("REWIND_PARTIAL"), reads={FULL_TAPE: MARK}))
        rows.append(row(state, state, reads={FULL_TAPE: frozenset((BLANK, VALID))},
                        moves={FULL_TAPE: -1}))
        return tuple(rows)

    if tag == "REWIND_PARTIAL":
        rows.append(row(state, Control("SCAN_ADVANCE", count=0), reads={PARTIAL_TAPE: MARK}))
        rows.append(row(state, state, reads={PARTIAL_TAPE: frozenset((BLANK, VALID))},
                        moves={PARTIAL_TAPE: -1}))
        return tuple(rows)

    if tag == "SCAN_ADVANCE":
        moves = {t: 1 for t in (FULL_TAPE, PARTIAL_TAPE, OUT1_TAPE, OUT2_TAPE, CANDIDATE_TAPE)}
        return (row(state, Control("RATIO", index=0, count=state.count), moves=moves),)

    if tag == "RATIO":
        k = state.index
        if not 0 <= k < 16:
            raise AssertionError(state)
        if k < 15:
            for left_atom, left_move in ((END, 0), (NONEND_SOURCE, 1)):
                for right_atom, right_move in ((END, 0), (NONEND_SOURCE, 1)):
                    moves = {}
                    if left_move:
                        moves[SRC_FWD] = 1
                    if right_move:
                        moves[SRC_FWD2] = 1
                    rows.append(row(
                        state, Control("RATIO", index=k + 1, count=state.count),
                        reads={SRC_FWD: left_atom, SRC_FWD2: right_atom}, moves=moves,
                    ))
        else:
            rows.append(row(state, Control("MERGE", count=state.count),
                            reads={SRC_FWD2: END}))
            rows.append(row(state, Control("MERGE", count=state.count),
                            reads={SRC_FWD2: NONEND_SOURCE}, moves={SRC_FWD2: 1}))
        return tuple(rows)

    if tag == "MERGE":
        # Passing the explicit axis end means there is no second distinct gap.
        rows.append(row(state, DONE, reads={PARTIAL_TAPE: AXIS_END}))
        for full_atom, full_ok in ((VALID, True), (NONVALID, False)):
            for part_atom, part_ok in ((VALID, True), (NONVALID, False)):
                found = full_ok or part_ok
                reads = {FULL_TAPE: full_atom, PARTIAL_TAPE: part_atom}
                if not found:
                    rows.append(row(state, Control("SCAN_ADVANCE", count=state.count), reads=reads))
                elif state.count == 0:
                    for base_atom, base_ok in ((END, False), (NONEND_SOURCE, True)):
                        for target_atom, target_over in ((END, True), (NONEND_SOURCE, False)):
                            rw = dict(reads)
                            rw.update({SRC_FWD: base_atom, SRC_FWD2: target_atom})
                            writes = {OUT1_TAPE: GAP}
                            if base_ok and target_over:
                                writes[CANDIDATE_TAPE] = GAP
                            rows.append(row(
                                state, Control("SCAN_ADVANCE", count=1),
                                reads=rw, writes=writes,
                            ))
                else:
                    rows.append(row(state, DONE, reads=reads, writes={OUT2_TAPE: GAP}))
        return tuple(rows)

    raise AssertionError(("unknown control state", state))


# ---------------------------------------------------------------------------
# Wrapped Algorithm-Y rows.


def wrapped_y_rows(state: WrappedY) -> tuple[SparseRow, ...]:
    ym = y_machine()
    run = state.phase.split("_", 1)[1]
    build = state.phase.startswith("BUILD_")
    walk = state.phase.startswith("WALK_")
    if not (build or walk):
        raise AssertionError(state)

    result: list[SparseRow] = []
    for source_row in ym._by_state.get(state.y, ()):  # audited immutable table
        reads, writes, moves = _globalize_y_row(run, source_row, helper_move=build)
        next_y = source_row.action.next_state
        next_parity = state.parity

        if walk and int(source_row.action.moves[0]) == -1:
            if run == "PLAIN" and state.parity == 1:
                moves[PERIOD_TAPE] = 1
            elif run == "PREFIX" and state.parity == 0:
                moves[PERIOD_TAPE] = -1
                moves[FULL_TAPE] = -1
            elif run == "SUFFIX" and state.parity == 0:
                moves[PARTIAL_TAPE] = 1
            next_parity ^= 1

        if next_y == Y_ERROR:
            nxt: Hashable = ERROR
        elif build and next_y in ym.halting_states:
            if not isinstance(next_y, YState):
                nxt = ERROR
            else:
                nxt = Control("AFTER_BUILD", run=run, y=next_y)
        elif walk and _is_walk_boundary(next_y):
            assert isinstance(next_y, YState)
            check_tag = {"PLAIN": "MARK_PLAIN", "PREFIX": "CHECK_PREFIX", "SUFFIX": "CHECK_SUFFIX"}[run]
            nxt = Control(check_tag, run=run, y=next_y, parity=next_parity)
        elif walk and next_y in ym.halting_states:
            nxt = ERROR
        else:
            assert isinstance(next_y, YState)
            nxt = WrappedY(state.phase, next_y, next_parity)
        result.append(row(state, nxt, reads=reads, writes=writes, moves=moves))
    return tuple(result)


def outgoing_rows(state: Hashable) -> tuple[SparseRow, ...]:
    if state in (DONE, ERROR):
        return ()
    if isinstance(state, Control):
        return controller_rows(state)
    if isinstance(state, WrappedY):
        return wrapped_y_rows(state)
    raise AssertionError(state)


# ---------------------------------------------------------------------------
# Reachability, execution, and export.


@dataclass
class CheckpointConfiguration:
    state: Hashable
    tapes: list[dict[int, str]]
    heads: list[int]
    steps: int = 0

    def scanned(self) -> tuple[str, ...]:
        return tuple(self.tapes[i].get(self.heads[i], BLANK) for i in range(TAPE_COUNT))


def _write_word(word: str) -> dict[int, str]:
    return {i: ch for i, ch in enumerate(word) if ch != BLANK}


def initial_configuration(word: str) -> CheckpointConfiguration:
    if not word or any(ch not in "01" for ch in word):
        raise ValueError("word must be a nonempty binary string")
    source = SENTINEL + word + END
    tapes: list[dict[int, str]] = [_write_word(source) for _ in range(SRC_COUNT)]
    heads = [1, len(word), 1]

    template = y_initial_configuration("00")
    for _run in RUN_NAMES:
        # Three private frozen pattern copies, initially containing only the
        # left sentinel.  Preparation writes the body and endmarker.
        for _ in range(3):
            tapes.append({0: SENTINEL}); heads.append(1)
        for local in range(2, 17):
            tapes.append(dict(template.tapes[local])); heads.append(template.heads[local])

    for _ in range(6):
        tapes.append({0: MARK}); heads.append(0)
    assert len(tapes) == TAPE_COUNT
    return CheckpointConfiguration(INITIAL, tapes, heads)


def step(config: CheckpointConfiguration) -> None:
    if config.state in (DONE, ERROR):
        raise RuntimeError("cannot step halted checkpoint machine")
    scanned = config.scanned()
    matches = [r for r in outgoing_rows(config.state) if r.matches(scanned)]
    if not matches:
        raise RuntimeError(("missing checkpoint row", config.state, scanned))
    first = matches[0]
    if any(other.action != first.action for other in matches[1:]):
        raise RuntimeError(("conflicting checkpoint rows", config.state, scanned, matches))
    for tape, symbol in first.action.writes:
        position = config.heads[tape]
        if symbol == BLANK:
            config.tapes[tape].pop(position, None)
        else:
            config.tapes[tape][position] = symbol
    for tape, move in first.action.moves:
        config.heads[tape] += move
    config.state = first.action.next_state
    config.steps += 1


def run(config: CheckpointConfiguration, max_steps: int = 100_000_000) -> int:
    start = config.steps
    while config.state not in (DONE, ERROR):
        if config.steps - start >= max_steps:
            raise TimeoutError((config.state, config.steps, config.scanned()))
        step(config)
    if config.state == ERROR:
        raise AssertionError(("checkpoint machine entered error", config.steps, config.scanned()))
    return config.steps - start


def marker_positions(config: CheckpointConfiguration, tape: int, symbol: str = GAP) -> tuple[int, ...]:
    return tuple(sorted(position for position, value in config.tapes[tape].items() if value == symbol))


@dataclass(frozen=True)
class OrdinaryCheckpointResult:
    gaps: tuple[int, ...]
    candidate: int | None
    microsteps: int


def run_checkpoint_ordinary(word: str, c: int = 16) -> OrdinaryCheckpointResult:
    if c != 16:
        raise ValueError("the generated checkpoint controller is currently specialized to c=16")
    config = initial_configuration(word)
    run(config)
    gaps = marker_positions(config, OUT1_TAPE) + marker_positions(config, OUT2_TAPE)
    candidate_positions = marker_positions(config, CANDIDATE_TAPE)
    return OrdinaryCheckpointResult(
        gaps=tuple(sorted(gaps)),
        candidate=candidate_positions[0] if candidate_positions else None,
        microsteps=config.steps,
    )


def enumerate_reachable() -> tuple[list[Hashable], int]:
    states: list[Hashable] = []
    seen: set[Hashable] = {INITIAL}
    queue = deque([INITIAL])
    rows = 0
    while queue:
        state = queue.popleft()
        states.append(state)
        outgoing = outgoing_rows(state)
        rows += len(outgoing)
        for item in outgoing:
            nxt = item.action.next_state
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return states, rows


def _atom_json(atom: ReadAtom):
    if isinstance(atom, frozenset):
        return sorted(atom)
    return atom


def export_table(path: str | Path = "generated/checkpoint_ordinary_table.json.gz") -> dict:
    states, row_count = enumerate_reachable()
    state_ids = {state: i for i, state in enumerate(states)}
    metadata = {
        "format": "sparse-map ordinary multitape TM v2",
        "semantics": (
            "Each row is one simultaneous one-cell transition. Missing read tapes are finite-alphabet "
            "wildcards; missing writes preserve; missing moves stay."
        ),
        "blank": BLANK,
        "c": 16,
        "tapes": TAPE_COUNT,
        "states": len(states),
        "rows": row_count,
        "initial_state": state_ids[INITIAL],
        "halting_states": [state_ids[DONE], state_ids[ERROR]],
        "error_state": state_ids[ERROR],
        "output_tapes": {
            "first_gap": OUT1_TAPE,
            "second_gap": OUT2_TAPE,
            "lemma33_candidate": CANDIDATE_TAPE,
            "marker": GAP,
        },
        "tape_alphabets": tape_alphabets(),
    }

    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == ".gz" else open
    mode = "wb"
    with opener(path, mode) as out:
        prefix = json.dumps(metadata, separators=(",", ":"))[:-1] + ',"rows_data":['
        out.write(prefix.encode())
        first = True
        for state in states:
            for item in outgoing_rows(state):
                data = [
                    state_ids[item.state],
                    [[t, _atom_json(a)] for t, a in item.reads],
                    state_ids[item.action.next_state],
                    [[t, s] for t, s in item.action.writes],
                    [[t, m] for t, m in item.action.moves],
                ]
                if not first:
                    out.write(b",")
                first = False
                out.write(json.dumps(data, separators=(",", ":")).encode())
        out.write(b"]}")
    return metadata


def export_summary(path: str | Path = "generated/checkpoint_ordinary_summary.json") -> dict:
    states, rows = enumerate_reachable()
    data = {
        "model": "ordinary one-head-per-tape checkpoint TM",
        "c": 16,
        "tapes": TAPE_COUNT,
        "states": len(states),
        "sparse_rows": rows,
        "algorithm_y_instances": 3,
        "candidate_representation": "monotone marker tapes",
        "operational_callbacks": False,
        "host_arithmetic_in_transitions": False,
    }
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


if __name__ == "__main__":
    print(export_summary())
    export_table()
    for sample in ("0", "00", "010", "0110", "0000", "010010"):
        print(sample, run_checkpoint_ordinary(sample))
