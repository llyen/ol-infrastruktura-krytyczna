# Automatyczne wdrożenie na Microsoft Fabric

Skrypty w tym katalogu odtwarzają całe środowisko demonstracyjne bez klikania w portalu.
Korzystają z publicznego REST API Fabric, OneLake DFS, API Kusto i Power BI — Fabric CLI (`fab`)
nie jest wymagane.

## Wymagania

| Wymaganie | Szczegóły |
| --- | --- |
| Azure CLI | `az login` na koncie z dostępem do dzierżawy Fabric |
| Pojemność Fabric | F2+ (referencyjne wdrożenie: `fcdemo`, F8) |
| Uprawnienia | tworzenie workspace'ów, przypisanie pojemności, rola Admin w utworzonym workspace |
| Python | 3.11+, `pip install -r ..\requirements.txt` |
| Dane | `python ..\generate_datasets.py` — ok. 190 MB w `..\datasets\` |

Skrypty pobierają tokeny przez `az account get-access-token` dla czterech zasobów:
`https://api.fabric.microsoft.com`, `https://storage.azure.com`, `https://kusto.kusto.windows.net`
oraz `https://analysis.windows.net/powerbi/api`.

Stan wdrożenia (identyfikatory workspace'u, lakehouse'u, bazy KQL, modelu) zapisywany jest
w `..\.fabric\deployment.json`. Każdy kolejny skrypt czyta ten plik, więc kolejność ma znaczenie.

## Kolejność uruchamiania

```powershell
cd C:\repos\OchronaLudnosci\ol-infrastruktura-krytyczna
$env:PYTHONIOENCODING = 'utf-8'

pwsh   deploy\01_create_workspace.ps1     # workspace + Lakehouse + Eventhouse
pwsh   deploy\02_upload_data.ps1          # CSV/JSONL -> OneLake Files/raw
python deploy\03_deploy_notebooks.py --run  # notatniki + uruchomienie ingestu do Delta
python deploy\04_deploy_kql.py           # baza KQL: tabele, polityki, funkcje, queryset
python deploy\05_load_eventhouse.py      # telemetria (186 MB) -> Eventhouse
python deploy\06_semantic_model.py       # model semantyczny DirectLake + odświeżenie
python deploy\07_verify_model.py         # 13 kontroli DAX wobec wartości referencyjnych
python deploy\08_verify_kql.py           # 16 zapytań Real-Time (kafle + detekcja kaskad)
python deploy\09_realtime_dashboard.py   # Real-Time Dashboard (2 strony, 11 kafli, 3 parametry)
```

Czas całości: ok. 25 minut, z czego notatnik ingestu ok. 6 minut, a wgranie telemetrii ok. 3 minuty.

## Co robi każdy skrypt

