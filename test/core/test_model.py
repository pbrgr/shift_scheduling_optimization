from dataclasses import replace

from test.conftest import with_transitions


def working_shifts(config):
    return config.shifts[:-1]


def count_transitions(schedule, prev_shift, next_shift):
    return sum(
        1
        for days in schedule.values()
        for d in range(len(days) - 1)
        if days[d] == prev_shift and days[d + 1] == next_shift
    )


def test_every_employee_works_exactly_one_shift_per_day(tiny_config, solve):
    _, _, schedule = solve(tiny_config)

    for e, days in schedule.items():
        assert len(days) == tiny_config.num_days
        #an empty string would mean no shift was picked at all
        assert all(shift in tiny_config.shifts for shift in days), e


def test_coverage_stays_within_bounds(tiny_config, solve):
    _, _, schedule = solve(tiny_config)

    for shift in working_shifts(tiny_config):
        for d in range(tiny_config.num_days):
            assigned = sum(1 for days in schedule.values() if days[d] == shift)
            assert tiny_config.min_ee <= assigned <= tiny_config.max_ee, (shift, d)


def test_day_off_shift_is_not_covered(tiny_config, solve):
    #R must be free to exceed max_ee, otherwise nobody could rest
    config = replace(tiny_config, employees=list(range(1, 13)))
    _, _, schedule = solve(config)

    resting = max(
        sum(1 for days in schedule.values() if days[d] == "R")
        for d in range(config.num_days)
    )
    assert resting > config.max_ee


def test_forbidden_transition_never_occurs(tiny_config, solve):
    config = with_transitions(tiny_config, [("1N", "2N", 0)])
    _, _, schedule = solve(config)

    assert count_transitions(schedule, "1N", "2N") == 0


def test_rewarded_transition_is_only_paid_when_it_happens(tiny_config, solve):
    #regression: with the penalty formulation from the OR-Tools example a
    #negative coefficient let the solver set every transition variable to 1
    #unconditionally, collecting the reward without ever scheduling it
    config = with_transitions(tiny_config, [("1N", "2N", -4)])
    sm, solver, schedule = solve(config)

    rewarded = sum(1 for v in sm.obj_bool_vars if solver.boolean_value(v))
    actual = count_transitions(schedule, "1N", "2N")

    assert rewarded == actual


def test_rewarded_transition_makes_the_solver_seek_it_out(tiny_config, solve):
    without = solve(tiny_config)[2]
    with_reward = solve(with_transitions(tiny_config, [("1N", "2N", -4)]))[2]

    assert count_transitions(with_reward, "1N", "2N") > count_transitions(
        without, "1N", "2N"
    )


def test_weekend_cap_applies_to_every_employee(tiny_config, solve):
    #regression: the loop ran over `ee` but indexed work[] with the leftover
    #`e` of the previous loop, so the cap only ever bound the last employee
    _, _, schedule = solve(tiny_config)

    for e, days in schedule.items():
        worked = sum(
            1 for d in tiny_config.weekend_indices if days[d] != "R"
        )
        assert worked <= tiny_config.max_weekend_days_worked, e


def test_fixed_assignment_is_honoured(tiny_config, solve):
    config = replace(tiny_config, fixed_assignments=[(3, "04.03", "2N")])
    _, _, schedule = solve(config)

    assert schedule[3][config.days.index("04.03")] == "2N"


def test_day_off_assignment_is_honoured(tiny_config, solve):
    config = replace(tiny_config, dayoff_assignments=[(2, "05.03")])
    _, _, schedule = solve(config)

    assert schedule[2][config.days.index("05.03")] == "R"


def test_requests_are_soft_and_rewarded_when_met(tiny_config, solve):
    config = replace(tiny_config, dayoff_requests=[(5, "03.03")])
    sm, solver, schedule = solve(config)

    #the only objective term here is the request itself
    assert len(sm.obj_bool_vars) == 1
    assert sm.obj_bool_coeffs == [config.weight_shift_request]
    assert schedule[5][config.days.index("03.03")] == "R"


def test_workload_fairness_narrows_the_spread(tiny_config, solve):
    #more employees than the coverage needs, so the solver has room to be unfair
    config = replace(tiny_config, employees=list(range(1, 13)))

    unweighted = solve(replace(config, weight_workload_fairness=0))[2]
    weighted = solve(config)[2]

    def spread(schedule):
        totals = [sum(1 for s in days if s != "R") for days in schedule.values()]
        return max(totals) - min(totals)

    assert spread(weighted) <= spread(unweighted)
