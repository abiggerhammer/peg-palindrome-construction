"""Ordinary six-tape table for the three-pattern preparation transducer."""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import json
from pathlib import Path

from flat_tm import Shift
from pattern_prepare_multihead import (
    MACHINE as SOURCE, HALT, WP, WPRE, WSUF,
    initial_configuration as source_initial,
)
from readonly_multihead_lowering import split_readonly_shared_tapes
from symbolic_tm import SymbolicConfiguration, SymbolicMultitapeMachine, SymbolicTableBuilder

LOWERED = split_readonly_shared_tapes(SOURCE)
assert not LOWERED.remaining_shared_tapes


def build_machine() -> SymbolicMultitapeMachine:
    # Physical tape order is logical-head order after duplication.
    tape_alphabets = tuple(
        LOWERED.machine.tape_alphabets[LOWERED.machine.head_to_tape[h]]
        for h in range(LOWERED.machine.head_count)
    )
    b = SymbolicTableBuilder(tape_alphabets, SOURCE.blank)
    for schema in SOURCE.schemata:
        b.add(schema.state, schema.reads, schema.next_state, schema.writes, schema.moves)
    return b.build({HALT})


MACHINE = build_machine()


def initial_configuration(word: str) -> SymbolicConfiguration:
    old = source_initial(word)
    split = LOWERED.transform_configuration(SOURCE, old)
    tapes = [dict(split.tapes[LOWERED.machine.head_to_tape[h]]) for h in range(6)]
    return SymbolicConfiguration(split.state, tapes, list(split.heads))


def _output(config: SymbolicConfiguration, tape: int, end: int) -> str:
    return "".join(config.tapes[tape].get(i, SOURCE.blank) for i in range(end))


@dataclass(frozen=True)
class OrdinaryPreparedPatterns:
    plain: str
    prefix: str
    suffix: str
    steps: int


def run_prepare_ordinary(word: str) -> OrdinaryPreparedPatterns:
    c = initial_configuration(word)
    MACHINE.run(c)
    return OrdinaryPreparedPatterns(
        _output(c, WP, c.heads[WP]),
        _output(c, WPRE, c.heads[WPRE]),
        _output(c, WSUF, c.heads[WSUF]),
        c.steps,
    )


def export_table(path: str | Path = "generated/pattern_prepare_ordinary_table.json.gz") -> None:
    state_ids = {state: i for i, state in enumerate(MACHINE.states)}
    data = {
        "format": "sparse ordinary multitape TM v1",
        "blank": MACHINE.blank,
        "tapes": MACHINE.tape_count,
        "states": len(MACHINE.states),
        "rows": len(MACHINE.rows),
        "initial_state": state_ids["PREP_COPY_FORWARD"],
        "halting_states": sorted(state_ids[s] for s in MACHINE.halting_states),
        "tape_alphabets": MACHINE.tape_alphabets,
        "rows_data": [
            [state_ids[r.state], list(r.reads), state_ids[r.action.next_state],
             list(r.action.writes), [int(x) for x in r.action.moves]]
            for r in MACHINE.rows
        ],
    }
    payload = json.dumps(data, separators=(",", ":")).encode()
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=9) as out:
        out.write(payload)


if __name__ == "__main__":
    export_table()
    for sample in ("0", "0110", "010001"):
        print(sample, run_prepare_ordinary(sample))
