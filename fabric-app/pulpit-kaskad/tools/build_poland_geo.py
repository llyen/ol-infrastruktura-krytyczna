"""
Generuje modul TypeScript z granicami wojewodztw, gotowy do wstawienia w mape.

Zrodlo: https://github.com/ppatrzyk/polska-geojson (dane GUS, licencja MIT).

Granice sa **wstepnie rzutowane** na te sama siatke, ktorej uzywa funkcja
`project` w `src/data/model.ts` (rzut rownoprostokatny na kwadrat 0..100).
Dzieki temu warstwa granic i warstwa punktow zawsze sie pokrywaja, a
przegladarka nie musi liczyc rzutu przy kazdej klatce przesuwania mapy.

Uruchomienie:
    python tools\\build_poland_geo.py
"""

from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path

SOURCE = (
    "https://raw.githubusercontent.com/ppatrzyk/polska-geojson/master/"
    "wojewodztwa/wojewodztwa-medium.geojson"
)

# Musi byc identyczne z BOUNDS w src/data/model.ts.
BOUNDS = {"minLat": 49.0, "maxLat": 54.9, "minLon": 14.1, "maxLon": 24.2}

# Tolerancja upraszczania w jednostkach docelowych (0..100).
# 0.06 daje ok. 0,4 km na krancach - ponizej grubosci kreski przy pelnym oddaleniu,
# a po przyblizeniu 8x linia brzegowa nadal jest gladka.
TOLERANCE = 0.06

# Pierscienie mniejsze niz to (w jednostkach kwadratowych) sa pomijane -
# to wysepki na Zalewie Szczecinskim, nieczytelne w tej skali.
MIN_RING_AREA = 0.02

OUT = Path(__file__).resolve().parent.parent / "src" / "data" / "poland.ts"

# Te same granice w postaci nieprzerzutowanej (dlugosc, szerokosc) - uzywa ich
# `build_scene.py` do sprawdzenia, czy punkt lezy w swoim wojewodztwie.
OUT_RINGS = Path(__file__).resolve().parent / "poland_rings.json"


def project(lon: float, lat: float) -> tuple[float, float]:
    x = (lon - BOUNDS["minLon"]) / (BOUNDS["maxLon"] - BOUNDS["minLon"]) * 100.0
    y = 100.0 - (lat - BOUNDS["minLat"]) / (BOUNDS["maxLat"] - BOUNDS["minLat"]) * 100.0
    return x, y


def unproject(x: float, y: float) -> tuple[float, float]:
    """Odwrotnosc `project` - rzut jest afiniczny, wiec odwrocenie jest dokladne."""
    lon = BOUNDS["minLon"] + x / 100.0 * (BOUNDS["maxLon"] - BOUNDS["minLon"])
    lat = BOUNDS["minLat"] + (100.0 - y) / 100.0 * (BOUNDS["maxLat"] - BOUNDS["minLat"])
    return lon, lat


def perpendicular_distance(pt, start, end) -> float:
    if start == end:
        return math.dist(pt, start)
    x0, y0 = pt
    x1, y1 = start
    x2, y2 = end
    num = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    den = math.hypot(y2 - y1, x2 - x1)
    return num / den


def simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker, iteracyjnie - rekurencja przy 8 tys. wierzcholkow
    potrafi przekroczyc limit stosu."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        worst, worst_i = 0.0, first
        for i in range(first + 1, last):
            d = perpendicular_distance(points[i], points[first], points[last])
            if d > worst:
                worst, worst_i = d, i
        if worst > tol:
            keep[worst_i] = True
            stack.append((first, worst_i))
            stack.append((worst_i, last))
    return [p for p, k in zip(points, keep) if k]


def ring_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def rings_of(geometry: dict) -> list[list]:
    kind = geometry["type"]
    if kind == "Polygon":
        return geometry["coordinates"]
    if kind == "MultiPolygon":
        return [ring for polygon in geometry["coordinates"] for ring in polygon]
    raise ValueError(f"nieobslugiwana geometria: {kind}")


def centroid(rings: list[list[tuple[float, float]]]) -> tuple[float, float]:
    """Srodek najwiekszego pierscienia - punkt zaczepienia etykiety."""
    biggest = max(rings, key=ring_area)
    cx = sum(p[0] for p in biggest) / len(biggest)
    cy = sum(p[1] for p in biggest) / len(biggest)
    return cx, cy


