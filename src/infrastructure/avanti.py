"""Translates between the Avanti DPService JSON contract and ScheduleConfig.

The input format is the de-facto contract observed in the DPAutoGen examples
(there is no version field yet). The reader is deliberately tolerant — it
touches only the fields it needs and ignores the rest ($id, @xdata.type,
colours, ...) — but loud: anything missing or unexpected raises AvantiError
with a plain message instead of producing a plausible but wrong plan.

Documented assumptions, to be confirmed with the DPService owner:

- output entries carry pofID, dienstCodeID and zeitStart as date plus the
  shift's start time (the target format sketched in wis_main.py), not the
  provisional "needtochange1" field
- free days (R, Komp) are not returned at all; the KNZ document leaves free
  days empty for manual planning
- a composite day (1N3N) is returned as two entries, morning and night,
  since the examples contain no dienstCode for the combination
- days on which an employee already has any entry in Avanti are not
  returned, since those entries already live in the Dienstplan
- resources are filtered to real, active employees (pofTyp "P",
  pofIstMitarbeiter, not deactivated); wishes count as fixed when approved
  or acknowledged, are dropped when rejected, and stay soft while pending
"""

from dataclasses import dataclass, field, replace
from datetime import datetime

from src.infrastructure.config import DEFAULT_CONFIG, ScheduleConfig, to_dates


class AvantiError(ValueError):
    """The payload does not match the expected Avanti structure."""


@dataclass(frozen=True)
class AvantiCode:
    dienst_code_id: str
    kz: str
    start_time: str | None  #"06:00", None for absence codes


@dataclass(frozen=True)
class AvantiInstance:
    config: ScheduleConfig
    #employee number -> resource identity
    resources: dict[int, dict] = field(default_factory=dict)
    #shift kz -> Avanti dienstCode
    codes: dict[str, AvantiCode] = field(default_factory=dict)
    #(employee, day) pairs that already carry an entry in Avanti
    occupied: frozenset = frozenset()


def _get(container, key, where):
    try:
        return container[key]
    except (KeyError, TypeError):
        raise AvantiError(f"{where} has no field {key!r}") from None


def _parse_day(value, where) -> tuple[str, int]:
    #dates arrive as "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS.mmm"
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        raise AvantiError(f"{where}: {value!r} is not an ISO date") from None
    return dt.strftime("%d.%m"), dt.year


def _employee_resources(parameter) -> list[dict]:
    resources = _get(parameter, "ressourcen", "parameter")
    kept = []
    for i, res in enumerate(resources):
        where = f"ressourcen[{i}]"
        if (
            _get(res, "pofTyp", where) == "P"
            and _get(res, "pofIstMitarbeiter", where)
            and str(res.get("pofDeaktiviert", "0")) == "0"
        ):
            kept.append(res)
    return kept


def _wish_disposition(entry) -> str:
    #an entry without wish info is an ordinary existing assignment: fixed
    wish = entry.get("wunsch")
    if not wish:
        return "fixed"
    if wish.get("ablehnung"):
        return "dropped"
    if wish.get("genehmigung") or wish.get("kenntnis"):
        return "fixed"
    return "soft"  #pending wish


def config_from_avanti(
        payload: dict,
        template: ScheduleConfig = DEFAULT_CONFIG,
) -> AvantiInstance:
    """Build a solvable config from an Avanti payload.

    The template supplies the rule set — weights, transitions, coverage
    bounds, the composite/compensation shifts — while the payload supplies
    the data: period, weekend flags, employees, existing entries and wishes.
    """
    parameter = _get(payload, "parameter", "payload")

    #period
    days, weekends, year = [], [], None
    for i, tag in enumerate(_get(parameter, "tage", "parameter")):
        where = f"tage[{i}]"
        day, day_year = _parse_day(_get(tag, "datum", where), where)
        days.append(day)
        weekends.append(1 if _get(tag, "wochenende", where) else 0)
        year = year if year is not None else day_year
    if not days:
        raise AvantiError("parameter.tage is empty")

    #employees, numbered; identity is carried through `resources`
    resources = {}
    for number, res in enumerate(_employee_resources(parameter), start=1):
        resources[number] = {
            "pofID": _get(res, "pofID", "ressource"),
            "pofCode": res.get("pofCode") or f"MA{number}",
        }
    if not resources:
        raise AvantiError("no plannable employees after filtering ressourcen")
    by_pof_id = {r["pofID"]: e for e, r in resources.items()}

    #dienstCodes: every atomic working shift of the template needs one
    codes = {}
    for i, code in enumerate(_get(parameter, "dienstCodes", "parameter")):
        where = f"dienstCodes[{i}]"
        codes[_get(code, "kz", where)] = AvantiCode(
            dienst_code_id=_get(code, "ID", where),
            kz=code["kz"],
            start_time=code.get("zeitStartText"),
        )
    missing = [s for s in template.atomic_working_shifts if s not in codes]
    if missing:
        raise AvantiError(
            f"dienstCodes is missing the shifts {missing}, cannot map output"
        )

    #existing entries and wishes
    fixed, soft, occupied = [], [], set()
    for i, entry in enumerate(payload.get("daten", {}).get("dienstEinteilungen", [])):
        where = f"dienstEinteilungen[{i}]"
        employee = by_pof_id.get(_get(entry, "pofID", where))
        if employee is None:
            continue  #resource outside the filtered selection
        day, _ = _parse_day(_get(entry, "zeitStart", where), where)
        if day not in days:
            continue

        disposition = _wish_disposition(entry)
        if disposition == "dropped":
            continue
        occupied.add((employee, day))

        kz = entry.get("dienstCodeKz")
        if kz in template.shifts:
            target = fixed if disposition == "fixed" else soft
            target.append((employee, day, kz))
        elif disposition == "fixed":
            #an entry our model does not know (Büro, Pikett, ...) blocks the
            #day for KNZ shifts; the closest expressible statement is "no
            #KNZ working shift here", i.e. the rest shift
            fixed.append((employee, day, template.rest_shift))

    config = replace(
        template,
        year=year,
        days=days,
        weekends_override=tuple(weekends),
        employees=list(resources),
        dayoff_assignments=[],
        dayoff_requests=[],
        fixed_assignments=fixed,
        assignment_requests=soft,
        recurring_assignments=[],
        recurring_requests=[],
    )

    return AvantiInstance(
        config=config,
        resources=resources,
        codes=codes,
        occupied=frozenset(occupied),
    )


def schedule_to_avanti(
        schedule: dict,
        instance: AvantiInstance,
        solver_status: str,
) -> dict:
    """Build the output payload: working shifts only, two entries per
    composite day, nothing for days Avanti already has an entry for."""
    config = instance.config
    dates = {
        day: dt.isoformat()
        for day, dt in zip(config.days, to_dates(config.days, config.year))
    }

    einteilungen = []
    for employee, days in schedule.items():
        identity = instance.resources[employee]
        for d, shift in enumerate(days):
            day = config.days[d]
            if shift in config.free_shifts or (employee, day) in instance.occupied:
                continue

            parts = config.composite_shifts.get(shift, (shift,))
            for part in parts:
                code = instance.codes[part]
                start = code.start_time or "00:00"
                einteilungen.append({
                    "pofID": identity["pofID"],
                    "pofCode": identity["pofCode"],
                    "dienstCodeID": code.dienst_code_id,
                    "dienstCodeKz": code.kz,
                    "zeitStart": f"{dates[day]}T{start}:00.000",
                })

    return {
        "version": "1",
        "solver": {"status": solver_status},
        "dienstEinteilungen": einteilungen,
    }
