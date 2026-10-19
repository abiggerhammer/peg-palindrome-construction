"""Executable Fischer--Paterson / Galil unary-delta KMP representation.

Galil's 1981 Section 4 restates the Fischer--Paterson Turing-machine encoding.
For a pattern ``x[0..n]`` let ``P(i)`` be the end position of the longest proper
prefix which is a suffix of ``x[:i+1]`` (or -1).  The tape stores

    Delta(i) = 1 + P(i) - P(i+1),   -1 <= i < n

as unary blocks ``0 1^Delta(-1) 0 1^Delta(0) ...``.  The jump length along the
backpointer at i is

    lambda(i) = i - P(i) = sum(Delta(j), j=-1..i-1).

This module makes those invariants and the two fundamental head operations
executable.  It is an audit-level multihead macro machine, not yet a one-cell
transition table: a block traversal is recorded with its exact unary distance
but is not expanded into individual read/write states.
"""

from __future__ import annotations

from dataclasses import dataclass


def failure_positions(pattern: str) -> list[int]:
    """Return Galil's P(0)..P(n) for a nonempty pattern."""

    if not pattern:
        raise ValueError("pattern must be nonempty")
    p = [-1] * len(pattern)
    for i in range(1, len(pattern)):
        j = p[i - 1]
        while j >= 0 and pattern[j + 1] != pattern[i]:
            j = p[j]
        if pattern[j + 1] == pattern[i]:
            j += 1
        p[i] = j
    return p


def delta_blocks(pattern: str) -> list[int]:
    """Return Delta(-1), Delta(0), ..., Delta(n-1)."""

    p = failure_positions(pattern)
    # P(-1)=-1.  There is one block for every transition into P(0)..P(n).
    previous = -1
    result: list[int] = []
    for current in p:
        result.append(1 + previous - current)
        previous = current
    assert all(value >= 0 for value in result)
    return result


def jump_length(pattern: str, position: int) -> int:
    p = failure_positions(pattern)
    if not (0 <= position < len(pattern)):
        raise ValueError(position)
    return position - p[position]


def unary_delta_tape(pattern: str) -> str:
    return "".join("0" + "1" * value for value in delta_blocks(pattern))


@dataclass(frozen=True)
class DeltaMove:
    kind: str
    old_position: int
    new_position: int
    unary_distance: int
    old_jump: int
    new_jump: int


@dataclass
class DeltaCursor:
    """Logical form of heads C and S in Galil's Figure 4.

    ``position`` is p, the currently matched pattern end.  ``jump`` is the
    unary counter s=lambda(p).  Position -1 is the left sentinel and has jump
    zero.
    """

    pattern: str
    position: int = -1
    jump: int = 0

    def __post_init__(self) -> None:
        self.p = failure_positions(self.pattern)
        self.delta = delta_blocks(self.pattern)
        self._assert_invariant()

    def _expected_jump(self, position: int) -> int:
        return 0 if position < 0 else position - self.p[position]

    def _assert_invariant(self) -> None:
        if not (-1 <= self.position < len(self.pattern)):
            raise AssertionError(self.position)
        assert self.jump == self._expected_jump(self.position)
        if self.position >= 0:
            assert self.jump == sum(self.delta[: self.position + 1])

    def go_backpointer(self) -> DeltaMove:
        if self.position < 0:
            raise ValueError("left sentinel has no backpointer")
        old_position = self.position
        old_jump = self.jump
        new_position = self.p[old_position]
        new_jump = self._expected_jump(new_position)
        # C crosses old_position-new_position blocks; Galil denotes this by s.
        unary_distance = old_jump
        self.position = new_position
        self.jump = new_jump
        self._assert_invariant()
        return DeltaMove(
            "backpointer",
            old_position,
            new_position,
            unary_distance,
            old_jump,
            new_jump,
        )

    def advance_match(self) -> DeltaMove:
        if self.position + 1 >= len(self.pattern):
            raise ValueError("already at complete match")
        old_position = self.position
        old_jump = self.jump
        new_position = old_position + 1
        new_jump = self._expected_jump(new_position)
        # C passes the next Delta block; S adds its number of unary 1s.
        block = self.delta[new_position]
        assert new_jump == old_jump + block
        self.position = new_position
        self.jump = new_jump
        self._assert_invariant()
        return DeltaMove(
            "match",
            old_position,
            new_position,
            block,
            old_jump,
            new_jump,
        )


@dataclass(frozen=True)
class MatchStep:
    symbol: str
    matched_length: int
    full_match: bool
    moves: tuple[DeltaMove, ...]


@dataclass
class DeltaKMPMatcher:
    """KMP matcher whose failure moves use the unary-delta cursor."""

    pattern: str

    def __post_init__(self) -> None:
        self.cursor = DeltaCursor(self.pattern)

    def feed(self, symbol: str, *, force_after_match: bool = True) -> MatchStep:
        if len(symbol) != 1:
            raise ValueError(symbol)
        moves: list[DeltaMove] = []

        while self.cursor.position >= 0 and self.pattern[self.cursor.position + 1] != symbol:
            moves.append(self.cursor.go_backpointer())

        if self.pattern[self.cursor.position + 1] == symbol:
            moves.append(self.cursor.advance_match())

        full = self.cursor.position == len(self.pattern) - 1
        matched_length = self.cursor.position + 1

        if full and force_after_match:
            # Treat an unmatchable endmarker as the next comparison.  This is
            # Galil's standard way to find all matches / force a mismatch.
            moves.append(self.cursor.go_backpointer())

        return MatchStep(symbol, matched_length, full, tuple(moves))
