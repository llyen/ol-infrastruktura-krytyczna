# Model danych

Wszystkie dane są syntetyczne (`generate_datasets.py`, seed=42, wynik w pełni powtarzalny).
Kodowanie UTF-8. Znaczniki czasu w ISO-8601 ze strefą `+02:00`. Kody TERYT: województwo 2 znaki,
powiat 4 znaki, gmina 7 znaków — jako tekst, z wiodącymi zerami.

Konwencja: **CSV = wymiary i fakty referencyjne** (Lakehouse), **JSONL = strumienie zdarzeń**
(Eventstream → Eventhouse).

Oś czasu scenariusza: start `2026-09-09 00:00+02:00`, **D0 = `2026-09-12 06:00+02:00`**
(przekroczenie stanów alarmowych), koniec `2026-09-22 00:00+02:00`. Godziny w wynikach symulacji
(`fail_hour`) liczone są od D0.

---

## Wymiary geograficzne

### `dim_voivodeship.csv` — 16 wierszy
Ziarno: województwo.

| Kolumna | Typ | Opis |
|---|---|---|
| `voivodeship_code` | text(2) | kod TERYT |
| `voivodeship_name` | text | nazwa |
| `lat`, `lon` | float | centroida |
| `scenario_axis` | text | `POWODZ_WRZESIEN` dla woj. 02 i 16, w pozostałych puste |

### `dim_powiat.csv` — 380 wierszy
Ziarno: powiat. Kolumny: `powiat_code` (4), `voivodeship_code`, `powiat_name`, `lat`, `lon`.

### `dim_gmina.csv` — 2477 wierszy
Ziarno: gmina.

| Kolumna | Typ | Opis |
|---|---|---|
| `gmina_code` | text(7) | kod TERYT |
| `powiat_code`, `voivodeship_code` | text | klucze nadrzędne |
| `gmina_name` | text | nazwa |
| `gmina_type` | text | `miejska` / `miejsko-wiejska` / `wiejska` |
| `population` | int | liczba mieszkańców |
| `lat`, `lon` | float | centroida |

### `dim_river_gauge.csv` — 120 wierszy
Ziarno: wodowskaz. Kolumny: `gauge_id`, `voivodeship_code`, `powiat_code`, `gmina_code`,
`warning_level_cm` (stan ostrzegawczy), `alarm_level_cm` (stan alarmowy), `lat`, `lon`.

---

## Wymiary dziedzinowe

### `dim_hazard.csv` — 20 wierszy
Katalog zagrożeń Z01–Z20 zgodny z KPZK. Kolumny: `hazard_code`, `hazard_name`,
`probability_label`, `impact_label`, `probability_score` (1–5), `impact_score` (1–5),
`risk_score` (iloczyn).

### `dim_ci_system.csv` — 11 wierszy
Systemy infrastruktury krytycznej wg art. 3 pkt 2 ustawy o zarządzaniu kryzysowym.

| Kolumna | Typ | Opis |
|---|---|---|
| `system_code` | text | `IK01`–`IK11` |
| `system_name` | text | nazwa ustawowa |
| `responsible_department` | text | dział administracji rządowej |
| `system_group` | text | klucz techniczny: `energy`, `telecom`, `ict`, `finance`, `food`, `water`, `health`, `transport`, `rescue`, `admin`, `chemical` |
| `spo_reference` | text | powiązana procedura SPO |

### `dim_ci_node.csv` — 2106 wierszy
**Tabela centralna.** Ziarno: pojedynczy obiekt infrastruktury krytycznej.

| Kolumna | Typ | Opis |
|---|---|---|
| `node_id` | text | klucz główny, `IK-<system>-<nr>` |
| `node_name` | text | nazwa obiektu (syntetyczna) |
| `system_code` | text | FK → `dim_ci_system` |
| `system_group` | text | grupa techniczna systemu |
| `node_type` | text | typ obiektu, np. `stacja NN 400/220 kV`, `ujęcie wody`, `szpital wojewódzki` (39 typów) |
| `gmina_code`, `powiat_code`, `voivodeship_code` | text | lokalizacja TERYT |
| `lat`, `lon`, `elevation_m` | float | położenie i wysokość (wysokość używana przy ekspozycji powodziowej) |
| `operator_name` | text | operator, zawsze z sufiksem `(fikc.)` |
| `ownership` | text | `publiczna` / `prywatna` / `mieszana` |
| `criticality_class` | text | `K1` / `K2` / `K3` |
| `criticality_score` | float | 0–100 |
| `population_served` | int | liczba obsługiwanych mieszkańców **w ramach danego systemu** — nie sumować między systemami |
| `backup_type` | text | `dual_feed`, `agregat`, `UPS`, `agregat+UPS`, `brak` |
| `autonomy_hours` | float | czas pracy na zasilaniu rezerwowym |
| `fuel_reserve_hours` | float | zapas paliwa dla agregatu |
| `in_flood_zone` | int | 0/1 — obiekt w strefie zalewowej |
| `restore_hours` | float | zakładany czas przywrócenia funkcji po awarii |
| `on_ci_register` | int | 0/1 — obiekt figuruje w rejestrze IK |
| `spo10_agreement` | int | 0/1 — zawarta umowa o współpracy w trybie SPO-10 |
| `last_exercise_date` | date | data ostatniego ćwiczenia z udziałem obiektu |

