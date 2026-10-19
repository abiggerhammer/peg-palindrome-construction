from itertools import product

from pattern_prepare_multihead import MACHINE, run_prepare


def test_pattern_preparer_is_finite_and_explicit():
    assert len(MACHINE.states) == 6
    assert len(MACHINE.delta) > 0


def test_pattern_preparer_exhaustive():
    for n in range(1, 11):
        for chars in product("01", repeat=n):
            word = "".join(chars)
            result = run_prepare(word)
            assert result.plain == word
            assert result.prefix == word + "@" + word[::-1]
            assert result.suffix == word[::-1] + "@" + word
            assert result.steps == 3 * n + 5
