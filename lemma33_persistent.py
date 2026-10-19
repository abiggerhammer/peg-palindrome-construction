"""Persistent online scheduler for the equal-input ``t=1`` Lemma 3.3 job.

The published proof of Lemma 3.3 refers back to the checkpoint schedule in
Lemma 1.3: freeze a prefix ``u``, perform one linear off-line search while the
physical input advances only by ``epsilon*|u|``, and, when a candidate is
found, catch the comparison heads up and follow its period until the unique
possible target length.

This module specializes that schedule to the ``r=s=0`` palindrome machine.
The checkpoint search itself is now a genuinely resumable microprogram
(:class:`checkpoint_scan_job.CheckpointCandidateScanJob`); its result is not
precomputed and then delayed artificially.  A fixed number of source
microsteps is spent per arriving input symbol, and each frozen scan survives
across those arrivals.

The scan's arrays are still an indexed-machine front end.  The equal predicates
are independently implemented through unary-Delta failure tapes elsewhere in
the workbench.  The remaining lowering boundary is therefore representation,
not scheduling or hidden recomputation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import ceil, floor, sqrt

from construction_constants import CHECKPOINT_STEPS_PER_SYMBOL

from checkpoint_scan_job import CheckpointCandidateScanJob
from checkpoint_scan_y_job import CheckpointCandidateYJob
from checkpoint_scan_y_tape_job import CheckpointCandidateYTapeJob
from lemma32_t1 import manacher_even, z_array
from lemma33_t1 import lemma33_t1_discovered_gap


def schedule_epsilon(c: int) -> float:
    if c <= 5:
        raise ValueError("the outer reversal proof requires c>5")
    # The Lemma 1.3 checkpoint invariant, reused verbatim by Lemma 3.3.
    return 0.5 * (sqrt(c / (c - 1)) - 1.0)


def _palindromic_prefix_flags(word: str) -> list[bool]:
    """Return flags for even prefix lengths ``2*d`` (reference implementation)."""

    n = len(word)
    radii = manacher_even(word)
    flags = [False] * (n // 2 + 1)
    for d in range(1, len(flags)):
        flags[d] = radii[d] >= d
    return flags


def checkpoint_candidate_t1(word: str, c: int) -> int | None:
    """Indexed reference for the candidate selected by Lemma 3.3.2.

    The online implementation uses :class:`CheckpointCandidateScanJob`; this
    function remains an independent oracle for differential tests.
    """

    if c <= 5:
        raise ValueError("the outer reversal proof requires c>5")
    n = len(word)
    if n == 0:
        return None

    z = z_array(word)
    pal_prefix = _palindromic_prefix_flags(word)
    max_life_before = -1

    for d in range(1, n // 2 + 1):
        period = 2 * d
        if pal_prefix[d]:
            life = n if period == n else period + z[period]
        else:
            life = -1

        base = (c - 1) * d
        target = c * d
        if base <= n < target and life >= n and max_life_before < base:
            return d
        if life > max_life_before:
            max_life_before = life
    return None


class Phase(Enum):
    BOOTSTRAP = auto()
    SEARCH = auto()
    CATCH_UP = auto()
    FOLLOW = auto()


@dataclass(frozen=True)
class BackgroundStep:
    length: int
    phase_before: Phase
    phase_after: Phase
    output_gap: int | None
    work_spent: int
    checkpoint_length: int | None
    candidate: int | None
    target_length: int | None


class PersistentLemma33T1:
    """Persistent equal-input Lemma 3.3 recognizer.

    ``feed`` returns a gap exactly on prefixes in the specialized language.
    The finite bootstrap handles a constant number of short prefixes.  Beyond
    it, every checkpoint scan is retained and receives ``work_budget`` source
    microsteps per arriving symbol; no scan is restarted at intermediate
    prefixes.  When a scan finishes, a separate resumable catch-up phase checks
    symbols that arrived while the checkpoint was frozen.
    """

    def __init__(
        self,
        c: int = 16,
        *,
        initial: str = "",
        work_budget: int | None = None,
        bootstrap_limit: int | None = 0,
        scan_backend: str = "algorithm_y_tape",
        audit: bool = False,
    ):
        if c <= 5:
            raise ValueError("the outer reversal proof requires c>5")
        self.c = c
        self.epsilon = schedule_epsilon(c)
        if scan_backend not in {"indexed", "algorithm_y", "algorithm_y_tape"}:
            raise ValueError(scan_backend)
        self.scan_backend = scan_backend
        self.audit = audit
        # The indexed scan is exhaustively bounded by 12n+8 ticks in the test
        # suite.  Sixteen ticks per unit of checkpoint length leaves room for
        # catch-up and finite-control bookkeeping.  Dividing by epsilon makes
        # the complete constant-rate job fit in the checkpoint window.
        scan_rate = {
            "indexed": 16,
            "algorithm_y": 100,
            "algorithm_y_tape": CHECKPOINT_STEPS_PER_SYMBOL,
        }[self.scan_backend]
        self.work_budget = (
            ceil(scan_rate / self.epsilon) if work_budget is None else work_budget
        )
        if self.work_budget <= 0:
            raise ValueError(self.work_budget)
        self.bootstrap_limit = (
            max(4, ceil(2 / self.epsilon))
            if bootstrap_limit is None
            else bootstrap_limit
        )
        if self.bootstrap_limit < 0:
            raise ValueError(self.bootstrap_limit)

        self.word = initial
        self.phase = Phase.BOOTSTRAP
        self.scan: (
            CheckpointCandidateScanJob
            | CheckpointCandidateYJob
            | CheckpointCandidateYTapeJob
            | None
        ) = None
        self.checkpoint_length: int | None = None
        self.deadline_length: int | None = None
        self.candidate: int | None = None
        self.target_length: int | None = None
        self.catchup_index: int | None = None
        self.period_ok = True
        self.scan_launches = 0

        if len(initial) > self.bootstrap_limit:
            self._launch_scan()

    def _launch_scan(self) -> None:
        self.phase = Phase.SEARCH
        if self.scan_backend == "indexed":
            self.scan = CheckpointCandidateScanJob(self.word, self.c)
        elif self.scan_backend == "algorithm_y":
            self.scan = CheckpointCandidateYJob(self.word, self.c)
        else:
            self.scan = CheckpointCandidateYTapeJob(self.word, self.c)
        self.checkpoint_length = len(self.word)
        window = max(1, floor(self.epsilon * max(1, len(self.word))))
        self.deadline_length = len(self.word) + window
        self.candidate = None
        self.target_length = None
        self.catchup_index = None
        self.period_ok = True
        self.scan_launches += 1

    def _install_scan_result(self, d: int | None) -> tuple[int | None, bool]:
        """Install a completed scan result.

        Returns ``(output, stop_for_this_input)``.  An empty scan restarts at
        the newly reached physical prefix and deliberately waits for the next
        symbol before doing more scan work; otherwise a large per-symbol budget
        could repeat the same frozen job indefinitely.
        """

        assert self.checkpoint_length is not None
        self.scan = None
        if d is None:
            self._launch_scan()
            return None, True

        target = self.c * d
        if target < len(self.word):
            raise AssertionError(
                ("checkpoint scan missed its target", self.checkpoint_length, len(self.word), d)
            )
        self.phase = Phase.CATCH_UP
        self.candidate = d
        self.target_length = target
        self.catchup_index = self.checkpoint_length
        self.period_ok = True
        return None, False

    def _tick_catch_up(self) -> tuple[int | None, bool]:
        assert self.phase is Phase.CATCH_UP
        assert self.candidate is not None
        assert self.target_length is not None
        assert self.catchup_index is not None

        if len(self.word) > self.target_length:
            raise AssertionError(
                ("catch-up missed candidate target", len(self.word), self.target_length)
            )

        if self.catchup_index < len(self.word):
            index = self.catchup_index
            period = 2 * self.candidate
            if index >= period and self.word[index] != self.word[index - period]:
                self.period_ok = False
            self.catchup_index += 1
            return None, False

        if len(self.word) == self.target_length:
            output = self.candidate if self.period_ok else None
            self._launch_scan()
            return output, True

        self.phase = Phase.FOLLOW
        self.catchup_index = None
        return None, False

    def _spend_background_work(self) -> tuple[int, int | None]:
        spent = 0
        output: int | None = None
        stop = False

        while spent < self.work_budget and not stop:
            if self.phase is Phase.SEARCH:
                assert self.scan is not None
                finished = self.scan.tick()
                spent += 1
                if (
                    not finished
                    and self.deadline_length is not None
                    and len(self.word) > self.deadline_length
                ):
                    raise AssertionError(
                        (
                            "linear checkpoint job missed its fixed-rate deadline",
                            len(self.word),
                            self.deadline_length,
                            self.scan.ticks,
                        )
                    )
                if finished:
                    output, stop = self._install_scan_result(self.scan.candidate)

            elif self.phase is Phase.CATCH_UP:
                spent += 1
                output, stop = self._tick_catch_up()

            else:
                break

        return spent, output

    def feed(self, symbol: str) -> BackgroundStep:
        if len(symbol) != 1:
            raise ValueError(symbol)
        phase_before = self.phase
        self.word += symbol
        output: int | None = None
        spent = 0

        if self.phase is Phase.BOOTSTRAP:
            if self.bootstrap_limit > 0:
                # A bounded short-prefix table can be compiled into finite
                # control.  The oracle call is retained only for the audit
                # implementation of that finite table.
                output = lemma33_t1_discovered_gap(self.word, self.c)
            if len(self.word) >= max(1, self.bootstrap_limit):
                self._launch_scan()

        elif self.phase in (Phase.SEARCH, Phase.CATCH_UP):
            spent, output = self._spend_background_work()

        elif self.phase is Phase.FOLLOW:
            assert self.candidate is not None and self.target_length is not None
            d = self.candidate
            period = 2 * d
            index = len(self.word) - 1
            if index >= period and self.word[index] != self.word[index - period]:
                self.period_ok = False
            if len(self.word) == self.target_length:
                if self.period_ok:
                    output = d
                self._launch_scan()
            elif len(self.word) > self.target_length:
                raise AssertionError((len(self.word), self.target_length, d))

        else:  # pragma: no cover
            raise AssertionError(self.phase)

        if self.audit:
            expected = lemma33_t1_discovered_gap(self.word, self.c)
            assert output == expected, (
                self.word,
                phase_before,
                self.phase,
                output,
                expected,
                self.candidate,
                self.target_length,
            )

        return BackgroundStep(
            length=len(self.word),
            phase_before=phase_before,
            phase_after=self.phase,
            output_gap=output,
            work_spent=spent,
            checkpoint_length=self.checkpoint_length,
            candidate=self.candidate,
            target_length=self.target_length,
        )
