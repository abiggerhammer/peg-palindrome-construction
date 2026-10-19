"""Streaming sparse sum-composition for registered ordinary-TM components.

This module is the table-production counterpart of
:mod:`registered_component_service`.  It embeds many disjoint ordinary
multitape components into one global tape layout while keeping their finite
controls in one-cell state registers.  The emitted global state set is a *sum*
of component state sets, never their Cartesian product.

Rows use sparse maps:

* omitted reads are finite-alphabet wildcards;
* omitted writes preserve the scanned symbol;
* omitted moves stay put.

Every row still denotes exactly one simultaneous ordinary-TM transition.
"""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import json
from pathlib import Path
from typing import Callable, Hashable, Iterable, Iterator, Mapping, Protocol, Sequence

from flat_tm import Shift
from symbolic_tm import SymbolicMultitapeMachine

ReadAtom = Hashable | frozenset[Hashable]


@dataclass(frozen=True)
class SparseAction:
    next_state: int
    writes: tuple[tuple[int, Hashable], ...] = ()
    moves: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class SparseRow:
    state: int
    reads: tuple[tuple[int, ReadAtom], ...]
    action: SparseAction


@dataclass(frozen=True)
class LocalSparseRow:
    state_id: int
    reads: tuple[tuple[int, ReadAtom], ...]
    next_state_id: int
    writes: tuple[tuple[int, Hashable], ...]
    moves: tuple[tuple[int, int], ...]


class ComponentAdapter(Protocol):
    name: str
    blank: str
    tape_alphabets: tuple[tuple[Hashable, ...], ...]
    state_count: int
    ready_state_ids: frozenset[int]
    error_state_ids: frozenset[int]

    def rows(self) -> Iterator[LocalSparseRow]: ...


@dataclass
class SymbolicAdapter:
    name: str
    machine: SymbolicMultitapeMachine
    ready_states: frozenset[Hashable]
    error_states: frozenset[Hashable] = frozenset()

    def __post_init__(self) -> None:
        self.blank = self.machine.blank
        self.tape_alphabets = tuple(tuple(a) for a in self.machine.tape_alphabets)
        self.id_to_state = tuple(self.machine.states)
        self.state_to_id = {state: i for i, state in enumerate(self.id_to_state)}
        self.state_count = len(self.id_to_state)
        self.row_count = len(self.machine.rows)
        self.ready_state_ids = frozenset(self.state_to_id[q] for q in self.ready_states)
        self.error_state_ids = frozenset(self.state_to_id[q] for q in self.error_states)

    def rows(self) -> Iterator[LocalSparseRow]:
        for row in self.machine.rows:
            reads = tuple(
                (i, atom) for i, atom in enumerate(row.reads) if atom is not None
            )
            writes = tuple(
                (i, value) for i, value in enumerate(row.action.writes)
                if value is not None
            )
            moves = tuple(
                (i, int(move)) for i, move in enumerate(row.action.moves)
                if move is not Shift.STAY
            )
            yield LocalSparseRow(
                self.state_to_id[row.state], reads,
                self.state_to_id[row.action.next_state], writes, moves,
            )


