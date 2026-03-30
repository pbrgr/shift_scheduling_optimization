from absl import app
from absl import flags

from ortools.sat.python import cp_model
import numpy as np


employees = np.arange(1, 31)
days = np.arange(1, 32) # e.g. for march
shifts = ["1N", "2N", "3N", "R"]

weight_shift_request = -2 #neg means that the requests always need to be formulated in a positive way
#so that the ee wants that specific shift


employees_dayoff_assignment = [
    (4, 2),
    (9, 15)
]

employees_dayoff_requests = [
    (1, 2),
    (5, 15),
    (7, 15)
]

#fixed assignments, which ee has specific days off, or have to work a specific shift
def get_fixed_assignment(
        employee: int,
        day: int,
        shift: str,
        shifts: list
)->tuple[int, int, int]:
    shift_number = shifts.index(shift)

    return employee, shift_number, day

#TODO: add logic to add fixed assignments for specific days
#e.g. ee 1 every wednesday needs to have the day off for education



#requests, so predefine weight, so that it is the same for all
def get_employee_requests(
        employee: int,
        day: int,
        shift: str,
        shifts: list,
        weight_request: int
)->tuple[int, int, int, int]:
    shift_number = shifts.index(shift)

    return employee, shift_number, day, weight_request


#TODO: add function for shift requests, so not day off, but specific shifts


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

    # create work variable with domain {0, 1}
    work = {}
    for e in num_employees:
        for s in num_shifts:
            for d in range(num_days):
                work[e, s, d] = model.new_bool_var(f"work{e}_{s}_{d}")

    #TODO: add objectives to min or max

    # for each ee only one shift per day
    for e in employees:
        for d in days:
            model.add_exactly_one(work[e, s, d] for s in shifts)

    #days off assignment:
    fixed_assignments = []
    for ee, day in employees_dayoff_assignment:
        fa = get_fixed_assignment(ee, day, "R", shifts)
        fixed_assignments.append(fa)

    #TODO: add other logic for assignment that need to be honored
    #where they append on to fixed_assignments


    #day off request
    requests = []
    for ee, day in employees_dayoff_requests:
        req = get_employee_requests(ee, day, "R", shifts, weight_shift_request)
        requests.append(req)

    #TODO: add other logic for requested shifts that are not days off


  
    #TODO:call add_assigmnet_request