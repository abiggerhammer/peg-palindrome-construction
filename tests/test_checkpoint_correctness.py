from itertools import product

import checkpoint_ordinary_tm as cp
import checkpoint_reusable_tm as reusable
from algorithm_y_ordinary_tm import maximum_microsteps_per_source_step
from checkpoint_correctness import (
    checkpoint_spec,
    gap_set_from_borders,
    ratio_heads_after_gap,
    ratio_marks_candidate,
)
from lemma32_t1 import lemma32_t1_same_gaps


def test_failure_characterization_exhaustive_binary_through_13():
    for n in range(1, 14):
        for bits in product("01", repeat=n):
            word = "".join(bits)
            assert gap_set_from_borders(word) == tuple(lemma32_t1_same_gaps(word)), word


def test_ratio_loop_formula_exhaustive_grid():
    for n in range(1, 513):
        for d in range(1, n + 2):
            left, right = ratio_heads_after_gap(n, d)
            assert left == min(15 * d, n + 1)
            assert right == min(16 * d, n + 1)
            assert ratio_marks_candidate(n, d) == (15 * d <= n < 16 * d)


def test_ordinary_checkpoint_against_independent_spec_through_7():
    for n in range(1, 8):
        for bits in product("01", repeat=n):
            word = "".join(bits)
            actual = cp.run_checkpoint_ordinary(word)
            expected = checkpoint_spec(word)
            assert actual.gaps == expected.gaps, word
            assert actual.candidate == expected.candidate, word


def test_reusable_lifts_every_one_shot_nonterminal_row_verbatim():
    states, _ = cp.enumerate_reachable()
    for state in states:
        if state in (cp.DONE, cp.ERROR):
            continue
        assert reusable.outgoing_rows(state) == cp.outgoing_rows(state), state


def test_algorithm_y_microprogram_is_acyclic_between_source_boundaries():
    assert maximum_microsteps_per_source_step() == 103
