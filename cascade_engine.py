"""Silnik propagacji kaskady awarii w grafie infrastruktury krytycznej.

Modul jest wspoldzielony przez notatniki 02-04. W Microsoft Fabric plik nalezy
umiescic w zasobach notatnika (Resources) albo w Lakehouse (`Files/code`) i
zaladowac przez `%run` lub `sys.path.append`.

Model:
  * Wezel ma progowa odpornosc `fail_threshold` (domyslnie 0.5) — przestaje
    dzialac, gdy laczny udzial utraconych wejsc (`impact_share`) przekroczy prog.
  * Kazda krawedz ma `lag_hours` — czas, po ktorym utrata dostawcy przeklada sie
    na odbiorce (bufory technologiczne: zbiorniki, magazyny, kolejki).
  * Zaleznosci zasilajace (`electricity`, `generation`, `fuel`) sa dodatkowo
    opoznione o autonomie zasilania rezerwowego wezla (`autonomy_hours`).
  * Dostawca jest odtwarzany po `restore_hours`. Jesli rezerwa odbiorcy jest
    dluzsza niz czas odtworzenia dostawcy, odbiorca **nie przestaje dzialac** —
    agregat lub zbiornik przykrywa cala przerwe. To wlasnie czyni z autonomii
    realna dzwignie inwestycyjna, a nie tylko odroczenie skutku.
  * Redundancja `full` oznacza automatyczne przelaczenie — pojedynczy dostawca
    przenosi tylko ulamek udzialu (`FULL_REDUNDANCY_FACTOR`).

Propagacja jest realizowana kolejka priorytetowa po czasie, dzieki czemu
kolejnosc zdarzen jest przyczynowo poprawna i deterministyczna.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

POWER_DEPS = {"electricity", "generation"}
FUEL_DEPS = {"fuel"}
FULL_REDUNDANCY_FACTOR = 0.40
PARTIAL_REDUNDANCY_FACTOR = 0.90
DEFAULT_THRESHOLD = 0.50
DEFAULT_HORIZON_H = 240.0


@dataclass
class Graph:
    """Graf zaleznosci: wezly + krawedzie wychodzace od dostawcy do odbiorcy."""

    nodes: dict[str, dict]
    out_edges: dict[str, list[dict]] = field(default_factory=dict)

    @classmethod
    def build(cls, node_records: list[dict], edge_records: list[dict]) -> "Graph":
        nodes = {n["node_id"]: n for n in node_records}
        out: dict[str, list[dict]] = {}
        for e in edge_records:
            if e["source_node_id"] not in nodes or e["target_node_id"] not in nodes:
                continue
            out.setdefault(e["source_node_id"], []).append(e)
        return cls(nodes=nodes, out_edges=out)

    def in_degree_by_type(self, edge_records: list[dict]) -> dict[tuple[str, str], int]:
        counts: dict[tuple[str, str], int] = {}
        for e in edge_records:
            key = (e["target_node_id"], e["dependency_type"])
            counts[key] = counts.get(key, 0) + 1
        return counts


def _edge_factor(edge: dict) -> float:
    level = edge.get("redundancy_level", "none")
    if level == "full":
        return FULL_REDUNDANCY_FACTOR
    if level == "partial":
        return PARTIAL_REDUNDANCY_FACTOR
    return 1.0


def _buffer_hours(node: dict, dep_type: str) -> float:
    """Bufor wezla dla danego typu zaleznosci (autonomia zasilania, zapas paliwa)."""
    if dep_type in POWER_DEPS:
        if node.get("backup_type") in ("genset", "onsite_fuel"):
            return min(float(node.get("autonomy_hours", 0)), float(node.get("fuel_reserve_hours", 0)) or float(node.get("autonomy_hours", 0)))
        return float(node.get("autonomy_hours", 0))
    if dep_type in FUEL_DEPS:
        return float(node.get("fuel_reserve_hours", 0))
    return 0.0


def simulate(
    graph: Graph,
    seeds: dict[str, float],
    threshold: float = DEFAULT_THRESHOLD,
    horizon_hours: float = DEFAULT_HORIZON_H,
    autonomy_bonus: dict[str, float] | None = None,
    survived_out: dict[str, int] | None = None,
) -> list[dict]:
    """Zwraca liste zdarzen awarii: kolejnosc przyczynowa, czas, fala, przyczyna.

    `seeds` to slownik `node_id -> godzina awarii` (0 = moment zdarzenia inicjujacego).
    `autonomy_bonus` pozwala w scenariuszach what-if dolozyc godziny autonomii wezlom.
    `survived_out` (opcjonalnie) zbiera wezly uratowane przez rezerwe zasilania.
    """
    autonomy_bonus = autonomy_bonus or {}
    lost: dict[str, float] = {}
    failed: dict[str, float] = {}
    survivors: dict[str, int] = survived_out if survived_out is not None else {}
    result: list[dict] = []
    heap: list[tuple[float, int, str, str | None, str | None, int]] = []
    counter = 0

    for node_id, t in sorted(seeds.items()):
        if node_id not in graph.nodes:
            continue
        counter += 1
        heapq.heappush(heap, (float(t), counter, node_id, None, "seed", 0))

    while heap:
        t, _, node_id, cause_id, cause_type, wave = heapq.heappop(heap)
        if node_id in failed or t > horizon_hours:
            continue
        failed[node_id] = t
        node = graph.nodes[node_id]
        result.append({
            "node_id": node_id,
            "node_name": node.get("node_name"),
            "system_code": node.get("system_code"),
            "system_group": node.get("system_group"),
            "node_type": node.get("node_type"),
            "voivodeship_code": node.get("voivodeship_code"),
            "powiat_code": node.get("powiat_code"),
            "gmina_code": node.get("gmina_code"),
            "criticality_class": node.get("criticality_class"),
            "population_served": node.get("population_served"),
            "fail_hour": round(t, 2),
            "wave": wave,
            "cause_node_id": cause_id,
            "cause_dependency": cause_type,
        })

        for edge in graph.out_edges.get(node_id, []):
            target_id = edge["target_node_id"]
            if target_id in failed:
                continue
            target = graph.nodes[target_id]
            contribution = float(edge["impact_share"]) * _edge_factor(edge)
            lost[target_id] = lost.get(target_id, 0.0) + contribution
            if lost[target_id] < threshold:
                continue
            dep_type = edge["dependency_type"]
            buffer_h = _buffer_hours(target, dep_type) + autonomy_bonus.get(target_id, 0.0)
            # rezerwa dluzsza niz przerwa u dostawcy = odbiorca przetrwa bez awarii
            if buffer_h > 0 and buffer_h >= float(node.get("restore_hours", 0) or 0):
                survivors[target_id] = survivors.get(target_id, 0) + 1
                continue
            fail_at = t + float(edge["lag_hours"]) + buffer_h
            if fail_at > horizon_hours:
                continue
            counter += 1
            heapq.heappush(heap, (fail_at, counter, target_id, node_id, dep_type, wave + 1))

    return result


def impact_summary(events: list[dict], gmina_population: dict[str, int],
                   service_groups: tuple[str, ...] = ("energy", "water", "health")) -> dict:
    """Skutki kaskady bez podwojnego liczenia ludnosci.

    `population_served` sumuje sie po systemach i moze sie nakladac, dlatego
    dodatkowo liczymy ludnosc gmin, w ktorych przestal dzialac wezel uslugowy.
    """
    secondary = [e for e in events if e["wave"] > 0]
    affected_gminas = {e["gmina_code"] for e in events if e["system_group"] in service_groups}
    by_group: dict[str, int] = {}
    for e in events:
        by_group[e["system_group"]] = by_group.get(e["system_group"], 0) + 1
    return {
        "nodes_failed_total": len(events),
        "nodes_failed_secondary": len(secondary),
        "max_wave": max((e["wave"] for e in events), default=0),
        "affected_gminas": len(affected_gminas),
        "affected_population": int(sum(gmina_population.get(g, 0) for g in affected_gminas)),
        "population_served_sum": int(sum(e["population_served"] for e in events)),
        "nodes_by_system_group": dict(sorted(by_group.items(), key=lambda kv: -kv[1])),
        "first_secondary_hour": round(min((e["fail_hour"] for e in secondary), default=0.0), 2),
        "k1_nodes_failed": sum(1 for e in events if e["criticality_class"] == "K1"),
    }
