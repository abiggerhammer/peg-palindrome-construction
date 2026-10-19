"""Explicit conservative constants for the generated construction.

The constants are intentionally generous.  They turn the asymptotic bounds in
the paper into concrete finite controller sizes; minimizing them is an
engineering task, not a correctness requirement.
"""

from __future__ import annotations

from math import isqrt, sqrt

SG_RATIO_C = 16

# Conservative allowance for the *one-shot local checkpoint body* per frozen
# input symbol.  The proved affine bound is 1130*n+612, hence <=2048*n for
# every n>=1.  This does NOT include source construction, output scans,
# registered-call overhead, or producer-paid retirement.
CHECKPOINT_STEPS_PER_SYMBOL = 2048

# Proved logical-work bound for one complete retained Lemma-3.3 checkpoint
# cycle (launch preparation, reusable checkpoint execution and producer-paid
# retirement, result decoding, candidate preparation, catch-up, and a failed
# candidate return).  See background_bounds.py.
BACKGROUND_CYCLE_LINEAR = 28_400
BACKGROUND_CYCLE_CONSTANT = 16_000


def checkpoint_window_epsilon(c: int = SG_RATIO_C) -> float:
    if c <= 5:
        raise ValueError(c)
    return 0.5 * (sqrt(c / (c - 1)) - 1.0)


def checkpoint_window_symbols(n: int, c: int = SG_RATIO_C) -> int:
    """Exact ``max(1, floor(epsilon*n))`` without floating arithmetic.

    With ``epsilon=(sqrt(c/(c-1))-1)/2``, let
    ``q=floor(n*sqrt(c/(c-1)))``.  Since ``n`` is integral,

        floor(epsilon*n) = floor((q-n)/2).

    The rational square-root floor is obtained exactly from integer
    arithmetic.  This function is the quantitative definition used by the
    proof certificates; ``checkpoint_window_epsilon`` is retained only for
    human-readable diagnostics.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError(n)
    if c <= 5:
        raise ValueError(c)
    q = isqrt((n * n * c) // (c - 1))
    return max(1, (q - n) // 2)


def _ceil_sqrt(value: int) -> int:
    if value < 0:
        raise ValueError(value)
    root = isqrt(value)
    return root if root * root == value else root + 1


def background_steps_per_input(c: int = SG_RATIO_C) -> int:
    """Exact proved logical background-unit budget per case-5 input.

    For ``h=max(1,floor(epsilon*n))`` one has ``n < 2h/epsilon``.
    Therefore it suffices to choose

        W >= 2*BACKGROUND_CYCLE_LINEAR/epsilon
             + BACKGROUND_CYCLE_CONSTANT.

    Rationalizing ``1/epsilon`` gives the exact quadratic-irrational form

        2L/epsilon = 4L*(sqrt(c(c-1)) + c - 1).

    The ceiling below is computed with integer square roots, not floating
    arithmetic.
    """
    if c <= 5:
        raise ValueError(c)
    linear = BACKGROUND_CYCLE_LINEAR
    scaled = 4 * linear
    irrational_ceiling = _ceil_sqrt(scaled * scaled * c * (c - 1))
    return (
        scaled * (c - 1)
        + irrational_ceiling
        + BACKGROUND_CYCLE_CONSTANT
    )


def background_clock_shape(c: int = SG_RATIO_C) -> tuple[int, int, int]:
    """Return ``(outer, radix, effective_units)`` for the factored clock.

    ``outer`` is represented by the ordinary unary CLOCK component.  The
    fixed ``radix`` is represented by one finite-control tape symbol.  Their
    product is the actual number of logical background units supplied and is
    the least near-square product obtained by this construction that is at
    least the proved budget.
    """
    required = background_steps_per_input(c)
    radix = isqrt(required)
    if radix * radix < required:
        radix += 1
    outer = (required + radix - 1) // radix
    return outer, radix, outer * radix


def scheduler_predictability_constant(c: int = SG_RATIO_C) -> int:
    """Certified Galil predictability constant for the corrected source machine.

    The proof is specific to the ``r=s=0`` construction with ``c=16``.  The
    import is deliberately local because ``scheduler_parameters`` also imports
    the background-bound module, which depends on this constants module.
    """
    if c != SG_RATIO_C:
        raise ValueError(
            f"scheduler constant is proved only for source ratio c={SG_RATIO_C}, got {c}"
        )
    from scheduler_parameters import GALIL_PREDICTABILITY_C

    return GALIL_PREDICTABILITY_C
