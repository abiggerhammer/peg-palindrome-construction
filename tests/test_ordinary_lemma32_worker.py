from itertools import product

from lemma32_y_tape import next_candidate_y_tape_local, recover_pair_y_tape
from ordinary_lemma32_worker import (
    next_candidate_ordinary_local,
    recover_pair_ordinary,
)


def test_ordinary_recover_worker_matches_algorithm_y_reference():
    for length in range(1, 6):
        for bits in product('01', repeat=length):
            word = ''.join(bits)
            expected = recover_pair_y_tape(word, 0)
            actual = recover_pair_ordinary(word, 0)
            assert (actual.first, actual.second) == (expected.first, expected.second)
            assert actual.ordinary_steps > 0


def test_ordinary_local_worker_matches_bounded_algorithm_y_reference():
    for length in range(1, 6):
        for bits in product('01', repeat=length):
            word = ''.join(bits)
            for radius in range(1, length + 2):
                expected, _ = next_candidate_y_tape_local(word, 0, radius=radius)
                actual = next_candidate_ordinary_local(word, 0, radius=radius)
                assert actual.candidate == expected
                assert actual.window_length <= 4 * radius
