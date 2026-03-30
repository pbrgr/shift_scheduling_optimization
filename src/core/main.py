from absl import app
from absl import flags

from ortools.sat.python import cp_model
from formatter import formatter
import numpy as np
import csv

import sys


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
    # num_days = len(days)
    # num_employees = len(employees)
    num_shifts = len(shifts)

    model = cp_model.CpModel()
    formatter = formatter(shifts=shifts, weight_requests=weight_shift_request)

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
    for e in employees:
        for d in days:
            model.add_exactly_one(work[e, s, d] for s in range(num_shifts))

    #Cover constraints:
    for s in range(num_shifts-1): #need to not take R into account
        for d in days:
            assigned = [work[e, s, d] for e in employees]
            model.add(sum(assigned) >= min_ee)
            model.add(sum(assigned) <= max_ee)


    #days off assignment:
    fixed_assignments = []
    for ee, day in employees_dayoff_assignment:
        fa = formatter.get_fixed_assignment(ee, day, "R")
        fixed_assignments.append(fa)

    #add other logic for assignment that need to be honored
    #where they append on to fixed_assignments
    for ee, day, shift in employees_fixed_assignment:
        fa = formatter.get_fixed_assignment(ee, day, shift)
        fixed_assignments.append(fa)


    #day off request
    requests = []
    for ee, day in employees_dayoff_requests:
        req = formatter.get_employee_requests(ee, day, "R")
        requests.append(req)

    #add other logic for requested shifts that are not days off
    for ee, day, shift in employees_assignment_requests:
        req = formatter.get_employee_requests(ee, day, shift)
        requests.append(req)

  
    #TODO:call add_assigmnet_request
    add_assignments_requests(model, work,fixed_assignments, requests,
                             obj_bool_vars, obj_bool_coeffs)
    

    # Objective
    model.minimize(
        sum(obj_bool_vars[i] * obj_bool_coeffs[i] for i in range(len(obj_bool_vars)))
        + sum(obj_int_vars[i] * obj_int_coeffs[i] for i in range(len(obj_int_vars)))
    )

    # Solve the model.
    solver = cp_model.CpSolver()
    # if params:
    #     solver.parameters.parse_text_format(params)
    solution_printer = cp_model.ObjectiveSolutionPrinter()
    status = solver.solve(model, solution_printer)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        csv_path = "schedule.csv"
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
            print(f"worker {e}: {schedule}")
        print(f"\nSchedule CSV written to {csv_path}")
        print()
        print("Penalties:")
        for i, var in enumerate(obj_bool_vars):
            if solver.boolean_value(var):
                penalty = obj_bool_coeffs[i]
                if penalty > 0:
                    print(f"  {var.name} violated, penalty={penalty}")
                else:
                    print(f"  {var.name} fulfilled, gain={-penalty}")

        for i, var in enumerate(obj_int_vars):
            if solver.value(var) > 0:
                print(
                    f"  {var.name} violated by {solver.value(var)}, linear"
                    f" penalty={obj_int_coeffs[i]}"
                )

    print()
    print(solver.response_stats())
