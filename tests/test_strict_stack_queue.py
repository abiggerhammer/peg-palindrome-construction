from collections import deque
import random

from hood_melville_queue import RTQueue
from strict_stack_queue import StrictStackQueue


def test_strict_stack_queue_random_against_deque_and_functional_queue():
    rng = random.Random(23)
    q = StrictStackQueue.empty()
    f = RTQueue.empty()
    ref = deque()
    for step in range(8000):
        if not ref or rng.random() < 0.59:
            x = rng.randrange(5)
            q.snoc(x)
            f = f.snoc(x)
            ref.append(x)
        else:
            assert q.head() == f.head() == ref[0]
            q.tail()
            f = f.tail()
            ref.popleft()
        assert q.is_empty == (not ref)
        if ref:
            assert q.head() == f.head() == ref[0]
        if step % 97 == 0:
            assert q.to_tuple() == f.to_tuple() == tuple(ref)
    assert q.to_tuple() == f.to_tuple() == tuple(ref)
    # Bound is independent of queue length.  The current primitive accounting
    # counts each individual push/pop/counter update separately.
    assert q.maximum_primitives_per_operation <= 20
