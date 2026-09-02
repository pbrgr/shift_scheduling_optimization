"""Quality metrics computed from a finished schedule.

Works off the shift names in the schedule and the plain meaning of the config,
never off the model's helper variables — the same principle as the objective
test: a plan that only looks plausible should become visible here.
"""

from dataclasses import dataclass

from src.infrastructure.config import ScheduleConfig

Schedule = dict[int, list[str]]  #employee -> shift name per day


@dataclass(frozen=True)
class ScheduleMetrics:
    #per employee
    shifts_worked: dict[int, int]
    weekend_days_worked: dict[int, int]

    #coverage per working shift: (min, max) over all days
    coverage: dict[str, tuple[int, int]]

    #transitions
    rewarded_transitions: dict[tuple[str, str], int]
    forbidden_transitions: dict[tuple[str, str], int]

    #requests: (employee, day, shift) -> granted?
    requests_granted: dict[tuple[int, str, str], bool]

    fair_shifts: tuple[int, int]
    fair_weekend_days: int
    max_weekend_days_worked: int

    @property
    def workload_spread(self) -> tuple[int, int]:
        return min(self.shifts_worked.values()), max(self.shifts_worked.values())

    @property
    def weekend_spread(self) -> tuple[int, int]:
        values = self.weekend_days_worked.values()
        return min(values), max(values)

    @property
    def employees_outside_fair_band(self) -> list[int]:
        low, high = self.fair_shifts
        return [
            e for e, worked in self.shifts_worked.items()
            if worked < low or worked > high
        ]

    @property
    def employees_over_weekend_cap(self) -> list[int]:
        return [
            e for e, worked in self.weekend_days_worked.items()
            if worked > self.max_weekend_days_worked
        ]

    @property
    def total_rewarded_transitions(self) -> int:
        return sum(self.rewarded_transitions.values())

    @property
    def total_forbidden_transitions(self) -> int:
        return sum(self.forbidden_transitions.values())

    @property
    def requests_fulfilled(self) -> tuple[int, int]:
        return sum(self.requests_granted.values()), len(self.requests_granted)


def count_transitions(schedule: Schedule, prev_shift: str, next_shift: str) -> int:
    return sum(
        1
        for days in schedule.values()
        for d in range(len(days) - 1)
        if days[d] == prev_shift and days[d + 1] == next_shift
    )


def compute_metrics(schedule: Schedule, config: ScheduleConfig) -> ScheduleMetrics:
    free = set(config.free_shifts)

    #weighted: a composite day (e.g. 1N3N) fills several coverage slots
    shifts_worked = {
        e: sum(config.shift_load(shift) for shift in days)
        for e, days in schedule.items()
    }
    weekend_days_worked = {
        e: sum(1 for d in config.weekend_indices if days[d] not in free)
        for e, days in schedule.items()
    }

    coverage = {}
    for atomic in config.atomic_working_shifts:
        covering = set(config.shifts_covering(atomic))
        per_day = [
            sum(1 for days in schedule.values() if days[d] in covering)
            for d in range(config.num_days)
        ]
        coverage[atomic] = (min(per_day), max(per_day))

    rewarded, forbidden = {}, {}
    for prev_shift, next_shift, reward in config.transitions:
        target = forbidden if reward == 0 else rewarded
        target[prev_shift, next_shift] = count_transitions(
            schedule, prev_shift, next_shift
        )

    requests_granted = {
        (e, day, shift): schedule[e][config.days.index(day)] == shift
        for e, day, shift in config.all_requests
    }

    return ScheduleMetrics(
        shifts_worked=shifts_worked,
        weekend_days_worked=weekend_days_worked,
        coverage=coverage,
        rewarded_transitions=rewarded,
        forbidden_transitions=forbidden,
        requests_granted=requests_granted,
        fair_shifts=config.fair_shifts,
        fair_weekend_days=config.fair_weekend_days,
        max_weekend_days_worked=config.max_weekend_days_worked,
    )


def summary_lines(metrics: ScheduleMetrics, config: ScheduleConfig) -> list[str]:
    lines = []

    low, high = metrics.workload_spread
    outside = metrics.employees_outside_fair_band
    lines.append(
        "Shift slots per employee: %d to %d (fair band %d to %d, outside: %s)"
        % (low, high, *metrics.fair_shifts, len(outside) or "none")
    )

    we_low, we_high = metrics.weekend_spread
    over = metrics.employees_over_weekend_cap
    lines.append(
        "Weekend days per employee: %d to %d (fair %d, cap %d, over cap: %s)"
        % (we_low, we_high, metrics.fair_weekend_days,
           metrics.max_weekend_days_worked, len(over) or "none")
    )

    for shift, (c_min, c_max) in metrics.coverage.items():
        lines.append(
            "Coverage %s: %d to %d per day (allowed %d to %d)"
            % (shift, c_min, c_max, config.min_ee, config.max_ee)
        )

    lines.append(
        "Rewarded transitions: %d (%s)"
        % (
            metrics.total_rewarded_transitions,
            ", ".join(
                f"{p}→{n}: {c}"
                for (p, n), c in metrics.rewarded_transitions.items()
            ) or "none configured",
        )
    )
    lines.append(
        "Forbidden transitions present: %d" % metrics.total_forbidden_transitions
    )

    granted, total = metrics.requests_fulfilled
    lines.append("Requests fulfilled: %d of %d" % (granted, total))

    return lines
