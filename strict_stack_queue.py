"""Imperative strict real-time queue using only stack/counter primitives.

This is the mutable, non-persistent form needed for a one-head-per-tape TM.
Each list is a stack with its top at the Python-list end.  A public operation
performs a fixed two rotation ticks.  Each tick uses only a bounded number of
stack pushes/pops and unary-counter increments/decrements.

The construction is the Hood--Melville rotation with two physical copies of
the front list.  The second copy replaces the persistent sharing used in the
functional presentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Generic, Iterable, TypeVar

T = TypeVar("T")


class RotationPhase(Enum):
    IDLE = auto()
    REVERSING = auto()
    APPENDING = auto()


@dataclass
class StrictStackQueue(Generic[T]):
    # Stable front copies, top/oldest at list end.
    f1: list[T]
    f2: list[T]
    # Stable/new rear, top/newest at list end.
    rear: list[T]
    # Rotation work stacks.
    fwork: list[T]
    fp: list[T]
    rold: list[T]
    rp1: list[T]
    rp2: list[T]
    phase: RotationPhase
    ok: int
    budget: int
    primitive_steps: int = 0
    maximum_primitives_per_operation: int = 0

    @staticmethod
    def empty() -> "StrictStackQueue[T]":
        return StrictStackQueue([], [], [], [], [], [], [], [], RotationPhase.IDLE, 0, 0)

    @staticmethod
    def from_iterable(values: Iterable[T]) -> "StrictStackQueue[T]":
        q: StrictStackQueue[T] = StrictStackQueue.empty()
        for value in values:
            q.snoc(value)
        return q

    @property
    def is_empty(self) -> bool:
        return not self.f1

    def head(self) -> T:
        if not self.f1:
            raise IndexError("head of empty queue")
        return self.f1[-1]

    def _start_rotation(self) -> None:
        assert self.phase is RotationPhase.IDLE
        assert self.budget == -1
        assert len(self.rear) == len(self.f1) + 1
        # f2 is the expendable frozen front copy. f1 continues serving reads.
        self.fwork = self.f2
        self.f2 = []
        self.rold = self.rear
        self.rear = []
        self.fp = []
        self.rp1 = []
        self.rp2 = []
        self.ok = 0
        self.budget = 0
        self.phase = RotationPhase.REVERSING
        self.primitive_steps += 1

    def _rotation_tick(self) -> None:
        if self.phase is RotationPhase.IDLE:
            return

        if self.phase is RotationPhase.REVERSING:
            if self.fwork and self.rold:
                x = self.fwork.pop()
                y = self.rold.pop()
                self.fp.append(x)
                self.rp1.append(y)
                self.rp2.append(y)
                self.ok += 1
                self.budget += 2
                self.primitive_steps += 8
                return
            if not self.fwork and len(self.rold) == 1:
                y = self.rold.pop()
                self.rp1.append(y)
                self.rp2.append(y)
                self.budget += 1
                self.phase = RotationPhase.APPENDING
                self.primitive_steps += 5
                return
            raise AssertionError(("bad reversing state", self.snapshot()))

        assert self.phase is RotationPhase.APPENDING
        if self.ok == 0:
            # Any remaining fp cells correspond to front elements invalidated
            # by dequeues while the rotation was in flight.
            self.fp = []
            self.f1 = self.rp1
            self.f2 = self.rp2
            self.rp1 = []
            self.rp2 = []
            self.fwork = []
            self.rold = []
            self.phase = RotationPhase.IDLE
            self.primitive_steps += 1
            assert self.budget == len(self.f1) - len(self.rear)
            assert self.budget >= 0
            return
        if not self.fp:
            raise AssertionError(("missing fp item", self.snapshot()))
        x = self.fp.pop()
        self.rp1.append(x)
        self.rp2.append(x)
        self.ok -= 1
        self.primitive_steps += 5

    def _exec2(self) -> None:
        self._rotation_tick()
        self._rotation_tick()

    def _consume_budget(self) -> None:
        self.budget -= 1
        self.primitive_steps += 1

    def _invalidate(self) -> None:
        if self.phase is RotationPhase.REVERSING:
            self.ok -= 1
            self.primitive_steps += 1
        elif self.phase is RotationPhase.APPENDING:
            if self.ok == 0:
                if not self.rp1 or not self.rp2:
                    raise AssertionError(self.snapshot())
                self.rp1.pop()
                self.rp2.pop()
                self.primitive_steps += 2
            else:
                self.ok -= 1
                self.primitive_steps += 1

    def _after_public_change(self, *, allow_start: bool) -> None:
        if self.phase is RotationPhase.IDLE and self.budget < 0:
            if not allow_start:
                raise AssertionError(self.snapshot())
            self._start_rotation()
        self._exec2()

    def snoc(self, value: T) -> None:
        before = self.primitive_steps
        self.rear.append(value)
        self.primitive_steps += 1
        self._consume_budget()
        self._after_public_change(allow_start=True)
        self.maximum_primitives_per_operation = max(
            self.maximum_primitives_per_operation, self.primitive_steps - before
        )
        self._assert_invariants()

    def tail(self) -> None:
        if not self.f1:
            raise IndexError("tail of empty queue")
        before = self.primitive_steps
        self.f1.pop()
        self.primitive_steps += 1
        if self.phase is RotationPhase.IDLE:
            # Stable front copies are identical.
            self.f2.pop()
            self.primitive_steps += 1
        else:
            self._invalidate()
        self._consume_budget()
        self._after_public_change(allow_start=True)
        self.maximum_primitives_per_operation = max(
            self.maximum_primitives_per_operation, self.primitive_steps - before
        )
        self._assert_invariants()

    def to_tuple(self) -> tuple[T, ...]:
        # Test-only observer.  Clone and destructively drain.
        import copy
        q = copy.deepcopy(self)
        out: list[T] = []
        while not q.is_empty:
            out.append(q.head())
            q.tail()
        return tuple(out)

    def snapshot(self) -> dict[str, object]:
        return {
            "f1": tuple(self.f1), "f2": tuple(self.f2), "rear": tuple(self.rear),
            "fwork": tuple(self.fwork), "fp": tuple(self.fp), "rold": tuple(self.rold),
            "rp1": tuple(self.rp1), "rp2": tuple(self.rp2), "phase": self.phase.name,
            "ok": self.ok, "budget": self.budget,
        }

    def _assert_invariants(self) -> None:
        assert self.budget >= 0
        if self.phase is RotationPhase.IDLE:
            assert self.f1 == self.f2
            assert not self.fwork and not self.fp and not self.rold
            assert not self.rp1 and not self.rp2
            assert self.ok == 0
            assert self.budget == len(self.f1) - len(self.rear)
        else:
            assert len(self.rp1) == len(self.rp2)
