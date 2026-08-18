from dataclasses import dataclass, field
from datetime import date

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


def to_dates(days: list[str], year: int) -> list[date]:
    #days are "DD.MM" without a year, so the year is supplied separately.
    #a month going backwards means the period crossed into the next year.
    dates = []
    current_year = year
    previous_month = None

    for day in days:
        d, m = (int(part) for part in day.split("."))
        if previous_month is not None and m < previous_month:
            current_year += 1
        dates.append(date(current_year, m, d))
        previous_month = m

    return dates


def weekend_flags(days: list[str], year: int) -> list[int]:
    #saturday=5, sunday=6
    return [1 if d.weekday() >= 5 else 0 for d in to_dates(days, year)]


@dataclass(frozen=True)
class ScheduleConfig:
    year: int
    days: list[str]
    employees: list[int]
    shifts: list[str]

    min_ee: int #min ee per shift
    max_ee: int

    #neg means that the requests always need to be formulated in a positive way
    #so that the ee wants that specific shift
    weight_shift_request: int
    weight_weekend_fairness: int #pos, penalty per weekend day below the fair share
    weight_workload_fairness: int #pos, penalty per shift outside the fair band

    max_solve_seconds: float

    dayoff_assignments: list[tuple[int, str]] #hard, (employee, day)
    fixed_assignments: list[tuple[int, str, str]] #hard, (employee, day, shift)
    dayoff_requests: list[tuple[int, str]] #soft, (employee, day)
    assignment_requests: list[tuple[int, str, str]] #soft, (employee, day, shift)

    #(previous_shift, next_shift, reward), 0 means forbidden
    transitions: list[tuple[str, str, int]]

    #rules that repeat every week, e.g. (1, WEDNESDAY, "R") for an employee
    #who is away on education every wednesday
    recurring_assignments: list[tuple[int, int, str]] = field(default_factory=list)
    recurring_requests: list[tuple[int, int, str]] = field(default_factory=list)

    #share of the weekend days an employee may work at most
    max_weekend_work_ratio: float = 5 / 8

    #CP-SAT detects and breaks symmetries itself at its default of 2. Measured
    #over 3 runs each on DEFAULT_CONFIG, that costs more search time than it
    #saves here: level 2 landed at a gap of 38-43, levels 0 and 1 at 28-32.
    symmetry_level: int = 1

    def days_on_weekday(self, weekday: int) -> list[str]:
        return [
            day
            for day, d in zip(self.days, to_dates(self.days, self.year))
            if d.weekday() == weekday
        ]

    def _expand(self, rules) -> list[tuple[int, str, str]]:
        return [
            (employee, day, shift)
            for employee, weekday, shift in rules
            for day in self.days_on_weekday(weekday)
        ]

    @property
    def all_fixed_assignments(self) -> list[tuple[int, str, str]]:
        #days off are just a fixed assignment to the last shift
        return (
            [(e, day, self.shifts[-1]) for e, day in self.dayoff_assignments]
            + list(self.fixed_assignments)
            + self._expand(self.recurring_assignments)
        )

    @property
    def all_requests(self) -> list[tuple[int, str, str]]:
        return (
            [(e, day, self.shifts[-1]) for e, day in self.dayoff_requests]
            + list(self.assignment_requests)
            + self._expand(self.recurring_requests)
        )

    def conflicting_assignments(self) -> list[tuple[int, str, tuple[str, ...]]]:
        #two hard rules demanding different shifts on the same day cannot both
        #hold, and the solver would only report a bare INFEASIBLE
        by_day: dict[tuple[int, str], set[str]] = {}
        for employee, day, shift in self.all_fixed_assignments:
            by_day.setdefault((employee, day), set()).add(shift)

        return [
            (employee, day, tuple(sorted(shifts)))
            for (employee, day), shifts in by_day.items()
            if len(shifts) > 1
        ]

    @property
    def num_days(self) -> int:
        return len(self.days)

    @property
    def num_employees(self) -> int:
        return len(self.employees)

    @property
    def num_shifts(self) -> int:
        return len(self.shifts)

    @property
    def working_shift_indices(self) -> range:
        return range(self.num_shifts - 1) #exclude R

    @property
    def weekends(self) -> list[int]:
        #derived from the calendar, so it can never drift from the dates
        return weekend_flags(self.days, self.year)

    @property
    def weekend_indices(self) -> list[int]:
        return [i for i, v in enumerate(self.weekends) if v == 1]

    @property
    def max_weekend_days_worked(self) -> int:
        return int(len(self.weekend_indices) * self.max_weekend_work_ratio)

    @property
    def fair_weekend_days(self) -> int:
        #fair share = weekend slots at minimum coverage, spread over all ee
        slots = (
            len(self.weekend_indices)
            * self.min_ee
            * len(self.working_shift_indices)
        )
        return slots // self.num_employees

    @property
    def fair_shifts(self) -> tuple[int, int]:
        #fair band = shifts at minimum coverage, spread over all ee
        slots = self.num_days * self.min_ee * len(self.working_shift_indices)
        return slots // self.num_employees, -(-slots // self.num_employees)


DEFAULT_CONFIG = ScheduleConfig(
    year=2026,
    days=["28.02",
     "01.03","02.03","03.03","04.03","05.03","06.03","07.03","08.03","09.03","10.03",
     "11.03","12.03","13.03","14.03","15.03","16.03","17.03","18.03","19.03","20.03",
     "21.03","22.03","23.03","24.03","25.03","26.03","27.03","28.03","29.03","30.03","31.03"],
    employees=list(range(1, 31)),
    shifts=["1N", "2N", "3N", "R"],

    min_ee=3,
    max_ee=5,

    weight_shift_request=-2,
    weight_weekend_fairness=3,
    weight_workload_fairness=8,

    max_solve_seconds=120.0,

    dayoff_assignments=[
        (4, "01.03"),
        (9, "16.03"),
    ],
    fixed_assignments=[
        (4, "06.03", "1N"),
    ],
    dayoff_requests=[
        (1, "01.03"),
        (5, "16.03"),
        (7, "16.03"),
    ],
    assignment_requests=[
        (1, "02.03", "2N"),
    ],

    transitions=[
        ("2N", "1N", -4),
        ("1N", "3N", -4),
        ("3N", "R", -4),
        ("3N", "1N", 0),
    ],
)
