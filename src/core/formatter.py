import numpy as np
from ortools.sat.python import cp_model


class formatter:
    def __init__(self, shifts, weight_requests):
        self.shifts = shifts
        self.weight_requests = weight_requests
    
    def get_fixed_assignment(
        self,
        employee: int,
        day: int,
        shift: str,
    )->tuple[int, int, int]:
        shift_number = self.shifts.index(shift)

        return employee, shift_number, day

    def get_employee_requests(
        self,
        employee: int,
        day: int,
        shift: str
    )->tuple[int, int, int, int]:
        shift_number = self.shifts.index(shift)

        return employee, shift_number, day, self.weight_requests
    
    #TODO: add logic to add fixed assignments for specific days

    def reward_transitions(
            self,
            prev_shift: str,
            next_shift: str,
            reward: int
    )->tuple[int, int, int]:
        prev_shift_number = self.shifts.index(prev_shift)
        next_shift_number = self.shifts.index(next_shift)

        return prev_shift_number, next_shift_number, reward
#e.g. ee 1 every wednesday needs to have the day off for education
