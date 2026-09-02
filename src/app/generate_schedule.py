from ortools.sat.python import cp_model

from src.core.metrics import compute_metrics, summary_lines
from src.core.model import ScheduleModel, build_model
from src.infrastructure.config import DEFAULT_CONFIG, ScheduleConfig
from src.infrastructure.csv_writer import get_assigned_shift_name, write_schedule_csv
from src.infrastructure.logger import setup_logging
from src.infrastructure.report import write_report

OUTPUT_PATH = "output"


def log_configuration(logger, config: ScheduleConfig) -> None:
    fair_min, fair_max = config.fair_shifts

    logger.info("Starting schedule generation")
    logger.info("Employees: %d", config.num_employees)
    logger.info("Days: %d (%d, weekends derived from calendar)",
                config.num_days, config.year)
    logger.info("Shifts: %s", config.shifts)
    logger.info("Min employees per shift: %d", config.min_ee)
    logger.info("Max employees per shift: %d", config.max_ee)
    logger.info("Weekend days: %d", len(config.weekend_indices))
    logger.info("Max weekend days worked per employee: %d",
                config.max_weekend_days_worked)
    logger.info("Fair weekend days per employee: %d", config.fair_weekend_days)
    logger.info("Fair shifts per employee: %d to %d", fair_min, fair_max)


def extract_schedule(solver, sm: ScheduleModel, config: ScheduleConfig) -> dict:
    return {
        e: [
            get_assigned_shift_name(solver, sm.work, e, d, config.shifts)
            for d in range(config.num_days)
        ]
        for e in config.employees
    }


def log_schedule(logger, schedule: dict) -> None:
    for e, days in schedule.items():
        logger.info("worker %s: %s", e, " ".join(days))


def log_objective_terms(logger, solver, sm: ScheduleModel) -> None:
    logger.info("Penalties:")

    for i, var in enumerate(sm.obj_bool_vars):
        if solver.boolean_value(var):
            penalty = sm.obj_bool_coeffs[i]
            if penalty > 0:
                logger.info("  %s violated, penalty=%s", var.name, penalty)
            else:
                logger.info("  %s fulfilled, gain=%s", var.name, -penalty)

    for i, var in enumerate(sm.obj_int_vars):
        if solver.value(var) > 0:
            logger.info(
                "  %s violated by %s, linear penalty=%s",
                var.name,
                solver.value(var),
                sm.obj_int_coeffs[i],
            )


def solve(sm: ScheduleModel, config: ScheduleConfig) -> tuple[cp_model.CpSolver, int]:
    solver = cp_model.CpSolver()
    #the transition rewards make proving optimality expensive, so cap the run
    solver.parameters.max_time_in_seconds = config.max_solve_seconds
    solver.parameters.symmetry_level = config.symmetry_level
    status = solver.solve(sm.model, cp_model.ObjectiveSolutionPrinter())

    return solver, status


def generate_schedule(
        config: ScheduleConfig = DEFAULT_CONFIG,
        output_path: str = OUTPUT_PATH,
) -> None:
    logger = setup_logging(output_path)
    log_configuration(logger, config)

    logger.info("Creating decision variables and constraints")
    sm = build_model(config)
    logger.info("Objective bool terms: %d", len(sm.obj_bool_vars))
    logger.info("Objective int terms: %d", len(sm.obj_int_vars))

    logger.info("Solving model (time limit: %.0fs)", config.max_solve_seconds)
    solver, status = solve(sm, config)
    logger.info("Solver finished with status: %s", solver.StatusName(status))

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.warning("No feasible solution found")
        logger.info("Solver response stats:\n%s", solver.response_stats())
        return

    if status == cp_model.FEASIBLE:
        logger.info(
            "Stopped on time limit, gap to best bound: %s",
            solver.best_objective_bound - solver.objective_value,
        )

    csv_path = write_schedule_csv(output_path, solver, sm.work, config)
    schedule = extract_schedule(solver, sm, config)
    log_schedule(logger, schedule)
    logger.info("Schedule CSV written to %s", csv_path)

    metrics = compute_metrics(schedule, config)
    logger.info("Quality metrics:")
    for line in summary_lines(metrics, config):
        logger.info("  %s", line)

    report_path = write_report(
        output_path,
        schedule=schedule,
        config=config,
        metrics=metrics,
        solver_status=solver.StatusName(status),
        objective=solver.objective_value,
        gap=solver.best_objective_bound - solver.objective_value,
    )
    logger.info("HTML report written to %s", report_path)

    log_objective_terms(logger, solver, sm)
    logger.info("Solver response stats:\n%s", solver.response_stats())


if __name__ == "__main__":
    generate_schedule()
