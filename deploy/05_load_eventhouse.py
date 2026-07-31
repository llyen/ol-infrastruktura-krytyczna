"""Zaladowanie danych do Eventhouse.

1. Telemetria `ci_node_status.jsonl` (186 MB) trafia do OneLake w blokach.
2. Tabele referencyjne (CiNode, CiDependency, CascadeCentrality) i strumienie
   zdarzen sa pobierane przez Kusto bezposrednio z OneLake (`;impersonate`).
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads((ROOT / ".fabric" / "deployment.json").read_text(encoding="utf-8"))
WS, LH = STATE["workspaceId"], STATE["lakehouseId"]
CLUSTER = STATE["kustoQueryUri"]
DB = "CriticalInfrastructure"
ONELAKE = f"https://onelake.dfs.fabric.microsoft.com/{WS}/{LH}"
CHUNK = 8 * 1024 * 1024


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        raise SystemExit(f"Brak tokenu ({resource}): {out.stderr}")
    return out.stdout.strip()


def upload_chunked(local: Path, remote: str) -> None:
    hdr = {"Authorization": f"Bearer {token('https://storage.azure.com')}"}
    url = f"{ONELAKE}/Files/{remote}"
    r = requests.put(f"{url}?resource=file", headers=hdr, timeout=120)
    if r.status_code not in (201, 202):
        raise SystemExit(f"create {remote}: {r.status_code} {r.text[:400]}")

    size = local.stat().st_size
    pos = 0
    started = time.time()
    with local.open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            r = requests.patch(f"{url}?action=append&position={pos}", headers=hdr,
                               data=block, timeout=600)
            if r.status_code not in (200, 202):
                raise SystemExit(f"append @{pos}: {r.status_code} {r.text[:400]}")
            pos += len(block)
            pct = pos / size * 100
            print(f"\r   {remote}: {pct:5.1f}%  ({pos/1024/1024:.0f}/{size/1024/1024:.0f} MB)",
                  end="", flush=True)
    r = requests.patch(f"{url}?action=flush&position={pos}", headers=hdr, timeout=300)
    if r.status_code not in (200, 202):
        raise SystemExit(f"flush: {r.status_code} {r.text[:400]}")
    print(f"\r   {remote}: gotowe, {size/1024/1024:.0f} MB w {time.time()-started:.0f} s")


def kusto(csl: str, timeout: int = 1800) -> dict:
    hdr = {"Authorization": f"Bearer {token('https://kusto.kusto.windows.net')}",
           "Content-Type": "application/json"}
    r = requests.post(f"{CLUSTER}/v1/rest/mgmt", headers=hdr,
                      json={"db": DB, "csl": csl}, timeout=timeout)
    if r.status_code != 200:
        raise SystemExit(f"KQL HTTP {r.status_code}: {r.text[:1500]}")
    return r.json()


def kusto_query(csl: str) -> list:
    hdr = {"Authorization": f"Bearer {token('https://kusto.kusto.windows.net')}",
           "Content-Type": "application/json"}
    r = requests.post(f"{CLUSTER}/v1/rest/query", headers=hdr,
                      json={"db": DB, "csl": csl}, timeout=600)
    if r.status_code != 200:
        raise SystemExit(f"KQL HTTP {r.status_code}: {r.text[:1500]}")
    tbl = next(t for t in r.json()["Tables"] if t["TableName"] in ("Table_0", "PrimaryResult"))
    return tbl["Rows"]


def ingest(table: str, remote: str, fmt: str, mapping: str | None = None) -> None:
    src = f"{ONELAKE}/Files/{remote};impersonate"
    opts = [f"format='{fmt}'"]
    if fmt == "csv":
        opts.append("ignoreFirstRecord=true")
    if mapping:
        opts.append(f"ingestionMappingReference='{mapping}'")
    csl = f".ingest into table {table} ('{src}') with ({', '.join(opts)})"
    kusto(csl)
    print(f"   {table} <- {remote}")


def main() -> None:
    print("== Telemetria do OneLake")
    tel = ROOT / "datasets" / "ci_node_status.jsonl"
    if tel.exists():
        upload_chunked(tel, "raw/streams/ci_node_status.jsonl")
    else:
        print("   BRAK pliku — uruchom generate_datasets.py")

    print("== Tabele referencyjne")
    for table, remote in [
        ("CiNode", "raw/dimensions/dim_ci_node.csv"),
        ("CiDependency", "raw/dimensions/fact_ci_dependency.csv"),
        ("CascadeCentrality", "raw/derived/cascade_centrality.csv"),
    ]:
        kusto(f".clear table {table} data")
        ingest(table, remote, "csv")

    print("== Strumienie zdarzen")
    for table, remote, mapping in [
        ("CiNodeStatus", "raw/streams/ci_node_status.jsonl", "CiNodeStatusMapping"),
        ("CiOperatorReport", "raw/streams/ci_operator_reports.jsonl", "CiOperatorReportMapping"),
        ("HydroReading", "raw/streams/hydro_readings.jsonl", "HydroReadingMapping"),
    ]:
        kusto(f".clear table {table} data")
        ingest(table, remote, "multijson", mapping)

    print("== Kontrola liczebnosci")
    for t in ("CiNode", "CiDependency", "CascadeCentrality",
              "CiNodeStatus", "CiOperatorReport", "HydroReading"):
        n = kusto_query(f"{t} | count")[0][0]
        print(f"   {t:<20} {n:>9}")

    print("== Widok materializowany CiNodeCurrent")
    rows = kusto_query("CiNodeCurrent | summarize c=count() by status | order by c desc")
    for status, c in rows:
        print(f"   {status:<14} {c:>6}")

    print("== Funkcja FuelRunout(6h) — kolejka dowozu paliwa")
    rows = kusto_query("FuelRunout(6.0) | count")
    print(f"   wezlow ponizej 6 h paliwa: {rows[0][0]}")

    print("\nGotowe.")


if __name__ == "__main__":
    main()
