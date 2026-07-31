"""Data Agent "Zapytaj o infrastrukture krytyczna" wg `ai/DATA_AGENT.md`.

Definicja elementu `DataAgent` sklada sie z:

    Files/Config/data_agent.json                        wersja schematu
    Files/Config/draft/stage_config.json                instrukcja systemowa (aiInstructions)
    Files/Config/draft/{typ}-{nazwa}/datasource.json    zrodlo danych + wybrane elementy
    .platform

Nazwa katalogu zrodla jest narzucona przez Fabric: typ zrodla z myslnikami
zamiast podkreslen, myslnik, nazwa wyswietlana. Plik zapisany pod inna sciezka
jest po cichu odrzucany - `updateDefinition` zwraca 202, a przy odczycie
zwrotnym zrodla po prostu nie ma.

Uzycie:
    python deploy/16_data_agent.py
    python deploy/16_data_agent.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
SPEC = ROOT / "ai" / "DATA_AGENT.md"
API = "https://api.fabric.microsoft.com/v1"

AGENT_NAME = "agent_infrastruktura_krytyczna"
AGENT_DESC = "Data Agent: pytania o zaleznosci, kaskady i gotowosc infrastruktury krytycznej"
DB_NAME = "CriticalInfrastructure"

SCHEMA_AGENT = ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/"
                "definition/dataAgent/2.1.0/schema.json")
SCHEMA_STAGE = ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/"
                "definition/stageConfiguration/1.0.0/schema.json")
SCHEMA_SOURCE = ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/"
                 "definition/dataSource/1.0.0/schema.json")

# Tabele Lakehouse podpiete do agenta - pytania analityczne i "co jesli".
LAKEHOUSE_TABLES = [
    "graph_nodes", "graph_edges", "dependency_matrix",
    "cascade_centrality", "cascade_effect_tree", "cascade_flood_timeline",
    "cascade_waves", "cascade_by_system", "cascade_by_voivodeship",
    "single_points_of_failure", "spo10_gaps", "system_summary",
    "whatif_variants", "whatif_marginal_value",
]

# Tabele Eventhouse podpiete do agenta - pytania o stan biezacy.
# Funkcje KQL walidujemy, ale NIE dodajemy jako `elements`: backend Data Agenta odrzuca
# elementy typu `kusto.functions` (updateDefinition konczy sie UnknownError), mimo ze
# schemat je dopuszcza. Zamiast tego ich sygnatury opisujemy w `KUSTO_HINT`.
KUSTO_TABLES = ["CiNodeStatus", "CiOperatorReport", "CiNode", "CiDependency", "CascadeCentrality"]
KUSTO_FUNCTIONS = ["CiNodeAt", "FuelRunout", "CascadeForecast", "CascadePath",
                   "CascadeFootprint", "CriticalNodesDown", "OutageAnomaly",
                   "ScenarioNow", "ScenarioPeak"]

LAKEHOUSE_HINT = (
    "Wyniki notebookow analitycznych: graf zaleznosci, symulacja kaskady i warianty "
    "hardeningu. To sa SYMULACJE, a nie stan faktyczny - nigdy nie przedstawiaj ich "
    "jako zdarzen, ktore juz nastapily. `cascade_effect_tree` opisuje skutki wtorne "
    "awarii pojedynczego obiektu, `whatif_variants` porownuje warianty inwestycyjne, "
    "`spo10_gaps` pokazuje operatorow bez umowy o wymianie danych."
)
KUSTO_HINT = (
    "Stan biezacy z telemetrii. Dane sa datowane na wrzesien 2026, wiec `now()` i `ago()` "
    "nie zwroca niczego - uzywaj funkcji zegara scenariusza: `ScenarioNow()` (najnowsze "
    "zdarzenie), `ScenarioPeak()` (szczyt kryzysu) oraz `CiNodeAt(at)` (stan obiektow na "
    "zadany moment). Do pytania \"dlaczego to padlo\" uzyj `CascadePath(node_id)`. "
    "`CiNodeStatus` powtarza status co godzine, wiec liczba wierszy nie jest liczba awarii.\n"
    "Baza ma gotowe funkcje - wywoluj je zamiast pisac logike od zera:\n"
    "- `ScenarioNow()` / `ScenarioPeak()` - kotwice czasowe scenariusza (datetime).\n"
    "- `CiNodeAt(at:datetime)` - stan wszystkich obiektow na zadany moment.\n"
    "- `CriticalNodesDown(at:datetime)` - obiekty krytyczne w awarii na dany moment.\n"
    "- `CascadePath(node_id:string)` - lancuch przyczyn awarii danego obiektu.\n"
    "- `CascadeForecast(node_id:string)` - prognoza dalszej propagacji kaskady.\n"
    "- `CascadeFootprint(node_id:string)` - zasieg skutkow (gminy, ludnosc).\n"
    "- `FuelRunout(at:datetime)` - przewidywany czas wyczerpania paliwa w agregatach.\n"
    "- `OutageAnomaly(at:datetime, min_outages:int)` - anomalia tempa nowych awarii."
)
MODEL_HINT = (
    "Model semantyczny DirectLake z miarami gotowymi do porownan i wskaznikow. "
    "Uzywaj go do pytan o agregaty i udzialy zamiast liczyc je recznie z tabel."
)


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def instructions() -> str:
    """Wyciaga instrukcje systemowa z `ai/DATA_AGENT.md` - sekcja zapisana jako cytat
    blokowy, zeby specyfikacja i wdrozenie nie rozjechaly sie w czasie."""
    text = SPEC.read_text(encoding="utf-8")
    m = re.search(r"## Instrukcja systemowa agenta\s*\n(.*?)(?=\n## )", text, re.S)
    if not m:
        sys.exit("Nie znalazlem sekcji 'Instrukcja systemowa agenta' w ai/DATA_AGENT.md")
    lines = []
    for line in m.group(1).splitlines():
        s = line.strip()
        if s.startswith(">"):
            lines.append(s[1:].strip())
        elif not s:
            lines.append("")
    out = "\n".join(lines).strip()
    if len(out) < 200:
        sys.exit("Instrukcja systemowa wyglada na pusta - sprawdz format sekcji w DATA_AGENT.md")
    return out


def lakehouse_tables(ws: str, lhid: str, hdr: dict) -> set[str]:
    r = requests.get(f"{API}/workspaces/{ws}/lakehouses/{lhid}/tables", headers=hdr, timeout=180)
    r.raise_for_status()
    return {t["name"] for t in r.json().get("data", [])}


def kusto_names(cluster: str, tk: str, what: str) -> set[str]:
    r = requests.post(f"{cluster}/v1/rest/mgmt",
                      headers={"Authorization": f"Bearer {tk}", "Content-Type": "application/json"},
                      json={"db": DB_NAME, "csl": f".show {what}"}, timeout=180)
    r.raise_for_status()
    return {row[0] for row in r.json()["Tables"][0]["Rows"]}


def model_tables(ws: str, smid: str, tk: str) -> set[str]:
    """Nazwy tabel modelu semantycznego. `INFO.TABLES()` nie dziala przez
    executeQueries, wiec bierzemy je z definicji modelu w deploy/06_semantic_model.py."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sm", ROOT / "deploy" / "06_semantic_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return set(mod.TABLES)


