"""Three-cursor input-history terminal built from ordinary zipper tables.

The terminal keeps three identical append-only copies of the binary input:

* ``CURRENT`` follows post-checkpoint input during CATCH_UP/FOLLOW;
* ``LAG`` follows the symbol one candidate period behind;
* ``COPY`` supplies monotone source extensions to the reusable checkpoint TM.

Each copy is the twelve-tape ordinary machine exported by
``history_zipper_ordinary_tm``.  This audit composition executes only literal
one-cell rows for cursor operations.  Direct writes to the checkpoint's three
ordinary source tapes are likewise counted as one simultaneous TM step.
"""

from __future__ import annotations

from dataclasses import dataclass

import checkpoint_ordinary_tm as cp
import checkpoint_reusable_tm as reusable
from checkpoint_reusable_tm import ReusableCheckpointConfiguration
from history_zipper_ordinary_tm import (
    BLANK,
    BOTTOM,
    FRONT_PHYS,
    QUEUE_PHYS_BASE,
    READY_TASK,
    ROLE_INDEX,
    current_symbol,
    initial_configuration,
    run_command,
)
from symbolic_tm import SymbolicConfiguration

CURRENT = 0
LAG = 1
COPY = 2
HISTORY_SENTINEL = "#"
CURSOR_COUNT = 3


@dataclass(frozen=True)
class TerminalOperation:
    name: str
    ordinary_steps: int


