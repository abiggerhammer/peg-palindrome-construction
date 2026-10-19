from itertools import product

from algorithm_y_append_read import run_algorithm_y_append_read
from fp_algorithm_y_multihead import run_algorithm_y


def test_append_read_algorithm_y_matches_multihead_reference():
    alphabet = "01"
    for n in range(1, 10):
        for symbols in product(alphabet, repeat=n):
            pattern = "".join(symbols)
            expected = run_algorithm_y(pattern)
            actual = run_algorithm_y_append_read(pattern)
            assert actual.blocks == expected.blocks
            assert actual.source_steps == expected.steps
            assert actual.maximum_queue_rotation_steps <= 4


def test_append_read_algorithm_y_with_separator_patterns():
    for pattern in ("0@0", "01@10", "0110@0110", "010@010"):
        expected = run_algorithm_y(pattern)
        actual = run_algorithm_y_append_read(pattern)
        assert actual.blocks == expected.blocks
        assert actual.source_steps == expected.steps
