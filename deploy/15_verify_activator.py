"""Weryfikacja Data Activatora: pobiera definicje z Fabric i sprawdza, ze graf
encji jest spojny, a kazda regula da sie faktycznie wykonac.

Kontrole:
  1. kazda regula wskazuje istniejace zdarzenie, a ono - istniejace zapytanie
  2. kazde zapytanie KQL wykonuje sie i zwraca kolumne `alert`
  3. kazde odwolanie do kolumny w tresci alertu istnieje w wyniku zapytania
  4. kazda regula ma warunek i akcje z odbiorca
  5. reguly sa wlaczone (`shouldRun`)

Uzycie:
    python deploy/15_verify_activator.py
"""

from __future__ import annotations

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
DB_NAME = "CriticalInfrastructure"


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def rows_of(step: dict, kind: str) -> list[dict]:
    return [r for r in step.get("rows", []) if r.get("kind") == kind]


def arg(row: dict, name: str):
    for a in row.get("arguments", []):
        if a.get("name") == name:
            return a.get("value", a.get("values"))
    return None


def field_refs(values: list) -> list[str]:
    """Wyciaga nazwy kolumn z fragmentow tresci alertu i z dodatkowych informacji."""
    out: list[str] = []
    for v in values or []:
        if not isinstance(v, dict):
            continue
        if v.get("kind") == "EventFieldReference":
            out += [a["value"] for a in v.get("arguments", []) if a.get("name") == "fieldName"]
        for a in v.get("arguments", []):
            if isinstance(a, dict) and a.get("kind") == "EventFieldReference":
                out += [x["value"] for x in a.get("arguments", []) if x.get("name") == "fieldName"]
    return out


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, cluster = state["workspaceId"], state["kustoQueryUri"]
    rid = state.get("reflexId")
    if not rid:
        sys.exit("Brak reflexId - uruchom najpierw deploy/14_activator.py")

    hdr = {"Authorization": f"Bearer {token('https://api.fabric.microsoft.com')}",
           "Content-Type": "application/json"}
    r = requests.post(f"{API}/workspaces/{ws}/reflexes/{rid}/getDefinition", headers=hdr, timeout=300)
    if r.status_code == 202:
        loc = r.headers["Location"]
        for _ in range(60):
            time.sleep(5)
            if requests.get(loc, headers=hdr, timeout=120).json().get("status") in ("Succeeded", "Failed"):
                break
        r = requests.get(loc + "/result", headers=hdr, timeout=180)
    r.raise_for_status()
    part = next(p for p in r.json()["definition"]["parts"] if p["path"] == "ReflexEntities.json")
    entities = json.loads(base64.b64decode(part["payload"]).decode("utf-8"))
    by_id = {e["uniqueIdentifier"]: e for e in entities}

    sources = {e["uniqueIdentifier"]: e for e in entities if e["type"] == "kqlSource-v1"}
    events, rules = {}, {}
    for e in entities:
        if e["type"] != "timeSeriesView-v1":
            continue
        d = e["payload"].get("definition", {})
        inst = json.loads(d["instance"]) if d.get("instance") else {}
        if inst.get("templateId") == "SourceEvent":
            events[e["uniqueIdentifier"]] = (e, inst)
        elif inst.get("templateId") == "EventTrigger":
            rules[e["uniqueIdentifier"]] = (e, inst, d.get("settings", {}))

    print(f"Encje: {len(entities)} | zapytania: {len(sources)} | zdarzenia: {len(events)} "
          f"| reguly: {len(rules)}")

    ktk = token("https://kusto.kusto.windows.net")
    problems: list[str] = []
    ok = 0

    for rule_id, (ent, inst, settings) in sorted(rules.items(), key=lambda x: x[1][0]["payload"]["name"]):
        name = ent["payload"]["name"]
        steps = {s["name"]: s for s in inst.get("steps", [])}

        # 1. regula -> zdarzenie -> zapytanie
        sel = rows_of(steps.get("FieldsDefaultsStep", {}), "Event")
        evt_id = None
        for row in sel:
            for a in row.get("arguments", []):
                if a.get("kind") == "EventReference":
                    evt_id = next(x["value"] for x in a["arguments"] if x["name"] == "entityId")
        if evt_id not in events:
            problems.append(f"{name}: regula nie wskazuje istniejacego zdarzenia")
            continue
        _, evt_inst = events[evt_id]
        src_row = evt_inst["steps"][0]["rows"][0]
        src_id = arg(src_row, "entityId")
        if src_id not in sources:
            problems.append(f"{name}: zdarzenie nie wskazuje istniejacego zapytania KQL")
            continue
        query = sources[src_id]["payload"]["query"]["queryString"]

        # 2. zapytanie sie wykonuje i ma kolumne `alert`
        qr = requests.post(f"{cluster}/v1/rest/query",
                           headers={"Authorization": f"Bearer {ktk}",
                                    "Content-Type": "application/json"},
                           json={"db": DB_NAME, "csl": f"{query} | take 1"}, timeout=300)
        if qr.status_code != 200:
            problems.append(f"{name}: zapytanie nie dziala: {qr.text[:200]}")
            continue
        cols = {c["ColumnName"] for c in qr.json()["Tables"][0]["Columns"]}
        if "alert" not in cols:
            problems.append(f"{name}: zapytanie nie zwraca kolumny 'alert'")

        # 3. warunek
        detect = steps.get("EventDetectStep", {})
        cond = rows_of(detect, "NumberValueCondition")
        fld = rows_of(detect, "EventField")
        if not cond or not fld:
            problems.append(f"{name}: brak warunku liczbowego")
        else:
            watched = arg(fld[0], "fieldName")
            if watched not in cols:
                problems.append(f"{name}: warunek patrzy na kolumne '{watched}', ktorej nie ma w wyniku")

        # 4. akcja i odwolania do kolumn w tresci
        act = steps.get("ActStep", {})
        teams = rows_of(act, "TeamsMessage")
        if not teams:
            problems.append(f"{name}: brak akcji")
        else:
            recips = arg(teams[0], "recipients") or []
            if not recips:
                problems.append(f"{name}: akcja bez odbiorcy")
            refs = set(field_refs(arg(teams[0], "optionalMessage")) +
                       field_refs(arg(teams[0], "additionalInformation")))
            missing = sorted(refs - cols)
            if missing:
                problems.append(f"{name}: tresc alertu odwoluje sie do nieistniejacych kolumn: {missing}")

        # 5. regula wlaczona
        if not settings.get("shouldRun"):
            problems.append(f"{name}: regula jest wylaczona")

        cr = requests.post(f"{cluster}/v1/rest/query",
                           headers={"Authorization": f"Bearer {ktk}",
                                    "Content-Type": "application/json"},
                           json={"db": DB_NAME, "csl": f"{query} | count"}, timeout=300)
        n = cr.json()["Tables"][0]["Rows"][0][0] if cr.status_code == 200 else -1
        print(f"  {name:42} {len(cols):2} kolumn, {n:4} wierszy teraz")
        ok += 1

    print()
    if problems:
        print(f"NIEPOWODZENIE: {len(problems)} problemow")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print(f"Wszystkie {ok} regul spojne: zapytanie -> zdarzenie -> warunek -> akcja.")


if __name__ == "__main__":
    main()
