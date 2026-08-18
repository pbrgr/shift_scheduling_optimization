import csv
import os

from ortools.sat.python import cp_model

from src.infrastructure.config import ScheduleConfig


def get_assigned_shift_name(solver, work, employee, day, shifts) -> str:
    for s, shift_name in enumerate(shifts):
        if solver.boolean_value(work[employee, s, day]):
            return shift_name
    return ""


def schedule_rows(
        solver: cp_model.CpSolver,
        work: dict,
        config: ScheduleConfig,
) -> list[list]:
    return [
        [e] + [
            get_assigned_shift_name(solver, work, e, d, config.shifts)
            for d in range(config.num_days)
        ]
        for e in config.employees
    ]


def write_schedule_csv(
        output_path: str,
        solver: cp_model.CpSolver,
        work: dict,
        config: ScheduleConfig,
) -> str:
    os.makedirs(output_path, exist_ok=True)
    csv_path = os.path.join(output_path, "schedule.csv")

    with open(csv_path, "w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["employee"] + [f"day_{d}" for d in config.days])
        writer.writerows(schedule_rows(solver, work, config))

    return csv_path
