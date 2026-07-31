# Wdrożenie w Microsoft Fabric

Instrukcja krok po kroku. Cały przebieg zajmuje ok. 90 minut, z czego większość to czekanie na
przetworzenie notatników. Wymagana pojemność Fabric F2 lub wyższa (F4+ zalecane ze względu na
symulację 2106 przebiegów w notatniku 03).

> **Szybka ścieżka.** Kroki 0–6 są w całości zautomatyzowane skryptami w katalogu `deploy\`.
> Jeśli nie chcesz klikać w portalu, przejdź od razu do [`deploy/README.md`](deploy/README.md)
> i wróć tutaj do kroków 7–10 (Real-Time Dashboard, Data Activator, Data Agent, Fabric App),
> których Fabric nie udostępnia jeszcze przez publiczne API.

Referencyjne wdrożenie tego repozytorium:

| Element | Wartość |
| --- | --- |
| Workspace | `OL-ZK-Demo-IK` |
| Pojemność | `fcdemo` (F8) |
| Lakehouse | `lh_ci_graph` (30 tabel Delta) |
| Eventhouse / baza KQL | `eh_ci_realtime` / `CriticalInfrastructure` |
| Model semantyczny | `sm_ci_cascade` (DirectLake, 19 tabel, 41 miar) |

Identyfikatory zapisane są w `.fabric\deployment.json` po pierwszym uruchomieniu skryptów.

---

## Krok 0 — Przygotowanie danych lokalnie

```powershell
cd C:\repos\OchronaLudnosci\ol-infrastruktura-krytyczna
pip install -r requirements.txt
python generate_datasets.py
```

Generator jest deterministyczny (seed=42) — ten sam wynik na każdej maszynie. Powstaje ok. 190 MB
w katalogu `datasets\`, głównie plik `ci_node_status.jsonl`.

Kontrola: `datasets\generation_summary.json` powinien wykazać 2106 obiektów, 6552 zależności
i 659 178 zdarzeń telemetrii.

---

## Krok 1 — Workspace

1. Utwórz workspace **`OL — Infrastruktura Krytyczna`**.
2. Przypisz pojemność Fabric.
3. Ustaw domyślną etykietę wrażliwości (w realnym wdrożeniu graf zależności IK wymaga
   klasyfikacji — patrz `ARCHITECTURE.md`).

---

## Krok 2 — Lakehouse

1. Utwórz Lakehouse **`lh_ci_graph`**.
2. Wgraj do `Files/raw/` zawartość katalogu `datasets\` (bez podkatalogu `derived`).
3. Załaduj pliki CSV do tabel Delta (`Load to Tables`), zachowując nazwy:
   `dim_voivodeship`, `dim_powiat`, `dim_gmina`, `dim_hazard`, `dim_river_gauge`,
   `dim_ci_system`, `dim_ci_node`, `fact_ci_dependency`, `fact_node_hazard_exposure`,
   `fact_spo10_cooperation`.

> **Uwaga:** kody TERYT muszą zostać typu `string`. Autodetekcja typów potrafi zamienić
> `voivodeship_code` na liczbę i zgubić wiodące zero — dolnośląskie `02` stanie się `2` i relacje
> przestaną działać. Sprawdź to przed dalszymi krokami.

---

## Krok 3 — Eventhouse i baza KQL

1. Utwórz Eventhouse **`eh_ci_realtime`**, w nim bazę **`CriticalInfrastructure`**.
2. Uruchom skrypty w kolejności, każdy w całości:

| Plik | Co tworzy |
|---|---|
| `kql\01_create_tables.kql` | tabele `CiNodeStatus`, `CiOperatorReport`, `HydroReading` (+ bufory `*Raw`), tabele referencyjne `CiNode`, `CiDependency`, `CascadeCentrality`, mapowania JSON, retencja 90 dni |
| `kql\02_update_policies.kql` | funkcje `ParseCiNodeStatus` / `ParseCiOperatorReport`, update policies, widoki materializowane `CiNodeCurrent` i `CiOutageHourly`, zegar scenariusza (`ScenarioNow`, `ScenarioPeak`, `CiNodeAt`), funkcje `FuelRunout`, `CriticalNodesDown`, `CascadeForecast`, `FloodPressure` |
| `kql\03_dashboard_queries.kql` | zapytania kafli Real-Time Dashboard |
| `kql\04_cascade_detection.kql` | detekcja kaskady, korelacja czasowa między systemami, wejścia dla Activatora |

3. Załaduj tabele referencyjne do Eventhouse — najprościej przez OneLake shortcut do
   `lh_ci_graph`, alternatywnie import `dim_ci_node.csv`, `fact_ci_dependency.csv` oraz
   (po kroku 5) `derived\cascade_centrality.csv`.

Kontrola: `CiNodeCurrent | count` po pierwszych danych; `CiNode | count` → 2106.

---

## Krok 4 — Eventstream

1. Utwórz Eventstream **`es_ci_telemetry`**.
2. Źródło: **Custom endpoint / Event Hub**. Skopiuj connection string.
3. Trzy destynacje do bazy `CriticalInfrastructure`:

| Strumień | Tabela docelowa | Mapowanie |
|---|---|---|
| `ci_node_status` | `CiNodeStatusRaw` | `CiNodeStatusMapping` |
| `ci_operator_reports` | `CiOperatorReportRaw` | `CiOperatorReportMapping` |
| `hydro_readings` | `HydroReadingRaw` | `HydroReadingMapping` |

Update policy przenosi dane z tabel `*Raw` do tabel docelowych automatycznie.

4. Uruchom symulator:

```powershell
$env:EVENTHUB_CONNECTION_STR = "<connection string>"
python simulate_realtime.py --speed 60
```

`--speed 60` oznacza, że godzina scenariusza trwa minutę. Dla demo na żywo warto zawęzić okno:

```powershell
python simulate_realtime.py --from 2026-09-12T06:00+02:00 --to 2026-09-13T00:00+02:00 --speed 120
```

Przed prezentacją sprawdź przebieg bez wysyłki: `python simulate_realtime.py --dry-run --limit 5`.

---

## Krok 5 — Notatniki

Zaimportuj pliki z `notebooks\` jako notatniki Fabric i podłącz `lh_ci_graph` jako domyślny
Lakehouse. Plik `cascade_engine.py` wgraj do `Files/lib/` i dodaj do ścieżki albo wklej jako
pierwszą komórkę notatnika 02.

Uruchom w kolejności:

| Notatnik | Czas | Produkuje |
|---|---|---|
| `01_load_graph.py` | < 1 min | `graph_nodes`, `graph_edges`, `system_summary`, `dependency_matrix`, `spo10_gaps` |
| `02_cascade_simulation.py` | ok. 1 min | `cascade_flood_timeline`, `cascade_waves`, `cascade_hourly_profile`, `cascade_single_node_timeline`, `cascade_effect_tree`, `cascade_gmina_time_to_effect` |
| `03_centrality_spof.py` | kilka minut | `cascade_centrality`, `cascade_top100`, `single_points_of_failure`, `cascade_by_voivodeship`, `cascade_by_system` |
| `04_hardening_whatif.py` | ok. 2 min | `whatif_variants`, `whatif_marginal_value` |

Wyniki zapisz jako tabele Delta w `lh_ci_graph`.

Kontrola poprawności — porównaj z wartościami referencyjnymi:

- `cascade_summary.json`: 777 obiektów łącznie, 545 wtórnych, wzmocnienie 3,35, max fala 7.
- `spof_summary.json`: 217 SPOF, 29 w kategorii „krytyczny".
- `whatif_summary.json`: wariant A −24,0%, wariant B −4,4%, wariant C −27,3%.

Rozbieżność oznacza, że dane zostały wygenerowane innym seedem albo zmieniono parametry silnika.

Zaplanuj notatniki 01 i 03 na cykl dobowy, 02 i 04 uruchamiaj na żądanie.

---

## Krok 6 — Model semantyczny i raport

1. Utwórz model semantyczny na `lh_ci_graph` zgodnie z `semantic-model\MODEL.md`.
2. Zbuduj relacje — pamiętaj o **dwóch relacjach** między `dim_ci_node` a `fact_ci_dependency`:
   aktywnej po `source_node_id` i **nieaktywnej** po `target_node_id`.
3. Dodaj miary DAX z `semantic-model\MEASURES.md`.
4. Zbuduj raport wg `report\REPORT_SPEC.md` — 6 stron:
   Przegląd • Kaskada powodziowa • Symulacja awarii • Punkty krytyczne • Warianty wzmocnienia • Governance SPO-10.
5. Kafle stanu bieżącego podepnij w trybie DirectQuery do bazy KQL, resztę zostaw w imporcie.

---

## Krok 7 — Real-Time Dashboard

Utwórz dashboard **`Infrastruktura krytyczna — obraz operacyjny`** i dodaj kafle z zapytań
`kql\03_dashboard_queries.kql`. Ustaw autoodświeżanie na 30 sekund i domyślny zakres czasu na
ostatnie 24 godziny.

---

## Krok 8 — Data Activator

Skonfiguruj 7 reguł z `activator\RULES.md`. Reguły opierają się na funkcjach z kroku 3
(`CriticalNodesDown`, `FuelRunout`, `CascadeForecast`) oraz zapytaniach z `04_cascade_detection.kql`.

Zasada nadrzędna: **alert dotyczy kaskady, nie pojedynczej awarii.** Zanim uruchomisz reguły
produkcyjnie, przetestuj je na danych historycznych, żeby ocenić liczbę powiadomień.

---

## Krok 9 — Data Agent

Utwórz Data Agent nad `lh_ci_graph` i bazą `CriticalInfrastructure`. Wklej instrukcję
z `ai\DATA_AGENT.md`, w tym **sekcję ograniczeń** — agent nie ujawnia dokładnych lokalizacji
obiektów K1, nie przypisuje intencji sprawcy i nie formułuje decyzji.

Przetestuj pytania kontrolne z tego pliku, w tym te, na które agent ma odmówić odpowiedzi.

---

## Krok 10 — Fabric App

Zbuduj aplikację wg `fabric-app\APP_SPEC.md`. Jeśli korzystasz z generatora aplikacji, użyj
gotowego promptu z `fabric-app\RAYFIN_PROMPT.md`.

Aplikacja obsługuje dwa write-backi: meldunek operatora IK oraz zatwierdzenie pozycji planu
wzmocnień (z uzasadnieniem i datą — ślad audytowy).

---

## Lista kontrolna przed demonstracją

- [ ] `generation_summary.json` zgodny z wartościami referencyjnymi
- [ ] Kody TERYT w Lakehouse są tekstem, `02` nie zamieniło się w `2`
- [ ] `CiNode | count` = 2106, `CiDependency | count` = 6552
- [ ] `CiNodeCurrent` zwraca dane i odpowiada w sekundach
- [ ] Symulator przetestowany w trybie `--dry-run`
- [ ] Wszystkie 4 notatniki wykonane, liczby zgodne z `*_summary.json`
- [ ] Relacja nieaktywna `target_node_id` istnieje i miary „od kogo zależę" działają
- [ ] Raport otwiera się w mniej niż 5 sekund na każdej z 6 stron
- [ ] Obiekt demonstracyjny `IK-01-00026` daje 538 453 osób i wodę po 0,9 h
- [ ] Magazyn paliw jest widoczny w pierwszej trójce rankingu SPOF
- [ ] Reguły Activatora przetestowane, powiadomienie dociera do Teams
- [ ] Data Agent odmawia odpowiedzi na pytanie o lokalizację obiektu K1
- [ ] Aplikacja zapisuje meldunek i zapis pojawia się w Lakehouse
- [ ] Slajd otwierający i zamykający zawiera informację o danych syntetycznych

---

## Sprzątanie

Usunięcie workspace kasuje wszystkie artefakty. Dane lokalne w `datasets\` można skasować —
odtwarza je `generate_datasets.py` w kilka minut, identycznie co do wiersza.
