"""Tiny ordinary one-head unary counters used by the outer SG cursor product.

The counters are intentionally literal: every method executes only operations
that a one-head tape can perform in one transition.  Push takes two transitions
(move to the fresh cell, then write); pop takes one transition (erase and move
left).  The finite sign of ``SignedUnaryCounter`` is kept in finite control.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

BLANK = "_"
BOTTOM = "#"
ONE = "1"
ALPHABET = (BLANK, BOTTOM, ONE)


@dataclass
class UnaryCounter:
    tape: dict[int, str]
    head: int = 0
    steps: int = 0

    @classmethod
    def zero(cls) -> "UnaryCounter":
        return cls({0: BOTTOM})

    def scanned(self) -> str:
        return self.tape.get(self.head, BLANK)

    @property
    def is_zero(self) -> bool:
        return self.scanned() == BOTTOM

    def increment(self) -> None:
        if self.scanned() not in (BOTTOM, ONE):
            raise AssertionError((self.head, self.scanned(), self.tape))
        # MOVE_RIGHT
        self.head += 1
        self.steps += 1
        if self.scanned() != BLANK:
            raise AssertionError(("nonblank push cell", self.head, self.scanned()))
        # WRITE_ONE
        self.tape[self.head] = ONE
        self.steps += 1

    def decrement(self) -> None:
        if self.scanned() != ONE:
            raise ValueError("cannot decrement zero unary counter")
        self.tape.pop(self.head, None)
        self.head -= 1
        self.steps += 1
        if self.scanned() not in (BOTTOM, ONE):
            raise AssertionError((self.head, self.scanned()))

    def clear(self) -> None:
        while not self.is_zero:
            self.decrement()

    def fresh_zero(self) -> None:
        """Start a new empty epoch without traversing the old unary contents."""
        self.head += 1
        self.steps += 1
        if self.scanned() != BLANK:
            raise AssertionError(("fresh epoch cell is not blank", self.head, self.scanned()))
        self.tape[self.head] = BOTTOM
        self.steps += 1

    def value(self) -> int:
        pos = self.head
        count = 0
        while self.tape.get(pos, BLANK) == ONE:
            count += 1
            pos -= 1
        if self.tape.get(pos, BLANK) != BOTTOM:
            raise AssertionError((pos, self.tape.get(pos, BLANK)))
        return count

    def copy_from(self, source: "UnaryCounter") -> None:
        """Replace this counter by a copy, restoring ``source``'s head.

        The loop is a direct finite-control traversal: source is walked to its
        bottom marker while this counter is pushed, then source is returned to
        its top by moving right over its existing unary cells.
        """
        self.clear()
        moved = 0
        while not source.is_zero:
            source.head -= 1
            source.steps += 1
            moved += 1
            self.increment()
        for _ in range(moved):
            source.head += 1
            source.steps += 1
            if source.scanned() != ONE:
                raise AssertionError(("restore source", source.head, source.scanned()))


class Sign(Enum):
    NEGATIVE = auto()
    ZERO = auto()
    POSITIVE = auto()


@dataclass
class SignedUnaryCounter:
    magnitude: UnaryCounter
    sign: Sign = Sign.ZERO
    control_steps: int = 0

    @classmethod
    def zero(cls) -> "SignedUnaryCounter":
        return cls(UnaryCounter.zero())

    @property
    def steps(self) -> int:
        return self.magnitude.steps + self.control_steps

    @property
    def is_positive(self) -> bool:
        return self.sign is Sign.POSITIVE

    def value(self) -> int:
        mag = self.magnitude.value()
        if self.sign is Sign.ZERO:
            if mag:
                raise AssertionError((self.sign, mag))
            return 0
        if not mag:
            raise AssertionError((self.sign, mag))
        return mag if self.sign is Sign.POSITIVE else -mag

    def clear(self) -> None:
        self.magnitude.clear()
        self.sign = Sign.ZERO
        self.control_steps += 1

    def fresh_zero(self) -> None:
        self.magnitude.fresh_zero()
        self.sign = Sign.ZERO
        self.control_steps += 1

    def increment(self) -> None:
        if self.sign is Sign.NEGATIVE:
            self.magnitude.decrement()
            if self.magnitude.is_zero:
                self.sign = Sign.ZERO
        elif self.sign is Sign.ZERO:
            self.magnitude.increment()
            self.sign = Sign.POSITIVE
        else:
            self.magnitude.increment()
        self.control_steps += 1

    def decrement(self) -> None:
        if self.sign is Sign.POSITIVE:
            self.magnitude.decrement()
            if self.magnitude.is_zero:
                self.sign = Sign.ZERO
        elif self.sign is Sign.ZERO:
            self.magnitude.increment()
            self.sign = Sign.NEGATIVE
        else:
            self.magnitude.increment()
        self.control_steps += 1
