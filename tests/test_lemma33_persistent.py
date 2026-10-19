from itertools import product

import pytest

from lemma33_persistent import (
    PersistentLemma33T1,
    checkpoint_candidate_t1,
)
from lemma33_t1 import lemma33_t1_discovered_gap


@pytest.mark.parametrize("c", [6, 7, 8, 16])
def test_persistent_scheduler_exhaustive(c: int):
    for n in range(15):
        for bits in product("01", repeat=n):
            word = "".join(bits)
            machine = PersistentLemma33T1(c=c, scan_backend="indexed", audit=True, bootstrap_limit=None)
            outputs = [machine.feed(ch).output_gap for ch in word]
            expected = [
                lemma33_t1_discovered_gap(word[:i], c)
                for i in range(1, len(word) + 1)
            ]
            assert outputs == expected


def test_can_start_from_existing_active_suffix():
    word = "01000100101101001010"
    for split in range(len(word) + 1):
        machine = PersistentLemma33T1(c=7, initial=word[:split], scan_backend="indexed", audit=True, bootstrap_limit=None)
        outputs = [machine.feed(ch).output_gap for ch in word[split:]]
        expected = [
            lemma33_t1_discovered_gap(word[:i], 7)
            for i in range(split + 1, len(word) + 1)
        ]
        assert outputs == expected


def test_checkpoint_candidate_is_future_target():
    for n in range(1, 80):
        word = ("010001" * 20)[:n]
        d = checkpoint_candidate_t1(word, 7)
        if d is not None:
            assert 6 * d <= n < 7 * d


def test_scan_completion_exactly_at_target_emits_without_delay():
    # With bootstrap disabled, the all-zero word selects d=1 at checkpoint 5
    # for c=6.  The scan completes on the same physical step as target 6.
    machine = PersistentLemma33T1(c=6, bootstrap_limit=0, scan_backend="indexed", audit=True)
    outputs = [machine.feed(ch).output_gap for ch in "000000"]
    assert outputs == [None, None, None, None, None, 1]


@pytest.mark.parametrize(
    "c,word,expected",
    [
        (6, "0110" * 3, (12, 2)),
        (7, "0110" * 4, (14, 2)),
        (16, "0110" * 8, (32, 2)),
    ],
)
def test_forced_bootstrap_exercises_retained_search_and_follow(c, word, expected):
    machine = PersistentLemma33T1(c=c, bootstrap_limit=0, scan_backend="indexed", audit=True)
    seen = set()
    outputs = []
    for index, symbol in enumerate(word, 1):
        step = machine.feed(symbol)
        seen.add(step.phase_before.name)
        seen.add(step.phase_after.name)
        if step.output_gap is not None:
            outputs.append((index, step.output_gap))
    assert "SEARCH" in seen
    assert "FOLLOW" in seen
    assert expected in outputs


def test_persistent_algorithm_y_backend_matches_reference():
    from itertools import product

    from lemma33_persistent import PersistentLemma33T1
    from lemma33_t1 import lemma33_t1_discovered_gap

    for c in (6, 7, 16):
        for n in range(1, 7):
            for chars in product("01", repeat=n):
                word = "".join(chars)
                machine = PersistentLemma33T1(
                    c,
                    work_budget=100000,
                    bootstrap_limit=0,
                    scan_backend="algorithm_y",
                )
                outputs = []
                for ch in word:
                    outputs.append(machine.feed(ch).output_gap)
                assert outputs[-1] == lemma33_t1_discovered_gap(word, c)


def test_persistent_algorithm_y_tape_backend_selected_prefixes():
    from lemma33_persistent import PersistentLemma33T1
    from lemma33_t1 import lemma33_t1_discovered_gap

    samples = [
        "00000000",
        "011001100110",
        "010001001011",
        "001011001011",
    ]
    for c in (6, 7, 16):
        for word in samples:
            machine = PersistentLemma33T1(
                c,
                work_budget=200000,
                bootstrap_limit=0,
                scan_backend="algorithm_y_tape",
            )
            outputs = [machine.feed(ch).output_gap for ch in word]
            expected = [
                lemma33_t1_discovered_gap(word[:i], c)
                for i in range(1, len(word) + 1)
            ]
            assert outputs == expected
