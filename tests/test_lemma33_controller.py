from lemma33_controller import (
    ControlPhase,
    ControlState,
    ScanResult,
    persistent_control_table,
)


def _action(
    phase,
    *,
    done=False,
    result=ScanResult.RUNNING,
    caught=False,
    target=False,
    match=True,
):
    return persistent_control_table()[
        (ControlState(phase), done, result, caught, target, match)
    ]


def test_control_table_is_literal_and_total() -> None:
    table = persistent_control_table()
    assert len(table) == 6 * 2 * 6 * 2 * 2 * 2


def test_scan_is_retained_until_completion() -> None:
    action = _action(ControlPhase.SEARCH, result=ScanResult.RUNNING)
    assert action.next_state.phase is ControlPhase.SEARCH
    assert action.spend_scan_step
    assert not action.launch_scan


def test_completed_empty_scan_restarts_once() -> None:
    action = _action(ControlPhase.SEARCH, result=ScanResult.NONE)
    assert action.launch_scan and action.clear_candidate
    assert not action.emit_gap


def test_candidate_enters_explicit_catchup() -> None:
    action = _action(ControlPhase.SEARCH, result=ScanResult.FUTURE)
    assert action.next_state.phase is ControlPhase.CATCH_UP_GOOD
    assert action.install_candidate


def test_candidate_whose_target_is_current_emits_without_one_symbol_delay() -> None:
    good = _action(ControlPhase.SEARCH, result=ScanResult.NOW_GOOD)
    bad = _action(ControlPhase.SEARCH, result=ScanResult.NOW_BAD)
    assert good.emit_gap and good.launch_scan
    assert not bad.emit_gap and bad.launch_scan


def test_catchup_and_follow_remember_a_mismatch_in_finite_control() -> None:
    mismatch = _action(ControlPhase.CATCH_UP_GOOD, caught=False, match=False)
    assert mismatch.next_state.phase is ControlPhase.CATCH_UP_BAD
    caught = _action(ControlPhase.CATCH_UP_BAD, caught=True, target=False, match=True)
    assert caught.next_state.phase is ControlPhase.FOLLOW_BAD
    at_target = _action(ControlPhase.FOLLOW_BAD, target=True, match=True)
    assert not at_target.emit_gap and at_target.launch_scan