> **Uwaga metodyczna do `population_served`:** systemy IK obsługują tę samą ludność równolegle
> (mieszkaniec ma prąd, wodę i szpital). Sumowanie tej kolumny między systemami zawyża wynik
> wielokrotnie. Wskaźniki ludnościowe w wynikach symulacji liczone są przez **unikalne gminy**,
> w których padł obiekt usługowy (`energy`, `water`, `health`) — patrz `impact_summary()`
> w `cascade_engine.py`.

### `fact_ci_dependency.csv` — 6552 wiersze
**Graf zależności.** Ziarno: skierowana krawędź „dostawca → odbiorca".

| Kolumna | Typ | Opis |
|---|---|---|
| `edge_id` | text | klucz główny |
| `source_node_id` | text | dostawca usługi |
| `target_node_id` | text | odbiorca zależny |
| `source_system`, `target_system` | text | kody systemów obu stron |
| `dependency_type` | text | `electricity`, `generation`, `fuel`, `water`, `telecom`, `ict`, `transport`, `chemical` |
| `impact_share` | float 0–1 | jaki udział wejść odbiorcy pokrywa ten dostawca |
| `lag_hours` | float | bufor technologiczny: opóźnienie skutku po awarii dostawcy |
| `redundancy_level` | text | `none` / `partial` / `full` |
| `cross_voivodeship` | int | 0/1 — zależność przekracza granicę województwa (132 przypadki) |
| `contract_sla_hours` | float | umowny czas reakcji dostawcy |
| `verified_in_exercise` | int | 0/1 — zależność potwierdzona w ćwiczeniu |

### `fact_node_hazard_exposure.csv` — 8614 wierszy
Ziarno: obiekt × zagrożenie. Kolumny: `node_id`, `hazard_code`, `exposure_score` (0–100),
`mitigation_level` (`brak` / `częściowe` / `pełne`), `assessment_date`.

### `fact_spo10_cooperation.csv` — 1463 wiersze
Ziarno: obiekt K1/K2 objęty trybem SPO-10.

| Kolumna | Typ | Opis |
|---|---|---|
| `node_id`, `operator_name` | text | obiekt i operator |
| `contact_point_registered` | int | 0/1 — zgłoszony punkt kontaktowy |
| `protection_plan_status` | text | `zatwierdzony` / `w opracowaniu` / `brak` |
| `protection_plan_age_days` | int | wiek planu ochrony |
| `data_sharing_agreement` | int | 0/1 — umowa o wymianie danych |
| `responsiveness_score` | float | 0–100, skuteczność kontaktu |
| `last_contact_test` | date | ostatni test łączności |

---

## Strumienie zdarzeń (JSONL → Eventstream)

### `ci_node_status.jsonl` — 659 178 zdarzeń
Ziarno: obiekt × 15-minutowy interwał. **190 MB — plik jest w `.gitignore`, odtwarzany
generatorem.**

| Pole | Typ | Opis |
|---|---|---|
| `event_time` | datetime | ISO-8601 `+02:00` |
| `node_id`, `system_code` | text | identyfikacja obiektu |
| `gmina_code`, `powiat_code`, `voivodeship_code` | text | lokalizacja |
| `status` | text | `operational` / `degraded` / `down` |
| `load_pct` | float | obciążenie / wykorzystanie |
| `on_backup_power` | int | 0/1 — praca na zasilaniu rezerwowym |
| `backup_fuel_hours_left` | float | pozostały zapas paliwa w godzinach |
| `water_level_margin_m` | float\|null | zapas do poziomu zalania (tylko obiekty w strefie zalewowej) |
| `population_served` | int | denormalizacja dla szybkich agregatów w KQL |

### `ci_operator_reports.jsonl` — 889 zdarzeń
Ziarno: meldunek operatora IK. Pola: `event_time`, `report_id`, `node_id`, `system_code`,
`voivodeship_code`, `powiat_code`, `operator_name`, `report_kind` (np. `zapotrzebowanie na pompy`,
`awaria zasilania`, `brak paliwa do agregatu`), `severity` (`info` / `warning` / `critical`),
`eta_restore_hours`, `support_requested` (0/1), `channel`.

### `hydro_readings.jsonl` — 37 560 zdarzeń
Ziarno: wodowskaz × interwał. Pola: `event_time`, `gauge_id`, `voivodeship_code`, `powiat_code`,
`gmina_code`, `water_level_cm`, `warning_level_cm`, `alarm_level_cm`, `state`
(`normalny` / `ostrzegawczy` / `alarmowy`).

### `generation_summary.json`
Metryki przebiegu generatora: liczby wierszy, parametry, seed, zakres czasu.

---

## Tabele wynikowe (`datasets/derived/`)

Produkowane przez notatniki; w Fabric zapisywane jako tabele Lakehouse i podpinane pod model
semantyczny.

### Z notatnika 01 — graf i jakość danych

