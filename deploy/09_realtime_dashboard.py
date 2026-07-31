"""Budowa Real-Time Dashboard "Efekt domina — obraz operacyjny" w Microsoft Fabric.

Zrodlem prawdy dla kafli jest plik `kql\\03_dashboard_queries.kql` — skrypt dzieli
go po naglowkach "// --- KAFEL n: tytul" i osadza kazde zapytanie w definicji
`RealTimeDashboard.json` (schema_version 52).

Identyfikatory sa deterministyczne (uuid5 z nazwy), wiec ponowne uruchomienie
aktualizuje istniejacy dashboard zamiast tworzyc duplikat i nie zrywa powiazan
z przypietymi elementami.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".fabric" / "deployment.json"
STATE = json.loads(STATE_PATH.read_text(encoding="utf-8"))
WS = STATE["workspaceId"]
API = "https://api.fabric.microsoft.com/v1"

DASHBOARD_NAME = "Efekt domina — obraz operacyjny"
DB_NAME = "CriticalInfrastructure"
NS = uuid.UUID("6f2a1c7e-0d43-4f8a-9e21-3b7c5d9a1e04")  # stala przestrzen nazw scenariusza

PAGES = [
    ("obraz-operacyjny", "Obraz operacyjny"),
    ("kaskada-decyzje", "Kaskada i decyzje"),
]

# numer kafla -> (strona, layout x/y/szerokosc/wysokosc, typ wizualizacji, opcje)
# Nazwy wlasciwosci wizualizacji sa prefiksowane (map__, multiStat__) — tak jak
# w plikach eksportowanych przez Fabric.
TILE_LAYOUT: dict[int, dict] = {
    1: dict(page=0, x=0, y=0, w=8, h=8, visual="multistat",
            options={"multiStat__labelColumn": "wskaznik",
                     "multiStat__valueColumn": "wartosc",
                     "multiStat__textSize": "auto",
                     "multiStat__displayOrientation": "vertical",
                     "multiStat__slot": {"width": 1, "height": 5},
                     "colorStyle": "light",
                     "colorRulesDisabled": True,
                     "colorRules": []}),
    2: dict(page=0, x=8, y=0, w=16, h=8, visual="bar",
            options={"xColumn": "system", "yColumns": ["down", "degraded"],
                     "seriesColumns": None, "hideLegend": False,
                     "legendLocation": "bottom",
                     "xColumnTitle": "System infrastruktury krytycznej"}),
    3: dict(page=0, x=0, y=8, w=12, h=10, visual="map",
            options={"map__type": "bubble",
                     "map__latitudeColumn": "lat",
                     "map__longitudeColumn": "lon",
                     "map__labelColumn": "node_name",
                     "map__sizeColumn": "population_served",
                     "map__sizeDisabled": False,
                     "map__geoType": "numeric",
                     "map__geoPointColumn": None}),
    4: dict(page=0, x=12, y=8, w=12, h=10, visual="timechart",
            options={"xColumn": "first_down", "yColumns": ["nodes_down"],
                     "seriesColumns": ["system_code"], "hideLegend": False,
                     "legendLocation": "bottom", "xColumnTitle": ""}),
    7: dict(page=0, x=0, y=18, w=10, h=7, visual="column",
            options={"xColumn": "wojewodztwo",
                     "yColumns": ["gauges_alarm", "gauges_warning"],
                     "seriesColumns": None, "hideLegend": False,
                     "legendLocation": "bottom",
                     "xColumnTitle": "Wojewodztwo"}),
    5: dict(page=0, x=10, y=18, w=14, h=7, visual="table", options={}),

    6: dict(page=1, x=0, y=0, w=24, h=9, visual="table", options={}),
    10: dict(page=1, x=0, y=9, w=12, h=8, visual="table", options={}),
    9: dict(page=1, x=12, y=9, w=12, h=8, visual="table", options={}),
    11: dict(page=1, x=0, y=17, w=12, h=8, visual="table", options={}),
    8: dict(page=1, x=12, y=17, w=12, h=8, visual="table", options={}),
}

# Wspolne opcje wykresow — Fabric zapisuje je nawet dla domyslnych ustawien.
CHART_VISUALS = {"bar", "column", "line", "area", "timechart", "anomalychart"}
CHART_DEFAULTS = {
    "multipleYAxes": {
        "base": {"id": "-1", "label": "", "columns": [], "yAxisMaximumValue": None,
                 "yAxisMinimumValue": None, "yAxisScale": "linear", "horizontalLines": []},
        "additional": [],
        "showMultiplePanels": False,
    },
    "xAxisScale": "linear",
    "verticalLine": "",
    "crossFilterDisabled": False,
    "drillthroughDisabled": False,
    "crossFilter": [],
    "drillthrough": [],
}


VALID_VISUALS = {"table", "bar", "column", "line", "area", "timechart", "anomalychart",
                 "map", "multistat", "card", "pie", "scatterchart", "heatmap", "markdownCard"}

# Parametry podstawiane przy kontroli kolumn — odpowiadaja domyslnym ustawieniom
# dashboardu (ostatnia godzina, brak filtrow).
PROBE_PARAMS = ("let _endTime = now();\n"
                "let _startTime = now() - 1h;\n"
                "let _voivodeship = dynamic([]);\n"
                "let _system = dynamic([]);\n")


def kusto_columns(query: str) -> list[str]:
    token_kusto = token("https://kusto.kusto.windows.net")
    r = requests.post(f"{STATE['kustoQueryUri']}/v1/rest/query",
                      headers={"Authorization": f"Bearer {token_kusto}",
                               "Content-Type": "application/json"},
                      json={"db": DB_NAME, "csl": PROBE_PARAMS + query}, timeout=300)
    if r.status_code != 200:
        raise SystemExit(f"Zapytanie kafla nie wykonalo sie: {r.text[:300]}")
    table = next(t for t in r.json()["Tables"]
                 if t["TableName"] in ("Table_0", "PrimaryResult"))
    return [c["ColumnName"] for c in table["Columns"]]


def verify_columns(tiles: dict[int, tuple[str, str]]) -> None:
    """Sprawdza, ze kolumny wskazane w wizualizacji istnieja w wyniku zapytania.

    Fabric waliduje definicje dopiero przy otwarciu dashboardu, wiec literowka
    w nazwie kolumny objawilaby sie dopiero na prezentacji.
    """
    print("== Kontrola kolumn wizualizacji")
    for number, cfg in sorted(TILE_LAYOUT.items()):
        if cfg["visual"] == "table":
            continue
        title, query = tiles[number]
        columns = kusto_columns(query)
        referenced: list[str] = []
        for key, value in cfg["options"].items():
            if not key.endswith(("Column", "Columns")) or value is None:
                continue
            referenced.extend(value if isinstance(value, list) else [value])
        missing = [c for c in referenced if c not in columns]
        status = "BLAD" if missing else "OK  "
        detail = f"brak kolumn: {missing}" if missing else ", ".join(referenced)
        print(f"   {status} kafel {number:>2} ({cfg['visual']:<9}) {detail}")
        if missing:
            raise SystemExit(f"Kafel {number} ({title}) wskazuje nieistniejace kolumny: {missing}")


def det_id(*parts: str) -> str:
    return str(uuid.uuid5(NS, "|".join(parts)))


def token(resource: str) -> str:
    out = subprocess.run(["az", "account", "get-access-token", "--resource", resource,
                          "--query", "accessToken", "-o", "tsv"],
                         capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr)
    return out.stdout.strip()


FAB = None


def headers() -> dict:
    global FAB
    if FAB is None:
        FAB = token("https://api.fabric.microsoft.com")
    return {"Authorization": f"Bearer {FAB}", "Content-Type": "application/json"}


def wait_operation(response: requests.Response) -> None:
    op = response.headers.get("x-ms-operation-id")
    if not op:
        return
    while True:
        time.sleep(4)
        s = requests.get(f"{API}/operations/{op}", headers=headers(), timeout=60).json()
        if s.get("status") not in ("NotStarted", "Running"):
            if s.get("status") != "Succeeded":
                raise SystemExit(f"Operacja nieudana: {json.dumps(s, ensure_ascii=False)[:600]}")
            return


def parse_tiles() -> dict[int, tuple[str, str]]:
    """Zwraca {numer kafla: (tytul, zapytanie)} z pliku kql\\03."""
    text = (ROOT / "kql" / "03_dashboard_queries.kql").read_text(encoding="utf-8")
    tiles: dict[int, tuple[str, str]] = {}
    current: tuple[int, str] | None = None
    buf: list[str] = []

    def flush() -> None:
        if current is not None:
            body = "\n".join(buf).strip()
            if body:
                tiles[current[0]] = (current[1], body)

    for line in text.splitlines():
        m = re.match(r"^//\s*---\s*KAFEL\s+(\d+):\s*(.+?)\s*-*\s*$", line.strip())
        if m:
            flush()
            current = (int(m.group(1)), m.group(2).strip())
            buf = []
            continue
        if line.strip().startswith("//"):
            continue
        buf.append(line)
    flush()
    return tiles


def used_variables(query: str) -> list[str]:
    return [v for v in ("_startTime", "_endTime", "_voivodeship", "_system") if v in query]


def build_definition(tiles: dict[int, tuple[str, str]], datasource_id: str) -> dict:
    pages = [{"name": name, "id": det_id("page", key)} for key, name in PAGES]
    ds = {
        "id": datasource_id,
        "name": DB_NAME,
        "clusterUri": STATE["kustoQueryUri"],
        "database": DB_NAME,
        "kind": "kusto-trident",
        "scopeId": "kusto-trident",
        "workspace": WS,
    }

    queries: list[dict] = []
    tile_defs: list[dict] = []

    for number, cfg in sorted(TILE_LAYOUT.items(), key=lambda kv: (kv[1]["page"], kv[1]["y"], kv[1]["x"])):
        if number not in tiles:
            raise SystemExit(f"Brak kafla {number} w pliku kql\\03_dashboard_queries.kql")
        title, query = tiles[number]
        query_id = det_id("query", str(number))
        queries.append({
            "dataSource": {"kind": "inline", "dataSourceId": datasource_id},
            "text": query,
            "id": query_id,
            "usedVariables": used_variables(query),
        })
        options = dict(CHART_DEFAULTS) if cfg["visual"] in CHART_VISUALS else {}
        options.update(cfg["options"])
        tile_defs.append({
            "id": det_id("tile", str(number)),
            "title": f"{number}. {title}",
            "visualType": cfg["visual"],
            "pageId": pages[cfg["page"]]["id"],
            "layout": {"x": cfg["x"], "y": cfg["y"], "width": cfg["w"], "height": cfg["h"]},
            "queryRef": {"kind": "query", "queryId": query_id},
            "visualOptions": options,
        })

    # Parametry: suwak czasu + dwa filtry wielokrotnego wyboru zasilane zapytaniem.
    voi_query_id = det_id("query", "param-voivodeship")
    sys_query_id = det_id("query", "param-system")
    queries.append({
        "dataSource": {"kind": "inline", "dataSourceId": datasource_id},
        "text": "CiVoivodeship\n| project voivodeship_code, voivodeship_name\n"
                "| order by voivodeship_name asc",
        "id": voi_query_id,
        "usedVariables": [],
    })
    queries.append({
        "dataSource": {"kind": "inline", "dataSourceId": datasource_id},
        "text": "CiSystem\n| project system_code, system_name\n| order by system_code asc",
        "id": sys_query_id,
        "usedVariables": [],
    })

    parameters = [
        {
            "kind": "duration",
            "id": det_id("param", "time"),
            "displayName": "Zakres czasu",
            "description": "Poza oknem danych scenariusza kafle pokazuja szczyt kryzysu.",
            "beginVariableName": "_startTime",
            "endVariableName": "_endTime",
            "defaultValue": {"kind": "dynamic", "count": 1, "unit": "hours"},
            "showOnPages": {"kind": "all"},
        },
        {
            "kind": "string",
            "id": det_id("param", "voivodeship"),
            "displayName": "Wojewodztwo",
            "description": "",
            "variableName": "_voivodeship",
            "selectionType": "array",
            "includeAllOption": True,
            "defaultValue": {"kind": "all"},
            "dataSource": {
                "kind": "query",
                "columns": {"value": "voivodeship_code", "label": "voivodeship_name"},
                "queryRef": {"kind": "query", "queryId": voi_query_id},
                "autoReset": True,
            },
            "showOnPages": {"kind": "all"},
            "allIsNull": True,
        },
        {
            "kind": "string",
            "id": det_id("param", "system"),
            "displayName": "System IK",
            "description": "",
            "variableName": "_system",
            "selectionType": "array",
            "includeAllOption": True,
            "defaultValue": {"kind": "all"},
            "dataSource": {
                "kind": "query",
                "columns": {"value": "system_code", "label": "system_name"},
                "queryRef": {"kind": "query", "queryId": sys_query_id},
                "autoReset": True,
            },
            "showOnPages": {"kind": "all"},
            "allIsNull": True,
        },
    ]

    return {
        "$schema": "https://dataexplorer.azure.com/static/d/schema/52/dashboard.json",
        "id": det_id("dashboard", DASHBOARD_NAME),
        "eTag": '""',
        "schema_version": "52",
        "title": DASHBOARD_NAME,
        "autoRefresh": {"enabled": True, "defaultInterval": "5m", "minInterval": "1m"},
        "baseQueries": [],
        "tiles": tile_defs,
        "dataSources": [ds],
        "pages": pages,
        "parameters": parameters,
        "queries": queries,
    }


def validate(definition: dict) -> None:
    """Kontrole, ktore Fabric wykonuje dopiero przy ladowaniu dashboardu."""
    def check_uuid(value: str, where: str) -> None:
        try:
            uuid.UUID(value)
        except ValueError:
            raise SystemExit(f"{where}: '{value}' nie jest UUID wg RFC 4122")

    for section in ("tiles", "queries", "baseQueries", "parameters", "dataSources", "pages"):
        seen: set[str] = set()
        for entry in definition[section]:
            check_uuid(entry["id"], section)
            if entry["id"] in seen:
                raise SystemExit(f"{section}: zduplikowany identyfikator {entry['id']}")
            seen.add(entry["id"])

    refs: list[str] = [t["queryRef"]["queryId"] for t in definition["tiles"]]
    refs += [b["queryId"] for b in definition["baseQueries"]]
    refs += [p["dataSource"]["queryRef"]["queryId"] for p in definition["parameters"]
             if isinstance(p.get("dataSource"), dict) and "queryRef" in p["dataSource"]]
    if len(refs) != len(set(refs)):
        raise SystemExit("Kazdy queryId musi byc uzyty dokladnie raz")
    query_ids = {q["id"] for q in definition["queries"]}
    if set(refs) != query_ids:
        missing = query_ids ^ set(refs)
        raise SystemExit(f"Niezgodnosc referencji zapytan: {missing}")

    page_ids = {p["id"] for p in definition["pages"]}
    for tile in definition["tiles"]:
        if tile["pageId"] not in page_ids:
            raise SystemExit(f"Kafel {tile['title']} wskazuje nieistniejaca strone")
        if tile["visualType"] not in VALID_VISUALS:
            raise SystemExit(f"Kafel {tile['title']}: nieznany typ wizualizacji "
                             f"'{tile['visualType']}'")

    ds_ids = {d["id"] for d in definition["dataSources"]}
    for q in definition["queries"]:
        if q["dataSource"]["dataSourceId"] not in ds_ids:
            raise SystemExit(f"Zapytanie {q['id']} wskazuje nieistniejace zrodlo danych")


def find_item(name: str, item_type: str) -> dict | None:
    items = requests.get(f"{API}/workspaces/{WS}/items", headers=headers(), timeout=120).json()["value"]
    return next((i for i in items if i["displayName"] == name and i["type"] == item_type), None)


def main() -> None:
    tiles = parse_tiles()
    print(f"== Kafle wczytane z kql\\03_dashboard_queries.kql: {len(tiles)}")
    missing = sorted(set(TILE_LAYOUT) - set(tiles))
    if missing:
        raise SystemExit(f"Brakujace kafle: {missing}")

    existing = find_item(DASHBOARD_NAME, "KQLDashboard")
    datasource_id = det_id("datasource", DB_NAME)
    definition = build_definition(tiles, datasource_id)
    validate(definition)
    print(f"   walidacja przeszla: {len(definition['tiles'])} kafli, "
          f"{len(definition['queries'])} zapytan, {len(definition['pages'])} strony")
    verify_columns(tiles)

    payload = base64.b64encode(
        json.dumps(definition, ensure_ascii=False, indent=2).encode("utf-8")).decode()
    platform = base64.b64encode(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
                   "platformProperties/2.0.0/schema.json",
        "metadata": {"type": "KQLDashboard", "displayName": DASHBOARD_NAME,
                     "description": "Obraz operacyjny kaskady infrastruktury krytycznej."},
        "config": {"version": "2.0", "logicalId": det_id("logical", DASHBOARD_NAME)},
    }, ensure_ascii=False).encode("utf-8")).decode()

    body_definition = {"parts": [
        {"path": "RealTimeDashboard.json", "payload": payload, "payloadType": "InlineBase64"},
        {"path": ".platform", "payload": platform, "payloadType": "InlineBase64"},
    ]}

    if existing:
        print(f"== Aktualizacja istniejacego dashboardu {existing['id']}")
        r = requests.post(f"{API}/workspaces/{WS}/items/{existing['id']}/updateDefinition"
                          "?updateMetadata=True",
                          headers=headers(), json={"definition": body_definition}, timeout=300)
        if r.status_code not in (200, 202):
            raise SystemExit(f"HTTP {r.status_code}: {r.text[:1500]}")
        wait_operation(r)
        item_id = existing["id"]
    else:
        print("== Tworzenie dashboardu")
        r = requests.post(f"{API}/workspaces/{WS}/kqlDashboards", headers=headers(),
                          json={"displayName": DASHBOARD_NAME,
                                "description": "Obraz operacyjny kaskady infrastruktury krytycznej.",
                                "definition": body_definition}, timeout=300)
        if r.status_code not in (200, 201, 202):
            raise SystemExit(f"HTTP {r.status_code}: {r.text[:1500]}")
        wait_operation(r)
        item = find_item(DASHBOARD_NAME, "KQLDashboard")
        if not item:
            raise SystemExit("Dashboard nie pojawil sie w workspace")
        item_id = item["id"]

    # Kontrola: odczyt definicji z Fabric i porownanie liczby kafli.
    d = requests.post(f"{API}/workspaces/{WS}/items/{item_id}/getDefinition",
                      headers=headers(), timeout=300)
    if d.status_code == 202:
        wait_operation(d)
        d = requests.post(f"{API}/workspaces/{WS}/items/{item_id}/getDefinition",
                          headers=headers(), timeout=300)
    part = next(p for p in d.json()["definition"]["parts"] if p["path"] == "RealTimeDashboard.json")
    saved = json.loads(base64.b64decode(part["payload"]).decode("utf-8"))
    print(f"== Kontrola po stronie Fabric")
    print(f"   tytul: {saved.get('title')}")
    print(f"   kafle: {len(saved.get('tiles', []))}, zapytania: {len(saved.get('queries', []))}, "
          f"strony: {len(saved.get('pages', []))}, parametry: {len(saved.get('parameters', []))}")
    for page in saved.get("pages", []):
        count = sum(1 for t in saved["tiles"] if t["pageId"] == page["id"])
        print(f"   strona '{page['name']}': {count} kafli")

    STATE["realtimeDashboardId"] = item_id
    STATE_PATH.write_text(json.dumps(STATE, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDashboard gotowy: {item_id}")


if __name__ == "__main__":
    main()
