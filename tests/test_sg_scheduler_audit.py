from itertools import product

from sg_scheduler_audit import scheduled_outputs, scheduled_trace, source_trace


def test_source_trace_outputs_even_palindromic_prefixes():
    for n in range(9):
        for bits in product("01", repeat=n):
            word = "".join(bits)
            trace = source_trace(word)
            assert trace.outputs == tuple(
                int(prefix == prefix[::-1] and len(prefix) % 2 == 0)
                for prefix in (word[:i] for i in range(1, len(word) + 1))
            )


def test_scheduler_table_preserves_outputs_on_representative_long_trace():
    # This family produces long recovery scans.  A deliberately small scheduler
    # constant forces genuine speculative-zero/SLOW-mode execution.
    word = "010000000" * 60
    trace, events = scheduled_trace(word, scheduler_c=1000)
    assert any(event.speculative for event in events)
    assert tuple(event.output for event in events) == trace.outputs