def to_path(rings: list[list[tuple[float, float]]]) -> str:
    parts = []
    for ring in rings:
        head = f"M{ring[0][0]:.2f} {ring[0][1]:.2f}"
        tail = "".join(f"L{x:.2f} {y:.2f}" for x, y in ring[1:])
        parts.append(head + tail + "Z")
    return "".join(parts)


def main() -> None:
    print(f"pobieram {SOURCE}")
    with urllib.request.urlopen(SOURCE, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))

    raw_points = 0
    kept_points = 0
    regions = []

    for feature in data["features"]:
        name = feature["properties"].get("nazwa") or feature["properties"].get("name")
        if not name:
            raise ValueError(f"brak nazwy w cechach: {feature['properties']}")

        projected_rings = []
        for ring in rings_of(feature["geometry"]):
            pts = [project(lon, lat) for lon, lat in ring]
            raw_points += len(pts)
            if ring_area(pts) < MIN_RING_AREA:
                continue
            simplified = simplify(pts, TOLERANCE)
            if len(simplified) < 4:
                continue
            kept_points += len(simplified)
            projected_rings.append(simplified)

        if not projected_rings:
            continue

        # Zaokraglamy raz, przed zapisem obu artefaktow. Kontur w pliku .ts ma
        # dwa miejsca po przecinku, wiec granice uzywane do sprawdzania punktow
        # musza wynikac dokladnie z tych samych liczb - inaczej punkt lezacy na
        # kresce raz wypada w srodku, a raz na zewnatrz.
        rounded_rings = [[(round(x, 2), round(y, 2)) for x, y in ring] for ring in projected_rings]

        cx, cy = centroid(rounded_rings)
        regions.append(
            {
                "name": name.lower(),
                "path": to_path(rounded_rings),
                "cx": round(cx, 2),
                "cy": round(cy, 2),
                "rings": [
                    [[round(v, 5) for v in unproject(x, y)] for x, y in ring]
                    for ring in rounded_rings
                ],
            }
        )

    regions.sort(key=lambda r: r["name"])

    lines = [
        "/**",
        " * Granice wojewodztw wstepnie rzutowane na siatke 0..100 uzywana przez",
        " * funkcje `project` w `model.ts`. Plik jest generowany - nie edytowac recznie.",
        " *",
        " * Zrodlo: https://github.com/ppatrzyk/polska-geojson (dane GUS, licencja MIT).",
        " * Generator: tools/build_poland_geo.py",
        " */",
        "",
        "export interface Region {",
        "  /** Nazwa wojewodztwa malymi literami. */",
        "  name: string;",
        "  /** Kontur w jednostkach 0..100, gotowy dla atrybutu `d` elementu <path>. */",
        "  path: string;",
        "  /** Punkt zaczepienia etykiety. */",
        "  cx: number;",
        "  cy: number;",
        "}",
        "",
        "export const REGIONS: Region[] = [",
    ]
    for region in regions:
        lines.append("  {")
        lines.append(f"    name: {json.dumps(region['name'], ensure_ascii=False)},")
        lines.append(f"    cx: {region['cx']},")
        lines.append(f"    cy: {region['cy']},")
        lines.append(f"    path: '{region['path']}',")
        lines.append("  },")
    lines.append("];")
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")

    OUT_RINGS.write_text(
        json.dumps(
            {r["name"]: r["rings"] for r in regions}, ensure_ascii=False, separators=(",", ":")
        ),
        encoding="utf-8",
    )

    size_kb = OUT.stat().st_size / 1024
    print(f"wojewodztw:      {len(regions)}")
    print(f"wierzcholkow:    {raw_points} -> {kept_points}")
    print(f"zapisano:        {OUT}  ({size_kb:.1f} kB)")
    print(f"zapisano:        {OUT_RINGS}  ({OUT_RINGS.stat().st_size / 1024:.1f} kB)")
    if len(regions) != 16:
        raise SystemExit(f"BLAD: oczekiwano 16 wojewodztw, jest {len(regions)}")


if __name__ == "__main__":
    main()
