from itertools import product

from sg_zero_ratio_machine import SGZeroRatioMachine


def test_sg_ordinary_checkpoint_background_selected_words():
    samples = [
        "01100110011001100110011001100110",
        "01000100101101001010010010110100",
        "00101100101100101100101100101100",
    ]
    for word in samples:
        machine = SGZeroRatioMachine(
            c=16,
            background_scan_backend="ordinary_checkpoint",
            background_work_budget=200000,
            background_bootstrap_limit=0,
            lemma32_backend="algorithm_y_tape",
            audit=True,
        )
        records = [machine.append(ch) for ch in word]
        assert machine.accepts == (word == word[::-1] and len(word) % 2 == 0)
        assert any(r.action.name in {"BACKGROUND", "BACKGROUND_COMPLETES", "DROP_SECOND"} for r in records)


def test_sg_ordinary_background_exhaustive_short():
    # Most short words never require a long retained search, but this checks
    # that installing the ordinary backend does not perturb any six-case path.
    for n in range(1, 8):
        for bits in product("01", repeat=n):
            word = "".join(bits)
            machine = SGZeroRatioMachine(
                c=16,
                background_scan_backend="ordinary_checkpoint",
                background_work_budget=200000,
                background_bootstrap_limit=0,
                audit=True,
            )
            for ch in word:
                machine.append(ch)
            assert machine.accepts == (word == word[::-1] and n % 2 == 0)
