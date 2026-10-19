from itertools import product

from pattern_prepare_multihead import run_prepare
from pattern_prepare_ordinary_tm import MACHINE, run_prepare_ordinary


def test_prepare_ordinary_table_shape():
    assert MACHINE.tape_count == 6
    assert len(MACHINE.states) == 6
    assert len(MACHINE.rows) == 11


def test_prepare_ordinary_exhaustive_through_8():
    for n in range(1, 9):
        for bits in product("01", repeat=n):
            word = "".join(bits)
            expected = run_prepare(word)
            actual = run_prepare_ordinary(word)
            assert (actual.plain, actual.prefix, actual.suffix) == (
                expected.plain, expected.prefix, expected.suffix
            )
            assert actual.steps == expected.steps
