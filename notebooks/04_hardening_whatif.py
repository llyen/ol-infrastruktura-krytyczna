# CELL
"""04 — what-if: co realnie zmniejsza skutki efektu domina.

Porownujemy warianty inwestycyjne na tym samym zdarzeniu inicjujacym
(POWODZ WRZESIEN), zeby odpowiedziec na pytanie decydenta: gdzie wydac
pieniadze, zeby kaskada byla krotsza i plytsza.

Warianty:
  A. AUTONOMIA  — agregat i zapas paliwa na 72 h w wezlach z listy SPOF.
  B. REDUNDANCJA — drugie, niezalezne zasilanie dla wezlow K1 z jednym zrodlem.
  C. RAZEM      — A + B.
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
HARDENING_HOURS = 72.0
TOP_HARDENED = 120

# CELL
nodes = pd.read_csv(OUT / "graph_nodes.csv", dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
edges = pd.read_csv(OUT / "graph_edges.csv")
gminas = pd.read_csv(DATA / "dim_gmina.csv", dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
spof = pd.read_csv(OUT / "single_points_of_failure.csv")
timeline = pd.read_csv(OUT / "cascade_flood_timeline.csv")
GM_POP = dict(zip(gminas.gmina_code, gminas.population))

node_records = nodes.to_dict("records")
edge_records = edges.to_dict("records")
graph = Graph.build(node_records, edge_records)

# zdarzenia inicjujace = wezly podtopione bezposrednio (fala 0)
seeds = dict(zip(timeline[timeline.wave == 0].node_id, timeline[timeline.wave == 0].fail_hour))
print(f"zdarzenia inicjujace: {len(seeds)}")

# CELL — wariant bazowy
base_survivors: dict[str, int] = {}
base_events = simulate(graph, seeds, horizon_hours=240, survived_out=base_survivors)
base_metrics = impact_summary(base_events, GM_POP)
base_df = pd.DataFrame(base_events)

# CELL — wariant A: agregat i paliwo na 72 h w wezlach uslugowych, ktore padly wtornie
# Wzmacniamy odbiorcow, nie zrodla: to obiekty uslugowe K1/K2 (zdrowie, woda,
# lacznosc, ratownictwo, administracja), ktore w wariancie bazowym przestaly
# dzialac dopiero na skutek utraty zasilania.
SERVICE_GROUPS = ("health", "water", "telecom", "rescue", "admin")
victims = base_df[(base_df.wave > 0)
                  & (base_df.system_group.isin(SERVICE_GROUPS))
                  & (base_df.criticality_class.isin(["K1", "K2"]))]
hardened = list(
    nodes[nodes.node_id.isin(victims.node_id)]
    .sort_values("population_served", ascending=False)
    .head(TOP_HARDENED).node_id
)
bonus = {}
for nid in hardened:
    current = float(nodes.loc[nodes.node_id == nid, "autonomy_hours"].iloc[0])
    bonus[nid] = max(HARDENING_HOURS - current, 0.0)
a_survivors: dict[str, int] = {}
a_events = simulate(graph, seeds, horizon_hours=240, autonomy_bonus=bonus, survived_out=a_survivors)
a_metrics = impact_summary(a_events, GM_POP)

# CELL — wariant B: drugie zasilanie dla wezlow K1 z jednym zrodlem
gpz = nodes[(nodes.system_group == "energy") & (nodes.node_type.isin(["GPZ 110/SN", "stacja NN 400/220 kV"]))]
targets = nodes[(nodes.criticality_class == "K1") & (nodes.single_source_power == 1)]
print(f"wezly K1 z jednym zrodlem zasilania: {len(targets)}")

edges_b = [dict(e) for e in edge_records]
by_target = {}
for e in edges_b:
    if e["dependency_type"] == "electricity":
        by_target.setdefault(e["target_node_id"], []).append(e)

new_edges, seq = [], 0
for _, t in targets.iterrows():
    existing = by_target.get(t.node_id, [])
    if not existing:
        continue
    current_src = {e["source_node_id"] for e in existing}
    pool = gpz[(gpz.voivodeship_code == t.voivodeship_code) & (~gpz.node_id.isin(current_src))]
    if pool.empty:
        continue
    pool = pool.assign(d=((pool.lat - t.lat).abs() * 111 + (pool.lon - t.lon).abs() * 71)).nsmallest(1, "d")
    alt = pool.iloc[0]
    seq += 1
    for e in existing:
        e["impact_share"] = round(float(e["impact_share"]) / 2, 3)
        e["redundancy_level"] = "full"
    new_edges.append({
        "edge_id": f"E-WHATIF-{seq:05d}",
        "source_node_id": alt.node_id,
        "target_node_id": t.node_id,
        "source_system": alt.system_code,
        "target_system": t.system_code,
        "dependency_type": "electricity",
        "impact_share": round(float(existing[0]["impact_share"]), 3),
        "lag_hours": 0.0,
        "redundancy_level": "full",
        "cross_voivodeship": 0,
        "contract_sla_hours": 4.0,
        "verified_in_exercise": 0,
    })

graph_b = Graph.build(node_records, edges_b + new_edges)
b_events = simulate(graph_b, seeds, horizon_hours=240)
b_metrics = impact_summary(b_events, GM_POP)

# CELL — wariant C: razem
c_events = simulate(graph_b, seeds, horizon_hours=240, autonomy_bonus=bonus)
c_metrics = impact_summary(c_events, GM_POP)

# CELL — porownanie wariantow
variants = [
    ("BAZOWY", "stan obecny", base_metrics, 0, 0),
    ("A_AUTONOMIA", f"agregat i paliwo na {int(HARDENING_HOURS)} h w {len(hardened)} węzłach usługowych K1/K2", a_metrics, len(hardened), 0),
    ("B_REDUNDANCJA", f"drugie zasilanie dla {len(new_edges)} węzłów K1", b_metrics, 0, len(new_edges)),
    ("C_RAZEM", "A + B", c_metrics, len(hardened), len(new_edges)),
]
comp = []
for code, desc, m, n_hard, n_red in variants:
    comp.append({
        "variant": code,
        "description": desc,
        "hardened_nodes": n_hard,
        "new_feeds": n_red,
        "nodes_failed_total": m["nodes_failed_total"],
        "nodes_failed_secondary": m["nodes_failed_secondary"],
        "max_wave": m["max_wave"],
        "affected_gminas": m["affected_gminas"],
        "affected_population": m["affected_population"],
        "k1_nodes_failed": m["k1_nodes_failed"],
        "secondary_reduction_pct": round(
            (1 - m["nodes_failed_secondary"] / max(base_metrics["nodes_failed_secondary"], 1)) * 100, 1),
        "population_reduction_pct": round(
            (1 - m["affected_population"] / max(base_metrics["affected_population"], 1)) * 100, 1),
    })
comp_df = pd.DataFrame(comp)
comp_df.to_csv(OUT / "whatif_variants.csv", index=False)

# CELL — ktore pojedyncze wzmocnienie daje najwiecej (ranking inwestycyjny)
marginal = []
for nid in hardened[:40]:
    current = float(nodes.loc[nodes.node_id == nid, "autonomy_hours"].iloc[0])
    ev = simulate(graph, seeds, horizon_hours=240,
                  autonomy_bonus={nid: max(HARDENING_HOURS - current, 0.0)})
    m = impact_summary(ev, GM_POP)
    row = nodes.loc[nodes.node_id == nid].iloc[0]
    marginal.append({
        "node_id": nid,
        "node_name": row.node_name,
        "node_type": row.node_type,
        "system_code": row.system_code,
        "voivodeship_code": row.voivodeship_code,
        "operator_name": row.operator_name,
        "current_autonomy_h": current,
        "nodes_saved": base_metrics["nodes_failed_secondary"] - m["nodes_failed_secondary"],
        "population_saved": base_metrics["affected_population"] - m["affected_population"],
        "spo10_agreement": int(row.spo10_agreement),
    })
marg_df = pd.DataFrame(marginal).sort_values(["population_saved", "nodes_saved"], ascending=False)
marg_df.to_csv(OUT / "whatif_marginal_value.csv", index=False)

# CELL — o ile czasu przesuwa sie pierwszy skutek wtorny (czas na reakcje)
def first_secondary(events):
    sec = [e["fail_hour"] for e in events if e["wave"] > 0]
    return round(min(sec), 2) if sec else None


summary = {
    "baseline": base_metrics,
    "variants": comp,
    "hardened_nodes": len(hardened),
    "new_redundant_feeds": len(new_edges),
    "first_secondary_hour": {
        "baseline": first_secondary(base_events),
        "A_AUTONOMIA": first_secondary(a_events),
        "B_REDUNDANCJA": first_secondary(b_events),
        "C_RAZEM": first_secondary(c_events),
    },
    "best_single_investment": marg_df.iloc[0][["node_id", "node_name", "nodes_saved", "population_saved"]].to_dict()
    if not marg_df.empty else None,
}
(OUT / "whatif_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(json.dumps({"variants": comp, "first_secondary_hour": summary["first_secondary_hour"]},
                 ensure_ascii=True, indent=2))
