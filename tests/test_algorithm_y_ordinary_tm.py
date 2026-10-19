from itertools import product

from algorithm_y_ordinary_tm import (
    machine, maximum_microsteps_per_source_step, run_algorithm_y_ordinary,
)
from algorithm_y_strict_storage import run_algorithm_y_strict
from fp_algorithm_y_multihead import run_algorithm_y


def test_ordinary_algorithm_y_table_shape_and_bound():
    m = machine()
    assert m.tape_count == 17
    assert len(m.states) == 124_926
    assert len(m.rows) == 198_751
    assert maximum_microsteps_per_source_step(m) == 103


def test_ordinary_algorithm_y_exhaustive_binary_through_8():
    for n in range(1, 9):
        for bits in product("01", repeat=n):
            pattern = "".join(bits)
            expected = run_algorithm_y(pattern)
            strict = run_algorithm_y_strict(pattern)
            actual = run_algorithm_y_ordinary(pattern)
            assert actual.blocks == expected.blocks == strict.blocks
            assert actual.source_steps == expected.steps
            assert actual.microsteps <= 103 * max(1, actual.source_steps)


def test_ordinary_algorithm_y_separator_patterns():
    for pattern in ("0@0", "01@10", "0110@0110", "010@010"):
        expected = run_algorithm_y(pattern)
        actual = run_algorithm_y_ordinary(pattern)
        assert actual.blocks == expected.blocks
        assert actual.source_steps == expected.steps
