"""Test dymny warstwy Real-Time: zapytania kafli dashboardu i funkcje detekcji kaskad.

Kazde zapytanie wykonywane jest realnie na Eventhouse. Kafle z pliku
`kql/03_dashboard_queries.kql` dostaja podstawione parametry dashboardu
(_startTime, _endTime, _voivodeship, _system), a funkcje z `kql/04` sa
wywolywane z domyslnymi argumentami.

Zegar scenariusza: dane demo sa datowane na wrzesien 2026, wiec `now()`
niczego by nie zwrocil. Test celowo podstawia domyslne okno dashboardu
(ostatnia godzina), zeby sprawdzic, ze funkcje WindowStart / WindowEnd
przelaczaja kafle na szczyt kryzysu zamiast pokazywac pustke.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads((ROOT / ".fabric" / "deployment.json").read_text(encoding="utf-8"))
CLUSTER = STATE["kustoQueryUri"]
DB = "CriticalInfrastructure"

# Parametry dashboardu podstawiane przed kazdym kaflem z pliku 03.
DASHBOARD_PARAMS = """let _endTime = now();
let _startTime = now() - 1h;
let _voivodeship = dynamic([]);
let _system = dynamic([]);
"""

# Funkcje z pliku 04 (same polecenia sterujace) sprawdzamy przez wywolanie.
DETECTION_QUERIES: list[tuple[str, str]] = [
    ("DetectCascade — sygnal domino", "DetectCascade() | take 20"),
    ("PowerToWaterCorrelation — skutek II rzedu", "PowerToWaterCorrelation() | take 20"),
    ("OutageAnomaly — anomalia wolumenu awarii", "OutageAnomaly(1h) | take 20"),
    ("CascadePath — sciezka do konkretnego wezla",
     "let failures = CiNodeStatus | where status != 'operational'"
     "\n    | summarize t = min(event_time) by node_id;"
     "\nlet target = toscalar("
     "\n    CiDependency"
     "\n    | join kind=inner (failures | project source_node_id = node_id, st = t) on source_node_id"
     "\n    | join kind=inner (failures | project target_node_id = node_id, tt = t) on target_node_id"
     "\n    | where st <= tt"
     "\n    | summarize parents = count() by target_node_id"
     "\n    | top 1 by parents desc | project target_node_id);"
     "\nCascadePath(target) | take 20"),
    ("CascadeFootprint — zasieg kaskady", "CascadeFootprint() | take 20"),
]


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://kusto.kusto.windows.net",
         "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr)
    return out.stdout.strip()


TOKEN = None


def query(csl: str) -> tuple[bool, str]:
    global TOKEN
    if TOKEN is None:
        TOKEN = token()
    r = requests.post(f"{CLUSTER}/v1/rest/query",
                      headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                      json={"db": DB, "csl": csl}, timeout=300)
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["@message"]
        except Exception:
            msg = r.text[:300]
        return False, msg.replace("\n", " ")[:160]
    tbl = next((t for t in r.json()["Tables"] if t["TableName"] in ("Table_0", "PrimaryResult")), None)
    if tbl is None:
        return True, "brak wynikow"
    return True, f"{len(tbl['Rows'])} wierszy"


def split_tiles(path: Path) -> list[tuple[str, str]]:
    """Dzieli plik kafli na pary (tytul, zapytanie).

    Separatorem jest linia komentarza rozpoczynajaca nowy kafel; komentarze
    wewnatrz kafla (bez poprzedzajacej tresci) tylko uzupelniaja tytul.
    """
    tiles: list[tuple[str, str]] = []
    title = path.stem
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body and not body.startswith("."):
            tiles.append((title, body))

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            if any(b.strip() for b in buf):
                flush()
                buf = []
            label = re.sub(r"^//[\s=-]*", "", stripped).strip()
            label = re.sub(r"[\s=-]+$", "", label)
            if label:
                title = label
            continue
        buf.append(line)
    flush()
    return tiles


def main() -> None:
    total = ok = 0
    print(f"== Kafle dashboardu ({CLUSTER.split('//')[1].split('.')[0]}/{DB})")
    anchor_ok, anchor = query("print peak = toscalar(ScenarioPeak()), now = toscalar(ScenarioNow())")
    print(f"   kotwica czasu: {'OK' if anchor_ok else 'BLAD'} {anchor}")

    for title, csl in split_tiles(ROOT / "kql" / "03_dashboard_queries.kql"):
        total += 1
        good, info = query(DASHBOARD_PARAMS + csl)
        ok += good
        print(f"   {'OK  ' if good else 'BLAD'} {title[:56]:<56} {info}")

    print("\n== Detekcja kaskad")
    for title, csl in DETECTION_QUERIES:
        total += 1
        good, info = query(csl)
        ok += good
        print(f"   {'OK  ' if good else 'BLAD'} {title[:56]:<56} {info}")

    print(f"\n{ok}/{total} zapytan wykonalo sie poprawnie.")
    if ok != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
