from sg_zero_ratio_machine import SGZeroRatioMachine


def test_sg_all_ordinary_worker_backends_selected_words():
    samples = (
        '0110011001100110',
        '0100010010110100',
        '0010110010110010',
        '0000000000000000',
    )
    for word in samples:
        machine = SGZeroRatioMachine(
            c=16,
            background_scan_backend='ordinary_terminal',
            background_work_budget=200000,
            background_bootstrap_limit=0,
            lemma32_backend='ordinary_checkpoint',
            audit=True,
        )
        records = [machine.append(symbol) for symbol in word]
        assert machine.accepts == (word == word[::-1] and len(word) % 2 == 0)
        assert all(record.nominal_work >= 1 for record in records)
