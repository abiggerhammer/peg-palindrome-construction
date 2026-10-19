"""Proof certificates for SG case-5 background and case-6 recovery bounds.

The constants here are deliberately conservative and are tied to the current
ordinary source programs.  They distinguish three different quantities:

* a *logical background unit* is one pass from ``C5_WORK`` to the common
  ``C5_WORK_DEC`` continuation;
* a primitive global transition is one ordinary one-head-per-tape TM step;
* a retained checkpoint cycle is the complete logical schedule from launch
  preparation through producer-paid cleanup and candidate catch-up/return.

Semantic correctness of the checkpoint result is a separate theorem.  The
bounds below prove that, conditional on that result, the generated worker has
enough time to consume it before the SG closeness invariant can fail.
"""

from __future__ import annotations

from dataclasses import dataclass

from checkpoint_lifecycle_bounds import (
    local_lifecycle_bound,
    recover_checkpoint_lifecycle_bound,
    registered_execute_and_retire_bound,
)
from construction_constants import (
    BACKGROUND_CYCLE_CONSTANT,
    BACKGROUND_CYCLE_LINEAR,
    SG_RATIO_C,
    background_clock_shape,
    background_steps_per_input,
    checkpoint_window_epsilon,
    checkpoint_window_symbols as exact_checkpoint_window_symbols,
)

# Exact registered command maxima derived from the acyclic service graphs.
HISTORY_APPEND = 101  # 2*49+3
HISTORY_LEFT = 21     # 2*9+3
HISTORY_RIGHT = 113   # 2*55+3
COUNTER_FRESH = 7     # 2*2+3
COUNTER_INC = 7       # 2*2+3
COUNTER_DEC = 5       # 2*1+3

# A relation-aware midpoint/left move is either one finite update or a
# has-right branch followed by a registered RIGHT command.
MID_OR_LEFT_RIGHT = 1 + HISTORY_RIGHT
MID_OR_LEFT_LEFT = HISTORY_LEFT


@dataclass(frozen=True)
class BackgroundUnitLedger:
    route: str
    primitive_transitions_to_work_dec: int
    explanation: str


BACKGROUND_UNIT_LEDGER = (
    BackgroundUnitLedger(
        "copy_append",
        1 + 1 + 3 * HISTORY_APPEND + 1,
        "dispatch, choose bit, append CURRENT/LAG/COPY, clear COPY_NEEDED",
    ),
    BackgroundUnitLedger(
        "copy_advance",
        1 + 1 + MID_OR_LEFT_RIGHT + COUNTER_INC + 1,
        "dispatch, has-right, BG right, BG_RETURN increment, mode update",
    ),
    BackgroundUnitLedger(
        "return_stale_second",
        1 + 3 * MID_OR_LEFT_LEFT + COUNTER_DEC,
        "dispatch, BP left, two LBP left moves, GAP decrement",
    ),
    BackgroundUnitLedger(
        "return_background",
        1 + MID_OR_LEFT_LEFT + COUNTER_DEC,
        "dispatch, BG left, BG_RETURN decrement",
    ),
    BackgroundUnitLedger(
        "launch_or_sync_history",
        1 + 1 + HISTORY_RIGHT,
        "phase dispatch, has-right branch, one history RIGHT",
    ),
    BackgroundUnitLedger(
        "result_counter_operation",
        1 + 1 + COUNTER_INC,
        "phase dispatch, finite axis move, unary increment",
    ),
    BackgroundUnitLedger(
        "candidate_build_preposition",
        (
            1                       # C5_WORK -> BUILD
            + 1                     # consume one candidate unit
            + 16 * COUNTER_INC      # construct 16d target
            + 2 * HISTORY_LEFT      # place L33 lag by 2
            + 1                     # enter BP-right helper
            + 3 * MID_OR_LEFT_RIGHT # BP and two LBP right moves
            + COUNTER_INC           # GAP records positioned distance
        ),
        "one d-unit: target, lag, retained B'/LEFT' preposition, GAP increment",
    ),
    BackgroundUnitLedger(
        "candidate_return",
        1 + 1 + 3 * MID_OR_LEFT_LEFT + COUNTER_DEC,
        "phase dispatch, BP/two LBP left moves, GAP decrement",
    ),
    BackgroundUnitLedger(
        "catch_up_compare",
        1 + 1 + HISTORY_RIGHT + 1 + HISTORY_RIGHT + 1 + COUNTER_DEC + 1,
        "dispatch, current/lag moves, compare, TARGET decrement, phase update",
    ),
)

BACKGROUND_UNIT_BODY_BOUND = max(
    item.primitive_transitions_to_work_dec for item in BACKGROUND_UNIT_LEDGER
)

