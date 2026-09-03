import io
import json
from dataclasses import replace
from datetime import date

from src.app.avanti_filter import run
from src.infrastructure.avanti import config_from_avanti
from src.infrastructure.avanti_generator import generate_payload
from src.infrastructure.config import DEFAULT_CONFIG


def test_same_seed_same_payload():
    assert generate_payload(seed=7) == generate_payload(seed=7)
    assert generate_payload(seed=7) != generate_payload(seed=8)


def test_generated_payload_parses_into_a_valid_config():
    instance = config_from_avanti(generate_payload(seed=1), DEFAULT_CONFIG)
    config = instance.config

    assert config.problems() == []
    assert config.num_employees == 30  #company and system account filtered
    assert config.num_days == 31
    assert config.year == 2026


def test_holiday_flag_reaches_the_weekend_override():
    config = config_from_avanti(generate_payload(seed=1), DEFAULT_CONFIG).config

    #Sa/So alone would be 9 weekend days in march 2026; the holiday adds one
    assert sum(config.weekends) == 10


def test_month_is_realistically_dense():
    payload = generate_payload(seed=1)
    entries = payload["daten"]["dienstEinteilungen"]

    #30 employees x 31 days: vacations, education, office days and wishes
    assert 100 <= len(entries) <= 250
    #every (pofID, day) pair at most once
    keys = [(e["pofID"], e["zeitStart"][:10]) for e in entries]
    assert len(keys) == len(set(keys))
    #every wish disposition occurs
    infos = [e["wunsch"] for e in entries if e["wunsch"]]
    assert any(w["genehmigung"] for w in infos)
    assert any(w["ablehnung"] for w in infos)
    assert any(w["kenntnis"] for w in infos)
    assert any(not (w["genehmigung"] or w["ablehnung"] or w["kenntnis"])
               for w in infos)


def test_generated_month_solves_end_to_end(tmp_path):
    #small edition so the suite stays fast; the full 30x31 stress run is a
    #manual exercise
    payload = generate_payload(
        seed=3, num_employees=10, num_days=14, start=date(2026, 3, 2)
    )
    template = replace(DEFAULT_CONFIG, min_ee=1, max_ee=3, max_solve_seconds=10.0)

    stdout = io.StringIO()
    exit_code = run(
        stdin=io.StringIO(json.dumps(payload)),
        stdout=stdout,
        template=template,
        output_path=str(tmp_path),
    )

    assert exit_code == 0
    result = json.loads(stdout.getvalue())
    assert result["dienstEinteilungen"]
