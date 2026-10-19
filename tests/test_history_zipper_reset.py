import history_zipper_ordinary_tm as hz


def test_reset_starts_fresh_epoch_without_traversing_old_history():
    config = hz.initial_configuration(("#",), reader=0)
    for command in ("APPEND0", "APPEND1", "APPEND1", "LEFT", "RIGHT", "APPEND0"):
        hz.run_command(config, command)
    old_heads = tuple(config.heads)
    steps = hz.run_command(config, "RESET")
    assert steps == 2
    assert hz.materialize(config) == ("#",)
    assert tuple(config.heads) == tuple(h + 1 for h in old_heads)
    for tape, head in zip(config.tapes, config.heads):
        assert tape[head] == hz.BOTTOM
    hz.run_command(config, "APPEND1")
    assert hz.materialize(config) == ("#", "1")
