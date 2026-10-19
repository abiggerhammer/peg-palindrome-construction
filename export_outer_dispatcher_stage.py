"""Export the registered service body and the tested SG dispatcher patch."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import orjson

from build_outer_service_fabric import build_fabric, main as build_body
from sg_outer_dispatcher_table import build_dispatcher_rows
from sg_outer_constant_cases import build_constant_case_rows, SOURCE_DONE_0, SOURCE_DONE_1


def _atom(atom):
    if isinstance(atom, frozenset):
        return sorted(atom, key=repr)
    return atom


def main() -> dict:
    # Regenerate the body header with the current control-tape layout.
    body_summary = build_body(full=True)

    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constants = build_constant_case_rows(fabric)
    patch_rows = dispatcher.rows + constants.rows + tuple(fabric.continuation_rows())
    path = Path("generated/outer_dispatcher_patch.jsonl.gz")
    header = {
        "format": "palindrome SG outer dispatcher patch v1",
        "semantics": (
            "append this row stream to outer_service_fabric_body.jsonl.gz; "
            "each row is one ordinary simultaneous one-cell transition"
        ),
        "blank": fabric.blank,
        "tapes": fabric.tape_count,
        "states": fabric.state_count_without_continuations,
        "tape_alphabets": fabric.tape_alphabets(),
        "continuation_dispatch_state": fabric.continue_dispatch_state,
        "continuation_tape": fabric.continuation_tape,
        "control_tapes": fabric.extra_tapes,
        "state_names": {
            str(k): v for k, v in {**dispatcher.state_names, **constants.state_names}.items()
        },
        "source_done_states": {"0": SOURCE_DONE_0, "1": SOURCE_DONE_1},
        "rows": len(patch_rows),
    }
    with gzip.open(path, "wb", compresslevel=1) as out:
        out.write(orjson.dumps(header, default=repr) + b"\n")
        for row in patch_rows:
            item = [
                row.state,
                [[t, _atom(a)] for t, a in row.reads],
                row.action.next_state,
                [[t, v] for t, v in row.action.writes],
                [[t, m] for t, m in row.action.moves],
            ]
            out.write(orjson.dumps(item, default=repr) + b"\n")

    summary = {
        "service_body": body_summary,
        "dispatcher_rows": len(dispatcher.rows),
        "constant_case_rows": len(constants.rows),
        "continuation_rows": len(tuple(fabric.continuation_rows())),
        "patch_rows": len(patch_rows),
        "body_path": "generated/outer_service_fabric_body.jsonl.gz",
        "patch_path": str(path),
        "combined_rows": body_summary["written_rows"] + len(patch_rows),
        "global_states": fabric.state_count_without_continuations,
        "global_tapes": fabric.tape_count,
        "case_entry_states": {
            name: state for state, name in dispatcher.state_names.items()
            if name.startswith("CASE_")
        },
        "source_done_states": {"0": SOURCE_DONE_0, "1": SOURCE_DONE_1},
    }
    Path("generated/outer_dispatcher_stage_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    main()
