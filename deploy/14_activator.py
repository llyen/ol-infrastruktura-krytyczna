"""Data Activator (Reflex) - siedem regul alertowych wg `activator/RULES.md`.

Format definicji (`ReflexEntities.json`) to plaska lista encji powiazanych
przez `uniqueIdentifier`. Dla kazdej reguly powstaja trzy encje:

    kqlSource-v1      zapytanie KQL uruchamiane cyklicznie na bazie Eventhouse
    timeSeriesView-v1 zdarzenie zrodlowe (`SourceEvent`) wskazujace to zapytanie
    timeSeriesView-v1 regula (`EventTrigger`) z warunkiem i akcja Teams

Cala logika progu siedzi w KQL (funkcje `ActivatorR*` z `activator/queries.kql`),
bo zapytanie zwraca wiersz wylacznie wtedy, gdy regula ma sie odpalic. Warunek
w regule sprawdza tylko techniczna kolumne `alert > 0` - Activator wymaga
warunku liczbowego i nie da sie go pominac.

Uzycie:
    python deploy/14_activator.py                      # kotwica: szczyt scenariusza
    python deploy/14_activator.py --anchor now         # kotwica: biezacy czas scenariusza
    python deploy/14_activator.py --recipient a@b.pl   # odbiorca alertow
    python deploy/14_activator.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess
import sys
import time
import uuid

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
QUERIES = ROOT / "activator" / "queries.kql"
API = "https://api.fabric.microsoft.com/v1"

REFLEX_NAME = "act_efekt_domina"
REFLEX_DESC = "Reguly alertowe kaskady infrastruktury krytycznej (R1-R7)"
DB_NAME = "CriticalInfrastructure"
TEMPLATE_VERSION = "1.2.6"
INTERVAL_SECONDS = 300

# Definicje regul. `call` przyjmuje kotwice czasowa: funkcje bez parametru `at`
# ignoruja ja, bo licza po oknie kroczacym.
#   headline   - naglowek alertu
#   message    - tresc; {pole} podstawiane jest z wiersza wyniku zapytania
#   context    - kolumny dolaczane jako "dodatkowe informacje" w karcie alertu
RULES = [
    {
        "id": "R1",
        "name": "R1 - Kaskada wykryta",
        "call": lambda at: "ActivatorR1Cascade()",
        "headline": "Efekt domina: kaskada awarii infrastruktury krytycznej",
        "message": ("Awaria {node_name} ({node_type}) pociagnela {children} obiektow "
                    "w {systems_hit} systemach IK. Srednie opoznienie skutku: {avg_delay_h} h."),
        "context": ["node_id", "node_name", "system_code", "voivodeship_code",
                    "operator_name", "children", "systems_hit", "avg_delay_h"],
    },
    {
        "id": "R2",
        "name": "R2 - Skutek trzeciego rzedu",
        "call": lambda at: "ActivatorR2ThirdOrder()",
        "headline": "Zdarzenie przekroczylo trzeci rzad skutkow",
        "message": ("Kaskada od {node_name} siega fali {cascade_max_wave} i obejmuje "
                    "{cascade_systems} systemow IK ({cascade_population} osob). "
                    "Rekomendacja: rozwazyc SPO-1 (posiedzenie RZZK) i SPO-12 (obieg informacji)."),
        "context": ["node_id", "node_name", "voivodeship_code", "cascade_max_wave",
                    "cascade_systems", "cascade_population"],
    },
    {
        "id": "R3",
        "name": "R3 - Paliwo w agregacie na wyczerpaniu",
        "call": lambda at: f"ActivatorR3Fuel(6.0, {at})",
        "headline": "Paliwo w agregacie na wyczerpaniu",
        "message": ("{node_name}: paliwo w agregacie na {backup_fuel_hours_left} h. "
                    "Obsluguje {population_served} odbiorcow. Operator: {operator_name}."),
        "context": ["node_id", "node_name", "criticality_class", "voivodeship_code",
                    "powiat_code", "operator_name", "backup_fuel_hours_left", "population_served"],
    },
    {
        "id": "R4",
        "name": "R4 - Woda przestanie plynac",
        "call": lambda at: f"ActivatorR4Water(12.0, {at})",
        "headline": "Prognoza utraty zasilania obiektu wodociagowego",
        "message": ("Prognoza: {any_target_name} straci zasilanie za {hours_left} h. "
                    "Ludnosc: {any_population}. Uruchomic dystrybucje wody butelkowanej (SPO-2)."),
        "context": ["node_id", "any_target_name", "any_target_type", "any_criticality",
                    "any_population", "hours_left", "sources_down"],
    },
    {
        "id": "R5",
        "name": "R5 - Obiekt K1 bez umowy SPO-10",
        "call": lambda at: f"ActivatorR5NoSpo10({at})",
        "headline": "Awaria obiektu K1 bez umowy o wymianie danych",
        "message": ("Awaria obiektu K1 {node_name}, operator {operator_name}, brak umowy "
                    "o wymianie danych (SPO-10). Kontakt wymaga trybu awaryjnego."),
        "context": ["node_id", "node_name", "system_code", "voivodeship_code",
                    "operator_name", "ownership", "population_served"],
    },
    {
        "id": "R6",
        "name": "R6 - Wiele systemow IK w jednym wojewodztwie",
        "call": lambda at: "ActivatorR6Footprint(4)",
        "headline": "Wiele systemow IK dotknietych w jednym wojewodztwie",
        "message": ("{voivodeship_code}: dotkniete {systems_affected} z 11 systemow IK, "
                    "{k1_affected} obiektow K1, {population_served} osob. "
                    "Sugerowany poziom: {escalation_hint}."),
        "context": ["voivodeship_code", "nodes_affected", "systems_affected",
                    "k1_affected", "population_served", "escalation_hint"],
    },
    {
        "id": "R7",
        "name": "R7 - Anomalia liczby awarii",
        "call": lambda at: f"ActivatorR7Anomaly(2.0, {at})",
        "headline": "Anomalia liczby awarii w systemie IK",
        "message": ("System {system_code}: {nodes_down} nowych awarii wobec spodziewanych "
                    "{baseline} (wskaznik {anomaly_score}). Sprawdzic, czy to zdarzenie "
                    "naturalne, czy dzialanie celowe (Z04/Z16)."),
        "context": ["system_code", "nodes_down", "baseline", "anomaly_score"],
    },
]


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def signed_in_user() -> str:
    out = subprocess.run(["az", "account", "show", "--query", "user.name", "-o", "tsv"],
                         capture_output=True, text=True, shell=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def uid(seed: str) -> str:
    """Deterministyczny identyfikator encji - dzieki temu ponowne wdrozenie
    podmienia te same reguly zamiast tworzyc duplikaty."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ol-ik-activator/{seed}"))