def element(name: str, kind: str) -> dict:
    return {"display_name": name, "type": kind, "is_selected": True, "children": []}


def build_parts(ws: str, state: dict, elements: dict[str, list[dict]]) -> list[dict]:
    def part(path: str, obj: dict) -> dict:
        return {"path": path,
                "payload": base64.b64encode(
                    json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")).decode(),
                "payloadType": "InlineBase64"}

    sources = [
        ("lh_ci_graph", "lakehouse_tables", state["lakehouseId"], LAKEHOUSE_HINT,
         "Graf zaleznosci i wyniki symulacji kaskady"),
        (DB_NAME, "kusto", state["kqlDatabaseId"], KUSTO_HINT,
         "Telemetria i stan biezacy obiektow IK"),
        ("sm_ci_cascade", "semantic_model", state["semanticModelId"], MODEL_HINT,
         "Model semantyczny z miarami"),
    ]

    parts = [
        part("Files/Config/data_agent.json", {"$schema": SCHEMA_AGENT}),
        part("Files/Config/draft/stage_config.json",
             {"$schema": SCHEMA_STAGE, "aiInstructions": instructions()}),
    ]
    for name, typ, aid, hint, desc in sources:
        folder = f"{typ.replace('_', '-')}-{name}"
        parts.append(part(f"Files/Config/draft/{folder}/datasource.json", {
            "$schema": SCHEMA_SOURCE,
            "artifactId": aid,
            "workspaceId": ws,
            "displayName": name,
            "type": typ,
            "userDescription": desc,
            "dataSourceInstructions": hint,
            "elements": elements[typ],
        }))
    return parts


def wait(r, hdr, want_result=False):
    if r.status_code != 202:
        return r
    loc = r.headers.get("Location")
    for _ in range(90):
        time.sleep(5)
        o = requests.get(loc, headers=hdr, timeout=120).json()
        if o.get("status") in ("Succeeded", "Completed", "Failed"):
            if o.get("status") == "Failed":
                sys.exit(f"Operacja nieudana: {json.dumps(o)[:800]}")
            break
    return requests.get(loc + "/result", headers=hdr, timeout=180) if want_result else r


def find_existing(ws: str, hdr: dict) -> str | None:
    r = requests.get(f"{API}/workspaces/{ws}/items?type=DataAgent", headers=hdr, timeout=120)
    r.raise_for_status()
    for it in r.json().get("value", []):
        if it["displayName"] == AGENT_NAME:
            return it["id"]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, cluster = state["workspaceId"], state["kustoQueryUri"]
    hdr = {"Authorization": f"Bearer {token('https://api.fabric.microsoft.com')}",
           "Content-Type": "application/json"}
    ktk = token("https://kusto.kusto.windows.net")

    print("Sprawdzam, czy wskazane elementy istnieja w zrodlach...")
    have_lh = lakehouse_tables(ws, state["lakehouseId"], hdr)
    have_kt = kusto_names(cluster, ktk, "tables")
    have_kf = kusto_names(cluster, ktk, "functions")
    have_sm = model_tables(ws, state["semanticModelId"], ktk)

    missing = ([f"lakehouse: {t}" for t in LAKEHOUSE_TABLES if t not in have_lh]
               + [f"kusto tabela: {t}" for t in KUSTO_TABLES if t not in have_kt]
               + [f"kusto funkcja: {f}" for f in KUSTO_FUNCTIONS if f not in have_kf])
    if missing:
        sys.exit("Brakuje elementow w zrodlach:\n  " + "\n  ".join(missing))

    elements = {
        "lakehouse_tables": [element(t, "lakehouse_tables.table") for t in LAKEHOUSE_TABLES],
        "kusto": [element(t, "kusto.table") for t in KUSTO_TABLES],
        "semantic_model": [element(t, "semantic_model.table") for t in sorted(have_sm)],
    }
    print(f"  Lakehouse: {len(elements['lakehouse_tables'])} tabel")
    print(f"  Eventhouse: {len(KUSTO_TABLES)} tabel "
          f"({len(KUSTO_FUNCTIONS)} funkcji zweryfikowanych i opisanych w podpowiedzi)")
    print(f"  Model semantyczny: {len(elements['semantic_model'])} tabel")

    instr = instructions()
    print(f"  Instrukcja systemowa: {len(instr)} znakow")

    parts = build_parts(ws, state, elements)
    if args.dry_run:
        for p in parts:
            print(f"--- {p['path']}")
            print(base64.b64decode(p["payload"]).decode("utf-8")[:900])
        return

    aid = find_existing(ws, hdr)
    if aid:
        print(f"Aktualizuje istniejacego agenta {aid}")
        r = requests.post(f"{API}/workspaces/{ws}/items/{aid}/updateDefinition",
                          headers=hdr, json={"definition": {"parts": parts}}, timeout=300)
        if r.status_code not in (200, 202):
            sys.exit(f"updateDefinition {r.status_code}: {r.text[:1200]}")
        wait(r, hdr)
    else:
        print("Tworze Data Agenta")
        r = requests.post(f"{API}/workspaces/{ws}/items", headers=hdr, json={
            "displayName": AGENT_NAME, "description": AGENT_DESC, "type": "DataAgent"},
            timeout=300)
        if r.status_code not in (200, 201, 202):
            sys.exit(f"create {r.status_code}: {r.text[:1200]}")
        aid = r.json()["id"]
        r = requests.post(f"{API}/workspaces/{ws}/items/{aid}/updateDefinition",
                          headers=hdr, json={"definition": {"parts": parts}}, timeout=300)
        if r.status_code not in (200, 202):
            sys.exit(f"updateDefinition {r.status_code}: {r.text[:1200]}")
        wait(r, hdr)

    # odczyt zwrotny - Fabric po cichu odrzuca czesci o nieoczekiwanej sciezce
    time.sleep(5)
    d = requests.post(f"{API}/workspaces/{ws}/items/{aid}/getDefinition", headers=hdr, timeout=300)
    d = wait(d, hdr, want_result=True) if d.status_code == 202 else d
    got = {p["path"]: json.loads(base64.b64decode(p["payload"]).decode("utf-8"))
           for p in d.json()["definition"]["parts"] if p["path"].endswith(".json")}
    srcs = {p: o for p, o in got.items() if p.endswith("datasource.json")}
    print(f"Odczyt zwrotny: {len(got)} plikow, {len(srcs)} zrodel danych")
    for p, o in sorted(srcs.items()):
        print(f"  {o['displayName']:24} {o['type']:16} {len(o.get('elements', []))} elementow")
    if len(srcs) != 3:
        sys.exit("Nie wszystkie zrodla zostaly przyjete przez Fabric.")
    stage = got.get("Files/Config/draft/stage_config.json", {})
    if not (stage.get("aiInstructions") or "").strip():
        sys.exit("Instrukcja systemowa nie zostala zapisana.")

    state["dataAgentId"] = aid
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGotowe. dataAgentId = {aid}")
    print("Publikacja agenta (przejscie z wersji roboczej do produkcyjnej) odbywa sie w interfejsie.")


if __name__ == "__main__":
    main()
