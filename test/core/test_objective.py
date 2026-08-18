"""The objective is recomputed from the finished schedule and compared with
what the solver reports.

Every other test asserts that a constraint holds. None of them would notice an
objective term that is wired up wrongly: the rewarded transitions used to be
collected unconditionally, pinning the objective at its theoretical maximum
while the schedule contained a fraction of the rewarded transitions. Every
constraint test stayed green throughout.

The recomputation below deliberately works off the shift names in the schedule
and the plain meaning of the config, never off the model's helper variables, so
a term that does not correspond to reality shows up as a mismatch.
"""

from dataclasses import replace

import pytest

from src.infrastructure.config import ScheduleConfig


@pytest.fixture
def objective_config() -> ScheduleConfig:
    #small, but with every kind of objective term active at once
    return ScheduleConfig(
        year=2026,
        days=["02.03", "03.03", "04.03", "05.03", "06.03", "07.03", "08.03",
              "09.03", "10.03", "11.03", "12.03", "13.03", "14.03", "15.03"],
        employees=list(range(1, 9)),
        shifts=["1N", "2N", "3N", "R"],
        min_ee=1,
        max_ee=3,
        weight_shift_request=-2,
        weight_weekend_fairness=3,
        weight_workload_fairness=8,
        max_solve_seconds=10.0,
        dayoff_assignments=[(1, "03.03")],
        fixed_assignments=[(2, "04.03", "1N")],
        dayoff_requests=[(3, "05.03"), (4, "06.03")],
        assignment_requests=[(5, "07.03", "2N")],
        transitions=[("2N", "1N", -4), ("1N", "3N", -4), ("3N", "1N", 0)],
    )


def recomputed_objective(schedule: dict, config: ScheduleConfig) -> int:
    total = 0

    #requests are rewarded when the schedule actually grants them
    for employee, day, shift in config.all_requests:
        if schedule[employee][config.days.index(day)] == shift:
            total += config.weight_shift_request

    #transitions are rewarded once per occurrence, reward 0 means forbidden
    for prev_shift, next_shift, reward in config.transitions:
        if reward == 0:
            continue
        for days in schedule.values():
            total += reward * sum(
                1
                for d in range(len(days) - 1)
                if days[d] == prev_shift and days[d + 1] == next_shift
            )

    #weekend fairness penalises days below the fair share
    for days in schedule.values():
        worked = sum(
            1 for d in config.weekend_indices if days[d] != config.rest_shift
        )
        total += config.weight_weekend_fairness * max(
            0, config.fair_weekend_days - worked
        )

    #workload fairness penalises both directions out of the fair band
    fair_min, fair_max = config.fair_shifts
    for days in schedule.values():
        worked = sum(1 for shift in days if shift != config.rest_shift)
        total += config.weight_workload_fairness * (
            max(0, fair_min - worked) + max(0, worked - fair_max)
        )

    return total


def test_objective_matches_the_schedule_it_describes(objective_config, solve):
    _, solver, schedule = solve(objective_config)

    assert recomputed_objective(schedule, objective_config) == solver.objective_value


def test_objective_matches_without_any_requests(objective_config, solve):
    config = replace(
        objective_config,
        dayoff_assignments=[],
        fixed_assignments=[],
        dayoff_requests=[],
        assignment_requests=[],
    )
    _, solver, schedule = solve(config)

    assert recomputed_objective(schedule, config) == solver.objective_value


def test_objective_matches_without_any_transitions(objective_config, solve):
    config = replace(objective_config, transitions=[])
    _, solver, schedule = solve(config)

    assert recomputed_objective(schedule, config) == solver.objective_value


def test_objective_matches_when_fairness_is_switched_off(objective_config, solve):
    config = replace(
        objective_config,
        weight_weekend_fairness=0,
        weight_workload_fairness=0,
    )
    _, solver, schedule = solve(config)

    assert recomputed_objective(schedule, config) == solver.objective_value


def test_rewards_cannot_be_collected_without_the_schedule_earning_them(
    objective_config, solve
):
    #the failure mode in plain terms: a plan that earns nothing must score 0,
    #never the sum of every reward the model could theoretically hand out
    config = replace(
        objective_config,
        dayoff_requests=[],
        assignment_requests=[],
        dayoff_assignments=[],
        fixed_assignments=[],
        weight_weekend_fairness=0,
        weight_workload_fairness=0,
        transitions=[("2N", "1N", -4)],
    )
    _, solver, schedule = solve(config)

    occurrences = sum(
        1
        for days in schedule.values()
        for d in range(len(days) - 1)
        if days[d] == "2N" and days[d + 1] == "1N"
    )

    assert solver.objective_value == -4 * occurrences
