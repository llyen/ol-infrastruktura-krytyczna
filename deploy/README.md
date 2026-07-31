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
python deploy\10_report.py               # raport Power BI PBIR (6 stron, 72 wizualizacje)
python deploy\11_verify_report.py        # kontrola odwolań raportu do modelu (77 pól)
python deploy\12_eventstream.py          # Eventstream: endpoint -> 3 filtry -> 3 tabele KQL
python deploy\13_verify_eventstream.py   # test dymny: 15 zdarzeń przez filtry do tabel
python deploy\14_activator.py            # Data Activator: 7 reguł alertowych (R1–R7)
python deploy\15_verify_activator.py     # kontrola spójności reguł i ich zapytań
python deploy\16_data_agent.py           # Data Agent: 3 źródła danych + instrukcja systemowa
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
| `10_report.py` | Generuje raport Power BI w formacie PBIR wprost z JSON-a (bez Power BI Desktop) wg `report\REPORT_SPEC.md` i wdraża go przez REST API. Przed wysyłką sprawdza nazwy wizualizacji, położenie na kanwie 1280×720 oraz każde odwołanie do tabeli, kolumny i miary. `--dry-run` = sama walidacja, `--save DIR` = zapis definicji na dysk, `--no-theme` = bez ciemnego motywu. |
| `11_verify_report.py` | Pobiera definicję raportu z Fabric, wyciąga wszystkie odwołania do modelu i sprawdza zapytaniem DAX, że każde z nich się rozwiązuje. |
| `12_eventstream.py` | Tworzy Eventstream `es_ci_telemetry`: custom endpoint → strumień → trzy filtry po polu `stream` → trzy destynacje Eventhouse. `--keys` wypisuje connection string dla `simulate_realtime.py`, `--dry-run` drukuje topologię. |
| `13_verify_eventstream.py` | Test dymny całej ścieżki: czeka na stan `Running`, wysyła po 5 zdarzeń z każdego strumienia, sprawdza, że trafiły do właściwej tabeli (i tylko do niej), po czym je usuwa. `--keep` zostawia dane. |
| `14_activator.py` | Buduje Data Activator `act_efekt_domina` z 7 regułami wg `activator\RULES.md`. Każda reguła to zapytanie KQL (`ActivatorR*`) + zdarzenie źródłowe + reguła z akcją Teams. Przed wdrożeniem wykonuje każde zapytanie i sprawdza, że kolumny użyte w treści alertu istnieją. `--anchor now\|peak`, `--recipient`, `--dry-run`. |
| `15_verify_activator.py` | Pobiera definicję Activatora z Fabric i sprawdza spójność grafu encji: reguła → zdarzenie → zapytanie, wykonalność zapytania, poprawność odwołań do kolumn w treści alertu, obecność odbiorcy i włączenie reguły. |
| `16_data_agent.py` | Tworzy Data Agenta `agent_infrastruktura_krytyczna` wg `ai\DATA_AGENT.md`: instrukcja systemowa + trzy źródła danych (Lakehouse 14 tabel, Eventhouse 5 tabel, model semantyczny 19 tabel). Przed wysyłką sprawdza, że każda wskazana tabela i funkcja naprawdę istnieje, a po wdrożeniu wykonuje odczyt zwrotny definicji. `--dry-run` drukuje pliki definicji. |

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
[`../SETUP_FABRIC.md`](../SETUP_FABRIC.md), krok 10:

- Fabric App (typ elementu `FabricApp`/`App` nie istnieje w API — zawsze ręcznie)
- publikacja Data Agenta z wersji roboczej do produkcyjnej (sama definicja wdraża się skryptem `16`)

## Format definicji Data Agenta

Definicja to zestaw plików pod `Files/Config`:

| Ścieżka | Zawartość |
| --- | --- |
| `Files/Config/data_agent.json` | tylko `$schema` (wersja `dataAgent/2.1.0`) |
| `Files/Config/draft/stage_config.json` | `aiInstructions` — instrukcja systemowa agenta |
| `Files/Config/draft/{typ}-{nazwa}/datasource.json` | jedno źródło danych z listą `elements` |

Pułapki ustalone doświadczalnie:

- **Nazwa folderu źródła jest narzucona**: typ z myślnikami zamiast podkreśleń, dywiz i
  `displayName` elementu, np. `lakehouse-tables-lh_ci_graph`, `kusto-CriticalInfrastructure`,
  `semantic-model-sm_ci_cascade`. Plik pod inną ścieżką jest **po cichu odrzucany** —
  `updateDefinition` zwraca 202 i kończy się sukcesem, ale przy odczycie zwrotnym źródła
  po prostu nie ma. Dlatego skrypt zawsze weryfikuje, że wróciły trzy źródła.
