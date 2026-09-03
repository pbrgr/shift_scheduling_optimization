"""Generates realistic Avanti DPService payloads for testing and demos.

Emits the same structure as the real Solver-Script-Input.json examples, but
with invented people, so the payloads can live in the public repo. The month
follows the KNZ document's description of reality: everybody hands in wishes
before the deadline, there are vacation blocks, weekly education days and
office days as existing entries, part-time pensums, and the payload contains
a company and a system account so the adapter's filtering is exercised.

Deliberately not generated, because the input structure cannot express them
(evidence for the open interface questions): per-day demand, populated
Fähigkeiten/roles, hour balances.

    python -m src.infrastructure.avanti_generator --seed 42 > input.json
"""

import json
import random
import sys
from datetime import date, timedelta

FIRST_NAMES = ["Mia", "Ben", "Pia", "Tim", "Lea", "Jon", "Ida", "Max", "Eva",
               "Nik", "Lia", "Tom", "Amy", "Rea", "Zoe", "Lou", "Kim", "Ali",
               "Uma", "Leo", "Ada", "Gil", "Sam", "Fee", "Ivo", "Ana", "Urs",
               "Elin", "Nora", "Jara"]
LAST_NAMES = ["Muster", "Beispiel", "Probe", "Modell", "Schema", "Fiktiv",
              "Platzhalter", "Entwurf", "Skizze", "Attrappe"]

#the KNZ dienstCodes, matching the real Dienstliste in structure
DIENST_CODES = [
    {"ID": "GEN-1N-000000", "kz": "1N", "bez": "Fruehschicht KNZ",
     "dienstArtCode": "S", "zeitStartText": "06:00", "zeitEndeText": "12:00"},
    {"ID": "GEN-2N-000000", "kz": "2N", "bez": "Spaetschicht KNZ",
     "dienstArtCode": "S", "zeitStartText": "11:30", "zeitEndeText": "18:30"},
    {"ID": "GEN-3N-000000", "kz": "3N", "bez": "Nachtschicht KNZ",
     "dienstArtCode": "S", "zeitStartText": "18:00", "zeitEndeText": "06:30"},
    {"ID": "GEN-R-0000000", "kz": "R", "bez": "Ruhe- und Feiertag",
     "dienstArtCode": "A", "zeitStartText": None, "zeitEndeText": None},
]

#codes that exist in Avanti but not in the solver's shift system; they
#arrive as existing entries and block the day (like BV/PA in the real data)
FOREIGN_CODES = {"FE": "08:00", "AUS": "08:00", "BV": "07:00"}
ENTRY_TIMES = {"1N": "06:00", "2N": "11:30", "3N": "18:00", "R": "00:00",
               **FOREIGN_CODES}


def _resource(number: int, rng: random.Random) -> dict:
    first = FIRST_NAMES[number % len(FIRST_NAMES)]
    last = LAST_NAMES[number % len(LAST_NAMES)]
    #most people are full-time, some work part-time
    pensum = 100 if rng.random() < 0.7 else rng.choice([50, 60, 80, 90])
    return {
        "pofID": f"GEN{number:03d}_1XO",
        "pofCode": f"T{first[0]}{last[0]}{number:02d}",
        "pofName": last, "pofVorname": first,
        "pofTyp": "P", "pofIstMitarbeiter": True, "pofDeaktiviert": "0",
        "beschaeftigungsgrad": str(pensum), "pofListeFaehigkeiten": None,
    }


def _wish_info(rng: random.Random):
    #the wish workflow: most are decided, some are still pending
    stamp = {"pofBez": "Generator", "zeitPunkt": "2026-01-01T08:00:00.000"}
    roll = rng.random()
    if roll < 0.50:
        return {"ablehnung": None, "kenntnis": None, "genehmigung": stamp}
    if roll < 0.65:
        return {"ablehnung": None, "kenntnis": stamp, "genehmigung": None}
    if roll < 0.80:
        return {"ablehnung": stamp, "kenntnis": None, "genehmigung": None}
    return {"ablehnung": None, "kenntnis": None, "genehmigung": None}


