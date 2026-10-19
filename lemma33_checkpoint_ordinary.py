"""Persistent Lemma 3.3 scheduler driven by the reusable ordinary checkpoint TM.

This is the composition checkpoint between table production stages.  Every
SEARCH tick is one row of ``checkpoint_reusable_tm``; no checkpoint result is
precomputed or restarted at intermediate prefixes.  The finite phase changes
are selected from ``lemma33_controller.persistent_control_table``.

The surrounding input-history terminal is still represented by a Python string
in this audit executor.  It supplies the period-comparison symbols used during
CATCH_UP/FOLLOW and bulk-updates the three checkpoint source terminals only
when a new frozen scan launches.  The next lowering stage replaces that
terminal by the already developed strict append/read zipper.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
import json
from pathlib import Path

import checkpoint_ordinary_tm as cp
from checkpoint_reusable_tm import (
    READY,
    RESULT_READY,
    ReusableCheckpointConfiguration,
    initial_configuration as checkpoint_initial,
    request_extended,
    request_retire,
    result as checkpoint_result,
    step as checkpoint_step,
)
from construction_constants import background_steps_per_input
from lemma33_controller import (
    ControlPhase,
    ControlState,
    ScanResult,
    persistent_control_table,
)
from lemma33_t1 import lemma33_t1_discovered_gap


class Phase(Enum):
    BOOTSTRAP = auto()
    SEARCH = auto()
    CLEANUP = auto()
    CATCH_UP_GOOD = auto()
    CATCH_UP_BAD = auto()
    FOLLOW_GOOD = auto()
    FOLLOW_BAD = auto()


CONTROL_PHASE = {
    Phase.BOOTSTRAP: ControlPhase.BOOTSTRAP,
    Phase.SEARCH: ControlPhase.SEARCH,
    Phase.CATCH_UP_GOOD: ControlPhase.CATCH_UP_GOOD,
    Phase.CATCH_UP_BAD: ControlPhase.CATCH_UP_BAD,
    Phase.FOLLOW_GOOD: ControlPhase.FOLLOW_GOOD,
    Phase.FOLLOW_BAD: ControlPhase.FOLLOW_BAD,
}
INVERSE_PHASE = {value: key for key, value in CONTROL_PHASE.items()}


@dataclass(frozen=True)
class OrdinaryBackgroundStep:
    length: int
    phase_before: Phase
    phase_after: Phase
    output_gap: int | None
    ordinary_steps: int
    checkpoint_length: int | None
    candidate: int | None
    target_length: int | None
    launches: int

    @property
    def work_spent(self) -> int:
        return self.ordinary_steps


class PersistentLemma33CheckpointOrdinary:
    """Retained c=16 checkpoint execution over literal ordinary TM rows."""

    def __init__(
        self,
        *,
        initial: str = "",
        work_budget: int | None = None,
        bootstrap_limit: int = 0,
        audit: bool = False,
    ) -> None:
        if bootstrap_limit < 0:
            raise ValueError(bootstrap_limit)
        self.c = 16
        self.work_budget = background_steps_per_input(16) if work_budget is None else work_budget
        if self.work_budget <= 0:
            raise ValueError(self.work_budget)
        self.bootstrap_limit = bootstrap_limit
        self.audit = audit
        if any(ch not in "01" for ch in initial):
            raise ValueError(initial)
        self.word = initial
        self.phase = Phase.BOOTSTRAP
        self.checkpoint: ReusableCheckpointConfiguration | None = None
        self.checkpoint_length: int | None = None
        self.candidate: int | None = None
        self.target_length: int | None = None
        self.catchup_index: int | None = None
        self.launches = 0
        self._after_cleanup: Phase | str | None = None
        self._table = persistent_control_table()
        if self.word and len(self.word) >= max(1, self.bootstrap_limit):
            self._launch()

    def _launch(self) -> None:
        if not self.word:
            return
        if self.checkpoint is None:
            self.checkpoint = checkpoint_initial(self.word)
        else:
            assert self.checkpoint.state == READY
            request_extended(self.checkpoint, self.word)
        self.checkpoint_length = len(self.word)
        self.candidate = None
        self.target_length = None
        self.catchup_index = None
        self.phase = Phase.SEARCH
        self.launches += 1

    def _control(
        self,
        *,
        scan_result: ScanResult = ScanResult.RUNNING,
        catchup_done: bool = False,
        target_now: bool = False,
        period_match: bool = True,
        bootstrap_done: bool = False,
    ):
        key = (
            ControlState(CONTROL_PHASE[self.phase]),
            bootstrap_done,
            scan_result,
            catchup_done,
            target_now,
            period_match,
        )
        return self._table[key]

    def _set_phase_from_action(self, action) -> None:
        self.phase = INVERSE_PHASE[action.next_state.phase]

    def _begin_cleanup(self, after: Phase | str) -> None:
        assert self.checkpoint is not None and self.checkpoint.state == RESULT_READY
        request_retire(self.checkpoint)
        self._after_cleanup = after
        self.phase = Phase.CLEANUP

    def _install_ready_scan(self) -> tuple[int | None, bool]:
        assert self.checkpoint is not None and self.checkpoint.state == RESULT_READY
        scan = checkpoint_result(self.checkpoint)
        d = scan.candidate
        if d is None:
            action = self._control(scan_result=ScanResult.NONE)
            assert action.launch_scan and action.clear_candidate
            self._set_phase_from_action(action)
            self._begin_cleanup("launch")
            return None, False

        target = self.c * d
        if target < len(self.word):
            raise AssertionError(("ordinary checkpoint missed target", self.checkpoint_length, len(self.word), d))
        self.candidate = d
        self.target_length = target
        assert self.checkpoint_length is not None
        self.catchup_index = self.checkpoint_length
        action = self._control(scan_result=ScanResult.FUTURE)
        assert action.install_candidate
        self._set_phase_from_action(action)
        after = self.phase
        self._begin_cleanup(after)
        return None, False

    def _tick_cleanup(self) -> tuple[int | None, bool]:
        assert self.checkpoint is not None
        if self.checkpoint.state != READY:
            checkpoint_step(self.checkpoint)
            return None, False
        after = self._after_cleanup
        self._after_cleanup = None
        if after == "launch":
            self.phase = Phase.SEARCH
            self._launch()
            return None, True
        if not isinstance(after, Phase):
            raise AssertionError(after)
        self.phase = after
        return None, False

    def _tick_catchup(self) -> tuple[int | None, bool]:
        assert self.candidate is not None and self.target_length is not None
        assert self.catchup_index is not None
        good = self.phase is Phase.CATCH_UP_GOOD
        if self.catchup_index < len(self.word):
            i = self.catchup_index
            period = 2 * self.candidate
            match = i < period or self.word[i] == self.word[i - period]
            self.catchup_index += 1
            if good and not match:
                self.phase = Phase.CATCH_UP_BAD
            return None, False

        target_now = len(self.word) == self.target_length
        action = self._control(catchup_done=True, target_now=target_now, period_match=True)
        output = self.candidate if action.emit_gap else None
        launch = action.launch_scan
        self._set_phase_from_action(action)
        if launch:
            self._launch()
            return output, True
        self.catchup_index = None
        return output, False

    def _spend(self) -> tuple[int, int | None]:
        start_steps = self.checkpoint.steps if self.checkpoint is not None else 0
        spent = 0
        output: int | None = None
        stop = False
        while spent < self.work_budget and not stop:
            before = self.checkpoint.steps if self.checkpoint is not None else 0
            if self.phase is Phase.SEARCH:
                assert self.checkpoint is not None
                if self.checkpoint.state != RESULT_READY:
                    checkpoint_step(self.checkpoint)
                if self.checkpoint.state == RESULT_READY:
                    output, stop = self._install_ready_scan()
            elif self.phase is Phase.CLEANUP:
                output, stop = self._tick_cleanup()
            elif self.phase in (Phase.CATCH_UP_GOOD, Phase.CATCH_UP_BAD):
                output, stop = self._tick_catchup()
                # Catch-up is one retained logical transition when it does not
                # touch the checkpoint component.
                if self.checkpoint is not None and self.checkpoint.steps == before:
                    self.checkpoint.steps += 1
            else:
                break
            after = self.checkpoint.steps if self.checkpoint is not None else before
            spent += after - before
        return (self.checkpoint.steps - start_steps if self.checkpoint is not None else spent), output

    def feed(self, symbol: str) -> OrdinaryBackgroundStep:
        if symbol not in "01":
            raise ValueError(symbol)
        before = self.phase
        self.word += symbol
        spent = 0
        output: int | None = None

        if self.phase is Phase.BOOTSTRAP:
            if self.bootstrap_limit and len(self.word) <= self.bootstrap_limit:
                # This is a finite lookup region.  It is used only in audit
                # configurations; production tests set bootstrap_limit=0.
                output = lemma33_t1_discovered_gap(self.word, self.c)
            if len(self.word) >= max(1, self.bootstrap_limit):
                action = self._control(bootstrap_done=True)
                assert action.launch_scan
                self._set_phase_from_action(action)
                self._launch()

        elif self.phase in (Phase.SEARCH, Phase.CLEANUP, Phase.CATCH_UP_GOOD, Phase.CATCH_UP_BAD):
            spent, output = self._spend()

        elif self.phase in (Phase.FOLLOW_GOOD, Phase.FOLLOW_BAD):
            assert self.candidate is not None and self.target_length is not None
            period = 2 * self.candidate
            i = len(self.word) - 1
            match = i < period or self.word[i] == self.word[i - period]
            target_now = len(self.word) == self.target_length
            action = self._control(target_now=target_now, period_match=match)
            output = self.candidate if action.emit_gap else None
            launch = action.launch_scan
            self._set_phase_from_action(action)
            if launch:
                self._launch()
            elif len(self.word) > self.target_length:
                raise AssertionError((len(self.word), self.target_length, self.candidate))
        else:  # pragma: no cover
            raise AssertionError(self.phase)

        if self.audit:
            expected = lemma33_t1_discovered_gap(self.word, self.c)
            assert output == expected, (
                self.word, before, self.phase, output, expected,
                self.candidate, self.target_length,
            )

        return OrdinaryBackgroundStep(
            len(self.word), before, self.phase, output, spent,
            self.checkpoint_length, self.candidate, self.target_length, self.launches,
        )


def export_summary(path: str | Path = "generated/lemma33_checkpoint_ordinary_summary.json") -> dict:
    from checkpoint_reusable_tm import enumerate_reachable

    states, rows = enumerate_reachable()
    data = {
        "model": "persistent Lemma 3.3 controller around reusable ordinary checkpoint TM",
        "c": 16,
        "checkpoint_tapes": 64,
        "checkpoint_states": len(states),
        "checkpoint_sparse_rows": rows,
        "finite_controller_entries": len(persistent_control_table()),
        "checkpoint_restarts_at_intermediate_prefixes": False,
        "ordinary_checkpoint_rows_per_search_tick": 1,
        "remaining_terminal_lowering": "input-history append/read zipper for catch-up and launch copying",
    }
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


if __name__ == "__main__":
    for sample in ("0000000000000000", "0110" * 8, "0100010010110100"):
        m = PersistentLemma33CheckpointOrdinary(work_budget=200000, audit=True)
        out = [m.feed(ch).output_gap for ch in sample]
        print(sample, [(i + 1, d) for i, d in enumerate(out) if d is not None])
    print(export_summary())