def text_parts(template: str, fields: list[str]) -> list[dict]:
    """Zamienia szablon '... {pole} ...' na liste fragmentow tekstu przeplatanych
    odwolaniami do kolumn zdarzenia."""
    parts: list[dict] = []
    rest = template
    while True:
        i = rest.find("{")
        if i < 0:
            break
        j = rest.find("}", i)
        if j < 0:
            break
        field = rest[i + 1:j]
        if i:
            parts.append({"type": "string", "value": rest[:i]})
        if field not in fields:
            sys.exit(f"Szablon odwoluje sie do kolumny '{field}', ktorej nie ma w wyniku zapytania")
        parts.append({"kind": "EventFieldReference", "type": "complex",
                      "arguments": [{"name": "fieldName", "type": "string", "value": field}]})
        rest = rest[j + 1:]
    if rest:
        parts.append({"type": "string", "value": rest})
    return parts


def build_entities(ws: str, dbid: str, anchor: str, recipient: str,
                   columns: dict[str, list[str]]) -> list[dict]:
    container_id = uid("container")
    entities: list[dict] = [{
        "uniqueIdentifier": container_id,
        "payload": {"name": "Kaskada IK - reguly alertowe",
                    "description": REFLEX_DESC,
                    "type": "kqlQueries"},
        "type": "container-v1",
    }]

    for rule in RULES:
        rid = rule["id"]
        src_id, evt_id, rule_id = uid(f"{rid}/source"), uid(f"{rid}/event"), uid(f"{rid}/rule")
        query = rule["call"](anchor)
        cols = columns[rid]

        entities.append({
            "uniqueIdentifier": src_id,
            "payload": {
                "name": rule["name"],
                "runSettings": {"executionIntervalInSeconds": INTERVAL_SECONDS},
                "query": {"queryString": query},
                "eventhouseItem": {"itemId": dbid, "workspaceId": ws,
                                   "itemType": "KustoDatabase"},
                "queryParameters": [],
                "parentContainer": {"targetUniqueIdentifier": container_id},
            },
            "type": "kqlSource-v1",
        })

        source_event = {
            "templateId": "SourceEvent", "templateVersion": TEMPLATE_VERSION,
            "steps": [{
                "name": "SourceEventStep", "id": uid(f"{rid}/event/step"),
                "rows": [{"name": "SourceSelector", "kind": "SourceReference",
                          "arguments": [{"name": "entityId", "type": "string", "value": src_id}]}],
            }],
        }
        entities.append({
            "uniqueIdentifier": evt_id,
            "payload": {"name": rule["name"],
                        "parentContainer": {"targetUniqueIdentifier": container_id},
                        "definition": {"type": "Event", "instance": json.dumps(source_event)}},
            "type": "timeSeriesView-v1",
        })

        additional = [{
            "kind": "NameReferencePair", "type": "complex",
            "arguments": [
                {"name": "name", "type": "string", "value": c},
                {"kind": "EventFieldReference", "name": "reference", "type": "complexReference",
                 "arguments": [{"name": "fieldName", "type": "string", "value": c}]},
            ],
        } for c in rule["context"]]

        trigger = {
            "templateId": "EventTrigger", "templateVersion": TEMPLATE_VERSION,
            "steps": [
                {"name": "FieldsDefaultsStep", "id": uid(f"{rid}/rule/fields"),
                 "rows": [{"name": "EventSelector", "kind": "Event", "arguments": [
                     {"kind": "EventReference", "type": "complex", "name": "event",
                      "arguments": [{"name": "entityId", "type": "string", "value": evt_id}]}]}]},
                {"name": "EventDetectStep", "id": uid(f"{rid}/rule/detect"),
                 "rows": [
                     {"name": "EventFieldSelector", "kind": "EventField",
                      "arguments": [{"name": "fieldName", "type": "string", "value": "alert"}]},
                     {"name": "NumberValueCondition", "kind": "NumberValueCondition",
                      "arguments": [{"name": "op", "type": "string", "value": "IsGreaterThan"},
                                    {"name": "threshold", "type": "number", "value": 0}]}]},
                {"name": "ActStep", "id": uid(f"{rid}/rule/act"),
                 "rows": [{"name": "TeamsBinding", "kind": "TeamsMessage", "arguments": [
                     {"name": "messageLocale", "type": "string", "value": "pl-pl"},
                     {"name": "recipients", "type": "array",
                      "values": [{"type": "string", "value": recipient}]},
                     {"name": "headline", "type": "array",
                      "values": [{"type": "string", "value": rule["headline"]}]},
                     {"name": "optionalMessage", "type": "array",
                      "values": text_parts(rule["message"], cols)},
                     {"name": "additionalInformation", "type": "array", "values": additional},
                 ]}]},
            ],
        }
        entities.append({
            "uniqueIdentifier": rule_id,
            "payload": {"name": rule["name"],
                        "parentContainer": {"targetUniqueIdentifier": container_id},
                        "definition": {"type": "Rule", "instance": json.dumps(trigger),
                                       "settings": {"shouldRun": True,
                                                    "shouldApplyRuleOnUpdate": False}}},
            "type": "timeSeriesView-v1",
        })
    return entities


