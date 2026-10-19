"""Certified source-predictability and Galil scheduler parameters.

This module translates the proved six-case primitive bounds for the corrected
Seiferas--Galil source machine into the two-part predictability condition used
by Galil's fast/slow real-time scheduler.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from background_bounds import (
    case5_primitive_per_input_bound,
    case6_predictability_coefficient,
)
from case14_predictability_bounds import (
    CASE1_BOUND,
    CASE4_BOUND,
    case2_linear_coefficient,
    case3_linear_coefficient,
)
from construction_constants import SG_RATIO_C

# Explicit affine theorem proved by combining all six SG cases.
SOURCE_AFFINE_C = 947_906
SOURCE_AFFINE_D = 1_782_767_609

# Case bounds in the common primitive accounting model.
CASE1_PRIMITIVE_BOUND = CASE1_BOUND
CASE2_J_COEFFICIENT = case2_linear_coefficient()
CASE3_J_COEFFICIENT = case3_linear_coefficient()
CASE4_PRIMITIVE_BOUND = CASE4_BOUND
CASE5_PRIMITIVE_BOUND = case5_primitive_per_input_bound()
CASE6_J_COEFFICIENT = case6_predictability_coefficient()

# The smallest Galil constant certified directly by the current case bounds.
# Cases 1, 4, and 5 have availability -1 and therefore need c at least their
# primitive bound.  Cases 2, 3, and 6 have availability 2j-1 and are covered
# when 2c dominates their j-coefficient.  Case 5 is the maximum.
GALIL_PREDICTABILITY_C = max(
    CASE1_PRIMITIVE_BOUND,
    CASE4_PRIMITIVE_BOUND,
    CASE5_PRIMITIVE_BOUND,
    (CASE2_J_COEFFICIENT + 1) // 2,
    (CASE3_J_COEFFICIENT + 1) // 2,
    (CASE6_J_COEFFICIENT + 1) // 2,
)
GALIL_SCHEDULER_PERIOD = 2 * GALIL_PREDICTABILITY_C


@dataclass(frozen=True)
class SchedulerParameterCertificate:
    source_ratio_c: int
    source_affine_C: int
    source_affine_D: int
    galil_predictability_c: int
    scheduler_source_step_period: int
    countdown_width_bits: int
    case1_bound: int
    case2_j_coefficient: int
    case3_j_coefficient: int
    case4_bound: int
    case5_bound: int
    case6_j_coefficient: int


def output_predictor(completion_distance: int) -> int:
    """A Galil output-predicting function from shortest completion distance.

    If ``e(x)`` is the shortest extension length taking ``x`` into the
    language, then ``max(e(x)-1, 0)`` is a number of future outputs guaranteed
    to be zero.  The value zero is permitted and makes the condition vacuous at
    accepting prefixes and at prefixes one symbol from acceptance.
    """

    if not isinstance(completion_distance, int) or completion_distance < 0:
        raise ValueError(completion_distance)
    return max(completion_distance - 1, 0)


def predictor_delta_lower_bound(availability: int) -> int:
    """Uniform lower bound ``Delta k >= availability - 1``."""

    if not isinstance(availability, int) or availability < -1:
        raise ValueError(availability)
    return availability - 1


def certificate() -> SchedulerParameterCertificate:
    return SchedulerParameterCertificate(
        source_ratio_c=SG_RATIO_C,
        source_affine_C=SOURCE_AFFINE_C,
        source_affine_D=SOURCE_AFFINE_D,
        galil_predictability_c=GALIL_PREDICTABILITY_C,
        scheduler_source_step_period=GALIL_SCHEDULER_PERIOD,
        countdown_width_bits=GALIL_SCHEDULER_PERIOD.bit_length(),
        case1_bound=CASE1_PRIMITIVE_BOUND,
        case2_j_coefficient=CASE2_J_COEFFICIENT,
        case3_j_coefficient=CASE3_J_COEFFICIENT,
        case4_bound=CASE4_PRIMITIVE_BOUND,
        case5_bound=CASE5_PRIMITIVE_BOUND,
        case6_j_coefficient=CASE6_J_COEFFICIENT,
    )


def certificate_dict() -> dict:
    return asdict(certificate())


def audit_parameters() -> None:
    """Raise if any arithmetic side condition of the translation fails."""

    c = GALIL_PREDICTABILITY_C
    assert c == CASE5_PRIMITIVE_BOUND
    assert c >= CASE1_PRIMITIVE_BOUND
    assert c >= CASE4_PRIMITIVE_BOUND
    assert 2 * c >= CASE2_J_COEFFICIENT
    assert 2 * c >= CASE3_J_COEFFICIENT
    assert 2 * c >= CASE6_J_COEFFICIENT
    assert SOURCE_AFFINE_C == (CASE6_J_COEFFICIENT + 1) // 2
    assert SOURCE_AFFINE_D == SOURCE_AFFINE_C + CASE5_PRIMITIVE_BOUND
    assert GALIL_SCHEDULER_PERIOD == 2 * c


audit_parameters()
