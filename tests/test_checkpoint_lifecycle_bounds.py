import itertools

import checkpoint_ordinary_tm as cp
import checkpoint_reusable_tm as reusable
from checkpoint_lifecycle_bounds import (
    local_lifecycle_bound,
    one_shot_bound,
    recover_checkpoint_lifecycle_bound,
    registered_execute_and_retire_bound,
    retirement_bound,
)


def words_up_to(length: int):
    for n in range(1, length + 1):
        for bits in itertools.product("01", repeat=n):
            yield "".join(bits)


def assert_clean_ready(cfg):
    assert cfg.state == reusable.READY
    # Axes retain only their origin marker and scan it.
    for tape in reusable.AXES:
        assert cfg.tapes[tape] == {0: cp.MARK}
        assert cfg.heads[tape] == 0
    # Prepared pattern epochs are erased; each head scans the blank after the
    # retained sentinel.
    for tape in reusable.PATTERNS:
        assert cfg.tapes[tape] == {0: cp.SENTINEL}
        assert cfg.heads[tape] == 1
    assert cfg.tapes[cp.SRC_FWD].get(cfg.heads[cp.SRC_FWD]) == cp.END
    assert cfg.tapes[cp.SRC_FWD2].get(cfg.heads[cp.SRC_FWD2]) == cp.END
    assert cfg.tapes[cp.SRC_REV].get(cfg.heads[cp.SRC_REV]) == cp.SENTINEL
    # Every Algorithm-Y work tape begins a fresh logical epoch.  S/T/U scan
    # the virgin blank just right of a new MARK.  Stack/counter tapes scan
    # either their new BOTTOM or the fixed initial top above it.
    for run in cp.RUN_NAMES:
        for local in range(2, 5):
            tape = cp.y_global_tape(run, local)
            head = cfg.heads[tape]
            assert cfg.tapes[tape].get(head - 1) == cp.MARK
            assert cfg.tapes[tape].get(head, cp.BLANK) == cp.BLANK
        for local in range(5, 17):
            tape = cp.y_global_tape(run, local)
            head = cfg.heads[tape]
            initial = reusable._initial_stack_value(local)
            if initial is None:
                assert cfg.tapes[tape].get(head) == reusable.BOTTOM
            else:
                assert cfg.tapes[tape].get(head) == initial
                assert cfg.tapes[tape].get(head - 1) == reusable.BOTTOM


def test_one_shot_and_retirement_bounds_exhaustive_short():
    for word in words_up_to(6):
        cfg = reusable.initial_configuration(word)
        e = reusable.run_to_result(cfg)
        assert e <= one_shot_bound(len(word))
        before = cfg.steps
        reusable.retire_result(cfg)
        r = cfg.steps - before
        assert r <= retirement_bound(len(word), e)
        assert 1 + e + r <= local_lifecycle_bound(len(word))
        assert_clean_ready(cfg)


def test_clean_ready_start_is_constant_after_different_old_epochs():
    for old_word in ("0", "0" * 5, "01" * 13, "0" * 55):
        cfg = reusable.initial_configuration(old_word)
        reusable.run_to_result(cfg)
        reusable.retire_result(cfg)
        assert_clean_ready(cfg)
        new_word = old_word + "1"
        before = cfg.steps
        reusable.request_extended(cfg, new_word)
        assert cfg.state == cp.INITIAL
        assert cfg.steps - before == 1


def test_affine_bounds_are_positive_and_nested():
    for n in (1, 2, 16, 1000):
        assert one_shot_bound(n) > 0
        assert registered_execute_and_retire_bound(n) >= 2 * one_shot_bound(n)
        assert recover_checkpoint_lifecycle_bound(n) > registered_execute_and_retire_bound(n)
