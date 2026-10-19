"""Machine-readable inventory of the factored palindrome construction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from construction_constants import (
    CHECKPOINT_STEPS_PER_SYMBOL,
    SG_RATIO_C,
    background_steps_per_input,
    scheduler_predictability_constant,
)
from fp_algorithm_y_multihead import MACHINE as ALGORITHM_Y
from fp_delta_micro import MACHINE as DELTA_PRIMITIVE
from lemma33_controller import persistent_control_table
from history_zipper_ordinary_tm import machine as history_zipper_machine
from checkpoint_reusable_tm import enumerate_reachable as reusable_checkpoint_reachable
from pattern_prepare_multihead import MACHINE as PATTERN_PREPARE
from predictability_scheduler import compact_scheduler_spec
from scheduled_source_composition import certificate as composition_certificate
from constant_speedup import certificate as speedup_certificate
from sg_controller import sg_control_table


@dataclass(frozen=True)
class Component:
    name: str
    model: str
    states: int
    transitions: int
    heads: int | None = None
    tapes: int | None = None


def component_inventory(*, materialize_scheduler: bool = False) -> list[Component]:
    del materialize_scheduler  # the proved production clock is never unrolled
    scheduler_c = scheduler_predictability_constant(SG_RATIO_C)
    scheduler = compact_scheduler_spec(scheduler_c)
    history = history_zipper_machine()
    checkpoint_states, checkpoint_rows = reusable_checkpoint_reachable()
    return [
        Component(
            "history_append_read_zipper",
            "one-head-per-tape sparse ordinary TM",
            len(history.states),
            len(history.rows),
            heads=history.tape_count,
            tapes=history.tape_count,
        ),
        Component(
            "reusable_checkpoint",
            "one-head-per-tape sparse ordinary TM",
            len(checkpoint_states),
            checkpoint_rows,
            heads=64,
            tapes=64,
        ),
        Component(
            "registered_complete_sg_source_fabric",
            "225-tape sparse ordinary TM source with all six cases complete",
            1_562_426,
            6_502_172,
            heads=225,
            tapes=225,
        ),
        Component(
            "fischer_paterson_delta_primitive",
            "one-head-per-tape flat TM",
            len(DELTA_PRIMITIVE.states),
            len(DELTA_PRIMITIVE.delta),
            heads=DELTA_PRIMITIVE.tape_count,
            tapes=DELTA_PRIMITIVE.tape_count,
        ),
        Component(
            "three_pattern_prepare",
            "flat multihead TM",
            len(PATTERN_PREPARE.states),
            len(PATTERN_PREPARE.delta),
            heads=len(PATTERN_PREPARE.head_to_tape),
            tapes=len(PATTERN_PREPARE.tape_alphabets),
        ),
        Component(
            "fischer_paterson_algorithm_y",
            "flat multihead TM",
            len(ALGORITHM_Y.states),
            len(ALGORITHM_Y.delta),
            heads=len(ALGORITHM_Y.head_to_tape),
            tapes=len(ALGORITHM_Y.tape_alphabets),
        ),
        Component(
            "sg_six_case_controller",
            "finite controller",
            1,
            len(sg_control_table()),
        ),
        Component(
            "persistent_lemma33_controller",
            "finite controller",
            6,
            len(persistent_control_table()),
        ),
        Component(
            "scheduled_sg_bounded_delay_machine",
            "factored ordinary one-head-per-tape FAST/SLOW composition",
            composition_certificate().scheduled_states,
            composition_certificate().scheduled_total_rows,
            heads=composition_certificate().scheduled_work_tapes,
            tapes=composition_certificate().scheduled_work_tapes,
        ),
    ]


def build_spec() -> dict:
    scheduler_c = scheduler_predictability_constant(SG_RATIO_C)
    return {
        "language": "{w w^R : w in {0,1}*}",
        "source_ratio_c": SG_RATIO_C,
        "checkpoint_steps_per_frozen_symbol": CHECKPOINT_STEPS_PER_SYMBOL,
        "background_steps_per_input": background_steps_per_input(SG_RATIO_C),
        "scheduler_predictability_constant": scheduler_c,
        "scheduler_source_step_period": 2 * scheduler_c,
        "scheduler_clock_width_bits": compact_scheduler_spec(scheduler_c)["clock"]["width_bits"],
        "scheduler_compact_clock_rows": compact_scheduler_spec(scheduler_c)["clock"]["row_count"],
        "scheduled_bounded_delay": composition_certificate().bounded_delay_transitions,
        "scheduled_work_tapes": composition_certificate().scheduled_work_tapes,
        "scheduled_states": composition_certificate().scheduled_states,
        "scheduled_rows": composition_certificate().scheduled_total_rows,
        "speedup_halving_iterations": speedup_certificate().halving_iterations,
        "speedup_macro_capacity": speedup_certificate().simulated_old_steps_per_new_step,
        "components": [asdict(item) for item in component_inventory()],
        "composition": [
            "registered sum-composition links nine history zippers, one reusable checkpoint, and twelve unary counters without a Cartesian state product",
            "literal outer dispatcher appends the input, advances midpoint/left cursors, updates signed k, and selects all six SG cases",
            "all six SG cases are complete through SOURCE_DONE_0/1 with producer-paid cleanup and proved primitive predictability bounds",
            "the proved Galil fast/slow parameters are represented by a compact 32-bit fixed countdown rather than 21 billion unrolled clock rows",
            "the source and scheduler are composed in an 8,305,403-row factored ordinary machine with bounded delay 416,945,810,716",
            "39 iterations of the constructive Hartmanis--Stearns halving transformation yield conventional real time",
            "the remaining PEG step is a symbolic compiler for the factored speedup representation",
        ],
        "operational_oracles": False,
        "audit_oracles_available": True,
    }


def export_spec(path: str | Path = "generated/palindrome_machine_spec.json") -> None:
    Path(path).write_text(json.dumps(build_spec(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    export_spec()
