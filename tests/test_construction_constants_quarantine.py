from construction_constants import (
    CHECKPOINT_STEPS_PER_SYMBOL,
    background_steps_per_input,
    scheduler_predictability_constant,
)
from checkpoint_lifecycle_bounds import one_shot_bound


def test_legacy_2048_constant_only_bounds_one_shot_body():
    for n in (1, 2, 16, 1000):
        assert one_shot_bound(n) <= CHECKPOINT_STEPS_PER_SYMBOL * n
    assert background_steps_per_input() > 0


def test_scheduler_constant_is_certified():
    assert scheduler_predictability_constant() == 1_781_819_703