# At a finite-radix boundary the common continuation performs one registered
# CLOCK decrement and one branch back to WORK/OUT_CHECK.  Non-boundary units
# cost only the direct finite-radix update, so this is the uniform maximum.
BACKGROUND_UNIT_CLOCK_OVERHEAD = COUNTER_DEC + 1
BACKGROUND_UNIT_GLOBAL_BOUND = (
    BACKGROUND_UNIT_BODY_BOUND + BACKGROUND_UNIT_CLOCK_OVERHEAD
)


@dataclass(frozen=True)
class BackgroundCycleOutsideLedger:
    name: str
    n_coefficient: int
    constant: int
    explanation: str


# These are logical C5_WORK-to-C5_WORK_DEC units, not primitive transitions.
# Each traversal is monotone within one frozen source epoch.  Candidate d
# satisfies (c-1)d <= n < cd, but the ledger deliberately uses only d<=n.
BACKGROUND_CYCLE_OUTSIDE_LEDGER = (
    BackgroundCycleOutsideLedger(
        "launch_preparation", 9, 15,
        "three source-to-END scans, delta copy, CURRENT/LAG sync, two forward rewinds, reverse positioning, request",
    ),
    BackgroundCycleOutsideLedger(
        "result_decode", 4, 5,
        "candidate-axis rewind, source rewind, lockstep marker decode and unary candidate construction",
    ),
    BackgroundCycleOutsideLedger(
        "candidate_and_catchup", 7, 12,
        "candidate build/restore, target source scan, catch-up/follow work available at the live prefix, and failed-candidate return",
    ),
)
BACKGROUND_CYCLE_OUTSIDE_LINEAR = sum(x.n_coefficient for x in BACKGROUND_CYCLE_OUTSIDE_LEDGER)
BACKGROUND_CYCLE_OUTSIDE_CONSTANT = sum(x.constant for x in BACKGROUND_CYCLE_OUTSIDE_LEDGER)

# Input append/follow is outside the clock.  This upper bound covers either a
# normal append followed by the clock or a FOLLOW comparison and constant-time
# installation at the target.
CASE5_UNCLOCKED_PREFIX_BOUND = 560


def factored_clock_build_bound(c: int = SG_RATIO_C) -> int:
    """Primitive cost to build the production outer clock factor."""
    outer, _radix, _effective = background_clock_shape(c)
    return COUNTER_FRESH + outer * COUNTER_INC + 1


def case5_primitive_per_input_bound(c: int = SG_RATIO_C) -> int:
    """Uniform primitive-transition bound for one case-5 input symbol."""
    _outer, _radix, effective = background_clock_shape(c)
    clocked = (
        CASE5_UNCLOCKED_PREFIX_BOUND
        + factored_clock_build_bound(c)
        + effective * BACKGROUND_UNIT_GLOBAL_BOUND
    )
    return max(CASE5_UNCLOCKED_PREFIX_BOUND, clocked)


