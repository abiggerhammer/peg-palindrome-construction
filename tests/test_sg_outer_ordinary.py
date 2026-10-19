from itertools import product

from sg_outer_ordinary import OrdinarySGOuter


def test_outer_cursor_product_exhaustive_short_binary_words():
    for length in range(0, 7):
        for bits in product('01', repeat=length):
            machine = OrdinarySGOuter(audit=True, background_work_budget=200000)
            word = ''.join(bits)
            outputs = [machine.append(ch).output for ch in word]
            assert outputs == [
                prefix == prefix[::-1] and len(prefix) % 2 == 0
                for prefix in (word[:i] for i in range(1, len(word) + 1))
            ]


def test_outer_cursor_product_selected_long_worker_paths():
    for word in (
        '0110011001100110',
        '0100010010110100',
        '0010110010110010',
        '0000000000000000',
    ):
        machine = OrdinarySGOuter(audit=True, background_work_budget=200000)
        records = [machine.append(ch) for ch in word]
        assert records[-1].output == (word == word[::-1] and len(word) % 2 == 0)
        assert all(record.ordinary_steps > 0 for record in records)
