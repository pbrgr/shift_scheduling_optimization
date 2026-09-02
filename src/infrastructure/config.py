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

    #the shift that means "not working". named rather than positional, so
    #reordering `shifts` cannot silently turn a working shift into the rest one
    rest_shift: str = "R"

    #compensation day after a night duty. counts as a free day like the rest
    #shift, but is only allowed right after one of `compensation_follows`
    #("Komp = Kompensation Nachtdienst, folgt auf ein 3N")
    compensation_shift: str | None = None
    compensation_follows: tuple[str, ...] = ()

    #shifts that mean working two shifts on the same day, e.g. "1N3N" is a
    #morning and a night shift. they count towards the coverage of each part.
    composite_shifts: dict[str, tuple[str, ...]] = field(default_factory=dict)

    #share of the weekend days an employee may work at most.
    #KAPO TG, "Ablauf/Regeln Dienstplanung KNZ" (26.11.2026), Schritt 2:
    #5 of 8 weekend days per month are FREE, so at most 3 of 8 are worked
    max_weekend_work_ratio: float = 3 / 8

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
        #days off are just a fixed assignment to the rest shift
        return (
            [(e, day, self.rest_shift) for e, day in self.dayoff_assignments]
            + list(self.fixed_assignments)
            + self._expand(self.recurring_assignments)
        )

    @property
    def all_requests(self) -> list[tuple[int, str, str]]:
        return (
            [(e, day, self.rest_shift) for e, day in self.dayoff_requests]
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

    def _duplicates(self, values) -> list:
        seen, duplicates = set(), []
        for v in values:
            if v in seen and v not in duplicates:
                duplicates.append(v)
            seen.add(v)
        return duplicates

    def problems(self) -> list[str]:
        #collected rather than raised one by one, so a broken config can be
        #fixed in one go instead of one message per run
        found = []

        if not self.days:
            found.append("days is empty")
        if not self.employees:
            found.append("employees is empty")
        if self.rest_shift not in self.shifts:
            found.append(
                f"rest_shift {self.rest_shift!r} is not one of shifts {self.shifts}"
            )
        elif len(self.shifts) < 2:
            found.append("shifts needs at least one working shift besides the rest shift")

        if self.compensation_shift is not None:
            if self.compensation_shift not in self.shifts:
                found.append(
                    f"compensation_shift {self.compensation_shift!r} is not one of shifts"
                )
            if self.compensation_shift == self.rest_shift:
                found.append("compensation_shift must differ from rest_shift")
            if not self.compensation_follows:
                found.append(
                    "compensation_shift is set but compensation_follows is empty"
                )
            for shift in self.compensation_follows:
                if shift not in self.shifts:
                    found.append(
                        f"compensation_follows refers to unknown shift {shift!r}"
                    )
        elif self.compensation_follows:
            found.append("compensation_follows is set but compensation_shift is not")

        for name, parts in self.composite_shifts.items():
            if name not in self.shifts:
                found.append(f"composite shift {name!r} is not one of shifts")
            if len(parts) < 2:
                found.append(f"composite shift {name!r} needs at least two parts")
            for part in parts:
                if part not in self.shifts:
                    found.append(
                        f"composite shift {name!r} refers to unknown shift {part!r}"
                    )
                elif part in self.free_shifts or part in self.composite_shifts:
                    found.append(
                        f"composite shift {name!r} part {part!r} must be an "
                        "atomic working shift"
                    )

        for label, values in (("days", self.days), ("employees", self.employees),
                              ("shifts", self.shifts)):
            for duplicate in self._duplicates(values):
                found.append(f"{label} contains {duplicate!r} more than once")

        if self.min_ee > self.max_ee:
            found.append(f"min_ee {self.min_ee} is above max_ee {self.max_ee}")
        if self.min_ee < 0:
            found.append(f"min_ee {self.min_ee} is negative")
        if self.max_solve_seconds <= 0:
            found.append(f"max_solve_seconds {self.max_solve_seconds} is not positive")

        known_employees, known_days = set(self.employees), set(self.days)
        known_shifts = set(self.shifts)

        for label, rules in (("fixed assignment", self.all_fixed_assignments),
                             ("request", self.all_requests)):
            for employee, day, shift in rules:
                if employee not in known_employees:
                    found.append(f"{label} for unknown employee {employee}")
                if day not in known_days:
                    found.append(f"{label} for employee {employee} on unknown day {day!r}")
                if shift not in known_shifts:
                    found.append(f"{label} for employee {employee} on {day} "
                                 f"asks for unknown shift {shift!r}")

        for label, rules in (("recurring assignment", self.recurring_assignments),
                             ("recurring request", self.recurring_requests)):
            for employee, weekday, _ in rules:
                if not 0 <= weekday <= 6:
                    found.append(f"{label} for employee {employee} has weekday "
                                 f"{weekday}, expected 0 (monday) to 6 (sunday)")

        for prev_shift, next_shift, _ in self.transitions:
            for shift in (prev_shift, next_shift):
                if shift not in known_shifts:
                    found.append(f"transition refers to unknown shift {shift!r}")

        found += [
            f"employee {employee} on {day} demanded as {'/'.join(shifts)}"
            for employee, day, shifts in self.conflicting_assignments()
        ]

        return found

    def validate(self) -> None:
        found = self.problems()
        if found:
            raise ValueError(
                "invalid schedule configuration:\n  - " + "\n  - ".join(found)
            )

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
    def rest_shift_index(self) -> int:
        return self.shifts.index(self.rest_shift)

    @property
    def free_shifts(self) -> tuple[str, ...]:
        #every shift name that means a free day
        if self.compensation_shift is None:
            return (self.rest_shift,)
        return (self.rest_shift, self.compensation_shift)

    @property
    def working_shift_indices(self) -> tuple[int, ...]:
        #includes composite shifts: a 1N3N day is a worked day
        return tuple(
            s for s in range(self.num_shifts)
            if self.shifts[s] not in self.free_shifts
        )

    @property
    def atomic_working_shifts(self) -> tuple[str, ...]:
        #the shifts that carry a coverage requirement of their own
        return tuple(
            self.shifts[s] for s in self.working_shift_indices
            if self.shifts[s] not in self.composite_shifts
        )

    def shift_load(self, shift: str) -> int:
        #how many coverage slots one day of this shift fills
        if shift in self.composite_shifts:
            return len(self.composite_shifts[shift])
        return 0 if shift in self.free_shifts else 1

    def shifts_covering(self, atomic: str) -> tuple[str, ...]:
        #the atomic shift itself plus every composite that contains it
        return (atomic,) + tuple(
            name for name, parts in self.composite_shifts.items()
            if atomic in parts
        )

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
            * len(self.atomic_working_shifts)
        )
        return slots // self.num_employees

    @property
    def fair_shifts(self) -> tuple[int, int]:
        #fair band = coverage slots at minimum coverage, spread over all ee.
        #a composite shift fills several slots in one day (see shift_load)
        slots = self.num_days * self.min_ee * len(self.atomic_working_shifts)
        return slots // self.num_employees, -(-slots // self.num_employees)


