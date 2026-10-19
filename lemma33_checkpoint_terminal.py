"""Persistent Lemma 3.3 execution with an ordinary three-zipper history terminal.

Compared with ``lemma33_checkpoint_ordinary``, this executor removes both uses
of the host string as a storage terminal:

* source extensions are copied cell by cell from the COPY zipper into the
  three checkpoint source tapes;
* CATCH_UP and FOLLOW comparisons are performed by the CURRENT and LAG zipper
  readers.

The remaining host-level duties are finite phase dispatch and reading the
checkpoint's already produced output markers.  The next product stage inlines
those duties into the SG controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from checkpoint_reusable_tm import (
    READY,
    RESULT_READY,
    ReusableCheckpointConfiguration,
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
from ordinary_history_terminal import OrdinaryHistoryTerminal


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
class TerminalBackgroundStep:
    length: int
    phase_before: Phase
    phase_after: Phase
    output_gap: int | None
    ordinary_steps: int
    checkpoint_steps: int
    terminal_steps: int
    checkpoint_length: int | None
    candidate: int | None
    target_length: int | None
    launches: int

    @property
    def work_spent(self) -> int:
        return self.ordinary_steps


class PersistentLemma33CheckpointTerminal:
    def __init__(
        self,
        *,
        initial: str = "",
        work_budget: int | None = None,
        bootstrap_limit: int = 0,
        audit: bool = False,
    ) -> None:
        if any(ch not in "01" for ch in initial):
            raise ValueError(initial)
        if bootstrap_limit < 0:
            raise ValueError(bootstrap_limit)
        self.c = 16
        self.work_budget = background_steps_per_input(16) if work_budget is None else work_budget
        if self.work_budget <= 0:
            raise ValueError(self.work_budget)
        self.bootstrap_limit = bootstrap_limit
        self.audit = audit
        self.word = initial
        self.terminal = OrdinaryHistoryTerminal(initial)
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

    def _total_steps(self) -> int:
        return self.terminal.ordinary_steps + (
            self.checkpoint.steps if self.checkpoint is not None else 0
        )

    def _launch(self) -> int:
        if not self.word:
            return 0
        before = self._total_steps()
        if self.checkpoint is None:
            self.checkpoint, _ = self.terminal.initialize_checkpoint()
        else:
            assert self.checkpoint.state == READY
            self.terminal.request_extended_checkpoint(self.checkpoint)
        self.checkpoint_length = len(self.word)
        self.candidate = None
        self.target_length = None
        self.catchup_index = None
        self.phase = Phase.SEARCH
        self.launches += 1
        return self._total_steps() - before

    def _control(
        self,
        *,
        scan_result: ScanResult = ScanResult.RUNNING,
        catchup_done: bool = False,
        target_now: bool = False,
        period_match: bool = True,
        bootstrap_done: bool = False,
    ):
        return self._table[(
            ControlState(CONTROL_PHASE[self.phase]),
            bootstrap_done,
            scan_result,
            catchup_done,
            target_now,
            period_match,
        )]

    def _set_phase(self, action) -> None:
        self.phase = INVERSE_PHASE[action.next_state.phase]

    def _begin_cleanup(self, after: Phase | str) -> None:
        assert self.checkpoint is not None and self.checkpoint.state == RESULT_READY
        request_retire(self.checkpoint)
        self._after_cleanup = after
        self.phase = Phase.CLEANUP

    def _install_ready_scan(self) -> tuple[int | None, bool, int]:
        assert self.checkpoint is not None and self.checkpoint.state == RESULT_READY
        before = self._total_steps()
        scan = checkpoint_result(self.checkpoint)
        d = scan.candidate
        if d is None:
            action = self._control(scan_result=ScanResult.NONE)
            self._set_phase(action)
            self._begin_cleanup("launch")
            return None, False, self._total_steps() - before

        target = self.c * d
        if target < len(self.word):
            raise AssertionError(("ordinary checkpoint missed target", self.checkpoint_length, len(self.word), d))
        self.candidate = d
        self.target_length = target
        assert self.checkpoint_length is not None
        self.catchup_index = self.checkpoint_length
        self.terminal.prepare_comparison(2 * d)
        action = self._control(scan_result=ScanResult.FUTURE)
        self._set_phase(action)
        after = self.phase
        self._begin_cleanup(after)
        return None, False, self._total_steps() - before

    def _tick_cleanup(self) -> tuple[int | None, bool, int]:
        assert self.checkpoint is not None
        before = self._total_steps()
        if self.checkpoint.state != READY:
            checkpoint_step(self.checkpoint)
            return None, False, self._total_steps() - before
        after = self._after_cleanup
        self._after_cleanup = None
        if after == "launch":
            self.phase = Phase.SEARCH
            self._launch()
            return None, True, self._total_steps() - before
        if not isinstance(after, Phase):
            raise AssertionError(after)
        self.phase = after
        return None, False, self._total_steps() - before

    def _tick_catchup(self) -> tuple[int | None, bool, int]:
        assert self.candidate is not None and self.target_length is not None
        assert self.catchup_index is not None
        before = self._total_steps()
        good = self.phase is Phase.CATCH_UP_GOOD
        if self.catchup_index < len(self.word):
            i = self.catchup_index
            match, _ = self.terminal.compare_next(compare=i >= 2 * self.candidate)
            self.catchup_index += 1
            if good and not match:
                self.phase = Phase.CATCH_UP_BAD
            return None, False, self._total_steps() - before

        target_now = len(self.word) == self.target_length
        action = self._control(catchup_done=True, target_now=target_now)
        output = self.candidate if action.emit_gap else None
        launch = action.launch_scan
        self._set_phase(action)
        if launch:
            self._launch()
            return output, True, self._total_steps() - before
        self.catchup_index = None
        return output, False, self._total_steps() - before

    def _spend(self) -> tuple[int, int | None]:
        start = self._total_steps()
        output: int | None = None
        stop = False
        while self._total_steps() - start < self.work_budget and not stop:
            if self.phase is Phase.SEARCH:
                assert self.checkpoint is not None
                if self.checkpoint.state != RESULT_READY:
                    checkpoint_step(self.checkpoint)
                if self.checkpoint.state == RESULT_READY:
                    output, stop, _ = self._install_ready_scan()
            elif self.phase is Phase.CLEANUP:
                output, stop, _ = self._tick_cleanup()
            elif self.phase in (Phase.CATCH_UP_GOOD, Phase.CATCH_UP_BAD):
                output, stop, _ = self._tick_catchup()
            else:
                break
        return self._total_steps() - start, output

    def feed(self, symbol: str) -> TerminalBackgroundStep:
        if symbol not in "01":
            raise ValueError(symbol)
        before_phase = self.phase
        start_total = self._total_steps()
        start_terminal = self.terminal.ordinary_steps
        start_checkpoint = self.checkpoint.steps if self.checkpoint is not None else 0

        self.word += symbol
        self.terminal.append(symbol)
        output: int | None = None

        if self.phase is Phase.BOOTSTRAP:
            if self.bootstrap_limit and len(self.word) <= self.bootstrap_limit:
                output = lemma33_t1_discovered_gap(self.word, self.c)
            if len(self.word) >= max(1, self.bootstrap_limit):
                action = self._control(bootstrap_done=True)
                self._set_phase(action)
                self._launch()

        elif self.phase in (Phase.SEARCH, Phase.CLEANUP, Phase.CATCH_UP_GOOD, Phase.CATCH_UP_BAD):
            _, output = self._spend()

        elif self.phase in (Phase.FOLLOW_GOOD, Phase.FOLLOW_BAD):
            assert self.candidate is not None and self.target_length is not None
            i = len(self.word) - 1
            match, _ = self.terminal.compare_next(compare=i >= 2 * self.candidate)
            target_now = len(self.word) == self.target_length
            action = self._control(target_now=target_now, period_match=match)
            output = self.candidate if action.emit_gap else None
            launch = action.launch_scan
            self._set_phase(action)
            if launch:
                self._launch()
            elif len(self.word) > self.target_length:
                raise AssertionError((len(self.word), self.target_length, self.candidate))
        else:  # pragma: no cover
            raise AssertionError(self.phase)

        if self.audit:
            expected = lemma33_t1_discovered_gap(self.word, self.c)
            assert output == expected, (
                self.word, before_phase, self.phase, output, expected,
                self.candidate, self.target_length,
            )

        end_checkpoint = self.checkpoint.steps if self.checkpoint is not None else 0
        return TerminalBackgroundStep(
            length=len(self.word),
            phase_before=before_phase,
            phase_after=self.phase,
            output_gap=output,
            ordinary_steps=self._total_steps() - start_total,
            checkpoint_steps=end_checkpoint - start_checkpoint,
            terminal_steps=self.terminal.ordinary_steps - start_terminal,
            checkpoint_length=self.checkpoint_length,
            candidate=self.candidate,
            target_length=self.target_length,
            launches=self.launches,
        )
