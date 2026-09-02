# shift_scheduling_optimization

Shift scheduler built on the OR-Tools CP-SAT solver. Assigns employees to the
shifts `1N`, `2N`, `3N` and `R` (= day off) over a given period, honouring
coverage requirements and fixed assignments while trading off shift requests,
shift transitions and fairness.

## Running

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m src.app.generate_schedule
```

Run from the repository root. Each run writes to `output/`:

- `schedule.csv` — the raw schedule matrix
- `report.html` — quality stat tiles, the schedule as a colored roster grid
  (employees x days, weekend columns marked) and a per-employee table; opens
  directly from the file system, light and dark mode
- `logs/run_<timestamp>.log` — the run log, including the same quality metrics
  (coverage, fairness spreads, transition counts, fulfilled requests)

Tests run against small configs that solve in milliseconds. Besides the
constraints they recompute the objective from the finished schedule and compare
it with what the solver reports, which catches objective terms that do not
correspond to the plan they claim to score:

```bash
pip install -r requirements-dev.txt
pytest
```

`notebooks/check_scheduler_results.ipynb` inspects that CSV against the same
configuration the solver used.

## Layout

	core/ = pure domain and algorithm
	•	app/ = orchestration, workflows, use-cases
	•	frontend/ = UI code later
	•	infrastructure/ = database, file system, external APIs

| Module | Contents |
|---|---|
| `src/core/model.py` | decision variables, constraints, objective |
| `src/core/formatter.py` | translates days and shift names into model indices |
| `src/app/generate_schedule.py` | the use case: build, solve, report, persist |
| `src/infrastructure/config.py` | `ScheduleConfig` and the current `DEFAULT_CONFIG` |
| `src/infrastructure/csv_writer.py` | schedule export |
| `src/infrastructure/logger.py` | file and console logging |

`test/core/shift_scheduling_sat.py` is the unmodified OR-Tools example this
project started from, kept as a reference.

## Configuration

Everything lives in `DEFAULT_CONFIG` in `src/infrastructure/config.py`: the
period, employees, shifts, coverage bounds, weights and the individual
assignments and requests.

Days are `"DD.MM"` strings plus a separate `year`. Weekends are **derived from
the calendar** rather than maintained by hand, so they cannot drift from the
dates. The fairness targets are derived too: the fair weekend share and the
fair band of shifts per employee both follow from the period, `min_ee` and the
number of working shifts.

Assignments come in four flavours, each either hard or soft:

| Field | Effect |
|---|---|
| `dayoff_assignments` | hard, `(employee, day)` |
| `fixed_assignments` | hard, `(employee, day, shift)` |
| `recurring_assignments` | hard, `(employee, weekday, shift)`, every matching week |
| `dayoff_requests` / `assignment_requests` / `recurring_requests` | the soft counterparts, weighted by `weight_shift_request` |

Recurring rules cover the standing cases, e.g. an employee who is away on
education every wednesday:

```python
from src.infrastructure.config import WEDNESDAY

recurring_assignments=[(1, WEDNESDAY, "R")]
```

The configuration is validated before the model is built, and every problem is
reported at once rather than one per run:

```
ValueError: invalid schedule configuration:
  - min_ee 6 is above max_ee 3
  - fixed assignment for unknown employee 99
  - fixed assignment for employee 99 on unknown day '15.07'
```

That covers unknown employees, days and shifts, duplicates, coverage bounds the
wrong way round, weekdays outside the week, and hard rules contradicting each
other on the same day — cases the solver would otherwise either crash on with a
bare `KeyError` or report as an unexplained `INFEASIBLE`.

The rest shift is named via `rest_shift` rather than taken from the end of
`shifts`, so reordering the list cannot silently turn a working shift into the
one that means "not working".

To try a variant without touching the defaults:

```python
from dataclasses import replace
from src.app.generate_schedule import generate_schedule
from src.infrastructure.config import DEFAULT_CONFIG

generate_schedule(replace(DEFAULT_CONFIG, min_ee=4), output_path="output_min4")
```

## Model

Hard constraints:

- exactly one shift per employee and day
- `min_ee` to `max_ee` employees per working shift and day (`R` is not covered)
- fixed assignments and fixed days off
- transitions with reward `0` are forbidden outright
- at most `max_weekend_work_ratio` of the weekend days per employee

Soft terms, weighted into the objective:

- shift requests (`weight_shift_request`, negative — requests are rewards, so
  they have to be phrased as something the employee wants)
- rewarded shift transitions
- weekend fairness: penalty per weekend day below the fair share
- workload fairness: penalty per shift outside the fair band

The transition rewards make proving optimality expensive, so the solver is
capped at `max_solve_seconds` and normally returns `FEASIBLE` with a small
remaining gap rather than `OPTIMAL`.