| Skrypt | Działanie |
| --- | --- |
| `01_create_workspace.ps1` | Tworzy workspace `OL-ZK-Demo-IK` na wskazanej pojemności, Lakehouse `lh_ci_graph`, Eventhouse `eh_ci_realtime`. Zapisuje `.fabric\deployment.json`. |
| `02_upload_data.ps1` | Wysyła pliki do OneLake pod `Files/raw/{dimensions,derived,streams}`. Duże pliki blokami po 8 MB. |
| `03_deploy_notebooks.py` | Konwertuje `notebooks\*.py` (separator `# CELL`) na `.ipynb`, podmienia ścieżki na `/lakehouse/default/Files/...` i wdraża. Dodaje notatnik ingestu CSV→Delta. `--run` uruchamia ingest, `--run-all` wszystkie. |
| `04_deploy_kql.py` | Tworzy bazę KQL `CriticalInfrastructure`, wykonuje `01_create_tables.kql`, `02_update_policies.kql` i `04_cascade_detection.kql` przez `.execute database script`, a `03_dashboard_queries.kql` publikuje jako KQL Queryset. |
| `05_load_eventhouse.py` | Wgrywa telemetrię do OneLake i zaciąga ją do Eventhouse poleceniem `.ingest` z mapowaniem `multijson`. |
| `06_semantic_model.py` | Generuje TMSL modelu DirectLake (19 tabel, 16 relacji, 41 miar) na podstawie schematów Delta wyeksportowanych przez notatnik ingestu, wdraża go i wymusza `refresh` (bez tego DAX zwraca „Failed to resolve name"). |
| `07_verify_model.py` | Wykonuje zapytania DAX przez `executeQueries` i porównuje wyniki z wartościami referencyjnymi z `datasets\derived\*.json`. |
| `08_verify_kql.py` | Test dymny warstwy Real-Time: podstawia parametry dashboardu i wywołuje wszystkie funkcje detekcji kaskad. |
| `09_realtime_dashboard.py` | Buduje Real-Time Dashboard z pliku `kql\03_dashboard_queries.kql` (nagłówek `// --- KAFEL n:` wyznacza kafel). Przed wdrożeniem sprawdza unikalność UUID, referencje zapytań i to, czy kolumny wskazane w wizualizacjach istnieją w wyniku zapytania. |

## Zegar scenariusza

Dane demonstracyjne datowane są na wrzesień 2026, więc `now()` i `ago()` nie zwróciłyby niczego.
Baza KQL udostępnia trzy funkcje pomocnicze, do których kotwiczą się wszystkie zapytania:

| Funkcja | Znaczenie |
| --- | --- |
| `ScenarioNow()` | najnowsze zdarzenie w strumieniu — na żywo równa się czasowi bieżącemu |
| `ScenarioPeak()` | godzina szczytu kryzysu (najwięcej obiektów w awarii) — domyślna kotwica demo |
| `CiNodeAt(at)` | stan każdego obiektu IK na zadany moment; `CiNodeCurrent` pokazuje wyłącznie koniec okna |

Kafle dashboardu używają `CiNodeAt(_endTime)`, dzięki czemu suwak czasu przewija przebieg kaskady.

## Elementy wymagające konfiguracji ręcznej

Fabric nie udostępnia jeszcze stabilnego API dla poniższych elementów — instrukcje w
[`../SETUP_FABRIC.md`](../SETUP_FABRIC.md), kroki 4 i 8–10:

- Eventstream `es_ci_telemetry` (w wdrożeniu skryptowym telemetria ładowana jest wsadowo)
- Raport Power BI (6 stron, `report\REPORT_SPEC.md`)
- Data Activator (7 reguł, `activator\RULES.md`)
- Data Agent i Fabric App

## Format definicji Real-Time Dashboard

Skrypt `09` generuje plik `RealTimeDashboard.json` w wersji `schema_version: "52"`. Kilka pułapek,
które kosztowały najwięcej czasu:

- Każdy `id` (kafla, zapytania, strony, parametru, źródła danych) musi być **UUID wg RFC 4122** —
  czytelne identyfikatory z myślnikami są odrzucane przy ładowaniu.
- Każdy `queryId` może być użyty **dokładnie raz** — łącznie w `tiles`, `baseQueries`
  i `parameters[].dataSource.queryRef`.
- Typy wizualizacji to `bar`, `column`, `timechart`, `map`, `multistat`, `table` — nie `barchart`
  ani `columnchart`.
- Nazwy kolumn w wizualizacjach mają prefiksy: `map__latitudeColumn`, `map__longitudeColumn`,
  `multiStat__labelColumn`, `multiStat__valueColumn`.
- Źródło danych Fabric to `kind: "kusto-trident"`, `scopeId: "kusto-trident"` plus pole `workspace`.
- Fabric **nie waliduje definicji przy zapisie** — błąd ujawnia się dopiero, gdy ktoś otworzy
  dashboard. Dlatego skrypt sam sprawdza referencje i istnienie kolumn przed wysłaniem.

## Ponowne uruchomienie

Skrypty są idempotentne: istniejące elementy są wykrywane po nazwie i pomijane lub aktualizowane
(`.create-or-alter` w KQL, nadpisanie definicji notatnika i modelu). Aby wdrożyć do innego
workspace'u, usuń `..\.fabric\deployment.json` i zacznij od skryptu `01`.
