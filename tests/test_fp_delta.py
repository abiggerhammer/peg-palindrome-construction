from fp_delta import (
    DeltaCursor,
    DeltaKMPMatcher,
    delta_blocks,
    failure_positions,
    jump_length,
    unary_delta_tape,
)


def naive_occurrences(pattern: str, text: str) -> list[int]:
    return [i for i in range(len(text) - len(pattern) + 1) if text.startswith(pattern, i)]


def test_delta_telescoping_identity() -> None:
    for pattern in ("a", "aaaa", "abacaba", "ababaca", "aabaaab"):
        blocks = delta_blocks(pattern)
        assert unary_delta_tape(pattern).count("0") == len(pattern)
        for i in range(len(pattern)):
            assert sum(blocks[: i + 1]) == jump_length(pattern, i)


def test_cursor_operations_follow_failure_positions() -> None:
    pattern = "ababaca"
    cursor = DeltaCursor(pattern)
    for _ in pattern:
        cursor.advance_match()
    p = failure_positions(pattern)
    old = cursor.position
    move = cursor.go_backpointer()
    assert move.new_position == p[old]
    assert cursor.jump == (0 if cursor.position < 0 else cursor.position - p[cursor.position])


def test_delta_matcher_finds_all_occurrences() -> None:
    for pattern, text in (
        ("aba", "ababaaba"),
        ("aaaa", "aaaaaa"),
        ("abcab", "zabcabcababcab"),
    ):
        matcher = DeltaKMPMatcher(pattern)
        got = []
        for i, symbol in enumerate(text):
            step = matcher.feed(symbol)
            if step.full_match:
                got.append(i - len(pattern) + 1)
        assert got == naive_occurrences(pattern, text)
