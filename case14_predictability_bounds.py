"""Primitive predictability certificates for SG cases 1--4.

The bounds in this module start when an input bit enters the literal ordinary
source dispatcher and end at ``SOURCE_DONE_0`` or ``SOURCE_DONE_1``.  They are
therefore directly comparable with the already-proved case-5 and case-6
primitive bounds.

Notation
--------
For an old prefix ``u`` and next bit ``a`` let

``A = RIGHT(u) - B(u)``
    old active-suffix length;
``d = B'(u) - B(u)``
    old second-candidate gap, when known;
``j = B(ua) - B(u)``
    progress of the first midpoint.

For the even-palindrome completion language, the exact availability increment
is ``avail(u,a) = 2*j - 1``.

The constants are deliberately conservative and are obtained by composing the
proved component maxima with the literal case programs.  They are not fitted
to execution traces.
"""

from __future__ import annotations

from dataclasses import dataclass

from checkpoint_lifecycle_bounds import (
    recover_checkpoint_lifecycle_bound,
    recover_source_construction_bound,
    registered_execute_and_retire_bound,
)

# Registered component maxima, already proved in the lifecycle/background
# ledgers.
HISTORY_APPEND = 101
HISTORY_LEFT = 21
HISTORY_RIGHT = 113
COUNTER_FRESH = 7
COUNTER_INC = 7
COUNTER_DEC = 5
SIGNED_UNIT = 8  # worst branch of signed_inc / signed_dec
RELATION_RIGHT = 1 + HISTORY_RIGHT

# ---------------------------------------------------------------------------
# Common finite wrapper.

# READ/CAPTURE; six APPEND calls; six relation-aware cursor advances; signed-k
# decrement and final 16-way dispatch.
DISPATCHER_BOUND = 2 + 6 * HISTORY_APPEND + 6 * HISTORY_RIGHT + 10

# OUT_CHECK worst path: LB LEFT, inspect, LB RIGHT, final source transition.
OUTPUT_BOUND = HISTORY_LEFT + 1 + HISTORY_RIGHT + 1


# ---------------------------------------------------------------------------
# Reusable helper bounds.


def align_second_bound(distance: int) -> int:
    """Return stale B'/LEFT' by ``distance`` and freshen K.

    Per unit: loop branch, BP LEFT, two LBP LEFTs, GAP DEC.  The affine
    constant includes entry, bottom branch, and K FRESH_ZERO.
    """
    _positive_or_zero(distance)
    return 69 * distance + 9


def promote_second_bound(distance: int) -> int:
    """Promote old B' to B while recording RADIUS=distance.

    One unit advances B, BG, two LB cells, and two BGL cells, then decrements
    GAP and increments RADIUS.
    """
    _positive(distance)
    return 698 * distance + 9


def signed_adjust_bound(length: int, factor: int) -> int:
    """Bound ``_emit_signed_adjust_by_counter``.

    Each source unit costs one destructive-read transition, ``factor`` signed
    operations of at most eight transitions each, and two restoration
    transitions.  Five finite transitions cover entry and endpoints.
    """
    _positive_or_zero(length)
    if not isinstance(factor, int) or factor <= 0:
        raise ValueError(factor)
    return (3 + 8 * factor) * length + 5


def update_k_after_promotion_bound(radius: int, gap: int) -> int:
    _positive(radius)
    _positive(gap)
    return signed_adjust_bound(radius, 15) + signed_adjust_bound(gap, 16)


def counter_multiple_bound(length: int, factor: int) -> int:
    """Fresh target, add ``factor`` per source unit, restore source."""
    _positive(length)
    if not isinstance(factor, int) or factor <= 0:
        raise ValueError(factor)
    return (3 + factor * COUNTER_INC) * length + 11


def quota_source_construction_bound(length: int) -> int:
    """Fresh checkpoint source and copy exactly ``length`` active symbols.

    This is the ordinary quota-copy program used by small-gap case 3.  The
    retained ``170*n+50`` bound includes forward copy, quota decrement,
    reverse copy while restoring B, and all three source rewinds.
    """
    _positive(length)
    return 170 * length + 50


def scan_next_out1_bound(source_length: int, limit: int) -> int:
    """Scan at most ``limit`` output coordinates of a source of given length.

    The limit counter copy costs ``10*limit+11``.  Each inspected coordinate
    costs at most 358 transitions while advancing BP/LEFT' and GAP.  The axis
    rewind is at most ``source_length+2``.
    """
    _positive(source_length)
    _positive(limit)
    if limit > source_length:
        raise ValueError((source_length, limit))
    return 368 * limit + source_length + 14


# ---------------------------------------------------------------------------
# Case bounds from input read through source completion.

CASE1_BOUND = DISPATCHER_BOUND + 1 + OUTPUT_BOUND
CASE4_BOUND = (
    DISPATCHER_BOUND
    + 1                    # case entry -> C4_FRESH_K
    + 2 * COUNTER_FRESH    # K_MAG and BG_RETURN
    + 3 * 7                # constant-time history RESET calls
    + OUTPUT_BOUND
)


