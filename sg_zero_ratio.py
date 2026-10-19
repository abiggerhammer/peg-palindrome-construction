"""Executable audit model for the r=s=0 Seiferas--Galil reversal theorem.

This module is deliberately *not* the final real-time transition table.  It is a
mathematical reference model for the zero-ratio specialization used to audit
and test the eventual lowering.

For a prefix ``u`` of length ``R``, let S(u) be the set of midpoint positions
``m`` for which ``u`` can be extended to an even palindrome of total length
``2*m``.  Seiferas and Galil's B3 and B3' become the two least members of S(u).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from itertools import product
from typing import Iterable, Iterator, Optional, Sequence


Alphabet = str


def is_palindrome(word: str) -> bool:
    return word == word[::-1]


def is_even_palindrome(word: str) -> bool:
    return len(word) % 2 == 0 and is_palindrome(word)


def has_period(word: str, period: int) -> bool:
    """Return whether ``period`` is a period in the paper's prefix sense."""

    if period <= 0:
        return False
    return all(word[i] == word[i - period] for i in range(period, len(word)))


def candidate_midpoint(word: str, midpoint: int) -> bool:
    """Whether ``word`` extends to ``x x^R`` with ``|x| == midpoint``.

    The test is finite even though the definition quantifies over extensions:

    * ``2*midpoint < len(word)``: impossible, because the proposed completed
      word is already shorter than the prefix;
    * ``midpoint >= len(word)``: always possible, because the whole prefix can
      still lie in the first half;
    * otherwise the already-read part of the second half must match the
      corresponding reversed part of the first half.
    """

    n = len(word)
    if midpoint < 0 or 2 * midpoint < n:
        return False
    if midpoint >= n:
        return True
    overlap = n - midpoint
    return word[midpoint:n] == word[2 * midpoint - n : midpoint][::-1]


def candidate_midpoint_via_suffix(word: str, midpoint: int) -> bool:
    """Equivalent characterization by an even palindromic suffix."""

    n = len(word)
    if midpoint < 0 or 2 * midpoint < n:
        return False
    if midpoint >= n:
        return True
    return is_palindrome(word[2 * midpoint - n : n])


def candidate_midpoints(word: str, *, extra: int = 2) -> list[int]:
    """List all relevant candidates through ``len(word)+extra``.

    All midpoints at or to the right of the current input end are candidates,
    so a finite prefix of S(u) is sufficient to obtain B3 and B3'.
    """

    n = len(word)
    return [m for m in range(0, n + extra + 1) if candidate_midpoint(word, m)]


def b3_pair(word: str) -> tuple[int, int]:
    candidates = candidate_midpoints(word, extra=2)
    if len(candidates) < 2:  # Defensive; n and n+1 are always candidates.
        raise AssertionError((word, candidates))
    return candidates[0], candidates[1]


