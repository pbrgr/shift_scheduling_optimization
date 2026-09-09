"""Unix-filter entry point for the Avanti DPService integration.

Reads the DPService payload from stdin, solves, and writes the result JSON
to stdout — nothing else goes to stdout. Logs go to stderr and to the run
log file; the exit status signals success (0) or error (>0), matching the
contract of the existing wis_main.py integration.

    python -m src.app.avanti_filter < input.json > output.json
"""

import json
import sys

from ortools.sat.python import cp_model

from src.app.generate_schedule import extract_schedule, log_objective_terms, solve
from src.core.metrics import compute_metrics, summary_lines
from src.core.model import build_model
from src.infrastructure.avanti import AvantiError, config_from_avanti, schedule_to_avanti
from src.infrastructure.config import DEFAULT_CONFIG
from src.infrastructure.logger import setup_logging
from src.infrastructure.report import write_report

OUTPUT_PATH = "output"


def run(stdin=None, stdout=None, template=DEFAULT_CONFIG,
        output_path: str = OUTPUT_PATH) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    logger = setup_logging(output_path, console_stream=sys.stderr)

    raw = stdin.read()
    logger.info("Read %d bytes from stdin", len(raw))

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as ex:
        logger.error("stdin is not valid JSON: %s", ex)
        return 1

    try:
        instance = config_from_avanti(payload, template)
        config = instance.config
        logger.info(
            "Parsed Avanti payload: %d employees, %d days (%s to %s), "
            "%d occupied days",
            config.num_employees, config.num_days,
            config.days[0], config.days[-1], len(instance.occupied),
        )
        if config.leader_skills and not config.leader_employees:
            logger.warning(
                "Leader rule stays dormant: nobody in this selection carries "
                "any of %s - check the skill wording in the Avanti DV",
                list(config.leader_skills),
            )
        sm = build_model(config)  #raises ValueError on an invalid config
    except (AvantiError, ValueError) as ex:
        logger.error("%s", ex)
        return 1

    logger.info("Solving (time limit: %.0fs)", config.max_solve_seconds)
    solver, status = solve(sm, config, show_progress=False)
    status_name = solver.StatusName(status)
    logger.info("Solver finished with status: %s", status_name)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.error(
            "No feasible plan. With %d employees the coverage of %d to %d "
            "per shift or the weekend rule cannot be met for this selection.",
            config.num_employees, config.min_ee, config.max_ee,
        )
        return 2

    schedule = extract_schedule(solver, sm, config)
    metrics = compute_metrics(schedule, config)
    for line in summary_lines(metrics, config):
        logger.info("  %s", line)
    log_objective_terms(logger, solver, sm)

    report_path = write_report(
        output_path,
        schedule=schedule, config=config, metrics=metrics,
        solver_status=status_name,
        objective=solver.objective_value,
        gap=solver.best_objective_bound - solver.objective_value,
    )
    logger.info("HTML report written to %s", report_path)

    result = schedule_to_avanti(schedule, instance, status_name)
    json.dump(result, stdout)
    stdout.write("\n")
    logger.info(
        "Wrote %d dienstEinteilungen to stdout", len(result["dienstEinteilungen"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