DEFAULT_CONFIG = ScheduleConfig(
    year=2026,
    days=["28.02",
     "01.03","02.03","03.03","04.03","05.03","06.03","07.03","08.03","09.03","10.03",
     "11.03","12.03","13.03","14.03","15.03","16.03","17.03","18.03","19.03","20.03",
     "21.03","22.03","23.03","24.03","25.03","26.03","27.03","28.03","29.03","30.03","31.03"],
    employees=list(range(1, 31)),
    #KNZ codes: Früh, Spät, Nacht, Früh+Nacht am selben Tag, Kompensation, Ruhe
    shifts=["1N", "2N", "3N", "1N3N", "Komp", "R"],
    compensation_shift="Komp",
    compensation_follows=("3N", "1N3N"),
    composite_shifts={"1N3N": ("1N", "3N")},

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
        #standard sequence per KNZ document: 2N, 1N3N, Komp, Ruhetag
        ("2N", "1N3N", -4),
        ("1N3N", "Komp", -4),
        ("Komp", "R", -4),
        #documented second-priority sequences: "2N, 2N, 1N3N" / "2N, 1N3N, 3N"
        ("2N", "2N", -2),
        ("1N3N", "3N", -2),
        #a night part ends 06:30, a morning shift starts 06:00: forbidden
        ("3N", "1N", 0),
        ("3N", "1N3N", 0),
        ("1N3N", "1N", 0),
        ("1N3N", "1N3N", 0),
    ],
)
