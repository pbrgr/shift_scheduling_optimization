"""Fetches real test data from the Avanti DPService API and runs the local
solver on it — the integration loop without waiting for mailed examples.

Strictly read-only: it only calls the two scheduling test endpoints and, on
request, the dienst-abfolgen lookup. Nothing is ever written to Avanti.

Requires the Swisscom VPN and a valid Avanti login. The password comes from
the environment variable AVANTI_PASSWORD (or an interactive prompt); it is
never stored or logged.

    export AVANTI_PASSWORD=...
    python -m src.app.avanti_remote --start 2026-02-28 --ende 2026-03-31
    python -m src.app.avanti_remote --abfolgen
    python -m src.app.avanti_remote --start ... --ende ... --compare

Defaults (server, mandant, user, Dienstliste) mirror the avel312 test
environment from the DPService repo's Bruno collection and can be overridden
via AVANTI_* environment variables.
"""

import argparse
import getpass
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from src.app.avanti_filter import run as run_filter

DEFAULTS = {
    "AVANTI_BASE_URL": "https://avel312.avanti.ch/Avanti/DPService/api/v1",
    "AVANTI_IDENTITY_URL": "https://dev.avanti.ch/identity",
    "AVANTI_CLIENT_ID": "AVANTIDP",
    "AVANTI_SCOPE": "offline_access AVANTIDP",
    "AVANTI_MANDANT": "8lBQzObMc8W_10H",
    "AVANTI_USERNAME": "avanti",
    "AVANTI_DIENSTLISTE": "B482BB2B492840E0AA8562DECDED4959",
}


def setting(name: str) -> str:
    return os.environ.get(name, DEFAULTS[name])


def expand_period(start: str, ende: str) -> tuple[str, str]:
    #the API expects full timestamps; accept bare dates
    if "T" not in start:
        start += "T00:00:00.000"
    if "T" not in ende:
        ende += "T23:59:59.999"
    return start, ende


def _request(url: str, method: str = "GET", data: bytes | None = None,
             headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        body = ex.read().decode("utf-8", errors="replace")[:300]
        raise SystemExit(
            f"HTTP {ex.code} von {url}\n{body}\n"
            + ("Hinweis: 400/401 deutet auf falsches Passwort oder fehlende "
               "Berechtigung." if ex.code in (400, 401, 403) else "")
        ) from None
    except urllib.error.URLError as ex:
        raise SystemExit(
            f"Keine Verbindung zu {url}: {ex.reason}\n"
            "Hinweis: Swisscom-VPN aktiv?"
        ) from None


def get_token(password: str) -> str:
    form = urllib.parse.urlencode({
        "client_id": setting("AVANTI_CLIENT_ID"),
        "grant_type": "password",
        "scope": setting("AVANTI_SCOPE"),
        "mandant": setting("AVANTI_MANDANT"),
        "username": setting("AVANTI_USERNAME"),
        "password": password,
    }).encode("utf-8")

    response = _request(
        setting("AVANTI_IDENTITY_URL") + "/connect/token",
        method="POST", data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return response["access_token"]


def api(token: str, path: str, method: str = "GET", params: dict | None = None) -> dict:
    url = setting("AVANTI_BASE_URL") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Authorization": f"Bearer {token}"}
    if os.environ.get("AVANTI_CTX"):
        headers["AVANTI_CTX"] = os.environ["AVANTI_CTX"]
    return _request(url, method=method, headers=headers)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Testdaten aus dem Avanti-Testsystem holen und lokal lösen"
        " (nur lesende Aufrufe)")
    parser.add_argument("--start", help="Periodenbeginn, z.B. 2026-02-28")
    parser.add_argument("--ende", help="Periodenende, z.B. 2026-03-31")
    parser.add_argument("--dienstliste", default=setting("AVANTI_DIENSTLISTE"))
    parser.add_argument("--out", default="output_remote",
                        help="Zielordner (default: output_remote)")
    parser.add_argument("--compare", action="store_true",
                        help="zusätzlich das serverseitige (alte) Skript via"
                        " /solve laufen lassen und dessen Output speichern")
    parser.add_argument("--abfolgen", action="store_true",
                        help="GET /dienst-abfolgen der Dienstliste ausgeben")
    args = parser.parse_args(argv)

    if not args.abfolgen and not (args.start and args.ende):
        parser.error("--start und --ende angeben (oder --abfolgen)")

    password = os.environ.get("AVANTI_PASSWORD") or getpass.getpass(
        f"Avanti-Passwort für {setting('AVANTI_USERNAME')}: ")
    token = get_token(password)
    print("Login ok.", file=sys.stderr)

    if args.abfolgen:
        abfolgen = api(token, f"/dienst-listen/{args.dienstliste}/dienst-abfolgen")
        json.dump(abfolgen, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        if not (args.start and args.ende):
            return 0

    start, ende = expand_period(args.start, args.ende)
    period = {"dienstListeID": args.dienstliste, "start": start, "ende": ende}

    print(f"Hole Input-Daten für {start[:10]} bis {ende[:10]} …", file=sys.stderr)
    payload = api(token, "/tests/scheduling-optimization-get-data",
                  method="POST", params=period)

    os.makedirs(args.out, exist_ok=True)
    input_path = os.path.join(args.out, "input.json")
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"Input gespeichert: {input_path}", file=sys.stderr)

    if args.compare:
        print("Starte serverseitigen Lauf (altes Skript) …", file=sys.stderr)
        remote = api(token, "/tests/scheduling-optimization-solve",
                     method="POST", params=period)
        remote_path = os.path.join(args.out, "output_altes_skript.json")
        with open(remote_path, "w", encoding="utf-8") as f:
            json.dump(remote, f, ensure_ascii=False, indent=1)
        print(f"Server-Output gespeichert: {remote_path}", file=sys.stderr)

    print("Löse lokal mit dem neuen Modell …", file=sys.stderr)
    out = io.StringIO()
    exit_code = run_filter(
        stdin=io.StringIO(json.dumps(payload)), stdout=out,
        output_path=args.out,
    )
    if exit_code == 0:
        output_path = os.path.join(args.out, "output_neues_skript.json")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(out.getvalue())
        print(f"Unser Output: {output_path}", file=sys.stderr)
        print(f"Report: {os.path.join(args.out, 'report.html')}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
