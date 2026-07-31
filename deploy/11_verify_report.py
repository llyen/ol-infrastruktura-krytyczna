"""Weryfikacja raportu rpt_efekt_domina.

Pobiera definicje raportu z Fabric, wyciaga wszystkie odwolania do modelu
semantycznego i sprawdza zapytaniem DAX, ze kazde z nich faktycznie sie
rozwiazuje. Fabric waliduje strukture PBIR przy zapisie, ale nie sprawdza,
czy pole istnieje w modelu - to robi dopiero przegladarka przy otwarciu.

Uzycie:
    python deploy/11_verify_report.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
from collections import defaultdict

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
FABRIC_API = "https://api.fabric.microsoft.com/v1"
PBI_API = "https://api.powerbi.com/v1.0/myorg"


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def get_definition(ws: str, rid: str, tk: str) -> list[dict]:
    hdr = {"Authorization": f"Bearer {tk}"}
    r = requests.post(f"{FABRIC_API}/workspaces/{ws}/reports/{rid}/getDefinition", headers=hdr, timeout=300)
    if r.status_code == 202:
        op = r.headers["x-ms-operation-id"]
        for _ in range(60):
            time.sleep(2)
            s = requests.get(f"{FABRIC_API}/operations/{op}", headers=hdr, timeout=60).json().get("status")
            if s not in ("NotStarted", "Running"):
                break
        r = requests.get(f"{FABRIC_API}/operations/{op}/result", headers=hdr, timeout=300)
    r.raise_for_status()
    return r.json()["definition"]["parts"]


def collect_refs(parts: list[dict]) -> tuple[dict[str, set[str]], dict[str, set[str]], dict]:
    """Zwraca (tabela->kolumny, tabela->miary, statystyki stron)."""
    import base64
    cols: dict[str, set[str]] = defaultdict(set)
    meas: dict[str, set[str]] = defaultdict(set)
    stats: dict[str, int] = defaultdict(int)
    for p in parts:
        if not p["path"].endswith("visual.json"):
            continue
        page = p["path"].split("/")[2]
        doc = json.loads(base64.b64decode(p["payload"]).decode("utf-8"))
        stats[page] += 1
        qs = doc["visual"].get("query", {}).get("queryState", {})
        for block in qs.values():
            for proj in block["projections"]:
                f = proj["field"]
                if "Measure" in f:
                    meas[f["Measure"]["Expression"]["SourceRef"]["Entity"]].add(f["Measure"]["Property"])
                else:
                    c = f["Aggregation"]["Expression"]["Column"] if "Aggregation" in f else f["Column"]
                    cols[c["Expression"]["SourceRef"]["Entity"]].add(c["Property"])
    return cols, meas, stats


def dax(ws: str, sm: str, tk: str, query: str) -> tuple[bool, str]:
    r = requests.post(f"{PBI_API}/groups/{ws}/datasets/{sm}/executeQueries",
                      headers={"Authorization": f"Bearer {tk}", "Content-Type": "application/json"},
                      json={"queries": [{"query": query}]}, timeout=300)
    if r.status_code != 200:
        try:
            det = r.json()["error"]["pbi.error"]["details"]
            msg = "; ".join(d["detail"]["value"] for d in det)
        except Exception:
            msg = r.text[:300]
        return False, msg
    return True, ""


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, sm, rid = state["workspaceId"], state["semanticModelId"], state.get("reportId")
    if not rid:
        sys.exit("Brak reportId w .fabric/deployment.json - uruchom najpierw deploy/10_report.py")

    print(f"Raport {rid}")
    parts = get_definition(ws, rid, token("https://api.fabric.microsoft.com"))
    cols, meas, stats = collect_refs(parts)
    print(f"  {len(parts)} czesci, {len(stats)} stron, {sum(stats.values())} wizualizacji")
    for page in sorted(stats):
        print(f"    {page}: {stats[page]} wiz.")

    tk = token("https://analysis.windows.net/powerbi/api")
    ok = fail = 0
    problems: list[str] = []

    print("\nKolumny:")
    for tbl in sorted(cols):
        sel = ", ".join(f'"{c}", \'{tbl}\'[{c}]' for c in sorted(cols[tbl]))
        good, msg = dax(ws, sm, tk, f"EVALUATE TOPN(1, SELECTCOLUMNS('{tbl}', {sel}))")
        n = len(cols[tbl])
        if good:
            ok += n
            print(f"  OK   {tbl}: {n} kolumn")
        else:
            fail += n
            print(f"  BLAD {tbl}: {n} kolumn -> {msg}")
            problems.append(f"{tbl} (kolumny): {msg}")

    print("\nMiary:")
    for tbl in sorted(meas):
        for m in sorted(meas[tbl]):
            good, msg = dax(ws, sm, tk, f'EVALUATE ROW("v", \'{tbl}\'[{m}])')
            if good:
                ok += 1
                print(f"  OK   {tbl}[{m}]")
            else:
                fail += 1
                print(f"  BLAD {tbl}[{m}] -> {msg}")
                problems.append(f"{tbl}[{m}]: {msg}")

    print(f"\nWynik: {ok}/{ok + fail} odwolan rozwiazuje sie w modelu")
    if problems:
        print("\nDo naprawy:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"https://app.powerbi.com/groups/{ws}/reports/{rid}")


if __name__ == "__main__":
    main()
