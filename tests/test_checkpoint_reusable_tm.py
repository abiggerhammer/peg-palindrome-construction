from itertools import product

import checkpoint_ordinary_tm as one
from checkpoint_reusable_tm import (
    READY,
    RESULT_READY,
    initial_configuration,
    launch_extended,
    request_extended,
    result,
    retire_result,
    run_to_result,
)


def _finish_and_retire(cfg):
    assert cfg.state == RESULT_READY
    retire_result(cfg)
    assert cfg.state == READY


def test_reusable_successive_zero_prefixes():
    cfg = initial_configuration("0")
    run_to_result(cfg)
    assert result(cfg).gaps == one.run_checkpoint_ordinary("0").gaps
    _finish_and_retire(cfg)
    for n in range(2, 18):
        word = "0" * n
        launch_extended(cfg, word)
        expected = one.run_checkpoint_ordinary(word)
        actual = result(cfg)
        assert actual.gaps == expected.gaps
        assert actual.candidate == expected.candidate
        _finish_and_retire(cfg)


def test_reusable_mixed_monotone_prefixes():
    for bits in product("01", repeat=6):
        word = "".join(bits)
        cfg = initial_configuration(word[:1])
        run_to_result(cfg)
        _finish_and_retire(cfg)
        for n in range(2, len(word) + 1):
            launch_extended(cfg, word[:n])
            expected = one.run_checkpoint_ordinary(word[:n])
            actual = result(cfg)
            assert actual.gaps == expected.gaps, (word, n)
            assert actual.candidate == expected.candidate, (word, n)
            _finish_and_retire(cfg)


def test_clean_ready_starts_next_request_in_one_checkpoint_transition():
    cfg = initial_configuration("01010")
    run_to_result(cfg)
    retire_result(cfg)
    assert cfg.state == READY

    before = cfg.steps
    request_extended(cfg, "010101")
    assert cfg.steps - before == 1
    assert cfg.state == one.INITIAL


def test_result_axes_survive_until_explicit_retirement():
    cfg = initial_configuration("0000000000000000")
    run_to_result(cfg)
    expected = result(cfg)
    assert cfg.state == RESULT_READY
    # No cleanup begins merely because the result is observed.
    assert result(cfg) == expected
    retire_result(cfg)
    assert cfg.state == READY
