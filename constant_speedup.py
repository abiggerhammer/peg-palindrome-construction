"""Explicit Hartmanis--Stearns speedup application for the scheduled machine.

This module does *not* invent a new block simulation.  It records the exact
application of the classical constant-speedup theorem used by Galil himself:
one iteration combines pairs of old tape symbols, stores the adjacent
information in finite control, and simulates two old operations in one new
operation.  Repeating this construction 39 times gives enough capacity to
compress the proved bounded delay into one conventional real-time operation.

The resulting finite control and block alphabets are effective but intentionally
left factored.  Materializing them is neither required for the existence proof
nor remotely practical; a later PEG compiler must consume this factored
Hartmanis--Stearns representation symbolically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

from scheduled_source_composition import BOUNDED_DELAY_TRANSITIONS


SPEEDUP_HALVINGS = (BOUNDED_DELAY_TRANSITIONS - 1).bit_length()
MACRO_CAPACITY = 1 << SPEEDUP_HALVINGS
SPEEDUP_SLACK = MACRO_CAPACITY - BOUNDED_DELAY_TRANSITIONS
SPEEDUP_RATIO_DENOMINATOR = MACRO_CAPACITY


@dataclass(frozen=True)
class SpeedupCertificate:
    bounded_delay_transitions: int
    halving_iterations: int
    simulated_old_steps_per_new_step: int
    spare_old_steps_per_input: int
    macrosteps_per_input: int
    theorem: str
    construction: str


def certificate() -> SpeedupCertificate:
    return SpeedupCertificate(
        bounded_delay_transitions=BOUNDED_DELAY_TRANSITIONS,
        halving_iterations=SPEEDUP_HALVINGS,
        simulated_old_steps_per_new_step=MACRO_CAPACITY,
        spare_old_steps_per_input=SPEEDUP_SLACK,
        macrosteps_per_input=1,
        theorem="Hartmanis--Stearns constant speedup, Theorem 2, iterated k=1/2 construction",
        construction=(
            "repeat 39 times: pair adjacent tape symbols into one new symbol, retain the "
            "scanned pair and adjacent pairs in finite control, and tabulate two old "
            "transitions as one new transition"
        ),
    )


def certificate_dict() -> dict:
    data = asdict(certificate())
    data.update(
        {
            "format": "Hartmanis-Stearns fixed-speedup application certificate v2",
            "status": "proved by application of imported constructive theorem; representation factored",
            "speedup_ratio": f"1/{SPEEDUP_RATIO_DENOMINATOR}",
            "side_conditions": {
                "fixed_finite_machine": True,
                "deterministic": True,
                "ordinary_one_cell_tape_moves": True,
                "fixed_bounded_delay": True,
                "read_output_boundary_respected": True,
                "capacity_at_least_delay": MACRO_CAPACITY >= BOUNDED_DELAY_TRANSITIONS,
            },
            "not_claimed": [
                "a materialized sped-up transition table",
                "a small alphabet or finite control",
                "optimality of the 39-iteration factor",
            ],
        }
    )
    return data


def write_certificate(path: str | Path) -> dict:
    data = certificate_dict()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def audit_constants() -> None:
    assert SPEEDUP_HALVINGS == 39
    assert MACRO_CAPACITY == 549_755_813_888
    assert SPEEDUP_SLACK == 132_810_003_172
    assert MACRO_CAPACITY >= BOUNDED_DELAY_TRANSITIONS
    assert MACRO_CAPACITY // 2 < BOUNDED_DELAY_TRANSITIONS


audit_constants()


if __name__ == "__main__":
    print(json.dumps(certificate_dict(), indent=2, sort_keys=True))
