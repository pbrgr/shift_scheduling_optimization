"""Standalone HTML report: quality stat tiles, the schedule as a colored
roster grid (employees x days, in the spirit of the Avanti Planblatt), and a
per-employee table view.

No dependencies — plain HTML/CSS written by stdlib code, so the report opens
from the file system anywhere. Shift colors are the first three slots of the
validated default categorical palette (light and dark mode both validated);
the rest shift is deliberately recessive since it encodes absence. Every cell
carries its shift code as text, so identity never rides on color alone.
"""

import html
import os
from datetime import date

from src.core.metrics import ScheduleMetrics, summary_lines
from src.infrastructure.config import ScheduleConfig, to_dates

#categorical slots 1-3 (blue, orange, aqua): light / dark steps
SHIFT_COLORS = [
    ("#2a78d6", "#3987e5"),
    ("#eb6834", "#d95926"),
    ("#1baf7a", "#199e70"),
]

WEEKDAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

STYLE = """
:root {
  color-scheme: light dark;
  --surface: #fcfcfb; --surface-2: #f1f0ee; --weekend: #e7e6e2;
  --ink: #0b0b0b; --ink-2: #52514e; --line: #dddcd8;
%(light_slots)s
}
@media (prefers-color-scheme: dark) {
  :root {
    --surface: #1a1a19; --surface-2: #232322; --weekend: #2e2e2c;
    --ink: #ffffff; --ink-2: #c3c2b7; --line: #3a3a38;
%(dark_slots)s
  }
}
body { background: var(--surface); color: var(--ink);
  font: 14px/1.45 system-ui, sans-serif; margin: 24px; }
h1 { font-size: 20px; margin: 0 0 2px; }
.sub { color: var(--ink-2); margin: 0 0 20px; }
.tiles { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
.tile { background: var(--surface-2); border-radius: 8px; padding: 10px 16px;
  min-width: 130px; }
.tile b { display: block; font-size: 20px; font-variant-numeric: tabular-nums; }
.tile span { color: var(--ink-2); font-size: 12px; }
.tile .flag { color: var(--ink); font-size: 12px; font-weight: 600; }
.legend { display: flex; gap: 16px; margin: 0 0 8px; color: var(--ink-2);
  font-size: 12px; align-items: center; }
.chip { display: inline-block; width: 10px; height: 10px; border-radius: 3px;
  margin-right: 5px; vertical-align: -1px; }
.grid { border-collapse: separate; border-spacing: 2px 2px; }
.grid th { font-weight: 400; font-size: 11px; color: var(--ink-2);
  padding: 1px 3px; text-align: center; }
.grid th.we { font-weight: 700; color: var(--ink); }
.grid td.name { text-align: right; padding-right: 8px; white-space: nowrap;
  font-size: 12px; }
.grid td.c { width: 30px; min-width: 30px; height: 22px; text-align: center;
  font-size: 11px; border-radius: 4px; background: var(--surface-2); }
.grid td.we { background: var(--weekend); }
.grid td.s { color: var(--ink); font-weight: 600;
  border-left: 3px solid var(--sc); background:
  color-mix(in srgb, var(--sc) 22%%, var(--surface)); }
.grid td.s2 { color: var(--ink); font-weight: 600; }
.grid td.rest { color: var(--ink-2); }
table.plain { border-collapse: collapse; margin-top: 8px; }
table.plain th, table.plain td { padding: 3px 10px; text-align: right;
  font-variant-numeric: tabular-nums; border-bottom: 1px solid var(--line); }
table.plain th { color: var(--ink-2); font-weight: 400; font-size: 12px; }
table.plain td:first-child, table.plain th:first-child { text-align: left; }
h2 { font-size: 15px; margin: 28px 0 6px; }
ul.checks { color: var(--ink-2); font-size: 13px; padding-left: 18px; }
"""


