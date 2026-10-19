from itertools import product

from case14_predictability_bounds import (
    CASE1_BOUND,
    CASE4_BOUND,
    DISPATCHER_BOUND,
    OUTPUT_BOUND,
    availability_from_jump,
    case2_affine_bound,
    case2_linear_coefficient,
    case3_at_end_bound,
    case3_large_bound,
    case3_linear_coefficient,
    case3_small_bound,
    jump_from_availability,
)
from checkpoint_correctness import gap_set_from_borders
from sg_zero_ratio import (
    UpdateCase,
    b3_pair,
    candidate_midpoint,
    update_facts,
)


def _words(max_length):
    for n in range(max_length + 1):
        for bits in product("01", repeat=n):
            yield "".join(bits)


def test_public_case14_constants():
    assert DISPATCHER_BOUND == 1296
    assert OUTPUT_BOUND == 136
    assert CASE1_BOUND == 1433
    assert CASE4_BOUND == 1468
    assert case2_linear_coefficient() == 264841
    assert case3_linear_coefficient() == 891977


def test_affine_bounds_are_absorbed_by_linear_coefficients():
    for jump in range(1, 1000):
        assert case2_affine_bound(jump) <= case2_linear_coefficient() * jump
        assert case3_at_end_bound(jump) <= case3_linear_coefficient() * jump
        assert case3_large_bound(jump) <= case3_linear_coefficient() * jump
        assert case3_small_bound(jump) <= case3_linear_coefficient() * jump


def test_availability_is_exactly_twice_jump_minus_one():
    for word in _words(11):
        old_b, _ = b3_pair(word)
        old_deficit = 2 * old_b - len(word)
        for bit in "01":
            new = word + bit
            new_b, _ = b3_pair(new)
            new_deficit = 2 * new_b - len(new)
            jump = new_b - old_b
            availability = new_deficit - old_deficit
            assert availability == availability_from_jump(jump)
            assert jump_from_availability(availability) == jump


def test_case1_case2_case4_geometry():
    for word in _words(12):
        for bit in "01":
            facts = update_facts(word, bit)
            active = len(word) - facts.old_b
            jump = facts.jump
            if facts.case is UpdateCase.ONE_BOTH_SURVIVE:
                assert jump == 0
            elif facts.case is UpdateCase.TWO_BOTH_FAIL:
                assert facts.old_gap < jump
                assert active < 4 * jump
                assert active + 1 <= 4 * jump
            elif facts.case is UpdateCase.FOUR_FIRST_SURVIVES:
                assert jump == 0
                new_active = len(word) + 1 - facts.new_b
                new_gap = facts.new_bp - facts.new_b
                assert new_active < 5 * new_gap


def test_case3_window_and_forgetting_lemma_exhaustively():
    """Finite audit of the specialized page-140/141 argument.

    The mathematical proof is in CASES_1_4_PREDICTABILITY_PROOF_2026-07-25.md.
    This test independently checks the exact local checkpoint predicate and
    the final Fine--Wilf forgetting inequality on all short binary instances.
    """
    saw = {"at_end": False, "large": False, "small_found": False, "small_missing": False}
    for word in _words(13):
        for bit in "01":
            facts = update_facts(word, bit)
            if facts.case is not UpdateCase.THREE_SECOND_SURVIVES:
                continue
            new_word = word + bit
            d = facts.old_gap
            assert facts.jump == d
            new_b = facts.new_b
            active = len(word) - facts.old_b
            source_length = len(new_word) - new_b

            if new_b == len(new_word):
                saw["at_end"] = True
                continue

            if 16 * d > active:
                saw["large"] = True
                assert source_length <= 15 * d
                continue

            # Small-gap branch: at least 4d source symbols are available.
            assert source_length >= 15 * d + 1
            local = new_word[new_b : new_b + 4 * d]
            assert len(local) == 4 * d
            local_gaps = set(gap_set_from_borders(local))

            full_small = []
            for gap in range(1, d + 1):
                full = candidate_midpoint(new_word, new_b + gap)
                local_answer = gap in local_gaps
                assert full == local_answer, (word, bit, d, gap, local)
                if full:
                    full_small.append(gap)

            new_gap = facts.new_bp - facts.new_b
            if full_small:
                saw["small_found"] = True
                assert new_gap == min(full_small)
                assert new_gap <= d
            else:
                saw["small_missing"] = True
                assert new_gap > d
                assert source_length < 4 * new_gap

    assert saw["at_end"] and saw["large"], saw

    # A known production regression reaches the genuine small-gap/found path.
    word = "0011" * 16 + "00"
    bit = "1"
    facts = update_facts(word, bit)
    assert facts.case is UpdateCase.THREE_SECOND_SURVIVES
    d = facts.old_gap
    assert 16 * d <= len(word) - facts.old_b
    new_word = word + bit
    local = new_word[facts.new_b : facts.new_b + 4 * d]
    local_gaps = set(gap_set_from_borders(local))
    assert facts.new_bp - facts.new_b == min(g for g in local_gaps if g <= d)
