from itertools import product

from fp_delta import DeltaKMPMatcher, failure_positions, jump_length
from fp_delta_micro import (
    DeferredDeltaKMPMatcher,
    MACHINE,
    run_primitive,
)


def words(max_length: int):
    for length in range(1, max_length + 1):
        for bits in product("01", repeat=length):
            yield "".join(bits)


def naive_occurrences(pattern: str, text: str) -> list[int]:
    return [i for i in range(len(text) - len(pattern) + 1) if text.startswith(pattern, i)]


def test_primitive_table_is_literal_and_finite() -> None:
    assert len(MACHINE.states) < 20
    assert len(MACHINE.delta) < 2000
    assert all(len(reads) == 4 for _, reads in MACHINE.delta)


def test_advance_and_backpointer_microprograms_exhaustively() -> None:
    for pattern in words(7):
        failure = failure_positions(pattern)
        for position in range(-1, len(pattern) - 1):
            got = run_primitive(pattern, position, "advance")
            assert got.new_position == position + 1
            assert got.new_jump == (0 if position + 1 < 0 else jump_length(pattern, position + 1))
            assert got.microsteps >= 2
        for position in range(len(pattern)):
            got = run_primitive(pattern, position, "backpointer")
            assert got.new_position == failure[position]
            assert got.old_jump == jump_length(pattern, position)
            assert got.new_jump == (
                0 if failure[position] < 0 else jump_length(pattern, failure[position])
            )
            assert got.microsteps > got.old_jump


def test_deferred_matcher_matches_logical_delta_kmp() -> None:
    cases = (
        ("aba", "ababaaba"),
        ("aaaa", "aaaaaa"),
        ("abcab", "zabcabcababcab"),
        ("00101", "0010010100101"),
    )
    for budget in (0, 1, 2, 5):
        for pattern, text in cases:
            direct = DeltaKMPMatcher(pattern)
            deferred = DeferredDeltaKMPMatcher(pattern, match_budget=budget)
            got = []
            expected = []
            for i, symbol in enumerate(text):
                a = direct.feed(symbol)
                b = deferred.feed(symbol)
                assert a.full_match == b.full_match
                if a.full_match:
                    expected.append(i - len(pattern) + 1)
                if b.full_match:
                    got.append(i - len(pattern) + 1)
            assert got == expected == naive_occurrences(pattern, text)


def test_deferred_updater_can_actually_lag_and_catch_up() -> None:
    matcher = DeferredDeltaKMPMatcher("aaaaaaaaab", match_budget=0)
    for symbol in "aaaaaaaaa":
        step = matcher.feed(symbol)
        assert not step.full_match
    assert matcher.pending_advances > 0
    # The mismatch forces all delayed C/S movement to complete before walking
    # a failure link.
    step = matcher.feed("b")
    assert step.microsteps > 0
    assert matcher.physical.position == matcher.logical_position
