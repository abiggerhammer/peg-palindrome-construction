from itertools import product

from lemma32_micro import next_candidate_micro, recover_pair_micro
from lemma32_y_tape import next_candidate_y_tape, recover_pair_y_tape


def test_y_tape_recover_and_local_match_micro_reference():
    for n in range(1, 7):
        for chars in product("01", repeat=n):
            word = "".join(chars)
            for anchor in range(n):
                result = recover_pair_y_tape(word, anchor)
                assert (result.first, result.second) == recover_pair_micro(word, anchor)
                for width in range(1, n - anchor + 2):
                    stop = anchor + width
                    found, _ = next_candidate_y_tape(word, anchor, stop=stop)
                    assert found == next_candidate_micro(word, anchor, stop=stop)


def test_local_y_tape_uses_only_four_radius_prefix():
    from lemma32_y_tape import next_candidate_y_tape_local
    from sg_zero_ratio import b3_pair, survives_append

    for n in range(13):
        for chars in product("01", repeat=n):
            before = "".join(chars)
            b, bp = b3_pair(before)
            for symbol in "01":
                if not survives_append(before, b, symbol) and survives_append(before, bp, symbol):
                    d = bp - b
                    if d <= (len(before) - b) / 16:
                        after = before + symbol
                        found, _ = next_candidate_y_tape_local(
                            after, bp, radius=d
                        )
                        assert found == next_candidate_micro(
                            after, bp, stop=bp + d
                        )