| Plik | Ziarno | Zawartość |
|---|---|---|
| `graph_nodes.csv` (2106) | obiekt | `dim_ci_node` + `in_degree`, `out_degree`, `power_suppliers`, `single_source_power`, `no_backup`, `fragility_score` |
| `graph_edges.csv` (6552) | krawędź | kopia `fact_ci_dependency` przygotowana dla modelu |
| `system_summary.csv` (11) | system | `nodes`, `k1_nodes`, `population_served`, `avg_autonomy_h`, `no_backup_nodes`, `single_source_power`, `on_register_pct`, `system_name`, `responsible_department` |
| `dependency_matrix.csv` (29) | system×system×typ | `src_sys`, `dst_sys`, `dependency_type`, `edges` |
| `spo10_gaps.csv` (827) | obiekt K1/K2 z luką | `protection_plan_status`, `responsiveness_score`, `population_served` |
| `graph_summary.json` | — | wskaźniki zbiorcze grafu |

### Z notatnika 02 — kaskada

| Plik | Ziarno | Zawartość |
|---|---|---|
| `cascade_flood_timeline.csv` (777) | obiekt niedziałający | `fail_hour`, `fail_time`, `wave`, `cause_node_id`, `cause_node_name`, `cause_dependency` + atrybuty obiektu |
| `cascade_waves.csv` (8) | fala 0–7 | `nodes`, `first_hour`, `last_hour`, `population_served` |
| `cascade_hourly_profile.csv` (361) | godzina × system | `nodes_failed`, `cumulative` |
| `cascade_single_node_timeline.csv` (104) | obiekt | skutki wyłączenia jednego węzła demonstracyjnego |
| `cascade_effect_tree.csv` (104) | obiekt | to samo z `parent_node_id` — do wizualizacji drzewa skutków |
| `cascade_gmina_time_to_effect.csv` (224) | gmina | godziny do utraty usługi: `energy`, `water`, `telecom`, `health` |
| `cascade_summary.json` | — | liczby nagłówkowe scenariusza |

### Z notatnika 03 — centralność i SPOF

| Plik | Ziarno | Zawartość |
|---|---|---|
| `cascade_centrality.csv` (2106) | obiekt | wynik symulacji awarii tego obiektu: `cascade_nodes`, `cascade_max_wave`, `cascade_systems`, `cascade_population`, `cascade_gminas`, `cascade_k1_nodes`, `first_secondary_hour`, `cascade_index`, `cascade_tier` |
| `cascade_top100.csv` (100) | obiekt | 100 najgroźniejszych wg `cascade_index` |
| `single_points_of_failure.csv` (217) | obiekt SPOF | jw. + `backup_type`, `autonomy_hours`, `single_source_power`, `on_ci_register`, `spo10_agreement`, `in_flood_zone`, `fragility_score`, `spof_reason` |
| `cascade_by_voivodeship.csv` (16) | województwo | `nodes`, `critical_nodes`, `max_cascade_population`, `avg_cascade_index` |
| `cascade_by_system.csv` (11) | system | `nodes`, `avg_cascade_index`, `max_cascade_nodes`, `spof_nodes` |
| `spof_summary.json` | — | liczby zbiorcze i luki governance |

`cascade_index` to złożony wskaźnik krytyczności kaskadowej: 0,38 × ludność + 0,27 × liczba
obiektów + 0,20 × liczba dotkniętych systemów + 0,15 × obiekty K1 (składowe znormalizowane 0–100).
Kryterium SPOF: awaria obiektu dotyka **co najmniej 3 systemów IK** lub **co najmniej 100 tys.
mieszkańców**; przyczyna zapisana w `spof_reason`.

### Z notatnika 04 — warianty inwestycyjne

| Plik | Ziarno | Zawartość |
|---|---|---|
| `whatif_variants.csv` (4) | wariant | `description`, `hardened_nodes`, `new_feeds`, `nodes_failed_total`, `nodes_failed_secondary`, `max_wave`, `affected_gminas`, `affected_population`, `k1_nodes_failed`, `secondary_reduction_pct`, `population_reduction_pct` |
| `whatif_marginal_value.csv` (40) | obiekt | wartość krańcowa wzmocnienia: `current_autonomy_h`, `nodes_saved`, `population_saved`, `spo10_agreement` |
| `whatif_summary.json` | — | porównanie wariantów |

---

## Relacje w modelu semantycznym

`dim_ci_node` łączy się z `fact_ci_dependency` **dwiema relacjami**: aktywną po
`source_node_id` (widok „na kogo wpływam") i nieaktywną po `target_node_id` (widok „od kogo
zależę"), przełączaną w miarach przez `USERELATIONSHIP`. Szczegóły: `semantic-model/MODEL.md`.

Pozostałe relacje: `dim_ci_node[gmina_code]` → `dim_gmina`, `dim_gmina[powiat_code]` →
`dim_powiat`, `dim_powiat[voivodeship_code]` → `dim_voivodeship`, `dim_ci_node[system_code]` →
`dim_ci_system`, `fact_node_hazard_exposure[hazard_code]` → `dim_hazard`.
