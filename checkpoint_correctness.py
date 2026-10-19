"""Pure specifications and proof-certificate helpers for ``CheckpointCorrect``.

This module deliberately separates the mathematical checkpoint specification
from every executable implementation.  Its functions are used by proof audits
and tests; the ordinary checkpoint transition table never calls them.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from fp_delta import failure_positions
from lemma32_t1 import lemma32_t1_same_gaps


@dataclass(frozen=True)
class CheckpointSpecResult:
    """Abstract result of a frozen c=16 checkpoint request."""

    gaps: tuple[int, ...]
    candidate: int | None


def borders_from_failure(word: str) -> tuple[int, ...]:
    """All positive proper border lengths, in strictly decreasing order."""

    if not word:
        return ()
    failure = failure_positions(word)
    out: list[int] = []
    endpoint = failure[-1]
    while endpoint >= 0:
        out.append(endpoint + 1)
        endpoint = failure[endpoint]
    return tuple(out)


def gap_set_from_borders(word: str) -> tuple[int, ...]:
    """Failure-chain characterization of the specialized Lemma-3.2 gaps.

    This is intentionally written independently of ``lemma32_failure`` so the
    certificate checks the theorem rather than merely invoking the same helper.
    """

    n = len(word)
    if n == 0:
        return ()
    sep = "\0"
    if sep in word:
        raise ValueError("reserved separator occurs in input")

    plain_borders = set(borders_from_failure(word))
    periods = {n} | {n - border for border in plain_borders}

    prefix_pattern = word + sep + word[::-1]
    pal_prefixes = {
        length for length in borders_from_failure(prefix_pattern) if length <= n
    }

    suffix_pattern = word[::-1] + sep + word
    pal_suffixes = {
        length for length in borders_from_failure(suffix_pattern) if length <= n
    }

    gaps: set[int] = {n}
    for length in periods & pal_prefixes:
        if length % 2 == 0:
            gaps.add(length // 2)
    for length in pal_suffixes:
        if length % 2 == 0 and length < n:
            gaps.add(n - length // 2)
    return tuple(sorted(gaps))


def checkpoint_spec(word: str, c: int = 16) -> CheckpointSpecResult:
    """Return the exact abstract output expected from a frozen checkpoint."""

    if not word or any(symbol not in "01" for symbol in word):
        raise ValueError("word must be a nonempty binary string")
    if c != 16:
        raise ValueError("the current ordinary table is specialized to c=16")
    gaps = tuple(lemma32_t1_same_gaps(word))
    first_two = gaps[:2]
    least = gaps[0]
    candidate = least if 15 * least <= len(word) < 16 * least else None
    return CheckpointSpecResult(first_two, candidate)


def ratio_heads_after_gap(n: int, d: int) -> tuple[int, int]:
    """Source-head coordinates after the ratio loop has inspected gap ``d``.

    Source position 0 is the sentinel and position ``n+1`` is END.
    """

    if n < 1 or d < 1:
        raise ValueError((n, d))
    end = n + 1
    return min(15 * d, end), min(16 * d, end)


def ratio_marks_candidate(n: int, d: int) -> bool:
    left, right = ratio_heads_after_gap(n, d)
    return left != n + 1 and right == n + 1


def first_two(values: Iterable[int]) -> tuple[int, ...]:
    return tuple(sorted(set(values)))[:2]


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
