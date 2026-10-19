"""Regenerate the corrected SG source transition-family inventory.

This intentionally counts the streamed transition families without writing a
multi-million-row monolithic table.  It must be rerun after any component or
controller lifecycle change; discrepancies are never repaired by hand.
"""
from __future__ import annotations

import json
from pathlib import Path

from background_bounds import (
    BACKGROUND_UNIT_GLOBAL_BOUND,
    case5_primitive_per_input_bound,
    case6_predictability_coefficient,
)
from build_outer_service_fabric import CONTROLLER_RESERVE, build_fabric
from case14_predictability_bounds import (
    CASE1_BOUND, CASE4_BOUND, case2_linear_coefficient, case3_linear_coefficient,
)
from construction_constants import (
    background_clock_shape,
    background_steps_per_input,
    scheduler_predictability_constant,
)
from scheduler_parameters import (
    GALIL_SCHEDULER_PERIOD,
    SOURCE_AFFINE_C,
    SOURCE_AFFINE_D,
)
from sg_outer_constant_cases import (
    SOURCE_DONE_0,
    SOURCE_DONE_1,
    build_constant_case_rows,
)
from sg_outer_dispatcher_table import READ0, READ1, build_dispatcher_rows
from sg_outer_remaining_cases import build_remaining_case_rows


def row_extent(row):
    states = (row.state, row.action.next_state)
    tapes = [t for t, _ in row.reads]
    tapes += [t for t, _ in row.action.writes]
    tapes += [t for t, _ in row.action.moves]
    return max(states), max(tapes, default=-1)


def main(path: str | Path = "generated/sg_source_row_manifest.json") -> dict:
    fabric = build_fabric()
    dispatcher = build_dispatcher_rows(fabric)
    constant = build_constant_case_rows(fabric)
    remaining = build_remaining_case_rows(
        fabric, background_budget=background_steps_per_input()
    )

    max_controller_state = -1
    max_global_state = -1
    max_tape = -1

    def count_rows(rows):
        nonlocal max_controller_state, max_global_state, max_tape
        count = 0
        for item in rows:
            s, t = row_extent(item)
            max_global_state = max(max_global_state, s)
            for q in (item.state, item.action.next_state):
                if q < CONTROLLER_RESERVE:
                    max_controller_state = max(max_controller_state, q)
            max_tape = max(max_tape, t)
            count += 1
        return count

    dispatcher_rows = count_rows(dispatcher.rows)
    constant_rows = count_rows(constant.rows)
    remaining_rows = count_rows(remaining.iter_rows(fabric))
    controller_rows = dispatcher_rows + constant_rows + remaining_rows

    # Iterating controller rows registers every used continuation, so the
    # service-row total must be read only now.
    summary = fabric.summary(controller_rows=controller_rows)
    service_rows = summary["service_rows"]
    data = {
        "format": "complete SG source row manifest v2",
        "status": (
            "transition families rebuilt after producer-paid cleanup, CheckpointCorrect, "
            "all six primitive bounds, and the global predictability theorem; compact "
            "scheduler parameters proved but physical scheduler excluded"
        ),
        "global_tapes": fabric.tape_count,
        "global_states": fabric.state_count_without_continuations,
        "controller_state_reserve": CONTROLLER_RESERVE,
        "background_steps_per_input": background_steps_per_input(),
        "background_required_units": background_steps_per_input(),
        "background_clock_outer": background_clock_shape()[0],
        "background_clock_radix": background_clock_shape()[1],
        "background_effective_units": background_clock_shape()[2],
        "background_unit_global_bound": BACKGROUND_UNIT_GLOBAL_BOUND,
        "case1_primitive_bound": CASE1_BOUND,
        "case2_predictability_coefficient": case2_linear_coefficient(),
        "case3_predictability_coefficient": case3_linear_coefficient(),
        "case4_primitive_bound": CASE4_BOUND,
        "case5_primitive_per_input_bound": case5_primitive_per_input_bound(),
        "case6_predictability_coefficient": case6_predictability_coefficient(),
        "source_predictability_affine_C": SOURCE_AFFINE_C,
        "source_predictability_affine_D": SOURCE_AFFINE_D,
        "galil_predictability_c": scheduler_predictability_constant(),
        "galil_scheduler_source_step_period": GALIL_SCHEDULER_PERIOD,
        "service_rows": service_rows,
        "dispatcher_rows": dispatcher_rows,
        "constant_case_rows": constant_rows,
        "remaining_case_rows": remaining_rows,
        "controller_rows": controller_rows,
        "total_rows": service_rows + controller_rows,
        "continuations": len(fabric._continuations),
        "source_entry_states": {"0": READ0, "1": READ1},
        "source_done_states": {"0": SOURCE_DONE_0, "1": SOURCE_DONE_1},
        "max_controller_row_state": max_controller_state,
        "max_global_row_state": max_global_state,
        "max_referenced_tape": max_tape,
        "checkpoint_result_ready_state": fabric.layout("CHECKPOINT").adapter.result_ready_state_id,
        "checkpoint_clean_ready_state": fabric.layout("CHECKPOINT").adapter.clean_ready_state_id,
    }
    if max_controller_state >= CONTROLLER_RESERVE:
        raise AssertionError((max_controller_state, CONTROLLER_RESERVE))
    if max_global_state >= fabric.state_count_without_continuations:
        raise AssertionError((max_global_state, fabric.state_count_without_continuations))
    if max_tape >= fabric.tape_count:
        raise AssertionError((max_tape, fabric.tape_count))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(json.dumps(data, indent=2, sort_keys=True))
    return data


if __name__ == "__main__":
    main()
