from itertools import product

from lemma32_micro import (
    lemma32_t1_same_gaps_micro,
    lemma33_discovered_gap_micro,
    next_candidate_micro,
    recover_pair_micro,
)
from lemma32_t1 import lemma32_t1_same_gaps, next_candidate_t1, recover_pair_t1
from lemma33_t1 import lemma33_t1_discovered_gap


def words(max_length: int):
    for length in range(max_length + 1):
        for symbols in product("01", repeat=length):
            yield "".join(symbols)


def test_micro_lemma32_matches_independent_implementation() -> None:
    for word in words(9):
        result = lemma32_t1_same_gaps_micro(word)
        assert list(result.gaps) == lemma32_t1_same_gaps(word), word
        if word:
            assert result.total_steps > 0


def test_micro_recover_and_local_queries() -> None:
    for word in words(8):
        for anchor in range(len(word) + 1):
            if anchor < len(word):
                assert recover_pair_micro(word, anchor) == recover_pair_t1(word, anchor)
            for stop in (None, anchor + 1, len(word) + 1):
                assert next_candidate_micro(word, anchor, stop=stop) == next_candidate_t1(
                    word, anchor, stop=stop
                )


def test_micro_lemma33_matches_reference() -> None:
    for c in (6, 7, 8):
        for word in words(9):
            assert lemma33_discovered_gap_micro(word, c) == lemma33_t1_discovered_gap(
                word, c
            )
