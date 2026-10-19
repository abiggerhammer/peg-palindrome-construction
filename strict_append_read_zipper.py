"""Mutable append/read tape using only stacks and a strict stack queue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterable, TypeVar

from strict_stack_queue import StrictStackQueue

T = TypeVar("T")


@dataclass
class StrictAppendReadZipper(Generic[T]):
    blank: T
    # Tops are at list end.
    left: list[T]
    current: T
    front: list[T]
    queue: StrictStackQueue[T]
    primitive_steps: int = 0
    maximum_primitives_per_operation: int = 0

    @staticmethod
    def from_cells(
        cells: Iterable[T], *, reader: int, writer: int, blank: T
    ) -> "StrictAppendReadZipper[T]":
        data = tuple(cells)
        if not (0 <= reader < writer == len(data)):
            raise ValueError((reader, writer, len(data)))
        return StrictAppendReadZipper(
            blank,
            list(data[:reader]),
            data[reader],
            [],
            StrictStackQueue.from_iterable(data[reader + 1 :]),
        )

    @property
    def reader_symbol(self) -> T:
        return self.current

    @property
    def writer_symbol(self) -> T:
        return self.blank

    def _record(self, before_self: int, before_queue: int) -> None:
        amount = (self.primitive_steps - before_self) + (
            self.queue.primitive_steps - before_queue
        )
        self.maximum_primitives_per_operation = max(
            self.maximum_primitives_per_operation, amount
        )

    def append(self, value: T) -> None:
        if value == self.blank:
            raise ValueError("appending blank")
        a, b = self.primitive_steps, self.queue.primitive_steps
        self.queue.snoc(value)
        self._record(a, b)

    def move_left(self) -> None:
        a, b = self.primitive_steps, self.queue.primitive_steps
        self.front.append(self.current)
        self.primitive_steps += 1
        if self.left:
            self.current = self.left.pop()
            self.primitive_steps += 1
        else:
            self.current = self.blank
        self._record(a, b)

    def move_right(self) -> None:
        a, b = self.primitive_steps, self.queue.primitive_steps
        self.left.append(self.current)
        self.primitive_steps += 1
        if self.front:
            self.current = self.front.pop()
            self.primitive_steps += 1
        elif not self.queue.is_empty:
            self.current = self.queue.head()
            self.queue.tail()
        else:
            self.current = self.blank
        self._record(a, b)

    def materialize(self) -> tuple[T, ...]:
        return tuple(self.left) + (self.current,) + tuple(reversed(self.front)) + self.queue.to_tuple()
