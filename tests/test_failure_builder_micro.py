from itertools import product

from fp_delta import delta_blocks, failure_positions
from fp_delta_micro import build_failure_delta_micro


def words(max_length: int):
    for length in range(1, max_length + 1):
        for symbols in product("01", repeat=length):
            yield "".join(symbols)


def test_micro_failure_builder_has_no_oracle_disagreement() -> None:
    for word in words(10):
        built = build_failure_delta_micro(word)
        assert list(built.failure) == failure_positions(word), word
        assert list(built.blocks) == delta_blocks(word), word


def test_total_delta_output_is_linear() -> None:
    for word in words(10):
        built = build_failure_delta_micro(word)
        assert sum(built.blocks) <= len(word)
        assert built.block_write_steps <= 2 * len(word) + 1