class OrdinaryHistoryTerminal:
    def __init__(self, initial: str = "") -> None:
        if any(ch not in "01" for ch in initial):
            raise ValueError(initial)
        self.word = ""
        self.cursors: list[SymbolicConfiguration] = [
            initial_configuration((HISTORY_SENTINEL,), reader=0)
            for _ in range(CURSOR_COUNT)
        ]
        self.ordinary_steps = 0
        for symbol in initial:
            self.append(symbol)

    def _run(self, cursor: int, command: str) -> int:
        steps = run_command(self.cursors[cursor], command)
        self.ordinary_steps += steps
        return steps

    def append(self, symbol: str) -> TerminalOperation:
        if symbol not in "01":
            raise ValueError(symbol)
        before = self.ordinary_steps
        command = "APPEND0" if symbol == "0" else "APPEND1"
        for cursor in range(CURSOR_COUNT):
            self._run(cursor, command)
        self.word += symbol
        return TerminalOperation("append", self.ordinary_steps - before)

    def symbol(self, cursor: int) -> str:
        return current_symbol(self.cursors[cursor])

    def _stack_empty(self, cursor: int, physical: int) -> bool:
        config = self.cursors[cursor]
        return config.tapes[physical].get(config.heads[physical], BLANK) == BOTTOM

    def has_right_data(self, cursor: int) -> bool:
        config = self.cursors[cursor]
        state = config.state
        if getattr(state, "task", None) != READY_TASK:
            raise ValueError(("cursor is not ready", state))
        if not self._stack_empty(cursor, FRONT_PHYS):
            return True
        f1_physical = QUEUE_PHYS_BASE + state.mapping[ROLE_INDEX["f1"]]
        return not self._stack_empty(cursor, f1_physical)

    def move_right(self, cursor: int) -> TerminalOperation:
        before = self.ordinary_steps
        self._run(cursor, "RIGHT")
        return TerminalOperation("right", self.ordinary_steps - before)

    def move_left(self, cursor: int) -> TerminalOperation:
        before = self.ordinary_steps
        self._run(cursor, "LEFT")
        return TerminalOperation("left", self.ordinary_steps - before)

    def sync_to_end(self, cursor: int) -> TerminalOperation:
        before = self.ordinary_steps
        while self.has_right_data(cursor):
            self._run(cursor, "RIGHT")
        return TerminalOperation("sync_to_end", self.ordinary_steps - before)

    def rewind_to_sentinel(self, cursor: int) -> TerminalOperation:
        before = self.ordinary_steps
        while self.symbol(cursor) != HISTORY_SENTINEL:
            self._run(cursor, "LEFT")
        return TerminalOperation("rewind", self.ordinary_steps - before)

    def move_left_n(self, cursor: int, amount: int) -> TerminalOperation:
        if amount < 0:
            raise ValueError(amount)
        before = self.ordinary_steps
        for _ in range(amount):
            self._run(cursor, "LEFT")
        return TerminalOperation("left_n", self.ordinary_steps - before)

    def prepare_comparison(self, period: int) -> TerminalOperation:
        if period <= 0:
            raise ValueError(period)
        before = self.ordinary_steps
        # Both cursors scan the last symbol of the frozen checkpoint.  The lag
        # cursor is positioned at the first corresponding old symbol.
        self.move_left_n(LAG, period - 1)
        return TerminalOperation("prepare_comparison", self.ordinary_steps - before)

    def compare_next(self, *, compare: bool = True) -> tuple[bool, TerminalOperation]:
        """Advance CURRENT to its next symbol and compare with LAG.

        LAG already scans the corresponding period-earlier symbol.  It is
        advanced after the comparison so the pair remains aligned.
        """
        before = self.ordinary_steps
        self._run(CURRENT, "RIGHT")
        left = self.symbol(CURRENT)
        if left not in "01":
            raise AssertionError(("CURRENT did not reach an input symbol", left))
        match = True if not compare else left == self.symbol(LAG)
        self._run(LAG, "RIGHT")
        return match, TerminalOperation("compare_next", self.ordinary_steps - before)

    # ------------------------------------------------------------------
    # Checkpoint source initialization/extension.

    @staticmethod
    def blank_checkpoint_shell() -> ReusableCheckpointConfiguration:
        """Return a fixed blank shell, independent of the input word."""
        template = cp.initial_configuration("0")
        tapes = [dict(tape) for tape in template.tapes] + [{}]
        heads = list(template.heads) + [0]
        for tape_index in (cp.SRC_FWD, cp.SRC_REV, cp.SRC_FWD2):
            tapes[tape_index] = {0: cp.SENTINEL, 1: cp.END}
            heads[tape_index] = 1
        return ReusableCheckpointConfiguration(cp.INITIAL, tapes, heads, "")

    @staticmethod
    def _source_scanned(
        checkpoint: ReusableCheckpointConfiguration, tape: int
    ) -> str:
        return checkpoint.tapes[tape].get(checkpoint.heads[tape], cp.BLANK)

    @staticmethod
    def _direct_move(
        checkpoint: ReusableCheckpointConfiguration,
        moves: dict[int, int],
    ) -> None:
        for tape, amount in moves.items():
            if amount not in (-1, 0, 1):
                raise ValueError(amount)
            checkpoint.heads[tape] += amount
        checkpoint.steps += 1

    @staticmethod
    def _direct_write_move(
        checkpoint: ReusableCheckpointConfiguration,
        writes: dict[int, str],
        moves: dict[int, int] | None = None,
    ) -> None:
        for tape, symbol in writes.items():
            position = checkpoint.heads[tape]
            if symbol == cp.BLANK:
                checkpoint.tapes[tape].pop(position, None)
            else:
                checkpoint.tapes[tape][position] = symbol
        for tape, amount in (moves or {}).items():
            checkpoint.heads[tape] += amount
        checkpoint.steps += 1

    def _copy_pending_to_sources(
        self,
        checkpoint: ReusableCheckpointConfiguration,
    ) -> int:
        before = self.ordinary_steps + checkpoint.steps
        sources = (cp.SRC_FWD, cp.SRC_REV, cp.SRC_FWD2)

        # Completed checkpoints leave the forward readers on END and the
        # reverse reader on the sentinel.  Move every source head to END using
        # literal one-cell ordinary transitions.
        for tape in sources:
            while self._source_scanned(checkpoint, tape) != cp.END:
                self._direct_move(checkpoint, {tape: 1})

        while self.has_right_data(COPY):
            self._run(COPY, "RIGHT")
            symbol = self.symbol(COPY)
            if symbol not in "01":
                raise AssertionError(("COPY reached noninput symbol", symbol))
            scanned = tuple(self._source_scanned(checkpoint, tape) for tape in sources)
            if any(value not in (cp.END, cp.BLANK) for value in scanned):
                raise AssertionError(("source writer not at terminal", scanned))
            self._direct_write_move(
                checkpoint,
                {tape: symbol for tape in sources},
                {tape: 1 for tape in sources},
            )

        self._direct_write_move(checkpoint, {tape: cp.END for tape in sources})
        checkpoint.word = self.word
        return self.ordinary_steps + checkpoint.steps - before

    def initialize_checkpoint(self) -> tuple[ReusableCheckpointConfiguration, TerminalOperation]:
        if not self.word:
            raise ValueError("cannot launch an empty checkpoint")
        before = self.ordinary_steps
        checkpoint = self.blank_checkpoint_shell()

        # COPY starts on the sentinel.  Move through the complete current word.
        self._copy_pending_to_sources(checkpoint)

        # Install the source-head positions expected by the one-shot body:
        # forward copies on the first character, reverse copy on the last.
        n = len(self.word)
        for _ in range(n):
            self._direct_move(checkpoint, {cp.SRC_FWD: -1, cp.SRC_FWD2: -1})
        self._direct_move(checkpoint, {cp.SRC_REV: -1})

        # CURRENT and LAG define the frozen boundary for later catch-up.
        self.sync_to_end(CURRENT)
        self.sync_to_end(LAG)
        return checkpoint, TerminalOperation(
            "initialize_checkpoint", self.ordinary_steps - before + checkpoint.steps
        )

    def request_extended_checkpoint(
        self,
        checkpoint: ReusableCheckpointConfiguration,
    ) -> TerminalOperation:
        if checkpoint.state != reusable.READY:
            raise ValueError("previous checkpoint is not READY")
        before = self.ordinary_steps + checkpoint.steps
        self._copy_pending_to_sources(checkpoint)
        # Producer-paid cleanup occurred before this extension, so source
        # construction must install the one-shot entry head positions itself.
        # This cost belongs to the new request's source-construction term; the
        # transition from clean READY into cp.INITIAL remains constant-time.
        while self._source_scanned(checkpoint, cp.SRC_FWD) != cp.SENTINEL:
            self._direct_move(checkpoint, {cp.SRC_FWD: -1})
        while self._source_scanned(checkpoint, cp.SRC_FWD2) != cp.SENTINEL:
            self._direct_move(checkpoint, {cp.SRC_FWD2: -1})
        self._direct_move(checkpoint, {cp.SRC_FWD: 1, cp.SRC_FWD2: 1, cp.SRC_REV: -1})
        # Comparison cursors are restored to the new frozen boundary.  This is
        # a direct sequence of ordinary zipper rows, not a host repositioning.
        self.sync_to_end(CURRENT)
        self.sync_to_end(LAG)
        checkpoint.tapes[reusable.CONTROL_TAPE][checkpoint.heads[reusable.CONTROL_TAPE]] = reusable.REQUEST
        reusable.step(checkpoint)
        return TerminalOperation(
            "request_extended_checkpoint",
            self.ordinary_steps + checkpoint.steps - before,
        )
