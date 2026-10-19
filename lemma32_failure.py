"""Failure-chain form of the equal-input, t=1 Lemma 3.2 specialization.

This is equivalent to :func:`lemma32_t1.lemma32_t1_same_gaps`, but it uses only
KMP failure links.  That matters for the final Turing-machine lowering because
Fischer--Paterson and Galil give a unary-Delta implementation of exactly those
links.

For an active word ``a`` of length ``n``:

* ``p`` is a period length iff ``n-p`` is a border length of ``a``;
* ``l`` is a palindromic-prefix length iff it is a border length of
  ``a + $ + reverse(a)``;
* ``l`` is a palindromic-suffix length iff it is a border length of
  ``reverse(a) + $ + a``.

The full Lemma-3.2 branch accepts gap ``d`` when ``2d`` is both a period and a
palindromic-prefix length.  The partial branch maps every even palindromic
suffix length ``l<n`` to ``d=n-l/2`` and also includes the empty suffix ``d=n``.
"""

from __future__ import annotations

from fp_delta import failure_positions


def border_lengths(word: str) -> list[int]:
    """Return all positive proper border lengths, in decreasing order."""

    if not word:
        return []
    failure = failure_positions(word)
    result: list[int] = []
    position = failure[-1]
    while position >= 0:
        result.append(position + 1)
        position = failure[position]
    return result


def period_lengths(word: str) -> set[int]:
    n = len(word)
    if n == 0:
        return set()
    return {n} | {n - border for border in border_lengths(word)}


def palindromic_prefix_lengths(word: str) -> set[int]:
    if not word:
        return set()
    sep = "\0"
    if sep in word:
        raise ValueError("reserved separator occurs in input")
    combined = word + sep + word[::-1]
    return {length for length in border_lengths(combined) if length <= len(word)}


def palindromic_suffix_lengths(word: str) -> set[int]:
    if not word:
        return set()
    sep = "\0"
    if sep in word:
        raise ValueError("reserved separator occurs in input")
    combined = word[::-1] + sep + word
    return {length for length in border_lengths(combined) if length <= len(word)}


def lemma32_t1_same_gaps_failure(word: str) -> list[int]:
    n = len(word)
    if n == 0:
        return []

    periods = period_lengths(word)
    pal_prefix = palindromic_prefix_lengths(word)
    pal_suffix = palindromic_suffix_lengths(word)
    result: set[int] = {n}  # empty palindromic suffix in the partial branch

    for length in periods & pal_prefix:
        if length % 2 == 0:
            gap = length // 2
            if 2 * gap <= n:
                result.add(gap)

    for length in pal_suffix:
        if length % 2 == 0 and length < n:
            gap = n - length // 2
            if 2 * gap > n:
                result.add(gap)

    return sorted(result)
