"""Linear reference implementation of Seiferas--Galil Lemma 3.2 at t=1.

The general lemma accepts two strings.  In the r=s=0 palindrome specialization
both strings supplied by Theorem 3 are the same active suffix ``a``.  This
collapses the two parse families to elementary period/palindrome predicates.

For a proposed gap ``d > 0``:

* if ``2*d <= len(a)``, the full-block branch holds exactly when ``2*d`` is a
  period of ``a`` and ``a[:2*d]`` is an even palindrome;
* if ``len(a) < 2*d``, the partial-block branch holds exactly when the suffix
  ``a[2*d-len(a):]`` is an even palindrome centred at ``d``.

A Z-array supplies all periods and Manacher's even-radius array supplies all
of the palindrome tests, so every valid gap is produced in O(len(a)) time on a
unit-cost indexed model.  This is an independent specialized implementation of
the logical job of Lemma 3.2; lowering these two arrays to primitive multitape
TM transitions is still a separate step.
"""

from __future__ import annotations


def z_array(word: str) -> list[int]:
    """Return the standard Z array in linear time."""

    n = len(word)
    if n == 0:
        return []
    z = [0] * n
    z[0] = n
    left = right = 0
    for i in range(1, n):
        if i < right:
            z[i] = min(right - i, z[i - left])
        while i + z[i] < n and word[z[i]] == word[i + z[i]]:
            z[i] += 1
        if i + z[i] > right:
            left, right = i, i + z[i]
    return z


def manacher_even(word: str) -> list[int]:
    """Return even-palindrome radii.

    ``radius[c]`` is the largest ``r`` such that ``word[c-r:c+r]`` is a
    palindrome.  Centres range from 0 through ``len(word)-1``; centre ``c`` is
    the boundary immediately before character ``c``.  The omitted boundary at
    ``len(word)`` has radius zero and is handled explicitly by callers.
    """

    n = len(word)
    radius = [0] * n
    left = 0
    right = -1
    for centre in range(n):
        r = 0 if centre > right else min(radius[left + right - centre + 1], right - centre + 1)
        while centre + r < n and centre - r - 1 >= 0 and word[centre + r] == word[centre - r - 1]:
            r += 1
        radius[centre] = r
        if centre + r - 1 > right:
            left = centre - r
            right = centre + r - 1
    return radius


def _even_radius_at(radii: list[int], centre: int, n: int) -> int:
    if centre == n:
        return 0
    return radii[centre]


def lemma32_t1_same_gaps(word: str) -> list[int]:
    """Return every positive gap accepted by Lemma 3.2 for ``(word, word)``.

    The output is sorted.  ``len(word)`` is always included for a nonempty
    word: it is the partial branch with an empty ``y``.
    """

    n = len(word)
    if n == 0:
        return []

    z = z_array(word)
    radii = manacher_even(word)
    result: list[int] = []

    for d in range(1, n + 1):
        if 2 * d <= n:
            period_ok = 2 * d == n or z[2 * d] >= n - 2 * d
            palindrome_prefix_ok = _even_radius_at(radii, d, n) >= d
            if period_ok and palindrome_prefix_ok:
                result.append(d)
        else:
            needed = n - d
            # word[2*d-n:n] is the even suffix centred at d.
            if _even_radius_at(radii, d, n) >= needed:
                result.append(d)

    return result


def lemma32_t1_same_midpoints(word: str, anchor: int) -> list[int]:
    """Translate valid gaps into absolute midpoint positions."""

    if not (0 <= anchor <= len(word)):
        raise ValueError((word, anchor))
    active = word[anchor:]
    return [anchor + d for d in lemma32_t1_same_gaps(active)]


def recover_pair_t1(word: str, anchor: int) -> tuple[int, int]:
    """Return the first two candidate midpoints strictly right of ``anchor``."""

    found = lemma32_t1_same_midpoints(word, anchor)
    automatic = len(word) + 1
    if automatic > anchor:
        found.append(automatic)
    found = sorted(set(found))
    if len(found) < 2:
        raise AssertionError((word, anchor, found))
    return found[0], found[1]


def next_candidate_t1(word: str, anchor: int, *, stop: int | None = None) -> int | None:
    """Return the least specialized Lemma-3.2 candidate after ``anchor``."""

    found = lemma32_t1_same_midpoints(word, anchor)
    automatic = len(word) + 1
    if stop is None or automatic <= stop:
        found.append(automatic)
    found = sorted(set(m for m in found if m > anchor and (stop is None or m <= stop)))
    return found[0] if found else None


def lemma32_t1_same_gaps_via_failure(word: str) -> list[int]:
    """Failure-link implementation, imported lazily to avoid a module cycle."""

    from lemma32_failure import lemma32_t1_same_gaps_failure

    return lemma32_t1_same_gaps_failure(word)
