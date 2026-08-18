from dataclasses import replace

import pytest
from ortools.sat.python import cp_model

from src.core.model import build_model
from src.infrastructure.config import ScheduleConfig
from src.infrastructure.csv_writer import get_assigned_shift_name

#02.03.2026 is a monday, so this is exactly one week with 2 weekend days
TINY_DAYS = ["02.03", "03.03", "04.03", "05.03", "06.03", "07.03", "08.03"]


@pytest.fixture
def tiny_config() -> ScheduleConfig:
    #small enough to solve instantly, large enough for every constraint to bite
    return ScheduleConfig(
        year=2026,
        days=TINY_DAYS,
        employees=[1, 2, 3, 4, 5, 6],
        shifts=["1N", "2N", "R"],
        min_ee=1,
        max_ee=2,
        weight_shift_request=-2,
        weight_weekend_fairness=3,
        weight_workload_fairness=8,
        max_solve_seconds=10.0,
        dayoff_assignments=[],
        fixed_assignments=[],
        dayoff_requests=[],
        assignment_requests=[],
        transitions=[],
    )


@pytest.fixture
def solve():
    def _solve(config: ScheduleConfig):
        sm = build_model(config)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = config.max_solve_seconds
        status = solver.solve(sm.model)

        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), (
            f"expected a solution, got {solver.StatusName(status)}"
        )

        schedule = {
            e: [
                get_assigned_shift_name(solver, sm.work, e, d, config.shifts)
                for d in range(config.num_days)
            ]
            for e in config.employees
        }
        return sm, solver, schedule

    return _solve


def with_transitions(config: ScheduleConfig, transitions) -> ScheduleConfig:
    return replace(config, transitions=transitions)
