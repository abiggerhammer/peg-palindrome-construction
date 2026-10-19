from itertools import product

from algorithm_y_strict_storage import run_algorithm_y_strict
from fp_algorithm_y_multihead import run_algorithm_y


def test_strict_storage_algorithm_y_exhaustive():
    for n in range(1, 11):
        for bits in product("01", repeat=n):
            pattern = "".join(bits)
            expected = run_algorithm_y(pattern)
            actual = run_algorithm_y_strict(pattern)
            assert actual.blocks == expected.blocks
            assert actual.source_steps == expected.steps
            # At most one append and one reader move occur in a source step.
            assert actual.max_storage_primitives <= 40


def test_strict_storage_separator_patterns():
    for pattern in ("0@0", "01@10", "0110@0110", "010@010"):
        expected = run_algorithm_y(pattern)
        actual = run_algorithm_y_strict(pattern)
        assert actual.blocks == expected.blocks
        assert actual.source_steps == expected.steps
