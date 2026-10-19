from itertools import product

from sg_zero_ratio import b3_pair, is_even_palindrome
from sg_zero_ratio_machine import SGZeroRatioMachine


def test_oracle_case_machine_exhaustively() -> None:
    alphabet = "01"
    for length in range(11):
        for symbols in product(alphabet, repeat=length):
            word = "".join(symbols)
            machine = SGZeroRatioMachine(c=16, lemma32_backend="micro", background_scan_backend="indexed", background_bootstrap_limit=None, audit=True)
            for prefix_len, symbol in enumerate(word, start=1):
                machine.append(symbol)
                prefix = word[:prefix_len]
                assert machine.b == b3_pair(prefix)[0]
                assert machine.accepts == is_even_palindrome(prefix)


def test_unknown_second_obeys_invariant() -> None:
    machine = SGZeroRatioMachine(c=16, lemma32_backend="micro", background_scan_backend="indexed", background_bootstrap_limit=None, audit=True)
    for symbol in "001011010010110100101101":
        machine.append(symbol)
        if machine.bp is None:
            b, bp = b3_pair(machine.word)
            assert bp - b > (len(machine.word) - b) / machine.c


def test_whole_sg_machine_can_force_persistent_background_from_first_symbol() -> None:
    # This word enters case 5 after dropping B3'.  Setting the finite bootstrap
    # to zero forces the retained SEARCH job rather than the short-prefix
    # lookup used by the default construction.
    word = "0110" * 12
    machine = SGZeroRatioMachine(c=6, lemma32_backend="micro", background_scan_backend="indexed", background_bootstrap_limit=0, audit=True)
    saw_background = False
    for prefix_len, symbol in enumerate(word, start=1):
        record = machine.append(symbol)
        if record.action.name == "BACKGROUND":
            saw_background = True
            assert machine.background is not None
            assert machine.background.phase.name in {"SEARCH", "FOLLOW"}
        prefix = word[:prefix_len]
        assert machine.b == b3_pair(prefix)[0]
        assert machine.accepts == is_even_palindrome(prefix)
    assert saw_background


def test_whole_sg_machine_can_use_algorithm_y_tape_background():
    from sg_zero_ratio_machine import Action, SGZeroRatioMachine

    word = "0110" * 12
    machine = SGZeroRatioMachine(
        c=16,
        background_work_budget=200000,
        background_bootstrap_limit=0,
        background_scan_backend="algorithm_y_tape",
        audit=True,
    )
    actions = [machine.append(ch).action for ch in word]
    assert machine.accepts == (word == word[::-1])
    assert Action.BACKGROUND in actions


def test_whole_sg_machine_uses_algorithm_y_tape_for_all_expensive_branches():
    from sg_zero_ratio_machine import SGZeroRatioMachine

    samples = [
        "01000100101101001010",
        "0110011001100110",
        "0010110100010110",
    ]
    for word in samples:
        machine = SGZeroRatioMachine(
            c=16,
            lemma32_backend="algorithm_y_tape",
            background_scan_backend="algorithm_y_tape",
            background_work_budget=200000,
            background_bootstrap_limit=0,
            audit=True,
        )
        for ch in word:
            machine.append(ch)
        assert machine.accepts == (word == word[::-1] and len(word) % 2 == 0)


def test_default_explicit_path_does_not_call_reference_oracles(monkeypatch):
    import lemma33_persistent
    import sg_zero_ratio_machine

    def forbidden(*args, **kwargs):
        raise AssertionError("reference oracle entered operational path")

    monkeypatch.setattr(sg_zero_ratio_machine, "b3_pair", forbidden)
    monkeypatch.setattr(sg_zero_ratio_machine, "is_even_palindrome", forbidden)
    monkeypatch.setattr(lemma33_persistent, "lemma33_t1_discovered_gap", forbidden)

    machine = SGZeroRatioMachine(c=16)
    word = "01100110"
    outputs = []
    for symbol in word:
        machine.append(symbol)
        outputs.append(machine.accepts)
    assert outputs == [
        prefix == prefix[::-1] and len(prefix) % 2 == 0
        for prefix in (word[:i] for i in range(1, len(word) + 1))
    ]