def even_palindromic_suffix_half_lengths(word: str) -> list[int]:
    """Descending half-lengths of even palindromic suffixes, including zero."""

    n = len(word)
    result = [
        d
        for d in range(0, n // 2 + 1)
        if is_palindrome(word[n - 2 * d : n])
    ]
    return sorted(result, reverse=True)


def b3_pair_via_suffixes(word: str) -> tuple[int, int]:
    n = len(word)
    halves = even_palindromic_suffix_half_lengths(word)
    b = n - halves[0]
    if len(halves) >= 2:
        bp = n - halves[1]
    else:
        bp = n + 1
    return b, bp


def left_position(word: str, midpoint: int) -> int:
    """The specialized LEFT value: 2*midpoint - RIGHT."""

    return 2 * midpoint - len(word)


def survives_append(word: str, midpoint: int, symbol: str) -> bool:
    """Constant-time survival test used by the six-case update.

    The caller may think of ``word`` as already recorded on a work tape with a
    head at ``LEFT = 2*midpoint-len(word)``.
    """

    n = len(word)
    new_n = n + 1
    if midpoint >= new_n:
        return True
    if 2 * midpoint <= n:
        return False
    mirror = 2 * midpoint - n - 1
    return 0 <= mirror < n and word[mirror] == symbol


class UpdateCase(Enum):
    ONE_BOTH_SURVIVE = auto()
    TWO_BOTH_FAIL = auto()
    THREE_SECOND_SURVIVES = auto()
    FOUR_FIRST_SURVIVES = auto()
    FIVE_SECOND_UNKNOWN_FIRST_SURVIVES = auto()
    SIX_SECOND_UNKNOWN_FIRST_FAILS = auto()


def classify_update(
    word: str,
    symbol: str,
    *,
    second_known: bool = True,
) -> UpdateCase:
    b, bp = b3_pair(word)
    b_ok = survives_append(word, b, symbol)
    if not second_known:
        return (
            UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES
            if b_ok
            else UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS
        )
    bp_ok = survives_append(word, bp, symbol)
    if b_ok and bp_ok:
        return UpdateCase.ONE_BOTH_SURVIVE
    if not b_ok and not bp_ok:
        return UpdateCase.TWO_BOTH_FAIL
    if not b_ok and bp_ok:
        return UpdateCase.THREE_SECOND_SURVIVES
    return UpdateCase.FOUR_FIRST_SURVIVES


@dataclass(frozen=True)
class UpdateFacts:
    word: str
    symbol: str
    case: UpdateCase
    old_b: int
    old_bp: int
    new_b: int
    new_bp: int

    @property
    def right(self) -> int:
        return len(self.word)

    @property
    def old_gap(self) -> int:
        return self.old_bp - self.old_b

    @property
    def jump(self) -> int:
        return self.new_b - self.old_b


def update_facts(word: str, symbol: str) -> UpdateFacts:
    old_b, old_bp = b3_pair(word)
    new_b, new_bp = b3_pair(word + symbol)
    return UpdateFacts(
        word=word,
        symbol=symbol,
        case=classify_update(word, symbol, second_known=True),
        old_b=old_b,
        old_bp=old_bp,
        new_b=new_b,
        new_bp=new_bp,
    )


def sg_l0_member(first: str, second: str, d: int) -> bool:
    """The r=s=0 specialization of the set L(m,n) in Lemma 3.1.

    Here ``d = m-n``.  The two branches are copied literally after setting
    ``(r+1)/(r+1+s) = 1``.
    """

    if d <= 0:
        return False

    # First branch: first = x y z, |x|=|y|=d,
    # y^R is a prefix of second, and z is a prefix of first.
    if len(first) >= 2 * d:
        x = first[:d]
        y = first[d : 2 * d]
        z = first[2 * d :]
        if second.startswith(y[::-1]) and first.startswith(z):
            return True

    # Second branch: first = x y, |x|=d, |y|<d,
    # y^R is a suffix of second[0:d].
    if d <= len(first) < 2 * d:
        x = first[:d]
        y = first[d:]
        if second[:d].endswith(y[::-1]):
            return True

    return False



def candidates_after_anchor_via_lemma31(
    word: str, anchor: int, *, stop: Optional[int] = None
) -> list[int]:
    """Enumerate candidate midpoints to the right of ``anchor`` via Lemma 3.1.

    The precondition used by the paper is that ``anchor`` was a candidate for
    the immediately preceding prefix, or is a candidate for ``word`` itself.
    The equivalence is valid for candidate positions through ``RIGHT(word)``.
    ``RIGHT(word)+1`` is then appended as the next automatic candidate when
    needed, because every midpoint at or beyond the current input end can still
    be completed arbitrarily in its first half.

    This is a literal, deliberately unoptimized implementation of the logical
    interface supplied by Lemma 3.1.  It does not yet implement Lemma 3.2's
    linear-time all-parses algorithm.
    """

    right = len(word)
    if not (0 <= anchor <= right):
        raise ValueError((word, anchor))
    upper = right if stop is None else min(stop, right)
    suffix = word[anchor:]
    result: list[int] = []
    for midpoint in range(anchor + 1, upper + 1):
        if sg_l0_member(suffix, suffix, midpoint - anchor):
            result.append(midpoint)
    return result


def recover_pair_via_lemma31(word: str, anchor: int) -> tuple[int, int]:
    """Recover the first two candidates strictly right of ``anchor``.

    This is the semantic RECOVER operation used in cases 2 and 6.  It scans
    candidate positions with the specialized Lemma 3.1 predicate, rather than
    consulting the direct palindrome oracle.  The scan is not yet real-time.
    """

    found = candidates_after_anchor_via_lemma31(word, anchor)
    right = len(word)
    # RIGHT and RIGHT+1 are always candidates.  RIGHT will normally already
    # have been found by the lemma predicate, but de-duplicate defensively.
    for automatic in (right, right + 1):
        if automatic > anchor and automatic not in found:
            found.append(automatic)
    found.sort()
    if len(found) < 2:
        raise AssertionError((word, anchor, found))
    return found[0], found[1]


def next_candidate_via_lemma31(
    word: str, anchor: int, *, stop: Optional[int] = None
) -> Optional[int]:
    """Return the least candidate greater than a currently valid anchor.

    If ``stop`` is supplied, search only through that midpoint.  This models
    the LOCAL search in the small-gap branch of case 3.
    """

    found = candidates_after_anchor_via_lemma31(word, anchor, stop=stop)
    if found:
        return found[0]
    automatic = max(len(word), anchor + 1)
    if stop is None or automatic <= stop:
        return automatic
    return None

def lemma31_holds(word: str, n: int, m: int) -> bool:
    """Check the specialized equivalence of Lemma 3.1 for one triple."""

    if not (0 <= n < m <= len(word)):
        raise ValueError((word, n, m))
    suffix = word[n:]
    return candidate_midpoint(word, m) == sg_l0_member(suffix, suffix, m - n)


def relevant_lemma31_triples(word: str) -> Iterator[tuple[int, int]]:
    """Yield triples covered by the lemma's one-symbol-extension hypothesis.

    The paper permits n in S(u') for u=u'a, even if n drops out of S(u).
    """

    if not word:
        return
    previous = word[:-1]
    for n in candidate_midpoints(previous, extra=0):
        if n >= len(word):
            continue
        for m in range(n + 1, len(word) + 1):
            yield n, m


def lemma31_period_conclusion(word: str) -> bool:
    """Check the period conclusion for B3 and B3' whenever B3' <= RIGHT."""

    b, bp = b3_pair(word)
    if bp > len(word):
        return True
    return has_period(word[b:], 2 * (bp - b))


def case_structural_facts(facts: UpdateFacts) -> list[str]:
    """Return violations of the order facts implicit in the six cases."""

    errors: list[str] = []
    c = facts.case
    b, bp, nb, nbp = facts.old_b, facts.old_bp, facts.new_b, facts.new_bp

    if c is UpdateCase.ONE_BOTH_SURVIVE:
        if not (nb == b and nbp == bp):
            errors.append("case 1 should preserve both candidates")
    elif c is UpdateCase.TWO_BOTH_FAIL:
        if not (nb > bp):
            errors.append("case 2 should jump past old B3'")
    elif c is UpdateCase.THREE_SECOND_SURVIVES:
        if not (nb == bp and nbp > bp):
            errors.append("case 3 should promote old B3'")
    elif c is UpdateCase.FOUR_FIRST_SURVIVES:
        if not (nb == b and nbp > bp):
            errors.append("case 4 should preserve B3 and discard old B3'")
    return errors


def case2_fine_wilf_bound(facts: UpdateFacts) -> bool:
    """Specialized page-139 bound for case 2.

    If the nontrivial premise ``b + 2*(new_b-b) < RIGHT`` holds, the paper
    derives ``RIGHT-b < 4*(new_b-b)``.  Otherwise the same asymptotic bound is
    immediate from the negation of the premise (up to the harmless endpoint).
    """

    if facts.case is not UpdateCase.TWO_BOTH_FAIL:
        return True
    if facts.jump <= 0:
        return False
    return facts.right - facts.old_b <= 4 * facts.jump


def enumerate_words(alphabet: Sequence[str], max_length: int) -> Iterable[str]:
    for n in range(max_length + 1):
        for chars in product(alphabet, repeat=n):
            yield "".join(chars)


def exhaustive_audit(alphabet: Sequence[str] = ("0", "1"), max_length: int = 10) -> None:
    """Run all reference-model proof checks through ``max_length``."""

    for word in enumerate_words(alphabet, max_length):
        assert b3_pair(word) == b3_pair_via_suffixes(word), word
        for m in range(0, len(word) + 3):
            assert candidate_midpoint(word, m) == candidate_midpoint_via_suffix(word, m), (
                word,
                m,
            )
        assert lemma31_period_conclusion(word), word

        if word:
            for n, m in relevant_lemma31_triples(word):
                assert lemma31_holds(word, n, m), (word, n, m)

        for symbol in alphabet:
            facts = update_facts(word, symbol)
            assert not case_structural_facts(facts), facts
            assert case2_fine_wilf_bound(facts), facts
            assert survives_append(word, facts.old_b, symbol) == candidate_midpoint(
                word + symbol, facts.old_b
            )
            assert survives_append(word, facts.old_bp, symbol) == candidate_midpoint(
                word + symbol, facts.old_bp
            )


if __name__ == "__main__":
    exhaustive_audit(max_length=12)
    print("SG r=s=0 audit passed through length 12")
