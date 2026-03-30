from absl import app
from absl import flags

from ortools.sat.python import cp_model
from formatter import formatter
import numpy as np


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

if __name__=="__main__":
    num_days = len(days)
    num_employees = len(employees)
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
            model.add_exactly_one(work[e, s, d] for s in shifts)

    #Cover constraints:
    for s in range(num_shifts):
        for d in days:
            assigned = [work[e, s, d] for e in employees]
            model.add(sum(assigned>= min_ee))
            model.add(sum(assigned<= max_ee))


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
    add_assignments_requests(model, fixed_assignments, requests,
                             obj_bool_vars, obj_bool_coeffs)