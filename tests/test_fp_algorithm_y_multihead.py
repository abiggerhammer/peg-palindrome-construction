from itertools import product

from fp_algorithm_y_multihead import MACHINE, run_algorithm_y
from fp_delta import delta_blocks, failure_positions


def test_algorithm_y_table_is_finite() -> None:
    assert len(MACHINE.states) < 32
    assert 0 < len(MACHINE.delta) < 100_000


def test_algorithm_y_matches_reference_exhaustively() -> None:
    for n in range(1, 11):
        for bits in product("01", repeat=n):
            pattern = "".join(bits)
            result = run_algorithm_y(pattern)
            assert result.failure == tuple(failure_positions(pattern))
            assert result.blocks == tuple(delta_blocks(pattern))


def test_algorithm_y_handles_reserved_separator_as_ordinary_character() -> None:
    result = run_algorithm_y("01@10@01")
    assert result.failure == tuple(failure_positions("01@10@01"))


def test_algorithm_y_runs_in_linear_steps_on_representative_long_inputs() -> None:
    for pattern in (
        "0" * 500,
        "01" * 250,
        ("010000" * 84)[:500],
        ("01101001" * 63)[:500],
    ):
        result = run_algorithm_y(pattern)
        assert result.steps <= 80 * len(pattern) + 32
