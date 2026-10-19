from itertools import product

from lemma32_t1 import (
    lemma32_t1_same_gaps,
    manacher_even,
    next_candidate_t1,
    recover_pair_t1,
    z_array,
)
from lemma33_t1 import lemma33_t1_discovered_gap, lemma33_t1_same_member
from sg_zero_ratio import sg_l0_member


def words(max_length: int):
    for n in range(max_length + 1):
        for symbols in product("01", repeat=n):
            yield "".join(symbols)


def literal_gaps(word: str) -> list[int]:
    return [d for d in range(1, len(word) + 1) if sg_l0_member(word, word, d)]


def test_z_array_examples() -> None:
    assert z_array("") == []
    assert z_array("aaaa") == [4, 3, 2, 1]
    assert z_array("abacaba") == [7, 0, 1, 0, 3, 0, 1]


def test_manacher_even_examples() -> None:
    radii = manacher_even("abba")
    assert radii[2] == 2
    assert manacher_even("aaaa") == [0, 1, 2, 1]


def test_lemma32_specialization_exhaustively() -> None:
    for word in words(12):
        assert lemma32_t1_same_gaps(word) == literal_gaps(word), word


def test_lemma33_is_first_candidate_at_ratio_exhaustively() -> None:
    for c in (6, 7, 8):
        for word in words(12):
            gaps = literal_gaps(word)
            expected = (
                bool(word)
                and len(word) % c == 0
                and bool(gaps)
                and gaps[0] == len(word) // c
            )
            assert lemma33_t1_same_member(word, c) == expected, (word, c, gaps)
            assert lemma33_t1_discovered_gap(word, c) == (
                len(word) // c if expected else None
            )


def test_linear_recover_and_local_match_literal_scans() -> None:
    from sg_zero_ratio import b3_pair, candidate_midpoint

    for old in words(10):
        old_b, old_bp = b3_pair(old)
        for symbol in "01":
            new = old + symbol
            direct_b, direct_bp = b3_pair(new)
            if not candidate_midpoint(new, old_b):
                assert recover_pair_t1(new, old_b) == (direct_b, direct_bp)
            if (
                not candidate_midpoint(new, old_b)
                and candidate_midpoint(new, old_bp)
            ):
                d = old_bp - old_b
                got = next_candidate_t1(new, old_bp, stop=old_bp + d)
                expected = direct_bp if direct_bp <= old_bp + d else None
                assert got == expected
