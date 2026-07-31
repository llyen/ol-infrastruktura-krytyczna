"""Eventstream es_ci_telemetry: jedno zrodlo, trzy tabele docelowe.

Topologia:

    custom endpoint  ->  strumien  ->  filtr stream == ci_node_status      -> CiNodeStatus
                                    -> filtr stream == ci_operator_reports -> CiOperatorReport
                                    -> filtr stream == hydro_readings      -> HydroReading

Symulator `simulate_realtime.py` dokleja do kazdego zdarzenia pole `stream`,
po ktorym rozgalezia sie ruch.

Uwaga: destynacja Eventhouse w trybie `ProcessedIngestion` mapuje pola JSON
na kolumny **po nazwach**, dlatego kieruje sie ja na tabele typowane, a nie
na bufory `*Raw` (kolumna `payload: dynamic`, zaden klucz JSON nie pasuje —
destynacja przechodzi w stan `Warning` i po cichu gubi zdarzenia). Bufory
`*Raw` wraz z update policy sluza wsadowemu ladowaniu przez `05_load_eventhouse.py`.

Uzycie:
    python deploy/12_eventstream.py            # wdrozenie topologii
    python deploy/12_eventstream.py --dry-run  # sam podglad definicji
    python deploy/12_eventstream.py --keys     # wypisz connection string zrodla
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
API = "https://api.fabric.microsoft.com/v1"
ES_NAME = "es_ci_telemetry"
ES_DESC = "Telemetria obiektow IK, meldunki operatorow i hydrologia -> Eventhouse."
DB_NAME = "CriticalInfrastructure"
SOURCE = "src_custom_endpoint"
STREAM = "stream_ci_telemetry"

# (nazwa strumienia w polu `stream`, wezel filtra, wezel destynacji, tabela)
ROUTES = [
    ("ci_node_status", "filter_node_status", "dst_node_status", "CiNodeStatus"),
    ("ci_operator_reports", "filter_operator_reports", "dst_operator_reports", "CiOperatorReport"),
    ("hydro_readings", "filter_hydro_readings", "dst_hydro_readings", "HydroReading"),
]


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def wait(resp: requests.Response, hdr: dict, want_result: bool = False):
    if resp.status_code != 202:
        return resp
    op = resp.headers["x-ms-operation-id"]
    for _ in range(120):
        time.sleep(3)
        r = requests.get(f"{API}/operations/{op}", headers=hdr, timeout=60).json()
        if r.get("status") not in ("NotStarted", "Running"):
            if r.get("status") != "Succeeded":
                sys.exit(f"Operacja {r.get('status')}: {json.dumps(r.get('error'), ensure_ascii=False)[:800]}")
            break
    else:
        sys.exit("Przekroczono czas oczekiwania na operacje Fabric.")
    return requests.get(f"{API}/operations/{op}/result", headers=hdr, timeout=300) if want_result else r


def build_topology(workspace_id: str, kql_database_id: str) -> dict:
    sources = [{"name": SOURCE, "type": "CustomEndpoint", "properties": {}}]
    streams = [{
        "name": STREAM, "type": "DefaultStream", "properties": {},
        "inputNodes": [{"name": SOURCE}],
    }]
    operators = []
    destinations = []
    for value, fnode, dnode, table in ROUTES:
        operators.append({
            "name": fnode, "type": "Filter",
            "inputNodes": [{"name": STREAM}],
            "properties": {"conditions": [{
                "column": {"expressionType": "ColumnReference", "node": STREAM,
                           "columnName": "stream", "columnPathSegments": []},
                "operatorType": "Equals",
                # dataType to indeks enuma, nie nazwa - API odrzuca nazwy typow.
                # 0=BigInt, 1=Float, 2=Nvarchar(max), 3=DateTime. Kolumna `stream`
                # jest tekstowa, wiec literal musi byc 2; przy 0 filtr porownuje
                # tekst z liczba i cicho odrzuca wszystkie zdarzenia.
                "value": {"dataType": 2, "value": value},
            }]},
        })
        destinations.append({
            "name": dnode, "type": "Eventhouse",
            "inputNodes": [{"name": fnode}],
            "properties": {
                "dataIngestionMode": "ProcessedIngestion",
                "workspaceId": workspace_id,
                # itemId to identyfikator bazy KQL, nie Eventhouse'u
                "itemId": kql_database_id,
                "databaseName": DB_NAME,
                "tableName": table,
                "inputSerialization": {"type": "Json", "properties": {"encoding": "UTF8"}},
            },
        })
    return {"sources": sources, "destinations": destinations, "streams": streams,
            "operators": operators, "compatibilityLevel": "1.1"}


def parts_payload(topology: dict) -> list[dict]:
    files = {
        "eventstream.json": json.dumps(topology, indent=2, ensure_ascii=False),
        "eventstreamProperties.json": json.dumps(
            {"retentionTimeInDays": 1, "eventThroughputLevel": "Low"}, indent=2),
        ".platform": json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Eventstream", "displayName": ES_NAME, "description": ES_DESC},
            "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
        }, indent=2, ensure_ascii=False),
    }
    return [{"path": p, "payload": base64.b64encode(t.encode("utf-8")).decode("ascii"),
             "payloadType": "InlineBase64"} for p, t in files.items()]


def find_existing(ws: str, hdr: dict) -> str | None:
    r = requests.get(f"{API}/workspaces/{ws}/eventstreams", headers=hdr, timeout=120)
    r.raise_for_status()
    item = next((i for i in r.json().get("value", []) if i["displayName"] == ES_NAME), None)
    return item["id"] if item else None


def show_keys(ws: str, esid: str, hdr: dict) -> None:
    r = requests.get(f"{API}/workspaces/{ws}/eventstreams/{esid}/topology", headers=hdr, timeout=120)
    if r.status_code != 200:
        print(f"  (topology {r.status_code}: {r.text[:200]})")
        return
    for src in r.json().get("sources", []):
        c = requests.get(f"{API}/workspaces/{ws}/eventstreams/{esid}/sources/{src['id']}/connection",
                         headers=hdr, timeout=120)
        if c.status_code != 200:
            print(f"  (connection {c.status_code}: {c.text[:200]})")
            continue
        body = c.json()
        keys = body.get("accessKeys", {})
        print(f"\n  Zrodlo {src['name']}:")
        print(f"    EVENTHUB_NAME           = {body.get('eventHubName')}")
        print(f"    EVENTHUB_CONNECTION_STR = {keys.get('primaryConnectionString')}")


def wait_stable(ws: str, esid: str, hdr: dict, timeout: int = 600) -> None:
    """Czeka, az wszystkie wezly wyjda ze stanow przejsciowych.

    Fabric odrzuca `updateDefinition`, jesli ktorykolwiek wezel jest w stanie
    `Creating`/`Updating` - przebudowa topologii wymaga usuniecia starych wezlow.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{API}/workspaces/{ws}/eventstreams/{esid}/topology", headers=hdr, timeout=120)
        if r.status_code != 200:
            time.sleep(10)
            continue
        topo = r.json()
        busy = {n["name"]: n.get("status")
                for k in ("sources", "destinations")
                for n in topo.get(k, [])
                if n.get("status") in ("Creating", "Updating", "Deleting")}
        if not busy:
            return
        print(f"  czekam na stabilizacje wezlow: {busy}")
        time.sleep(15)
    print("  UWAGA: wezly nadal w stanie przejsciowym, probuje mimo to")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keys", action="store_true", help="wypisz connection string i zakoncz")
    args = ap.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, dbid = state["workspaceId"], state["kqlDatabaseId"]
    hdr = {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}

    if args.keys:
        esid = state.get("eventstreamId") or find_existing(ws, hdr)
        if not esid:
            sys.exit(f"Brak Eventstreamu {ES_NAME}.")
        show_keys(ws, esid, hdr)
        return

    topology = build_topology(ws, dbid)
    print(f"Topologia: {len(topology['sources'])} zrodlo, {len(topology['operators'])} filtrow, "
          f"{len(topology['destinations'])} destynacji")
    for _, _, dnode, table in ROUTES:
        print(f"  {dnode} -> {DB_NAME}.{table}")
    if args.dry_run:
        print(json.dumps(topology, indent=2, ensure_ascii=False))
        return

    parts = parts_payload(topology)
    esid = find_existing(ws, hdr)
    if esid:
        print(f"Aktualizuje istniejacy Eventstream {esid}")
        wait_stable(ws, esid, hdr)
        r = requests.post(f"{API}/workspaces/{ws}/eventstreams/{esid}/updateDefinition",
                          headers=hdr, json={"definition": {"parts": parts}}, timeout=300)
        if r.status_code not in (200, 202):
            sys.exit(f"updateDefinition {r.status_code}: {r.text[:1500]}")
        wait(r, hdr)
    else:
        print("Tworze Eventstream")
        r = requests.post(f"{API}/workspaces/{ws}/eventstreams", headers=hdr, json={
            "displayName": ES_NAME, "description": ES_DESC,
            "definition": {"parts": parts},
        }, timeout=300)
        if r.status_code not in (200, 201, 202):
            sys.exit(f"create {r.status_code}: {r.text[:1500]}")
        res = wait(r, hdr, want_result=True)
        esid = (r.json() if r.status_code in (200, 201) else res.json()).get("id") or find_existing(ws, hdr)

    # odczyt zwrotny
    d = requests.post(f"{API}/workspaces/{ws}/eventstreams/{esid}/getDefinition", headers=hdr, timeout=300)
    d = wait(d, hdr, want_result=True) if d.status_code == 202 else d
    got = next(p for p in d.json()["definition"]["parts"] if p["path"] == "eventstream.json")
    topo = json.loads(base64.b64decode(got["payload"]).decode("utf-8"))
    print(f"Odczyt zwrotny: {len(topo['sources'])} zrodel, {len(topo['operators'])} operatorow, "
          f"{len(topo['destinations'])} destynacji")
    for d_ in topo["destinations"]:
        print(f"  {d_['name']} -> {d_['properties'].get('tableName')}")

    state["eventstreamId"] = esid
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGotowe. eventstreamId = {esid}")
    print("Connection string do symulatora: python deploy/12_eventstream.py --keys")


if __name__ == "__main__":
    main()
