from constant_speedup import (
    MACRO_CAPACITY,
    SPEEDUP_HALVINGS,
    SPEEDUP_SLACK,
    certificate_dict,
)
from scheduled_source_composition import BOUNDED_DELAY_TRANSITIONS


def test_fixed_speedup_application_is_exact():
    cert = certificate_dict()
    assert SPEEDUP_HALVINGS == 39
    assert MACRO_CAPACITY == 2**39
    assert MACRO_CAPACITY >= BOUNDED_DELAY_TRANSITIONS
    assert MACRO_CAPACITY // 2 < BOUNDED_DELAY_TRANSITIONS
    assert SPEEDUP_SLACK == MACRO_CAPACITY - BOUNDED_DELAY_TRANSITIONS
    assert cert["macrosteps_per_input"] == 1
    assert all(cert["side_conditions"].values())
    assert "three shifted" not in cert["construction"]
