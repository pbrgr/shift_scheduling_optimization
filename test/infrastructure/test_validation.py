from dataclasses import replace

import pytest

from src.core.model import build_model
from src.infrastructure.config import DEFAULT_CONFIG, FRIDAY


def problems_of(**overrides) -> str:
    return "\n".join(replace(DEFAULT_CONFIG, **overrides).problems())


def test_the_shipped_config_is_valid():
    assert DEFAULT_CONFIG.problems() == []


def test_rest_shift_is_found_by_name_not_by_position():
    #regression: working shifts used to be range(num_shifts - 1), so moving R
    #turned a real shift into the rest shift and produced a plausible but
    #wrong schedule without any complaint
    config = replace(
        DEFAULT_CONFIG, shifts=["R", "Komp", "1N", "2N", "3N", "1N3N"]
    )

    assert config.problems() == []
    assert config.rest_shift_index == 0
    assert config.working_shift_indices == (2, 3, 4, 5)
    assert config.atomic_working_shifts == ("1N", "2N", "3N")


def test_unknown_rest_shift_is_rejected():
    assert "not one of shifts" in problems_of(rest_shift="frei")


def test_coverage_bounds_the_wrong_way_round_are_rejected():
    assert "min_ee 6 is above max_ee 3" in problems_of(min_ee=6, max_ee=3)


def test_duplicate_days_are_rejected():
    days = DEFAULT_CONFIG.days[:-1] + ["30.03"]

    assert "days contains '30.03' more than once" in problems_of(days=days)


def test_unknown_employee_is_rejected():
    assert "unknown employee 99" in problems_of(
        fixed_assignments=[(99, "06.03", "1N")]
    )


def test_unknown_day_is_rejected():
    assert "unknown day '15.07'" in problems_of(
        fixed_assignments=[(4, "15.07", "1N")]
    )


def test_unknown_shift_is_rejected():
    assert "unknown shift 'XX'" in problems_of(
        fixed_assignments=[(4, "06.03", "XX")]
    )


def test_unknown_shift_in_a_transition_is_rejected():
    assert "transition refers to unknown shift 'XX'" in problems_of(
        transitions=[("XX", "1N", -4)]
    )


def test_weekday_outside_the_week_is_rejected():
    assert "has weekday 9" in problems_of(recurring_assignments=[(1, 9, "R")])


def test_non_positive_time_limit_is_rejected():
    assert "is not positive" in problems_of(max_solve_seconds=0.0)


def test_conflicting_hard_rules_are_still_reported():
    #employee 4 is fixed to 1N on 06.03, which is a friday
    assert "employee 4 on 06.03 demanded as 1N/R" in problems_of(
        recurring_assignments=[(4, FRIDAY, "R")]
    )


def test_every_problem_is_reported_at_once():
    #a broken config should be fixable in one pass, not one message per run
    found = replace(
        DEFAULT_CONFIG,
        min_ee=6,
        max_ee=3,
        fixed_assignments=[(99, "15.07", "XX")],
    ).problems()

    assert len(found) == 4


def test_build_model_refuses_an_invalid_config():
    config = replace(DEFAULT_CONFIG, min_ee=6, max_ee=3)

    with pytest.raises(ValueError, match="invalid schedule configuration"):
        build_model(config)


def test_compensation_without_follows_is_rejected():
    assert "compensation_follows is empty" in problems_of(
        compensation_follows=()
    )


def test_composite_with_unknown_part_is_rejected():
    assert "refers to unknown shift 'XX'" in problems_of(
        composite_shifts={"1N3N": ("1N", "XX")}
    )


def test_composite_part_must_be_atomic():
    assert "must be an atomic working shift" in problems_of(
        composite_shifts={"1N3N": ("1N", "R")}
    )