- `artifactId` dla Eventhouse to **ID bazy KQL**, nie samego Eventhouse'u.
- Elementy typu **`kusto.functions` są odrzucane przez backend** (`updateDefinition` kończy
  się `UnknownError`), mimo że schemat publiczny je dopuszcza — dotyczy to każdej nazwy,
  także nieistniejącej. Funkcje KQL opisujemy więc w `dataSourceInstructions`, a skrypt
  jedynie sprawdza, że istnieją w bazie.
- Schematy publiczne: `https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/{dataAgent/2.1.0,stageConfiguration/1.0.0,dataSource/1.0.0}/schema.json`.
- Instrukcja systemowa nie jest duplikowana w kodzie — skrypt wyciąga ją z cytatu blokowego
  w sekcji „Instrukcja systemowa agenta" pliku `ai\DATA_AGENT.md`.

## Format definicji Data Activatora (Reflex)

Definicja to `ReflexEntities.json` — **płaska lista encji** powiązanych przez
`uniqueIdentifier`; hierarchię wyrażają pola `parentContainer.targetUniqueIdentifier`
i `parentObject.targetUniqueIdentifier`. Typy encji użyte tutaj:

| `type` | Rola |
|---|---|
| `container-v1` | kontener grupujący (`payload.type: "kqlQueries"`) |
| `kqlSource-v1` | zapytanie KQL uruchamiane cyklicznie na bazie Eventhouse |
| `timeSeriesView-v1` | zdarzenia, obiekty, atrybuty i reguły — rozróżniane przez `payload.definition.type` |

Pułapki:

- **`payload.definition.instance` jest podwójnie serializowany** — to *string* z JSON-em,
  nie obiekt. Wewnątrz siedzi `{templateId, templateVersion, steps}`.
- `templateId` rozróżnia rodzaj encji: `SourceEvent` (zdarzenie źródłowe),
  `EventTrigger` (reguła na surowym zdarzeniu), `AttributeTrigger` (reguła na atrybucie
  modelu obiektowego), `IdentityPartAttribute`, `SplitEvent`, `BasicEventAttribute`.
- Ścieżka `EventTrigger` **nie wymaga modelu obiektowego** — wystarczy kontener,
  źródło, zdarzenie i reguła. To najkrótsza droga do alertu z zapytania KQL.
- Kroki reguły `EventTrigger`: `FieldsDefaultsStep` (wskazanie zdarzenia) →
  `EventDetectStep` (warunek) → `ActStep` (akcja).
- **Activator wymaga warunku liczbowego** i nie da się go pominąć. Dlatego każde
  zapytanie zwraca sztuczną kolumnę `alert = 1`, a warunek brzmi `alert > 0` —
  cała logika progu zostaje w KQL, gdzie jest wersjonowana i testowalna.
- `eventhouseItem.itemId` to **ID bazy KQL** (`itemType: "KustoDatabase"`), tak samo
  jak w destynacji Eventstreamu.
- Odbiorcy: akcja e-mail używa pola `sentTo`, akcja Teams — `recipients`.
- Tekst alertu to tablica fragmentów: zwykłe `{"type":"string","value":"…"}` przeplatane
  odwołaniami `{"kind":"EventFieldReference","arguments":[{"name":"fieldName",…}]}`.
- `definition.settings.shouldRun` włącza regułę po wdrożeniu.
- `uniqueIdentifier` to dowolne UUID-y, wewnętrzne dla pliku. Skrypt generuje je
  deterministycznie (`uuid5`), więc ponowne wdrożenie podmienia te same reguły
  zamiast tworzyć duplikaty.
- Endpointy: `POST /v1/workspaces/{ws}/reflexes` oraz `.../reflexes/{id}/updateDefinition`.

## Format definicji Eventstreamu

Definicja składa się z trzech części: `eventstream.json` (`sources`, `streams`,
`operators`, `destinations`, `compatibilityLevel: "1.1"`), `eventstreamProperties.json`
(retencja, przepustowość) i `.platform`. Pułapki, które kosztowały najwięcej czasu:

- **Nazwy węzłów: tylko litery, cyfry i `_`**, powyżej 3 i do 64 znaków. Myślniki są odrzucane.
- **`dataType` w warunku filtra to indeks enuma, nie nazwa.** Nazwy (`String`, `Nvarchar`, …)
  są odrzucane. `0` = `BigInt`, `1` = `Float`, **`2` = `Nvarchar(max)`**, `3` = `DateTime`.
  Ustawienie `0` dla kolumny tekstowej nie powoduje żadnego błędu — filtr po prostu
  nigdy nie dopasowuje i wszystkie zdarzenia znikają.
- **`itemId` destynacji Eventhouse to ID bazy KQL**, nie ID Eventhouse'u (inaczej
  „Unable to extract cluster URL…").
