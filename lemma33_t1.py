"""The t=1, equal-input specialization of Seiferas--Galil Lemma 3.3.

During case 5 of the r=s=0 reversal machine, B2=B3, so the two strings supplied
to Lemma 3.3 are identical.  Let ``q`` be that common active suffix and let
``c>5`` be the fixed scheduling constant.

The positive part of L' requires a parse with ``|q| = c|x|``.  The subtraction
removes q whenever there is an earlier valid parse with ``|q| > c|x|``.  Hence
q is in L' exactly when ``|q|`` is divisible by c and ``|q|/c`` is the least
positive Lemma-3.1 candidate gap.
"""

from __future__ import annotations

from lemma32_t1 import lemma32_t1_same_gaps


def lemma33_t1_same_member(word: str, c: int) -> bool:
    """Whether ``(word, word)`` belongs to specialized Lemma 3.3 language L'."""

    if c <= 5:
        raise ValueError("the Theorem 3 schedule assumes c>5")
    n = len(word)
    if n == 0 or n % c:
        return False
    target = n // c
    gaps = lemma32_t1_same_gaps(word)
    return bool(gaps) and gaps[0] == target


def lemma33_t1_discovered_gap(word: str, c: int) -> int | None:
    """Return the candidate gap discovered at this exact input length."""

    if not lemma33_t1_same_member(word, c):
        return None
    return len(word) // c