def generate_payload(
        seed: int = 42,
        num_employees: int = 30,
        start: date = date(2026, 3, 1),
        num_days: int = 31,
        wishes_per_employee: tuple[int, int] = (2, 4),
) -> dict:
    rng = random.Random(seed)
    days = [start + timedelta(days=d) for d in range(num_days)]

    #one weekday per month may be a holiday: Avanti flags it as weekend
    holiday = rng.choice([d for d in days if d.weekday() < 5])
    tage = [
        {"datum": d.isoformat(), "wochenende": d.weekday() >= 5 or d == holiday}
        for d in days
    ]

    resources = [_resource(n, rng) for n in range(1, num_employees + 1)]
    ressourcen = list(resources)
    #a company and a system account, so the filtering is exercised
    ressourcen.insert(rng.randrange(len(ressourcen) + 1), {
        "pofID": "GENFIRMA_1XO", "pofCode": None, "pofName": "Beispiel AG",
        "pofTyp": "F", "pofIstMitarbeiter": False, "pofDeaktiviert": "0",
        "beschaeftigungsgrad": "100", "pofListeFaehigkeiten": None,
    })
    ressourcen.insert(rng.randrange(len(ressourcen) + 1), {
        "pofID": "GENSYS00_1XO", "pofCode": "SYS", "pofName": "Dienstplan, System",
        "pofTyp": "P", "pofIstMitarbeiter": False, "pofDeaktiviert": "0",
        "beschaeftigungsgrad": "100", "pofListeFaehigkeiten": None,
    })

    entries = []
    used: set[tuple[str, date]] = set()

    def add_entry(res: dict, day: date, kz: str, wish=None) -> None:
        if (res["pofID"], day) in used:
            return
        used.add((res["pofID"], day))
        entries.append({
            "pofID": res["pofID"],
            "zeitStart": f"{day.isoformat()}T{ENTRY_TIMES[kz]}:00.000",
            "dienstCodeKz": kz, "dienstCodeBez": kz, "wunsch": wish,
        })

    #vacation blocks: existing entries the planner already made
    for res in rng.sample(resources, k=max(1, num_employees // 8)):
        first_day = rng.randrange(num_days - 7)
        for offset in range(rng.randint(5, 12)):
            if first_day + offset < num_days:
                add_entry(res, days[first_day + offset], "FE")

    #weekly education day for a couple of people (Avanti has no recurrence,
    #so the DPService delivers them as individual entries)
    for res in rng.sample(resources, k=max(1, num_employees // 15)):
        weekday = rng.randrange(5)
        for day in days:
            if day.weekday() == weekday:
                add_entry(res, day, "AUS")

    #a few office days and pre-planned shifts
    for res in rng.sample(resources, k=max(1, num_employees // 10)):
        for _ in range(rng.randint(1, 3)):
            add_entry(res, rng.choice(days), "BV")
    for res in rng.sample(resources, k=max(1, num_employees // 10)):
        add_entry(res, rng.choice(days), rng.choice(["1N", "2N", "3N"]))

    #wishes: everybody hands some in before the deadline
    for res in resources:
        for _ in range(rng.randint(*wishes_per_employee)):
            kz = "R" if rng.random() < 0.4 else rng.choice(["1N", "2N", "3N"])
            add_entry(res, rng.choice(days), kz, wish=_wish_info(rng))

    return {
        "$id": 1,
        "parameter": {
            "$id": 2,
            "tage": tage,
            "ressourcen": ressourcen,
            "dienstCodes": [dict(c) for c in DIENST_CODES],
        },
        "daten": {"$id": 3, "dienstEinteilungen": entries},
    }


if __name__ == "__main__":
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 42
    json.dump(generate_payload(seed=seed), sys.stdout, indent=1)
    sys.stdout.write("\n")
