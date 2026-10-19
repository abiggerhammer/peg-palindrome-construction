"""Bounded-work outer SG machine with lazy case-5 background launch.

This refines :mod:`sg_outer_ordinary` in the place where the audit wrapper was
still too eager: case 4 no longer returns the discarded B3' cursor or copies
the active suffix immediately.  A dedicated BG history cursor catches up,
returns to B3, and starts the incremental Lemma-3.3 checkpoint over subsequent
case-5 inputs.  The stale B3' cursor is returned in the same background budget.
If B3 fails first, case 6 finishes the bounded outstanding returns before its
paid RECOVER scan.
"""

from __future__ import annotations

from typing import Optional

from history_zipper_ordinary_tm import initial_configuration
from lemma33_checkpoint_incremental import IncrementalLemma33CheckpointTerminal
from ordinary_history_terminal import HISTORY_SENTINEL
from ordinary_unary_counter import UnaryCounter
from sg_outer_ordinary import (
    B_CURSOR,
    BP_CURSOR,
    LB_CURSOR,
    LBP_CURSOR,
    LeftRelation,
    MidRelation,
    OrdinarySGOuter,
    OuterStepRecord,
)
from sg_zero_ratio import UpdateCase, b3_pair

BG_CURSOR = "BG"
BGL_CURSOR = "BGL"
ALL_CURSORS = (B_CURSOR, BP_CURSOR, LB_CURSOR, LBP_CURSOR, BG_CURSOR, BGL_CURSOR)


