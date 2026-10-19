"""Strict real-time FIFO queue (Hood--Melville/Okasaki schedule).

This is a small executable reference for the storage primitive needed to lower
Algorithm Y's residual append/read tape unit.  Each public queue operation
performs at most two rotation-state transitions; no operation traverses a
list.  Tuples below model stacks (index zero is the top).  A later table
expansion maps each tuple head/tail operation to one ordinary tape step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterable, TypeVar, Union

T = TypeVar("T")


@dataclass(frozen=True)
class Idle:
    pass


@dataclass(frozen=True)
class Reversing(Generic[T]):
    ok: int
    f: tuple[T, ...]
    fp: tuple[T, ...]
    r: tuple[T, ...]
    rp: tuple[T, ...]


@dataclass(frozen=True)
class Appending(Generic[T]):
    ok: int
    fp: tuple[T, ...]
    rp: tuple[T, ...]


@dataclass(frozen=True)
class Done(Generic[T]):
    newf: tuple[T, ...]


Rotation = Union[Idle, Reversing[T], Appending[T], Done[T]]


@dataclass(frozen=True)
class RTQueue(Generic[T]):
    lenf: int
    f: tuple[T, ...]
    state: Rotation[T]
    lenr: int
    r: tuple[T, ...]
    rotation_steps: int = 0

    @staticmethod
    def empty() -> "RTQueue[T]":
        return RTQueue(0, (), Idle(), 0, ())

    @staticmethod
    def from_iterable(values: Iterable[T]) -> "RTQueue[T]":
        q: RTQueue[T] = RTQueue.empty()
        for value in values:
            q = q.snoc(value)
        return q

    @property
    def is_empty(self) -> bool:
        return self.lenf == 0

    def head(self) -> T:
        if not self.f:
            raise IndexError("head of empty queue")
        return self.f[0]

    @staticmethod
    def _exec_state(state: Rotation[T]) -> tuple[Rotation[T], int]:
        if isinstance(state, Reversing):
            if state.f and state.r:
                x, f = state.f[0], state.f[1:]
                y, r = state.r[0], state.r[1:]
                return Reversing(
                    state.ok + 1,
                    f,
                    (x,) + state.fp,
                    r,
                    (y,) + state.rp,
                ), 1
            if not state.f and len(state.r) == 1:
                y = state.r[0]
                return Appending(state.ok, state.fp, (y,) + state.rp), 1
            raise AssertionError(("bad reversing state", state))

        if isinstance(state, Appending):
            if state.ok == 0:
                return Done(state.rp), 1
            if state.fp:
                x, fp = state.fp[0], state.fp[1:]
                return Appending(state.ok - 1, fp, (x,) + state.rp), 1
            raise AssertionError(("bad appending state", state))

        return state, 0

    @staticmethod
    def _invalidate(state: Rotation[T]) -> Rotation[T]:
        if isinstance(state, Reversing):
            return Reversing(state.ok - 1, state.f, state.fp, state.r, state.rp)
        if isinstance(state, Appending):
            if state.ok == 0:
                if not state.rp:
                    raise AssertionError(state)
                return Done(state.rp[1:])
            return Appending(state.ok - 1, state.fp, state.rp)
        return state

    def _exec(self) -> "RTQueue[T]":
        state, spent = self._exec_state(self.state)
        if isinstance(state, Done):
            return RTQueue(self.lenf, state.newf, Idle(), self.lenr, self.r,
                           self.rotation_steps + spent)
        return RTQueue(self.lenf, self.f, state, self.lenr, self.r,
                       self.rotation_steps + spent)

    def _exec2(self) -> "RTQueue[T]":
        return self._exec()._exec()

    def _check(self) -> "RTQueue[T]":
        if self.lenr <= self.lenf:
            return self._exec2()
        # The invariant before the operation implies lenr == lenf + 1.
        assert self.lenr == self.lenf + 1, (self.lenf, self.lenr)
        q = RTQueue(
            self.lenf + self.lenr,
            self.f,
            Reversing(0, self.f, (), self.r, ()),
            0,
            (),
            self.rotation_steps,
        )
        return q._exec2()

    def snoc(self, value: T) -> "RTQueue[T]":
        return RTQueue(
            self.lenf,
            self.f,
            self.state,
            self.lenr + 1,
            (value,) + self.r,
            self.rotation_steps,
        )._check()

    def tail(self) -> "RTQueue[T]":
        if not self.f:
            raise IndexError("tail of empty queue")
        return RTQueue(
            self.lenf - 1,
            self.f[1:],
            self._invalidate(self.state),
            self.lenr,
            self.r,
            self.rotation_steps,
        )._check()

    def to_tuple(self) -> tuple[T, ...]:
        q = self
        out: list[T] = []
        # This observer is only for tests; it does not participate in the
        # real-time implementation.
        while not q.is_empty:
            out.append(q.head())
            q = q.tail()
        return tuple(out)
