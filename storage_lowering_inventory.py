"""Export the exact storage units remaining after read-only duplication."""

from __future__ import annotations

import json
from pathlib import Path

from fp_algorithm_y_multihead import MACHINE as Y_MACHINE
from pattern_prepare_multihead import MACHINE as PREP_MACHINE
from readonly_multihead_lowering import (
    append_read_unit_signature,
    heads_on_tape,
    split_readonly_shared_tapes,
    tape_is_read_only,
)


def inventory() -> dict[str, object]:
    prep = split_readonly_shared_tapes(PREP_MACHINE)
    y = split_readonly_shared_tapes(Y_MACHINE)
    residual = y.remaining_shared_tapes
    return {
        "three_pattern_prepare": {
            "source_tapes": PREP_MACHINE.tape_count,
            "source_heads": PREP_MACHINE.head_count,
            "read_only_source_tapes": [
                t for t in range(PREP_MACHINE.tape_count)
                if tape_is_read_only(PREP_MACHINE, t)
            ],
            "lowered_tapes": prep.machine.tape_count,
            "remaining_shared_tapes": list(prep.remaining_shared_tapes),
            "ordinary_multitape_complete": not prep.remaining_shared_tapes,
        },
        "algorithm_y": {
            "source_tapes": Y_MACHINE.tape_count,
            "source_heads": Y_MACHINE.head_count,
            "read_only_source_tapes": [
                t for t in range(Y_MACHINE.tape_count)
                if tape_is_read_only(Y_MACHINE, t)
            ],
            "lowered_tapes": y.machine.tape_count,
            "remaining_shared_tapes": list(residual),
            "residual_units": [append_read_unit_signature(y.machine, t) for t in residual],
        },
        "conclusion": (
            "All frozen-pattern multihead access is eliminated exactly by duplication. "
            "The sole remaining shared storage primitive is Algorithm Y's unary-Delta "
            "append/read unit (C movable reader, D right-moving append-only writer)."
        ),
    }


def export(path: str | Path = "generated/storage_lowering_inventory.json") -> None:
    Path(path).write_text(json.dumps(inventory(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    export()
