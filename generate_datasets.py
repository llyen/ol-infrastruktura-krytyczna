"""Generate deterministic synthetic data for the CRITICAL INFRASTRUCTURE / DOMINO demo.

All data is fictional. Seed=42, UTF-8, synthetic TERYT-like codes.
Scenario axis: POWODZ WRZESIEN (Z02) with secondary Z07, Z12, Z14.
"""
from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

SEED = 42
random.seed(SEED)
rng = np.random.default_rng(SEED)

BASE = Path(__file__).resolve().parent
DATA = BASE / "datasets"
DERIVED = DATA / "derived"
DATA.mkdir(exist_ok=True)
DERIVED.mkdir(exist_ok=True)

TZ = timezone(timedelta(hours=2))
START = datetime(2026, 9, 9, 0, 0, tzinfo=TZ)      # D-3
D0 = datetime(2026, 9, 12, 6, 0, tzinfo=TZ)        # przekroczenie stanow alarmowych
END = datetime(2026, 9, 22, 0, 0, tzinfo=TZ)       # D+10

# wojewodztwa osi scenariusza: dolnoslaskie, opolskie (+ kontekst slaskie, lubuskie)
AXIS = {"02", "16"}
AXIS_CONTEXT = {"24", "08", "32"}


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def write_csv(name: str, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or list(rows[0].keys())
    with (DATA / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(name: str, rows) -> int:
    n = 0
    with (DATA / name).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n


# ---------------------------------------------------------------- geografia
voivs = [
    ("02", "dolnośląskie", 51.1, 16.9), ("04", "kujawsko-pomorskie", 53.0, 18.5),
    ("06", "lubelskie", 51.2, 22.6), ("08", "lubuskie", 52.2, 15.5),
    ("10", "łódzkie", 51.8, 19.5), ("12", "małopolskie", 50.1, 19.9),
    ("14", "mazowieckie", 52.2, 21.0), ("16", "opolskie", 50.7, 17.9),
    ("18", "podkarpackie", 50.0, 22.0), ("20", "podlaskie", 53.1, 23.2),
    ("22", "pomorskie", 54.4, 18.6), ("24", "śląskie", 50.3, 19.0),
    ("26", "świętokrzyskie", 50.9, 20.6), ("28", "warmińsko-mazurskie", 53.8, 20.5),
    ("30", "wielkopolskie", 52.4, 16.9), ("32", "zachodniopomorskie", 53.4, 14.6),
]
voiv_rows = []
for c, n, lat, lon in voivs:
    axis = "POWODZ_WRZESIEN" if c in AXIS else ("context" if c in AXIS_CONTEXT else "national_context")
    voiv_rows.append({"voivodeship_code": c, "voivodeship_name": n, "lat": lat, "lon": lon,
                      "scenario_axis": axis})
write_csv("dim_voivodeship.csv", voiv_rows)
VOIV_NAME = {c: n for c, n, _, _ in voivs}
VOIV_POS = {c: (lat, lon) for c, _, lat, lon in voivs}

pow_counts = {"02": 30, "04": 23, "06": 24, "08": 14, "10": 24, "12": 22, "14": 42, "16": 12,
              "18": 25, "20": 17, "22": 20, "24": 36, "26": 14, "28": 21, "30": 35, "32": 21}
powiats = []
for c, n, lat, lon in voivs:
    for i in range(1, pow_counts[c] + 1):
        suffix = ["północny", "południowy", "wschodni", "zachodni", "centralny", "miejski"][i % 6]
        powiats.append({"powiat_code": f"{c}{i:02d}", "voivodeship_code": c,
                        "powiat_name": f"powiat {n}-{suffix}-{i:02d}",
                        "lat": round(lat + rng.normal(0, .38), 5),
                        "lon": round(lon + rng.normal(0, .55), 5)})
write_csv("dim_powiat.csv", powiats)

extra = 2477 - 6 * len(powiats)
gminas = []
for p_idx, p in enumerate(powiats):
    for j in range(1, 7 + (1 if p_idx < extra else 0)):
        typ = random.choices(["miejska", "miejsko-wiejska", "wiejska"], [.18, .26, .56])[0]
        pop = int(clamp(rng.lognormal(9.0 if typ != "miejska" else 10.2, .62), 1800, 240000))
        code = f"{p['powiat_code']}{j:03d}"[:7]
        gminas.append({
            "gmina_code": code,
            "powiat_code": p["powiat_code"],
            "voivodeship_code": p["voivodeship_code"],
            "gmina_name": f"gmina {p['powiat_name'].split()[-1]}-{j:02d}",
            "gmina_type": typ,
            "population": pop,
            "lat": round(p["lat"] + rng.normal(0, .13), 5),
            "lon": round(p["lon"] + rng.normal(0, .19), 5),
        })
write_csv("dim_gmina.csv", gminas)

GM_BY_VOIV: dict[str, list[dict]] = {}
for g in gminas:
    GM_BY_VOIV.setdefault(g["voivodeship_code"], []).append(g)
GMINA = {g["gmina_code"]: g for g in gminas}

# ---------------------------------------------------------------- zagrozenia KPZK
hazards = [
    ("Z01", "Epidemia", "możliwe", "katastrofalne"), ("Z02", "Powódź", "prawdopodobne", "duże"),
    ("Z03", "Zakłócenie funkcjonowania systemów i sieci teleinformatycznych", "możliwe", "duże"),
    ("Z04", "Działania hybrydowe", "możliwe", "duże"), ("Z05", "Susza/upał", "prawdopodobne", "średnie"),
    ("Z06", "Epizootia", "prawdopodobne", "średnie"),
    ("Z07", "Zakłócenie w systemie energetycznym", "prawdopodobne", "średnie"),
    ("Z08", "Silny wiatr", "prawdopodobne", "średnie"),
    ("Z09", "Zakłócenie w systemie paliwowym", "możliwe", "średnie"),
    ("Z10", "Pożar wielkopowierzchniowy", "możliwe", "średnie"),
    ("Z11", "Epifitoza", "możliwe", "średnie"),
    ("Z12", "Zakłócenie funkcjonowania systemów i usług telekomunikacyjnych", "możliwe", "średnie"),
    ("Z13", "Skażenie chemiczne na lądzie", "rzadkie", "małe"),
    ("Z14", "Zakłócenie w systemie gazowym", "rzadkie", "średnie"),
    ("Z15", "Katastrofa morska", "rzadkie", "średnie"),
    ("Z16", "Zdarzenie o charakterze terrorystycznym", "bardzo rzadkie", "duże"),
    ("Z17", "Skażenie promieniotwórcze", "bardzo rzadkie", "duże"),
    ("Z18", "Zbiorowe zakłócenie porządku publicznego", "prawdopodobne", "małe"),
    ("Z19", "Silny mróz/intensywne opady śniegu", "możliwe", "małe"),
    ("Z20", "Dezinformacja", "nieujęte", "nieujęte"),
]
PROB = {"bardzo rzadkie": 1, "rzadkie": 2, "możliwe": 3, "prawdopodobne": 4, "bardzo prawdopodobne": 5, "nieujęte": 0}
IMPACT = {"nieistotne": 1, "małe": 2, "średnie": 3, "duże": 4, "katastrofalne": 5, "nieujęte": 0}
write_csv("dim_hazard.csv", [
    {"hazard_code": c, "hazard_name": n, "probability_label": p, "impact_label": i,
     "probability_score": PROB[p], "impact_score": IMPACT[i], "risk_score": PROB[p] * IMPACT[i]}
    for c, n, p, i in hazards
])

# ---------------------------------------------------------------- systemy IK
# 11 systemow wg art. 3 pkt 2 ustawy o zarzadzaniu kryzysowym
systems = [
    ("IK01", "Zaopatrzenie w energię, surowce energetyczne i paliwa", "IV Energia", "energy"),
    ("IK02", "Łączność", "XIII Łączność", "telecom"),
    ("IK03", "Sieci teleinformatyczne", "X Informatyzacja", "ict"),
    ("IK04", "Systemy finansowe", "V Finanse publiczne", "finance"),
    ("IK05", "Zaopatrzenie w żywność", "XVII Rolnictwo", "food"),
    ("IK06", "Zaopatrzenie w wodę", "VIII Gospodarka wodna", "water"),
    ("IK07", "Ochrona zdrowia", "IX Zdrowie", "health"),
    ("IK08", "Systemy transportowe", "XXII Transport", "transport"),
    ("IK09", "Systemy ratownicze", "XIX Sprawy wewnętrzne", "rescue"),
    ("IK10", "Ciągłość działania administracji publicznej", "I Administracja publiczna", "admin"),
    ("IK11", "Produkcja, składowanie i stosowanie substancji chemicznych i promieniotwórczych",
     "XXI Środowisko", "chemical"),
]
write_csv("dim_ci_system.csv", [
    {"system_code": c, "system_name": n, "responsible_department": d, "system_group": g,
     "spo_reference": "SPO-10"}
    for c, n, d, g in systems
])
SYS_BY_GROUP = {g: c for c, _, _, g in systems}

# ---------------------------------------------------------------- typy wezlow
# (group, node_type, count, criticality_bias, population_factor, base_autonomy_h, backup_mix)
node_types = [
    ("energy", "stacja NN 400/220 kV", 40, .95, 900000, 0, "dual_feed"),
    ("energy", "GPZ 110/SN", 200, .72, 62000, 0, "dual_feed"),
    ("energy", "elektrownia systemowa", 26, .93, 700000, 0, "onsite_fuel"),
    ("energy", "elektrociepłownia", 34, .70, 95000, 0, "onsite_fuel"),
    ("energy", "tłocznia gazu", 30, .82, 180000, 0, "genset"),
    ("energy", "magazyn/terminal paliw", 44, .74, 260000, 0, "genset"),
    ("energy", "stacja redukcyjna gazu", 46, .55, 48000, 0, "genset"),
    ("telecom", "węzeł szkieletowy telekom", 60, .88, 480000, 8, "genset"),
    ("telecom", "węzeł agregacyjny/RAN hub", 200, .52, 42000, 4, "battery"),
    ("ict", "centrum przetwarzania danych", 44, .90, 1200000, 24, "genset"),
    ("ict", "węzeł sieci rządowej", 56, .78, 300000, 12, "genset"),
    ("ict", "system rejestrów państwowych", 50, .84, 800000, 12, "genset"),
    ("finance", "centrum rozliczeniowe", 18, .86, 1500000, 24, "genset"),
    ("finance", "centrum przetwarzania banku", 40, .64, 420000, 16, "genset"),
    ("finance", "hurtownia wartości/gotówki", 32, .48, 210000, 8, "genset"),
    ("food", "magazyn rezerw strategicznych", 30, .80, 350000, 12, "genset"),
    ("food", "chłodnia składowa", 44, .50, 120000, 6, "genset"),
    ("food", "zakład przetwórstwa spożywczego", 66, .40, 70000, 2, "none"),
    ("water", "ujęcie wody", 90, .66, 58000, 0, "genset"),
    ("water", "stacja uzdatniania wody", 92, .74, 66000, 4, "genset"),
    ("water", "przepompownia wody", 88, .52, 24000, 2, "battery"),
    ("water", "oczyszczalnia ścieków", 34, .58, 82000, 3, "genset"),
    ("health", "szpital wielospecjalistyczny", 62, .92, 190000, 48, "genset"),
    ("health", "szpital powiatowy", 98, .70, 62000, 24, "genset"),
    ("health", "centrum dializ", 46, .66, 900, 6, "genset"),
    ("health", "bank krwi / magazyn farmaceutyczny", 44, .60, 340000, 12, "genset"),
    ("transport", "węzeł kolejowy", 56, .74, 260000, 4, "genset"),
    ("transport", "most/przeprawa krytyczna", 74, .68, 95000, 0, "none"),
    ("transport", "port lotniczy", 15, .80, 600000, 12, "genset"),
    ("transport", "port morski/rzeczny", 12, .62, 180000, 8, "genset"),
    ("transport", "centrum sterowania ruchem", 45, .58, 140000, 6, "genset"),
    ("rescue", "jednostka ratowniczo-gaśnicza PSP", 72, .64, 55000, 12, "genset"),
    ("rescue", "centrum powiadamiania ratunkowego", 18, .94, 1400000, 48, "genset"),
    ("rescue", "baza lotniczego pogotowia", 20, .76, 700000, 24, "genset"),
    ("admin", "centrum zarządzania kryzysowego", 62, .88, 420000, 24, "genset"),
    ("admin", "węzeł teleinformatyczny urzędu", 58, .54, 120000, 6, "genset"),
    ("chemical", "zakład dużego ryzyka (ZDR)", 30, .82, 45000, 8, "genset"),
    ("chemical", "zakład zwiększonego ryzyka (ZZR)", 22, .60, 22000, 6, "genset"),
    ("chemical", "obiekt jądrowy/składowisko odpadów prom.", 8, .96, 30000, 72, "genset"),
]

OPERATORS = {
    "energy": ["Operator Przesyłowy S.A. (fikc.)", "OSD Zachód (fikc.)", "OSD Południe (fikc.)",
               "Gazoprzesył S.A. (fikc.)", "Paliwa Krajowe S.A. (fikc.)"],
    "telecom": ["Telko Alfa S.A. (fikc.)", "Telko Beta S.A. (fikc.)", "Telko Gamma S.A. (fikc.)"],
    "ict": ["Centrum Informatyki Państwowej (fikc.)", "Chmura Krajowa Sp. z o.o. (fikc.)"],
    "finance": ["Izba Rozliczeniowa (fikc.)", "Bank Krajowy S.A. (fikc.)", "Bank Regionalny S.A. (fikc.)"],
    "food": ["Agencja Rezerw (fikc.)", "Sieć Chłodni Polska (fikc.)", "Spółdzielnia Spożywcza (fikc.)"],
    "water": ["Wodociągi Miejskie (fikc.)", "Zakład Wodociągowy Gminny (fikc.)"],
    "health": ["Samodzielny Publiczny ZOZ (fikc.)", "Szpital Wojewódzki (fikc.)", "Sieć Medyczna Vita (fikc.)"],
    "transport": ["Kolej Krajowa S.A. (fikc.)", "Zarząd Dróg (fikc.)", "Porty Lotnicze (fikc.)"],
    "rescue": ["Komenda Wojewódzka PSP (fikc.)", "Urząd Wojewódzki (fikc.)"],
    "admin": ["Urząd Wojewódzki (fikc.)", "Starostwo Powiatowe (fikc.)", "Urząd Gminy (fikc.)"],
    "chemical": ["Zakłady Chemiczne Wisła (fikc.)", "Agencja Materiałów Prom. (fikc.)"],
}
OWNERSHIP_P = {"energy": .70, "telecom": .95, "ict": .35, "finance": .90, "food": .75,
               "water": .15, "health": .25, "transport": .30, "rescue": .02, "admin": .02,
               "chemical": .85}

# gminy najbardziej dotkniete (ogniska powodzi) — pierwsze gminy w wojewodztwach osi
flood_focus = []
for v in ("02", "16"):
    flood_focus.extend([g["gmina_code"] for g in GM_BY_VOIV[v][:190]])
FLOOD_FOCUS = set(flood_focus)

nodes = []
seq = 0
for group, ntype, count, crit_bias, pop_factor, autonomy, backup in node_types:
    sys_code = SYS_BY_GROUP[group]
    for _ in range(count):
        seq += 1
        # rozklad geograficzny: 32% wezlow w wojewodztwach osi scenariusza
        if rng.random() < .32:
            v = "02" if rng.random() < .62 else "16"
        else:
            v = random.choice([c for c, _, _, _ in voivs])
        g = random.choice(GM_BY_VOIV[v])
        crit_raw = clamp(rng.normal(crit_bias, .11), .05, .99)
        crit_class = "K1" if crit_raw >= .80 else "K2" if crit_raw >= .58 else "K3"
        pop = int(clamp(rng.lognormal(math.log(max(pop_factor, 300)), .55), 120, 3_200_000))
        eff_backup = backup
        if backup == "genset" and rng.random() < .16:
            eff_backup = "none"
        if backup == "battery" and rng.random() < .10:
            eff_backup = "none"
        aut = 0.0 if eff_backup == "none" else round(clamp(rng.normal(max(autonomy, 2), max(autonomy, 2) * .30), 0.5, 168), 1)
        if eff_backup == "dual_feed":
            aut = 0.0
        fuel_h = round(aut * rng.uniform(.7, 1.0), 1) if eff_backup in ("genset", "onsite_fuel") else 0.0
        in_flood = g["gmina_code"] in FLOOD_FOCUS and rng.random() < .55
        elev = round(clamp(rng.normal(190 if v in AXIS else 150, 70), 4, 900), 1)
        nodes.append({
            "node_id": f"IK-{sys_code[2:]}-{seq:05d}",
            "node_name": f"{ntype} {g['gmina_name'].split()[-1]}-{seq:05d}",
            "system_code": sys_code,
            "system_group": group,
            "node_type": ntype,
            "gmina_code": g["gmina_code"],
            "powiat_code": g["powiat_code"],
            "voivodeship_code": v,
            "lat": round(g["lat"] + rng.normal(0, .04), 5),
            "lon": round(g["lon"] + rng.normal(0, .06), 5),
            "elevation_m": elev,
            "operator_name": random.choice(OPERATORS[group]),
            "ownership": "prywatna" if rng.random() < OWNERSHIP_P[group] else "publiczna",
            "criticality_class": crit_class,
            "criticality_score": round(crit_raw * 100, 1),
            "population_served": pop,
            "backup_type": eff_backup,
            "autonomy_hours": aut,
            "fuel_reserve_hours": fuel_h,
            "in_flood_zone": int(in_flood),
            "restore_hours": round(clamp(rng.normal(14 if group in ("telecom", "ict") else 26, 9), 2, 96), 1),
            "on_ci_register": int(rng.random() < (.93 if crit_class == "K1" else .74 if crit_class == "K2" else .41)),
            "spo10_agreement": int(rng.random() < (.86 if crit_class == "K1" else .58 if crit_class == "K2" else .27)),
            "last_exercise_date": (START - timedelta(days=int(rng.integers(20, 1300)))).date().isoformat(),
        })

NODES = {n["node_id"]: n for n in nodes}
BY_GROUP: dict[str, list[dict]] = {}
for n in nodes:
    BY_GROUP.setdefault(n["system_group"], []).append(n)


def dist(a: dict, b: dict) -> float:
    return math.hypot((a["lat"] - b["lat"]) * 111.0, (a["lon"] - b["lon"]) * 71.0)


def nearest(target: dict, pool: list[dict], k: int, exclude: set[str] | None = None) -> list[dict]:
    exclude = exclude or set()
    same_voiv = [p for p in pool if p["voivodeship_code"] == target["voivodeship_code"] and p["node_id"] not in exclude]
    pool_eff = same_voiv if len(same_voiv) >= k else [p for p in pool if p["node_id"] not in exclude]
    return sorted(pool_eff, key=lambda p: dist(target, p))[:k]


# ---------------------------------------------------------------- krawedzie zaleznosci
POWER_SOURCES = [n for n in BY_GROUP["energy"] if n["node_type"] in ("GPZ 110/SN", "stacja NN 400/220 kV")]
GPZ = [n for n in BY_GROUP["energy"] if n["node_type"] == "GPZ 110/SN"]
NN = [n for n in BY_GROUP["energy"] if n["node_type"] == "stacja NN 400/220 kV"]
PLANTS = [n for n in BY_GROUP["energy"] if n["node_type"] in ("elektrownia systemowa", "elektrociepłownia")]
FUEL = [n for n in BY_GROUP["energy"] if n["node_type"] in ("magazyn/terminal paliw",)]
GAS = [n for n in BY_GROUP["energy"] if n["node_type"] in ("tłocznia gazu", "stacja redukcyjna gazu")]
TELCO_CORE = [n for n in BY_GROUP["telecom"] if n["node_type"] == "węzeł szkieletowy telekom"]
TELCO = BY_GROUP["telecom"]
ICT = BY_GROUP["ict"]
WATER_SUPPLY = [n for n in BY_GROUP["water"] if n["node_type"] in ("stacja uzdatniania wody", "ujęcie wody")]
TRANSPORT = BY_GROUP["transport"]

# ile zaleznosci danego typu ma wezel danej grupy: (typ, pool, liczba, impact, lag_h, redundancy_p)
DEP_RULES = {
    "telecom": [("electricity", "power", 1, .95, 0.0, .30), ("ict", "ict", 1, .45, 0.5, .40)],
    "ict": [("electricity", "power", 2, .60, 0.0, .70), ("telecom", "telco_core", 1, .70, 0.2, .55)],
    "finance": [("electricity", "power", 2, .55, 0.0, .65), ("telecom", "telco_core", 1, .85, 0.2, .50),
                ("ict", "ict", 1, .60, 0.5, .45)],
    "food": [("electricity", "power", 1, .90, 0.0, .18), ("transport", "transport", 1, .40, 8.0, .30),
             ("water", "water", 1, .35, 4.0, .20)],
    "water": [("electricity", "power", 1, .95, 0.0, .22), ("telecom", "telco", 1, .25, 2.0, .35)],
    "health": [("electricity", "power", 1, .92, 0.0, .34), ("water", "water", 1, .55, 3.0, .12),
               ("telecom", "telco", 1, .40, 1.0, .30), ("transport", "transport", 1, .25, 6.0, .25)],
    "transport": [("electricity", "power", 1, .70, 0.0, .40), ("telecom", "telco", 1, .35, 1.0, .30)],
    "rescue": [("electricity", "power", 1, .70, 0.0, .55), ("telecom", "telco_core", 1, .88, 0.3, .45),
               ("fuel", "fuel", 1, .45, 12.0, .35)],
    "admin": [("electricity", "power", 1, .78, 0.0, .45), ("ict", "ict", 1, .72, 0.5, .40),
              ("telecom", "telco", 1, .50, 0.5, .35)],
    "chemical": [("electricity", "power", 1, .88, 0.0, .48), ("water", "water", 1, .50, 2.0, .25)],
}
POOLS = {"power": GPZ, "ict": ICT, "telco_core": TELCO_CORE, "telco": TELCO,
         "water": WATER_SUPPLY, "transport": TRANSPORT, "fuel": FUEL}

edges = []
eseq = 0


def add_edge(src: dict, dst: dict, dep_type: str, impact: float, lag: float, redundancy: str) -> None:
    global eseq
    if src["node_id"] == dst["node_id"]:
        return
    eseq += 1
    edges.append({
        "edge_id": f"E-{eseq:06d}",
        "source_node_id": src["node_id"],
        "target_node_id": dst["node_id"],
        "source_system": src["system_code"],
        "target_system": dst["system_code"],
        "dependency_type": dep_type,
        "impact_share": round(clamp(impact, .05, 1.0), 3),
        "lag_hours": round(max(lag, 0.0), 2),
        "redundancy_level": redundancy,
        "cross_voivodeship": int(src["voivodeship_code"] != dst["voivodeship_code"]),
        "contract_sla_hours": round(clamp(rng.normal(8, 4), 1, 48), 1),
        "verified_in_exercise": int(rng.random() < .38),
    })


for group, rules in DEP_RULES.items():
    for dst in BY_GROUP[group]:
        for dep_type, pool_key, k, impact, lag, red_p in rules:
            pool = POOLS[pool_key]
            cands = nearest(dst, pool, k + 1, exclude={dst["node_id"]})
            if not cands:
                continue
            redundant = rng.random() < red_p and len(cands) > 1
            chosen = cands[:2] if redundant else cands[:1]
            level = "partial" if redundant else "none"
            if redundant and dst["criticality_class"] == "K1" and rng.random() < .45:
                level = "full"
            share = impact * rng.uniform(.85, 1.12)
            for src in chosen:
                add_edge(src, dst, dep_type,
                         share / (len(chosen) if level != "none" else 1),
                         lag + (0.0 if dep_type == "electricity" else rng.uniform(0, .6)),
                         level)

# zaleznosci wewnatrz systemu energetycznego
for gpz in GPZ:
    for src in nearest(gpz, NN, 2 if rng.random() < .55 else 1, exclude={gpz["node_id"]}):
        add_edge(src, gpz, "electricity", .55, 0.0, "partial" if rng.random() < .55 else "none")
for plant in PLANTS:
    for src in nearest(plant, FUEL + GAS, 1, exclude={plant["node_id"]}):
        add_edge(src, plant, "fuel", .62, round(rng.uniform(18, 60), 1), "partial" if rng.random() < .4 else "none")
for nn in NN:
    for src in nearest(nn, PLANTS, 2, exclude={nn["node_id"]}):
        add_edge(src, nn, "generation", .40, 0.0, "partial")
for f in FUEL + GAS:
    for src in nearest(f, GPZ, 1, exclude={f["node_id"]}):
        add_edge(src, f, "electricity", .80, 0.0, "none" if rng.random() < .5 else "partial")
    for src in nearest(f, TRANSPORT, 1, exclude={f["node_id"]}):
        add_edge(src, f, "transport", .30, round(rng.uniform(6, 24), 1), "partial")

write_csv("dim_ci_node.csv", nodes)
write_csv("fact_ci_dependency.csv", edges)

# ---------------------------------------------------------------- ekspozycja na zagrozenia
HAZ_BY_GROUP = {
    "energy": ["Z07", "Z02", "Z08", "Z16", "Z04"],
    "telecom": ["Z12", "Z07", "Z08", "Z04"],
    "ict": ["Z03", "Z07", "Z04", "Z16"],
    "finance": ["Z03", "Z07", "Z04"],
    "food": ["Z07", "Z02", "Z09"],
    "water": ["Z02", "Z07", "Z05", "Z13"],
    "health": ["Z01", "Z07", "Z02", "Z12"],
    "transport": ["Z02", "Z08", "Z19", "Z07"],
    "rescue": ["Z02", "Z07", "Z12", "Z16"],
    "admin": ["Z03", "Z07", "Z04", "Z02"],
    "chemical": ["Z13", "Z17", "Z10", "Z02"],
}
exposure = []
for n in nodes:
    for hz in HAZ_BY_GROUP[n["system_group"]]:
        base_exp = rng.uniform(.15, .70)
        if hz == "Z02" and n["in_flood_zone"]:
            base_exp = rng.uniform(.72, .97)
        exposure.append({
            "node_id": n["node_id"],
            "hazard_code": hz,
            "exposure_score": round(base_exp * 100, 1),
            "mitigation_level": random.choices(["brak", "częściowe", "pełne"], [.28, .53, .19])[0],
            "assessment_date": (START - timedelta(days=int(rng.integers(15, 700)))).date().isoformat(),
        })
write_csv("fact_node_hazard_exposure.csv", exposure)

# ---------------------------------------------------------------- SPO-10: wspolpraca z operatorami
spo10 = []
for n in nodes:
    if not n["on_ci_register"]:
        continue
    resp = clamp(rng.normal(65 if n["spo10_agreement"] else 34, 18), 3, 100)
    spo10.append({
        "node_id": n["node_id"],
        "operator_name": n["operator_name"],
        "contact_point_registered": int(rng.random() < (.92 if n["spo10_agreement"] else .48)),
        "protection_plan_status": random.choices(
            ["zatwierdzony", "w aktualizacji", "brak"],
            [.62, .27, .11] if n["spo10_agreement"] else [.24, .34, .42])[0],
        "protection_plan_age_days": int(rng.integers(20, 1500)),
        "data_sharing_agreement": n["spo10_agreement"],
        "responsiveness_score": round(resp, 1),
        "last_contact_test": (START - timedelta(days=int(rng.integers(2, 500)))).date().isoformat(),
    })
write_csv("fact_spo10_cooperation.csv", spo10)

# ---------------------------------------------------------------- strumienie real-time
HOURS = int((END - START).total_seconds() // 3600)


def flood_intensity(t: datetime, voiv: str) -> float:
    """0..1 — nasilenie zagrozenia powodziowego w danej chwili i wojewodztwie."""
    h = (t - D0).total_seconds() / 3600
    if voiv == "02":
        peak, width = 6.0, 34.0
    elif voiv == "16":
        peak, width = 26.0, 40.0
    elif voiv in AXIS_CONTEXT:
        peak, width = 54.0, 50.0
    else:
        return 0.02
    return float(clamp(math.exp(-((h - peak) ** 2) / (2 * (width / 2.4) ** 2)), 0, 1))


# wezly, ktore realnie zostana dotkniete (podtopienie) — deterministycznie
impacted = {}
for n in nodes:
    if n["voivodeship_code"] not in AXIS | AXIS_CONTEXT:
        continue
    p = .58 if n["in_flood_zone"] else .05
    p *= 1.25 if n["elevation_m"] < 150 else .8
    if rng.random() < p:
        v = n["voivodeship_code"]
        offset = {"02": 4.0, "16": 24.0}.get(v, 52.0) + float(rng.normal(0, 9))
        impacted[n["node_id"]] = D0 + timedelta(hours=float(clamp(offset, -18, 190)))

NODE_STATUS_NAME = "ci_node_status.jsonl"


def gen_node_status():
    for step in range(HOURS + 1):
        t = START + timedelta(hours=step)
        for n in nodes:
            v = n["voivodeship_code"]
            fi = flood_intensity(t, v)
            fail_at = impacted.get(n["node_id"])
            failed = fail_at is not None and t >= fail_at
            restored = failed and t >= fail_at + timedelta(hours=n["restore_hours"] * rng.uniform(1.4, 3.2))
            if restored:
                status = "degraded" if rng.random() < .25 else "operational"
            elif failed:
                status = "down"
            elif fi > .45 and rng.random() < fi * .22:
                status = "degraded"
            else:
                status = "operational"
            load = clamp(rng.normal(62, 14) + fi * 18, 0, 128)
            if status == "down":
                load = 0.0
            elif status == "degraded":
                load *= rng.uniform(.35, .75)
            on_backup = status in ("down", "degraded") and n["backup_type"] in ("genset", "battery", "onsite_fuel")
            if on_backup and fail_at:
                elapsed = (t - fail_at).total_seconds() / 3600
                fuel_left = round(max(n["fuel_reserve_hours"] - elapsed, 0), 1)
            else:
                fuel_left = n["fuel_reserve_hours"]
            yield {
                "event_time": iso(t),
                "node_id": n["node_id"],
                "system_code": n["system_code"],
                "gmina_code": n["gmina_code"],
                "powiat_code": n["powiat_code"],
                "voivodeship_code": v,
                "status": status,
                "load_pct": round(load, 1),
                "on_backup_power": int(on_backup),
                "backup_fuel_hours_left": fuel_left,
                "water_level_margin_m": round(clamp(n["elevation_m"] - 120 - fi * 55, -12, 400), 1)
                if n["in_flood_zone"] else None,
                "population_served": n["population_served"],
            }


n_status = write_jsonl(NODE_STATUS_NAME, gen_node_status())


def gen_operator_reports():
    """Meldunki operatorow IK w trybie SPO-10."""
    kinds = ["podtopienie obiektu", "utrata zasilania podstawowego", "uruchomienie agregatu",
             "wyczerpanie paliwa agregatu", "utrata łączności z obiektem", "ewakuacja personelu",
             "ograniczenie przepustowości", "przywrócenie funkcji", "zapotrzebowanie na pompy",
             "zapotrzebowanie na paliwo"]
    out = []
    for node_id, ft in impacted.items():
        n = NODES[node_id]
        k = int(clamp(rng.poisson(3.1), 1, 9))
        for i in range(k):
            t = ft + timedelta(hours=float(rng.uniform(-6, 60)))
            if not (START <= t <= END):
                continue
            out.append({
                "event_time": iso(t),
                "report_id": f"R-{node_id}-{i:02d}",
                "node_id": node_id,
                "system_code": n["system_code"],
                "voivodeship_code": n["voivodeship_code"],
                "powiat_code": n["powiat_code"],
                "operator_name": n["operator_name"],
                "report_kind": random.choice(kinds),
                "severity": random.choices(["info", "warning", "critical"], [.34, .43, .23])[0],
                "eta_restore_hours": round(clamp(rng.normal(n["restore_hours"], 7), 1, 140), 1),
                "support_requested": int(rng.random() < .34),
                "channel": random.choices(["SPO-10 kontakt operacyjny", "telefon dyżurny", "e-mail", "system RCB"],
                                          [.42, .27, .16, .15])[0],
            })
    out.sort(key=lambda r: r["event_time"])
    return out


n_reports = write_jsonl("ci_operator_reports.jsonl", gen_operator_reports())


def gen_hydro():
    """Odczyty wodowskazow spojne z osia POWODZ WRZESIEN."""
    gauges = []
    for v in ("02", "16", "24", "08", "32"):
        for i in range(1, 25):
            g = random.choice(GM_BY_VOIV[v])
            gauges.append({"gauge_id": f"WG-{v}-{i:03d}", "voivodeship_code": v,
                           "gmina_code": g["gmina_code"], "powiat_code": g["powiat_code"],
                           "warning_level_cm": int(rng.integers(240, 330)),
                           "alarm_level_cm": int(rng.integers(340, 430)),
                           "lat": round(g["lat"], 5), "lon": round(g["lon"], 5)})
    write_csv("dim_river_gauge.csv", gauges)
    for step in range(0, HOURS + 1):
        t = START + timedelta(hours=step)
        for g in gauges:
            fi = flood_intensity(t, g["voivodeship_code"])
            level = g["warning_level_cm"] * .62 + fi * (g["alarm_level_cm"] - g["warning_level_cm"] * .62) * 1.35
            level += rng.normal(0, 9)
            yield {
                "event_time": iso(t),
                "gauge_id": g["gauge_id"],
                "voivodeship_code": g["voivodeship_code"],
                "powiat_code": g["powiat_code"],
                "gmina_code": g["gmina_code"],
                "water_level_cm": round(clamp(level, 20, 900), 1),
                "warning_level_cm": g["warning_level_cm"],
                "alarm_level_cm": g["alarm_level_cm"],
                "state": "alarm" if level >= g["alarm_level_cm"] else "ostrzegawczy" if level >= g["warning_level_cm"] else "normalny",
            }


n_hydro = write_jsonl("hydro_readings.jsonl", gen_hydro())

meta = {
    "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
    "seed": SEED,
    "scenario": "POWODZ WRZESIEN (Z02) + kaskada Z07/Z12/Z14",
    "window": {"start": iso(START), "d0": iso(D0), "end": iso(END)},
    "counts": {
        "voivodeships": len(voiv_rows), "powiats": len(powiats), "gminas": len(gminas),
        "ci_systems": len(systems), "ci_nodes": len(nodes), "dependencies": len(edges),
        "hazard_exposures": len(exposure), "spo10_records": len(spo10),
        "node_status_events": n_status, "operator_reports": n_reports, "hydro_readings": n_hydro,
        "flood_impacted_nodes": len(impacted),
    },
}
(DATA / "generation_summary.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(meta["counts"], ensure_ascii=True, indent=2))