@dataclass
class JsonSparseAdapter:
    """Adapter for an already generated sparse-map JSON table."""

    name: str
    path: str | Path

    def __post_init__(self) -> None:
        path = Path(self.path)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as handle:
            data = json.load(handle)
        self._data = data
        self.blank = data["blank"]
        self.tape_alphabets = tuple(tuple(a) for a in data["tape_alphabets"])
        self.state_count = int(data["states"])
        self.row_count = int(data["rows"])
        ready = data.get("ready_states")
        if ready is None:
            ready = (data["ready_state"],)
        self.ready_state_ids = frozenset(map(int, ready))
        self.result_ready_state_id = (
            int(data["result_ready_state"]) if "result_ready_state" in data else None
        )
        self.clean_ready_state_id = (
            int(data["clean_ready_state"]) if "clean_ready_state" in data
            else int(data["ready_state"])
        )
        errors = []
        if "error_state" in data:
            errors.append(int(data["error_state"]))
        self.error_state_ids = frozenset(errors)

    @staticmethod
    def _decode_row(raw) -> LocalSparseRow:
        # Sparse-map formats use [state, reads, next, writes, moves].
        state, reads, nxt, writes, moves = raw
        return LocalSparseRow(
            int(state),
            tuple((int(t), _decode_atom(atom)) for t, atom in reads),
            int(nxt),
            tuple((int(t), value) for t, value in writes),
            tuple((int(t), int(move)) for t, move in moves),
        )

    def rows(self) -> Iterator[LocalSparseRow]:
        for raw in self._data["rows_data"]:
            yield self._decode_row(raw)

    def rows_for_state(self, state_id: int) -> tuple[LocalSparseRow, ...]:
        """Decode only one state's rows, retaining a compact slice index.

        Generated tables are state-sorted.  The lazy audit interpreter uses
        this method so a 700k-row checkpoint table need not be duplicated as
        Python row objects merely to execute a few selected outer traces.
        """
        index = getattr(self, "_state_slices", None)
        if index is None:
            index = {}
            rows = self._data["rows_data"]
            start = 0
            while start < len(rows):
                state = int(rows[start][0])
                end = start + 1
                while end < len(rows) and int(rows[end][0]) == state:
                    end += 1
                index[state] = (start, end)
                start = end
            self._state_slices = index
        bounds = index.get(int(state_id))
        if bounds is None:
            return ()
        start, end = bounds
        return tuple(self._decode_row(raw) for raw in self._data["rows_data"][start:end])


def _decode_atom(atom):
    if isinstance(atom, list):
        return frozenset(atom)
    return atom


def _json_atom(atom):
    if isinstance(atom, frozenset):
        return sorted(atom, key=repr)
    return atom


@dataclass(frozen=True)
class Layout:
    adapter: ComponentAdapter
    tape_start: int
    register_tape: int
    load_state: int
    active_start: int
    error_state: int

    def active_state(self, local_state_id: int) -> int:
        return self.active_start + local_state_id

    def qsymbol(self, local_state_id: int) -> str:
        return f"@{self.adapter.name}:q{local_state_id}"


