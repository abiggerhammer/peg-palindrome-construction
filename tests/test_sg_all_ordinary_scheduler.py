from construction_constants import scheduler_predictability_constant
from sg_scheduler_audit import scheduled_trace


def test_all_ordinary_workers_feed_galil_scheduler_with_proof_constant():
    word = '01100110011001100110011001100110'
    trace, events = scheduled_trace(
        word,
        scheduler_c=scheduler_predictability_constant(),
        background_scan_backend='ordinary_terminal',
        lemma32_backend='ordinary_checkpoint',
    )
    assert trace.outputs == tuple(
        int(prefix == prefix[::-1] and len(prefix) % 2 == 0)
        for prefix in (word[:i] for i in range(1, len(word) + 1))
    )
    assert tuple(event.output for event in events) == trace.outputs


def test_all_ordinary_trace_exercises_slow_mode_on_zero_output_family():
    # This word has no even-palindromic prefix.  A deliberately small audit
    # constant therefore lets us exercise the literal SLOW/speculative-zero
    # controller without changing the correct output sequence.
    word = '01000100101101001010010010110100'
    trace, events = scheduled_trace(
        word,
        scheduler_c=64,
        background_scan_backend='ordinary_terminal',
        lemma32_backend='ordinary_checkpoint',
        background_work_budget=200000,
    )
    assert not any(trace.outputs)
    assert tuple(event.output for event in events) == trace.outputs
    assert any(event.speculative for event in events)
