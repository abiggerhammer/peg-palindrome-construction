"""One-reader/append-only-writer tape via stacks and a real-time queue.

The represented tape segment is

    reverse(left) + current + front + queue

where ``left`` and ``front`` are ordinary stacks and ``queue`` is a strict
real-time FIFO.  The writer is always at the blank immediately after the queue.
The reader may move in either direction.  Every operation performs O(1) stack
or queue-state steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterable, TypeVar

from hood_melville_queue import RTQueue

T = TypeVar("T")


@dataclass(frozen=True)
class AppendReadZipper(Generic[T]):
    blank: T
    left: tuple[T, ...]
    current: T
    front: tuple[T, ...]
    queue: RTQueue[T]

    @staticmethod
    def from_cells(
        cells: Iterable[T], *, reader: int, writer: int, blank: T
    ) -> "AppendReadZipper[T]":
        data = tuple(cells)
        if not (0 <= reader < writer <= len(data)):
            raise ValueError((reader, writer, len(data)))
        # Writer points at the first blank after the represented data.
        if writer != len(data):
            raise ValueError("reference initializer expects writer at end")
        return AppendReadZipper(
            blank=blank,
            left=tuple(reversed(data[:reader])),
            current=data[reader],
            front=(),
            queue=RTQueue.from_iterable(data[reader + 1 : writer]),
        )

    @property
    def reader_symbol(self) -> T:
        return self.current

    @property
    def writer_symbol(self) -> T:
        return self.blank

    def append(self, value: T) -> "AppendReadZipper[T]":
        if value == self.blank:
            raise ValueError("appending blank is not a write")
        return AppendReadZipper(
            self.blank, self.left, self.current, self.front, self.queue.snoc(value)
        )

    def move_left(self) -> "AppendReadZipper[T]":
        if not self.left:
            new_current = self.blank
            new_left: tuple[T, ...] = ()
        else:
            new_current = self.left[0]
            new_left = self.left[1:]
        return AppendReadZipper(
            self.blank,
            new_left,
            new_current,
            (self.current,) + self.front,
            self.queue,
        )

    def move_right(self) -> "AppendReadZipper[T]":
        if self.front:
            new_current = self.front[0]
            new_front = self.front[1:]
            new_queue = self.queue
        elif not self.queue.is_empty:
            new_current = self.queue.head()
            new_front = ()
            new_queue = self.queue.tail()
        else:
            new_current = self.blank
            new_front = ()
            new_queue = self.queue
        return AppendReadZipper(
            self.blank,
            (self.current,) + self.left,
            new_current,
            new_front,
            new_queue,
        )

    def materialize(self) -> tuple[T, ...]:
        left = tuple(reversed(self.left))
        return left + (self.current,) + self.front + self.queue.to_tuple()
