# WIS BEGIN
import sys
import os
# - PYTHONPATH wird ignoriert
# - CurrentWorkingDir setzen funktioniert nicht
# - . in ._pth ist offenbar nicht CurrentWorkingDir
# - geht, aber current-working-dir nutzen wir für "base" sys.path.append(os.getcwd())
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# WIS END

from absl import app
from absl import flags

from ortools.sat.python import cp_model
from formatter import formatter
from logger import setup_logging
import numpy as np
import csv

# WIS BEGIN
#import os

#import sys

"""
CHANGES:
  - parameter.tage[].tag -> parameter.tage[].datum
"""

raw_in = sys.stdin.buffer.read().decode("utf-8")

print("raw_in len: ", len(raw_in), file=sys.stderr)
print("raw_in starts with", raw_in[:200], file=sys.stderr)

import json
json_in = json.loads(raw_in)

# parameter.ressourcen
ressourcen = json_in["parameter"]["ressourcen"]
employees  = np.arange(1, len(ressourcen) + 1)

for i, res in zip(employees, ressourcen):
    print(f'Ressource ID {i}: {res["pofCode"]}', file=sys.stderr)

# parameter.tage
from datetime import datetime, timedelta

days      = []
weekends  = []

for item in json_in["parameter"]["tage"]:
    dt = datetime.strptime(item["datum"], "%Y-%m-%d")
    #tag_formatted = dt.strftime("%d.%m.%Y") --> error ValueError: '01.03' is not in list --> fa = formatter.get_fixed_assignment(ee, day, "R")
    tag_formatted = dt.strftime("%d.%m")
    
    # days
    days.append(tag_formatted)
    
    # weekends
    weekends.append(1 if item["wochenende"] else 0)

print("Employees:", employees, file=sys.stderr)
print("Days:", days, file=sys.stderr)
print("Weekends:", weekends, file=sys.stderr)
# WIS END


output_path = 'output'

"""
-> per input
employees = np.arange(1, 31)
"""

"""
-> per input
days = ["28.02",
 "01.03","02.03","03.03","04.03","05.03","06.03","07.03","08.03","09.03","10.03",
 "11.03","12.03","13.03","14.03","15.03","16.03","17.03","18.03","19.03","20.03",
 "21.03","22.03","23.03","24.03","25.03","26.03","27.03","28.03","29.03","30.03","31.03"]
"""

"""
-> per input
weekends = [1,
 1,0,0,0,0,0,1,1,0,0,
 0,0,0,1,1,0,0,0,0,0,
 1,1,0,0,0,0,0,1,1,0,0]
"""
shifts = ["1N", "2N", "3N", "R"]

min_ee = 3 #min ee per shift
max_ee = 5

weight_shift_request = -2 #neg means that the requests always need to be formulated in a positive way
#so that the ee wants that specific shift

employees_dayoff_assignment = [
# WIS BEGIN
#    (4, "01.03"),
#    (9, "16.03")
# WIS END
]

employees_fixed_assignment = [
# WIS BEGIN
#    (4, "06.03", "1N")
# WIS END
]

employees_dayoff_requests = [
# WIS BEGIN
#    (1, "01.03"),
#    (5, "16.03"),
#    (7, "16.03")
# WIS END
]