class SparseRegisteredFabric:
    """Global disjoint layout and streaming row generator."""

    def __init__(
        self,
        adapters: Sequence[ComponentAdapter],
        *,
        controller_states: Sequence[Hashable] = (),
        blank: str = "_",
        extra_tape_alphabets: Mapping[str, Sequence[Hashable]] | None = None,
    ) -> None:
        self.adapters = tuple(adapters)
        self.blank = blank
        self.controller_states = tuple(controller_states)
        self.controller_ids = {state: i for i, state in enumerate(self.controller_states)}
        # One shared continuation dispatcher replaces one RETURN state and
        # one continuation-row family per component.
        self.continue_dispatch_state = len(self.controller_states)
        next_state = self.continue_dispatch_state + 1
        next_tape = 0
        alphabets: list[tuple[Hashable, ...]] = []
        layouts: list[Layout] = []
        for adapter in self.adapters:
            if adapter.blank != blank:
                raise ValueError((adapter.name, adapter.blank, blank))
            tape_start = next_tape
            alphabets.extend(adapter.tape_alphabets)
            next_tape += len(adapter.tape_alphabets)
            register_tape = next_tape
            alphabets.append(tuple(
                f"@{adapter.name}:q{i}" for i in range(adapter.state_count)
            ) + (blank,))
            next_tape += 1
            load_state = next_state
            error_state = next_state + 1
            active_start = next_state + 2
            next_state = active_start + adapter.state_count
            layouts.append(Layout(
                adapter, tape_start, register_tape,
                load_state, active_start, error_state,
            ))
        self.layouts = tuple(layouts)
        self.by_name = {layout.adapter.name: layout for layout in layouts}
        self.continuation_tape = next_tape
        self._continuations: set[int] = set()
        alphabets.append((blank,))
        next_tape += 1
        self.extra_tapes: dict[str, int] = {}
        for name, alphabet in (extra_tape_alphabets or {}).items():
            if name in self.extra_tapes:
                raise ValueError(name)
            values = tuple(alphabet)
            if blank not in values:
                values = values + (blank,)
            self.extra_tapes[name] = next_tape
            alphabets.append(values)
            next_tape += 1
        self._alphabets = alphabets
        self.state_count_without_continuations = next_state

    @property
    def tape_count(self) -> int:
        return len(self._alphabets)

    def layout(self, name: str) -> Layout:
        return self.by_name[name]

    def controller_id(self, state: Hashable) -> int:
        return self.controller_ids[state]

    @staticmethod
    def continuation_symbol(state_id: int) -> str:
        return f"@CONT:q{state_id}"

    def register_continuation(self, state_id: int) -> None:
        if not 0 <= state_id < len(self.controller_states):
            raise ValueError(state_id)
        self._continuations.add(state_id)

    def tape_alphabets(self) -> tuple[tuple[Hashable, ...], ...]:
        alphabets = list(self._alphabets)
        alphabets[self.continuation_tape] = tuple(
            self.continuation_symbol(i) for i in sorted(self._continuations)
        ) + (self.blank,)
        return tuple(alphabets)

    def call_rows(
        self,
        *,
        caller_state: Hashable,
        component: str,
        continuation_state: Hashable,
        entry_transform: Callable[[int], int],
        allowed_local_states: Iterable[int],
    ) -> Iterator[SparseRow]:
        layout = self.layout(component)
        caller = self.controller_id(caller_state)
        continuation = self.controller_id(continuation_state)
        self.register_continuation(continuation)
        for paused in allowed_local_states:
            entry = entry_transform(paused)
            if not 0 <= entry < layout.adapter.state_count:
                raise ValueError((component, paused, entry))
            yield SparseRow(
                caller,
                ((layout.register_tape, layout.qsymbol(paused)),),
                SparseAction(
                    layout.load_state,
                    (
                        (layout.register_tape, layout.qsymbol(entry)),
                        (self.continuation_tape, self.continuation_symbol(continuation)),
                    ),
                    (),
                ),
            )

    def service_rows(self, component: str) -> Iterator[SparseRow]:
        layout = self.layout(component)
        adapter = layout.adapter
        for q in range(adapter.state_count):
            if q in adapter.error_state_ids:
                nxt = layout.error_state
            elif q in adapter.ready_state_ids:
                nxt = self.continue_dispatch_state
            else:
                nxt = layout.active_state(q)
            yield SparseRow(
                layout.load_state,
                ((layout.register_tape, layout.qsymbol(q)),),
                SparseAction(nxt),
            )
        for row in adapter.rows():
            reads = tuple(
                (layout.tape_start + tape, atom) for tape, atom in row.reads
            ) + ((layout.register_tape, layout.qsymbol(row.state_id)),)
            writes = tuple(
                (layout.tape_start + tape, value) for tape, value in row.writes
            ) + ((layout.register_tape, layout.qsymbol(row.next_state_id)),)
            moves = tuple(
                (layout.tape_start + tape, move) for tape, move in row.moves
            )
            yield SparseRow(
                layout.active_state(row.state_id),
                reads,
                SparseAction(layout.load_state, writes, moves),
            )
    def continuation_rows(self) -> Iterator[SparseRow]:
        for continuation in sorted(self._continuations):
            yield SparseRow(
                self.continue_dispatch_state,
                ((self.continuation_tape, self.continuation_symbol(continuation)),),
                SparseAction(continuation),
            )

    def all_service_rows(self) -> Iterator[SparseRow]:
        for layout in self.layouts:
            yield from self.service_rows(layout.adapter.name)
        yield from self.continuation_rows()

    def initial_register_symbols(self, local_states: Mapping[str, int]) -> dict[int, str]:
        result = {}
        for name, local_state in local_states.items():
            layout = self.layout(name)
            result[layout.register_tape] = layout.qsymbol(local_state)
        return result

    def summary(self, controller_rows: int = 0) -> dict:
        service_rows = sum(
            layout.adapter.state_count
            + layout.adapter.row_count
            for layout in self.layouts
        ) + len(self._continuations)
        return {
            "format": "sparse registered ordinary multitape TM fabric v1",
            "blank": self.blank,
            "components": [
                {
                    "name": layout.adapter.name,
                    "tapes": len(layout.adapter.tape_alphabets),
                    "states": layout.adapter.state_count,
                    "ready_states": len(layout.adapter.ready_state_ids),
                    "rows": layout.adapter.row_count,
                    "global_tape_start": layout.tape_start,
                    "state_register_tape": layout.register_tape,
                    "global_active_state_start": layout.active_start,
                }
                for layout in self.layouts
            ],
            "controller_states": len(self.controller_states),
            "global_states": self.state_count_without_continuations,
            "global_tapes": self.tape_count,
            "service_rows": service_rows,
            "controller_rows": controller_rows,
            "total_rows": service_rows + controller_rows,
            "continuations": len(self._continuations),
            "extra_tapes": dict(self.extra_tapes),
        }


