from dataclasses import replace
from datetime import date

from src.infrastructure.config import DEFAULT_CONFIG, to_dates, weekend_flags


def test_weekend_flags_match_the_calendar():
    days = ["05.03", "06.03", "07.03", "08.03", "09.03"] #thu fri sat sun mon
    assert weekend_flags(days, 2026) == [0, 0, 1, 1, 0]


def test_default_config_weekends_match_its_year():
    #regression: the flags used to be maintained by hand, with no link to the
    #dates, so they silently kept pointing at the wrong days of the week
    for day, flag in zip(DEFAULT_CONFIG.days, DEFAULT_CONFIG.weekends):
        d, m = (int(part) for part in day.split("."))
        expected = 1 if date(DEFAULT_CONFIG.year, m, d).weekday() >= 5 else 0
        assert flag == expected, day


def test_dates_roll_over_into_the_next_year():
    #"DD.MM" carries no year, so a falling month means the period wrapped
    dates = to_dates(["30.12", "31.12", "01.01", "02.01"], 2026)

    assert dates == [
        date(2026, 12, 30),
        date(2026, 12, 31),
        date(2027, 1, 1),
        date(2027, 1, 2),
    ]


def test_weekend_bounds_follow_from_the_period():
    config = DEFAULT_CONFIG

    assert len(config.weekend_indices) == 10
    assert config.max_weekend_days_worked == int(10 * config.max_weekend_work_ratio)
    #10 weekend days * 3 min_ee * 3 working shifts, over 30 employees
    assert config.fair_weekend_days == 90 // 30


def test_fair_shift_band_follows_from_the_period():
    #32 days * 3 min_ee * 3 working shifts = 288, over 30 employees
    assert DEFAULT_CONFIG.fair_shifts == (9, 10)


def test_fair_band_tracks_a_changed_coverage_requirement():
    config = replace(DEFAULT_CONFIG, min_ee=4)

    assert config.fair_shifts == (12, 13)
    assert config.fair_weekend_days == 4
