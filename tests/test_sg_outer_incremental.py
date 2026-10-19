from itertools import product

from sg_outer_incremental import OrdinarySGOuterIncremental
from sg_zero_ratio import UpdateCase


def test_incremental_outer_exhaustive_all_six_cases_short():
    seen = set()
    for length in range(0, 8):
        for bits in product('01', repeat=length):
            word = ''.join(bits)
            machine = OrdinarySGOuterIncremental(audit=True, background_work_budget=200000)
            outputs = []
            for ch in word:
                record = machine.append(ch)
                seen.add(record.case)
                outputs.append(record.output)
            assert outputs == [
                prefix == prefix[::-1] and len(prefix) % 2 == 0
                for prefix in (word[:i] for i in range(1, len(word)+1))
            ]
    assert seen == set(UpdateCase)


def test_incremental_outer_long_selected_words():
    for word in (
        '01100110011001100110011001100110',
        '01000100101101001010010010110100',
        '0' * 32,
        '01' * 16,
    ):
        machine = OrdinarySGOuterIncremental(audit=True, background_work_budget=200000)
        records = [machine.append(ch) for ch in word]
        assert records[-1].output == (word == word[::-1] and len(word) % 2 == 0)
