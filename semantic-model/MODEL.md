# Model semantyczny — Infrastruktura Krytyczna / efekt domina

Model jest zbudowany wokół jednego pytania: **jeśli ten obiekt przestanie działać, co się stanie i kiedy.**
Dlatego centralną tabelą faktów nie jest telemetria, lecz **wynik symulacji kaskady** — telemetria
odpowiada za obraz bieżący, a symulacja za obraz przewidywany.

## Tryb łączności

| Warstwa | Tryb | Uzasadnienie |
|---|---|---|
| Wymiary i wyniki notebooków (Lakehouse) | Import | małe wolumeny, złożone miary DAX, szybkie drill-down |
| `CiNodeStatus` / `CiNodeCurrent` (Eventhouse) | DirectQuery na KQL | obraz bieżący musi być świeży, nie odświeżany harmonogramem |
| Raport operacyjny dyżurnego | Real-Time Dashboard (KQL) | osobne narzędzie, osobny cykl decyzyjny |

## Tabele

### Wymiary

| Tabela | Źródło | Ziarno | Rola |
|---|---|---|---|
| `DimNode` | `datasets/derived/graph_nodes.csv` | obiekt IK | oś główna wszystkich analiz |
| `DimSystem` | `dim_ci_system.csv` | system IK (11) | podział ustawowy, dział administracji |
| `DimVoivodeship`, `DimPowiat`, `DimGmina` | `dim_*.csv` | jednostka TERYT | hierarchia geograficzna i drill-down |
| `DimHazard` | `dim_hazard.csv` | zagrożenie Z01–Z20 | powiązanie z matrycą ryzyka KPZK |
| `DimOperator` | wyliczana z `graph_nodes.csv` | operator IK | perspektywa SPO-10 |
| `DimWave` | tabela wyliczana 0–8 | fala kaskady | oś „rząd skutku” |

### Fakty

| Tabela | Źródło | Ziarno | Kluczowe kolumny |
|---|---|---|---|
| `FactDependency` | `graph_edges.csv` | krawędź grafu | `impact_share`, `lag_hours`, `redundancy_level` |
| `FactCascadeCentrality` | `cascade_centrality.csv` | obiekt IK | `cascade_index`, `cascade_population`, `cascade_systems` |
| `FactCascadeTimeline` | `cascade_flood_timeline.csv` | obiekt × zdarzenie | `fail_hour`, `wave`, `cause_node_id` |
| `FactEffectTree` | `cascade_effect_tree.csv` | obiekt × scenariusz jednowęzłowy | `parent_node_id`, `wave` |
| `FactWhatIf` | `whatif_variants.csv` | wariant inwestycyjny | `secondary_reduction_pct`, `affected_population` |
| `FactMarginalValue` | `whatif_marginal_value.csv` | obiekt kandydat | `nodes_saved`, `population_saved` |
| `FactHazardExposure` | `fact_node_hazard_exposure.csv` | obiekt × zagrożenie | `exposure_score`, `mitigation_level` |
| `FactSpo10` | `fact_spo10_cooperation.csv` | obiekt | `protection_plan_status`, `responsiveness_score` |
| `FactNodeStatus` | KQL `CiNodeStatus` | obiekt × godzina | `status`, `on_backup_power`, `backup_fuel_hours_left` |

## Relacje

```
DimVoivodeship 1 ─── * DimPowiat 1 ─── * DimGmina 1 ─── * DimNode
DimSystem      1 ─── * DimNode
DimOperator    1 ─── * DimNode
DimNode        1 ─── * FactCascadeCentrality   (1:1 w praktyce)
DimNode        1 ─── * FactCascadeTimeline
DimNode        1 ─── * FactNodeStatus
DimNode        1 ─── * FactSpo10
DimNode        1 ─── * FactHazardExposure * ─── 1 DimHazard
DimNode        1 ─── * FactDependency        (rola: dostawca)
DimNode        1 ─── * FactDependency        (rola: odbiorca, relacja nieaktywna + USERELATIONSHIP)
DimWave        1 ─── * FactCascadeTimeline
```

**Dwie role `DimNode` wobec `FactDependency`** są kluczowe: ta sama tabela obiektów pełni rolę
dostawcy i odbiorcy. Relacja „odbiorca” jest nieaktywna i włączana przez `USERELATIONSHIP`
w miarach, które patrzą na graf „od strony ofiary”, a nie „od strony przyczyny”.

## Grupy obliczeniowe

**`Perspektywa`** — przełącza cały raport między trzema ujęciami bez duplikowania miar:

| Element | Znaczenie |
|---|---|
| `Stan bieżący` | dane z Eventhouse: co nie działa teraz |
| `Symulacja` | wynik kaskady: co przestanie działać i kiedy |
| `Po wzmocnieniu` | wariant C z what-if: jak wyglądałoby to samo zdarzenie po inwestycjach |

## Hierarchie

- `Geografia`: województwo → powiat → gmina → obiekt
- `System IK`: system (11) → typ obiektu → obiekt
- `Kaskada`: fala → system → obiekt

## Zabezpieczenia (RLS)

| Rola | Filtr | Uzasadnienie |
|---|---|---|
| `RCB_Krajowy` | brak | pełny obraz krajowy |
| `Wojewoda` | `DimVoivodeship[voivodeship_code] = USERPRINCIPALNAME()` przez tabelę mapowania | wojewoda widzi swoje województwo |
| `Operator_IK` | `DimOperator[operator_name] = <mapowanie użytkownika>` | operator widzi wyłącznie własne obiekty i swoje zależności |
| `Analityk` | `DimNode[criticality_class] <> "K1"` | warstwa robocza bez najbardziej wrażliwych obiektów |

Rola `Operator_IK` jest istotna merytorycznie: SPO-10 zakłada dwustronną wymianę informacji z
operatorami, ale operator nie może widzieć pełnej mapy zależności krajowej infrastruktury.

## Etykiety wrażliwości

Model jest oznaczony jako `Confidential — synthetic critical infrastructure demo`.
W realnym wdrożeniu lokalizacje i zależności obiektów IK są informacją chronioną — model
wymagałby etykiety niejawności, Private Link i pełnego audytu dostępu.
