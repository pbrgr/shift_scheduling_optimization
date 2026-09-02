from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from src.core.formatter import formatter
from src.infrastructure.config import ScheduleConfig


@dataclass
class ScheduleModel:
    model: cp_model.CpModel
    work: dict[tuple[int, int, int], cp_model.BoolVarT]

    #linear terms of the objective in a minimization context
    obj_bool_vars: list[cp_model.BoolVarT] = field(default_factory=list)
    obj_bool_coeffs: list[int] = field(default_factory=list)
    obj_int_vars: list[cp_model.IntVar] = field(default_factory=list)
    obj_int_coeffs: list[int] = field(default_factory=list)

    def add_bool_cost(self, var: cp_model.BoolVarT, coeff: int) -> None:
        self.obj_bool_vars.append(var)
        self.obj_bool_coeffs.append(coeff)

    def add_int_costs(
            self,
            variables: list[cp_model.IntVar],
            coeffs: list[int],
    ) -> None:
        self.obj_int_vars.extend(variables)
        self.obj_int_coeffs.extend(coeffs)

    def minimize(self) -> None:
        self.model.minimize(
            sum(
                self.obj_bool_vars[i] * self.obj_bool_coeffs[i]
                for i in range(len(self.obj_bool_vars))
            )
            + sum(
                self.obj_int_vars[i] * self.obj_int_coeffs[i]
                for i in range(len(self.obj_int_vars))
            )
        )


def add_soft_sum(
        model: cp_model.CpModel,
        works: list[cp_model.BoolVarT],
        soft_min: int,
        soft_max: int,
        hard_max: int,
        min_cost: int,
        max_cost: int,
        prefix: str
)->tuple[list[cp_model.IntVar], list[int]]:
    #sum(works) is hard capped at hard_max via the variable domain.
    #leaving the soft band costs min_cost / max_cost per unit of deviation.
    sum_var = model.new_int_var(0, hard_max, f"{prefix}_sum")
    model.add(sum_var == sum(works))

    cost_vars: list[cp_model.IntVar] = []
    cost_coeffs: list[int] = []

    if min_cost > 0 and soft_min > 0:
        under_sum = model.new_int_var(0, soft_min, f"{prefix}_under_sum")
        model.add_max_equality(under_sum, [soft_min - sum_var, 0])
        cost_vars.append(under_sum)
        cost_coeffs.append(min_cost)

    if max_cost > 0 and soft_max < hard_max:
        over_sum = model.new_int_var(0, hard_max - soft_max, f"{prefix}_over_sum")
        model.add_max_equality(over_sum, [sum_var - soft_max, 0])
        cost_vars.append(over_sum)
        cost_coeffs.append(max_cost)

    return cost_vars, cost_coeffs


def add_one_shift_per_day(sm: ScheduleModel, config: ScheduleConfig) -> None:
    for e in config.employees:
        for d in range(config.num_days):
            sm.model.add_exactly_one(
                sm.work[e, s, d] for s in range(config.num_shifts)
            )


def add_cover_constraints(sm: ScheduleModel, config: ScheduleConfig) -> None:
    #free shifts are not covered; a composite shift (e.g. 1N3N) counts
    #towards the coverage of each of its parts
    for atomic in config.atomic_working_shifts:
        indices = [config.shifts.index(s) for s in config.shifts_covering(atomic)]
        for d in range(config.num_days):
            assigned = [
                sm.work[e, s, d] for e in config.employees for s in indices
            ]
            sm.model.add(sum(assigned) >= config.min_ee)
            sm.model.add(sum(assigned) <= config.max_ee)


def add_compensation_rule(sm: ScheduleModel, config: ScheduleConfig) -> None:
    #a compensation day is only allowed right after a night duty
    if config.compensation_shift is None:
        return

    comp = config.shifts.index(config.compensation_shift)
    follows = [config.shifts.index(s) for s in config.compensation_follows]

    #day 0 has no visible predecessor. left open, the solver hands out free
    #compensation days there to collect the Komp->R transition reward, so it
    #is forbidden unless the planner fixed it (night duty in the prior month)
    fixed_day0 = {
        e
        for e, day, shift in config.all_fixed_assignments
        if day == config.days[0] and shift == config.compensation_shift
    }

    for e in config.employees:
        if e not in fixed_day0:
            sm.model.add(sm.work[e, comp, 0] == 0)

        for d in range(1, config.num_days):
            sm.model.add_bool_or(
                [~sm.work[e, comp, d]]
                + [sm.work[e, f, d - 1] for f in follows]
            )