def background_cycle_bound(n: int) -> int:
    """Logical units for one retained checkpoint/catch-up cycle.

    Ledger outside the reusable lifecycle, for frozen length n:

    * launch source/head preparation: <= 9n+15;
    * result-axis decoding: <= 4n+5;
    * candidate build/restore, target scan, catch-up and failed return:
      <= 7n+12.

    Thus the non-checkpoint total is at most ``20n+32``.  Combining it
    with ``local_lifecycle_bound(n)=28290n+15526`` is below the retained
    public bound ``28400n+16000``.  Work that is waiting for a future input
    symbol in FOLLOW is not charged before that symbol exists; reaching
    FOLLOW is therefore earlier than this complete available-work bound.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError(n)
    return BACKGROUND_CYCLE_LINEAR * n + BACKGROUND_CYCLE_CONSTANT


def checkpoint_window_symbols(n: int, c: int = SG_RATIO_C) -> int:
    if not isinstance(n, int) or n <= 0:
        raise ValueError(n)
    return exact_checkpoint_window_symbols(n, c)


def background_window_capacity(n: int, c: int = SG_RATIO_C) -> int:
    """Logical units supplied during the Lemma-3.3 checkpoint window."""
    return background_clock_shape(c)[2] * checkpoint_window_symbols(n, c)


def background_catchup_inequality(n: int, c: int = SG_RATIO_C) -> bool:
    """Mechanical statement used by the BackgroundCatchUp proof."""
    return background_window_capacity(n, c) >= background_cycle_bound(n)


def lazy_setup_logical_bound(active_length: int) -> int:
    """COPY/RETURN setup after dropping B', before the first launch.

    At most two units per active symbol copy the frozen history, at most one
    unit per symbol returns stale B', at most one returns BG, and eight finite
    endpoint/alignment units cover all boundaries.
    """
    if not isinstance(active_length, int) or active_length <= 0:
        raise ValueError(active_length)
    return 4 * active_length + 8


def initial_setup_input_bound(active_length: int, c: int = SG_RATIO_C) -> int:
    """Input symbols sufficient to finish the lazy COPY/RETURN bootstrap."""
    if not isinstance(active_length, int) or active_length <= 0:
        raise ValueError(active_length)
    units = background_clock_shape(c)[2]
    return (lazy_setup_logical_bound(active_length) + units - 1) // units


def first_checkpoint_deadline_inputs(active_length: int, c: int = SG_RATIO_C) -> int:
    """Bootstrap plus first frozen-job catch-up delay, in input symbols.

    During bootstrap B is fixed.  If it takes ``s`` inputs, the frozen source
    length is at most ``active_length+s``.  The retained job then catches the
    live input within its exact checkpoint window.
    """
    setup = initial_setup_input_bound(active_length, c)
    frozen = active_length + setup
    return setup + checkpoint_window_symbols(frozen, c)


def first_checkpoint_beats_case5_runway(active_length: int, c: int = SG_RATIO_C) -> bool:
    """Exact integer form of the initial case-5 deadline inequality.

    The SG paper's case-5 argument gives more than ``(c-5)A/5`` input symbols
    before the closeness invariant could fail.  This predicate verifies that
    the implementation has completed bootstrap and caught its first frozen
    job up strictly inside that runway.
    """
    delay = first_checkpoint_deadline_inputs(active_length, c)
    return 5 * delay <= (c - 5) * active_length


def case5_runway_numerator(c: int = SG_RATIO_C) -> tuple[int, int]:
    """Return the paper's runway coefficient ``(c-5)/5`` as a fraction."""
    if c <= 5:
        raise ValueError(c)
    return c - 5, 5


def case6_two_job_bound(jump: int, c: int = SG_RATIO_C) -> int:
    """Primitive bound for case 6, including outstanding and fresh jobs.

    Let j=B(ua)-B(u).  Since the second midpoint was unknown,

        RIGHT(u)-B(u) < c*j,

    hence the fresh RECOVER source length n is at most c*j.  An initial
    stale GAP is below j.  A prepositioned checkpoint candidate has gap
    d <= m/(c-1) for frozen length m <= n, hence d < 2j when c=16; the
    uniform stale-head return charge is therefore two jump lengths.
    BG_RETURN is at most n.  An outstanding checkpoint is no more expensive
    than a complete registered lifecycle on n, and the fresh job is bounded
    by the full RECOVER lifecycle on n.
    """
    if not isinstance(jump, int) or jump <= 0:
        raise ValueError(jump)
    n = c * jump
    return (
        138 * jump                    # stale BP/LBP return; candidate gap < 2j
        + 27 * n                      # BG return
        + 10                          # finite dispatch/relation copies
        + registered_execute_and_retire_bound(n)
        + recover_checkpoint_lifecycle_bound(n)
    )


def case6_predictability_coefficient(c: int = SG_RATIO_C) -> int:
    """Linear coefficient C with ``case6_two_job_bound(j)<=C*j``."""
    # The bound is affine in j and j>=1, so its value at one absorbs the fixed
    # term for every larger jump.
    return case6_two_job_bound(1, c)


def _proof_sanity() -> None:
    # The retained public cycle bound dominates the detailed ledger.
    for n in (1, 2, 16, 1000):
        detailed = (
            local_lifecycle_bound(n)
            + BACKGROUND_CYCLE_OUTSIDE_LINEAR * n
            + BACKGROUND_CYCLE_OUTSIDE_CONSTANT
        )
        assert detailed <= background_cycle_bound(n)
        assert background_catchup_inequality(n)
    assert BACKGROUND_CYCLE_OUTSIDE_LINEAR == 20
    assert BACKGROUND_CYCLE_OUTSIDE_CONSTANT == 32
    assert BACKGROUND_UNIT_BODY_BOUND == 506
    assert BACKGROUND_UNIT_GLOBAL_BOUND == 512


_proof_sanity()


if __name__ == "__main__":
    print({
        "unit_body": BACKGROUND_UNIT_BODY_BOUND,
        "unit_global": BACKGROUND_UNIT_GLOBAL_BOUND,
        "clock_shape": background_clock_shape(),
        "case5_per_input": case5_primitive_per_input_bound(),
        "case6_coefficient": case6_predictability_coefficient(),
    })
