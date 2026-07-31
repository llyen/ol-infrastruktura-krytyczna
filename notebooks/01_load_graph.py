# CELL
"""01 — zaladowanie grafu infrastruktury krytycznej i kontrola jakosci.

W Fabric: zamien odczyty na `spark.read` z Lakehouse i zapis `saveAsTable`.
"""
from pathlib import Path
import json

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "datasets"
OUT = DATA / "derived"
OUT.mkdir(exist_ok=True)

# CELL
nodes = pd.read_csv(DATA / "dim_ci_node.csv", dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
edges = pd.read_csv(DATA / "fact_ci_dependency.csv")
systems = pd.read_csv(DATA / "dim_ci_system.csv")
gminas = pd.read_csv(DATA / "dim_gmina.csv", dtype={"gmina_code": str, "powiat_code": str, "voivodeship_code": str})
spo10 = pd.read_csv(DATA / "fact_spo10_cooperation.csv")
exposure = pd.read_csv(DATA / "fact_node_hazard_exposure.csv")

# CELL — kontrola spojnosci grafu
known = set(nodes.node_id)
orphan_edges = edges[~edges.source_node_id.isin(known) | ~edges.target_node_id.isin(known)]
self_loops = edges[edges.source_node_id == edges.target_node_id]
assert orphan_edges.empty, f"krawedzie wskazujace na nieznane wezly: {len(orphan_edges)}"
assert self_loops.empty, f"petle wlasne: {len(self_loops)}"

in_deg = edges.groupby("target_node_id").size().rename("in_degree")
out_deg = edges.groupby("source_node_id").size().rename("out_degree")
nodes = nodes.merge(in_deg, left_on="node_id", right_index=True, how="left") \
             .merge(out_deg, left_on="node_id", right_index=True, how="left")
nodes[["in_degree", "out_degree"]] = nodes[["in_degree", "out_degree"]].fillna(0).astype(int)

# CELL — pojedyncze punkty zasilania: odbiorca z jednym, nieredundantnym dostawca
power = edges[edges.dependency_type.isin(["electricity", "generation"])]
supplier_count = power.groupby("target_node_id").source_node_id.nunique().rename("power_suppliers")
nodes = nodes.merge(supplier_count, left_on="node_id", right_index=True, how="left")
nodes["power_suppliers"] = nodes.power_suppliers.fillna(0).astype(int)
nodes["single_source_power"] = ((nodes.power_suppliers == 1) & (nodes.system_group != "energy")).astype(int)
nodes["no_backup"] = (nodes.backup_type == "none").astype(int)
nodes["fragility_score"] = (
    0.40 * (nodes.criticality_score / 100)
    + 0.25 * nodes.single_source_power
    + 0.20 * nodes.no_backup
    + 0.15 * (1 - (nodes.autonomy_hours.clip(0, 72) / 72))
).round(4) * 100

# CELL — agregaty systemowe
sys_summary = (
    nodes.groupby("system_code")
    .agg(nodes=("node_id", "count"),
         k1_nodes=("criticality_class", lambda s: int((s == "K1").sum())),
         population_served=("population_served", "sum"),
         avg_autonomy_h=("autonomy_hours", "mean"),
         no_backup_nodes=("no_backup", "sum"),
         single_source_power=("single_source_power", "sum"),
         on_register_pct=("on_ci_register", "mean"))
    .reset_index()
    .merge(systems[["system_code", "system_name", "responsible_department"]], on="system_code")
)
sys_summary["avg_autonomy_h"] = sys_summary.avg_autonomy_h.round(1)
sys_summary["on_register_pct"] = (sys_summary.on_register_pct * 100).round(1)
sys_summary = sys_summary.sort_values("population_served", ascending=False)

dep_matrix = (
    edges.merge(nodes[["node_id", "system_code"]].rename(columns={"node_id": "source_node_id", "system_code": "src_sys"}), on="source_node_id")
         .merge(nodes[["node_id", "system_code"]].rename(columns={"node_id": "target_node_id", "system_code": "dst_sys"}), on="target_node_id")
         .groupby(["src_sys", "dst_sys", "dependency_type"]).size().rename("edges").reset_index()
         .sort_values("edges", ascending=False)
)

# CELL — luki wspolpracy z operatorami (SPO-10)
gaps = nodes.merge(spo10, on="node_id", how="left")
gaps["spo10_gap"] = (
    (gaps.data_sharing_agreement.fillna(0) == 0)
    | (gaps.contact_point_registered.fillna(0) == 0)
    | (gaps.protection_plan_status.fillna("brak") == "brak")
).astype(int)
spo10_gaps = gaps[(gaps.spo10_gap == 1) & (gaps.criticality_class.isin(["K1", "K2"]))][
    ["node_id", "node_name", "system_code", "voivodeship_code", "criticality_class",
     "operator_name_x", "protection_plan_status", "responsiveness_score", "population_served"]
].rename(columns={"operator_name_x": "operator_name"}).sort_values("population_served", ascending=False)

# CELL — zapis wynikow
nodes.to_csv(OUT / "graph_nodes.csv", index=False)
edges.to_csv(OUT / "graph_edges.csv", index=False)
sys_summary.to_csv(OUT / "system_summary.csv", index=False)
dep_matrix.to_csv(OUT / "dependency_matrix.csv", index=False)
spo10_gaps.to_csv(OUT / "spo10_gaps.csv", index=False)

summary = {
    "nodes": int(len(nodes)),
    "edges": int(len(edges)),
    "systems": int(nodes.system_code.nunique()),
    "cross_voivodeship_edges": int(edges.cross_voivodeship.sum()),
    "avg_out_degree": round(float(edges.groupby("source_node_id").size().mean()), 2),
    "max_out_degree": int(edges.groupby("source_node_id").size().max()),
    "nodes_without_backup": int(nodes.no_backup.sum()),
    "single_source_power_nodes": int(nodes.single_source_power.sum()),
    "k1_nodes": int((nodes.criticality_class == "K1").sum()),
    "k1_not_on_register": int(((nodes.criticality_class == "K1") & (nodes.on_ci_register == 0)).sum()),
    "spo10_gaps_k1_k2": int(len(spo10_gaps)),
    "hazard_exposure_rows": int(len(exposure)),
    "gminas_with_ci_node": int(nodes.gmina_code.nunique()),
}
(OUT / "graph_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True, indent=2))
