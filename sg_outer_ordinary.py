"""Outer Seiferas--Galil midpoint cursors using only ordinary tape operations.

This module removes the host-level ``B3``/``B3'`` positions from the worker
composition.  Four independent strict append/read zippers carry the logical
midpoint and LEFT cursors; unary tapes carry the known gap and the signed
quantity ``16*(B3'-B3) - (RIGHT-B3)``.  RECOVER and LOCAL results are installed
by walking the checkpoint machine's unary marker tapes one cell at a time.

Python integers and ``word`` are retained only for differential assertions and
human-readable records.  Branches use finite relation flags, scanned tape
symbols, unary zero/sign tests, and the already generated ordinary checkpoint
rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import checkpoint_ordinary_tm as cp
import checkpoint_reusable_tm as reusable
from checkpoint_reusable_tm import ReusableCheckpointConfiguration
from history_zipper_ordinary_tm import (
    BLANK as ZIP_BLANK,
    BOTTOM,
    FRONT_PHYS,
    QUEUE_PHYS_BASE,
    READY_TASK,
    ROLE_INDEX,
    current_symbol,
    initial_configuration,
    run_command,
)
from lemma33_checkpoint_terminal import PersistentLemma33CheckpointTerminal
from ordinary_history_terminal import HISTORY_SENTINEL, OrdinaryHistoryTerminal
from ordinary_unary_counter import SignedUnaryCounter, UnaryCounter
from sg_zero_ratio import UpdateCase, b3_pair
from symbolic_tm import SymbolicConfiguration


class MidRelation(Enum):
    BEFORE_END = auto()  # logical position < RIGHT; reader scans that character
    AT_END = auto()      # logical boundary RIGHT; reader is clamped to last char
    AFTER_END = auto()   # logical boundary RIGHT+1; reader is clamped to last char


class LeftRelation(Enum):
    EXACT = auto()       # reader scans the exact logical cell (may be left of sentinel)
    AT_END = auto()      # logical boundary RIGHT, reader clamped to last character
    AFTER1 = auto()      # transient RIGHT+1
    AFTER2 = auto()      # logical position RIGHT+2


B_CURSOR = "B"
BP_CURSOR = "BP"
LB_CURSOR = "LB"
LBP_CURSOR = "LBP"
CURSORS = (B_CURSOR, BP_CURSOR, LB_CURSOR, LBP_CURSOR)


@dataclass(frozen=True)
class OuterStepRecord:
    symbol: str
    case: UpdateCase
    old_b: int
    old_bp: int
    new_b: int
    new_bp: int
    second_known: bool
    output: bool
    ordinary_steps: int
    checkpoint_steps: int
    background_steps: int


class OrdinarySGOuter:
    """Operational outer product over ordinary zipper/checkpoint transitions."""

    def __init__(
        self,
        *,
        c: int = 16,
        background_work_budget: int = 200_000,
        audit: bool = True,
    ) -> None:
        if c != 16:
            raise ValueError("ordinary outer product is specialized to c=16")
        self.c = c
        self.audit = audit
        self.background_work_budget = background_work_budget
        self.word = ""
        self.b = 0
        self.bp: Optional[int] = 1
        self.cursors: dict[str, SymbolicConfiguration] = {
            name: initial_configuration((HISTORY_SENTINEL,), reader=0)
            for name in CURSORS
        }
        self.b_rel = MidRelation.AT_END
        self.bp_rel = MidRelation.AFTER_END
        self.lb_rel = LeftRelation.AT_END
        self.lbp_rel = LeftRelation.AFTER2
        self.gap = UnaryCounter.zero()
        self.gap.increment()  # B3'-B3 = 1 initially.
        self.k = SignedUnaryCounter.zero()
        for _ in range(16):
            self.k.increment()
        self.background: PersistentLemma33CheckpointTerminal | None = None
        self.zipper_steps = 0
        self.control_steps = 0
        self.checkpoint_steps = 0
        self.background_steps = 0
        self._assert_invariant()

    # ------------------------------------------------------------------
    # Ordinary zipper terminal operations.

    def _run(self, cursor: str, command: str) -> int:
        steps = run_command(self.cursors[cursor], command)
        self.zipper_steps += steps
        return steps

    def _symbol(self, cursor: str) -> str:
        return current_symbol(self.cursors[cursor])

    def _stack_empty(self, cursor: str, physical: int) -> bool:
        config = self.cursors[cursor]
        return config.tapes[physical].get(config.heads[physical], ZIP_BLANK) == BOTTOM

    def _has_right_data(self, cursor: str) -> bool:
        config = self.cursors[cursor]
        state = config.state
        if getattr(state, "task", None) != READY_TASK:
            raise ValueError((cursor, state))
        if not self._stack_empty(cursor, FRONT_PHYS):
            return True
        f1_physical = QUEUE_PHYS_BASE + state.mapping[ROLE_INDEX["f1"]]
        return not self._stack_empty(cursor, f1_physical)

    def _append_all(self, symbol: str) -> None:
        command = "APPEND0" if symbol == "0" else "APPEND1"
        for cursor in CURSORS:
            self._run(cursor, command)

    # ------------------------------------------------------------------
    # Logical midpoint and LEFT one-cell movement with end clamping.

    def _mid_right(self, cursor: str, relation: MidRelation) -> MidRelation:
        if relation is MidRelation.BEFORE_END:
            if self._has_right_data(cursor):
                self._run(cursor, "RIGHT")
                return MidRelation.BEFORE_END
            self.control_steps += 1
            return MidRelation.AT_END
        if relation is MidRelation.AT_END:
            self.control_steps += 1
            return MidRelation.AFTER_END
        raise ValueError(("midpoint moved beyond RIGHT+1", cursor, relation))

    def _mid_left(self, cursor: str, relation: MidRelation) -> MidRelation:
        if relation is MidRelation.AFTER_END:
            self.control_steps += 1
            return MidRelation.AT_END
        if relation is MidRelation.AT_END:
            self.control_steps += 1
            return MidRelation.BEFORE_END
        self._run(cursor, "LEFT")
        return MidRelation.BEFORE_END

    def _left_right(self, cursor: str, relation: LeftRelation) -> LeftRelation:
        if relation is LeftRelation.EXACT:
            if self._has_right_data(cursor):
                self._run(cursor, "RIGHT")
                return LeftRelation.EXACT
            self.control_steps += 1
            return LeftRelation.AT_END
        if relation is LeftRelation.AT_END:
            self.control_steps += 1
            return LeftRelation.AFTER1
        if relation is LeftRelation.AFTER1:
            self.control_steps += 1
            return LeftRelation.AFTER2
        raise ValueError(("LEFT moved beyond RIGHT+2", cursor, relation))

    def _left_left(self, cursor: str, relation: LeftRelation) -> LeftRelation:
        if relation is LeftRelation.AFTER2:
            self.control_steps += 1
            return LeftRelation.AFTER1
        if relation is LeftRelation.AFTER1:
            self.control_steps += 1
            return LeftRelation.AT_END
        if relation is LeftRelation.AT_END:
            self.control_steps += 1
            return LeftRelation.EXACT
        self._run(cursor, "LEFT")
        return LeftRelation.EXACT

    def _advance_mid_for_append(self, cursor: str, relation: MidRelation) -> MidRelation:
        if relation in (MidRelation.AT_END, MidRelation.AFTER_END):
            # The newly appended symbol is now immediately to the reader's right.
            self._run(cursor, "RIGHT")
            return (
                MidRelation.BEFORE_END
                if relation is MidRelation.AT_END
                else MidRelation.AT_END
            )
        return relation

    def _advance_left_and_test(
        self,
        cursor: str,
        relation: LeftRelation,
        midpoint_relation_before: MidRelation,
        symbol: str,
    ) -> tuple[LeftRelation, bool]:
        if midpoint_relation_before is MidRelation.AFTER_END:
            if relation is not LeftRelation.AFTER2:
                raise AssertionError((cursor, relation, midpoint_relation_before))
            self._run(cursor, "RIGHT")
            return LeftRelation.AT_END, True
        if relation is LeftRelation.AT_END:
            relation = LeftRelation.EXACT
            self.control_steps += 1
        elif relation is LeftRelation.EXACT:
            self._run(cursor, "LEFT")
        else:
            raise AssertionError((cursor, relation, midpoint_relation_before))
        return relation, self._symbol(cursor) == symbol

    # ------------------------------------------------------------------
    # Gap alignment and installation.

    def _align_second_to_first(self) -> None:
        while not self.gap.is_zero:
            self.bp_rel = self._mid_left(BP_CURSOR, self.bp_rel)
            self.lbp_rel = self._left_left(LBP_CURSOR, self.lbp_rel)
            self.lbp_rel = self._left_left(LBP_CURSOR, self.lbp_rel)
            self.gap.decrement()
        self.k.clear()
        if self.audit:
            assert self.bp is not None
            self.bp = self.b

    def _promote_second(self, *, save_radius: bool) -> UnaryCounter:
        radius = UnaryCounter.zero()
        while not self.gap.is_zero:
            self.b_rel = self._mid_right(B_CURSOR, self.b_rel)
            self.lb_rel = self._left_right(LB_CURSOR, self.lb_rel)
            self.lb_rel = self._left_right(LB_CURSOR, self.lb_rel)
            self.gap.decrement()
            if save_radius:
                radius.increment()
        if self.audit:
            assert self.bp is not None
            self.b = self.bp
        return radius

    @staticmethod
    def _counter_multiple(source: UnaryCounter, factor: int) -> UnaryCounter:
        target = UnaryCounter.zero()
        moved = 0
        while not source.is_zero:
            source.head -= 1
            source.steps += 1
            moved += 1
            for _ in range(factor):
                target.increment()
        for _ in range(moved):
            source.head += 1
            source.steps += 1
        return target

    # ------------------------------------------------------------------
    # One-shot checkpoint copied from the B cursor, cell by cell.

    @staticmethod
    def _cp_scanned(config: ReusableCheckpointConfiguration, tape: int) -> str:
        return config.tapes[tape].get(config.heads[tape], cp.BLANK)

    def _cp_move(self, config: ReusableCheckpointConfiguration, moves: dict[int, int]) -> None:
        for tape, amount in moves.items():
            if amount not in (-1, 0, 1):
                raise ValueError(amount)
            config.heads[tape] += amount
        config.steps += 1
        self.checkpoint_steps += 1

    def _cp_write_move(
        self,
        config: ReusableCheckpointConfiguration,
        writes: dict[int, str],
        moves: dict[int, int] | None = None,
    ) -> None:
        for tape, value in writes.items():
            pos = config.heads[tape]
            if value == cp.BLANK:
                config.tapes[tape].pop(pos, None)
            else:
                config.tapes[tape][pos] = value
        for tape, amount in (moves or {}).items():
            config.heads[tape] += amount
        config.steps += 1
        self.checkpoint_steps += 1

    def _run_checkpoint_from_b(
        self,
        *,
        quota: UnaryCounter | None = None,
    ) -> tuple[ReusableCheckpointConfiguration, UnaryCounter, str]:
        if self.b_rel is not MidRelation.BEFORE_END:
            raise AssertionError(("worker requires nonempty active suffix", self.b_rel, self.word, self.b))
        checkpoint = OrdinaryHistoryTerminal.blank_checkpoint_shell()
        length = UnaryCounter.zero()
        restore = UnaryCounter.zero()
        chars: list[str] = []
        sources = (cp.SRC_FWD, cp.SRC_REV, cp.SRC_FWD2)

        while quota is None or not quota.is_zero:
            symbol = self._symbol(B_CURSOR)
            if symbol not in "01":
                raise AssertionError(("B cursor not on input", symbol, self.b_rel, self.word, self.b))
            self._cp_write_move(
                checkpoint,
                {tape: symbol for tape in sources},
                {tape: 1 for tape in sources},
            )
            chars.append(symbol)
            length.increment()
            restore.increment()
            if quota is not None:
                quota.decrement()
            if (quota is not None and quota.is_zero) or not self._has_right_data(B_CURSOR):
                break
            self._run(B_CURSOR, "RIGHT")

        self._cp_write_move(checkpoint, {tape: cp.END for tape in sources})
        self._cp_move(checkpoint, {cp.SRC_REV: -1})
        first = True
        while not restore.is_zero:
            self._cp_move(checkpoint, {cp.SRC_FWD: -1, cp.SRC_FWD2: -1})
            if not first:
                self._run(B_CURSOR, "LEFT")
            first = False
            restore.decrement()

        checkpoint.word = "".join(chars)
        before = checkpoint.steps
        reusable.run_to_result(checkpoint)
        self.checkpoint_steps += checkpoint.steps - before
        return checkpoint, length, checkpoint.word

    def _rewind_marker_tape(self, checkpoint: ReusableCheckpointConfiguration, tape: int) -> None:
        while self._cp_scanned(checkpoint, tape) != cp.MARK:
            self._cp_move(checkpoint, {tape: -1})

    def _copy_counter(self, source: UnaryCounter) -> UnaryCounter:
        target = UnaryCounter.zero()
        target.copy_from(source)
        return target

    def _scan_gap(
        self,
        checkpoint: ReusableCheckpointConfiguration,
        tape: int,
        limit: UnaryCounter,
        on_unit,
        *,
        automatic_after_limit: bool,
    ) -> tuple[bool, int]:
        self._rewind_marker_tape(checkpoint, tape)
        distance = 0
        while not limit.is_zero:
            self._cp_move(checkpoint, {tape: 1})
            distance += 1
            on_unit()
            limit.decrement()
            if self._cp_scanned(checkpoint, tape) == cp.GAP:
                return True, distance
        if automatic_after_limit:
            on_unit()
            distance += 1
        return False, distance

    def _install_recover_pair(self, checkpoint, length: UnaryCounter) -> tuple[int, int]:
        # Both logical midpoint groups are aligned at the old anchor and gap=0.
        limit2 = self._copy_counter(length)

        def second_unit() -> None:
            self.bp_rel = self._mid_right(BP_CURSOR, self.bp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.gap.increment()

        found2, d2 = self._scan_gap(
            checkpoint, cp.OUT2_TAPE, limit2, second_unit,
            automatic_after_limit=True,
        )
        del found2

        limit1 = self._copy_counter(length)

        def first_unit() -> None:
            self.b_rel = self._mid_right(B_CURSOR, self.b_rel)
            self.lb_rel = self._left_right(LB_CURSOR, self.lb_rel)
            self.lb_rel = self._left_right(LB_CURSOR, self.lb_rel)
            self.gap.decrement()

        found1, d1 = self._scan_gap(
            checkpoint, cp.OUT1_TAPE, limit1, first_unit,
            automatic_after_limit=False,
        )
        if not found1:
            raise AssertionError(("OUT1 missing", checkpoint.word))
        self.bp = (self.b + d2) if self.audit else 0
        self.b = (self.b + d1) if self.audit else 0
        return d1, d2

    def _install_next_from_out1(
        self,
        checkpoint: ReusableCheckpointConfiguration,
        length: UnaryCounter,
        *,
        radius: UnaryCounter | None = None,
    ) -> tuple[bool, int | None]:
        limit = self._copy_counter(radius if radius is not None else length)

        def unit() -> None:
            self.bp_rel = self._mid_right(BP_CURSOR, self.bp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.gap.increment()

        found, distance = self._scan_gap(
            checkpoint, cp.OUT1_TAPE, limit, unit,
            automatic_after_limit=False,
        )
        if found and self.audit:
            self.bp = self.b + distance
        return found, distance if found else None

    # ------------------------------------------------------------------
    # Signed large-gap register.

    @staticmethod
    def _walk_counter_preserving(counter: UnaryCounter, action) -> None:
        moved = 0
        while not counter.is_zero:
            counter.head -= 1
            counter.steps += 1
            moved += 1
            action()
        for _ in range(moved):
            counter.head += 1
            counter.steps += 1

    def _update_k_after_promotion(self, old_gap: UnaryCounter) -> None:
        # After the append K has already become K_old-1.  Promotion by d and
        # installation of a new gap e changes it by 16e-15d.  This avoids an
        # active-suffix scan in the small-gap case, preserving the O(d) bound.
        self._walk_counter_preserving(
            old_gap, lambda: [self.k.decrement() for _ in range(15)]
        )
        self._walk_counter_preserving(
            self.gap, lambda: [self.k.increment() for _ in range(16)]
        )

    def _recompute_k(self) -> None:
        self.k.clear()
        moved = 0
        while not self.gap.is_zero:
            self.gap.head -= 1
            self.gap.steps += 1
            moved += 1
            for _ in range(16):
                self.k.increment()
        for _ in range(moved):
            self.gap.head += 1
            self.gap.steps += 1

        if self.b_rel is MidRelation.BEFORE_END:
            restore = UnaryCounter.zero()
            while True:
                self.k.decrement()
                restore.increment()
                if not self._has_right_data(B_CURSOR):
                    break
                self._run(B_CURSOR, "RIGHT")
            first = True
            while not restore.is_zero:
                if not first:
                    self._run(B_CURSOR, "LEFT")
                first = False
                restore.decrement()
        elif self.b_rel is not MidRelation.AT_END:
            raise AssertionError(("least midpoint beyond end", self.b_rel))

    # ------------------------------------------------------------------
    # Background construction and output installation.

    def _start_background(self) -> None:
        bg = PersistentLemma33CheckpointTerminal(
            initial="",
            work_budget=self.background_work_budget,
            bootstrap_limit=0,
            audit=self.audit,
        )
        if self.b_rel is not MidRelation.BEFORE_END:
            raise AssertionError(("background active suffix empty", self.b_rel))
        restore = UnaryCounter.zero()
        while True:
            symbol = self._symbol(B_CURSOR)
            bg.word += symbol
            bg.terminal.append(symbol)
            restore.increment()
            if not self._has_right_data(B_CURSOR):
                break
            self._run(B_CURSOR, "RIGHT")
        first = True
        while not restore.is_zero:
            if not first:
                self._run(B_CURSOR, "LEFT")
            first = False
            restore.decrement()
        bg._launch()
        self.background = bg

    def _install_background_gap(self, distance: int) -> None:
        emitted = UnaryCounter.zero()
        for _ in range(distance):
            emitted.increment()
        while not emitted.is_zero:
            self.bp_rel = self._mid_right(BP_CURSOR, self.bp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.lbp_rel = self._left_right(LBP_CURSOR, self.lbp_rel)
            self.gap.increment()
            emitted.decrement()
        if self.audit:
            self.bp = self.b + distance
        # Lemma 3.3 emits exactly at active length 16*d.
        self.k.fresh_zero()

    # ------------------------------------------------------------------

    def _ordinary_steps(self) -> int:
        return (
            self.zipper_steps + self.control_steps + self.checkpoint_steps
            + self.gap.steps + self.k.steps
        )

    def _is_accepting_cursor(self) -> bool:
        if not self.word:
            return True
        if self.lb_rel is not LeftRelation.EXACT:
            return False
        self._run(LB_CURSOR, "LEFT")
        symbol = self._symbol(LB_CURSOR)
        self._run(LB_CURSOR, "RIGHT")
        return symbol == HISTORY_SENTINEL

    @property
    def accepts(self) -> bool:
        result = self._is_accepting_cursor()
        if self.audit:
            assert result == (len(self.word) % 2 == 0 and self.word == self.word[::-1])
        return result

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
        self.lb_rel, b_ok = self._advance_left_and_test(
            LB_CURSOR, self.lb_rel, old_b_rel, symbol
        )
        self.lbp_rel, bp_ok = self._advance_left_and_test(
            LBP_CURSOR, self.lbp_rel, old_bp_rel, symbol
        )
        if self.bp is None:
            # LBP is a spare aligned with LB, so its survival result is ignored.
            bp_ok = False
        else:
            self.k.decrement()  # RIGHT-B increases by one while B is still fixed.

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

        elif case in (UpdateCase.TWO_BOTH_FAIL, UpdateCase.SIX_SECOND_UNKNOWN_FIRST_FAILS):
            if self.bp is not None:
                self._align_second_to_first()
            else:
                self.background = None
            checkpoint, length, _ = self._run_checkpoint_from_b()
            self._install_recover_pair(checkpoint, length)
            self._recompute_k()
            self.background = None

        elif case is UpdateCase.THREE_SECOND_SURVIVES:
            radius = self._promote_second(save_radius=True)
            # Both midpoint groups now coincide at the promoted B3.  If the
            # promoted midpoint is exactly RIGHT, the next candidate is the
            # automatic RIGHT+1 and no active suffix remains to scan.
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
                    raise AssertionError(("large recovery found no next gap", checkpoint.word))
                self._update_k_after_promotion(radius)
            else:
                quota = self._counter_multiple(radius, 4)
                checkpoint, length, _ = self._run_checkpoint_from_b(quota=quota)
                found, _ = self._install_next_from_out1(
                    checkpoint, length, radius=radius
                )
                if found:
                    self._update_k_after_promotion(radius)
                else:
                    self._align_second_to_first()
                    self.bp = None
                    self._start_background()

        elif case is UpdateCase.FOUR_FIRST_SURVIVES:
            self._align_second_to_first()
            self.bp = None
            self._start_background()

        elif case is UpdateCase.FIVE_SECOND_UNKNOWN_FIRST_SURVIVES:
            if self.background is None:
                raise AssertionError("missing retained background")
            event = self.background.feed(symbol)
            self.background_steps += event.ordinary_steps
            if event.output_gap is not None:
                self._install_background_gap(event.output_gap)
                self.background = None
            else:
                self.bp = None

        else:
            raise AssertionError(case)

        if self.audit:
            exact_b, exact_bp = b3_pair(self.word)
            assert self.b == exact_b, (case, self.word, self.b, exact_b)
            if self.bp is not None:
                assert self.bp == exact_bp, (case, self.word, self.bp, exact_bp)
        self._assert_invariant()
        output = self.accepts
        return OuterStepRecord(
            symbol, case, old_b, -1 if old_bp is None else old_bp,
            self.b, -1 if self.bp is None else self.bp,
            self.bp is not None, output,
            self._ordinary_steps() - start,
            self.checkpoint_steps - start_cp,
            self.background_steps - start_bg,
        )

    def _assert_invariant(self) -> None:
        if not self.audit:
            return
        exact_b, exact_bp = b3_pair(self.word)
        assert self.b == exact_b
        if self.bp is not None:
            assert self.bp == exact_bp
            assert self.gap.value() == self.bp - self.b
            assert self.k.value() == 16 * (self.bp - self.b) - (len(self.word) - self.b)
        else:
            assert self.gap.is_zero
        # Cursor relation flags are audited against the semantic positions.
        def mid_rel(position: int) -> MidRelation:
            if position < len(self.word):
                return MidRelation.BEFORE_END
            if position == len(self.word):
                return MidRelation.AT_END
            if position == len(self.word) + 1:
                return MidRelation.AFTER_END
            raise AssertionError((position, len(self.word)))
        assert self.b_rel is mid_rel(self.b)
        if self.bp is not None:
            assert self.bp_rel is mid_rel(self.bp)
        else:
            assert self.bp_rel is self.b_rel

        def left_rel(value: int) -> LeftRelation:
            if value < len(self.word):
                return LeftRelation.EXACT
            if value == len(self.word):
                return LeftRelation.AT_END
            if value == len(self.word) + 1:
                return LeftRelation.AFTER1
            if value == len(self.word) + 2:
                return LeftRelation.AFTER2
            raise AssertionError((value, len(self.word)))
        assert self.lb_rel is left_rel(2 * self.b - len(self.word))
        if self.bp is not None:
            assert self.lbp_rel is left_rel(2 * self.bp - len(self.word))
        else:
            assert self.lbp_rel is self.lb_rel
