"""Wdrozenie notatnikow do Microsoft Fabric.

Tworzy w workspace:
  * 00_ingest_to_delta  — CSV z Files/raw -> tabele Delta (kody TERYT jako string)
  * 01..04              — notatniki analityczne przeniesione z katalogu notebooks/

Uzycie:
    python deploy\\03_deploy_notebooks.py            # utworz/zaktualizuj
    python deploy\\03_deploy_notebooks.py --run      # dodatkowo uruchom 00
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads((ROOT / ".fabric" / "deployment.json").read_text(encoding="utf-8"))
WS = STATE["workspaceId"]
LH = STATE["lakehouseId"]
API = "https://api.fabric.microsoft.com/v1"

FILES = "/lakehouse/default/Files"
DIM_DIR = f"{FILES}/raw/dimensions"
DER_DIR = f"{FILES}/raw/derived"


def token(resource: str = "https://api.fabric.microsoft.com") -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"Brak tokenu: {out.stderr}")
    return out.stdout.strip()


def headers() -> dict:
    return {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


# --------------------------------------------------------------------------
# Budowa notatnika 00 — ingest do Delta
# --------------------------------------------------------------------------

CODE_COLS = ["voivodeship_code", "powiat_code", "gmina_code", "src_sys", "dst_sys"]

DIM_TABLES = [
    "dim_voivodeship", "dim_powiat", "dim_gmina", "dim_hazard", "dim_river_gauge",
    "dim_ci_system", "dim_ci_node", "fact_ci_dependency",
    "fact_node_hazard_exposure", "fact_spo10_cooperation",
]

DER_TABLES = [
    "graph_nodes", "graph_edges", "system_summary", "dependency_matrix", "spo10_gaps",
    "cascade_flood_timeline", "cascade_waves", "cascade_hourly_profile",
    "cascade_single_node_timeline", "cascade_effect_tree", "cascade_gmina_time_to_effect",
    "cascade_centrality", "cascade_top100", "single_points_of_failure",
    "cascade_by_voivodeship", "cascade_by_system",
    "whatif_variants", "whatif_marginal_value",
]

INGEST_CELLS = [
    '''# Ingest: CSV z Files/raw -> tabele Delta w lh_ci_graph
#
# Kody TERYT musza pozostac tekstem. Autodetekcja typow zamienia "02" na 2,
# co zrywa relacje z dim_voivodeship. Dlatego kolumny kodowe sa rzutowane
# jawnie na string i uzupelniane wiodacymi zerami.
from pyspark.sql import functions as F

CODE_WIDTHS = {"voivodeship_code": 2, "powiat_code": 4, "gmina_code": 7}
''',

    f'''DIM_DIR = "Files/raw/dimensions"
DER_DIR = "Files/raw/derived"

DIM_TABLES = {json.dumps(DIM_TABLES, indent=4)}

DER_TABLES = {json.dumps(DER_TABLES, indent=4)}
''',

    '''def load_csv_to_delta(folder: str, name: str) -> int:
    df = (spark.read
          .option("header", "true")
          .option("inferSchema", "true")
          .option("multiLine", "true")
          .option("escape", '"')
          .csv(f"{folder}/{name}.csv"))

    for col, width in CODE_WIDTHS.items():
        if col in df.columns:
            df = df.withColumn(col, F.lpad(F.col(col).cast("string"), width, "0"))

    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)
    return df.count()
''',

    '''results = []
for t in DIM_TABLES:
    results.append((t, load_csv_to_delta(DIM_DIR, t)))
    print(f"{t:<32} {results[-1][1]:>8} wierszy")
''',

    '''for t in DER_TABLES:
    try:
        results.append((t, load_csv_to_delta(DER_DIR, t)))
        print(f"{t:<32} {results[-1][1]:>8} wierszy")
    except Exception as exc:
        print(f"{t:<32} POMINIETO ({type(exc).__name__})")
''',

    '''# Kontrola zgodnosci z wartosciami referencyjnymi z repozytorium
EXPECTED = {
    "dim_ci_node": 2106,
    "fact_ci_dependency": 6552,
    "dim_gmina": 2477,
    "cascade_flood_timeline": 777,
    "single_points_of_failure": 217,
    "cascade_centrality": 2106,
}
actual = dict(results)
problems = [(k, v, actual.get(k)) for k, v in EXPECTED.items() if actual.get(k) != v]
if problems:
    for k, exp, got in problems:
        print(f"ROZBIEZNOSC {k}: oczekiwano {exp}, jest {got}")
    raise AssertionError("Dane nie zgadzaja sie z wartosciami referencyjnymi.")
print(f"OK — {len(results)} tabel Delta, wartosci referencyjne zgodne.")
''',

    '''# Kontrola kluczowa: kod wojewodztwa dolnoslaskiego musi byc tekstem "02"
display(spark.sql("""
    SELECT n.voivodeship_code, v.voivodeship_name, COUNT(*) AS obiekty_ik
    FROM dim_ci_node n
    JOIN dim_voivodeship v ON v.voivodeship_code = n.voivodeship_code
    GROUP BY n.voivodeship_code, v.voivodeship_name
    ORDER BY obiekty_ik DESC
