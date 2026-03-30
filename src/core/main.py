from absl import app
from absl import flags

from ortools.sat.python import cp_model
from formatter import formatter
from logger import setup_logging
import numpy as np
import csv
import os

import sys

output_path = 'output'

employees = np.arange(1, 31)
days = np.arange(1, 32) # e.g. for march
shifts = ["1N", "2N", "3N", "R"]

min_ee = 3 #min ee per shift
max_ee = 5

weight_shift_request = -2 #neg means that the requests always need to be formulated in a positive way
#so that the ee wants that specific shift

employees_dayoff_assignment = [
    (4, 2),
    (9, 15)
]

employees_fixed_assignment = [
    (4, 5, "1N")
]

employees_dayoff_requests = [
    (1, 2),
    (5, 15),
    (7, 15)
]

employees_assignment_requests = [
    (1, 3, "2N")
]

#transitions:
#(previous_shift, next_shift, penalty)
#0 means forbidden
transitions = [
    ("2N", "1N", -4),
    ("1N", "3N", -4),
    ("3N", "R", -4),
    ("3N", "1N", 0)
]

#TODO: finish function
def add_assignments_requests(
        model: cp_model.CpModel,
        work,
        fixed_assignments: list,
        requests: list,
        obj_bool_vars: list[cp_model.BoolVarT],
        obj_bool_coeffs: list[int]
):
    for e, s, d in fixed_assignments:
        model.add(work[e, s, d]==1)
    
    for e, s, d, w in requests:
        obj_bool_vars.append(work[e, s, d])
        obj_bool_coeffs.append(w)


def get_assigned_shift_name(solver, work, employee, day, shifts):
    for s, shift_name in enumerate(shifts):
        if solver.boolean_value(work[employee, s, day]):
            return shift_name
    return ""

if __name__=="__main__":
    logger = setup_logging(output_path)
    # num_days = len(days)
    # num_employees = len(employees)
    num_shifts = len(shifts)

    logger.info("Starting schedule generation")
    logger.info("Employees: %d", len(employees))
    logger.info("Days: %d", len(days))
    logger.info("Shifts: %s", shifts)
    logger.info("Min employees per shift: %d", min_ee)
    logger.info("Max employees per shift: %d", max_ee)

    model = cp_model.CpModel()
    formatter = formatter(shifts=shifts, weight_requests=weight_shift_request)

    logger.info("Creating decision variables")

    # create work variable with domain {0, 1}
    work = {}
    for e in employees:
        for s in range(num_shifts):
            for d in days:
                work[e, s, d] = model.new_bool_var(f"work{e}_{s}_{d}")

    # Linear terms of the objective in a minimization context.
    obj_int_vars: list[cp_model.IntVar] = []
    obj_int_coeffs: list[int] = []
    obj_bool_vars: list[cp_model.BoolVarT] = []
    obj_bool_coeffs: list[int] = []

    # for each ee only one shift per day
    logger.info("Adding one-shift-per-day constraints")
    for e in employees:
        for d in days:
            model.add_exactly_one(work[e, s, d] for s in range(num_shifts))

    #Cover constraints:
    logger.info("Adding coverage constraints")
    for s in range(num_shifts-1): #need to not take R into account
        for d in days:
            assigned = [work[e, s, d] for e in employees]
            model.add(sum(assigned) >= min_ee)
            model.add(sum(assigned) <= max_ee)

    #Reward Good Transitions:
    for prev_shift, next_shift, reward in transitions:
        prev_shift, next_shift, reward = formatter.reward_transitions(prev_shift,next_shift,reward)

        for e in employees:
            for d in days[:-1]:
                t = [
                    ~work[e, prev_shift, d],
                    ~work[e, next_shift, d + 1],
                ]

                if reward == 0:
                    model.add_bool_or(t)
                else:
                    trans_var = model.new_bool_var(
                        f"transition (employee={e}, day={d})"
                    )
                    t.append(trans_var)
                    model.add_bool_or(t)
                    obj_bool_vars.append(trans_var)
                    obj_bool_coeffs.append(reward)

    #days off assignment:
    logger.info("Preparing fixed assignments")
    fixed_assignments = []
    for ee, day in employees_dayoff_assignment:
        fa = formatter.get_fixed_assignment(ee, day, "R")
        fixed_assignments.append(fa)

    #add other logic for assignment that need to be honored
    #where they append on to fixed_assignments
    for ee, day, shift in employees_fixed_assignment:
        fa = formatter.get_fixed_assignment(ee, day, shift)
        fixed_assignments.append(fa)

    logger.info("Fixed assignments count: %d", len(fixed_assignments))

    logger.info("Preparing requests")

    #day off request
    requests = []
    for ee, day in employees_dayoff_requests:
        req = formatter.get_employee_requests(ee, day, "R")
        requests.append(req)

    #add other logic for requested shifts that are not days off
    for ee, day, shift in employees_assignment_requests:
        req = formatter.get_employee_requests(ee, day, shift)
        requests.append(req)

    logger.info("Requests count: %d", len(requests))

    add_assignments_requests(model, work,fixed_assignments, requests,
                             obj_bool_vars, obj_bool_coeffs)
    logger.info("Objective bool terms: %d", len(obj_bool_vars))
    logger.info("Objective int terms: %d", len(obj_int_vars))


    # Objective
    model.minimize(
        sum(obj_bool_vars[i] * obj_bool_coeffs[i] for i in range(len(obj_bool_vars)))
        + sum(obj_int_vars[i] * obj_int_coeffs[i] for i in range(len(obj_int_vars)))
    )

    logger.info("Solving model")
    # Solve the model.
    solver = cp_model.CpSolver()
    # if params:
    #     solver.parameters.parse_text_format(params)
    solution_printer = cp_model.ObjectiveSolutionPrinter()
    status = solver.solve(model, solution_printer)
    
    logger.info("Solver finished with status: %s", solver.StatusName(status))

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        csv_path = os.path.join(output_path, "schedule.csv")
        with open(csv_path, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["employee"] + [f"day_{d}" for d in days])

            for e in employees:
                row = [e]
                for d in days:
                    row.append(get_assigned_shift_name(solver, work, e, d, shifts))
                writer.writerow(row)

        print()
        # header = "          "
        # for w in range(num_weeks):
        #     header += "M T W T F S S "
        # print(header)
        for e in employees:
            schedule = ""
            for d in days:
                schedule += get_assigned_shift_name(solver, work, e, d, shifts) + " "
            logger.info(f"worker {e}: {schedule}")
        logger.info("Schedule CSV written to %s", csv_path)

        logger.info("Penalties:")
        for i, var in enumerate(obj_bool_vars):
            if solver.boolean_value(var):
                penalty = obj_bool_coeffs[i]
                if penalty > 0:
                    logger.info("  %s violated, penalty=%s", var.name, penalty)
                else:
                    logger.info("  %s fulfilled, gain=%s", var.name, -penalty)

        for i, var in enumerate(obj_int_vars):
            if solver.value(var) > 0:
                logger.info(
                    "  %s violated by %s, linear penalty=%s",
                    var.name,
                    solver.value(var),
                    obj_int_coeffs[i],
                )
    else:
        logger.warning("No feasible solution found")

    logger.info("Solver response stats:\n%s", solver.response_stats())
