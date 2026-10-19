"""Build the registered service fabric used by the final SG outer controller.

The output intentionally reserves 8192 low-numbered states for the finite
outer microprogram.  The giant worker controls then occupy disjoint active
state ranges.  Adding or revising the outer program does not renumber or
regenerate the worker body.
"""

from __future__ import annotations

import json
from pathlib import Path

import history_zipper_ordinary_tm as hz
from construction_constants import background_clock_shape
from sparse_registered_linker import (
    JsonSparseAdapter,
    SparseRegisteredFabric,
    SymbolicAdapter,
    write_sparse_rows_json_gz,
    write_sparse_rows_jsonl_gz,
)
from unary_counter_ordinary_tm import ERROR, READY, machine as counter_machine

CONTROLLER_RESERVE = 262144
HISTORY_NAMES = (
    "B", "BP", "LB", "LBP", "BG", "BGL",
    "L33_CURRENT", "L33_LAG", "L33_COPY",
)
COUNTER_NAMES = (
    "GAP", "K_MAG", "BG_RETURN", "RADIUS", "QUOTA", "LENGTH",
    "RESTORE", "CANDIDATE", "TARGET", "SCRATCH", "SCAN", "CLOCK",
)

CONTROL_TAPES = {
    "INPUT": ("_", "0", "1"),
    "SECOND": ("_", "K", "U"),
    "B_REL": ("_", "B", "A", "X"),
    "BP_REL": ("_", "B", "A", "X"),
    "BG_REL": ("_", "B", "A", "X"),
    "LB_REL": ("_", "E", "A", "1", "2"),
    "LBP_REL": ("_", "E", "A", "1", "2"),
    "BGL_REL": ("_", "E", "A", "1", "2"),
    "B_OK": ("_", "0", "1"),
    "BP_OK": ("_", "0", "1"),
    "GAP_LARGE": ("_", "0", "1"),
    "LAZY_MODE": ("_", "N", "C", "R", "U"),
    "COPY_NEEDED": ("_", "0", "1"),
    "K_SIGN": ("_", "N", "Z", "P"),
    "OUTPUT": ("_", "0", "1"),
    "CASE": ("_", "1", "2", "3", "4", "5", "6"),
    "L33_PHASE": (
        "_", "I", "T0", "T1", "T2", "LC", "LW", "SC", "SL", "Q",
        "S", "RF", "RC", "RS", "RA", "RK", "BC", "BR", "TR", "TS", "TX",
        "CG", "CB", "FG", "FB", "CR", "CL", "CC", "W0", "W1", "WV",
    ),
    "CLOCK_PHASE": tuple(
        ["_"] + [f"P{i}" for i in range(background_clock_shape()[1])]
    ),
}


def build_fabric() -> SparseRegisteredFabric:
    hm = hz.machine()
    histories = tuple(
        SymbolicAdapter(
            name, hm,
            frozenset(hm.halting_states - {hz.ERROR_STATE}),
            frozenset((hz.ERROR_STATE,)),
        )
        for name in HISTORY_NAMES
    )
    checkpoint = JsonSparseAdapter(
        "CHECKPOINT", "generated/checkpoint_reusable_table.json.gz"
    )
    cm = counter_machine()
    counters = tuple(
        SymbolicAdapter(name, cm, frozenset((READY,)), frozenset((ERROR,)))
        for name in COUNTER_NAMES
    )
    controller_states = tuple(range(CONTROLLER_RESERVE))
    return SparseRegisteredFabric(
        histories + (checkpoint,) + counters,
        controller_states=controller_states,
        extra_tape_alphabets=CONTROL_TAPES,
    )


def main(*, full: bool = True) -> dict:
    fabric = build_fabric()
    summary = fabric.summary()
    summary.update({
        "controller_state_reserve": CONTROLLER_RESERVE,
        "history_components": HISTORY_NAMES,
        "counter_components": COUNTER_NAMES,
        "checkpoint_component": "CHECKPOINT",
        "continuation_dispatch_state": fabric.continue_dispatch_state,
        "continuation_tape": fabric.continuation_tape,
        "control_tapes": fabric.extra_tapes,
        "note": (
            "Worker body only. Outer controller call rows and the shared "
            "continuation rows are appended after its program counters are assigned."
        ),
    })
    out = Path("generated/outer_service_fabric_summary.json")
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if full:
        path = Path("generated/outer_service_fabric_body.jsonl.gz")
        count = write_sparse_rows_jsonl_gz(
            path,
            fabric=fabric,
            rows=fabric.all_service_rows(),
            metadata={
                "format": "palindrome SG registered service fabric body v1",
                "semantics": (
                    "one simultaneous ordinary one-cell transition; omitted "
                    "reads wildcard, writes preserve, moves stay"
                ),
                "controller_state_reserve": CONTROLLER_RESERVE,
                "continuation_dispatch_state": fabric.continue_dispatch_state,
                "continuation_tape": fabric.continuation_tape,
        "control_tapes": fabric.extra_tapes,
                "components": summary["components"],
            },
        )
        summary["written_rows"] = count
        summary["body_path"] = str(path)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    main()