def write_sparse_rows_json_gz(
    path: str | Path,
    *,
    fabric: SparseRegisteredFabric,
    rows: Iterable[SparseRow],
    metadata: Mapping[str, object],
) -> int:
    """Stream a compact JSON table without retaining its rows in memory."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with gzip.open(path, "wt", compresslevel=9) as out:
        prefix = dict(metadata)
        prefix.update({
            "blank": fabric.blank,
            "tapes": fabric.tape_count,
            "states": fabric.state_count_without_continuations,
            "tape_alphabets": fabric.tape_alphabets(),
        })
        raw = json.dumps(prefix, separators=(",", ":"))
        if not raw.endswith("}"):
            raise AssertionError(raw[-20:])
        out.write(raw[:-1])
        out.write(',"rows_data":[')
        first = True
        for row in rows:
            item = [
                row.state,
                [[t, _json_atom(a)] for t, a in row.reads],
                row.action.next_state,
                [[t, v] for t, v in row.action.writes],
                [[t, m] for t, m in row.action.moves],
            ]
            if not first:
                out.write(",")
            first = False
            out.write(json.dumps(item, separators=(",", ":"), default=repr))
            count += 1
        out.write("]}")
    return count


def write_sparse_rows_jsonl_gz(
    path: str | Path,
    *,
    fabric: SparseRegisteredFabric,
    rows: Iterable[SparseRow],
    metadata: Mapping[str, object],
    compresslevel: int = 1,
) -> int:
    """Fast streaming JSON-lines form for multi-million-row component bodies.

    Line 1 is a header object.  Every later line is one compact row array
    ``[state, reads, next, writes, moves]``.  This avoids both a giant in-memory
    JSON array and the substantial per-row overhead of the standard encoder.
    """
    import orjson

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = dict(metadata)
    header.update({
        "blank": fabric.blank,
        "tapes": fabric.tape_count,
        "states": fabric.state_count_without_continuations,
        "tape_alphabets": fabric.tape_alphabets(),
        "row_encoding": "one compact JSON array per following line",
    })
    count = 0
    with gzip.open(path, "wb", compresslevel=compresslevel) as out:
        out.write(orjson.dumps(header, default=repr))
        out.write(b"\n")
        for row in rows:
            item = [
                row.state,
                [[t, _json_atom(a)] for t, a in row.reads],
                row.action.next_state,
                [[t, v] for t, v in row.action.writes],
                [[t, m] for t, m in row.action.moves],
            ]
            out.write(orjson.dumps(item, default=repr))
            out.write(b"\n")
            count += 1
    return count


@dataclass
class SparseFabricConfiguration:
    state: int
    tapes: list[dict[int, Hashable]]
    heads: list[int]
    steps: int = 0


class SparseFabricInterpreter:
    """Small audit interpreter for linked sparse rows."""

    def __init__(self, fabric: SparseRegisteredFabric, rows: Iterable[SparseRow]) -> None:
        self.fabric = fabric
        self.rows = tuple(rows)
        by_state: dict[int, list[SparseRow]] = {}
        for row in self.rows:
            by_state.setdefault(row.state, []).append(row)
        self.by_state = by_state

    def scanned(self, config: SparseFabricConfiguration) -> tuple[Hashable, ...]:
        return tuple(
            config.tapes[i].get(config.heads[i], self.fabric.blank)
            for i in range(self.fabric.tape_count)
        )

    @staticmethod
    def _matches(row: SparseRow, scanned: Sequence[Hashable]) -> bool:
        for tape, atom in row.reads:
            value = scanned[tape]
            if isinstance(atom, frozenset):
                if value not in atom:
                    return False
            elif value != atom:
                return False
        return True

    def step(self, config: SparseFabricConfiguration) -> None:
        scanned = self.scanned(config)
        matches = [
            row for row in self.by_state.get(config.state, ())
            if self._matches(row, scanned)
        ]
        if not matches:
            raise RuntimeError(("missing sparse-fabric row", config.state, scanned))
        action = matches[0].action
        if any(row.action != action for row in matches[1:]):
            raise RuntimeError(("conflicting sparse-fabric rows", config.state, scanned, matches))
        writes = dict(action.writes)
        moves = dict(action.moves)
        for tape, old in enumerate(scanned):
            value = writes.get(tape, old)
            pos = config.heads[tape]
            if value == self.fabric.blank:
                config.tapes[tape].pop(pos, None)
            else:
                config.tapes[tape][pos] = value
            config.heads[tape] += moves.get(tape, 0)
        config.state = action.next_state
        config.steps += 1


class LazySparseFabricInterpreter:
    """Audit interpreter that expands registered component rows on demand.

    This avoids materializing millions of repeated global service rows during
    differential tests.  The emitted production table is unchanged.
    """

    def __init__(
        self,
        fabric: SparseRegisteredFabric,
        controller_rows: Iterable[SparseRow],
        *,
        deferred_checkpoint_calls: Iterable[object] = (),
    ) -> None:
        self.fabric = fabric
        self.deferred_checkpoint_calls = {
            int(spec.state): spec for spec in deferred_checkpoint_calls
        }
        by_state: dict[int, list[SparseRow]] = {}
        for row in controller_rows:
            by_state.setdefault(row.state, []).append(row)
        self.controller_by_state = by_state
        # Large controller families (notably the one-step checkpoint service)
        # are indexed by their most discriminating singleton read.  This keeps
        # audit execution proportional to the handful of rows relevant to the
        # scanned state-register symbol rather than to a 700k-row family.
        self.controller_indexes: dict[
            int, tuple[int, dict[Hashable, tuple[SparseRow, ...]], tuple[SparseRow, ...]]
        ] = {}
        for state, rows in by_state.items():
            if len(rows) < 1024:
                continue
            # Registered-component call/step families carry a highly
            # discriminating state-register symbol such as @CHECKPOINT:q123.
            # Detect that tape in one pass, then group only by it.  Building
            # candidate maps for every read tape was both slower and much more
            # memory hungry than the table itself.
            chosen_tape = None
            for row in rows:
                for tape, atom in row.reads:
                    if (
                        isinstance(atom, str)
                        and atom.startswith("@")
                        and ":q" in atom
                    ):
                        chosen_tape = tape
                        break
                if chosen_tape is not None:
                    break
            if chosen_tape is None:
                continue
            groups: dict[Hashable, list[SparseRow]] = {}
            fallback: list[SparseRow] = []
            for row in rows:
                value = None
                for tape, atom in row.reads:
                    if tape == chosen_tape and not isinstance(atom, frozenset):
                        value = atom
                        break
                if value is None:
                    fallback.append(row)
                else:
                    groups.setdefault(value, []).append(row)
            self.controller_indexes[state] = (
                chosen_tape,
                {value: tuple(group) for value, group in groups.items()},
                tuple(fallback),
            )
        self._symbolic_rows: dict[tuple[str, int], tuple[LocalSparseRow, ...]] = {}
        for layout in fabric.layouts:
            adapter = layout.adapter
            if isinstance(adapter, SymbolicAdapter):
                grouped: dict[int, list[LocalSparseRow]] = {}
                for row in adapter.rows():
                    grouped.setdefault(row.state_id, []).append(row)
                for qid, rows in grouped.items():
                    self._symbolic_rows[(adapter.name, qid)] = tuple(rows)

    def scanned(self, config: SparseFabricConfiguration) -> tuple[Hashable, ...]:
        return tuple(
            config.tapes[i].get(config.heads[i], self.fabric.blank)
            for i in range(self.fabric.tape_count)
        )

    @staticmethod
    def _row_matches(row: SparseRow, scanned: Sequence[Hashable]) -> bool:
        for tape, atom in row.reads:
            value = scanned[tape]
            if isinstance(atom, frozenset):
                if value not in atom:
                    return False
            elif value != atom:
                return False
        return True

    @staticmethod
    def _local_matches(row: LocalSparseRow, scanned: Sequence[Hashable]) -> bool:
        for tape, atom in row.reads:
            value = scanned[tape]
            if isinstance(atom, frozenset):
                if value not in atom:
                    return False
            elif value != atom:
                return False
        return True

    def _apply(
        self,
        config: SparseFabricConfiguration,
        *,
        next_state: int,
        writes: Mapping[int, Hashable],
        moves: Mapping[int, int],
        scanned: Sequence[Hashable],
    ) -> None:
        for tape, old in enumerate(scanned):
            value = writes.get(tape, old)
            pos = config.heads[tape]
            if value == self.fabric.blank:
                config.tapes[tape].pop(pos, None)
            else:
                config.tapes[tape][pos] = value
            config.heads[tape] += moves.get(tape, 0)
        config.state = next_state
        config.steps += 1

    def step(self, config: SparseFabricConfiguration) -> None:  # noqa: C901
        scanned = self.scanned(config)
        deferred = self.deferred_checkpoint_calls.get(config.state)
        # A deferred single-step checkpoint family shares its outer state with
        # the other fixed-budget Case-5 phases.  Its production rows are
        # guarded by L33_PHASE == "S"; mirror that guard here and fall through
        # to ordinary controller rows for every other phase.
        if deferred is not None and deferred.mode == "single_step":
            phase_value = scanned[self.fabric.extra_tapes["L33_PHASE"]]
            if phase_value not in ("S", "CL", "CC"):
                deferred = None
        if deferred is not None:
            layout = self.fabric.layout("CHECKPOINT")
            adapter = layout.adapter
            symbol = scanned[layout.register_tape]
            prefix = "@CHECKPOINT:q"
            if not isinstance(symbol, str) or not symbol.startswith(prefix):
                raise RuntimeError(("bad deferred checkpoint register", symbol))
            qid = int(symbol[len(prefix):])

            if deferred.mode == "run_to_result":
                if qid in adapter.error_state_ids:
                    raise RuntimeError(("deferred checkpoint error", qid))
                if qid not in adapter.ready_state_ids:
                    continuation = self.fabric.controller_id(deferred.continuation)
                    self.fabric.register_continuation(continuation)
                    self._apply(
                        config,
                        next_state=layout.load_state,
                        writes={
                            self.fabric.continuation_tape:
                                self.fabric.continuation_symbol(continuation),
                        },
                        moves={}, scanned=scanned,
                    )
                    return
                deferred = None

            elif deferred.mode == "single_step":
                phase_tape = self.fabric.extra_tapes["L33_PHASE"]
                phase_value = scanned[phase_tape]
                result_ready = getattr(adapter, "result_ready_state_id", None)
                clean_ready = getattr(adapter, "clean_ready_state_id", None)
                if phase_value == "S" and qid == result_ready:
                    self._apply(
                        config, next_state=deferred.continuation,
                        writes={phase_tape: "RF"}, moves={}, scanned=scanned,
                    )
                    return
                if phase_value == "CL" and qid == clean_ready:
                    self._apply(
                        config, next_state=deferred.continuation,
                        writes={phase_tape: "T0"}, moves={}, scanned=scanned,
                    )
                    return
                if phase_value == "CC" and qid == clean_ready:
                    self._apply(
                        config, next_state=deferred.continuation,
                        writes={phase_tape: "CG"}, moves={}, scanned=scanned,
                    )
                    return
                if qid in adapter.error_state_ids:
                    raise RuntimeError(("deferred checkpoint error", qid))
                if qid not in adapter.ready_state_ids:
                    if not isinstance(adapter, JsonSparseAdapter):
                        raise TypeError(type(adapter))
                    local_scanned = scanned[
                        layout.tape_start : layout.tape_start + len(adapter.tape_alphabets)
                    ]
                    local_rows = adapter.rows_for_state(qid)
                    matches = [r for r in local_rows if self._local_matches(r, local_scanned)]
                    if not matches:
                        raise RuntimeError(("missing deferred checkpoint row", qid, local_scanned))
                    row = matches[0]
                    if any(
                        (r.next_state_id, r.writes, r.moves)
                        != (row.next_state_id, row.writes, row.moves)
                        for r in matches[1:]
                    ):
                        raise RuntimeError(("conflicting deferred checkpoint rows", qid))
                    writes = {
                        layout.tape_start + tape: value for tape, value in row.writes
                    }
                    writes[layout.register_tape] = layout.qsymbol(row.next_state_id)
                    moves = {
                        layout.tape_start + tape: move for tape, move in row.moves
                    }
                    self._apply(
                        config, next_state=deferred.continuation,
                        writes=writes, moves=moves, scanned=scanned,
                    )
                    return
                deferred = None
            else:
                raise ValueError(deferred.mode)
        # Outer/controller rows, including call rows and continuation dispatch.
        rows = self.controller_by_state.get(config.state)
        if rows is not None:
            indexed = self.controller_indexes.get(config.state)
            if indexed is not None:
                tape, groups, fallback = indexed
                rows = groups.get(scanned[tape], ()) + fallback
            matches = [row for row in rows if self._row_matches(row, scanned)]
            if not matches:
                raise RuntimeError(("missing lazy controller row", config.state, scanned))
            action = matches[0].action
            if any(row.action != action for row in matches[1:]):
                raise RuntimeError(("conflicting lazy controller rows", config.state, scanned))
            self._apply(
                config,
                next_state=action.next_state,
                writes=dict(action.writes),
                moves=dict(action.moves),
                scanned=scanned,
            )
            return

        if config.state == self.fabric.continue_dispatch_state:
            symbol = scanned[self.fabric.continuation_tape]
            prefix = "@CONT:q"
            if not isinstance(symbol, str) or not symbol.startswith(prefix):
                raise RuntimeError(("bad continuation symbol", symbol))
            self._apply(
                config, next_state=int(symbol[len(prefix):]),
                writes={}, moves={}, scanned=scanned,
            )
            return

        for layout in self.fabric.layouts:
            adapter = layout.adapter
            if config.state == layout.load_state:
                symbol = scanned[layout.register_tape]
                prefix = f"@{adapter.name}:q"
                if not isinstance(symbol, str) or not symbol.startswith(prefix):
                    raise RuntimeError(("bad component register", adapter.name, symbol))
                qid = int(symbol[len(prefix):])
                if qid in adapter.error_state_ids:
                    nxt = layout.error_state
                elif qid in adapter.ready_state_ids:
                    nxt = self.fabric.continue_dispatch_state
                else:
                    nxt = layout.active_state(qid)
                self._apply(config, next_state=nxt, writes={}, moves={}, scanned=scanned)
                return
            if layout.active_start <= config.state < layout.active_start + adapter.state_count:
                qid = config.state - layout.active_start
                local_rows = self._symbolic_rows.get((adapter.name, qid))
                if local_rows is None and isinstance(adapter, JsonSparseAdapter):
                    local_rows = adapter.rows_for_state(qid)
                if not local_rows:
                    raise NotImplementedError(("lazy rows unavailable", adapter.name, qid))
                local_scanned = scanned[
                    layout.tape_start : layout.tape_start + len(adapter.tape_alphabets)
                ]
                matches = [r for r in local_rows if self._local_matches(r, local_scanned)]
                if not matches:
                    raise RuntimeError(("missing local row", adapter.name, qid, local_scanned))
                row = matches[0]
                if any(
                    (r.next_state_id, r.writes, r.moves)
                    != (row.next_state_id, row.writes, row.moves)
                    for r in matches[1:]
                ):
                    raise RuntimeError(("conflicting local rows", adapter.name, qid))
                writes = {
                    layout.tape_start + tape: value for tape, value in row.writes
                }
                writes[layout.register_tape] = layout.qsymbol(row.next_state_id)
                moves = {
                    layout.tape_start + tape: move for tape, move in row.moves
                }
                self._apply(
                    config, next_state=layout.load_state,
                    writes=writes, moves=moves, scanned=scanned,
                )
                return
        raise RuntimeError(("unknown lazy fabric state", config.state))
