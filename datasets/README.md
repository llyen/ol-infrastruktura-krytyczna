# Zbiory danych

> ⚠️ **Wszystkie dane w tym katalogu są syntetyczne.** Powstają proceduralnie w
> `generate_datasets.py` (seed=42, wynik w pełni powtarzalny). Nie odzwierciedlają rzeczywistej
> infrastruktury krytycznej, jej lokalizacji, operatorów ani zależności. Nazwy operatorów są
> fikcyjne i oznaczone skrótem „(fikc.)". Nie wykorzystywać do żadnych celów operacyjnych.

Pełny opis kolumn, typów i ziarna: [`../DATA_MODEL.md`](../DATA_MODEL.md).

## Odtworzenie

```powershell
python generate_datasets.py
```

Kilka minut, ok. 196 MB. Zawartość katalogu jest w całości odtwarzalna — można ją bezpiecznie
skasować.

## Wymiary i fakty (CSV)

| Plik | Wiersze | Rozmiar | Ziarno |
|---|---:|---:|---|
| `dim_voivodeship.csv` | 16 | 1 KB | województwo |
| `dim_powiat.csv` | 380 | 22 KB | powiat |
| `dim_gmina.csv` | 2 477 | 206 KB | gmina |
| `dim_river_gauge.csv` | 120 | 6 KB | wodowskaz |
| `dim_hazard.csv` | 20 | 1 KB | zagrożenie Z01–Z20 |
| `dim_ci_system.csv` | 11 | 1 KB | system IK |
| `dim_ci_node.csv` | 2 106 | 489 KB | obiekt IK |
| `fact_ci_dependency.csv` | 6 552 | 500 KB | zależność dostawca → odbiorca |
| `fact_node_hazard_exposure.csv` | 8 614 | 354 KB | obiekt × zagrożenie |
| `fact_spo10_cooperation.csv` | 1 463 | 111 KB | obiekt objęty trybem SPO-10 |

## Strumienie zdarzeń (JSONL)

| Plik | Zdarzenia | Rozmiar | Ziarno |
|---|---:|---:|---|
| `ci_node_status.jsonl` | 659 178 | **186 MB** | obiekt × 15 min |
| `hydro_readings.jsonl` | 37 560 | 7,8 MB | wodowskaz × interwał |
| `ci_operator_reports.jsonl` | 889 | 302 KB | meldunek operatora IK |

> `ci_node_status.jsonl` jest wyłączony z repozytorium przez `.gitignore` ze względu na rozmiar.
> Odtwarza go generator.

## Metryki przebiegu

`generation_summary.json` — liczby wierszy, parametry, seed i zakres czasu. Służy do
weryfikacji, czy dane wygenerowały się identycznie (patrz lista kontrolna w `../SETUP_FABRIC.md`).

## Wyniki analiz — `derived/`

Katalog produkowany przez notatniki, nie przez generator. Zawiera 22 pliki: oś czasu kaskady,
drzewo skutków, czas do utraty usługi per gmina, ranking centralności kaskadowej, listę
pojedynczych punktów awarii oraz porównanie wariantów wzmocnienia. Opis w
[`../DATA_MODEL.md`](../DATA_MODEL.md), sekcja „Tabele wynikowe".

Odtworzenie:

```powershell
python notebooks\01_load_graph.py
python notebooks\02_cascade_simulation.py
python notebooks\03_centrality_spof.py
python notebooks\04_hardening_whatif.py
```

## Zakres czasu

Wszystkie strumienie obejmują okno `2026-09-09 00:00+02:00` … `2026-09-22 00:00+02:00`.
D0 scenariusza (przekroczenie stanów alarmowych) to `2026-09-12 06:00+02:00`. Godziny w wynikach
symulacji liczone są od D0.
