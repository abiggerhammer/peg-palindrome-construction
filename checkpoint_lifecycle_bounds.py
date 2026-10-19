"""Explicit compositional bounds for the reusable SG checkpoint lifecycle.

The bounds in this module are proof certificates, not fitted measurements.
They deliberately over-approximate the generated ordinary-TM programs.

Notation
--------
``n`` is the nonempty frozen source length and ``E`` is the number of local
checkpoint transitions from ``checkpoint_ordinary_tm.INITIAL`` to
``checkpoint_ordinary_tm.DONE``.

The proof has three layers.

1. The one-shot body performs at most ``10*n + 4`` Algorithm-Y source steps.
   There are three patterns of lengths ``n, 2*n+1, 2*n+1``.  For a pattern of
   length ``m``, table construction advances the stage head at most ``m``
   times, and the subsequent failure-chain walk moves its border head strictly
   left at most ``m`` times.  The exact generated ordinary microprogram bound
   is 103 transitions per source step.  All non-Y preparation, rewind,
   marking, parity, and final ratio/merge control is bounded by ``100*n+200``.

2. Producer-paid retirement is counted directly from
   ``checkpoint_reusable_tm.reset_rows``.  It costs at most

       24*E + 40*n + 225

   local checkpoint transitions, including the RESULT_READY -> cleanup
   transition.  The coefficient 24 consists of six first axis rewinds, nine
   pattern rewinds, and nine fresh source-work epochs; all other traversals
   are charged explicitly to n.  See ``retirement_ledger`` below.

3. The registered fabric simulates each local transition in two global
   transitions and adds the finite call/load/return overhead.  A complete
   source-machine checkpoint call followed by retirement is therefore bounded
   by ``56580*n + 31054`` global transitions, excluding caller-side source
   construction and result consumption.

These constants are intentionally loose.  Their purpose is to restore a valid
quantitative theorem after the old undocumented 2048-per-symbol lifecycle
claim was retracted.
"""

from __future__ import annotations

from dataclasses import dataclass

ALGORITHM_Y_MICROSTEPS_PER_SOURCE_STEP = 103

# Three patterns have total length 5n+2.  Build plus failure walk is at most
# twice that total length.
def algorithm_y_source_steps_bound(n: int) -> int:
    _check_n(n)
    return 10 * n + 4


def one_shot_control_bound(n: int) -> int:
    """Bound all checkpoint transitions outside wrapped Algorithm Y.

    The detailed tag-by-tag ledger is below 70n+100; 100n+200 leaves a clear
    margin for singleton and terminal branches without relying on cancellation.
    """
    _check_n(n)
    return 100 * n + 200


def one_shot_bound(n: int) -> int:
    """Local transitions from one-shot INITIAL through RESULT_READY."""
    _check_n(n)
    return (
        ALGORITHM_Y_MICROSTEPS_PER_SOURCE_STEP
        * algorithm_y_source_steps_bound(n)
        + one_shot_control_bound(n)
    )


@dataclass(frozen=True)
class RetirementLedger:
    e_coefficient: int
    n_coefficient: int
    constant: int
    explanation: tuple[str, ...]


RETIREMENT_LEDGER = RetirementLedger(
    e_coefficient=24,
    n_coefficient=40,
    constant=225,
    explanation=(
        "RETIRE dispatch: 1",
        "six first axis rewinds and terminal tests: <= 6E+6",
        "simultaneous axis clear plus six final rewinds: <= 7n+19",
        "nine pattern rewind/clear/rewind cycles (total prepared length 15n+6): <= 9E+30n+75",
        "two forward sources to END and reverse source to SENTINEL: <= 3n+6",
        "nine Algorithm-Y S/T/U fresh epochs and 36 stack/counter epochs: <= 9E+123",
    ),
)


def retirement_bound(n: int, one_shot_steps: int) -> int:
    """Local transitions from RESULT_READY through clean READY.

    ``one_shot_steps`` is the actual E for the request being retired.  The
    bound charges every variable cleanup traversal to that producer.
    """
    _check_n(n)
    if one_shot_steps < 0:
        raise ValueError(one_shot_steps)
    l = RETIREMENT_LEDGER
    return l.e_coefficient * one_shot_steps + l.n_coefficient * n + l.constant


def local_lifecycle_bound(n: int) -> int:
    """Clean READY -> result -> clean READY, in local checkpoint transitions.

    Includes the one REQUEST transition and the producer-paid RETIRE path.
    """
    e = one_shot_bound(n)
    return 1 + e + retirement_bound(n, e)


def registered_execute_and_retire_bound(n: int) -> int:
    """Two registered calls: execute to result, then retire to clean READY.

    A registered call with m local transitions costs exactly 2m+3 globally.
    The retirement call bypasses the local RETIRE dispatch row, so using the
    full local retirement bound is a safe two-transition overestimate.
    """
    e = one_shot_bound(n)
    r = retirement_bound(n, e)
    return 2 * e + 3 + 2 * (r - 1) + 3


# Caller-side source construction used by the full RECOVER path.  This follows
# the literal `_emit_fresh_checkpoint_sources` / `_emit_copy_active_suffix`
# program and uses the graph-theoretic history command maxima RIGHT=55 and
# LEFT=9.  Registered costs are 113 and 21 respectively; unary FRESH/INC/DEC
# costs are 7/7/5.  The exact symbolic sum is <=161n-107 for n>=1; retain a
# positive margin for branch endpoints.
def recover_source_construction_bound(n: int) -> int:
    _check_n(n)
    return 161 * n + 20


# Result consumption in RECOVER: OUT2 scan <=369n+364, OUT1 scan <=709n+13,
# and K recomputation <=145n+23.
def recover_result_consumption_bound(n: int) -> int:
    _check_n(n)
    return 1223 * n + 400


def recover_checkpoint_lifecycle_bound(n: int) -> int:
    """Source construction + checkpoint + output consumption + retirement.

    This covers `_emit_recover(..., align=False)` through K recomputation.  It
    excludes any case-specific pre-alignment of old B/B' cursors.
    """
    return (
        recover_source_construction_bound(n)
        + registered_execute_and_retire_bound(n)
        + recover_result_consumption_bound(n)
    )


def _check_n(n: int) -> None:
    if not isinstance(n, int) or n <= 0:
        raise ValueError(n)


if __name__ == "__main__":
    for n in (1, 16, 64):
        print(n, {
            "one_shot": one_shot_bound(n),
            "retire_after_bound": retirement_bound(n, one_shot_bound(n)),
            "local_lifecycle": local_lifecycle_bound(n),
            "registered_execute_retire": registered_execute_and_retire_bound(n),
            "recover_lifecycle": recover_checkpoint_lifecycle_bound(n),
        })
