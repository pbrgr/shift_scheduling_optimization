"""The KNZ shift system from the KAPO TG document "Ablauf/Regeln
Dienstplanung KNZ" (26.11.2026): the 1N3N composite day, the Komp
compensation day and the 3/8 weekend rule."""

from dataclasses import replace

import pytest
from ortools.sat.python import cp_model

from src.core.metrics import compute_metrics
from src.core.model import build_model
from src.infrastructure.config import DEFAULT_CONFIG


@pytest.fixture
def knz_config(tiny_config):
    return replace(
        tiny_config,
        shifts=["1N", "2N", "3N", "1N3N", "Komp", "R"],
        compensation_shift="Komp",
        compensation_follows=("3N", "1N3N"),
        composite_shifts={"1N3N": ("1N", "3N")},
    )


def test_composite_counts_towards_both_coverages(knz_config, solve):
    _, _, schedule = solve(knz_config)
    metrics = compute_metrics(schedule, knz_config)

    #coverage is reported per atomic shift, with 1N3N counted for both
    assert set(metrics.coverage) == {"1N", "2N", "3N"}
    for c_min, c_max in metrics.coverage.values():
        assert knz_config.min_ee <= c_min <= c_max <= knz_config.max_ee


def test_composite_day_fills_two_workload_slots(knz_config, solve):
    config = replace(knz_config, fixed_assignments=[(3, "04.03", "1N3N")])
    _, _, schedule = solve(config)
    metrics = compute_metrics(schedule, config)

    plain_days = sum(1 for s in schedule[3] if s not in ("1N3N", "Komp", "R"))
    composite_days = sum(1 for s in schedule[3] if s == "1N3N")
    assert metrics.shifts_worked[3] == plain_days + 2 * composite_days
    assert composite_days >= 1


def test_compensation_requires_a_night_duty_the_day_before(knz_config):
    #2N on 03.03 followed by Komp on 04.03 violates the rule
    config = replace(
        knz_config,
        fixed_assignments=[(2, "03.03", "2N"), (2, "04.03", "Komp")],
    )
    sm = build_model(config)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.max_solve_seconds

    assert solver.solve(sm.model) == cp_model.INFEASIBLE


def test_compensation_after_a_night_duty_is_allowed(knz_config, solve):
    config = replace(
        knz_config,
        fixed_assignments=[(2, "03.03", "3N"), (2, "04.03", "Komp")],
    )
    _, _, schedule = solve(config)

    assert schedule[2][config.days.index("04.03")] == "Komp"


def test_compensation_counts_as_a_free_weekend_day(knz_config, solve):
    #a Komp on saturday must not count as weekend work
    config = replace(
        knz_config,
        fixed_assignments=[(2, "06.03", "3N"), (2, "07.03", "Komp")],
    )
    _, _, schedule = solve(config)
    metrics = compute_metrics(schedule, config)

    saturday = config.days.index("07.03")
    worked_weekend_days = sum(
        1
        for d in config.weekend_indices
        if schedule[2][d] not in config.free_shifts
    )
    assert schedule[2][saturday] == "Komp"
    assert metrics.weekend_days_worked[2] == worked_weekend_days


def test_default_weekend_cap_follows_the_knz_document():
    #"5 of 8 weekend days per month are free": at most 3 of 8 are worked.
    #the shipped period has 10 weekend days, so the cap is int(10 * 3/8) = 3
    assert DEFAULT_CONFIG.max_weekend_work_ratio == 3 / 8
    assert DEFAULT_CONFIG.max_weekend_days_worked == 3


def test_default_config_encodes_the_standard_sequence():
    #2N, 1N3N, Komp, Ruhetag is the documented first-priority sequence
    rewarded = {
        (p, n) for p, n, w in DEFAULT_CONFIG.transitions if w < 0
    }
    assert {("2N", "1N3N"), ("1N3N", "Komp"), ("Komp", "R")} <= rewarded

    forbidden = {
        (p, n) for p, n, w in DEFAULT_CONFIG.transitions if w == 0
    }
    #a night part ends 06:30, a morning shift starts 06:00 the same morning
    assert {("3N", "1N"), ("1N3N", "1N"), ("3N", "1N3N")} <= forbidden


def test_compensation_on_day_zero_is_forbidden(knz_config, solve):
    #left open, the solver would hand out free Komp days on day 0 to collect
    #the Komp->R reward without any night duty justifying them
    config = replace(
        knz_config,
        transitions=[("Komp", "R", -4)],
    )
    _, _, schedule = solve(config)

    assert all(days[0] != "Komp" for days in schedule.values())


def test_compensation_on_day_zero_can_be_fixed_by_the_planner(knz_config, solve):
    #night duty on the last day of the previous month: the planner fixes it
    config = replace(
        knz_config,
        fixed_assignments=[(2, "02.03", "Komp")],
    )
    _, _, schedule = solve(config)

    assert schedule[2][0] == "Komp"
