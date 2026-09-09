import io
import json
import os
from dataclasses import replace

import pytest

from src.app.avanti_filter import run
from src.infrastructure.avanti import (
    AvantiError,
    config_from_avanti,
    schedule_to_avanti,
)
from src.infrastructure.config import DEFAULT_CONFIG

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures",
                       "avanti_input.json")

#the fixture has 6 employees, far fewer than the KNZ coverage of 3 to 5
#per shift needs; the relaxed bounds keep it solvable in milliseconds
RELAXED = replace(DEFAULT_CONFIG, min_ee=1, max_ee=2, max_solve_seconds=10.0)


@pytest.fixture
def payload() -> dict:
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_parses_period_and_weekend_override(payload):
    config = config_from_avanti(payload, RELAXED).config

    assert config.year == 2026
    assert config.days[0] == "05.10" and config.days[-1] == "14.10"
    #12.10 is a monday, but Avanti flags it (holiday): the override wins
    #over the calendar derivation
    assert config.weekends == [0, 0, 0, 0, 0, 1, 1, 1, 0, 0]


def test_filters_out_companies_and_system_accounts(payload):
    instance = config_from_avanti(payload, RELAXED)

    kept = {r["pofID"] for r in instance.resources.values()}
    assert len(kept) == 6
    assert "FIRMA1_1XO" not in kept  #pofTyp F
    assert "SYSTEM_1XO" not in kept  #pofIstMitarbeiter false


def test_wish_dispositions(payload):
    instance = config_from_avanti(payload, RELAXED)
    config = instance.config
    number = {r["pofID"]: e for e, r in instance.resources.items()}

    #plain existing entry: fixed as-is
    assert (number["FAKE01_1XO"], "06.10", "1N") in config.fixed_assignments
    #approved wish with a code our model does not know: blocks the day
    assert (number["FAKE02_1XO"], "07.10", "R") in config.fixed_assignments
    #rejected wish: dropped entirely, the day stays plannable
    assert not any(
        e == number["FAKE03_1XO"] and day == "08.10"
        for e, day, _ in config.fixed_assignments
    )
    assert (number["FAKE03_1XO"], "08.10") not in {
        (e, d) for e, d in instance.occupied
    }
    #pending wish: soft request
    assert (number["FAKE04_1XO"], "09.10", "3N") in config.assignment_requests
    #entry of a resource outside the selection is ignored
    assert all(day != "09.10" or e != "OUTSIDE_1XO"
               for e, day, _ in config.fixed_assignments)


def test_missing_fields_fail_loudly(payload):
    del payload["parameter"]["dienstCodes"]

    with pytest.raises(AvantiError, match="parameter has no field 'dienstCodes'"):
        config_from_avanti(payload, RELAXED)


def test_missing_shift_code_fails_loudly(payload):
    payload["parameter"]["dienstCodes"] = [
        c for c in payload["parameter"]["dienstCodes"] if c["kz"] != "2N"
    ]

    with pytest.raises(AvantiError, match="missing the shifts \\['2N'\\]"):
        config_from_avanti(payload, RELAXED)


def test_output_contains_only_working_shifts_with_ids_and_times(payload):
    instance = config_from_avanti(payload, RELAXED)
    config = instance.config

    #hand-built schedule: composite day, free days, an occupied day
    schedule = {e: ["R"] * config.num_days for e in config.employees}
    schedule[1][0] = "1N3N"  #05.10: two entries expected
    schedule[1][1] = "1N"    #06.10: occupied (existing entry), must be skipped
    schedule[2][3] = "2N"    #08.10
    schedule[2][4] = "Komp"  #09.10: free, must not appear

    out = schedule_to_avanti(schedule, instance, "FEASIBLE")

    assert out["version"] == "1"
    assert out["solver"] == {"status": "FEASIBLE"}

    entries = {
        (e["pofID"], e["zeitStart"], e["dienstCodeKz"], e["dienstCodeID"])
        for e in out["dienstEinteilungen"]
    }
    pof1 = instance.resources[1]["pofID"]
    pof2 = instance.resources[2]["pofID"]
    assert entries == {
        (pof1, "2026-10-05T06:00:00.000", "1N", "CODE-1N-0000"),
        (pof1, "2026-10-05T18:00:00.000", "3N", "CODE-3N-0000"),
        (pof2, "2026-10-08T11:30:00.000", "2N", "CODE-2N-0000"),
    }


def test_filter_end_to_end(payload, tmp_path):
    stdout = io.StringIO()
    exit_code = run(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=stdout,
        template=RELAXED,
        output_path=str(tmp_path),
    )

    assert exit_code == 0
    result = json.loads(stdout.getvalue())
    assert result["solver"]["status"] in ("OPTIMAL", "FEASIBLE")
    assert result["dienstEinteilungen"]

    free = set(RELAXED.free_shifts)
    for entry in result["dienstEinteilungen"]:
        assert entry["dienstCodeKz"] not in free
        assert entry["dienstCodeID"].startswith("CODE-")
        assert "T" in entry["zeitStart"]

    assert (tmp_path / "report.html").exists()


def test_filter_rejects_garbage_input(tmp_path):
    stdout = io.StringIO()

    exit_code = run(
        stdin=io.StringIO("this is not json"),
        stdout=stdout,
        template=RELAXED,
        output_path=str(tmp_path),
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""  #stdout stays clean on errors


REAL_FILES = [
    "Avanti/DPAutoGen-1/Solver-Script-Input.json",
    "Avanti/DPAutoGen-2/Solver-Script-Input.json",
]


@pytest.mark.skipif(
    not all(os.path.exists(p) for p in REAL_FILES),
    reason="real Avanti examples only exist locally (not committed: PII)",
)
@pytest.mark.parametrize("path", REAL_FILES)
def test_real_avanti_examples_parse(path):
    with open(path, encoding="utf-8") as f:
        instance = config_from_avanti(json.load(f), RELAXED)

    config = instance.config
    assert config.num_employees > 0
    assert config.num_days in (23, 19)
    assert config.problems() == []
    #every atomic shift got a real dienstCodeID
    for shift in config.atomic_working_shifts:
        assert instance.codes[shift].dienst_code_id


def test_real_stdout_stays_pure_json_even_with_progress_output(
    payload, tmp_path, capsys
):
    #regression: the CP-SAT progress printer used to write "Solution 0, ..."
    #lines to stdout, corrupting the JSON when the filter runs as a real
    #Unix filter (shell redirection). Silvan hit the very same issue in his
    #wis_main.py and removed the printer there
    run(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=io.StringIO(),
        template=RELAXED,
        output_path=str(tmp_path),
    )

    assert capsys.readouterr().out == ""
