"""The plan must always compute: rules that used to be hard are penalised.

An impossible selection yields a plan with visible violations rather than
INFEASIBLE, and the violations dominate the objective so they only appear
when genuinely unavoidable."""

from dataclasses import replace


def test_a_selection_too_small_still_yields_a_plan(tiny_config, solve):
    #3 employees cannot fill 2 shifts x 2 heads: formerly INFEASIBLE
    config = replace(tiny_config, employees=[1, 2, 3], min_ee=2, max_ee=2)
    _, solver, schedule = solve(config)

    assert len(schedule) == 3  #solve() already asserts a solution exists


def test_understaffing_is_counted_and_reported(tiny_config, solve):
    from src.core.metrics import compute_metrics, summary_lines

    config = replace(tiny_config, employees=[1, 2], min_ee=2, max_ee=2)
    _, _, schedule = solve(config)
    metrics = compute_metrics(schedule, config)

    #2 employees for 2 shifts x 2 heads: at least someone is missing
    assert metrics.understaffed_slots > 0
    assert any("STAFFING VIOLATED" in line
               for line in summary_lines(metrics, config))


def test_rules_still_hold_when_the_selection_allows_it(tiny_config, solve):
    #with enough people the penalties keep every former hard rule intact
    _, _, schedule = solve(tiny_config)
    from src.core.metrics import compute_metrics

    metrics = compute_metrics(schedule, tiny_config)
    assert metrics.understaffed_slots == 0
    assert metrics.overstaffed_slots == 0
    assert not metrics.employees_over_weekend_cap


def test_fixed_entries_violating_a_forbidden_transition_do_not_explode(
    tiny_config, solve
):
    #Avanti can deliver manually planned entries that break the sequence
    #rules; they are reality and must not make the model infeasible
    config = replace(
        tiny_config,
        transitions=[("1N", "2N", 0)],
        fixed_assignments=[(4, "03.03", "1N"), (4, "04.03", "2N")],
    )
    _, _, schedule = solve(config)

    assert schedule[4][1] == "1N" and schedule[4][2] == "2N"


def test_forbidden_transitions_are_avoided_when_possible(tiny_config, solve):
    from src.core.metrics import compute_metrics

    config = replace(tiny_config, transitions=[("1N", "2N", 0)])
    _, _, schedule = solve(config)

    assert compute_metrics(schedule, config).total_forbidden_transitions == 0
