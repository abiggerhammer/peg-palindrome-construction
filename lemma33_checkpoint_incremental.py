"""Incremental ordinary launch/reset wrapper for the c=16 Lemma 3.3 job.

Unlike the earlier audit wrapper, checkpoint source extension, source-head
positioning, CURRENT/LAG synchronization, and lag-head installation are all
retained phases.  ``feed`` spends a fixed ordinary-step budget across those
phases and the checkpoint body; it never runs a whole O(n) launch operation in
one Python call.

The checkpoint result marker is decoded by an explicit retained tape scan.
The candidate axis and a source terminal are rewound one cell at a time; they
then advance in lockstep while a literal unary counter records the candidate
gap.  Host integers remain only in the surrounding audit/control wrapper and
are not used to discover the marker.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import checkpoint_ordinary_tm as cp
import checkpoint_reusable_tm as reusable
from checkpoint_reusable_tm import ReusableCheckpointConfiguration
from construction_constants import background_steps_per_input
from lemma33_controller import ControlPhase, ControlState, ScanResult, persistent_control_table
from lemma33_t1 import lemma33_t1_discovered_gap
from ordinary_history_terminal import CURRENT, LAG, COPY, OrdinaryHistoryTerminal
from ordinary_unary_counter import BOTTOM as COUNTER_BOTTOM, BLANK as COUNTER_BLANK, ONE as COUNTER_ONE, UnaryCounter


class Phase(Enum):
    BOOTSTRAP = auto()
    LAUNCH_TO_END_0 = auto()
    LAUNCH_TO_END_1 = auto()
    LAUNCH_TO_END_2 = auto()
    LAUNCH_COPY = auto()
    LAUNCH_SYNC_CURRENT = auto()
    LAUNCH_SYNC_LAG = auto()
    LAUNCH_FWD_REWIND_0 = auto()
    LAUNCH_FWD_REWIND_1 = auto()
    LAUNCH_REV_LEFT = auto()
    LAUNCH_REQUEST = auto()
    SEARCH = auto()
    CLEANUP = auto()
    SCAN_RESULT_REWIND_CANDIDATE = auto()
    SCAN_RESULT_REWIND_SOURCE = auto()
    SCAN_RESULT_ADVANCE = auto()
    SCAN_RESULT_CHECK = auto()
    BUILD_CANDIDATE = auto()
    RESTORE_CANDIDATE = auto()
    TARGET_REWIND_SOURCE = auto()
    TARGET_SUBTRACT = auto()
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
INVERSE_CONTROL = {value: key for key, value in CONTROL_PHASE.items()}


@dataclass(frozen=True)
class IncrementalBackgroundStep:
    length: int
    phase_before: Phase
    phase_after: Phase
    output_gap: int | None
    ordinary_steps: int
    launches: int

    @property
    def work_spent(self) -> int:
        return self.ordinary_steps


class IncrementalLemma33CheckpointTerminal:
    c = 16

    def __init__(
        self,
        *,
        initial: str = "",
        work_budget: int | None = None,
        audit: bool = False,
        auto_launch: bool = True,
    ) -> None:
        if any(ch not in "01" for ch in initial):
            raise ValueError(initial)
        self.work_budget = background_steps_per_input(16) if work_budget is None else work_budget
        if self.work_budget <= 0:
            raise ValueError(self.work_budget)
        self.audit = audit
        self.word = initial
        self.terminal = OrdinaryHistoryTerminal(initial)
        self.checkpoint: ReusableCheckpointConfiguration = self.terminal.blank_checkpoint_shell()
        self.phase = Phase.BOOTSTRAP
        self.first_launch = True
        self.checkpoint_length: int | None = None
        self.candidate: int | None = None
        self.target_length: int | None = None
        self.catchup_index: int | None = None  # audit-only mirror
        self.candidate_counter = UnaryCounter.zero()
        self.target_remaining = UnaryCounter.zero()
        self.launches = 0
        self._after_cleanup: Phase | str | None = None
        self._table = persistent_control_table()
        if initial and auto_launch:
            self.begin_launch()

    def _total(self) -> int:
        return (
            self.terminal.ordinary_steps
            + self.checkpoint.steps
            + self.candidate_counter.steps
            + self.target_remaining.steps
        )

    def _scanned(self, tape: int) -> str:
        return self.checkpoint.tapes[tape].get(self.checkpoint.heads[tape], cp.BLANK)

    def _move(self, moves: dict[int, int]) -> None:
        for tape, amount in moves.items():
            self.checkpoint.heads[tape] += amount
        self.checkpoint.steps += 1

    def _write_move(self, writes: dict[int, str], moves: dict[int, int] | None = None) -> None:
        for tape, symbol in writes.items():
            pos = self.checkpoint.heads[tape]
            if symbol == cp.BLANK:
                self.checkpoint.tapes[tape].pop(pos, None)
            else:
                self.checkpoint.tapes[tape][pos] = symbol
        for tape, amount in (moves or {}).items():
            self.checkpoint.heads[tape] += amount
        self.checkpoint.steps += 1

    def begin_launch(self) -> None:
        if not self.word:
            return
        if self.phase not in {
            Phase.BOOTSTRAP, Phase.SEARCH, Phase.CATCH_UP_GOOD,
            Phase.CATCH_UP_BAD, Phase.FOLLOW_GOOD, Phase.FOLLOW_BAD,
        }:
            raise ValueError(("launch already in progress", self.phase))
        self.phase = Phase.LAUNCH_TO_END_0
        self.candidate = None
        self.target_length = None
        self.catchup_index = None
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
        return self._table[(
            ControlState(CONTROL_PHASE[self.phase]),
            bootstrap_done,
            scan_result,
            catchup_done,
            target_now,
            period_match,
        )]

    def _set_control_phase(self, action) -> None:
        self.phase = INVERSE_CONTROL[action.next_state.phase]

    def _tick_launch(self) -> bool:  # noqa: C901
        sources = (cp.SRC_FWD, cp.SRC_REV, cp.SRC_FWD2)
        if self.phase in (Phase.LAUNCH_TO_END_0, Phase.LAUNCH_TO_END_1, Phase.LAUNCH_TO_END_2):
            index = {
                Phase.LAUNCH_TO_END_0: 0,
                Phase.LAUNCH_TO_END_1: 1,
                Phase.LAUNCH_TO_END_2: 2,
            }[self.phase]
            tape = sources[index]
            if self._scanned(tape) == cp.END:
                self.phase = (
                    Phase.LAUNCH_TO_END_1 if index == 0 else
                    Phase.LAUNCH_TO_END_2 if index == 1 else
                    Phase.LAUNCH_COPY
                )
                self.checkpoint.steps += 1  # finite-control transition
            else:
                self._move({tape: 1})
            return True

        if self.phase is Phase.LAUNCH_COPY:
            if self.terminal.has_right_data(COPY):
                self.terminal.move_right(COPY)
                symbol = self.terminal.symbol(COPY)
                if symbol not in "01":
                    raise AssertionError(("COPY reached noninput", symbol))
                self._write_move(
                    {tape: symbol for tape in sources},
                    {tape: 1 for tape in sources},
                )
            else:
                self._write_move({tape: cp.END for tape in sources})
                self.checkpoint_length = len(self.word)
                self.phase = Phase.LAUNCH_SYNC_CURRENT
            return True

        if self.phase is Phase.LAUNCH_SYNC_CURRENT:
            if self.terminal.has_right_data(CURRENT):
                self.terminal.move_right(CURRENT)
            else:
                self.phase = Phase.LAUNCH_SYNC_LAG
                self.checkpoint.steps += 1
            return True

        if self.phase is Phase.LAUNCH_SYNC_LAG:
            if self.terminal.has_right_data(LAG):
                self.terminal.move_right(LAG)
            else:
                self.phase = Phase.LAUNCH_FWD_REWIND_0
                self.checkpoint.steps += 1
            return True

        if self.phase in (Phase.LAUNCH_FWD_REWIND_0, Phase.LAUNCH_FWD_REWIND_1):
            tape = cp.SRC_FWD if self.phase is Phase.LAUNCH_FWD_REWIND_0 else cp.SRC_FWD2
            if self._scanned(tape) == cp.SENTINEL:
                self._move({tape: 1})
                self.phase = (
                    Phase.LAUNCH_FWD_REWIND_1
                    if tape == cp.SRC_FWD else Phase.LAUNCH_REV_LEFT
                )
            else:
                self._move({tape: -1})
            return True

        if self.phase is Phase.LAUNCH_REV_LEFT:
            # REV was left on END by LAUNCH_COPY.
            if self._scanned(cp.SRC_REV) != cp.END:
                raise AssertionError(("REV not on END", self._scanned(cp.SRC_REV)))
            self._move({cp.SRC_REV: -1})
            if self.first_launch:
                self.phase = Phase.SEARCH
                self.first_launch = False
            else:
                self.phase = Phase.LAUNCH_REQUEST
            return True

        if self.phase is Phase.LAUNCH_REQUEST:
            if self.checkpoint.state != reusable.READY:
                raise AssertionError(("relaunch checkpoint not READY", self.checkpoint.state))
            tape = reusable.CONTROL_TAPE
            self.checkpoint.tapes[tape][self.checkpoint.heads[tape]] = reusable.REQUEST
            reusable.step(self.checkpoint)
            self.phase = Phase.SEARCH
            return True

        return False

    def _begin_result_scan(self) -> None:
        if self.checkpoint.state != reusable.RESULT_READY:
            raise AssertionError(("checkpoint result not ready", self.checkpoint.state))
        self.candidate_counter.fresh_zero()
        self.phase = Phase.SCAN_RESULT_REWIND_CANDIDATE

    def _begin_cleanup(self, after: Phase | str) -> None:
        if self.checkpoint.state != reusable.RESULT_READY:
            raise AssertionError(("checkpoint result not ready", self.checkpoint.state))
        reusable.request_retire(self.checkpoint)
        self._after_cleanup = after
        self.phase = Phase.CLEANUP

    def _tick_cleanup(self) -> tuple[int | None, bool]:
        if self.checkpoint.state != reusable.READY:
            reusable.step(self.checkpoint)
            return None, False
        after = self._after_cleanup
        self._after_cleanup = None
        if after == "launch":
            self.phase = Phase.SEARCH
            self.begin_launch()
            return None, True
        if not isinstance(after, Phase):
            raise AssertionError(after)
        self.phase = after
        return None, False

    def _finish_no_candidate(self) -> tuple[int | None, bool]:
        # The finite controller transition is charged explicitly.  Restore the
        # abstract SEARCH phase only for the table lookup; the resulting action
        # immediately starts the next retained launch.
        self.phase = Phase.SEARCH
        action = self._control(scan_result=ScanResult.NONE)
        self.checkpoint.steps += 1
        self._set_control_phase(action)
        self._begin_cleanup("launch")
        return None, False

    def _finish_candidate(self) -> tuple[int | None, bool]:
        # Discovery itself is complete.  The candidate counter is now consumed
        # non-destructively to (a) build 16d units of target distance and
        # (b) place LAG exactly 2d-1 cells behind the frozen boundary.
        if self.candidate_counter.is_zero:
            raise AssertionError("nonpositive candidate")
        self.target_remaining.fresh_zero()
        self.phase = Phase.BUILD_CANDIDATE
        self.checkpoint.steps += 1
        return None, False

    def _tick_result_scan(self) -> tuple[int | None, bool]:
        if self.phase is Phase.SCAN_RESULT_REWIND_CANDIDATE:
            if self._scanned(cp.CANDIDATE_TAPE) == cp.MARK:
                self.phase = Phase.SCAN_RESULT_REWIND_SOURCE
                self.checkpoint.steps += 1
            else:
                self._move({cp.CANDIDATE_TAPE: -1})
            return None, False

        if self.phase is Phase.SCAN_RESULT_REWIND_SOURCE:
            if self._scanned(cp.SRC_FWD) == cp.SENTINEL:
                self.phase = Phase.SCAN_RESULT_ADVANCE
                self.checkpoint.steps += 1
            else:
                self._move({cp.SRC_FWD: -1})
            return None, False

        if self.phase is Phase.SCAN_RESULT_ADVANCE:
            # Move from position j to j+1 on both finite axes, then record that
            # one-based position in the unary counter.  These are three literal
            # ordinary transitions: one simultaneous move and a two-step push.
            self._move({cp.CANDIDATE_TAPE: 1, cp.SRC_FWD: 1})
            self.candidate_counter.increment()
            self.phase = Phase.SCAN_RESULT_CHECK
            return None, False

        if self.phase is Phase.SCAN_RESULT_CHECK:
            candidate_symbol = self._scanned(cp.CANDIDATE_TAPE)
            source_symbol = self._scanned(cp.SRC_FWD)
            if candidate_symbol == cp.GAP:
                return self._finish_candidate()
            if source_symbol == cp.END:
                return self._finish_no_candidate()
            if source_symbol not in "01":
                raise AssertionError(("bad result-scan source", source_symbol))
            if candidate_symbol != cp.BLANK:
                raise AssertionError(("bad candidate-axis symbol", candidate_symbol))
            self.phase = Phase.SCAN_RESULT_ADVANCE
            self.checkpoint.steps += 1
            return None, False

        raise AssertionError(self.phase)

    def _tick_build_candidate(self) -> None:
        scanned = self.candidate_counter.scanned()
        if scanned == COUNTER_ONE:
            # Consume one candidate unit by walking toward the bottom marker.
            self.candidate_counter.head -= 1
            self.candidate_counter.steps += 1
            # Fixed c=16 expansion.  Since c is fixed, this is a bounded finite
            # macro and expands to 32 literal unary-counter transitions.
            for _ in range(self.c):
                self.target_remaining.increment()
            # Install a net two-cell lag per unit.  A single compensating right
            # move at the bottom yields exactly 2d-1.
            self.terminal.move_left(LAG)
            self.terminal.move_left(LAG)
            return
        if scanned != COUNTER_BOTTOM:
            raise AssertionError(("candidate traversal", scanned))
        self.terminal.move_right(LAG)
        self.candidate_counter.head += 1
        self.candidate_counter.steps += 1
        self.phase = Phase.RESTORE_CANDIDATE

    def _tick_restore_candidate(self) -> None:
        scanned = self.candidate_counter.scanned()
        if scanned == COUNTER_ONE:
            self.candidate_counter.head += 1
            self.candidate_counter.steps += 1
            return
        if scanned != COUNTER_BLANK:
            raise AssertionError(("candidate restore", scanned))
        self.candidate_counter.head -= 1
        self.candidate_counter.steps += 1
        # Audit mirrors are read only after the ordinary traversal is restored.
        d = self.candidate_counter.value()
        self.candidate = d
        self.target_length = self.c * d
        self.phase = Phase.TARGET_REWIND_SOURCE
        self.checkpoint.steps += 1

    def _missed_target(self) -> tuple[int | None, bool]:
        self.phase = Phase.SEARCH
        action = self._control(scan_result=ScanResult.MISSED)
        self.checkpoint.steps += 1
        self._set_control_phase(action)
        self._begin_cleanup("launch")
        return None, False

    def _tick_target_setup(self) -> tuple[int | None, bool]:
        if self.phase is Phase.TARGET_REWIND_SOURCE:
            if self._scanned(cp.SRC_FWD) == cp.SENTINEL:
                self.phase = Phase.TARGET_SUBTRACT
                self.checkpoint.steps += 1
            else:
                self._move({cp.SRC_FWD: -1})
            return None, False

        if self.phase is not Phase.TARGET_SUBTRACT:
            raise AssertionError(self.phase)
        self._move({cp.SRC_FWD: 1})
        symbol = self._scanned(cp.SRC_FWD)
        if symbol == cp.END:
            self.checkpoint.steps += 1
            self._begin_cleanup(Phase.CATCH_UP_GOOD)
            return None, False
        if symbol not in "01":
            raise AssertionError(("target source", symbol))
        if self.target_remaining.is_zero:
            return self._missed_target()
        self.target_remaining.decrement()
        return None, False

    def _tick_catchup(self) -> tuple[int | None, bool]:
        assert self.candidate is not None
        good = self.phase is Phase.CATCH_UP_GOOD
        if self.terminal.has_right_data(CURRENT):
            # Before the period-earlier cursor reaches actual input, the
            # partial-overlap branch imposes no comparison.  The scanned tape
            # symbol itself supplies that finite signal; no numeric i>=2d test
            # remains.
            compare = self.terminal.symbol(LAG) in "01"
            match, _ = self.terminal.compare_next(compare=compare)
            if self.target_remaining.is_zero:
                return self._missed_target()
            self.target_remaining.decrement()
            if good and not match:
                self.phase = Phase.CATCH_UP_BAD
            return None, False
        target_now = self.target_remaining.is_zero
        action = self._control(catchup_done=True, target_now=target_now)
        output = self.candidate if action.emit_gap else None
        launch = action.launch_scan
        self._set_control_phase(action)
        self.checkpoint.steps += 1
        if launch:
            self.begin_launch()
            return output, True
        self.catchup_index = None
        return output, False

    def _spend(self, limit: int | None = None) -> tuple[int, int | None]:
        budget = self.work_budget if limit is None else limit
        if budget <= 0:
            return 0, None
        start = self._total()
        output: int | None = None
        stop = False
        while self._total() - start < budget and not stop:
            if self._tick_launch():
                continue
            if self.phase is Phase.SEARCH:
                if self.checkpoint.state != reusable.RESULT_READY:
                    reusable.step(self.checkpoint)
                if self.checkpoint.state == reusable.RESULT_READY:
                    self._begin_result_scan()
            elif self.phase is Phase.CLEANUP:
                output, stop = self._tick_cleanup()
            elif self.phase in (
                Phase.SCAN_RESULT_REWIND_CANDIDATE,
                Phase.SCAN_RESULT_REWIND_SOURCE,
                Phase.SCAN_RESULT_ADVANCE,
                Phase.SCAN_RESULT_CHECK,
            ):
                output, stop = self._tick_result_scan()
            elif self.phase is Phase.BUILD_CANDIDATE:
                self._tick_build_candidate()
            elif self.phase is Phase.RESTORE_CANDIDATE:
                self._tick_restore_candidate()
            elif self.phase in (Phase.TARGET_REWIND_SOURCE, Phase.TARGET_SUBTRACT):
                output, stop = self._tick_target_setup()
            elif self.phase in (Phase.CATCH_UP_GOOD, Phase.CATCH_UP_BAD):
                output, stop = self._tick_catchup()
            else:
                break
        return self._total() - start, output

    def feed(self, symbol: str, *, budget_override: int | None = None) -> IncrementalBackgroundStep:
        if symbol not in "01":
            raise ValueError(symbol)
        before = self.phase
        start = self._total()
        self.word += symbol
        self.terminal.append(symbol)
        output: int | None = None

        if self.phase is Phase.BOOTSTRAP:
            self.begin_launch()
        elif self.phase in (Phase.FOLLOW_GOOD, Phase.FOLLOW_BAD):
            assert self.candidate is not None
            compare = self.terminal.symbol(LAG) in "01"
            match, _ = self.terminal.compare_next(compare=compare)
            if self.target_remaining.is_zero:
                # A retained real-time execution should have relaunched at the
                # previous target.  Keep the defensive branch explicit.
                self.phase = Phase.SEARCH
                action = self._control(scan_result=ScanResult.MISSED)
                self.checkpoint.steps += 1
                self._set_control_phase(action)
                self.begin_launch()
            else:
                self.target_remaining.decrement()
                target_now = self.target_remaining.is_zero
                action = self._control(target_now=target_now, period_match=match)
                output = self.candidate if action.emit_gap else None
                launch = action.launch_scan
                self._set_control_phase(action)
                self.checkpoint.steps += 1
                if launch:
                    self.begin_launch()
        else:
            _, output = self._spend(budget_override)

        if self.audit:
            expected = lemma33_t1_discovered_gap(self.word, self.c)
            assert output == expected, (
                self.word, before, self.phase, output, expected,
                self.candidate, self.target_length,
            )
        return IncrementalBackgroundStep(
            len(self.word), before, self.phase, output,
            self._total() - start, self.launches,
        )
