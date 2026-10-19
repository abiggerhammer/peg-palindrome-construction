from itertools import product

from predictability_scheduler import (
    compact_scheduler_spec,
    countdown_step,
    fixed_countdown_rows,
    schedule_trace,
    schedule_trace_via_compact,
    scheduler_control_table,
)
from regenerate_galil_scheduler import main as regenerate_scheduler
from scheduler_parameters import (
    CASE1_PRIMITIVE_BOUND,
    CASE2_J_COEFFICIENT,
    CASE3_J_COEFFICIENT,
    CASE4_PRIMITIVE_BOUND,
    CASE5_PRIMITIVE_BOUND,
    CASE6_J_COEFFICIENT,
    GALIL_PREDICTABILITY_C,
    GALIL_SCHEDULER_PERIOD,
    SOURCE_AFFINE_C,
    SOURCE_AFFINE_D,
    output_predictor,
)


def bits(value: int, width: int) -> tuple[int, ...]:
    return tuple((value >> i) & 1 for i in range(width))


def test_six_case_affine_and_galil_constants():
    assert SOURCE_AFFINE_C == 947_906
    assert SOURCE_AFFINE_D == 1_782_767_609
    assert CASE1_PRIMITIVE_BOUND == 1_433
    assert CASE2_J_COEFFICIENT == 264_841
    assert CASE3_J_COEFFICIENT == 891_977
    assert CASE4_PRIMITIVE_BOUND == 1_468
    assert CASE5_PRIMITIVE_BOUND == 1_781_819_703
    assert CASE6_J_COEFFICIENT == 1_895_812
    assert GALIL_PREDICTABILITY_C == CASE5_PRIMITIVE_BOUND
    assert GALIL_SCHEDULER_PERIOD == 3_563_639_406


def test_output_predictor_delta_bounds_exhaustively():
    for old_distance in range(40):
        for new_distance in range(max(0, old_distance - 1), 80):
            availability = new_distance - old_distance
            delta = output_predictor(new_distance) - output_predictor(old_distance)
            assert availability >= -1
            assert delta >= -1
            assert delta >= availability - 1


def test_galil_condition_arithmetic_for_all_case_shapes():
    c = GALIL_PREDICTABILITY_C

    # j=0 cases: Delta k >= -1 and work <= c.
    for work in (CASE1_PRIMITIVE_BOUND, CASE4_PRIMITIVE_BOUND, CASE5_PRIMITIVE_BOUND):
        assert work <= c
        assert -1 >= work / c - 2

    # j>=1 cases: Delta k >= 2j-2 and the linear coefficients fit.
    for coefficient in (CASE2_J_COEFFICIENT, CASE3_J_COEFFICIENT, CASE6_J_COEFFICIENT):
        assert coefficient <= 2 * c
        for jump in (1, 2, 17, 10_000):
            work = coefficient * jump
            delta_k = 2 * jump - 2
            assert delta_k >= work / c - 2


def test_compact_countdown_rows_partition_and_decrement_small_periods():
    for period in range(1, 65):
        rows = fixed_countdown_rows(period)
        width = period.bit_length()
        assert len(rows) == 2 * width - 1
        for value in range(1, 1 << width):
            updated, tick = countdown_step(bits(value, width), rows)
            if value == 1:
                assert tick
                assert updated == bits(period, width)
            else:
                assert not tick
                assert updated == bits(value - 1, width)


def test_compact_scheduler_matches_reference_exhaustively_for_small_c():
    for c in (1, 2, 3):
        for n in range(1, 5):
            for work in product(range(1, 7), repeat=n):
                for outputs in product((0, 1), repeat=n):
                    try:
                        reference = schedule_trace(work, outputs, c)
                        compact = schedule_trace_via_compact(work, outputs, c)
                    except AssertionError:
                        continue
                    assert compact == reference


def test_production_compact_spec_is_small_and_exact():
    spec = compact_scheduler_spec(GALIL_PREDICTABILITY_C)
    assert spec["source_step_period"] == GALIL_SCHEDULER_PERIOD
    assert spec["clock"]["width_bits"] == 32
    assert spec["clock"]["row_count"] == 63
    assert spec["clock"]["target_binary"] == "11010100011010001101001001101110"
    assert spec["materialized_unrolled_rows"] == 21_381_836_436


def test_production_unrolled_table_fails_closed():
    try:
        scheduler_control_table(GALIL_PREDICTABILITY_C)
    except ValueError as exc:
        assert "compact_scheduler_spec" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("production controller must not be unrolled")


def test_regenerated_scheduler_artifact_is_deterministic(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    regenerate_scheduler(first)
    regenerate_scheduler(second)
    assert first.read_bytes() == second.read_bytes()