- **`dataIngestionMode: "ProcessedIngestion"` mapuje pola JSON na kolumny po nazwach.**
  Skierowanie na tabelę `*Raw` z jedną kolumną `payload: dynamic` przełącza destynację
  w stan `Warning` i gubi zdarzenia bez śladu w błędach ingestii. Dlatego destynacje
  wskazują tabele typowane (`CiNodeStatus`, `CiOperatorReport`, `HydroReading`);
  nadmiarowe pole `stream` jest po prostu ignorowane.
- Po `updateDefinition` węzły przechodzą przez stan `Creating`/`Updating` (60–80 s).
  **Zdarzenia wysłane w tym czasie przepadają**, a kolejny `updateDefinition` zostaje
  odrzucony — dlatego skrypt najpierw czeka na stabilizację (`wait_stable`).
- Od wysyłki do widoczności w tabeli docelowej mija ok. 40 s.
- Endpoint pobiera się z `GET .../eventstreams/{id}/sources/{srcId}/connection`; odpowiedź
  jest płaska: `fullyQualifiedNamespace`, `eventHubName`, `accessKeys.primaryConnectionString`.

Rozgałęzienie opiera się na polu `stream` doklejanym do każdego zdarzenia przez
`simulate_realtime.py` — to jedyny dyskryminator, po którym filtry rozdzielają ruch.

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

## Format definicji raportu Power BI (PBIR)

Skrypt `10` generuje raport w formacie **PBIR** — po jednym pliku JSON na wizualizację. Struktura
części wysyłanych do API:

```text
definition.pbir                                    # wiązanie z modelem semantycznym
definition/version.json
definition/report.json                             # motyw, ustawienia raportu
definition/pages/pages.json                        # kolejność stron
definition/pages/{strona}/page.json
definition/pages/{strona}/visuals/{wizual}/visual.json
StaticResources/RegisteredResources/OL-ZK-Dark.json  # motyw niestandardowy
.platform
```

Pułapki, które kosztowały trzy nieudane importy:

- `definition/version.json` — pole `version` musi pasować do wzorca `^[1-9][0-9]*\.(0|[1-9][0-9]*)\.0$`,
  czyli np. `2.0.0`. Wartość `1.0` jest odrzucana.
- `themeCollection.customTheme` wymaga pola `reportVersionAtImport` — bez niego import się nie powiedzie.
- Wiązanie z istniejącym modelem: `datasetReference.byConnection` z `pbiModelDatabaseName` ustawionym
  na **identyfikator obiektu** modelu semantycznego (nie nazwę), `pbiModelVirtualServerName =
  "sobe_wowvirtualserver"`, `connectionType = "pbiServiceXmlaStyleLive"`.
- Nazwy stron i wizualizacji: `[A-Za-z0-9_-]`, do 50 znaków; nie muszą być GUID-ami, ale muszą być
  unikalne w obrębie strony.
- Nazwy typów wizualizacji odbiegają od nazw z interfejsu: tabela to `tableEx`, macierz to
  `pivotTable`, mapa to `azureMap`, drzewo dekompozycji to `decompositionTreeVisual`.
- Odwołanie do miary i do kolumny mają różny kształt (`Measure` vs `Column`), a kolumna użyta jako
  wartość liczbowa musi być opakowana w `Aggregation` z polem `Function`
  (`0` = suma, `1` = średnia, `2` = zliczanie unikalnych, `3` = minimum, `4` = maksimum, `5` = zliczanie).
- Nazwy ról w `queryState` zależą od typu wizualizacji: `Values` (karta, tabela, fragmentator),
  `Category`/`Series`/`Y` (wykresy), `Rows`/`Columns`/`Values` (macierz), `Analyze`/`ExplainBy`
  (drzewo dekompozycji), `Latitude`/`Longitude`/`Size` (mapa).
- Tekst statyczny to `visualType: "textbox"` z nietypową strukturą
  `objects.general[0].properties.paragraphs[].textRuns[]`.
- Fabric **waliduje strukturę** PBIR przy zapisie (`Report_Import_FailedToImportReport` z dokładnym
  komunikatem), ale **nie sprawdza, czy pole istnieje w modelu**. Dlatego `10` waliduje odwołania
  lokalnie przed wysyłką, a `11` weryfikuje je zapytaniem DAX po wdrożeniu.

## Ponowne uruchomienie

Skrypty są idempotentne: istniejące elementy są wykrywane po nazwie i pomijane lub aktualizowane
(`.create-or-alter` w KQL, nadpisanie definicji notatnika i modelu). Aby wdrożyć do innego
workspace'u, usuń `..\.fabric\deployment.json` i zacznij od skryptu `01`.
