from sg_zero_ratio import (
    UpdateCase,
    b3_pair,
    candidate_midpoint,
    classify_update,
    candidates_after_anchor_via_lemma31,
    exhaustive_audit,
    next_candidate_via_lemma31,
    recover_pair_via_lemma31,
    is_even_palindrome,
)


def test_midpoint_acceptance_matches_even_palindrome() -> None:
    samples = ["", "00", "0110", "0101", "011110", "101101"]
    for word in samples:
        b, _ = b3_pair(word)
        assert (2 * b == len(word)) == is_even_palindrome(word)


def test_candidate_examples() -> None:
    # "0110" is already xx^R with x="01".
    assert candidate_midpoint("0110", 2)
    # It can also be extended with a longer first half.
    assert candidate_midpoint("0110", 4)
    # Total length 6 with midpoint 3 would require suffix "10" to mirror "11".
    assert not candidate_midpoint("0110", 3)


def test_case_examples() -> None:
    # Starting from "0", appending the same symbol preserves midpoint 1.
    assert classify_update("0", "0") in {
        UpdateCase.ONE_BOTH_SURVIVE,
        UpdateCase.FOUR_FIRST_SURVIVES,
    }
    # Appending a different symbol destroys midpoint 1.
    assert classify_update("0", "1") in {
        UpdateCase.TWO_BOTH_FAIL,
        UpdateCase.THREE_SECOND_SURVIVES,
    }


def test_exhaustive_audit() -> None:
    exhaustive_audit(max_length=9)


def test_lemma31_recovery_matches_direct_candidates() -> None:
    from itertools import product

    for old_length in range(9):
        for symbols in product("01", repeat=old_length):
            old = "".join(symbols)
            old_b, old_bp = b3_pair(old)
            for symbol in "01":
                new = old + symbol
                direct_b, direct_bp = b3_pair(new)

                # RECOVER is used only when old B fails.
                if not candidate_midpoint(new, old_b):
                    assert recover_pair_via_lemma31(new, old_b) == (
                        direct_b,
                        direct_bp,
                    )

                # If old B' survives and becomes the new B, LOCAL searches
                # only the next old gap.
                if (
                    not candidate_midpoint(new, old_b)
                    and candidate_midpoint(new, old_bp)
                ):
                    d = old_bp - old_b
                    local = next_candidate_via_lemma31(
                        new, old_bp, stop=old_bp + d
                    )
                    expected = direct_bp if direct_bp <= old_bp + d else None
                    assert local == expected
