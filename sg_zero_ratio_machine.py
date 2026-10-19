"""Executable transcription of the Seiferas--Galil r=s=0 read loop.

This module lowers the *case structure* of Theorem 3.  The semantic
``RECOVER`` and ``LOCAL`` use the cell-level unary-Delta equal-input specialization of
Lemma 3.2 implemented in ``lemma32_micro.py``.

``BACKGROUND`` now uses the equal-input, t=1 specialization of Lemma 3.3.
No update branch consults the direct palindrome oracle; the remaining boundary
is lowering the linear indexed scans and scheduler to primitive multitape transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Sequence

from lemma32_micro import (
    next_candidate_micro,
    recover_pair_micro,
)
from lemma33_persistent import PersistentLemma33T1
from lemma33_checkpoint_ordinary import PersistentLemma33CheckpointOrdinary
from lemma33_checkpoint_terminal import PersistentLemma33CheckpointTerminal
from ordinary_lemma32_worker import (
    next_candidate_ordinary_local,
    recover_pair_ordinary,
)
from lemma32_y_tape import (
    next_candidate_y_tape,
    next_candidate_y_tape_local,
    recover_pair_y_tape,
)

from sg_zero_ratio import (
    UpdateCase,
    b3_pair,
    candidate_midpoint,
    is_even_palindrome,
    survives_append,
)


class Action(Enum):
    CONSTANT = auto()
    RECOVER = auto()
    LOCAL = auto()
    DROP_SECOND = auto()
    BACKGROUND = auto()
    BACKGROUND_COMPLETES = auto()


@dataclass(frozen=True)
class StepRecord:
    before: str
    symbol: str
    after: str
    case: UpdateCase
    action: Action
    old_b: int
    old_bp_actual: int
    old_bp_known: bool
    new_b: int
    new_bp_actual: int
    new_bp_known: bool
    nominal_work: int
    jump: int


@dataclass
class SGZeroRatioMachine:
    """High-level online machine preserving the specialized SG invariant."""

    c: int = 16
    word: str = ""
    b: int = 0
    bp: Optional[int] = 1
    background_anchor: Optional[int] = None
    background: PersistentLemma33T1 | PersistentLemma33CheckpointOrdinary | PersistentLemma33CheckpointTerminal | None = None
    background_work_budget: int | None = None
    background_bootstrap_limit: int | None = 0
    background_scan_backend: str = "algorithm_y_tape"
    lemma32_backend: str = "algorithm_y_tape"
    audit: bool = False

    def __post_init__(self) -> None:
        if self.c <= 5:
            raise ValueError("The specialized proof requires c>5 before Lemma 3.3")
        if self.lemma32_backend not in {"micro", "algorithm_y_tape", "ordinary_checkpoint"}:
            raise ValueError(self.lemma32_backend)
        if self.word:
            if not self.audit:
                raise ValueError(
                    "nonempty SG initialization requires audit=True or an explicit "
                    "lowered machine snapshot"
                )
            exact_b, exact_bp = b3_pair(self.word)
            if self.b != exact_b:
                self.b = exact_b
            if self.bp is not None and self.bp != exact_bp:
                self.bp = exact_bp
        if self.bp is None and self.background_anchor is None:
            self.background_anchor = self.b
        if self.bp is not None:
            self.background_anchor = None
            self.background = None
        elif self.background is None:
            assert self.background_anchor is not None
            self.background = self._new_background(
                self.word[self.background_anchor :]
            )
        self._assert_invariant()

    def _new_background(
        self, initial: str
    ) -> PersistentLemma33T1 | PersistentLemma33CheckpointOrdinary | PersistentLemma33CheckpointTerminal:
        if self.background_scan_backend in {"ordinary_checkpoint", "ordinary_terminal"}:
            if self.c != 16:
                raise ValueError("ordinary checkpoint background is specialized to c=16")
            cls = (
                PersistentLemma33CheckpointTerminal
                if self.background_scan_backend == "ordinary_terminal"
                else PersistentLemma33CheckpointOrdinary
            )
            return cls(
                initial=initial,
                work_budget=self.background_work_budget,
                bootstrap_limit=self.background_bootstrap_limit or 0,
                audit=self.audit,
            )
        return PersistentLemma33T1(
            c=self.c,
            initial=initial,
            work_budget=self.background_work_budget,
            bootstrap_limit=self.background_bootstrap_limit,
            scan_backend=self.background_scan_backend,
            audit=self.audit,
        )

    def _recover_pair(self, word: str, anchor: int) -> tuple[int, int, int]:
        if self.lemma32_backend == "micro":
            first, second = recover_pair_micro(word, anchor)
            return first, second, max(1, len(word) - anchor)
        if self.lemma32_backend == "ordinary_checkpoint":
            result = recover_pair_ordinary(word, anchor)
            return result.first, result.second, max(1, result.ordinary_steps)
        result = recover_pair_y_tape(word, anchor)
        return result.first, result.second, max(1, result.ticks)

    def _next_candidate(
        self, word: str, anchor: int, *, stop: int | None = None
    ) -> tuple[int | None, int]:
        if self.lemma32_backend == "micro":
            return next_candidate_micro(word, anchor, stop=stop), max(1, len(word) - anchor)
        if self.lemma32_backend == "ordinary_checkpoint":
            if stop is None:
                # RECOVER is the only unbounded ordinary worker used by the
                # specialized six-case loop.  LOCAL always supplies its proof
                # radius explicitly.
                result = recover_pair_ordinary(word, anchor)
                return result.second, max(1, result.ordinary_steps)
            result = next_candidate_ordinary_local(
                word, anchor, radius=stop - anchor
            )
            return result.candidate, max(1, result.ordinary_steps)
        if stop is not None:
            radius = stop - anchor
            found, ticks = next_candidate_y_tape_local(
                word, anchor, radius=radius
            )
        else:
            found, ticks = next_candidate_y_tape(word, anchor, stop=stop)
        return found, max(1, ticks)

    @property
    def accepts(self) -> bool:
        return 2 * self.b == len(self.word)

    def _assert_invariant(self) -> None:
        if self.bp is not None:
            assert self.background_anchor is None
            assert self.background is None
        else:
            assert self.background is not None
            assert self.background_anchor is not None
            assert self.background.word == self.word[self.background_anchor :]
        if not self.audit:
            return
        exact_b, exact_bp = b3_pair(self.word)
        assert self.b == exact_b, (self.word, self.b, exact_b)
        if self.bp is not None:
            assert self.bp == exact_bp, (self.word, self.bp, exact_bp)
        else:
            assert exact_bp - exact_b > (len(self.word) - exact_b) / self.c, (
                self.word,
                exact_b,
                exact_bp,
                self.c,
            )
            assert self.background_anchor == self.b
        assert self.accepts == is_even_palindrome(self.word)

    def append(self, symbol: str) -> StepRecord:
        if len(symbol) != 1:
            raise ValueError(symbol)

        before = self.word
        right = len(before)
        old_b = self.b
        old_bp_actual = b3_pair(before)[1] if self.audit else (self.bp if self.bp is not None else -1)
        old_known = self.bp is not None
        b_survives = survives_append(before, self.b, symbol)
        if self.bp is None:
            case = (
                UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES
                if b_survives
                else UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS
            )
        else:
            bp_survives = survives_append(before, self.bp, symbol)
            if b_survives and bp_survives:
                case = UpdateCase.ONE_BOTH_SURVIVE
            elif not b_survives and not bp_survives:
                case = UpdateCase.TWO_BOTH_FAIL
            elif not b_survives and bp_survives:
                case = UpdateCase.THREE_SECOND_SURVIVES
            else:
                case = UpdateCase.FOUR_FIRST_SURVIVES
        after = before + symbol
        if self.audit:
            exact_new_b, exact_new_bp = b3_pair(after)
        else:
            exact_new_b = exact_new_bp = None
        action: Action
        nominal_work = 1

        if case is UpdateCase.ONE_BOTH_SURVIVE:
            assert self.bp is not None
            # Both positions remain exactly where they were.
            action = Action.CONSTANT

        elif case in (UpdateCase.TWO_BOTH_FAIL, UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS):
            # The paper invokes Lemma 3.2 over the active suffix [B3,RIGHT].
            action = Action.RECOVER
            recovered_b, recovered_bp, nominal_work = self._recover_pair(after, old_b)
            self.b = recovered_b
            self.bp = recovered_bp
            self.background_anchor = None
            self.background = None

        elif case is UpdateCase.THREE_SECOND_SURVIVES:
            assert self.bp is not None
            d = self.bp - self.b
            self.b = self.bp

            if d > (right - old_b) / self.c:
                # Large gap: recover exactly as in case 6.
                action = Action.RECOVER
                recovered_b, recovered_bp, nominal_work = self._recover_pair(after, old_b)
                assert recovered_b == self.b
                self.bp = recovered_bp
                self.background_anchor = None
                self.background = None
            else:
                # Small gap: Lemma 3.2 only needs the first 4d symbols of the
                # active suffix to look for B3' in (new B3, new B3+d].
                action = Action.LOCAL
                local_bp, nominal_work = self._next_candidate(
                    after, self.b, stop=self.b + d
                )
                if local_bp is not None:
                    self.bp = local_bp
                else:
                    # The Fine--Wilf argument proves clause (2) permits this.
                    action = Action.DROP_SECOND
                    self.bp = None
                    self.background_anchor = self.b
                    self.background = self._new_background(
                        after[self.background_anchor :]
                    )

        elif case is UpdateCase.FOUR_FIRST_SURVIVES:
            # The new B3 remains old B3.  The paper's Fine--Wilf bound shows
            # that the new B3' is far enough away that it need not be found.
            action = Action.DROP_SECOND
            self.bp = None
            self.background_anchor = self.b
            self.background = self._new_background(
                after[self.background_anchor :]
            )

        elif case is UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES:
            # B3 remains fixed while one persistent Lemma 3.3 checkpoint job
            # advances.  The job is retained across prefixes instead of being
            # rebuilt from the active suffix on every input symbol.
            assert self.background_anchor == self.b
            assert self.background is not None
            background_step = self.background.feed(symbol)
            discovered = background_step.output_gap
            nominal_work = max(1, background_step.work_spent)
            if discovered is not None:
                action = Action.BACKGROUND_COMPLETES
                self.bp = self.background_anchor + discovered
                self.background_anchor = None
                self.background = None
            else:
                action = Action.BACKGROUND
                self.bp = None

        else:  # pragma: no cover - Enum exhaustiveness guard.
            raise AssertionError(case)

        self.word = after
        # In constant-time branches B3 is unchanged; in all others it has
        # already been assigned.  Assert rather than silently correct it.
        if self.audit:
            assert self.b == exact_new_b, (case, before, symbol, self.b, exact_new_b)
        self._assert_invariant()

        return StepRecord(
            before=before,
            symbol=symbol,
            after=after,
            case=case,
            action=action,
            old_b=old_b,
            old_bp_actual=old_bp_actual,
            old_bp_known=old_known,
            new_b=self.b,
            new_bp_actual=(
                exact_new_bp if self.audit else (self.bp if self.bp is not None else -1)
            ),
            new_bp_known=self.bp is not None,
            nominal_work=nominal_work,
            jump=self.b - old_b,
        )


def run(word: str, *, c: int = 16) -> list[StepRecord]:
    machine = SGZeroRatioMachine(c=c)
    return [machine.append(ch) for ch in word]
