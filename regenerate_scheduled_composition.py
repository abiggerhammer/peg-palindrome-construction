"""Regenerate deterministic manifests for the factored scheduled composition.

The certified six-million-row source body remains represented by its existing
manifest and a pure one-for-one lift.  This script enumerates and hashes every
new source-dispatch, history-service, history-call, completion, and clock row.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from scheduled_source_composition import (
    ScheduledRow,
    certificate_dict,
    iter_buffer_service_rows,
    iter_small_controller_rows,
    iter_source_dispatch_rows,
)
from constant_speedup import certificate_dict as speedup_certificate_dict


def atom_json(atom):
    if isinstance(atom, frozenset):
        return ["SET", *sorted(atom, key=repr)]
    return atom


def row_json(row: ScheduledRow):
    return [
        row.state,
        row.input_symbol,
        [[t, atom_json(a)] for t, a in row.reads],
        row.action.next_state,
        [[t, v] for t, v in row.action.writes],
        [[t, m] for t, m in row.action.moves],
        row.action.input_move,
        row.action.emit,
    ]


def hash_rows(rows: Iterable[ScheduledRow]) -> tuple[int, str]:
    h = hashlib.sha256()
    count = 0
    for row in rows:
        h.update(json.dumps(row_json(row), separators=(",", ":"), sort_keys=False).encode())
        h.update(b"\n")
        count += 1
    return count, h.hexdigest()


def main(path: str | Path = "generated/scheduled_composition_row_family_manifest.json") -> dict:
    dispatch_count, dispatch_hash = hash_rows(iter_source_dispatch_rows())
    service_count, service_hash = hash_rows(iter_buffer_service_rows())
    small_count, small_hash = hash_rows(iter_small_controller_rows())
    source_manifest = Path("generated/sg_source_row_manifest.json")
    source_manifest_hash = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    data = {
        "format": "scheduled composition row-family manifest v1",
        "composition": certificate_dict(),
        "fixed_speedup": speedup_certificate_dict(),
        "source_manifest_sha256": source_manifest_hash,
        "source_lift": {
            "rows": certificate_dict()["transformed_source_rows"],
            "mapping": "pure lift_source_row, one output row per source row",
        },
        "enumerated_families": {
            "source_dispatch": {"rows": dispatch_count, "sha256": dispatch_hash},
            "input_history_service": {"rows": service_count, "sha256": service_hash},
            "small_scheduler_controller": {"rows": small_count, "sha256": small_hash},
        },
        "status": "all new row families deterministically regenerated; source lift tied to certified source manifest",
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(json.dumps(data, indent=2, sort_keys=True))
    return data


if __name__ == "__main__":
    main()