def _tile(value: str, label: str, flag: str = "") -> str:
    extra = f'<div class="flag">⚠ {html.escape(flag)}</div>' if flag else ""
    return (
        f'<div class="tile"><b>{html.escape(value)}</b>'
        f"<span>{html.escape(label)}</span>{extra}</div>"
    )


def _shift_style(config: ScheduleConfig) -> tuple[dict[str, int], str, str]:
    #only atomic shifts get a colour slot; composites are rendered as a
    #split cell of their parts, so no fourth categorical colour is needed
    #(the palette trio is validated all-pairs, a fourth slot would not be)
    working = list(config.atomic_working_shifts)
    slot_of = {shift: i for i, shift in enumerate(working[:3])}
    light = "".join(
        f"  --s{i}: {SHIFT_COLORS[i][0]};\n" for i in range(len(slot_of))
    )
    dark = "".join(
        f"    --s{i}: {SHIFT_COLORS[i][1]};\n" for i in range(len(slot_of))
    )
    return slot_of, light, dark


def _grid(schedule, config: ScheduleConfig, slot_of) -> str:
    dates = to_dates(config.days, config.year)
    weekend = set(config.weekend_indices)

    head = "<tr><th></th>" + "".join(
        '<th class="%s">%s<br>%s</th>'
        % ("we" if d in weekend else "",
           WEEKDAY_NAMES[dt.weekday()], dt.strftime("%d.%m"))
        for d, dt in enumerate(dates)
    ) + "</tr>"

    rows = []
    for e, days in schedule.items():
        cells = []
        for d, shift in enumerate(days):
            classes = ["c"] + (["we"] if d in weekend else [])
            style = ""
            parts = config.composite_shifts.get(shift, ())
            if shift in slot_of:
                classes.append("s")
                style = f' style="--sc: var(--s{slot_of[shift]})"'
            elif parts and all(p in slot_of for p in parts):
                #composite day: split the cell between its parts' colours
                classes.append("s2")
                stops = ", ".join(
                    "color-mix(in srgb, var(--s%d) 22%%, var(--surface)) "
                    "%d%% %d%%"
                    % (slot_of[p], i * 100 // len(parts),
                       (i + 1) * 100 // len(parts))
                    for i, p in enumerate(parts)
                )
                style = (
                    f' style="background: linear-gradient(90deg, {stops});'
                    f' border-left: 3px solid var(--s{slot_of[parts[0]]})"'
                )
            else:
                classes.append("rest")
            tip = f"MA {e} — {config.days[d]} — {shift}"
            cells.append(
                '<td class="%s"%s title="%s">%s</td>'
                % (" ".join(classes), style, html.escape(tip), html.escape(shift))
            )
        rows.append(
            f'<tr><td class="name">MA {e}</td>' + "".join(cells) + "</tr>"
        )

    return f'<table class="grid">{head}{"".join(rows)}</table>'


def _employee_table(metrics: ScheduleMetrics) -> str:
    low, high = metrics.fair_shifts
    rows = "".join(
        "<tr><td>MA %d</td><td>%d</td><td>%d</td><td>%s</td></tr>"
        % (
            e,
            worked,
            metrics.weekend_days_worked[e],
            "außerhalb" if e in metrics.employees_outside_fair_band else "im Band",
        )
        for e, worked in metrics.shifts_worked.items()
    )
    return (
        '<table class="plain"><tr><th>Mitarbeiter:in</th><th>Schicht-Slots</th>'
        f"<th>Wochenendtage</th><th>Fair-Band {low}–{high}</th></tr>{rows}</table>"
    )


def render_report(
        schedule,
        config: ScheduleConfig,
        metrics: ScheduleMetrics,
        solver_status: str,
        objective: float,
        gap: float,
) -> str:
    slot_of, light_slots, dark_slots = _shift_style(config)

    granted, total = metrics.requests_fulfilled
    low, high = metrics.workload_spread
    we_low, we_high = metrics.weekend_spread

    tiles = [
        _tile(solver_status, "Solver-Status"),
        _tile("%.0f" % objective, "Objective (Lücke %.0f)" % gap),
        _tile(
            str(metrics.understaffed_slots), "fehlende Besetzung (Slots)",
            flag="Mindestbestand verletzt" if metrics.understaffed_slots else "",
        ),
        _tile(str(metrics.total_rewarded_transitions), "belohnte Übergänge"),
        _tile(
            str(metrics.total_forbidden_transitions), "verbotene Übergänge",
            flag="sollte 0 sein" if metrics.total_forbidden_transitions else "",
        ),
        _tile(f"{granted}/{total}", "Wünsche erfüllt"),
    ]
    if metrics.shifts_without_leader is not None:
        tiles.append(_tile(
            str(metrics.shifts_without_leader), "Schichten ohne Schichtleiter",
            flag="Anforderung verletzt" if metrics.shifts_without_leader else "",
        ))
    tiles += [
        _tile(
            f"{low}–{high}", "Schicht-Slots pro MA",
            flag="%d MA außerhalb" % len(metrics.employees_outside_fair_band)
            if metrics.employees_outside_fair_band else "",
        ),
        _tile(
            f"{we_low}–{we_high}", "Wochenendtage pro MA",
            flag="%d MA über Cap" % len(metrics.employees_over_weekend_cap)
            if metrics.employees_over_weekend_cap else "",
        ),
    ]

    legend_items = [
        f'<span><i class="chip" style="background: var(--s{i})"></i>'
        f"{html.escape(shift)}</span>"
        for shift, i in slot_of.items()
    ]
    for name, parts in config.composite_shifts.items():
        if all(p in slot_of for p in parts):
            stops = ", ".join(
                "var(--s%d) %d%% %d%%"
                % (slot_of[p], i * 100 // len(parts), (i + 1) * 100 // len(parts))
                for i, p in enumerate(parts)
            )
            legend_items.append(
                f'<span><i class="chip" style="background:'
                f' linear-gradient(90deg, {stops})"></i>'
                f"{html.escape(name)} ({'+'.join(parts)})</span>"
            )
    if config.compensation_shift:
        legend_items.append(
            '<span><i class="chip" style="background: var(--surface-2);'
            ' border: 1px solid var(--line)"></i>'
            f"{html.escape(config.compensation_shift)} (Kompensation)</span>"
        )
    legend_items.append(
        '<span><i class="chip" style="background: var(--surface-2);'
        ' border: 1px solid var(--line)"></i>'
        f"{html.escape(config.rest_shift)} (frei)</span>"
    )
    legend_items.append("<span>graue Spalten = Wochenende</span>")
    legend = '<div class="legend">' + "".join(legend_items) + "</div>"

    checks = "".join(
        f"<li>{html.escape(line)}</li>" for line in summary_lines(metrics, config)
    )

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>Schichtplan {config.days[0]}–{config.days[-1]} ({config.year})</title>
<style>{STYLE % {"light_slots": light_slots, "dark_slots": dark_slots}}</style>
</head><body>
<h1>Schichtplan {html.escape(config.days[0])}–{html.escape(config.days[-1])}</h1>
<p class="sub">{config.year} · {config.num_employees} Mitarbeitende ·
{config.num_days} Tage · erzeugt am {date.today().isoformat()}</p>
<div class="tiles">{"".join(tiles)}</div>
{legend}
{_grid(schedule, config, slot_of)}
<h2>Kennzahlen im Detail</h2>
<ul class="checks">{checks}</ul>
<h2>Pro Mitarbeiter:in</h2>
{_employee_table(metrics)}
</body></html>
"""


def write_report(output_path: str, **kwargs) -> str:
    os.makedirs(output_path, exist_ok=True)
    report_path = os.path.join(output_path, "report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(render_report(**kwargs))
    return report_path
