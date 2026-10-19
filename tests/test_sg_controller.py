from sg_controller import Worker, sg_control_table
from sg_zero_ratio import UpdateCase


def test_sg_controller_is_total_and_finite():
    assert len(sg_control_table()) == 2**4


def test_unknown_second_selects_only_background_or_recovery():
    table = sg_control_table()
    for bp_ok in (False, True):
        for large in (False, True):
            assert table[(False, True, bp_ok, large)].worker is Worker.ADVANCE_BACKGROUND
            assert table[(False, False, bp_ok, large)].worker is Worker.RECOVER


def test_small_case_three_launches_local_worker():
    action = sg_control_table()[(True, False, True, False)]
    assert action.case is UpdateCase.THREE_SECOND_SURVIVES
    assert action.worker is Worker.LOCAL
    assert action.promote_second
