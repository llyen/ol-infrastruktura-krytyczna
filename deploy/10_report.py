"""Raport Power BI "Efekt domina" (6 stron) w formacie PBIR.

Buduje definicje raportu wprost z JSON-a (bez Power BI Desktop) i wdraza ja
przez Fabric REST API na model semantyczny sm_ci_cascade.

Zrodlo merytoryczne: report/REPORT_SPEC.md
Format PBIR: patrz deploy/README.md, sekcja "Format definicji raportu (PBIR)".

Uzycie:
    python deploy/10_report.py            # walidacja + wdrozenie
    python deploy/10_report.py --dry-run  # sama walidacja, bez wysylki
    python deploy/10_report.py --no-theme # bez ciemnego motywu (awaryjnie)
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import pathlib
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
REPORT_NAME = "rpt_efekt_domina"
REPORT_DESC = "Efekt domina - infrastruktura krytyczna. Raport na odprawe sztabu."
FABRIC_API = "https://api.fabric.microsoft.com/v1"

W, H = 1280, 720
SCHEMA_VIS = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.0.0/schema.json"
SCHEMA_PAGE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.4.0/schema.json"
SCHEMA_PAGES = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
SCHEMA_REPORT = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.3.0/schema.json"
SCHEMA_PBIR = "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json"
SCHEMA_VERSION = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"

FOOTER = "Dane syntetyczne. Model wskazuje priorytety - decyzje podejmuje czlowiek."

# Funkcje agregujace wg schematu semanticQuery
SUM, AVG, DCOUNT, MIN, MAX, COUNT, MEDIAN = 0, 1, 2, 3, 4, 5, 6

# ---------------------------------------------------------------- metadane


def load_model_metadata() -> tuple[dict[str, str], dict[str, set[str]], dict[str, str]]:
    """Zwraca (tabela->tabela delta, tabela->kolumny, miara->tabela)."""
    spec = importlib.util.spec_from_file_location("sm06", ROOT / "deploy" / "06_semantic_model.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    tables = dict(mod.TABLES)
    schemas = json.loads((ROOT / ".fabric" / "schemas.json").read_text(encoding="utf-8"))
    columns: dict[str, set[str]] = {}
    for tbl, delta in tables.items():
        fields = schemas.get(delta, [])
        columns[tbl] = {f["name"] if isinstance(f, dict) else f for f in fields}
    measures = {name: tbl for tbl, name, *_ in mod.MEASURES}
    return tables, columns, measures


# ---------------------------------------------------------------- pola


def col(entity: str, prop: str) -> dict:
    return {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }


def mea(entity: str, prop: str) -> dict:
    return {
        "field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }


AGG_NAME = {SUM: "Sum", AVG: "Avg", DCOUNT: "CountNonNull", MIN: "Min", MAX: "Max",
            COUNT: "CountNonNull", MEDIAN: "Median"}


def agg(entity: str, prop: str, fn: int = SUM, label: str | None = None) -> dict:
    name = AGG_NAME.get(fn, "Sum")
    return {
        "field": {
            "Aggregation": {
                "Expression": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
                "Function": fn,
            }
        },
        "queryRef": f"{name}({entity}.{prop})",
        "nativeQueryRef": label or f"{name} {prop}",
    }


def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": f"'{value}'"}}}


def boolean(value: bool) -> dict:
    return {"expr": {"Literal": {"Value": "true" if value else "false"}}}


def title_obj(text: str) -> dict:
    return {
        "title": [{"properties": {"show": boolean(True), "text": lit(text),
                                  "fontSize": {"expr": {"Literal": {"Value": "11D"}}}}}]
    }


# ---------------------------------------------------------------- wizualizacje


def visual(name: str, vtype: str, x: int, y: int, w: int, h: int,
           roles: dict[str, list[dict]] | None = None,
           title: str | None = None,
           objects: dict | None = None,
           z: int | None = None) -> dict:
    v: dict = {"visualType": vtype}
    if roles:
        v["query"] = {"queryState": {role: {"projections": projs} for role, projs in roles.items()}}
    if objects:
        v["objects"] = objects
    if title:
        v["visualContainerObjects"] = title_obj(title)
    return {
        "$schema": SCHEMA_VIS,
        "name": name,
        "position": {"x": x, "y": y, "z": z if z is not None else 0,
                     "width": w, "height": h, "tabOrder": 0},
        "visual": v,
    }


def textbox(name: str, x: int, y: int, w: int, h: int, text: str,
            size: str = "14pt", color: str = "#F2F2F2", align: str = "left",
            bold: bool = False) -> dict:
    style = {"fontFamily": "Segoe UI", "fontSize": size, "color": color}
    if bold:
        style["fontWeight"] = "bold"
    return visual(
        name, "textbox", x, y, w, h,
        objects={"general": [{"properties": {"paragraphs": [
            {"textRuns": [{"value": text, "textStyle": style}], "horizontalTextAlignment": align}
        ]}}]},
    )


def header(page_no: int, title: str, question: str) -> list[dict]:
    return [
        textbox(f"p{page_no}_hdr", 16, 8, 900, 40, f"{page_no}. {title}", size="20pt", bold=True),
        textbox(f"p{page_no}_sub", 16, 46, 900, 26, question, size="11pt", color="#A6A6A6"),
        textbox(f"p{page_no}_ftr", 16, H - 26, 900, 22, FOOTER, size="9pt", color="#8C8C8C"),
    ]


def card(name: str, x: int, y: int, w: int, h: int, entity: str, measure: str, title: str) -> dict:
    return visual(name, "card", x, y, w, h, {"Values": [mea(entity, measure)]}, title=title)


def card_agg(name: str, x: int, y: int, w: int, h: int, entity: str, prop: str, fn: int, title: str) -> dict:
    return visual(name, "card", x, y, w, h, {"Values": [agg(entity, prop, fn)]}, title=title)


# ---------------------------------------------------------------- strony

CARD_H = 88


def page1() -> tuple[str, str, list[dict]]:
    vis = header(1, "Mapa zaleznosci", "Czym jest krajowa infrastruktura krytyczna i jak bardzo jest ze soba splatana.")
    cards = [
        ("p1_c1", "DimNode", "Obiekty IK", "Obiekty IK"),
        ("p1_c2", "FactDependency", "Zaleznosci", "Zaleznosci miedzy obiektami"),
        ("p1_c3", "FactDependency", "Udzial zaleznosci bez redundancji %", "Bez redundancji %"),
        ("p1_c4", "FactDependency", "Zaleznosci niesprawdzone w cwiczeniu %", "Niesprawdzone w cwiczeniu %"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(visual("p1_map", "azureMap", 16, 180, 440, 380, {
        "Category": [col("DimNode", "node_name")],
        "Latitude": [agg("DimNode", "lat", AVG)],
        "Longitude": [agg("DimNode", "lon", AVG)],
        "Size": [agg("DimNode", "population_served", SUM, "Ludnosc obslugiwana")],
    }, title="Rozmieszczenie obiektow IK (rozmiar = ludnosc obslugiwana)"))
    vis.append(visual("p1_matrix", "pivotTable", 468, 180, 460, 380, {
        "Rows": [col("FactDependency", "source_system")],
        "Columns": [col("FactDependency", "target_system")],
        "Values": [mea("FactDependency", "Zaleznosci")],
    }, title="Macierz zaleznosci: system dostawcy x system odbiorcy"))
    vis.append(visual("p1_types", "barChart", 940, 180, 324, 190, {
        "Category": [col("FactDependency", "dependency_type")],
        "Y": [mea("FactDependency", "Zaleznosci")],
    }, title="Typy zaleznosci"))
    vis.append(visual("p1_sl1", "slicer", 940, 378, 324, 60, {"Values": [col("DimVoivodeship", "voivodeship_name")]},
                      title="Wojewodztwo"))
    vis.append(visual("p1_sl2", "slicer", 940, 442, 324, 60, {"Values": [col("DimSystem", "system_name")]},
                      title="System IK"))
    vis.append(visual("p1_sl3", "slicer", 940, 506, 324, 54, {"Values": [col("DimNode", "criticality_class")]},
                      title="Klasa krytycznosci"))
    vis.append(textbox("p1_note", 16, 568, 1248, 60,
                       "System energetyczny jest dostawca dla wszystkich pozostalych dziesieciu systemow. "
                       "To nie opinia - to policzalna wlasciwosc grafu.", size="11pt", color="#D9D9D9"))
    return "p1MapaZaleznosci", "1. Mapa zaleznosci", vis


def page2() -> tuple[str, str, list[dict]]:
    vis = header(2, "Wylacz ten wezel", "Co sie stanie, jesli ten jeden obiekt przestanie dzialac.")
    vis.append(visual("p2_sl", "slicer", 16, 80, 300, 96, {"Values": [col("DimNode", "node_name")]},
                      title="Wybierz obiekt"))
    vis.append(card("p2_head", 328, 80, 936, CARD_H, "FactCascadeTimeline", "Naglowek kaskady",
                    "Skutki wybranego zdarzenia"))
    vis.append(visual("p2_tree", "decompositionTreeVisual", 16, 184, 640, 340, {
        "Analyze": [agg("FactEffectTree", "node_id", COUNT, "Obiekty dotkniete")],
        "ExplainBy": [col("FactEffectTree", "wave"), col("FactEffectTree", "system_group"),
                      col("FactEffectTree", "node_type"), col("FactEffectTree", "node_name")],
    }, title="Drzewo skutkow: fala > system > typ obiektu > obiekt"))
    vis.append(visual("p2_time", "columnChart", 668, 184, 596, 200, {
        "Category": [col("FactCascadeTimeline", "fail_hour")],
        "Series": [col("FactCascadeTimeline", "system_group")],
        "Y": [mea("FactCascadeTimeline", "Obiekty w kaskadzie")],
    }, title="Os czasu skutkow wg systemu IK"))
    vis.append(visual("p2_first", "tableEx", 668, 392, 596, 132, {
        "Values": [col("FactCascadeTimeline", "system_group"),
                   agg("FactCascadeTimeline", "fail_hour", MIN, "Pierwszy skutek (h)"),
                   mea("FactCascadeTimeline", "Obiekty w kaskadzie")],
    }, title="Kiedy zabraknie uslugi w kazdym z systemow"))
    vis.append(visual("p2_types", "barChart", 16, 532, 624, 156, {
        "Category": [col("FactEffectTree", "node_type")],
        "Y": [agg("FactEffectTree", "node_id", COUNT, "Obiekty")],
    }, title="Skutki wg typu obiektu"))
    vis.append(textbox("p2_note", 668, 532, 596, 150,
                       "Klikniecie w jeden obiekt - i po sekundzie pelna lista skutkow drugiego i trzeciego "
                       "rzedu wraz z czasem ich wystapienia. Skutki wychodza poza system, w ktorym doszlo "
                       "do awarii, i poza resort, ktory za ten system odpowiada.", size="11pt", color="#D9D9D9"))
    return "p2WylaczWezel", "2. Wylacz ten wezel", vis


def page3() -> tuple[str, str, list[dict]]:
    vis = header(3, "Pojedyncze punkty awarii", "Gdzie jedna awaria kosztuje najwiecej i czy w ogole o tych obiektach wiemy.")
    cards = [
        ("p3_c1", "FactCascadeCentrality", "Pojedyncze punkty awarii", "Pojedyncze punkty awarii"),
        ("p3_c2", "FactCascadeCentrality", "SPOF poza rejestrem IK", "SPOF poza rejestrem IK"),
        ("p3_c3", "FactCascadeCentrality", "SPOF bez umowy SPO-10", "SPOF bez umowy SPO-10"),
        ("p3_c4", "DimNode", "Krytyczne obiekty bez kontaktu operacyjnego", "Bez kontaktu operacyjnego"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(visual("p3_rank", "tableEx", 16, 180, 620, 250, {
        "Values": [col("FactCascadeCentrality", "node_name"), col("FactCascadeCentrality", "system_code"),
                   mea("FactCascadeCentrality", "Indeks kaskadowy"),
                   agg("FactCascadeCentrality", "cascade_nodes", MAX, "Obiekty w kaskadzie"),
                   agg("FactCascadeCentrality", "cascade_systems", MAX, "Systemy IK"),
                   agg("FactCascadeCentrality", "cascade_population", MAX, "Ludnosc")],
    }, title="Ranking obiektow wg indeksu kaskadowego"))
    vis.append(visual("p3_scatter", "scatterChart", 648, 180, 616, 250, {
        "Category": [col("FactCascadeCentrality", "node_name")],
        "Series": [col("FactCascadeCentrality", "system_code")],
        "X": [agg("FactCascadeCentrality", "cascade_nodes", MAX, "Obiekty w kaskadzie")],
        "Y": [agg("FactCascadeCentrality", "cascade_population", MAX, "Ludnosc")],
    }, title="Zasieg kaskady a ludnosc dotknieta"))
    vis.append(visual("p3_spof", "tableEx", 16, 438, 620, 220, {
        "Values": [col("FactSpof", "node_name"), col("FactSpof", "spof_reason"),
                   col("FactSpof", "operator_name"), col("FactSpof", "backup_type")],
    }, title="Powod klasyfikacji jako pojedynczy punkt awarii"))
    vis.append(visual("p3_map", "azureMap", 648, 438, 616, 220, {
        "Category": [col("DimNode", "node_name")],
        "Latitude": [agg("DimNode", "lat", AVG)],
        "Longitude": [agg("DimNode", "lon", AVG)],
        "Size": [mea("FactCascadeCentrality", "Indeks kaskadowy")],
    }, title="Koncentracja obiektow o wysokim indeksie kaskadowym"))
    vis.append(textbox("p3_note", 16, 664, 1248, 30,
                       "Najwyzej w rankingu nie stoi elektrownia, tylko magazyn paliw - bo zasila generatory, "
                       "ktore zasilaja wszystko inne.", size="11pt", color="#D9D9D9"))
    return "p3PunktyAwarii", "3. Pojedyncze punkty awarii", vis


def page4() -> tuple[str, str, list[dict]]:
    vis = header(4, "Powodz wrzesien - kaskada w czasie",
                 "Jak wyglada pelna kaskada realnego zdarzenia i kiedy przestaje byc lokalna.")
    cards = [
        ("p4_c1", "FactCascadeTimeline", "Zdarzenia inicjujace", "Zdarzenia inicjujace"),
        ("p4_c2", "FactCascadeTimeline", "Skutki wtorne", "Skutki wtorne"),
        ("p4_c3", "FactCascadeTimeline", "Wspolczynnik wzmocnienia", "Wspolczynnik wzmocnienia"),
        ("p4_c4", "FactCascadeTimeline", "Okno reakcji (h)", "Okno reakcji (h)"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(card("p4_esc", 880, 80, 384, CARD_H, "FactCascadeTimeline", "Poziom eskalacji", "Poziom eskalacji"))
    vis.append(visual("p4_waves", "stackedAreaChart", 16, 180, 620, 240, {
        "Category": [col("FactCascadeTimeline", "fail_hour")],
        "Series": [col("FactCascadeTimeline", "wave")],
        "Y": [mea("FactCascadeTimeline", "Obiekty w kaskadzie")],
    }, title="Os czasu fal kaskady (godzina od D0)"))
    vis.append(visual("p4_prof", "lineChart", 648, 180, 616, 240, {
        "Category": [col("FactCascadeTimeline", "fail_hour")],
        "Series": [col("FactCascadeTimeline", "system_group")],
        "Y": [mea("FactCascadeTimeline", "Obiekty w kaskadzie")],
    }, title="Profil systemowy kaskady"))
    vis.append(visual("p4_gmina", "tableEx", 16, 428, 620, 230, {
        "Values": [col("FactGminaTimeToEffect", "gmina_name"),
                   agg("FactGminaTimeToEffect", "energy", MIN, "Energia (h)"),
                   agg("FactGminaTimeToEffect", "water", MIN, "Woda (h)"),
                   agg("FactGminaTimeToEffect", "health", MIN, "Zdrowie (h)"),
                   agg("FactGminaTimeToEffect", "telecom", MIN, "Lacznosc (h)")],
    }, title="Czas do skutku w gminie (godziny od D0)"))
    vis.append(visual("p4_wavebar", "barChart", 648, 428, 616, 230, {
        "Category": [col("FactCascadeWaves", "wave")],
        "Y": [agg("FactCascadeWaves", "nodes", SUM, "Obiekty")],
    }, title="Liczba obiektow w kolejnych falach"))
    vis.append(textbox("p4_note", 16, 664, 1248, 30,
                       "Zdarzenie mnozy sie ponad trzykrotnie, a pierwszy skutek wtorny pojawia sie po 33 minutach "
                       "- czyli zanim sztab zdazy sie zebrac.", size="11pt", color="#D9D9D9"))
    return "p4PowodzKaskada", "4. Powodz wrzesien", vis


def page5() -> tuple[str, str, list[dict]]:
    vis = header(5, "Co warto wzmocnic", "Gdzie wydac pieniadze, zeby to samo zdarzenie zabolalo mniej.")
    cards = [
        ("p5_c1", "FactWhatIf", "Redukcja skutkow wtornych %", "Redukcja skutkow wtornych %"),
        ("p5_c2", "FactWhatIf", "Ludnosc uratowana", "Ludnosc uratowana"),
        ("p5_c3", "FactWhatIf", "Efektywnosc wariantu", "Efektywnosc wariantu"),
        ("p5_c4", "FactMarginalValue", "Najlepsza pojedyncza inwestycja", "Najlepsza pojedyncza inwestycja"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 306, 80, 290, CARD_H, e, m, t))
    vis.append(visual("p5_var", "barChart", 16, 180, 620, 240, {
        "Category": [col("FactWhatIf", "variant")],
        "Y": [agg("FactWhatIf", "nodes_failed_secondary", SUM, "Skutki wtorne")],
    }, title="Skutki wtorne w wariantach BAZOWY / A / B / C"))
    vis.append(visual("p5_vartab", "tableEx", 648, 180, 616, 240, {
        "Values": [col("FactWhatIf", "variant"), col("FactWhatIf", "description"),
                   agg("FactWhatIf", "hardened_nodes", SUM, "Obiekty wzmocnione"),
                   agg("FactWhatIf", "secondary_reduction_pct", MAX, "Redukcja skutkow %"),
                   agg("FactWhatIf", "population_reduction_pct", MAX, "Redukcja ludnosci %")],
    }, title="Warianty inwestycyjne"))
    vis.append(visual("p5_marg", "tableEx", 16, 428, 1248, 230, {
        "Values": [col("FactMarginalValue", "node_name"), col("FactMarginalValue", "node_type"),
                   col("FactMarginalValue", "operator_name"),
                   agg("FactMarginalValue", "current_autonomy_h", MAX, "Autonomia (h)"),
                   agg("FactMarginalValue", "nodes_saved", MAX, "Obiekty uratowane"),
                   agg("FactMarginalValue", "population_saved", MAX, "Ludnosc uratowana"),
                   col("FactMarginalValue", "spo10_agreement")],
    }, title="Ranking inwestycji: obiekty do wzmocnienia"))
    vis.append(textbox("p5_note", 16, 664, 1248, 30,
                       "Wariant tanszy - agregaty w obiektach uslugowych - daje kilkukrotnie wieksza redukcje "
                       "niz wariant drozszy, czyli nowe linie zasilajace.", size="11pt", color="#D9D9D9"))
    return "p5CoWzmocnic", "5. Co warto wzmocnic", vis


def page6() -> tuple[str, str, list[dict]]:
    vis = header(6, "Gotowosc i wspolpraca (SPO-10)", "Czy mamy z kim rozmawiac, zanim cos sie stanie.")
    cards = [
        ("p6_c1", "DimNode", "Obiekty w rejestrze IK %", "Obiekty w rejestrze IK %"),
        ("p6_c2", "DimNode", "Umowy o wymianie danych %", "Umowy o wymianie danych %"),
        ("p6_c3", "FactSpo10", "Plany ochrony nieaktualne", "Plany ochrony nieaktualne"),
        ("p6_c4", "FactSpo10", "Responsywnosc operatora", "Responsywnosc operatora"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(visual("p6_ops", "tableEx", 16, 180, 700, 250, {
        "Values": [col("FactSpo10", "operator_name"),
                   mea("DimNode", "Obiekty IK"),
                   mea("FactSpo10", "Responsywnosc operatora"),
                   agg("FactSpo10", "last_contact_test", MAX, "Ostatni test kontaktu"),
                   agg("FactSpo10", "protection_plan_age_days", MAX, "Wiek planu (dni)")],
    }, title="Operatorzy infrastruktury krytycznej"))
    vis.append(visual("p6_gap", "columnChart", 728, 180, 536, 250, {
        "Category": [col("DimSystem", "system_name")],
        "Y": [mea("FactCascadeCentrality", "SPOF poza rejestrem IK")],
    }, title="Luka rejestrowa: SPOF poza rejestrem IK wg systemu"))
    vis.append(visual("p6_plans", "columnChart", 16, 438, 620, 220, {
        "Category": [col("FactSpo10", "protection_plan_status")],
        "Y": [agg("FactSpo10", "node_id", COUNT, "Obiekty")],
    }, title="Stan planow ochrony"))
    vis.append(visual("p6_ex", "columnChart", 648, 438, 616, 220, {
        "Category": [col("DimNode", "last_exercise_date")],
        "Y": [mea("DimNode", "Obiekty IK")],
    }, title="Data ostatniego cwiczenia"))
    vis.append(textbox("p6_note", 16, 664, 1248, 30,
                       "Czesc obiektow o najwyzszym indeksie kaskadowym jest poza rejestrem IK i bez umowy "
                       "o wymianie danych. Model odpornosci jest tyle wart, ile jakosc rejestru.",
                       size="11pt", color="#D9D9D9"))
    return "p6GotowoscSpo10", "6. Gotowosc i wspolpraca", vis


PAGE_BUILDERS = [page1, page2, page3, page4, page5, page6]

# ---------------------------------------------------------------- motyw

DARK_THEME = {
    "name": "OL-ZK-Dark",
    "dataColors": ["#4FC3F7", "#FFB74D", "#E57373", "#81C784", "#BA68C8", "#4DD0E1",
                   "#F06292", "#AED581", "#FFD54F", "#9575CD", "#4DB6AC", "#FF8A65"],
    "background": "#1B1B1F",
    "foreground": "#F2F2F2",
    "tableAccent": "#4FC3F7",
    "good": "#81C784",
    "neutral": "#FFB74D",
    "bad": "#E57373",
    "maximum": "#E57373",
    "center": "#FFB74D",
    "minimum": "#81C784",
    "visualStyles": {
        "*": {
            "*": {
                "background": [{"color": {"solid": {"color": "#26262B"}}, "transparency": 0}],
                "border": [{"show": True, "color": {"solid": {"color": "#3A3A42"}}, "radius": 6}],
                "title": [{"show": True, "fontColor": {"solid": {"color": "#F2F2F2"}},
                           "background": {"solid": {"color": "#26262B"}}, "fontSize": 11}],
                "labels": [{"color": {"solid": {"color": "#F2F2F2"}}}],
                "categoryAxis": [{"labelColor": {"solid": {"color": "#C7C7CF"}},
                                  "gridlineColor": {"solid": {"color": "#3A3A42"}}}],
                "valueAxis": [{"labelColor": {"solid": {"color": "#C7C7CF"}},
                               "gridlineColor": {"solid": {"color": "#3A3A42"}}}],
                "legend": [{"labelColor": {"solid": {"color": "#C7C7CF"}}}],
            }
        },
        "card": {"*": {"labels": [{"color": {"solid": {"color": "#4FC3F7"}}, "fontSize": 26}],
                       "categoryLabels": [{"color": {"solid": {"color": "#A6A6A6"}}, "fontSize": 9}]}},
        "textbox": {"*": {"background": [{"show": False}], "border": [{"show": False}]}},
    },
}

THEME_FILE = "OL-ZK-Dark.json"

# ---------------------------------------------------------------- definicja


def build_parts(semantic_model_id: str, use_theme: bool) -> list[tuple[str, str]]:
    """Zwraca liste (sciezka, tekst JSON)."""
    parts: list[tuple[str, str]] = []

    parts.append(("definition.pbir", json.dumps({
        "$schema": SCHEMA_PBIR,
        "version": "4.0",
        "datasetReference": {"byConnection": {
            "connectionString": None,
            "pbiServiceModelId": None,
            "pbiModelVirtualServerName": "sobe_wowvirtualserver",
            "pbiModelDatabaseName": semantic_model_id,
            "connectionType": "pbiServiceXmlaStyleLive",
            "name": "EntityDataSource",
        }},
    }, indent=2, ensure_ascii=False)))

    parts.append(("definition/version.json", json.dumps({
        "$schema": SCHEMA_VERSION, "version": "2.0.0",
    }, indent=2)))

    report: dict = {
        "$schema": SCHEMA_REPORT,
        "themeCollection": {"baseTheme": {"name": "CY24SU02", "reportVersionAtImport": "5.55",
                                          "type": "SharedResources"}},
        "layoutOptimization": "None",
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True},
    }
    if use_theme:
        report["themeCollection"]["customTheme"] = {"name": "OL-ZK-Dark", "reportVersionAtImport": "5.55",
                                                   "type": "RegisteredResources"}
        report["resourcePackages"] = [{
            "name": "RegisteredResources", "type": "RegisteredResources",
            "items": [{"name": THEME_FILE, "path": THEME_FILE, "type": "CustomTheme"}],
        }]
        parts.append((f"StaticResources/RegisteredResources/{THEME_FILE}",
                      json.dumps(DARK_THEME, indent=2, ensure_ascii=False)))
    parts.append(("definition/report.json", json.dumps(report, indent=2, ensure_ascii=False)))

    order: list[str] = []
    for build in PAGE_BUILDERS:
        name, display, visuals = build()
        order.append(name)
        parts.append((f"definition/pages/{name}/page.json", json.dumps({
            "$schema": SCHEMA_PAGE, "name": name, "displayName": display,
            "displayOption": "FitToPage", "height": H, "width": W,
        }, indent=2, ensure_ascii=False)))
        for v in visuals:
            parts.append((f"definition/pages/{name}/visuals/{v['name']}/visual.json",
                          json.dumps(v, indent=2, ensure_ascii=False)))

    parts.append(("definition/pages/pages.json", json.dumps({
        "$schema": SCHEMA_PAGES, "pageOrder": order, "activePageName": order[0],
    }, indent=2)))

    parts.append((".platform", json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": REPORT_NAME, "description": REPORT_DESC},
        "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
    }, indent=2, ensure_ascii=False)))

    return parts


# ---------------------------------------------------------------- walidacja


def validate(parts: list[tuple[str, str]], columns: dict[str, set[str]], measures: dict[str, str]) -> list[str]:
    errors: list[str] = []
    names: dict[str, set[str]] = {}
    checked = 0

    for path, text in parts:
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: niepoprawny JSON - {exc}")
            continue
        if not path.endswith("visual.json"):
            continue
        page = path.split("/")[2]
        vname = doc["name"]
        if vname in names.setdefault(page, set()):
            errors.append(f"{page}: zdublowana nazwa wizualizacji '{vname}'")
        names[page].add(vname)
        if len(vname) > 50 or not all(c.isalnum() or c in "-_" for c in vname):
            errors.append(f"{page}/{vname}: nazwa niezgodna z [A-Za-z0-9_-]{{1,50}}")
        pos = doc["position"]
        if pos["x"] < 0 or pos["y"] < 0 or pos["x"] + pos["width"] > W or pos["y"] + pos["height"] > H:
            errors.append(f"{page}/{vname}: wizualizacja poza kanwa {W}x{H} ({pos})")
        qs = doc["visual"].get("query", {}).get("queryState", {})
        for role, block in qs.items():
            for proj in block["projections"]:
                field = proj["field"]
                checked += 1
                if "Measure" in field:
                    entity = field["Measure"]["Expression"]["SourceRef"]["Entity"]
                    prop = field["Measure"]["Property"]
                    if prop not in measures:
                        errors.append(f"{page}/{vname}[{role}]: brak miary '{prop}' w modelu")
                    elif measures[prop] != entity:
                        errors.append(f"{page}/{vname}[{role}]: miara '{prop}' nalezy do "
                                      f"'{measures[prop]}', a nie '{entity}'")
                else:
                    if "Aggregation" in field:
                        c = field["Aggregation"]["Expression"]["Column"]
                    else:
                        c = field["Column"]
                    entity = c["Expression"]["SourceRef"]["Entity"]
                    prop = c["Property"]
                    if entity not in columns:
                        errors.append(f"{page}/{vname}[{role}]: brak tabeli '{entity}' w modelu")
                    elif prop not in columns[entity]:
                        errors.append(f"{page}/{vname}[{role}]: brak kolumny '{entity}'[{prop}]")
    print(f"  sprawdzono {checked} odwolan do modelu w {sum(len(v) for v in names.values())} wizualizacjach")
    return errors


# ---------------------------------------------------------------- Fabric API


def token(resource: str = "https://api.fabric.microsoft.com") -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def wait_operation(resp: requests.Response, tk: str) -> requests.Response:
    if resp.status_code != 202:
        return resp
    op = resp.headers.get("x-ms-operation-id")
    for _ in range(120):
        time.sleep(3)
        r = requests.get(f"{FABRIC_API}/operations/{op}", headers={"Authorization": f"Bearer {tk}"}, timeout=60)
        status = r.json().get("status")
        if status not in ("NotStarted", "Running"):
            if status != "Succeeded":
                sys.exit(f"Operacja zakonczona statusem {status}: {r.text[:600]}")
            return r
    sys.exit("Przekroczono czas oczekiwania na operacje Fabric.")


def deploy(parts: list[tuple[str, str]], workspace_id: str) -> str:
    tk = token()
    hdr = {"Authorization": f"Bearer {tk}", "Content-Type": "application/json"}
    payload_parts = [{"path": p, "payload": base64.b64encode(t.encode("utf-8")).decode("ascii"),
                      "payloadType": "InlineBase64"} for p, t in parts]

    r = requests.get(f"{FABRIC_API}/workspaces/{workspace_id}/reports", headers=hdr, timeout=120)
    r.raise_for_status()
    existing = next((i for i in r.json().get("value", []) if i["displayName"] == REPORT_NAME), None)

    if existing:
        rid = existing["id"]
        print(f"  aktualizuje istniejacy raport {rid}")
        resp = requests.post(f"{FABRIC_API}/workspaces/{workspace_id}/reports/{rid}/updateDefinition",
                             headers=hdr, json={"definition": {"parts": payload_parts}}, timeout=300)
        if resp.status_code not in (200, 202):
            sys.exit(f"updateDefinition {resp.status_code}: {resp.text[:1200]}")
        wait_operation(resp, tk)
    else:
        print("  tworze nowy raport")
        resp = requests.post(f"{FABRIC_API}/workspaces/{workspace_id}/reports", headers=hdr, json={
            "displayName": REPORT_NAME, "description": REPORT_DESC,
            "definition": {"parts": payload_parts},
        }, timeout=300)
        if resp.status_code not in (200, 201, 202):
            sys.exit(f"create report {resp.status_code}: {resp.text[:1200]}")
        done = wait_operation(resp, tk)
        rid = (resp.json() if resp.status_code in (200, 201) else done.json().get("result", {})).get("id")
        if not rid:
            r = requests.get(f"{FABRIC_API}/workspaces/{workspace_id}/reports", headers=hdr, timeout=120)
            rid = next(i["id"] for i in r.json()["value"] if i["displayName"] == REPORT_NAME)
    return rid


def readback(workspace_id: str, report_id: str) -> None:
    tk = token()
    hdr = {"Authorization": f"Bearer {tk}"}
    r = requests.post(f"{FABRIC_API}/workspaces/{workspace_id}/reports/{report_id}/getDefinition",
                      headers=hdr, timeout=300)
    if r.status_code == 202:
        op = r.headers.get("x-ms-operation-id")
        wait_operation(r, tk)
        r = requests.get(f"{FABRIC_API}/operations/{op}/result", headers=hdr, timeout=300)
    parts = r.json().get("definition", {}).get("parts", [])
    print(f"  odczyt zwrotny: {len(parts)} czesci definicji")
    pages = sorted({p["path"].split("/")[2] for p in parts
                    if p["path"].startswith("definition/pages/") and p["path"].count("/") >= 3})
    vis = len([p for p in parts if p["path"].endswith("visual.json")])
    print(f"  strony: {len(pages)} -> {', '.join(pages)}")
    print(f"  wizualizacje: {vis}")
    if len(pages) != len(PAGE_BUILDERS):
        print(f"  UWAGA: oczekiwano {len(PAGE_BUILDERS)} stron")


# ---------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-theme", action="store_true", help="pomin ciemny motyw (diagnostyka)")
    ap.add_argument("--save", metavar="DIR", help="zapisz definicje na dysk (podglad)")
    args = ap.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, sm = state["workspaceId"], state["semanticModelId"]

    print("Metadane modelu semantycznego...")
    _, columns, measures = load_model_metadata()
    print(f"  {len(columns)} tabel, {len(measures)} miar")

    print("Budowanie definicji PBIR...")
    parts = build_parts(sm, use_theme=not args.no_theme)
    print(f"  {len(parts)} czesci, {sum(len(t) for _, t in parts) // 1024} KB")

    print("Walidacja...")
    errors = validate(parts, columns, measures)
    if errors:
        print(f"\nBLEDY ({len(errors)}):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("  OK")

    if args.save:
        out = pathlib.Path(args.save)
        for p, t in parts:
            f = out / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t, encoding="utf-8")
        print(f"  zapisano do {out}")

    if args.dry_run:
        print("\n--dry-run: pomijam wdrozenie.")
        return

    print("Wdrozenie do Fabric...")
    rid = deploy(parts, ws)
    print(f"  reportId = {rid}")
    readback(ws, rid)

    state["reportId"] = rid
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGotowe. https://app.powerbi.com/groups/{ws}/reports/{rid}")


if __name__ == "__main__":
    main()
