from collections import deque
import random

from append_read_zipper import AppendReadZipper
from hood_melville_queue import RTQueue


def test_realtime_queue_exhaustive_small_sequences():
    def visit(q, ref, depth):
        assert q.to_tuple() == tuple(ref)
        if depth == 0:
            return
        for value in (0, 1):
            visit(q.snoc(value), ref + [value], depth - 1)
        if ref:
            visit(q.tail(), ref[1:], depth - 1)

    visit(RTQueue.empty(), [], 8)


def test_realtime_queue_random_and_two_rotation_steps_per_operation():
    rng = random.Random(7)
    q = RTQueue.empty()
    ref = deque()
    for _ in range(5000):
        before = q.rotation_steps
        if not ref or rng.random() < 0.62:
            value = rng.randrange(4)
            q = q.snoc(value)
            ref.append(value)
        else:
            assert q.head() == ref[0]
            q = q.tail()
            ref.popleft()
        assert q.rotation_steps - before <= 2
        assert q.to_tuple() == tuple(ref)


def test_append_read_zipper_against_materialized_tape():
    z = AppendReadZipper.from_cells("#010", reader=1, writer=4, blank="_")
    tape = list("#010")
    reader = 1
    rng = random.Random(19)

    for _ in range(3000):
        choices = ["append"]
        if reader > 0:
            choices.append("left")
        if reader + 1 < len(tape):  # source invariant: reader stays left of writer
            choices.append("right")
        op = rng.choice(choices)
        if op == "append":
            value = rng.choice("01")
            z = z.append(value)
            tape.append(value)
        elif op == "left":
            z = z.move_left()
            reader -= 1
        else:
            z = z.move_right()
            reader += 1
        assert z.reader_symbol == tape[reader]
        assert "".join(z.materialize()) == "".join(tape)
