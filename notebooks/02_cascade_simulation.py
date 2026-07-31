# CELL
"""02 — symulacja efektu domina.

Dwa scenariusze:
  A. POWODZ WRZESIEN — kaskada wywolana podtopieniem wielu obiektow naraz.
  B. POJEDYNCZY WEZEL — "wylacz te stacje" na potrzeby demo i cwiczen.

W Fabric: `%run cascade_engine` albo umieszczenie modulu w zasobach notatnika.
"""
from pathlib import Path
import json
import sys

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "datasets"
OUT = DATA / "derived"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(BASE))

from cascade_engine import Graph, simulate, impact_summary  # noqa: E402

D0 = pd.Timestamp("2026-09-12T06:00:00+02:00")

# CELL
nodes = pd.read_csv(OUT / "graph_nodes.csv", dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
edges = pd.read_csv(OUT / "graph_edges.csv")
gminas = pd.read_csv(DATA / "dim_gmina.csv", dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
GM_POP = dict(zip(gminas.gmina_code, gminas.population))
GM_NAME = dict(zip(gminas.gmina_code, gminas.gmina_name))

graph = Graph.build(nodes.to_dict("records"), edges.to_dict("records"))
NODE = graph.nodes

# CELL — scenariusz A: zdarzenia inicjujace z telemetrii (podtopione obiekty)
status = pd.read_json(DATA / "ci_node_status.jsonl", lines=True,
                      dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
status["event_time"] = pd.to_datetime(status.event_time, utc=True)
down = status[status.status == "down"]
first_down = down.groupby("node_id").event_time.min()
seeds_flood = {nid: max((ts - D0.tz_convert("UTC")).total_seconds() / 3600, 0.0)
               for nid, ts in first_down.items() if nid in NODE}
print(f"zdarzenia inicjujace (podtopienie): {len(seeds_flood)}")

flood_events = simulate(graph, seeds_flood, horizon_hours=240)
flood_df = pd.DataFrame(flood_events)
flood_df["gmina_name"] = flood_df.gmina_code.map(GM_NAME)
flood_df["cause_node_name"] = flood_df.cause_node_id.map(lambda x: NODE[x]["node_name"] if isinstance(x, str) else None)
flood_df["fail_time"] = (D0 + pd.to_timedelta(flood_df.fail_hour, unit="h")).dt.strftime("%Y-%m-%dT%H:%M%z")
flood_df.sort_values("fail_hour").to_csv(OUT / "cascade_flood_timeline.csv", index=False)

flood_summary = impact_summary(flood_events, GM_POP)
flood_summary["flooded_nodes"] = len(seeds_flood)
# Wzmocnienie liczymy wzgledem obiektow, ktore faktycznie weszly do kaskady jako
# fala 0. Czesc podtopionych obiektow nie generuje skutkow w horyzoncie analizy,
# a dzielenie przez nie zawyzaloby mianownik i zanizalo wskaznik.
primary = sum(1 for e in flood_events if e["wave"] == 0)
flood_summary["seed_nodes"] = primary
flood_summary["amplification_ratio"] = round(len(flood_events) / max(primary, 1), 2)

# CELL — jak kaskada rozklada sie w czasie (fale skutkow)
waves = (
    flood_df.groupby("wave")
    .agg(nodes=("node_id", "count"),
         first_hour=("fail_hour", "min"),
         last_hour=("fail_hour", "max"),
         population_served=("population_served", "sum"))
    .reset_index()
)
waves["first_hour"] = waves.first_hour.round(1)
waves["last_hour"] = waves.last_hour.round(1)
waves.to_csv(OUT / "cascade_waves.csv", index=False)

hourly = (
    flood_df.assign(hour_bucket=flood_df.fail_hour.astype(int))
    .groupby(["hour_bucket", "system_group"]).size().rename("nodes_failed").reset_index()
)
hourly["cumulative"] = hourly.sort_values("hour_bucket").groupby("system_group").nodes_failed.cumsum()
hourly.to_csv(OUT / "cascade_hourly_profile.csv", index=False)

# CELL — scenariusz B: pojedynczy wezel ("wylacz te stacje")
# Do demo wybieramy wezel na osi scenariusza (dolnoslaskie/opolskie), zeby narracja
# byla spojna z COP-24; wariant krajowy liczymy osobno jako punkt odniesienia.
AXIS = {"02", "16"}
energy_k1 = nodes[(nodes.system_group == "energy") & (nodes.criticality_class == "K1")]


def pick_worst(pool: pd.DataFrame, top_n: int = 40):
    best_id, best_ev, best_m = None, None, None
    for nid in pool.sort_values("out_degree", ascending=False).head(top_n).node_id:
        ev = simulate(graph, {nid: 0.0}, horizon_hours=240)
        m = impact_summary(ev, GM_POP)
        if best_m is None or m["affected_population"] > best_m["affected_population"]:
            best_id, best_ev, best_m = nid, ev, m
    return best_id, best_ev, best_m


best, best_events, best_metrics = pick_worst(energy_k1[energy_k1.voivodeship_code.isin(AXIS)])
nat_id, _, nat_metrics = pick_worst(energy_k1)

single_df = pd.DataFrame(best_events)
single_df["gmina_name"] = single_df.gmina_code.map(GM_NAME)
single_df["cause_node_name"] = single_df.cause_node_id.map(lambda x: NODE[x]["node_name"] if isinstance(x, str) else None)
single_df.sort_values("fail_hour").to_csv(OUT / "cascade_single_node_timeline.csv", index=False)

# CELL — naglowek dla decydenta: co to znaczy w praktyce
sec = single_df[single_df.wave > 0]
node_idx = nodes.set_index("node_id")
hospitals = sec[sec.node_type.str.contains("szpital", case=False, na=False)]
pumps = sec[sec.node_type.str.contains("przepompownia|stacja uzdatniania|ujęcie", case=False, na=False)]
telco = sec[sec.system_group == "telecom"]
rescue = sec[sec.system_group == "rescue"]
water_stop_h = float(pumps.fail_hour.min()) if not pumps.empty else None
hosp_aut = node_idx.loc[hospitals.node_id, "autonomy_hours"] if not hospitals.empty else pd.Series(dtype=float)
headline = {
    "trigger_node_id": best,
    "trigger_node_name": NODE[best]["node_name"],
    "trigger_node_type": NODE[best]["node_type"],
    "trigger_voivodeship": NODE[best]["voivodeship_code"],
    "trigger_gmina": GM_NAME.get(NODE[best]["gmina_code"]),
    "people_without_power": int(best_metrics["affected_population"]),
    "secondary_nodes": int(best_metrics["nodes_failed_secondary"]),
    "max_wave": int(best_metrics["max_wave"]),
    "hospitals_affected": int(len(hospitals)),
    "hospitals_on_gensets": int((hosp_aut > 0).sum()) if len(hosp_aut) else 0,
    "hospitals_without_backup": int((hosp_aut == 0).sum()) if len(hosp_aut) else 0,
    "hospital_median_autonomy_h": round(float(hosp_aut[hosp_aut > 0].median()), 1) if (len(hosp_aut) and (hosp_aut > 0).any()) else None,
    "water_nodes_affected": int(len(pumps)),
    "hours_until_water_stops": round(water_stop_h, 1) if water_stop_h is not None else None,
    "telecom_nodes_affected": int(len(telco)),
    "rescue_nodes_affected": int(len(rescue)),
    "first_secondary_hour": best_metrics["first_secondary_hour"],
}

# CELL — drzewo skutkow do raportu i aplikacji
tree_rows = []
for e in best_events:
    tree_rows.append({
        "node_id": e["node_id"],
        "node_name": e["node_name"],
        "parent_node_id": e["cause_node_id"],
        "dependency": e["cause_dependency"],
        "wave": e["wave"],
        "fail_hour": e["fail_hour"],
        "system_group": e["system_group"],
        "node_type": e["node_type"],
        "gmina_name": GM_NAME.get(e["gmina_code"]),
        "population_served": e["population_served"],
    })
pd.DataFrame(tree_rows).to_csv(OUT / "cascade_effect_tree.csv", index=False)

# CELL — czas do skutku per gmina (kiedy mieszkaniec odczuje awarie)
svc = flood_df[flood_df.system_group.isin(["energy", "water", "health", "telecom"])]
gmina_effect = (
    svc.groupby(["gmina_code", "system_group"]).fail_hour.min().unstack(fill_value=float("nan")).reset_index()
)
gmina_effect["gmina_name"] = gmina_effect.gmina_code.map(GM_NAME)
gmina_effect["population"] = gmina_effect.gmina_code.map(GM_POP)
gmina_effect = gmina_effect.sort_values("population", ascending=False)
gmina_effect.to_csv(OUT / "cascade_gmina_time_to_effect.csv", index=False)

summary = {
    "flood_scenario": flood_summary,
    "single_node_scenario": best_metrics,
    "worst_single_node_national": {"node_id": nat_id, "node_name": NODE[nat_id]["node_name"],
                                   "voivodeship_code": NODE[nat_id]["voivodeship_code"], **nat_metrics},
    "headline": headline,
}
(OUT / "cascade_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True, indent=2))