def add_transitions(
        sm: ScheduleModel,
        config: ScheduleConfig,
        fmt: formatter,
) -> None:
    for prev_name, next_name, reward in config.transitions:
        prev_shift, next_shift, reward = fmt.reward_transitions(
            prev_name, next_name, reward
        )

        for e in config.employees:
            for d in range(config.num_days - 1):
                if reward == 0:
                    #forbid the transition outright
                    sm.model.add_bool_or([
                        ~sm.work[e, prev_shift, d],
                        ~sm.work[e, next_shift, d + 1],
                    ])
                else:
                    #trans_var must equal the transition actually happening,
                    #otherwise a negative reward would be collected for free
                    trans_var = sm.model.new_bool_var(
                        f"transition_{prev_shift}_{next_shift}_{e}_{d}"
                    )
                    sm.model.add_min_equality(
                        trans_var,
                        [sm.work[e, prev_shift, d], sm.work[e, next_shift, d + 1]],
                    )
                    sm.add_bool_cost(trans_var, reward)


def add_assignments_and_requests(
        sm: ScheduleModel,
        config: ScheduleConfig,
        fmt: formatter,
) -> None:
    #one-off days off, fixed shifts and weekly recurring rules all end up as
    #the same (employee, day, shift) triples
    hard = [
        fmt.get_fixed_assignment(ee, day, shift)
        for ee, day, shift in config.all_fixed_assignments
    ]

    soft = [
        fmt.get_employee_requests(ee, day, shift)
        for ee, day, shift in config.all_requests
    ]

    for e, s, d in hard:
        sm.model.add(sm.work[e, s, d] == 1)

    for e, s, d, w in soft:
        sm.add_bool_cost(sm.work[e, s, d], w)


def add_weekend_fairness(sm: ScheduleModel, config: ScheduleConfig) -> None:
    for e in config.employees:
        weekend_work = []
        for d in config.weekend_indices:
            worked_that_day = sm.model.new_bool_var(f"weekend_work_{e}_{d}")
            sm.model.add_max_equality(
                worked_that_day,
                [sm.work[e, s, d] for s in config.working_shift_indices],
            )
            weekend_work.append(worked_that_day)

        sm.add_int_costs(*add_soft_sum(
            sm.model,
            weekend_work,
            config.fair_weekend_days,
            config.max_weekend_days_worked,
            config.max_weekend_days_worked,
            config.weight_weekend_fairness,
            0, #upper bound is already hard capped
            f"weekend_{e}",
        ))


def add_workload_fairness(sm: ScheduleModel, config: ScheduleConfig) -> None:
    fair_min, fair_max = config.fair_shifts

    #a composite shift fills several coverage slots in one day, so it has to
    #weigh accordingly, otherwise a 1N3N day would look like half the work
    hard_max = config.num_days * max(
        (config.shift_load(config.shifts[s]) for s in config.working_shift_indices),
        default=1,
    )

    for e in config.employees:
        #exactly one shift per day, so summing the weighted working shifts
        #over all days counts the coverage slots actually filled
        total_work = []
        for d in range(config.num_days):
            for s in config.working_shift_indices:
                total_work.extend(
                    [sm.work[e, s, d]] * config.shift_load(config.shifts[s])
                )

        sm.add_int_costs(*add_soft_sum(
            sm.model,
            total_work,
            fair_min,
            fair_max,
            hard_max,
            config.weight_workload_fairness,
            config.weight_workload_fairness,
            f"workload_{e}",
        ))


def build_model(config: ScheduleConfig) -> ScheduleModel:
    config.validate()

    model = cp_model.CpModel()
    fmt = formatter(
        shifts=config.shifts,
        days=config.days,
        weight_requests=config.weight_shift_request,
    )

    # create work variable with domain {0, 1}
    work = {
        (e, s, d): model.new_bool_var(f"work{e}_{s}_{d}")
        for e in config.employees
        for s in range(config.num_shifts)
        for d in range(config.num_days)
    }

    sm = ScheduleModel(model=model, work=work)

    add_one_shift_per_day(sm, config)
    add_cover_constraints(sm, config)
    add_compensation_rule(sm, config)
    add_transitions(sm, config, fmt)
    add_assignments_and_requests(sm, config, fmt)
    add_weekend_fairness(sm, config)
    add_workload_fairness(sm, config)

    sm.minimize()

    return sm
