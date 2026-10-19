from predictability_scheduler import Mode, schedule_trace, scheduled_bits


def test_all_fast() -> None:
    work = [1, 4, 2, 3]
    outputs = [1, 0, 1, 1]
    assert scheduled_bits(work, outputs, c=2) == outputs
    assert all(not event.speculative for event in schedule_trace(work, outputs, 2))


def test_slow_mode_catches_up_across_zero_run() -> None:
    # Position 0 is expensive.  The scheduler speculates positions 0 and 1 as
    # zero, then A catches up at position 2 and returns to fast mode.
    work = [9, 1, 1, 1, 1]
    outputs = [0, 0, 1, 0, 1]
    events = schedule_trace(work, outputs, c=2)
    assert [e.output for e in events] == outputs
    assert any(e.speculative for e in events)
    assert any(e.mode is Mode.SLOW and not e.speculative for e in events)


def test_multiple_slow_excursions() -> None:
    work = [7, 1, 1, 8, 1, 1, 1]
    outputs = [0, 0, 1, 0, 0, 1, 1]
    assert scheduled_bits(work, outputs, c=2) == outputs
