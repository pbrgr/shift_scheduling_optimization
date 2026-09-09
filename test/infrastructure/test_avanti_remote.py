"""Offline-testable pieces of the remote tool; network calls stay untested
here (they need VPN and a login) and are exercised manually."""

from src.app.avanti_remote import DEFAULTS, expand_period, setting


def test_bare_dates_are_expanded_to_the_api_timestamp_format():
    start, ende = expand_period("2026-02-28", "2026-03-31")
    assert start == "2026-02-28T00:00:00.000"
    assert ende == "2026-03-31T23:59:59.999"


def test_full_timestamps_pass_through_unchanged():
    start, ende = expand_period("2026-02-28T08:00:00.000",
                                "2026-03-31T12:00:00.000")
    assert start.endswith("T08:00:00.000")
    assert ende.endswith("T12:00:00.000")


def test_settings_can_be_overridden_via_environment(monkeypatch):
    assert setting("AVANTI_CLIENT_ID") == DEFAULTS["AVANTI_CLIENT_ID"]
    monkeypatch.setenv("AVANTI_CLIENT_ID", "ANDERER")
    assert setting("AVANTI_CLIENT_ID") == "ANDERER"