def case2_affine_bound(jump: int) -> int:
    """Complete case-2 bound in primitive transitions.

    The SG/Fine--Wilf geometry gives ``d<j`` and
    ``A<4j``.  The copied source has length ``n=A+1<=4j``.
    """
    _positive(jump)
    return 231_925 * jump + 32_916


def case2_linear_coefficient() -> int:
    """C with ``case2_need(j)<=C*j`` for every integer ``j>=1``."""
    return case2_affine_bound(1)


@dataclass(frozen=True)
class Case3Bounds:
    at_end_affine: int
    large_affine: int
    small_affine: int


def case3_at_end_bound(jump: int) -> int:
    """Promotion followed by installation of the automatic unit gap."""
    _positive(jump)
    return 821 * jump + 1_934


def case3_large_bound(jump: int) -> int:
    """Large-gap full-checkpoint branch.

    Here ``j=d`` and the post-promotion source length satisfies ``n<=15j``.
    The detailed pre-substitution ledger is

        dispatcher + promotion + branch
        + source( n ) + execute/retire( n )
        + OUT1-next scan( n,n )
        + K update( radius=j, gap<=n ) + output.
    """
    _positive(jump)
    n = 15 * jump
    detailed = (
        DISPATCHER_BOUND
        + promote_second_bound(jump)
        + 1
        + recover_source_construction_bound(n)
        + registered_execute_and_retire_bound(n)
        + scan_next_out1_bound(n, n)
        + update_k_after_promotion_bound(jump, n)
        + 1 + OUTPUT_BOUND
    )
    # Kept as a stable public affine certificate.
    public = 859_436 * jump + 32_541
    assert detailed <= public, (jump, detailed, public)
    return public


def case3_small_bound(jump: int) -> int:
    """Small-gap 4j-window branch, including either terminal path.

    The semantic window lemma supplies exactly ``q=4j`` frozen symbols.  The
    found branch dominates the missing-and-forget branch.
    """
    _positive(jump)
    q = 4 * jump
    found = (
        DISPATCHER_BOUND
        + promote_second_bound(jump)
        + 1
        + counter_multiple_bound(jump, 4)
        + quota_source_construction_bound(q)
        + registered_execute_and_retire_bound(q)
        + scan_next_out1_bound(q, jump)
        + update_k_after_promotion_bound(jump, jump)
        + 1 + OUTPUT_BOUND
    )
    missing = (
        DISPATCHER_BOUND
        + promote_second_bound(jump)
        + 1
        + counter_multiple_bound(jump, 4)
        + quota_source_construction_bound(q)
        + registered_execute_and_retire_bound(q)
        + scan_next_out1_bound(q, jump)
        + align_second_bound(jump)
        + 1                    # enter shared case-4 freshening tail
        + 2 * COUNTER_FRESH
        + 3 * 7
        + OUTPUT_BOUND
    )
    public = 228_355 * jump + 32_582
    assert found <= public, (jump, found, public)
    assert missing <= public, (jump, missing, public)
    return public


def case3_bounds(jump: int) -> Case3Bounds:
    return Case3Bounds(
        case3_at_end_bound(jump),
        case3_large_bound(jump),
        case3_small_bound(jump),
    )


def case3_linear_coefficient() -> int:
    """Uniform C with ``case3_need(j)<=C*j`` for all three subcases."""
    return max(
        case3_at_end_bound(1),
        case3_large_bound(1),
        case3_small_bound(1),
    )


# ---------------------------------------------------------------------------
# Availability conversion.


def availability_from_jump(jump: int) -> int:
    """Exact ``avail(u,a)`` for the even-palindrome completion language."""
    _positive_or_zero(jump)
    return 2 * jump - 1


def jump_from_availability(availability: int) -> int:
    if not isinstance(availability, int) or availability < -1 or availability % 2 == 0:
        raise ValueError(availability)
    return (availability + 1) // 2


def _positive(value: int) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(value)


def _positive_or_zero(value: int) -> None:
    if not isinstance(value, int) or value < 0:
        raise ValueError(value)


def _sanity() -> None:
    assert DISPATCHER_BOUND == 1296
    assert OUTPUT_BOUND == 136
    assert CASE1_BOUND == 1433
    assert CASE4_BOUND == 1468
    assert case2_affine_bound(1) == 264_841
    assert case2_linear_coefficient() == 264_841
    assert case3_at_end_bound(1) == 2_755
    assert case3_large_bound(1) == 891_977
    assert case3_small_bound(1) == 260_937
    assert case3_linear_coefficient() == 891_977


_sanity()


if __name__ == "__main__":
    print({
        "dispatcher": DISPATCHER_BOUND,
        "output": OUTPUT_BOUND,
        "case1": CASE1_BOUND,
        "case2_coefficient": case2_linear_coefficient(),
        "case3_coefficient": case3_linear_coefficient(),
        "case4": CASE4_BOUND,
    })