def probe_columns(cluster: str, anchor: str, tk: str) -> dict[str, list[str]]:
    """Sprawdza, ze kazde zapytanie reguly wykonuje sie i zwraca kolumny, do
    ktorych odwoluja sie szablony tresci alertu. Bez tego blad literowy w nazwie
    kolumny wyszedlby dopiero w tresci alertu u odbiorcy."""
    cols: dict[str, list[str]] = {}
    for rule in RULES:
        query = rule["call"](anchor)
        r = requests.post(f"{cluster}/v1/rest/query",
                          headers={"Authorization": f"Bearer {tk}",
                                   "Content-Type": "application/json"},
                          json={"db": DB_NAME, "csl": f"{query} | take 1"}, timeout=300)
        if r.status_code != 200:
            sys.exit(f"{rule['id']}: zapytanie nie dziala: {r.text[:300]}")
        names = [c["ColumnName"] for c in r.json()["Tables"][0]["Columns"]]
        if "alert" not in names:
            sys.exit(f"{rule['id']}: zapytanie nie zwraca kolumny 'alert'")
        cols[rule["id"]] = names
    return cols


def rows_now(cluster: str, anchor: str, tk: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for rule in RULES:
        r = requests.post(f"{cluster}/v1/rest/query",
                          headers={"Authorization": f"Bearer {tk}",
                                   "Content-Type": "application/json"},
                          json={"db": DB_NAME, "csl": f"{rule['call'](anchor)} | count"}, timeout=300)
        out[rule["id"]] = r.json()["Tables"][0]["Rows"][0][0] if r.status_code == 200 else -1
    return out


def wait(r, hdr, want_result=False):
    if r.status_code != 202:
        return r
    loc = r.headers.get("Location")
    for _ in range(90):
        time.sleep(5)
        o = requests.get(loc, headers=hdr, timeout=120)
        if o.json().get("status") in ("Succeeded", "Failed", "Completed"):
            if o.json().get("status") == "Failed":
                sys.exit(f"Operacja nieudana: {o.text[:800]}")
            break
    return requests.get(loc + "/result", headers=hdr, timeout=180) if want_result else r


def find_existing(ws: str, hdr: dict) -> str | None:
    r = requests.get(f"{API}/workspaces/{ws}/items?type=Reflex", headers=hdr, timeout=120)
    r.raise_for_status()
    for it in r.json().get("value", []):
        if it["displayName"] == REFLEX_NAME:
            return it["id"]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", choices=["peak", "now"], default="peak",
                    help="kotwica czasowa regul: szczyt scenariusza (demo na danych "
                         "statycznych) albo biezacy czas scenariusza (symulator na zywo)")
    ap.add_argument("--recipient", help="adres odbiorcy alertow Teams (domyslnie zalogowany uzytkownik)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, dbid, cluster = state["workspaceId"], state["kqlDatabaseId"], state["kustoQueryUri"]
    anchor = "ScenarioPeak()" if args.anchor == "peak" else "ScenarioNow()"

    recipient = args.recipient or signed_in_user()
    if not recipient or "@" not in recipient:
        sys.exit("Nie udalo sie ustalic odbiorcy alertow - podaj --recipient adres@domena")

    ktk = token("https://kusto.kusto.windows.net")
    print(f"Kotwica: {anchor}, odbiorca: {recipient}")
    print("Sprawdzam zapytania regul...")
    columns = probe_columns(cluster, anchor, ktk)
    counts = rows_now(cluster, anchor, ktk)
    for rule in RULES:
        n = counts[rule["id"]]
        flag = "  " if n > 0 else "  (cisza) "
        print(f"  {rule['id']}: {len(columns[rule['id']])} kolumn, {n} wierszy{flag}")
    silent = [r["id"] for r in RULES if counts[r["id"]] == 0]
    if silent:
        print(f"  UWAGA: przy tej kotwicy nie odpalilyby sie: {', '.join(silent)}")

    entities = build_entities(ws, dbid, anchor, recipient, columns)
    print(f"Encje: {len(entities)} ({len(RULES)} regul x 3 + kontener)")

    if args.dry_run:
        print(json.dumps(entities, indent=2, ensure_ascii=False))
        return

    hdr = {"Authorization": f"Bearer {token('https://api.fabric.microsoft.com')}",
           "Content-Type": "application/json"}
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
                   "platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Reflex", "displayName": REFLEX_NAME, "description": REFLEX_DESC},
        "config": {"version": "2.0", "logicalId": uid("logical")},
    }
    parts = [
        {"path": "ReflexEntities.json",
         "payload": base64.b64encode(json.dumps(entities, ensure_ascii=False).encode("utf-8")).decode(),
         "payloadType": "InlineBase64"},
        {"path": ".platform",
         "payload": base64.b64encode(json.dumps(platform, ensure_ascii=False).encode("utf-8")).decode(),
         "payloadType": "InlineBase64"},
    ]

    rid = find_existing(ws, hdr)
    if rid:
        print(f"Aktualizuje istniejacy Reflex {rid}")
        r = requests.post(f"{API}/workspaces/{ws}/reflexes/{rid}/updateDefinition",
                          headers=hdr, json={"definition": {"parts": parts}}, timeout=300)
        if r.status_code not in (200, 202):
            sys.exit(f"updateDefinition {r.status_code}: {r.text[:1500]}")
        wait(r, hdr)
    else:
        print("Tworze Reflex")
        r = requests.post(f"{API}/workspaces/{ws}/reflexes", headers=hdr, json={
            "displayName": REFLEX_NAME, "description": REFLEX_DESC,
            "definition": {"parts": parts}}, timeout=300)
        if r.status_code not in (200, 201, 202):
            sys.exit(f"create {r.status_code}: {r.text[:1500]}")
        res = wait(r, hdr, want_result=True)
        rid = (r.json() if r.status_code in (200, 201) else res.json()).get("id") or find_existing(ws, hdr)

    d = requests.post(f"{API}/workspaces/{ws}/reflexes/{rid}/getDefinition", headers=hdr, timeout=300)
    d = wait(d, hdr, want_result=True) if d.status_code == 202 else d
    got = next(p for p in d.json()["definition"]["parts"] if p["path"] == "ReflexEntities.json")
    back = json.loads(base64.b64decode(got["payload"]).decode("utf-8"))
    kinds: dict[str, int] = {}
    for e in back:
        kinds[e["type"]] = kinds.get(e["type"], 0) + 1
    print(f"Odczyt zwrotny: {len(back)} encji {kinds}")

    state["reflexId"] = rid
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGotowe. reflexId = {rid}")


if __name__ == "__main__":
    main()