class OrdinarySGOuterIncremental(OrdinarySGOuter):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cursors[BG_CURSOR] = initial_configuration((HISTORY_SENTINEL,), reader=0)
        self.cursors[BGL_CURSOR] = initial_configuration((HISTORY_SENTINEL,), reader=0)
        self.bg_rel = MidRelation.AT_END
        self.bgl_rel = LeftRelation.AT_END
        self.bg_return = UnaryCounter.zero()
        self.lazy_background: IncrementalLemma33CheckpointTerminal | None = None
        self.lazy_mode: str | None = None  # COPY, RETURN, RUN
        self.lazy_copy_needed = False
        # The eager wrapper field is not used in this refinement.
        self.background = None
        self._assert_incremental_invariant()

    def _append_all(self, symbol: str) -> None:
        command = "APPEND0" if symbol == "0" else "APPEND1"
        for cursor in ALL_CURSORS:
            self._run(cursor, command)

    def _ordinary_steps(self) -> int:
        base = super()._ordinary_steps()
        return base + self.bg_return.steps

    def _advance_bgl_no_test(
        self, relation: LeftRelation, midpoint_before: MidRelation
    ) -> LeftRelation:
        if midpoint_before is MidRelation.AFTER_END:
            if relation is not LeftRelation.AFTER2:
                raise AssertionError((relation, midpoint_before))
            self._run(BGL_CURSOR, "RIGHT")
            return LeftRelation.AT_END
        if relation is LeftRelation.AT_END:
            self.control_steps += 1
            return LeftRelation.EXACT
        if relation is LeftRelation.EXACT:
            self._run(BGL_CURSOR, "LEFT")
            return LeftRelation.EXACT
        raise AssertionError((relation, midpoint_before))

    def _b_right_unit(self) -> None:
        self.b_rel = self._mid_right(B_CURSOR, self.b_rel)
        self.bg_rel = self._mid_right(BG_CURSOR, self.bg_rel)
        self.lb_rel = self._left_right(LB_CURSOR, self.lb_rel)
        self.lb_rel = self._left_right(LB_CURSOR, self.lb_rel)
        self.bgl_rel = self._left_right(BGL_CURSOR, self.bgl_rel)
        self.bgl_rel = self._left_right(BGL_CURSOR, self.bgl_rel)

    def _promote_second(self, *, save_radius: bool) -> UnaryCounter:
        if self.lazy_mode is not None:
            raise AssertionError("promotion while background active")
        radius = UnaryCounter.zero()
        while not self.gap.is_zero:
            self._b_right_unit()
            self.gap.decrement()
            if save_radius:
                radius.increment()
        if self.audit:
            assert self.bp is not None
            self.b = self.bp
        return radius

    def _install_recover_pair(self, checkpoint, length: UnaryCounter) -> tuple[int, int]:
        limit2 = self._copy_counter(length)

        def second_unit() -> None:
            self.bp_rel = self._mid_right(BP_CURSOR, self.bp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.gap.increment()

        _, d2 = self._scan_gap(
            checkpoint, __import__('checkpoint_ordinary_tm').OUT2_TAPE,
            limit2, second_unit, automatic_after_limit=True,
        )
        limit1 = self._copy_counter(length)

        def first_unit() -> None:
            self._b_right_unit()
            self.gap.decrement()

        found, d1 = self._scan_gap(
            checkpoint, __import__('checkpoint_ordinary_tm').OUT1_TAPE,
            limit1, first_unit, automatic_after_limit=False,
        )
        if not found:
            raise AssertionError(("OUT1 missing", checkpoint.word))
        if self.audit:
            anchor = self.b
            self.bp = anchor + d2
            self.b = anchor + d1
        return d1, d2

    # ------------------------------------------------------------------
    # Lazy discarded-head return and background bootstrap.

    def _start_lazy_background(self) -> None:
        if self.b_rel is not MidRelation.BEFORE_END:
            raise AssertionError(("empty active suffix", self.b_rel, self.word, self.b))
        self.k.fresh_zero()
        self.bg_return.fresh_zero()
        self.lazy_background = IncrementalLemma33CheckpointTerminal(
            initial="",
            work_budget=self.background_work_budget,
            audit=False,
            auto_launch=False,
        )
        self.lazy_mode = "COPY"
        self.lazy_copy_needed = True

    def _return_p_one(self) -> None:
        if self.gap.is_zero:
            return
        self.bp_rel = self._mid_left(BP_CURSOR, self.bp_rel)
        self.lbp_rel = self._left_left(LBP_CURSOR, self.lbp_rel)
        self.lbp_rel = self._left_left(LBP_CURSOR, self.lbp_rel)
        self.gap.decrement()

    def _return_bg_one(self) -> None:
        if self.bg_return.is_zero:
            return
        self.bg_rel = self._mid_left(BG_CURSOR, self.bg_rel)
        self.bg_return.decrement()

    def _finish_lazy_returns(self) -> None:
        while not self.gap.is_zero:
            self._return_p_one()
        while not self.bg_return.is_zero:
            self._return_bg_one()
        # Both spare midpoint readers are now at B.  BGL was maintained with LB.
        self.bp_rel = self.b_rel
        self.lbp_rel = self.lb_rel
        self.bg_rel = self.b_rel
        self.bgl_rel = self.lb_rel

    def _lazy_total(self) -> int:
        own = self._ordinary_steps()
        if self.lazy_background is not None:
            own += self.lazy_background._total()
        return own

    def _advance_lazy_background(self, symbol: str) -> UnaryCounter | None:
        machine = self.lazy_background
        if machine is None or self.lazy_mode is None:
            raise AssertionError("missing lazy background")
        mode_at_start = self.lazy_mode
        start = self._lazy_total()
        budget = self.background_work_budget
        output: Optional[int] = None

        # Once the active suffix has been frozen, later input symbols are
        # appended directly to the retained terminal.  COPY mode instead sees
        # them through the outer BG history cursor.
        if mode_at_start == "RETURN":
            machine.word += symbol
            machine.terminal.append(symbol)
        elif mode_at_start == "RUN":
            event = machine.feed(symbol, budget_override=budget)
            return machine.candidate_counter if event.output_gap is not None else None

        while self._lazy_total() - start < budget:
            if self.lazy_mode == "COPY":
                if self.lazy_copy_needed:
                    value = self._symbol(BG_CURSOR)
                    if value not in "01":
                        raise AssertionError(("BG not on input", value, self.bg_rel))
                    machine.word += value
                    machine.terminal.append(value)
                    self.lazy_copy_needed = False
                    continue
                if self._has_right_data(BG_CURSOR):
                    self.bg_rel = self._mid_right(BG_CURSOR, self.bg_rel)
                    self.bg_return.increment()
                    self.lazy_copy_needed = True
                    continue
                self.lazy_mode = "RETURN"
                continue

            if self.lazy_mode == "RETURN":
                if not self.gap.is_zero:
                    self._return_p_one()
                    continue
                if not self.bg_return.is_zero:
                    self._return_bg_one()
                    continue
                self.bp_rel = self.b_rel
                self.lbp_rel = self.lb_rel
                self.bg_rel = self.b_rel
                machine.begin_launch()
                self.lazy_mode = "RUN"
                continue

            assert self.lazy_mode == "RUN"
            remaining = budget - (self._lazy_total() - start)
            _, output = machine._spend(max(1, remaining))
            break
        return machine.candidate_counter if output is not None else None

    def _install_background_gap_counter(self, emitted: UnaryCounter) -> None:
        if not self.gap.is_zero or not self.bg_return.is_zero:
            raise AssertionError((
                "background emitted before heads returned",
                self.gap.value(), self.bg_return.value(),
            ))
        audit_distance = emitted.value() if self.audit else None
        while not emitted.is_zero:
            self.bp_rel = self._mid_right(BP_CURSOR, self.bp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.gap.increment()
            emitted.decrement()
        if self.audit:
            assert audit_distance is not None
            self.bp = self.b + audit_distance
        # Lemma 3.3 emits exactly at active length 16*d.
        self.k.fresh_zero()
        self.lazy_background = None
        self.lazy_mode = None
        self.lazy_copy_needed = False

    def _discard_lazy_background(self) -> None:
        self._finish_lazy_returns()
        self.lazy_background = None
        self.lazy_mode = None
        self.lazy_copy_needed = False

    def _install_background_gap(self, distance: int) -> None:
        if not self.gap.is_zero or not self.bg_return.is_zero:
            raise AssertionError(("background emitted before heads returned", self.gap.value(), self.bg_return.value()))
        super()._install_background_gap(distance)
        # BG/BGL are already aligned with B/LB.
        self.lazy_background = None
        self.lazy_mode = None
        self.lazy_copy_needed = False

    # ------------------------------------------------------------------

    def append(self, symbol: str) -> OuterStepRecord:  # noqa: C901
        if symbol not in "01":
            raise ValueError(symbol)
        start = self._ordinary_steps()
        start_cp = self.checkpoint_steps
        start_bg = self.background_steps
        old_b, old_bp = self.b, self.bp
        old_b_rel, old_bp_rel = self.b_rel, self.bp_rel
        gap_large = self.k.is_positive if self.bp is not None else False

        self._append_all(symbol)
        self.b_rel = self._advance_mid_for_append(B_CURSOR, old_b_rel)
        self.bp_rel = self._advance_mid_for_append(BP_CURSOR, old_bp_rel)
        self.bg_rel = self._advance_mid_for_append(BG_CURSOR, self.bg_rel)
        self.lb_rel, b_ok = self._advance_left_and_test(
            LB_CURSOR, self.lb_rel, old_b_rel, symbol
        )
        self.lbp_rel, bp_ok = self._advance_left_and_test(
            LBP_CURSOR, self.lbp_rel, old_bp_rel, symbol
        )
        self.bgl_rel = self._advance_bgl_no_test(self.bgl_rel, old_b_rel)
        if self.bp is None:
            bp_ok = False
        else:
            self.k.decrement()

        self.word += symbol
        if self.bp is None:
            case = (
                UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES
                if b_ok else UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS
            )
        elif b_ok and bp_ok:
            case = UpdateCase.ONE_BOTH_SURVIVE
        elif not b_ok and not bp_ok:
            case = UpdateCase.TWO_BOTH_FAIL
        elif not b_ok and bp_ok:
            case = UpdateCase.THREE_SECOND_SURVIVES
        else:
            case = UpdateCase.FOUR_FIRST_SURVIVES

        if case is UpdateCase.ONE_BOTH_SURVIVE:
            pass

        elif case is UpdateCase.TWO_BOTH_FAIL:
            self._align_second_to_first()
            checkpoint, length, _ = self._run_checkpoint_from_b()
            self._install_recover_pair(checkpoint, length)
            self._recompute_k()

        elif case is UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS:
            self._discard_lazy_background()
            checkpoint, length, _ = self._run_checkpoint_from_b()
            self._install_recover_pair(checkpoint, length)
            self._recompute_k()

        elif case is UpdateCase.THREE_SECOND_SURVIVES:
            radius = self._promote_second(save_radius=True)
            if self.b_rel is MidRelation.AT_END:
                self.bp_rel = self._mid_right(BP_CURSOR, self.bp_rel)
                self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
                self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
                self.gap.increment()
                if self.audit:
                    self.bp = self.b + 1
                self._update_k_after_promotion(radius)
            elif gap_large:
                checkpoint, length, _ = self._run_checkpoint_from_b()
                found, _ = self._install_next_from_out1(checkpoint, length)
                if not found:
                    raise AssertionError(("large recovery missing next", checkpoint.word))
                self._update_k_after_promotion(radius)
            else:
                quota = self._counter_multiple(radius, 4)
                checkpoint, length, _ = self._run_checkpoint_from_b(quota=quota)
                found, _ = self._install_next_from_out1(checkpoint, length, radius=radius)
                if found:
                    self._update_k_after_promotion(radius)
                else:
                    self._align_second_to_first()  # O(d), paid by this case-3 jump.
                    self.bp = None
                    self._start_lazy_background()

        elif case is UpdateCase.FOUR_FIRST_SURVIVES:
            # Constant-time drop: P remains stale and is returned later.
            self.bp = None
            self._start_lazy_background()

        elif case is UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES:
            emitted = self._advance_lazy_background(symbol)
            if emitted is not None:
                self._install_background_gap_counter(emitted)
            else:
                self.bp = None

        else:  # pragma: no cover
            raise AssertionError(case)

        if self.audit:
            exact_b, exact_bp = b3_pair(self.word)
            assert self.b == exact_b, (case, self.word, self.b, exact_b)
            if self.bp is not None:
                assert self.bp == exact_bp, (case, self.word, self.bp, exact_bp)
        self._assert_incremental_invariant()
        output_bit = self.accepts
        return OuterStepRecord(
            symbol, case, old_b, -1 if old_bp is None else old_bp,
            self.b, -1 if self.bp is None else self.bp,
            self.bp is not None, output_bit,
            self._ordinary_steps() - start,
            self.checkpoint_steps - start_cp,
            self.background_steps - start_bg,
        )

    def _assert_incremental_invariant(self) -> None:
        if not self.audit:
            return
        exact_b, exact_bp = b3_pair(self.word)
        assert self.b == exact_b
        if self.bp is not None:
            assert self.bp == exact_bp
            assert self.lazy_mode is None
            assert self.gap.value() == self.bp - self.b
            assert self.k.value() == 16 * (self.bp - self.b) - (len(self.word) - self.b)
            assert self.bg_return.is_zero
            assert self.bg_rel is self.b_rel
            assert self.bgl_rel is self.lb_rel
        else:
            assert self.lazy_mode in {"COPY", "RETURN", "RUN"}
            # B and BGL remain the live invariant heads.  P and BG may be in
            # bounded return/copy phases and are audited when they rejoin.
            assert self.bgl_rel is self.lb_rel
