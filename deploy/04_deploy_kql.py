"""Wdrozenie bazy KQL w Eventhouse: tabele, update policies, widoki materializowane.

Skrypty 01 i 02 zawieraja polecenia sterujace i sa wykonywane przez
`.execute database script`. Skrypty 03 i 04 to biblioteki zapytan — trafiaja
do workspace jako KQL Queryset.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".fabric" / "deployment.json"
STATE = json.loads(STATE_PATH.read_text(encoding="utf-8"))
WS = STATE["workspaceId"]
EH = STATE["eventhouseId"]
API = "https://api.fabric.microsoft.com/v1"
DB_NAME = "CriticalInfrastructure"


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"Brak tokenu ({resource}): {out.stderr}")
    return out.stdout.strip()


def fab_headers() -> dict:
    return {"Authorization": f"Bearer {token('https://api.fabric.microsoft.com')}",
            "Content-Type": "application/json"}


def wait(resp: requests.Response):
    if resp.status_code in (200, 201):
        return resp.json() if resp.content else None
    if resp.status_code == 202:
        op = resp.headers.get("x-ms-operation-id")
        while True:
            time.sleep(5)
            st = requests.get(f"{API}/operations/{op}", headers=fab_headers(), timeout=120).json()
            if st["status"] not in ("NotStarted", "Running"):
                break
        if st["status"] != "Succeeded":
            raise SystemExit(f"Operacja {op}: {st['status']} {st.get('error')}")
        return None
    raise SystemExit(f"HTTP {resp.status_code}: {resp.text[:900]}")


# --------------------------------------------------------------------------
# 1. Baza KQL
# --------------------------------------------------------------------------
def ensure_database() -> dict:
    items = requests.get(f"{API}/workspaces/{WS}/items", headers=fab_headers(), timeout=120).json()
    db = next((i for i in items.get("value", [])
               if i["displayName"] == DB_NAME and i["type"] == "KQLDatabase"), None)
    if not db:
        body = {
            "displayName": DB_NAME,
            "description": "Stan biezacy obiektow IK, meldunki SPO-10, hydrologia, detekcja kaskad.",
            "creationPayload": {"databaseType": "ReadWrite", "parentEventhouseItemId": EH},
        }
        r = requests.post(f"{API}/workspaces/{WS}/kqlDatabases", headers=fab_headers(), json=body, timeout=300)
        db = wait(r)
        if db is None:
            items = requests.get(f"{API}/workspaces/{WS}/items", headers=fab_headers(), timeout=120).json()
            db = next(i for i in items["value"] if i["displayName"] == DB_NAME and i["type"] == "KQLDatabase")
        print(f"   baza {DB_NAME} utworzona: {db['id']}")
    else:
        print(f"   baza {DB_NAME} istnieje: {db['id']}")
    return db


# --------------------------------------------------------------------------
# 2. Wykonanie skryptow sterujacych
# --------------------------------------------------------------------------
def kusto_mgmt(cluster: str, database: str, csl: str) -> dict:
    hdr = {"Authorization": f"Bearer {token('https://kusto.kusto.windows.net')}",
           "Content-Type": "application/json"}
    r = requests.post(f"{cluster}/v1/rest/mgmt", headers=hdr,
                      json={"db": database, "csl": csl}, timeout=600)
    if r.status_code != 200:
        raise SystemExit(f"KQL HTTP {r.status_code}: {r.text[:2000]}")
    return r.json()


def run_script(cluster: str, path: Path) -> None:
    script = path.read_text(encoding="utf-8")
    csl = ".execute database script with (ContinueOnErrors=false) <|\n" + script
    res = kusto_mgmt(cluster, DB_NAME, csl)
    rows = res["Tables"][0]["Rows"]
    cols = [c["ColumnName"] for c in res["Tables"][0]["Columns"]]
    idx_ok = cols.index("Succeeded") if "Succeeded" in cols else None
    idx_res = cols.index("Result") if "Result" in cols else None
    failed = [r for r in rows if idx_ok is not None and r[idx_ok] is False]
    print(f"   {path.name}: {len(rows)} polecen, bledow {len(failed)}")
    for f in failed[:5]:
        print(f"      BLAD: {f[idx_res] if idx_res is not None else f}")
    if failed:
        raise SystemExit(f"{path.name} zakonczony bledami.")


# --------------------------------------------------------------------------
# 3. Biblioteka zapytan
# --------------------------------------------------------------------------
def ensure_queryset(db_id: str) -> None:
    import base64
    parts = []
    for name in ("03_dashboard_queries.kql", "04_cascade_detection.kql"):
        parts.append(f"// ==== {name} ====\n" + (ROOT / "kql" / name).read_text(encoding="utf-8"))
    content = {
        "queryset": {
            "queries": [
                {"queryName": "03 — kafle dashboardu", "queryText": parts[0]},
                {"queryName": "04 — detekcja kaskad", "queryText": parts[1]},
            ]
        },
        "dataSources": [
            {"clusterUri": STATE["kustoQueryUri"], "databaseName": DB_NAME,
             "databaseItemId": db_id, "type": "KustoDatabase"}
        ],
    }
    payload = base64.b64encode(json.dumps(content, ensure_ascii=False).encode()).decode()
    body = {
        "displayName": "Zapytania — infrastruktura krytyczna",
        "description": "Kafle dashboardu operacyjnego i detekcja kaskad.",
        "definition": {"parts": [
            {"path": "RealTimeQueryset.json", "payload": payload, "payloadType": "InlineBase64"}]},
    }
    items = requests.get(f"{API}/workspaces/{WS}/items", headers=fab_headers(), timeout=120).json()
    ex = next((i for i in items["value"]
               if i["displayName"] == body["displayName"] and i["type"] == "KQLQueryset"), None)
    if ex:
        r = requests.post(f"{API}/workspaces/{WS}/items/{ex['id']}/updateDefinition",
                          headers=fab_headers(), json={"definition": body["definition"]}, timeout=300)
        if r.status_code in (200, 202):
            wait(r)
            print("   queryset zaktualizowany")
        else:
            print(f"   aktualizacja querysetu pominieta (HTTP {r.status_code})")
        return
    r = requests.post(f"{API}/workspaces/{WS}/kqlQerysets", headers=fab_headers(), json=body, timeout=300)
    if r.status_code == 404:
        r = requests.post(f"{API}/workspaces/{WS}/kqlQuerysets", headers=fab_headers(), json=body, timeout=300)
    if r.status_code in (200, 201, 202):
        wait(r)
        print("   queryset utworzony")
    else:
        print(f"   queryset pominiety (HTTP {r.status_code})")


def main() -> None:
    print("== Baza KQL")
    db = ensure_database()

    detail = requests.get(f"{API}/workspaces/{WS}/kqlDatabases/{db['id']}",
                          headers=fab_headers(), timeout=120).json()
    cluster = detail["properties"]["queryServiceUri"]
    STATE["kqlDatabaseId"] = db["id"]
    STATE["kustoQueryUri"] = cluster
    STATE["kustoIngestUri"] = detail["properties"]["ingestionServiceUri"]
    STATE_PATH.write_text(json.dumps(STATE, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   cluster: {cluster}")

    print("== Skrypty sterujace")
    for name in ("01_create_tables.kql", "02_update_policies.kql", "04_cascade_detection.kql"):
        run_script(cluster, ROOT / "kql" / name)

    print("== Kontrola")
    res = kusto_mgmt(cluster, DB_NAME, ".show tables | project TableName | order by TableName asc")
    tables = [r[0] for r in res["Tables"][0]["Rows"]]
    print(f"   tabele ({len(tables)}): {', '.join(tables)}")

    res = kusto_mgmt(cluster, DB_NAME, ".show materialized-views | project Name")
    print(f"   widoki materializowane: {[r[0] for r in res['Tables'][0]['Rows']]}")

    res = kusto_mgmt(cluster, DB_NAME, ".show functions | project Name")
    print(f"   funkcje: {[r[0] for r in res['Tables'][0]['Rows']]}")

    print("== Biblioteka zapytan")
    ensure_queryset(db["id"])
    print("\nGotowe.")


if __name__ == "__main__":
    main()
