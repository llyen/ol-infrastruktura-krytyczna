"""Kontrola modelu semantycznego: wykonanie DAX i porownanie z wartosciami referencyjnymi."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STATE = json.loads((ROOT / ".fabric" / "deployment.json").read_text(encoding="utf-8"))
WS, MODEL = STATE["workspaceId"], STATE["semanticModelId"]
PBI = "https://api.powerbi.com/v1.0/myorg"


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource",
         "https://analysis.windows.net/powerbi/api", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr)
    return out.stdout.strip()


def dax(query: str) -> list[dict]:
    r = requests.post(
        f"{PBI}/groups/{WS}/datasets/{MODEL}/executeQueries",
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
        json={"queries": [{"query": query}], "serializerSettings": {"includeNulls": True}},
        timeout=300)
    if r.status_code != 200:
        raise SystemExit(f"DAX HTTP {r.status_code}: {r.text[:2000]}")
    return r.json()["results"][0]["tables"][0]["rows"]


CHECKS = [
    ("Obiekty IK", 2106),
    ("Zaleznosci", 6552),
    ("Zaleznosci miedzywojewodzkie", 132),
    ("Obiekty w kaskadzie", 777),
    ("Skutki wtorne", 545),
    ("Zdarzenia inicjujace", 232),
    ("Najglebsza fala", 7),
    ("Wspolczynnik wzmocnienia", 3.35),
    ("Gminy dotkniete", 200),
    ("Ludnosc dotknieta", 2627373),
    ("Pojedyncze punkty awarii", 217),
    ("Najgorszy pojedynczy obiekt - ludnosc", 642162),
    ("Obiekty z jednym zrodlem zasilania", 1025),
]


def main() -> None:
    print("== Miary vs wartosci referencyjne")
    expr = ", ".join(f'"{n}", [{n}]' for n, _ in CHECKS)
    rows = dax(f"EVALUATE ROW({expr})")[0]
    bad = 0
    for name, expected in CHECKS:
        got = rows.get(f"[{name}]")
        got_i = round(got, 2) if isinstance(got, float) and expected != int(expected) else (
            round(got) if isinstance(got, (int, float)) else got)
        ok = got_i == expected
        bad += 0 if ok else 1
        print(f"   {'OK ' if ok else 'BLAD'} {name:<42} {got_i!s:>12}  (oczekiwano {expected})")

    print("\n== Wspolczynnik wzmocnienia i okno reakcji")
    r = dax('EVALUATE ROW("wzm", [Wspolczynnik wzmocnienia], '
            '"pierwszy", [Pierwszy skutek wtorny (h)], "eskalacja", [Poziom eskalacji])')[0]
    print(f"   wzmocnienie: {r['[wzm]']:.2f}   pierwszy skutek: {r['[pierwszy]']} h")
    print(f"   eskalacja:   {r['[eskalacja]']}")

    print("\n== Warianty what-if")
    rows = dax("EVALUATE SUMMARIZECOLUMNS(FactWhatIf[variant], "
               '"redukcja", [Redukcja skutkow wtornych %], "ludnosc", [Ludnosc uratowana])')
    for row in rows:
        red = row.get("[redukcja]")
        print(f"   {row['FactWhatIf[variant]']:<16} redukcja {red:>6.1f}%   "
              f"ludnosc uratowana {row.get('[ludnosc]') or 0:>10,.0f}")

    print("\n== Relacja nieaktywna (USERELATIONSHIP) — dostawcy wezla demo")
    rows = dax('EVALUATE ROW("dostawcy", CALCULATE([Dostawcy obiektu], '
               'DimNode[node_id] = "IK-01-00026"), "odbiorcy", '
               'CALCULATE([Zaleznosci], DimNode[node_id] = "IK-01-00026"))')[0]
    print(f"   IK-01-00026: dostawcow {rows['[dostawcy]']}, odbiorcow {rows['[odbiorcy]']}")

    print("\n== Top 3 pojedyncze punkty awarii")
    rows = dax("EVALUATE TOPN(3, SUMMARIZECOLUMNS(FactSpof[node_type], FactSpof[voivodeship_code], "
               '"ludnosc", MAX(FactSpof[cascade_population]), "obiekty", MAX(FactSpof[cascade_nodes])), '
               "[ludnosc], DESC)")
    for row in rows:
        print(f"   {row['FactSpof[node_type]']:<26} woj. {row['FactSpof[voivodeship_code]']}  "
              f"{row['[ludnosc]']:>8,} os.  {row['[obiekty]']:>4} obiektow")

    if bad:
        raise SystemExit(f"\n{bad} miar niezgodnych z wartosciami referencyjnymi.")
    print("\nModel semantyczny zweryfikowany.")


if __name__ == "__main__":
    main()