employees_assignment_requests = [
# WIS BEGIN
#    (1, "02.03", "2N")
# WIS END
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
    num_days = len(days)
    num_employees = len(employees)
    num_shifts = len(shifts)

    logger.info("Starting schedule generation")
    logger.info("Employees: %d", len(employees))
    logger.info("Days: %d", len(days))
    logger.info("Shifts: %s", shifts)
    logger.info("Min employees per shift: %d", min_ee)
    logger.info("Max employees per shift: %d", max_ee)

    model = cp_model.CpModel()
    formatter = formatter(shifts=shifts, days= days, weight_requests=weight_shift_request)

    logger.info("Creating decision variables")

    # create work variable with domain {0, 1}
    work = {}
    for e in employees:
        for s in range(num_shifts):
            for d in range(num_days):
                work[e, s, d] = model.new_bool_var(f"work{e}_{s}_{d}")

    # Linear terms of the objective in a minimization context.
    obj_int_vars: list[cp_model.IntVar] = []
    obj_int_coeffs: list[int] = []
    obj_bool_vars: list[cp_model.BoolVarT] = []
    obj_bool_coeffs: list[int] = []

    # for each ee only one shift per day
    logger.info("Adding one-shift-per-day constraints")
    for e in employees:
        for d in range(num_days):
            model.add_exactly_one(work[e, s, d] for s in range(num_shifts))

    #Cover constraints:
    logger.info("Adding coverage constraints")
    for s in range(num_shifts-1): #need to not take R into account
        for d in range(num_days):
            assigned = [work[e, s, d] for e in employees]
            model.add(sum(assigned) >= min_ee)
            model.add(sum(assigned) <= max_ee)

    #Reward Good Transitions:
    for prev_shift, next_shift, reward in transitions:
        prev_shift, next_shift, reward = formatter.reward_transitions(prev_shift,next_shift,reward)

        for e in employees:
            for d in range(num_days-1):
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

    working_shift_indices = range(num_shifts - 1)  # exclude R

    total_weekends = sum(weekends)
    weekend_indices = [i for i, v in enumerate(weekends) if v == 1]
    min_weekend_days_off = 5/8
    max_weekend_days_worked = int(total_weekends*min_weekend_days_off) #still need to adapt for actual amount of weekend days
    
    #TODO: Add min weekend days worked, so its fair
    #min_weekend_days_worked = 

    for ee in range(num_employees):
        weekend_work = []
        for d in weekend_indices:
            worked_that_day = model.new_bool_var(f"weekend_work_{e}_{d}")
            model.add_max_equality(
                worked_that_day,
                [work[e, s, d] for s in working_shift_indices],
            )
            weekend_work.append(worked_that_day)

        #TODO: maybe add with a weight
        model.add(sum(weekend_work)<=max_weekend_days_worked)


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
    
    # WIS BEGIN
    #status = solver.solve(model, solution_printer)
    status = solver.solve(model)
    # WIS END
    
    logger.info("Solver finished with status: %s", solver.StatusName(status))

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # WIS BEGIN
        
        """
        {
          "Version": "1",
          "dienstEinteilungen": [
            { "zeitStart": "2026-03-01T18:00:00.000", "pofID": "FfekLLpFP00_1XO", "dienstCodeID": "0386188683F74415AE01334FE54BE1B5" },
            { "zeitStart": "2026-03-02T18:00:00.000", "pofID": "FfekLLpFP00_1XO", "dienstCodeID": "55BDA61D1CC54D35B468A301E153774D" },
            ...
          ]
        }
        """
        
        json_out = {
            "version": "1",
            "solver": {
                "status": solver.StatusName(status)
            },
            "dienstEinteilungen": []
        }
        
        for e, res in zip(employees, ressourcen):
            for d, tag in enumerate(json_in["parameter"]["tage"]):
                dienstEinteilung = {
                    "pofID":         res["pofID"],
                    "pofCode":       res["pofCode"],
                    "zeitStart":     tag["datum"],
                    "needtochange1": get_assigned_shift_name(solver, work, e, d, shifts)
                }
                
                json_out["dienstEinteilungen"].append(dienstEinteilung)
        
        print(json.dumps(json_out));
        
        os.makedirs("output", exist_ok=True)
        
        with open("output/schedule.json", "w", encoding="utf-8") as f:
            json.dump(json_out, f, ensure_ascii=False, indent=2)
        
        # WIS END
        
        csv_path = os.path.join(output_path, "schedule.csv")
        with open(csv_path, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["employee"] + [f"day_{d}" for d in days])

            for e in employees:
                row = [e]
                for d in range(num_days):
                    row.append(get_assigned_shift_name(solver, work, e, d, shifts))
                writer.writerow(row)

        print()
        # header = "          "
        # for w in range(num_weeks):
        #     header += "M T W T F S S "
        # print(header)
        for e in employees:
            schedule = ""
            for d in range(num_days):
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
