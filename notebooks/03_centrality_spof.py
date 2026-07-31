# CELL
"""03 — centralnosc kaskadowa i pojedyncze punkty awarii (SPOF).

Dla kazdego wezla liczymy pelna symulacje "co jesli ten jeden wezel padnie".
Wynik to ranking, ktory odpowiada na pytanie: gdzie jedna awaria kosztuje
najwiecej i ktore obiekty nalezy wzmocnic w pierwszej kolejnosci.
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

# CELL
nodes = pd.read_csv(OUT / "graph_nodes.csv", dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
edges = pd.read_csv(OUT / "graph_edges.csv")
gminas = pd.read_csv(DATA / "dim_gmina.csv", dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
GM_POP = dict(zip(gminas.gmina_code, gminas.population))
graph = Graph.build(nodes.to_dict("records"), edges.to_dict("records"))

# CELL — centralnosc kaskadowa: symulacja awarii kazdego wezla z osobna
rows = []
for nid, node in graph.nodes.items():
    events = simulate(graph, {nid: 0.0}, horizon_hours=240)
    m = impact_summary(events, GM_POP)
    sec = [e for e in events if e["wave"] > 0]
    rows.append({
        "node_id": nid,
        "node_name": node["node_name"],
        "system_code": node["system_code"],
        "system_group": node["system_group"],
        "node_type": node["node_type"],
        "voivodeship_code": node["voivodeship_code"],
        "gmina_code": node["gmina_code"],
        "criticality_class": node["criticality_class"],
        "cascade_nodes": m["nodes_failed_secondary"],
        "cascade_max_wave": m["max_wave"],
        "cascade_systems": len({e["system_group"] for e in sec}),
        "cascade_population": m["affected_population"],
        "cascade_gminas": m["affected_gminas"],
        "cascade_k1_nodes": sum(1 for e in sec if e["criticality_class"] == "K1"),
        "first_secondary_hour": m["first_secondary_hour"],
    })
cent = pd.DataFrame(rows)

# CELL — indeks krytycznosci kaskadowej 0-100
def norm(series: pd.Series) -> pd.Series:
    lo, hi = float(series.min()), float(series.max())
    return (series - lo) / (hi - lo) if hi > lo else series * 0


cent["cascade_index"] = (
    0.38 * norm(cent.cascade_population)
    + 0.27 * norm(cent.cascade_nodes)
    + 0.20 * norm(cent.cascade_systems)
    + 0.15 * norm(cent.cascade_k1_nodes)
) * 100
cent["cascade_index"] = cent.cascade_index.round(2)
cent["cascade_tier"] = pd.cut(cent.cascade_index, [-1, 5, 20, 45, 101],
                              labels=["marginalny", "istotny", "wysoki", "krytyczny"])
cent = cent.sort_values("cascade_index", ascending=False)
cent.to_csv(OUT / "cascade_centrality.csv", index=False)
cent.head(100).to_csv(OUT / "cascade_top100.csv", index=False)

# CELL — pojedyncze punkty awarii
# SPOF = wezel, ktorego samodzielna awaria wywoluje skutki wtorne w >=3 systemach
# lub pozbawia uslug ponad 100 tys. mieszkancow.
spof = cent[(cent.cascade_systems >= 3) | (cent.cascade_population >= 100_000)].copy()
spof = spof.merge(
    nodes[["node_id", "backup_type", "autonomy_hours", "single_source_power", "on_ci_register",
           "spo10_agreement", "operator_name", "in_flood_zone", "fragility_score"]],
    on="node_id", how="left")
spof["spof_reason"] = spof.apply(
    lambda r: "; ".join(filter(None, [
        f"skutki w {int(r.cascade_systems)} systemach" if r.cascade_systems >= 3 else None,
        f"{int(r.cascade_population):,} mieszkańców bez usług".replace(",", " ") if r.cascade_population >= 100_000 else None,
        "brak zasilania rezerwowego" if r.backup_type == "none" else None,
        "jedno źródło zasilania" if r.single_source_power == 1 else None,
        "poza rejestrem IK" if r.on_ci_register == 0 else None,
        "w strefie zalewowej" if r.in_flood_zone == 1 else None,
    ])), axis=1)
spof.sort_values("cascade_index", ascending=False).to_csv(OUT / "single_points_of_failure.csv", index=False)

# CELL — ujecie wojewodzkie i systemowe
by_voiv = (
    cent.groupby("voivodeship_code")
    .agg(nodes=("node_id", "count"),
         critical_nodes=("cascade_tier", lambda s: int((s.astype(str) == "krytyczny").sum())),
         max_cascade_population=("cascade_population", "max"),
         avg_cascade_index=("cascade_index", "mean"))
    .reset_index()
)
by_voiv["avg_cascade_index"] = by_voiv.avg_cascade_index.round(2)
by_voiv.sort_values("max_cascade_population", ascending=False).to_csv(OUT / "cascade_by_voivodeship.csv", index=False)

by_system = (
    cent.groupby("system_code")
    .agg(nodes=("node_id", "count"),
         avg_cascade_index=("cascade_index", "mean"),
         max_cascade_nodes=("cascade_nodes", "max"),
         spof_nodes=("node_id", lambda s: int(s.isin(spof.node_id).sum())))
    .reset_index()
)
by_system["avg_cascade_index"] = by_system.avg_cascade_index.round(2)
by_system.sort_values("avg_cascade_index", ascending=False).to_csv(OUT / "cascade_by_system.csv", index=False)

summary = {
    "nodes_simulated": int(len(cent)),
    "spof_nodes": int(len(spof)),
    "critical_tier_nodes": int((cent.cascade_tier.astype(str) == "krytyczny").sum()),
    "top_node_id": cent.iloc[0].node_id,
    "top_node_name": cent.iloc[0].node_name,
    "top_cascade_population": int(cent.iloc[0].cascade_population),
    "top_cascade_nodes": int(cent.iloc[0].cascade_nodes),
    "spof_without_backup": int((spof.backup_type == "none").sum()),
    "spof_outside_register": int((spof.on_ci_register == 0).sum()),
    "spof_without_spo10": int((spof.spo10_agreement == 0).sum()),
    "spof_in_flood_zone": int((spof.in_flood_zone == 1).sum()),
    "median_cascade_nodes": float(cent.cascade_nodes.median()),
}
(OUT / "spof_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True, indent=2))
