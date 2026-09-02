from dataclasses import replace

from src.core.metrics import compute_metrics, summary_lines


def test_metrics_reflect_a_solved_schedule(tiny_config, solve):
    config = replace(
        tiny_config,
        dayoff_requests=[(5, "03.03")],
        transitions=[("1N", "2N", -4), ("2N", "1N", 0)],
    )
    _, _, schedule = solve(config)
    metrics = compute_metrics(schedule, config)

    #totals must add up against the raw schedule
    assert metrics.shifts_worked == {
        e: sum(1 for s in days if s != "R") for e, days in schedule.items()
    }
    assert metrics.requests_fulfilled == (1, 1)
    assert metrics.total_forbidden_transitions == 0
    assert metrics.coverage.keys() == {"1N", "2N"}
    for c_min, c_max in metrics.coverage.values():
        assert config.min_ee <= c_min <= c_max <= config.max_ee


def test_metrics_expose_a_bad_schedule():
    #hand-built pathological plan in the spirit of DPAutoGen-1: one employee
    #works every day, one rests every day, a forbidden transition occurs
    from test.conftest import TINY_DAYS
    from src.infrastructure.config import ScheduleConfig

    config = ScheduleConfig(
        year=2026, days=TINY_DAYS, employees=[1, 2], shifts=["1N", "2N", "R"],
        min_ee=0, max_ee=2, weight_shift_request=-2,
        weight_weekend_fairness=3, weight_workload_fairness=8,
        max_solve_seconds=1.0,
        dayoff_assignments=[], fixed_assignments=[],
        dayoff_requests=[(2, "02.03")], assignment_requests=[],
        transitions=[("1N", "2N", 0)],
    )
    schedule = {
        1: ["1N", "2N", "1N", "1N", "1N", "1N", "1N"],  #1N->2N is forbidden
        2: ["R", "R", "R", "R", "R", "R", "R"],
    }
    metrics = compute_metrics(schedule, config)

    assert metrics.workload_spread == (0, 7)
    assert metrics.employees_outside_fair_band  #both are far off the band
    assert metrics.total_forbidden_transitions == 1
    assert metrics.weekend_days_worked[1] == 2  #07.03/08.03 are the weekend
    assert metrics.requests_fulfilled == (1, 1)  #ee 2 rests on 02.03

    text = "\n".join(summary_lines(metrics, config))
    assert "Forbidden transitions present: 1" in text
    assert "0 to 7" in text
