from itertools import product

from lemma32_failure import (
    border_lengths,
    lemma32_t1_same_gaps_failure,
    palindromic_prefix_lengths,
    palindromic_suffix_lengths,
    period_lengths,
)
from lemma32_t1 import lemma32_t1_same_gaps


def words(max_length: int):
    for length in range(max_length + 1):
        for symbols in product("01", repeat=length):
            yield "".join(symbols)


def test_border_chain_examples() -> None:
    assert border_lengths("ababa") == [3, 1]
    assert period_lengths("ababa") == {2, 4, 5}
    assert palindromic_prefix_lengths("abba01") == {1, 4}
    assert palindromic_suffix_lengths("01abba") == {1, 4}


def test_failure_chain_lemma32_matches_z_manacher_exhaustively() -> None:
    for word in words(13):
        assert lemma32_t1_same_gaps_failure(word) == lemma32_t1_same_gaps(word), word