"""))
''',

    '''# Telemetria stanu obiektow -> Delta (potrzebna modelowi semantycznemu;
# w warstwie operacyjnej te same zdarzenia obsluguje Eventhouse).
tel = (spark.read.json("Files/raw/streams/ci_node_status.jsonl")
       .withColumn("event_time", F.to_timestamp("event_time"))
       .withColumn("on_backup_power", F.col("on_backup_power").cast("boolean")))
for col, width in CODE_WIDTHS.items():
    if col in tel.columns:
        tel = tel.withColumn(col, F.lpad(F.col(col).cast("string"), width, "0"))

tel.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("fact_node_status")
print(f"fact_node_status: {tel.count()} zdarzen")

# Stan na szczycie zdarzenia — podstawa kart w raporcie dla decydenta
peak_hour = (tel.filter(F.col("status") == "down")
             .groupBy(F.date_trunc("hour", "event_time").alias("h"))
             .count().orderBy(F.desc("count")).first())
print(f"szczyt awarii: {peak_hour['h']} — {peak_hour['count']} obiektow niedzialajacych")

(tel.filter(F.date_trunc("hour", F.col("event_time")) == F.lit(peak_hour["h"]))
    .write.mode("overwrite").option("overwriteSchema", "true")
    .saveAsTable("fact_node_status_peak"))
''',

    '''# Eksport schematow tabel Delta — zrodlo prawdy dla modelu semantycznego DirectLake
import json

tables = [r.tableName for r in spark.sql("SHOW TABLES").collect()]
schemas = {
    t: [{"name": f.name, "type": f.dataType.simpleString()} for f in spark.table(t).schema.fields]
    for t in tables
}
mssparkutils.fs.put("Files/raw/_schemas.json",
                    json.dumps(schemas, indent=2, ensure_ascii=False), overwrite=True)
print(f"Zapisano schematy {len(schemas)} tabel do Files/raw/_schemas.json")
''',
]


def build_notebook(cells: list[str], name: str) -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": [
            {"cell_type": "code", "source": c.splitlines(keepends=True),
             "execution_count": None, "outputs": [], "metadata": {}}
            for c in cells
        ],
        "metadata": {
            "language_info": {"name": "python"},
            "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
            "dependencies": {
                "lakehouse": {
                    "default_lakehouse": LH,
                    "default_lakehouse_name": "lh_ci_graph",
                    "default_lakehouse_workspace_id": WS,
                }
            },
        },
    }


def convert_local_notebook(path: Path) -> list[str]:
    """Zamienia skrypt z notebooks/ na komorki wykonywalne w Fabric."""
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'BASE = Path(__file__).resolve().parents[1]\nDATA = BASE / "datasets"\nOUT = DATA / "derived"\nOUT.mkdir(exist_ok=True)',
        f'DATA = Path("{DIM_DIR}")\nOUT = Path("{DER_DIR}")\nOUT.mkdir(parents=True, exist_ok=True)',
    )
    text = text.replace(
        'BASE = Path(__file__).resolve().parents[1]\nDATA = BASE / "datasets"\nOUT = DATA / "derived"',
        f'DATA = Path("{DIM_DIR}")\nOUT = Path("{DER_DIR}")',
    )
    text = text.replace('sys.path.append(str(BASE))', f'sys.path.append("{FILES}/code")')
    text = text.replace('sys.path.insert(0, str(BASE))', f'sys.path.insert(0, "{FILES}/code")')

    cells = [c.strip("\n") for c in text.split("# CELL")]
    cells = [c for c in cells if c.strip()]

    prelude = (
        "# Notatnik przeniesiony z repozytorium ol-infrastruktura-krytyczna.\n"
        "# Dane wejsciowe: Files/raw/dimensions, wyniki: Files/raw/derived.\n"
        "import sys\n"
        f'sys.path.insert(0, "{FILES}/code")   # cascade_engine.py\n'
        f'from pathlib import Path\n'
        f'DATA = Path("{DIM_DIR}")\n'
        f'OUT = Path("{DER_DIR}")\n'
        f'OUT.mkdir(parents=True, exist_ok=True)\n'
    )
    return [prelude] + cells


def upsert_notebook(name: str, nb: dict, description: str) -> str:
    payload = base64.b64encode(json.dumps(nb, ensure_ascii=False).encode("utf-8")).decode()
    body = {
        "displayName": name,
        "description": description,
        "definition": {
            "format": "ipynb",
            "parts": [{"path": "notebook-content.py", "payload": payload, "payloadType": "InlineBase64"}],
        },
    }

    items = requests.get(f"{API}/workspaces/{WS}/items", headers=headers(), timeout=120).json()
    existing = next((i for i in items.get("value", [])
                     if i["displayName"] == name and i["type"] == "Notebook"), None)

    if existing:
        r = requests.post(
            f"{API}/workspaces/{WS}/notebooks/{existing['id']}/updateDefinition",
            headers=headers(), json={"definition": body["definition"]}, timeout=300)
        _wait(r)
        print(f"   zaktualizowano {name}")
        return existing["id"]

    r = requests.post(f"{API}/workspaces/{WS}/notebooks", headers=headers(), json=body, timeout=300)
    item = _wait(r)
    if item is None:
        items = requests.get(f"{API}/workspaces/{WS}/items", headers=headers(), timeout=120).json()
        item = next(i for i in items["value"] if i["displayName"] == name and i["type"] == "Notebook")
    print(f"   utworzono {name}: {item['id']}")
    return item["id"]


def _wait(resp: requests.Response):
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
            raise SystemExit(f"Operacja {op}: {st['status']} {st.get('error')}")
        return None
    raise SystemExit(f"HTTP {resp.status_code}: {resp.text[:800]}")


def run_notebook(nb_id: str, name: str, timeout_s: int = 2400) -> str:
    r = requests.post(
        f"{API}/workspaces/{WS}/items/{nb_id}/jobs/instances?jobType=RunNotebook",
        headers=headers(), json={"executionData": {}}, timeout=120)
    if r.status_code not in (200, 202):
        raise SystemExit(f"Uruchomienie {name}: HTTP {r.status_code} {r.text[:500]}")
    loc = r.headers["Location"]
    print(f"   {name}: uruchomiony...", flush=True)

    started = time.time()
    while time.time() - started < timeout_s:
        time.sleep(20)
        st = requests.get(loc, headers=headers(), timeout=120).json()
        status = st.get("status")
        if status in ("Completed", "Failed", "Cancelled", "Deduped"):
            mins = (time.time() - started) / 60
            print(f"   {name}: {status} ({mins:.1f} min)")
            if status != "Completed":
                print(json.dumps(st.get("failureReason"), ensure_ascii=False, indent=2)[:1500])
            return status
    return "Timeout"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="uruchom notatnik ingestu po wdrozeniu")
    ap.add_argument("--run-all", action="store_true", help="uruchom rowniez notatniki analityczne 01-04")
    args = ap.parse_args()

    print("== Notatnik ingestu")
    ingest_id = upsert_notebook(
        "00_ingest_to_delta", build_notebook(INGEST_CELLS, "00_ingest_to_delta"),
        "Ladowanie CSV z Files/raw do tabel Delta; kody TERYT wymuszone jako string.")

    print("== Notatniki analityczne")
    analytic = []
    for src in sorted((ROOT / "notebooks").glob("0*.py")):
        name = src.stem
        nb = build_notebook(convert_local_notebook(src), name)
        analytic.append((name, upsert_notebook(name, nb, f"Analiza kaskad IK — {name}.")))

    if args.run or args.run_all:
        print("== Uruchomienie ingestu")
        if run_notebook(ingest_id, "00_ingest_to_delta") != "Completed":
            sys.exit(1)

    if args.run_all:
        print("== Uruchomienie notatnikow analitycznych")
        for name, nb_id in analytic:
            if run_notebook(nb_id, name) != "Completed":
                sys.exit(1)

    print("\nGotowe.")


if __name__ == "__main__":
    main()
