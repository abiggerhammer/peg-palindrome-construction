"""Literal finite controller for the specialized six-case SG read loop.

Unbounded data (B3/B3' head locations, the active-suffix length, and worker
results) remain on tapes.  The controller sees only finite signals produced by
those heads and chooses which already-lowered worker to launch.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum, auto
import json
from pathlib import Path

from sg_zero_ratio import UpdateCase


class Worker(Enum):
    NONE = auto()
    RECOVER = auto()
    LOCAL = auto()
    START_BACKGROUND = auto()
    ADVANCE_BACKGROUND = auto()


@dataclass(frozen=True)
class SGControlAction:
    case: UpdateCase
    worker: Worker
    promote_second: bool
    retain_second: bool
    second_known_after: bool | None


def sg_control_table() -> dict[
    tuple[bool, bool, bool, bool], SGControlAction
]:
    """Return the total finite decision table.

    Key fields are ``(second_known, b_survives, bp_survives, gap_large)``.
    ``bp_survives`` and ``gap_large`` are ignored when their corresponding
    values are unavailable, but retaining them in the key makes the table easy
    to inline into a conventional complete transition function.

    For LOCAL and BACKGROUND actions, ``second_known_after`` is ``None`` until
    the worker emits its one-bit ``found`` signal.
    """

    table: dict[tuple[bool, bool, bool, bool], SGControlAction] = {}
    for known in (False, True):
        for b_ok in (False, True):
            for bp_ok in (False, True):
                for large in (False, True):
                    if not known:
                        if b_ok:
                            action = SGControlAction(
                                UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES,
                                Worker.ADVANCE_BACKGROUND,
                                False,
                                False,
                                None,
                            )
                        else:
                            action = SGControlAction(
                                UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS,
                                Worker.RECOVER,
                                False,
                                False,
                                True,
                            )
                    elif b_ok and bp_ok:
                        action = SGControlAction(
                            UpdateCase.ONE_BOTH_SURVIVE,
                            Worker.NONE,
                            False,
                            True,
                            True,
                        )
                    elif not b_ok and not bp_ok:
                        action = SGControlAction(
                            UpdateCase.TWO_BOTH_FAIL,
                            Worker.RECOVER,
                            False,
                            False,
                            True,
                        )
                    elif not b_ok and bp_ok:
                        if large:
                            action = SGControlAction(
                                UpdateCase.THREE_SECOND_SURVIVES,
                                Worker.RECOVER,
                                True,
                                False,
                                True,
                            )
                        else:
                            action = SGControlAction(
                                UpdateCase.THREE_SECOND_SURVIVES,
                                Worker.LOCAL,
                                True,
                                False,
                                None,
                            )
                    else:
                        action = SGControlAction(
                            UpdateCase.FOUR_FIRST_SURVIVES,
                            Worker.START_BACKGROUND,
                            False,
                            False,
                            False,
                        )
                    table[(known, b_ok, bp_ok, large)] = action
    return table


def export_sg_control_table(path: str | Path) -> None:
    rows = []
    for key, action in sg_control_table().items():
        known, b_ok, bp_ok, large = key
        rows.append(
            {
                "second_known": known,
                "b_survives": b_ok,
                "bp_survives": bp_ok,
                "gap_large": large,
                "action": {
                    **asdict(action),
                    "case": action.case.name,
                    "worker": action.worker.name,
                },
            }
        )
        rows[-1]["action"]["case"] = action.case.name
        rows[-1]["action"]["worker"] = action.worker.name
    Path(path).write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    export_sg_control_table("generated/sg_zero_ratio_control.json")
