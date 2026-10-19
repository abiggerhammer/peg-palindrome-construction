from sg_zero_ratio_machine import SGZeroRatioMachine


def test_sg_ordinary_terminal_backend_selected_words():
    samples = (
        '01100110011001100110011001100110',
        '01000100101101001010010010110100',
        '00101100101100101100101100101100',
    )
    for word in samples:
        machine = SGZeroRatioMachine(
            c=16,
            background_scan_backend='ordinary_terminal',
            background_work_budget=200000,
            background_bootstrap_limit=0,
            lemma32_backend='algorithm_y_tape',
            audit=True,
        )
        records = [machine.append(symbol) for symbol in word]
        assert machine.accepts == (word == word[::-1] and len(word) % 2 == 0)
        assert any(record.action.name in {'BACKGROUND', 'BACKGROUND_COMPLETES', 'DROP_SECOND'} for record in records)
