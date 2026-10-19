"""Head-and-tape bookkeeping for the Algorithm-Y checkpoint scan.

This module removes the indexed candidate arrays from
:mod:`checkpoint_scan_y_job`.  Period candidates are written to a unary-indexed
work tape.  Three logical heads move monotonically over that tape while the A
head of Fischer--Paterson Algorithm Y walks the corresponding failure chains.

Every call to :meth:`tick` performs one transition of a finite source machine,
one one-cell initialization move, one one-cell candidate-head move coupled to
an Algorithm-Y A-head move, or one finite-control inspection/write.  The only
host integers below are the displayed positions of those simulated tape heads.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from fp_algorithm_y_multihead import (
    A,
    AFTER_BACK,
    BACK_START,
    HALT,
    MACHINE,
    MultiheadConfiguration,
    initial_configuration,
)
from pattern_prepare_multihead import (
    HALT as PREP_HALT,
    MACHINE as PREP_MACHINE,
    WP,
    WPRE,
    WSUF,
    initial_configuration as prep_initial_configuration,
    output_word as prep_output_word,
)

BLANK = "_"
PERIOD = "P"


class _Phase(Enum):
    PREPARE = auto()
    BUILD_PLAIN = auto()
    INIT_PLAIN = auto()
    MARK_PLAIN = auto()
    WALK_PLAIN = auto()
    BUILD_PREFIX = auto()
    INIT_PREFIX = auto()
    CHECK_PREFIX = auto()
    WALK_PREFIX = auto()
    BUILD_SUFFIX = auto()
    INIT_SUFFIX = auto()
    CHECK_SUFFIX = auto()
    WALK_SUFFIX = auto()
    FINISH = auto()
    DONE = auto()


@dataclass
class CheckpointCandidateYTapeJob:
    word: str
    c: int

    def __post_init__(self) -> None:
        if self.c <= 5:
            raise ValueError("the outer reversal proof requires c>5")
        if not self.word or any(ch not in "01" for ch in self.word):
            raise ValueError("word must be a nonempty binary string")
        self.n = len(self.word)
        self.patterns: tuple[str, str, str] | None = None
        self.prep_config = prep_initial_configuration(self.word)
        self.config: MultiheadConfiguration | None = None
        self.phase = _Phase.PREPARE

        # Candidate tape is indexed by d.  Position zero is a permanent left
        # marker; ordinary cells are blank or PERIOD.
        self.candidate_tape: dict[int, str] = {0: "#"}
        self.dp = 0
        self.df = 0
        self.ds = self.n
        self.helper = 0
        self.parity = 0
        self.min_full: int | None = None
        self.second_full: int | None = None
        self.min_partial: int | None = None
        self.second_partial: int | None = None
        self.gaps: tuple[int, ...] = ()
        self.least_gap: int | None = None
        self.candidate: int | None = None

        self.ticks = 0
        self.source_steps = 0
        self.candidate_moves = 0
        self.candidate_writes = 0
        self.border_events = 0

    @property
    def done(self) -> bool:
        return self.phase is _Phase.DONE

    def _start_pattern(self, index: int, build_phase: _Phase) -> None:
        assert self.patterns is not None
        self.config = initial_configuration(self.patterns[index])
        self.phase = build_phase

    def _step_source(self) -> tuple[int, int]:
        assert self.config is not None
        before = self.config.heads[A]
        MACHINE.step(self.config)
        after = self.config.heads[A]
        self.source_steps += 1
        return before, after

    def _build_complete(self) -> bool:
        assert self.config is not None
        return self.config.state == HALT

    def _walk_complete(self) -> bool:
        assert self.config is not None
        return self.config.state in (HALT, AFTER_BACK)

    def _plain_source_step(self) -> None:
        before, after = self._step_source()
        if after == before - 1:
            # p=n-border increases by one.  floor(p/2) advances exactly when
            # old p was odd.
            if self.parity == 1:
                self.dp += 1
                self.candidate_moves += 1
            self.parity ^= 1

    def _prefix_source_step(self) -> None:
        before, after = self._step_source()
        if after == before - 1:
            # floor(border/2) decreases exactly when old border was even.
            if self.parity == 0:
                self.df -= 1
                self.candidate_moves += 1
            self.parity ^= 1

    def _suffix_source_step(self) -> None:
        before, after = self._step_source()
        if after == before - 1:
            # n-floor(border/2) increases exactly when old border was even.
            if self.parity == 0:
                self.ds += 1
                self.candidate_moves += 1
            self.parity ^= 1

    def _mark_period(self) -> None:
        if self.parity == 0:
            self.candidate_tape[self.dp] = PERIOD
            self.candidate_writes += 1
        self.border_events += 1
        assert self.config is not None
        if self.config.heads[A] > 0:
            self.config.state = BACK_START
            self.phase = _Phase.WALK_PLAIN
        else:
            self._start_pattern(1, _Phase.BUILD_PREFIX)

    def _check_prefix(self) -> None:
        if self.parity == 0 and self.candidate_tape.get(self.df, BLANK) == PERIOD:
            # Border lengths decrease, so this monotonically improves the
            # minimum full-branch gap.
            if self.min_full != self.df:
                self.second_full = self.min_full
                self.min_full = self.df
        self.border_events += 1
        assert self.config is not None
        if self.config.heads[A] > 0:
            self.config.state = BACK_START
            self.phase = _Phase.WALK_PREFIX
        else:
            self._start_pattern(2, _Phase.BUILD_SUFFIX)

    def _check_suffix(self) -> None:
        if self.parity == 0:
            # Border lengths decrease, hence n-border/2 increases.  Retain the
            # first two distinct partial-branch gaps.
            if self.min_partial is None:
                self.min_partial = self.ds
            elif self.second_partial is None and self.ds != self.min_partial:
                self.second_partial = self.ds
        self.border_events += 1
        assert self.config is not None
        if self.config.heads[A] > 0:
            self.config.state = BACK_START
            self.phase = _Phase.WALK_SUFFIX
        else:
            # Empty suffix contributes gap n.
            if self.min_partial is None:
                self.min_partial = self.n
            elif self.second_partial is None and self.n != self.min_partial:
                self.second_partial = self.n
            self.phase = _Phase.FINISH

    def tick(self) -> bool:
        if self.done:
            raise RuntimeError("checkpoint job already complete")
        self.ticks += 1

        if self.phase is _Phase.PREPARE:
            if self.prep_config.state != PREP_HALT:
                PREP_MACHINE.step(self.prep_config)
                self.source_steps += 1
            else:
                self.patterns = (
                    prep_output_word(self.prep_config, 1, self.prep_config.heads[WP]),
                    prep_output_word(self.prep_config, 2, self.prep_config.heads[WPRE]),
                    prep_output_word(self.prep_config, 3, self.prep_config.heads[WSUF]),
                )
                self.prep_config = None
                self._start_pattern(0, _Phase.BUILD_PLAIN)

        elif self.phase is _Phase.BUILD_PLAIN:
            if not self._build_complete():
                self._step_source()
            else:
                assert self.config is not None
                self.helper = self.config.heads[A]
                self.dp = 0
                self.parity = 0
                self.phase = _Phase.INIT_PLAIN

        elif self.phase is _Phase.INIT_PLAIN:
            # Last pattern character is at absolute position n.
            if self.helper < self.n:
                self.helper += 1
                if self.parity == 1:
                    self.dp += 1
                    self.candidate_moves += 1
                self.parity ^= 1
            else:
                self.phase = _Phase.MARK_PLAIN

        elif self.phase is _Phase.MARK_PLAIN:
            self._mark_period()

        elif self.phase is _Phase.WALK_PLAIN:
            if not self._walk_complete():
                self._plain_source_step()
            else:
                self.phase = _Phase.MARK_PLAIN

        elif self.phase is _Phase.BUILD_PREFIX:
            if not self._build_complete():
                self._step_source()
            else:
                assert self.config is not None
                self.helper = 0
                self.df = 0
                self.parity = 0
                self.phase = _Phase.INIT_PREFIX

        elif self.phase is _Phase.INIT_PREFIX:
            assert self.config is not None
            border = self.config.heads[A]
            if self.helper < border:
                self.helper += 1
                self.parity ^= 1
                if self.parity == 0:
                    self.df += 1
                    self.candidate_moves += 1
            else:
                self.phase = _Phase.CHECK_PREFIX

        elif self.phase is _Phase.CHECK_PREFIX:
            self._check_prefix()

        elif self.phase is _Phase.WALK_PREFIX:
            if not self._walk_complete():
                self._prefix_source_step()
            else:
                self.phase = _Phase.CHECK_PREFIX

        elif self.phase is _Phase.BUILD_SUFFIX:
            if not self._build_complete():
                self._step_source()
            else:
                assert self.config is not None
                self.helper = 0
                self.ds = self.n
                self.parity = 0
                self.phase = _Phase.INIT_SUFFIX

        elif self.phase is _Phase.INIT_SUFFIX:
            assert self.config is not None
            border = self.config.heads[A]
            if self.helper < border:
                self.helper += 1
                self.parity ^= 1
                if self.parity == 0:
                    self.ds -= 1
                    self.candidate_moves += 1
            else:
                self.phase = _Phase.CHECK_SUFFIX

        elif self.phase is _Phase.CHECK_SUFFIX:
            self._check_suffix()

        elif self.phase is _Phase.WALK_SUFFIX:
            if not self._walk_complete():
                self._suffix_source_step()
            else:
                self.phase = _Phase.CHECK_SUFFIX

        elif self.phase is _Phase.FINISH:
            choices = sorted(
                {
                    d
                    for d in (
                        self.min_full,
                        self.second_full,
                        self.min_partial,
                        self.second_partial,
                    )
                    if d is not None
                }
            )
            self.gaps = tuple(choices[:2])
            self.least_gap = self.gaps[0]
            base = (self.c - 1) * self.least_gap
            target = self.c * self.least_gap
            if base <= self.n < target:
                self.candidate = self.least_gap
            self.phase = _Phase.DONE

        else:  # pragma: no cover
            raise AssertionError(self.phase)
        return self.done

    def run(self, *, max_ticks: int = 10_000_000) -> int | None:
        while not self.done:
            if self.ticks >= max_ticks:
                raise TimeoutError((self.phase, self.n, self.ticks))
            self.tick()
        return self.candidate
