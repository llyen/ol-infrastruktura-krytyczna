"""
Budowa sceny dla aplikacji „Symulator kaskad IK".

Aplikacja nie dostaje gotowych wynikow symulacji, tylko **graf zaleznosci**:
2106 wezlow i 6552 krawedzi. Propagacje liczy przegladarka (`src/data/cascade.ts`,
wierny port `cascade_engine.py`). Powod jest prosty: uzytkownik ma wskazac dowolny
obiekt i zobaczyc skutki, a wyliczenie 2106 kaskad na zapas dawaloby plik nie do
pobrania i tak nie pokryloby przelacznikow „wszystkie agregaty sprawne" ani
suwaka horyzontu.

Graf jest zapisany kolumnowo (tablice tablic), bo forma obiektowa dla 6552
krawedzi to kilkukrotnie wiecej bajtow na te same dane.

    python tools/build_scene.py

Wynik: `public/data/scene.json`.
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parents[1]
REPO = APP_DIR.parents[1]
DATA = REPO / "datasets"
DERIVED = DATA / "derived"
OUT = APP_DIR / "public" / "data" / "scene.json"

FLOOD_FRAME_HOURS = 1.0
FLOOD_FRAMES = 97

# ---------------------------------------------------------------------------
# Korekta wspolrzednych
# ---------------------------------------------------------------------------
#
# Generator zbiorow rozrzuca obiekty losowym odchyleniem wokol srodka
# wojewodztwa i nie sprawdza, czy punkt zostal w kraju. 36 z 2106 wezlow wypada
# poza granica - w Baltyku albo po niemieckiej stronie Odry.
#
# Poprawiamy to **wylacznie w warstwie prezentacji**, przy budowie sceny.
# Zbiory zrodlowe, derived/, notatniki i wyniki symulacji zostaja nietkniete,
# wiec zaden wskaznik ani zadna kotwica regresyjna sie nie zmienia - wspolrzedne
# nie wchodza do propagacji kaskady.

RINGS_FILE = Path(__file__).resolve().parent / "poland_rings.json"
INWARD = 0.06


def _fold(text: str) -> str:
    """Nazwy wojewodztw w zbiorach sa bez znakow diakrytycznych, w granicach - z."""
    text = text.replace("\u0142", "l").replace("\u0141", "L")
    stripped = unicodedata.normalize("NFD", text)
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").lower()


def load_regions() -> dict[str, list[list[list[float]]]]:
    if not RINGS_FILE.exists():
        raise SystemExit(
            f"brak {RINGS_FILE.name} - uruchom najpierw: python tools/build_poland_geo.py"
        )
    with open(RINGS_FILE, encoding="utf-8") as f:
        return {_fold(k): v for k, v in json.load(f).items()}


def in_region(lon: float, lat: float, rings: list[list[list[float]]]) -> bool:
    """Test parzystosci przeciec promienia poziomego."""
    inside = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            if (y1 > lat) != (y2 > lat):
                if lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                    inside = not inside
    return inside


def _km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return math.hypot((lon2 - lon1) * 68.5, (lat2 - lat1) * 111.2)


def snap_into(lon: float, lat: float, rings: list[list[list[float]]]) -> tuple[float, float]:
    """Najblizszy wierzcholek granicy, przesuniety w strone srodka wielokata.

    Przy wklesnych ksztaltach - a takie sa Lubuskie czy Pomorskie - pojedyncze
    zanurzenie potrafi nie wystarczyc, wiec zwiekszamy je, az punkt faktycznie
    znajdzie sie w srodku.
    """
    best_vertex = None
    best_centroid = (lon, lat)
    best_d = float("inf")
    for ring in rings:
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        for x, y in ring:
            d = _km(lon, lat, x, y)
            if d < best_d:
                best_d = d
                best_vertex = (x, y)
                best_centroid = (cx, cy)
    if best_vertex is None:
        return lon, lat

    vx, vy = best_vertex
    cx, cy = best_centroid
    for inward in (INWARD, 0.12, 0.25, 0.5):
        nx = round(vx + (cx - vx) * inward, 3)
        ny = round(vy + (cy - vy) * inward, 3)
        if in_region(nx, ny, rings):
            return nx, ny
    return round(cx, 3), round(cy, 3)


def correct_coordinates(nodes: pd.DataFrame, voiv: pd.DataFrame) -> pd.DataFrame:
    """Przesuwa wezly, ktore wypadly poza wlasne wojewodztwo, do jego wnetrza."""
    regions = load_regions()
    voiv_name = dict(zip(voiv.voivodeship_code, voiv.voivodeship_name.map(_fold)))
    moved: Counter[str] = Counter()

    lats: list[float] = []
    lons: list[float] = []
    for r in nodes.itertuples():
        lon, lat = round(num(r.lon), 5), round(num(r.lat), 5)
        rings = regions.get(voiv_name.get(r.voivodeship_code, ""))
        if rings and not in_region(lon, lat, rings):
            lon, lat = snap_into(lon, lat, rings)
            moved[r.voivodeship_code] += 1
        lons.append(lon)
        lats.append(lat)

    nodes = nodes.copy()
    nodes["lon"] = lons
    nodes["lat"] = lats
    print(f"  korekta wspolrzednych: {sum(moved.values())} wezlow, wojewodztwa {dict(moved)}")
    return nodes



def num(value, default=0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) else f


def main() -> None:
    nodes = pd.read_csv(DATA / "dim_ci_node.csv", dtype=str)
    edges = pd.read_csv(DATA / "fact_ci_dependency.csv", dtype=str)
    systems = pd.read_csv(DATA / "dim_ci_system.csv", dtype=str)
    gminas = pd.read_csv(DATA / "dim_gmina.csv", dtype=str)
    voiv = pd.read_csv(DATA / "dim_voivodeship.csv", dtype=str)
    coop = pd.read_csv(DATA / "fact_spo10_cooperation.csv", dtype=str)
    sysum = pd.read_csv(DERIVED / "system_summary.csv", dtype=str)
    top100 = pd.read_csv(DERIVED / "cascade_top100.csv", dtype=str)
    spof = pd.read_csv(DERIVED / "single_points_of_failure.csv", dtype=str)
    variants = pd.read_csv(DERIVED / "whatif_variants.csv", dtype=str)
    marginal = pd.read_csv(DERIVED / "whatif_marginal_value.csv", dtype=str)
    flood = pd.read_csv(DERIVED / "cascade_flood_timeline.csv", dtype=str)
    summary = json.loads((DERIVED / "cascade_summary.json").read_text(encoding="utf-8"))

    nodes = correct_coordinates(nodes, voiv)

    # ---------------------------------------------------------------- wezly
    coop_by_node = coop.set_index("node_id").to_dict("index")
    gmina_name = dict(zip(gminas.gmina_code, gminas.gmina_name))
    gmina_pop = {r.gmina_code: int(num(r.population)) for r in gminas.itertuples()}

    node_index: dict[str, int] = {}
    node_rows: list[list] = []
    for i, r in enumerate(nodes.itertuples()):
        node_index[r.node_id] = i
        c = coop_by_node.get(r.node_id, {})
        node_rows.append([
            r.node_id,
            r.node_name,
            r.system_code,
            r.system_group,
            r.node_type,
            r.gmina_code,
            r.voivodeship_code,
            round(num(r.lat), 5),
            round(num(r.lon), 5),
            r.criticality_class,
            round(num(r.criticality_score), 1),
            int(num(r.population_served)),
            r.backup_type,
            round(num(r.autonomy_hours), 1),
            round(num(r.fuel_reserve_hours), 1),
            round(num(r.restore_hours), 1),
            r.operator_name,
            int(num(r.on_ci_register)),
            int(num(r.spo10_agreement)),
            int(num(r.in_flood_zone)),
            c.get("protection_plan_status", "brak"),
            int(num(c.get("contact_point_registered"))),
            int(num(c.get("data_sharing_agreement"))),
            round(num(c.get("responsiveness_score")), 1),
            c.get("last_contact_test") or "",
            r.last_exercise_date or "",
        ])

    # -------------------------------------------------------------- krawedzie
    edge_rows: list[list] = []
    for r in edges.itertuples():
        s = node_index.get(r.source_node_id)
        t = node_index.get(r.target_node_id)
        if s is None or t is None:
            continue
        edge_rows.append([
            s,
            t,
            r.dependency_type,
            round(num(r.impact_share), 3),
            round(num(r.lag_hours), 2),
            r.redundancy_level,
        ])

    # ---------------------------------------------------- obraz biezacy (powodz)
    # Kaskada powodziowa rozlozona na klatki godzinowe. Aplikacja odtwarza ja
    # jak strumien: w klatce N widac wezly, ktore padly do godziny N.
    flood_events = []
    for r in flood.itertuples():
        i = node_index.get(r.node_id)
        if i is None:
            continue
        flood_events.append((round(num(r.fail_hour), 2), i, int(num(r.wave))))
    flood_events.sort()

    frames: list[list[list[int]]] = [[] for _ in range(FLOOD_FRAMES)]
    for hour, i, wave in flood_events:
        f = min(FLOOD_FRAMES - 1, int(hour / FLOOD_FRAME_HOURS))
        frames[f].append([i, wave])

    flood_start = flood.fail_time.min()

    # ------------------------------------------------------------- meldunki
    reports = []
    with (DATA / "ci_operator_reports.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            i = node_index.get(r["node_id"])
            if i is None:
                continue
            reports.append([
                r["event_time"],
                i,
                r["report_kind"],
                r["severity"],
                round(num(r.get("eta_restore_hours")), 1),
                int(num(r.get("support_requested"))),
                r.get("channel", ""),
            ])
    reports.sort()
    reports = reports[-600:]

    # ------------------------------------------------------------ plan wzmocnien
    marginal_rows = []
    for r in marginal.itertuples():
        i = node_index.get(r.node_id)
        if i is None:
            continue
        marginal_rows.append([
            i,
            round(num(r.current_autonomy_h), 1),
            int(num(r.nodes_saved)),
            int(num(r.population_saved)),
        ])
    marginal_rows.sort(key=lambda x: (-x[2], -x[3]))

    # ------------------------------------------------------------- luki SPO-10
    gaps_by_operator: dict[str, dict] = defaultdict(
        lambda: {"nodes": 0, "noPlan": 0, "noContact": 0, "noAgreement": 0, "pop": 0, "resp": []}
    )
    for r in nodes.itertuples():
        c = coop_by_node.get(r.node_id, {})
        g = gaps_by_operator[r.operator_name]
        g["nodes"] += 1
        g["pop"] += int(num(r.population_served))
        if c.get("protection_plan_status") != "zatwierdzony":
            g["noPlan"] += 1
        if not int(num(c.get("contact_point_registered"))):
            g["noContact"] += 1
        if not int(num(c.get("data_sharing_agreement"))):
            g["noAgreement"] += 1
        g["resp"].append(num(c.get("responsiveness_score")))

    operators = []
    for name, g in gaps_by_operator.items():
        resp = g.pop("resp")
        operators.append({
            "name": name,
            **g,
            "responsiveness": round(sum(resp) / len(resp), 1) if resp else 0.0,
        })
    operators.sort(key=lambda o: (-(o["noPlan"] + o["noContact"] + o["noAgreement"]), -o["pop"]))

    scene = {
        "meta": {
            "generatedBy": "tools/build_scene.py",
            "nodeCount": len(node_rows),
            "edgeCount": len(edge_rows),
            "floodStart": flood_start,
            "floodFrames": FLOOD_FRAMES,
            "frameHours": FLOOD_FRAME_HOURS,
            "headline": summary["headline"],
            "floodScenario": summary["flood_scenario"],
            "worstSingleNode": summary["worst_single_node_national"],
        },
        "nodeFields": [
            "id", "name", "systemCode", "group", "type", "gmina", "voiv",
            "lat", "lon", "critClass", "critScore", "population",
            "backupType", "autonomyH", "fuelH", "restoreH", "operator",
            "onRegister", "spo10", "inFloodZone",
            "planStatus", "hasContact", "hasAgreement", "responsiveness",
            "lastContactTest", "lastExercise",
        ],
        "nodes": node_rows,
        "edgeFields": ["source", "target", "dependency", "impactShare", "lagHours", "redundancy"],
        "edges": edge_rows,
        "systems": [
            {
                "code": r.system_code,
                "name": r.system_name,
                "group": r.system_group,
                "department": r.responsible_department,
                "spo": r.spo_reference,
            }
            for r in systems.itertuples()
        ],
        "systemStats": [
            {
                "code": r.system_code,
                "nodes": int(num(r.nodes)),
                "k1": int(num(r.k1_nodes)),
                "avgAutonomyH": round(num(r.avg_autonomy_h), 1),
                "noBackup": int(num(r.no_backup_nodes)),
                "singleSourcePower": int(num(r.single_source_power)),
                "onRegisterPct": round(num(r.on_register_pct), 1),
            }
            for r in sysum.itertuples()
        ],
        "voivodeships": [
            {"code": r.voivodeship_code, "name": r.voivodeship_name}
            for r in voiv.itertuples()
        ],
        "gminaNames": gmina_name,
        "gminaPopulation": gmina_pop,
        "floodFrames": frames,
        "reportFields": ["time", "node", "kind", "severity", "etaH", "support", "channel"],
        "reports": reports,
        "topCascade": [
            {
                "node": node_index[r.node_id],
                "cascadeIndex": round(num(r.cascade_index), 2),
                "nodes": int(num(r.cascade_nodes)),
                "population": int(num(r.cascade_population)),
                "systems": int(num(r.cascade_systems)),
                "tier": r.cascade_tier,
                "firstSecondaryHour": round(num(r.first_secondary_hour), 2),
            }
            for r in top100.itertuples()
            if r.node_id in node_index
        ],
        "spof": [
            {
                "node": node_index[r.node_id],
                "fragility": round(num(r.fragility_score), 2),
                "reason": r.spof_reason,
                "cascadeNodes": int(num(r.cascade_nodes)),
                "cascadePopulation": int(num(r.cascade_population)),
            }
            for r in spof.itertuples()
            if r.node_id in node_index
        ][:120],
        "variants": [
            {
                "variant": r.variant,
                "description": r.description,
                "hardenedNodes": int(num(r.hardened_nodes)),
                "newFeeds": int(num(r.new_feeds)),
                "nodesFailed": int(num(r.nodes_failed_total)),
                "nodesSecondary": int(num(r.nodes_failed_secondary)),
                "maxWave": int(num(r.max_wave)),
                "gminas": int(num(r.affected_gminas)),
                "population": int(num(r.affected_population)),
                "k1Failed": int(num(r.k1_nodes_failed)),
                "secondaryReductionPct": round(num(r.secondary_reduction_pct), 1),
                "populationReductionPct": round(num(r.population_reduction_pct), 1),
            }
            for r in variants.itertuples()
        ],
        "marginalFields": ["node", "autonomyH", "nodesSaved", "populationSaved"],
        "marginal": marginal_rows,
        "operators": operators[:60],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(scene, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    size_mb = OUT.stat().st_size / 1024 / 1024
    print(f"scene.json: {size_mb:.2f} MB")
    print(f"  wezly {len(node_rows)}, krawedzie {len(edge_rows)}")
    print(f"  klatki powodzi {FLOOD_FRAMES}, zdarzen {len(flood_events)}")
    print(f"  meldunki {len(reports)}, operatorzy {len(operators)}")
    print(f"  kotwica: skutek pojedynczego wezla = {summary['headline']['people_without_power']} osob")


if __name__ == "__main__":
    main()
