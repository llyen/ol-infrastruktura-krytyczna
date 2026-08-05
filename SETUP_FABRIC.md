# Wdrożenie w Microsoft Fabric

Instrukcja krok po kroku. Cały przebieg zajmuje ok. 90 minut, z czego większość to czekanie na
przetworzenie notatników. Wymagana pojemność Fabric F2 lub wyższa (F4+ zalecane ze względu na
symulację 2106 przebiegów w notatniku 03).

> **Szybka ścieżka.** Kroki 0–6 są w całości zautomatyzowane skryptami w katalogu `deploy\`,
> podobnie jak Real-Time Dashboard i raport Power BI. Jeśli nie chcesz klikać w portalu,
> przejdź od razu do [`deploy/README.md`](deploy/README.md) i wróć tutaj do kroków 8–10
> (Data Activator, Data Agent, Fabric App), których Fabric nie udostępnia jeszcze
> przez publiczne API.

Referencyjne wdrożenie tego repozytorium:

| Element | Wartość |
| --- | --- |
| Workspace | `OL-ZK-Demo-IK` |
| Pojemność | `fcdemo` (F8) |
| Lakehouse | `lh_ci_graph` (30 tabel Delta) |
| Eventhouse / baza KQL | `eh_ci_realtime` / `CriticalInfrastructure` |
| Model semantyczny | `sm_ci_cascade` (DirectLake, 19 tabel, 41 miar) |
| Real-Time Dashboard | `Efekt domina — obraz operacyjny` (2 strony, 11 kafli) |
| Raport Power BI | `rpt_efekt_domina` (6 stron, 72 wizualizacje) |
| Eventstream | `es_ci_telemetry` (endpoint → 3 filtry → 3 tabele KQL) |
| Data Activator | `act_efekt_domina` (7 reguł R1–R7, akcja Teams) |
| Data Agent | `agent_infrastruktura_krytyczna` (3 źródła: Lakehouse, Eventhouse, model) |

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
| `kql\02_update_policies.kql` | funkcje `ParseCiNodeStatus` / `ParseCiOperatorReport` / `ParseHydroReading`, update policies, widoki materializowane `CiNodeCurrent` i `CiOutageHourly`, zegar scenariusza (`ScenarioNow`, `ScenarioPeak`, `CiNodeAt`), funkcje `FuelRunout`, `CriticalNodesDown`, `CascadeForecast`, `FloodPressure` |
| `kql\03_dashboard_queries.kql` | zapytania kafli Real-Time Dashboard |
| `kql\04_cascade_detection.kql` | detekcja kaskady, korelacja czasowa między systemami, wejścia dla Activatora |
| `activator\queries.kql` | funkcje `ActivatorR1Cascade`…`ActivatorR7Anomaly` — zapytania źródłowe 7 reguł alertowych |

3. Załaduj tabele referencyjne do Eventhouse — najprościej przez OneLake shortcut do
   `lh_ci_graph`, alternatywnie import `dim_ci_node.csv`, `fact_ci_dependency.csv` oraz
   (po kroku 5) `derived\cascade_centrality.csv`.

Kontrola: `CiNodeCurrent | count` po pierwszych danych; `CiNode | count` → 2106.

---

## Krok 4 — Eventstream

Krok jest zautomatyzowany:

```powershell
python deploy\12_eventstream.py          # topologia
python deploy\13_verify_eventstream.py   # test dymny end-to-end
```

Powstaje Eventstream **`es_ci_telemetry`**: custom endpoint → strumień
`stream_ci_telemetry` → trzy filtry po polu `stream` → trzy destynacje Eventhouse
w bazie `CriticalInfrastructure`:

| Wartość pola `stream` | Filtr | Tabela docelowa |
|---|---|---|
| `ci_node_status` | `filter_node_status` | `CiNodeStatus` |
| `ci_operator_reports` | `filter_operator_reports` | `CiOperatorReport` |
| `hydro_readings` | `filter_hydro_readings` | `HydroReading` |

Destynacje pracują w trybie `ProcessedIngestion`, który mapuje pola JSON na kolumny
po nazwach, więc kierują wprost do tabel typowanych — tabele `*Raw` i update policy
zostają jako ścieżka zapasowa dla ingestu wsadowego.

Connection string dla symulatora: `python deploy\12_eventstream.py --keys`.

Uruchom symulator:

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
   Mapa zależności • Wyłącz ten węzeł • Pojedyncze punkty awarii • Powódź wrzesień • Co warto wzmocnić • Gotowość SPO-10.
   Skrypt `deploy\10_report.py` generuje ten raport automatycznie w formacie PBIR i wdraża go
   przez REST API — ręczne budowanie w Power BI Desktop jest potrzebne tylko wtedy, gdy chcesz
   zmienić układ poza tym, co opisuje `TILE`/`PAGE_BUILDERS` w skrypcie.
5. Kafle stanu bieżącego podepnij w trybie DirectQuery do bazy KQL, resztę zostaw w imporcie.

---

## Krok 7 — Real-Time Dashboard

Utwórz dashboard **`Infrastruktura krytyczna — obraz operacyjny`** i dodaj kafle z zapytań
`kql\03_dashboard_queries.kql`. Ustaw autoodświeżanie na 30 sekund i domyślny zakres czasu na
ostatnie 24 godziny.

---

## Krok 8 — Data Activator

Skonfiguruj 7 reguł z `activator\RULES.md`. Krok jest zautomatyzowany:

```powershell
python deploy\14_activator.py            # kotwica: szczyt scenariusza
python deploy\15_verify_activator.py     # kontrola spójności 7 reguł
```

Powstaje Activator **`act_efekt_domina`**. Każda reguła ma własną funkcję KQL
(`activator\queries.kql`, funkcje `ActivatorR1Cascade`…`ActivatorR7Anomaly`), która
zwraca wiersz wyłącznie wtedy, gdy alert ma się odpalić. Activator uruchamia je co
5 minut i wysyła wiadomość Teams do odbiorcy podanego przez `--recipient`
(domyślnie: zalogowany użytkownik).

Na danych statycznych używaj domyślnej kotwicy `--anchor peak`; przy symulatorze
na żywo — `--anchor now`.

Zasada nadrzędna: **alert dotyczy kaskady, nie pojedynczej awarii.** Zanim uruchomisz reguły
produkcyjnie, przetestuj je na danych historycznych, żeby ocenić liczbę powiadomień.

---

## Krok 9 — Data Agent

Krok jest zautomatyzowany:

```powershell
python deploy\16_data_agent.py
```

Powstaje Data Agent **`agent_infrastruktura_krytyczna`** z instrukcją systemową pobraną
z `ai\DATA_AGENT.md` (sekcja „Instrukcja systemowa agenta") i trzema źródłami danych:

| Źródło | Zakres |
| --- | --- |
| Lakehouse `lh_ci_graph` | 14 tabel: graf zależności, symulacja kaskady, warianty hardeningu |
| Eventhouse `CriticalInfrastructure` | 5 tabel telemetrii stanu bieżącego |
| Model semantyczny `sm_ci_cascade` | 19 tabel z miarami DAX |

Skrypt sprawdza przed wysyłką, że każda wskazana tabela i funkcja istnieje, a po wdrożeniu
wykonuje odczyt zwrotny definicji — Fabric po cichu odrzuca pliki o nieoczekiwanej ścieżce.

Do zrobienia ręcznie w interfejsie:

1. **Opublikuj agenta** (przejście z wersji roboczej do produkcyjnej) — API tego nie udostępnia.
2. Przetestuj pytania kontrolne z `ai\DATA_AGENT.md`, w tym te, na które agent ma odmówić
   odpowiedzi: nie ujawnia dokładnych lokalizacji obiektów K1, nie przypisuje intencji
   sprawcy i nie formułuje decyzji.

Funkcje KQL (`CascadePath`, `CiNodeAt`, `ScenarioPeak`…) nie są podpięte jako elementy
źródła — backend Data Agenta odrzuca elementy typu `kusto.functions`. Ich sygnatury trafiają
do instrukcji źródła, więc agent i tak wie, że ma je wywoływać.

---

## Krok 10 — Fabric App

Zbuduj aplikację wg `fabric-app\APP_SPEC.md`. Jeśli korzystasz z generatora aplikacji, użyj
gotowego promptu z `fabric-app\RAYFIN_PROMPT.md`.

Aplikacja obsługuje dwa write-backi: meldunek operatora IK oraz zatwierdzenie pozycji planu
wzmocnień (z uzasadnieniem i datą — ślad audytowy).

Aplikacja jest już zbudowana i wdrożona — kod w `fabric-app\pulpit-kaskad`, adres i
identyfikatory w `DEPLOYMENT_STATUS.md`. Ponowne wdrożenie:

```powershell
.\deploy\ensure_capacity.ps1
cd fabric-app\pulpit-kaskad
npx rayfin up -y --workspace-id 8eed174a-6298-4867-929c-bc12e129cff7
```

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
