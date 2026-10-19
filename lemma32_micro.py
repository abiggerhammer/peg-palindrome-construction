"""Cell-level unary-Delta realization of specialized Lemma 3.2.

This module computes the same gaps as ``lemma32_t1.py`` without Z arrays,
Manacher arrays, or a precomputed KMP failure table.  It constructs three
failure tapes using :func:`fp_delta_micro.build_failure_delta_micro` and walks
their border chains through the flat unary backpointer program.

The remaining operations are finite-control arithmetic on marked positions:
set intersection, parity, doubling/halving, and translating a relative gap to
an absolute midpoint.  Those are kept explicit in Python here and are the next
small counter/head layer to lower.
"""

from __future__ import annotations

from dataclasses import dataclass

from fp_delta_micro import (
    FailureBuildResult,
    build_failure_delta_micro,
    run_primitive_blocks,
)


@dataclass(frozen=True)
class MicroGapResult:
    gaps: tuple[int, ...]
    primitive_microsteps: int
    block_write_steps: int
    border_walk_steps: int
    constructed_lengths: tuple[int, int, int]

    @property
    def total_steps(self) -> int:
        return self.primitive_microsteps + self.block_write_steps + self.border_walk_steps


def _border_chain_micro(built: FailureBuildResult) -> tuple[list[int], int]:
    """Return proper border lengths by unary backpointer traversal."""

    position = len(built.pattern) - 1
    borders: list[int] = []
    work = 0
    while position >= 0:
        move = run_primitive_blocks(list(built.blocks), position, "backpointer")
        work += move.microsteps
        position = move.new_position
        if position >= 0:
            borders.append(position + 1)
    return borders, work


def lemma32_t1_same_gaps_micro(word: str) -> MicroGapResult:
    n = len(word)
    if n == 0:
        return MicroGapResult((), 0, 0, 0, (0, 0, 0))
    sep = "\0"
    if sep in word:
        raise ValueError("reserved separator occurs in input")

    plain = build_failure_delta_micro(word)
    prefix_combined = build_failure_delta_micro(word + sep + word[::-1])
    suffix_combined = build_failure_delta_micro(word[::-1] + sep + word)

    plain_borders, plain_walk = _border_chain_micro(plain)
    prefix_borders, prefix_walk = _border_chain_micro(prefix_combined)
    suffix_borders, suffix_walk = _border_chain_micro(suffix_combined)

    periods = {n} | {n - border for border in plain_borders}
    pal_prefix = {length for length in prefix_borders if length <= n}
    pal_suffix = {length for length in suffix_borders if length <= n}

    gaps: set[int] = {n}
    for length in periods & pal_prefix:
        if length % 2 == 0:
            gaps.add(length // 2)
    for length in pal_suffix:
        if length % 2 == 0 and length < n:
            gaps.add(n - length // 2)

    builds = (plain, prefix_combined, suffix_combined)
    return MicroGapResult(
        gaps=tuple(sorted(gaps)),
        primitive_microsteps=sum(item.primitive_microsteps for item in builds),
        block_write_steps=sum(item.block_write_steps for item in builds),
        border_walk_steps=plain_walk + prefix_walk + suffix_walk,
        constructed_lengths=tuple(len(item.pattern) for item in builds),
    )


def recover_pair_micro(word: str, anchor: int) -> tuple[int, int]:
    active = word[anchor:]
    found = [anchor + gap for gap in lemma32_t1_same_gaps_micro(active).gaps]
    found.append(len(word) + 1)
    found = sorted(set(value for value in found if value > anchor))
    if len(found) < 2:
        raise AssertionError((word, anchor, found))
    return found[0], found[1]


def next_candidate_micro(
    word: str, anchor: int, *, stop: int | None = None
) -> int | None:
    active = word[anchor:]
    found = [anchor + gap for gap in lemma32_t1_same_gaps_micro(active).gaps]
    automatic = len(word) + 1
    if stop is None or automatic <= stop:
        found.append(automatic)
    found = sorted(
        set(value for value in found if value > anchor and (stop is None or value <= stop))
    )
    return found[0] if found else None


def lemma33_discovered_gap_micro(word: str, c: int) -> int | None:
    if c <= 5:
        raise ValueError("the Theorem 3 schedule assumes c>5")
    n = len(word)
    if n == 0 or n % c:
        return None
    gaps = lemma32_t1_same_gaps_micro(word).gaps
    target = n // c
    return target if gaps and gaps[0] == target else None
