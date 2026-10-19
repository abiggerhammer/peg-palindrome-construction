from background_bounds import (
    BACKGROUND_UNIT_BODY_BOUND,
    BACKGROUND_UNIT_GLOBAL_BOUND,
    BACKGROUND_UNIT_LEDGER,
    BACKGROUND_CYCLE_OUTSIDE_LINEAR,
    BACKGROUND_CYCLE_OUTSIDE_CONSTANT,
    CASE5_UNCLOCKED_PREFIX_BOUND,
    background_catchup_inequality,
    background_cycle_bound,
    background_window_capacity,
    case5_primitive_per_input_bound,
    case6_predictability_coefficient,
    case6_two_job_bound,
    checkpoint_window_symbols,
    first_checkpoint_beats_case5_runway,
    first_checkpoint_deadline_inputs,
    initial_setup_input_bound,
    lazy_setup_logical_bound,
)
from build_outer_service_fabric import CONTROLLER_RESERVE, build_fabric
from construction_constants import (
    BACKGROUND_CYCLE_CONSTANT,
    BACKGROUND_CYCLE_LINEAR,
    background_clock_shape,
    background_steps_per_input,
    checkpoint_window_epsilon,
    checkpoint_window_symbols as exact_checkpoint_window_symbols,
)
from sg_outer_remaining_cases import build_remaining_case_rows
from history_zipper_ordinary_tm import maximum_microsteps_per_command


def test_background_unit_ledger_has_proved_maximum():
    costs = {item.route: item.primitive_transitions_to_work_dec for item in BACKGROUND_UNIT_LEDGER}
    assert costs["candidate_build_preposition"] == 506
    assert max(costs.values()) == BACKGROUND_UNIT_BODY_BOUND == 506
    assert BACKGROUND_UNIT_GLOBAL_BOUND == 512


def test_component_costs_and_case5_install_are_mechanically_tied():
    maxima = maximum_microsteps_per_command()
    assert maxima["APPEND0"] == maxima["APPEND1"] == 49
    assert maxima["LEFT"] == 9
    assert maxima["RIGHT"] == 55
    # Exact longest unclocked FOLLOW-success route is 549; retain margin 11.
    assert CASE5_UNCLOCKED_PREFIX_BOUND == 560
    assert BACKGROUND_CYCLE_OUTSIDE_LINEAR == 20
    assert BACKGROUND_CYCLE_OUTSIDE_CONSTANT == 32

    fabric = build_fabric()
    remaining = build_remaining_case_rows(fabric, background_budget=8)
    names = set(remaining.state_names.values())
    assert "C5_BUILD_MOVE_BP" in names
    assert "C5_RETURN_CANDIDATE" in names
    assert not any(name.endswith("INSTALL_LOOP") for name in names)


def test_factored_clock_supplies_proved_budget_without_state_explosion():
    required = background_steps_per_input()
    outer, radix, effective = background_clock_shape()
    assert outer * radix == effective
    assert effective >= required
    assert outer + radix < 10_000
    assert case5_primitive_per_input_bound() > effective

    fabric = build_fabric()
    remaining = build_remaining_case_rows(fabric)
    assert max(remaining.state_names) < CONTROLLER_RESERVE


def test_background_window_inequality_exhaustive_and_symbolic_boundary():
    epsilon = checkpoint_window_epsilon()
    budget = background_clock_shape()[2]
    for n in range(1, 100_001):
        h = exact_checkpoint_window_symbols(n)
        assert h == checkpoint_window_symbols(n)
        # Floating evaluation is diagnostic only; exact arithmetic is the source of truth.
        assert abs(h - max(1, int(epsilon * n // 1))) <= 1
        assert budget * h == background_window_capacity(n)
        assert background_catchup_inequality(n)
        assert budget * h >= BACKGROUND_CYCLE_LINEAR * n + BACKGROUND_CYCLE_CONSTANT


def test_lazy_setup_fits_within_active_length_inputs():
    budget = background_clock_shape()[2]
    for active in range(1, 100_001):
        assert lazy_setup_logical_bound(active) <= budget * active


def test_initial_background_catches_up_before_case5_runway():
    for active in range(1, 100_001):
        setup = initial_setup_input_bound(active)
        assert 1 <= setup <= active
        assert first_checkpoint_deadline_inputs(active) >= setup + 1
        assert first_checkpoint_beats_case5_runway(active)


def test_case6_two_job_bound_is_linear_in_jump():
    coefficient = case6_predictability_coefficient()
    assert coefficient == 1_895_812
    for jump in range(1, 10_001):
        assert case6_two_job_bound(jump) <= coefficient * jump
