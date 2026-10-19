"""Resumable linear checkpoint scan for the ``t=1`` Lemma 3.3 specialization.

The earlier audit implementation calculated a Z array and Manacher radii in a
single host-language call, then merely charged their estimated cost to later
input positions.  This module exposes the actual loops as a deterministic
microprogram.  One call to :meth:`tick` performs at most one character
comparison plus a constant number of indexed reads/writes.

The arrays are still an indexed-machine representation; lowering those indexed
locations to the already implemented unary-Delta tapes is a separate mechanical
step.  What matters for the online schedule is that the scan is now genuinely
resumable and that no answer is known before the corresponding microprogram has
finished.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class _Loop(Enum):
    Z_PREP = auto()
    Z_COMPARE = auto()
    Z_UPDATE = auto()
    M_PREP = auto()
    M_COMPARE = auto()
    M_STORE = auto()
    SWEEP = auto()
    DONE = auto()


@dataclass
class CheckpointCandidateScanJob:
    word: str
    c: int

    def __post_init__(self) -> None:
        if self.c <= 5:
            raise ValueError("the outer reversal proof requires c>5")
        self.n = len(self.word)
        self.z = [0] * self.n
        self.radii = [0] * self.n
        self.loop = _Loop.Z_PREP if self.n > 1 else _Loop.M_PREP

        # Z-loop registers.  We use the half-open Z-box [zl,zr).
        self.zi = 1
        self.zl = 0
        self.zr = 0

        # Manacher-even registers.  The active palindrome is [ml,mr].
        self.mi = 0
        self.ml = 0
        self.mr = -1
        self.mk = 0

        # Candidate sweep registers.
        self.d = 1
        self.max_life_before = -1
        self.candidate: int | None = None
        self.ticks = 0
        self.comparisons = 0

    @property
    def done(self) -> bool:
        return self.loop is _Loop.DONE

    def _finish_z_if_needed(self) -> bool:
        if self.zi < self.n:
            return False
        self.loop = _Loop.M_PREP
        return True

    def _finish_manacher_if_needed(self) -> bool:
        if self.mi < self.n:
            return False
        self.loop = _Loop.SWEEP
        return True

    def tick(self) -> bool:
        """Execute one bounded indexed-machine microstep.

        Returns ``True`` iff the whole checkpoint job is complete after this
        tick.  Calling ``tick`` after completion is an error.
        """

        if self.done:
            raise RuntimeError("checkpoint job already complete")
        self.ticks += 1

        if self.loop is _Loop.Z_PREP:
            if self._finish_z_if_needed():
                return False
            if self.zi < self.zr:
                self.z[self.zi] = min(
                    self.zr - self.zi,
                    self.z[self.zi - self.zl],
                )
            else:
                self.z[self.zi] = 0
            self.loop = _Loop.Z_COMPARE

        elif self.loop is _Loop.Z_COMPARE:
            amount = self.z[self.zi]
            if self.zi + amount < self.n:
                self.comparisons += 1
                if self.word[amount] == self.word[self.zi + amount]:
                    self.z[self.zi] += 1
                    return False
            self.loop = _Loop.Z_UPDATE

        elif self.loop is _Loop.Z_UPDATE:
            end = self.zi + self.z[self.zi]
            if end > self.zr:
                self.zl = self.zi
                self.zr = end
            self.zi += 1
            self.loop = _Loop.Z_PREP

        elif self.loop is _Loop.M_PREP:
            if self._finish_manacher_if_needed():
                return False
            if self.mi > self.mr:
                self.mk = 0
            else:
                mirror = self.ml + self.mr - self.mi + 1
                self.mk = min(self.radii[mirror], self.mr - self.mi + 1)
            self.loop = _Loop.M_COMPARE

        elif self.loop is _Loop.M_COMPARE:
            left = self.mi - self.mk - 1
            right = self.mi + self.mk
            if left >= 0 and right < self.n:
                self.comparisons += 1
                if self.word[left] == self.word[right]:
                    self.mk += 1
                    return False
            self.loop = _Loop.M_STORE

        elif self.loop is _Loop.M_STORE:
            self.radii[self.mi] = self.mk
            if self.mi + self.mk - 1 > self.mr:
                self.ml = self.mi - self.mk
                self.mr = self.mi + self.mk - 1
            self.mi += 1
            self.loop = _Loop.M_PREP

        elif self.loop is _Loop.SWEEP:
            if self.d > self.n // 2:
                self.loop = _Loop.DONE
                return True

            period = 2 * self.d
            if self.radii[self.d] >= self.d:
                life = self.n if period == self.n else period + self.z[period]
            else:
                life = -1

            base = (self.c - 1) * self.d
            target = self.c * self.d
            if (
                base <= self.n < target
                and life >= self.n
                and self.max_life_before < base
            ):
                self.candidate = self.d
                self.loop = _Loop.DONE
                return True

            if life > self.max_life_before:
                self.max_life_before = life
            self.d += 1

        else:  # pragma: no cover - enum exhaustiveness
            raise AssertionError(self.loop)

        return self.done

    def run(self) -> int | None:
        while not self.done:
            self.tick()
        return self.candidate
