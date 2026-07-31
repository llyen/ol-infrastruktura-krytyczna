"""Test dymny Eventstreamu: wysyla po kilka zdarzen z kazdego strumienia
i sprawdza, ze doszly do tabel `*Raw`, a update policy przeniosla je do
tabel docelowych.

Zdarzenia testowe maja znacznik czasu z przyszlosci scenariusza i node_id
z prefiksem TEST-, wiec nie zaklocaja demo. Skrypt sprzata po sobie.

Uzycie:
    python deploy/13_verify_eventstream.py
    python deploy/13_verify_eventstream.py --keep   # bez sprzatania
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
API = "https://api.fabric.microsoft.com/v1"
DB = "CriticalInfrastructure"
MARK = "TEST-ES"
N = 5

CHECKS = [
    ("ci_node_status", "CiNodeStatus", "node_id"),
    ("ci_operator_reports", "CiOperatorReport", "node_id"),
    ("hydro_readings", "HydroReading", "gauge_id"),
]


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def connection_string(ws: str, esid: str) -> tuple[str, str]:
    h = {"Authorization": f"Bearer {token('https://api.fabric.microsoft.com')}"}
    # zdarzenia wyslane, zanim destynacja przejdzie w stan Running, przepadaja
    for attempt in range(40):
        t = requests.get(f"{API}/workspaces/{ws}/eventstreams/{esid}/topology", headers=h, timeout=120)
        t.raise_for_status()
        topo = t.json()
        states = {d["name"]: d.get("status") for d in topo.get("destinations", [])}
        if states and all(s == "Running" for s in states.values()):
            break
        print(f"  czekam na aktywacje destynacji: {states}")
        time.sleep(10)
    else:
        sys.exit("Destynacje nie osiagnely stanu Running.")
    src = next(s for s in topo["sources"] if s["type"] == "CustomEndpoint")
    c = requests.get(f"{API}/workspaces/{ws}/eventstreams/{esid}/sources/{src['id']}/connection",
                     headers=h, timeout=120)
    c.raise_for_status()
    body = c.json()
    return body["accessKeys"]["primaryConnectionString"], body["eventHubName"]


def kql(cluster: str, query: str, tk: str, mgmt: bool = False):
    """Wykonuje zapytanie KQL. Ponawia proby przy bledach sieciowych -
    endpoint Kusto potrafi zrywac polaczenie TLS przy dluzszym odpytywaniu."""
    url = f"{cluster}/v1/rest/{'mgmt' if mgmt else 'query'}"
    last = ""
    for attempt in range(4):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {tk}",
                                            "Content-Type": "application/json"},
                              json={"db": DB, "csl": query}, timeout=300)
        except requests.RequestException as exc:
            last = f"{type(exc).__name__}: {exc}"[:200]
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code != 200:
            return None, r.text[:300]
        table = r.json()["Tables"][0]
        return table["Rows"], None
    return None, last


def sample_events(ts: dt.datetime) -> list[dict]:
    ev: list[dict] = []
    for i in range(N):
        t = (ts + dt.timedelta(seconds=i)).isoformat()
        ev.append({"stream": "ci_node_status", "event_time": t, "node_id": f"{MARK}-{i:02d}",
                   "system_code": "S01", "gmina_code": "0201011", "powiat_code": "0201",
                   "voivodeship_code": "02", "status": "down", "load_pct": 0.0,
                   "on_backup_power": True, "backup_fuel_hours_left": 4.5,
                   "water_level_margin_m": -0.3, "population_served": 1234})
        ev.append({"stream": "ci_operator_reports", "event_time": t, "report_id": f"{MARK}-R{i:02d}",
                   "node_id": f"{MARK}-{i:02d}", "system_code": "S01", "voivodeship_code": "02",
                   "powiat_code": "0201", "operator_name": MARK, "report_kind": "awaria",
                   "severity": "critical", "eta_restore_hours": 6.0,
                   "support_requested": True, "channel": "test"})
        ev.append({"stream": "hydro_readings", "event_time": t, "gauge_id": f"{MARK}-G{i:02d}",
                   "voivodeship_code": "02", "powiat_code": "0201", "gmina_code": "0201011",
                   "water_level_cm": 512.0, "warning_level_cm": 400,
                   "alarm_level_cm": 480, "state": "alarm"})
    return ev


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="nie usuwaj zdarzen testowych")
    args = ap.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, esid, cluster = state["workspaceId"], state.get("eventstreamId"), state["kustoQueryUri"]
    if not esid:
        sys.exit("Brak eventstreamId - uruchom najpierw deploy/12_eventstream.py")

    conn, hub = connection_string(ws, esid)
    print(f"Endpoint: {hub}")

    from azure.eventhub import EventData, EventHubProducerClient

    ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    events = sample_events(ts)
    producer = EventHubProducerClient.from_connection_string(conn, eventhub_name=hub)
    with producer:
        batch = producer.create_batch()
        for e in events:
            batch.add(EventData(json.dumps(e, ensure_ascii=False)))
        producer.send_batch(batch)
    print(f"Wyslano {len(events)} zdarzen ({N} na strumien)")

    tk = token("https://kusto.kusto.windows.net")
    deadline = time.time() + 420
    pending = {name: (table, key) for name, table, key in CHECKS}
    results: dict[str, int] = {}

    print("Czekam na przeplyw (Eventstream -> filtr -> tabela docelowa)...")
    while pending and time.time() < deadline:
        time.sleep(15)
        for name in list(pending):
            table, key = pending[name]
            rows, err = kql(cluster, f'{table} | where {key} startswith "{MARK}" | count', tk)
            if err or rows is None:
                print(f"  (blad zapytania dla {name}: {err})")
                continue
            n = rows[0][0] if rows else 0
            results[name] = n
            if n >= N:
                print(f"  OK   {name}: {table} = {n}")
                del pending[name]
        if pending:
            print(f"  ... czekam na: {', '.join(pending)} "
                  f"({int(deadline - time.time())} s do konca)")

    # kontrola rozgalezienia: zdarzenie nie moze trafic do niewlasciwej tabeli
    print("Kontrola rozgalezienia filtrow:")
    crosstalk = []
    for name, table, key in CHECKS:
        rows, _ = kql(cluster, f'{table} | where {key} startswith "{MARK}" | count', tk)
        n = rows[0][0] if rows else 0
        if n != N:
            crosstalk.append(f"{table}: {n} wierszy zamiast {N}")
    if crosstalk:
        print("  UWAGA - zdarzenia przeciekaja miedzy filtrami:")
        for c in crosstalk:
            print("   ", c)
    else:
        print(f"  OK - kazda tabela dostala dokladnie {N} zdarzen")

    if not args.keep:
        print("Sprzatanie zdarzen testowych...")
        for name, table, key in CHECKS:
            _, err = kql(cluster,
                         f'.delete table {table} records <| {table} | where {key} startswith "{MARK}"',
                         tk, mgmt=True)
            if err:
                print(f"  UWAGA: nie udalo sie posprzatac {table}: {err}")
        print("  usunieto")

    if pending or crosstalk:
        print(f"\nNIEPOWODZENIE: {', '.join(pending) or 'przeciek miedzy filtrami'}")
        for name, n in results.items():
            print(f"  {name}: {n}")
        sys.exit(1)
    print("\nWszystkie trzy strumienie przechodza przez Eventstream do wlasciwych tabel.")


if __name__ == "__main__":
    main()
