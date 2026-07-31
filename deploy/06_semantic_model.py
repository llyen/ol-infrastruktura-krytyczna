"""Model semantyczny DirectLake nad lh_ci_graph.

Tabele modelu maja nazwy logiczne (DimNode, FactDependency...), zgodne
z `semantic-model/MODEL.md` i `MEASURES.md`; zrodlem sa tabele Delta.
Kluczowy element: dwie relacje miedzy DimNode a FactDependency — aktywna po
`source_node_id` ("na kogo wplywam") i nieaktywna po `target_node_id`
("od kogo zaleze").
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".fabric" / "deployment.json"
STATE = json.loads(STATE_PATH.read_text(encoding="utf-8"))
WS, LH = STATE["workspaceId"], STATE["lakehouseId"]
API = "https://api.fabric.microsoft.com/v1"
MODEL_NAME = "sm_ci_cascade"

SCHEMAS = json.loads((ROOT / ".fabric" / "schemas.json").read_text(encoding="utf-8"))

TYPE_MAP = {
    "string": "string", "boolean": "boolean", "date": "dateTime", "timestamp": "dateTime",
    "int": "int64", "bigint": "int64", "smallint": "int64", "tinyint": "int64",
    "double": "double", "float": "double",
}

# nazwa w modelu -> tabela Delta
TABLES = {
    "DimNode": "graph_nodes",
    "DimGmina": "dim_gmina",
    "DimPowiat": "dim_powiat",
    "DimVoivodeship": "dim_voivodeship",
    "DimSystem": "dim_ci_system",
    "DimHazard": "dim_hazard",
    "FactDependency": "graph_edges",
    "FactNodeStatus": "fact_node_status_peak",
    "FactCascadeTimeline": "cascade_flood_timeline",
    "FactCascadeWaves": "cascade_waves",
    "FactEffectTree": "cascade_effect_tree",
    "FactGminaTimeToEffect": "cascade_gmina_time_to_effect",
    "FactCascadeCentrality": "cascade_centrality",
    "FactSpof": "single_points_of_failure",
    "FactSpo10": "fact_spo10_cooperation",
    "FactExposure": "fact_node_hazard_exposure",
    "FactWhatIf": "whatif_variants",
    "FactMarginalValue": "whatif_marginal_value",
    "FactSystemSummary": "system_summary",
}

RELATIONSHIPS = [
    # (fromTable, fromColumn, toTable, toColumn, isActive, bothDirections)
    ("FactDependency", "source_node_id", "DimNode", "node_id", True, False),
    ("FactDependency", "target_node_id", "DimNode", "node_id", False, False),
    ("FactNodeStatus", "node_id", "DimNode", "node_id", True, False),
    ("FactCascadeTimeline", "node_id", "DimNode", "node_id", True, False),
    ("FactEffectTree", "node_id", "DimNode", "node_id", True, False),
    ("FactCascadeCentrality", "node_id", "DimNode", "node_id", True, False),
    ("FactSpof", "node_id", "DimNode", "node_id", True, False),
    ("FactSpo10", "node_id", "DimNode", "node_id", True, True),
    ("FactExposure", "node_id", "DimNode", "node_id", True, False),
    ("FactExposure", "hazard_code", "DimHazard", "hazard_code", True, False),
    ("DimNode", "gmina_code", "DimGmina", "gmina_code", True, False),
    ("DimNode", "system_code", "DimSystem", "system_code", True, False),
    ("DimGmina", "powiat_code", "DimPowiat", "powiat_code", True, False),
    ("DimPowiat", "voivodeship_code", "DimVoivodeship", "voivodeship_code", True, False),
    ("FactGminaTimeToEffect", "gmina_code", "DimGmina", "gmina_code", True, False),
    ("FactSystemSummary", "system_code", "DimSystem", "system_code", True, False),
]

FMT_INT = "#,0"
FMT_1DP = "#,0.0"
FMT_PCT = "#,0.0"

MEASURES: list[tuple[str, str, str, str | None]] = [
    # --- 1. Obraz biezacy
    ("DimNode", "Obiekty IK", "COUNTROWS(DimNode)", FMT_INT),
    ("DimNode", "Obiekty niedzialajace",
     'CALCULATE(DISTINCTCOUNT(FactNodeStatus[node_id]), FactNodeStatus[status] = "down")', FMT_INT),
    ("DimNode", "Dostepnosc IK %",
     "VAR Total = [Obiekty IK] RETURN IF(Total = 0, BLANK(), DIVIDE(Total - [Obiekty niedzialajace], Total) * 100)", FMT_PCT),
    ("DimNode", "Obiekty na zasilaniu rezerwowym",
     "CALCULATE(DISTINCTCOUNT(FactNodeStatus[node_id]), FactNodeStatus[on_backup_power] = TRUE())", FMT_INT),
    ("DimNode", "Godziny paliwa - mediana",
     "MEDIANX(FILTER(FactNodeStatus, FactNodeStatus[on_backup_power] = TRUE()), FactNodeStatus[backup_fuel_hours_left])", FMT_1DP),
    ("DimNode", "Obiekty K1 niedzialajace",
     'CALCULATE([Obiekty niedzialajace], DimNode[criticality_class] = "K1")', FMT_INT),

    # --- 2. Kaskada
    ("FactCascadeTimeline", "Obiekty w kaskadzie", "COUNTROWS(FactCascadeTimeline)", FMT_INT),
    ("FactCascadeTimeline", "Skutki wtorne",
     "CALCULATE(COUNTROWS(FactCascadeTimeline), FactCascadeTimeline[wave] > 0)", FMT_INT),
    ("FactCascadeTimeline", "Zdarzenia inicjujace",
     "CALCULATE(COUNTROWS(FactCascadeTimeline), FactCascadeTimeline[wave] = 0)", FMT_INT),
    ("FactCascadeTimeline", "Wspolczynnik wzmocnienia",
     "DIVIDE([Obiekty w kaskadzie], [Zdarzenia inicjujace])", FMT_1DP),
    ("FactCascadeTimeline", "Najglebsza fala", "MAX(FactCascadeTimeline[wave])", "0"),
    ("FactCascadeTimeline", "Pierwszy skutek wtorny (h)",
     "CALCULATE(MIN(FactCascadeTimeline[fail_hour]), FactCascadeTimeline[wave] > 0)", FMT_1DP),
    ("FactCascadeTimeline", "Okno reakcji (h)",
     "VAR Pierwszy = [Pierwszy skutek wtorny (h)] "
     "VAR TrzeciRzad = CALCULATE(MIN(FactCascadeTimeline[fail_hour]), FactCascadeTimeline[wave] >= 3) "
     "RETURN TrzeciRzad - Pierwszy", FMT_1DP),
    ("FactCascadeTimeline", "Ludnosc dotknieta",
     'VAR Gminy = CALCULATETABLE(VALUES(FactCascadeTimeline[gmina_code]), '
     'FactCascadeTimeline[system_group] IN {"energy", "water", "health"}) '
     "RETURN SUMX(Gminy, LOOKUPVALUE(DimGmina[population], DimGmina[gmina_code], "
     "FactCascadeTimeline[gmina_code]))", FMT_INT),
    ("FactCascadeTimeline", "Systemy IK dotkniete",
     "DISTINCTCOUNT(FactCascadeTimeline[system_code])", "0"),
    ("FactCascadeTimeline", "Gminy dotkniete",
     "CALCULATE(DISTINCTCOUNT(FactCascadeTimeline[gmina_code]), "
     'FactCascadeTimeline[system_group] IN {"energy", "water", "health"})', FMT_INT),

    # --- 3. Krytycznosc kaskadowa i SPOF
    ("FactCascadeCentrality", "Indeks kaskadowy", "AVERAGE(FactCascadeCentrality[cascade_index])", FMT_1DP),
    ("FactCascadeCentrality", "Indeks kaskadowy - maks.", "MAX(FactCascadeCentrality[cascade_index])", FMT_1DP),
    ("FactCascadeCentrality", "Pojedyncze punkty awarii",
     "CALCULATE(DISTINCTCOUNT(FactCascadeCentrality[node_id]), "
     "FILTER(FactCascadeCentrality, FactCascadeCentrality[cascade_systems] >= 3 "
     "|| FactCascadeCentrality[cascade_population] >= 100000))", FMT_INT),
    ("FactCascadeCentrality", "SPOF bez umowy SPO-10",
     "CALCULATE([Pojedyncze punkty awarii], FactSpo10[data_sharing_agreement] = 0)", FMT_INT),
    ("FactCascadeCentrality", "SPOF poza rejestrem IK",
     "CALCULATE([Pojedyncze punkty awarii], DimNode[on_ci_register] = 0)", FMT_INT),
    ("FactCascadeCentrality", "Najgorszy pojedynczy obiekt - ludnosc",
     "MAX(FactCascadeCentrality[cascade_population])", FMT_INT),
    ("FactCascadeCentrality", "Zasieg miedzysystemowy",
     "MAX(FactCascadeCentrality[cascade_systems])", "0"),

    # --- 4. Zaleznosci i redundancja
    ("FactDependency", "Zaleznosci", "COUNTROWS(FactDependency)", FMT_INT),
    ("FactDependency", "Zaleznosci bez redundancji",
     'CALCULATE(COUNTROWS(FactDependency), FactDependency[redundancy_level] = "none")', FMT_INT),
    ("FactDependency", "Udzial zaleznosci bez redundancji %",
     "DIVIDE([Zaleznosci bez redundancji], [Zaleznosci]) * 100", FMT_PCT),
    ("FactDependency", "Zaleznosci miedzywojewodzkie",
     "CALCULATE(COUNTROWS(FactDependency), FactDependency[cross_voivodeship] = 1)", FMT_INT),
    ("FactDependency", "Zaleznosci niesprawdzone w cwiczeniu %",
     "DIVIDE(CALCULATE(COUNTROWS(FactDependency), FactDependency[verified_in_exercise] = 0), [Zaleznosci]) * 100", FMT_PCT),
    ("FactDependency", "Dostawcy obiektu",
     "CALCULATE(DISTINCTCOUNT(FactDependency[source_node_id]), "
     "USERELATIONSHIP(DimNode[node_id], FactDependency[target_node_id]))", FMT_INT),
    ("DimNode", "Obiekty z jednym zrodlem zasilania",
     "CALCULATE(DISTINCTCOUNT(DimNode[node_id]), DimNode[single_source_power] = 1)", FMT_INT),

    # --- 5. What-if
    ("FactWhatIf", "Redukcja skutkow wtornych %",
     'VAR Baza = CALCULATE(MAX(FactWhatIf[nodes_failed_secondary]), ALL(FactWhatIf), FactWhatIf[variant] = "BAZOWY") '
     "VAR Wariant = SELECTEDVALUE(FactWhatIf[nodes_failed_secondary]) "
     "RETURN DIVIDE(Baza - Wariant, Baza) * 100", FMT_PCT),
    ("FactWhatIf", "Ludnosc uratowana",
     'VAR Baza = CALCULATE(MAX(FactWhatIf[affected_population]), ALL(FactWhatIf), FactWhatIf[variant] = "BAZOWY") '
     "VAR Wariant = SELECTEDVALUE(FactWhatIf[affected_population]) "
     "RETURN Baza - Wariant", FMT_INT),
    ("FactWhatIf", "Efektywnosc wariantu",
     "VAR Interwencje = SELECTEDVALUE(FactWhatIf[hardened_nodes]) + SELECTEDVALUE(FactWhatIf[new_feeds]) "
     'VAR Baza = CALCULATE(MAX(FactWhatIf[nodes_failed_secondary]), ALL(FactWhatIf), FactWhatIf[variant] = "BAZOWY") '
     "VAR Wariant = SELECTEDVALUE(FactWhatIf[nodes_failed_secondary]) "
     "RETURN DIVIDE(Baza - Wariant, Interwencje)", "#,0.00"),
    ("FactMarginalValue", "Najlepsza pojedyncza inwestycja",
     "CONCATENATEX(TOPN(1, FactMarginalValue, FactMarginalValue[nodes_saved], DESC), "
     'FactMarginalValue[node_name] & " (" & FactMarginalValue[nodes_saved] & " obiektow)", ", ")', None),

    # --- 6. Governance SPO-10
    ("DimNode", "Obiekty w rejestrze IK %",
     "DIVIDE(CALCULATE(COUNTROWS(DimNode), DimNode[on_ci_register] = 1), [Obiekty IK]) * 100", FMT_PCT),
    ("DimNode", "Umowy o wymianie danych %",
     "DIVIDE(CALCULATE(COUNTROWS(DimNode), DimNode[spo10_agreement] = 1), [Obiekty IK]) * 100", FMT_PCT),
    ("FactSpo10", "Plany ochrony nieaktualne",
     'CALCULATE(COUNTROWS(FactSpo10), FactSpo10[protection_plan_status] IN {"brak", "w opracowaniu"})', FMT_INT),
    ("FactSpo10", "Responsywnosc operatora", "AVERAGE(FactSpo10[responsiveness_score])", FMT_1DP),
    ("DimNode", "Krytyczne obiekty bez kontaktu operacyjnego",
     'CALCULATE(COUNTROWS(DimNode), DimNode[criticality_class] = "K1", '
     "FactSpo10[contact_point_registered] = 0)", FMT_INT),

    # --- 7. Miary narracyjne
    ("FactCascadeTimeline", "Naglowek kaskady",
     'VAR Ludzie = FORMAT([Ludnosc dotknieta], "#,0") '
     "VAR Systemy = [Systemy IK dotkniete] "
     'VAR Okno = FORMAT([Pierwszy skutek wtorny (h)], "0.0") '
     'RETURN "Bez uslug: " & Ludzie & " mieszkancow | systemy IK: " & Systemy & '
     '" | pierwszy skutek wtorny po " & Okno & " h"', None),
    ("FactCascadeTimeline", "Poziom eskalacji",
     'SWITCH(TRUE(), [Systemy IK dotkniete] >= 6 && [Obiekty K1 niedzialajace] >= 5, "Przeslanka do RZZK (SPO-1)", '
     '[Systemy IK dotkniete] >= 4, "Poziom wojewody", '
     '[Systemy IK dotkniete] >= 2, "Poziom powiatu", "Poziom gminy")', None),
]


def tag() -> str:
    return str(uuid.uuid4())


def build_columns(delta_table: str) -> list[dict]:
    cols = []
    for f in SCHEMAS[delta_table]:
        base = f["type"].split("(")[0]
        dt = TYPE_MAP.get(base)
        if dt is None:
            dt = "decimal" if base.startswith("decimal") else "string"
        col = {
            "name": f["name"],
            "dataType": dt,
            "sourceColumn": f["name"],
            "lineageTag": tag(),
            "summarizeBy": "none",
        }
        if dt == "dateTime":
            col["formatString"] = "yyyy-mm-dd hh:nn:ss"
        cols.append(col)
    return cols


def build_model() -> dict:
    tables = []
    measures_by_table: dict[str, list[dict]] = {}
    for tbl, name, expr, fmt in MEASURES:
        m = {"name": name, "expression": expr, "lineageTag": tag()}
        if fmt:
            m["formatString"] = fmt
        measures_by_table.setdefault(tbl, []).append(m)

    for model_name, delta in TABLES.items():
        if delta not in SCHEMAS:
            raise SystemExit(f"Brak tabeli Delta '{delta}' w schemas.json")
        t = {
            "name": model_name,
            "lineageTag": tag(),
            "columns": build_columns(delta),
            "partitions": [{
                "name": model_name,
                "mode": "directLake",
                "source": {"type": "entity", "entityName": delta,
                           "expressionSource": "DatabaseQuery"},
            }],
        }
        if model_name in measures_by_table:
            t["measures"] = measures_by_table[model_name]
        tables.append(t)

    rels = []
    for i, (ft, fc, tt, tc, active, both) in enumerate(RELATIONSHIPS, start=1):
        for tname, cname in ((ft, fc), (tt, tc)):
            if not any(c["name"] == cname for c in
                       next(x for x in tables if x["name"] == tname)["columns"]):
                raise SystemExit(f"Relacja {i}: brak kolumny {tname}[{cname}]")
        r = {
            "name": f"rel_{i:02d}_{ft}_{fc}_{tt}",
            "fromTable": ft, "fromColumn": fc,
            "toTable": tt, "toColumn": tc,
            "isActive": active,
        }
        if both:
            r["crossFilteringBehavior"] = "bothDirections"
        rels.append(r)

    return {
        "name": MODEL_NAME,
        "compatibilityLevel": 1604,
        "model": {
            "culture": "pl-PL",
            "collation": "Latin1_General_100_BIN2_UTF8",
            "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "pl-PL",
            "expressions": [{
                "name": "DatabaseQuery",
                "kind": "m",
                "lineageTag": tag(),
                "expression": (
                    "let\n"
                    f'    Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{WS}/{LH}")\n'
                    "in\n    Source"
                ),
                "annotations": [{"name": "PBI_IncludeFutureArtifacts", "value": "False"}],
            }],
            "tables": tables,
            "relationships": rels,
            "annotations": [{"name": "PBI_QueryOrder", "value": '["DatabaseQuery"]'}],
        },
    }


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com",
         "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr)
    return out.stdout.strip()


def headers() -> dict:
    return {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


def b64(obj) -> str:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)
    return base64.b64encode(text.encode("utf-8")).decode()


def wait(resp: requests.Response):
    if resp.status_code in (200, 201):
        return resp.json() if resp.content else None
    if resp.status_code == 202:
        op = resp.headers.get("x-ms-operation-id")
        while True:
            time.sleep(5)
            st = requests.get(f"{API}/operations/{op}", headers=headers(), timeout=120).json()
            if st["status"] not in ("NotStarted", "Running"):
                break
        if st["status"] != "Succeeded":
            raise SystemExit(f"Operacja {op}: {st['status']} {json.dumps(st.get('error'), ensure_ascii=False)}")
        return None
    raise SystemExit(f"HTTP {resp.status_code}: {resp.text[:2000]}")


def main() -> None:
    model = build_model()
    (ROOT / ".fabric" / "model.bim").write_text(
        json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    n_meas = sum(len(t.get("measures", [])) for t in model["model"]["tables"])
    print(f"== TMSL: {len(model['model']['tables'])} tabel, "
          f"{len(model['model']['relationships'])} relacji, {n_meas} miar")

    definition = {"parts": [
        {"path": "model.bim", "payload": b64(model), "payloadType": "InlineBase64"},
        {"path": "definition.pbism",
         "payload": b64({"version": "1.0", "settings": {}}), "payloadType": "InlineBase64"},
    ]}

    items = requests.get(f"{API}/workspaces/{WS}/items", headers=headers(), timeout=120).json()
    ex = next((i for i in items["value"]
               if i["displayName"] == MODEL_NAME and i["type"] == "SemanticModel"), None)

    if ex:
        r = requests.post(f"{API}/workspaces/{WS}/semanticModels/{ex['id']}/updateDefinition",
                          headers=headers(), json={"definition": definition}, timeout=600)
        wait(r)
        model_id = ex["id"]
        print(f"   zaktualizowano: {model_id}")
    else:
        body = {"displayName": MODEL_NAME,
                "description": "Efekt domina w infrastrukturze krytycznej — DirectLake nad lh_ci_graph.",
                "definition": definition}
        r = requests.post(f"{API}/workspaces/{WS}/semanticModels", headers=headers(), json=body, timeout=600)
        item = wait(r)
        if item is None:
            items = requests.get(f"{API}/workspaces/{WS}/items", headers=headers(), timeout=120).json()
            item = next(i for i in items["value"]
                        if i["displayName"] == MODEL_NAME and i["type"] == "SemanticModel")
        model_id = item["id"]
        print(f"   utworzono: {model_id}")

    STATE["semanticModelId"] = model_id
    STATE_PATH.write_text(json.dumps(STATE, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nGotowe.")


if __name__ == "__main__":
    main()
