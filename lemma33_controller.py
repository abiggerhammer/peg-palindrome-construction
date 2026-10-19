"""Finite-control shell for the persistent equal-input Lemma 3.3 job.

The unbounded quantities used by the checkpoint construction (remaining scan
work, checkpoint length, candidate gap, and target length) live on ordinary
unary work tapes in the eventual machine.  Once comparisons on those tapes are
presented as finite signals, all phase changes are governed by the literal
finite table generated here.

This module intentionally separates *control* from the scan submachine.  It
closes a common source of hidden power in algorithm descriptions: phrases such
as "if the scan finishes", "catch up", and "continue the periodicity" are no
longer host-language branches in the controller.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum, auto
import json
from pathlib import Path


class ControlPhase(Enum):
    BOOTSTRAP = auto()
    SEARCH = auto()
    CATCH_UP_GOOD = auto()
    CATCH_UP_BAD = auto()
    FOLLOW_GOOD = auto()
    FOLLOW_BAD = auto()


class ScanResult(Enum):
    RUNNING = auto()
    NONE = auto()
    FUTURE = auto()
    NOW_GOOD = auto()
    NOW_BAD = auto()
    MISSED = auto()


@dataclass(frozen=True)
class ControlState:
    phase: ControlPhase


@dataclass(frozen=True)
class ControlAction:
    next_state: ControlState
    emit_gap: bool
    launch_scan: bool
    spend_scan_step: bool
    install_candidate: bool
    clear_candidate: bool


def persistent_control_table() -> dict[
    tuple[ControlState, bool, ScanResult, bool, bool, bool], ControlAction
]:
    """Return the complete finite phase controller.

    Keys are ``(state, bootstrap_done, scan_result, catchup_done,
    target_now, period_match)``.  The unbounded counters producing these
    signals live on work tapes; the phase logic itself is finite.
    """

    table: dict[
        tuple[ControlState, bool, ScanResult, bool, bool, bool], ControlAction
    ] = {}
    for phase in ControlPhase:
        state = ControlState(phase)
        for bootstrap_done in (False, True):
            for result in ScanResult:
                for catchup_done in (False, True):
                    for target_now in (False, True):
                        for period_match in (False, True):
                            if phase is ControlPhase.BOOTSTRAP:
                                action = ControlAction(
                                    ControlState(
                                        ControlPhase.SEARCH
                                        if bootstrap_done
                                        else ControlPhase.BOOTSTRAP
                                    ),
                                    False,
                                    bootstrap_done,
                                    False,
                                    False,
                                    bootstrap_done,
                                )

                            elif phase is ControlPhase.SEARCH:
                                if result is ScanResult.RUNNING:
                                    action = ControlAction(state, False, False, True, False, False)
                                elif result is ScanResult.NONE:
                                    action = ControlAction(state, False, True, False, False, True)
                                elif result is ScanResult.FUTURE:
                                    action = ControlAction(
                                        ControlState(ControlPhase.CATCH_UP_GOOD),
                                        False, False, False, True, False,
                                    )
                                elif result is ScanResult.NOW_GOOD:
                                    action = ControlAction(state, True, True, False, False, True)
                                else:  # NOW_BAD or unreachable MISSED
                                    action = ControlAction(state, False, True, False, False, True)

                            elif phase in (
                                ControlPhase.CATCH_UP_GOOD,
                                ControlPhase.CATCH_UP_BAD,
                            ):
                                good_before = phase is ControlPhase.CATCH_UP_GOOD
                                good_after = good_before and period_match
                                if catchup_done and target_now:
                                    action = ControlAction(
                                        ControlState(ControlPhase.SEARCH),
                                        good_after,
                                        True,
                                        False,
                                        False,
                                        True,
                                    )
                                elif catchup_done:
                                    action = ControlAction(
                                        ControlState(
                                            ControlPhase.FOLLOW_GOOD
                                            if good_after
                                            else ControlPhase.FOLLOW_BAD
                                        ),
                                        False, False, False, False, False,
                                    )
                                else:
                                    action = ControlAction(
                                        ControlState(
                                            ControlPhase.CATCH_UP_GOOD
                                            if good_after
                                            else ControlPhase.CATCH_UP_BAD
                                        ),
                                        False, False, False, False, False,
                                    )

                            else:
                                good_before = phase is ControlPhase.FOLLOW_GOOD
                                good_after = good_before and period_match
                                if target_now:
                                    action = ControlAction(
                                        ControlState(ControlPhase.SEARCH),
                                        good_after,
                                        True,
                                        False,
                                        False,
                                        True,
                                    )
                                else:
                                    action = ControlAction(
                                        ControlState(
                                            ControlPhase.FOLLOW_GOOD
                                            if good_after
                                            else ControlPhase.FOLLOW_BAD
                                        ),
                                        False, False, False, False, False,
                                    )

                            table[(
                                state,
                                bootstrap_done,
                                result,
                                catchup_done,
                                target_now,
                                period_match,
                            )] = action
    return table


def export_control_table(path: str | Path) -> None:
    table = persistent_control_table()
    rows = []
    for (
        state,
        bootstrap_done,
        result,
        catchup_done,
        target_now,
        period_match,
    ), action in table.items():
        rows.append(
            {
                "state": state.phase.name,
                "bootstrap_done": bootstrap_done,
                "scan_result": result.name,
                "catchup_done": catchup_done,
                "target_now": target_now,
                "period_match": period_match,
                "action": {
                    **asdict(action),
                    "next_state": action.next_state.phase.name,
                },
            }
        )
        rows[-1]["action"].pop("next_state", None)
        rows[-1]["action"]["next_state"] = action.next_state.phase.name
    Path(path).write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    export_control_table("generated/lemma33_persistent_control.json")
