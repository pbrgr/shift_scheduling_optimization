"""The shift leader rule: at least one leader (or deputy) per shift and day,
with priority-1 leaders preferred. Armed only when the selection actually
contains skill carriers, so unmaintained data cannot flood the objective."""

import json
import os
from dataclasses import replace

from src.core.metrics import compute_metrics, summary_lines
from src.infrastructure.avanti import config_from_avanti
from src.infrastructure.config import DEFAULT_CONFIG

LEADERS = {"Schichtleiter": 1, "Schichtleiter Stv": 2}


def test_matching_is_exact_but_case_insensitive():
    config = replace(
        DEFAULT_CONFIG,
        skills={1: ("schichtleiter",), 2: ("Schichtleiter Stv", "Arzt"),
                3: ("Schichtleiterin",), 4: ("Arzt",)},
        leader_skills=LEADERS,
    )

    assert config.leader_employees == {1: 1, 2: 2}  #3: no exact match


def test_rule_stays_dormant_without_carriers(tiny_config, solve):
    config = replace(tiny_config, leader_skills=LEADERS)
    _, _, schedule = solve(config)
    metrics = compute_metrics(schedule, config)

    assert metrics.shifts_without_leader is None
    assert any("DORMANT" in line for line in summary_lines(metrics, config))


def test_every_shift_gets_a_leader_when_possible(tiny_config, solve):
    config = replace(
        tiny_config,
        leader_skills=LEADERS,
        skills={1: ("Schichtleiter",), 2: ("Schichtleiter",),
                3: ("Schichtleiter Stv",), 4: ("Schichtleiter Stv",)},
    )
    _, _, schedule = solve(config)
    metrics = compute_metrics(schedule, config)

    assert metrics.shifts_without_leader == 0
    assert any("Shifts without leader: 0" in line
               for line in summary_lines(metrics, config))


def test_adapter_parses_skills_from_all_language_variants():
    fixture = os.path.join(os.path.dirname(__file__), "..", "fixtures",
                           "avanti_input.json")
    with open(fixture, encoding="utf-8") as f:
        instance = config_from_avanti(json.load(f), DEFAULT_CONFIG)

    config = instance.config
    number = {r["pofID"]: e for e, r in instance.resources.items()}
    assert config.skills[number["FAKE01_1XO"]] == (
        "Führerausweis C1", "Schichtleiter",
    )
    #this one is maintained only in the language variant field
    assert config.skills[number["FAKE03_1XO"]] == ("Schichtleiter Stv",)
    assert config.leader_employees == {
        number["FAKE01_1XO"]: 1, number["FAKE03_1XO"]: 2,
    }
