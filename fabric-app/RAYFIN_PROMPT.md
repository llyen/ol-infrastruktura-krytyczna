# Prompt do generatora aplikacji (Rayfin / Fabric Apps)

Poniższy prompt służy do wygenerowania aplikacji opisanej w `APP_SPEC.md`.
Wklej całość jako pojedyncze polecenie.

---

Zbuduj aplikację operacyjną **„Symulator kaskad infrastruktury krytycznej"** dla centrum
zarządzania kryzysowego. Aplikacja korzysta z Lakehouse `lh_ci_graph` oraz bazy KQL
`CriticalInfrastructure` w tym samym workspace.

## Źródła danych

Lakehouse `lh_ci_graph`:
- `graph_nodes` — obiekty infrastruktury krytycznej (`node_id`, `node_name`, `node_type`,
  `system_code`, `criticality_class`, `operator_name`, `population_served`, `autonomy_hours`,
  `backup_type`, `on_ci_register`, `spo10_agreement`, `lat`, `lon`, `voivodeship_code`, `gmina_code`)
- `graph_edges` — zależności (`source_node_id`, `target_node_id`, `dependency_type`,
  `impact_share`, `lag_hours`, `redundancy_level`)
- `cascade_centrality` — ranking krytyczności kaskadowej (`cascade_index`, `cascade_nodes`,
  `cascade_population`, `cascade_systems`, `cascade_tier`)
- `cascade_effect_tree` — drzewo skutków (`node_id`, `parent_node_id`, `wave`, `fail_hour`)
- `whatif_marginal_value` — wartość pojedynczych inwestycji (`nodes_saved`, `population_saved`)
- `spo10_gaps` — luki we współpracy z operatorami

Baza KQL `CriticalInfrastructure`:
- funkcja `CiNodeCurrent` — aktualny stan obiektów
- funkcja `FuelRunout(threshold_hours)` — obiekty z kończącym się paliwem
- funkcja `CascadeForecast(horizon_hours)` — prognoza kolejnych awarii
- tabela `CiOperatorReport` — meldunki operatorów

## Ekrany

**1. Symulacja.** Wyszukiwarka obiektów po nazwie, typie i operatorze. Po wyborze obiektu pokaż
w panelu po prawej: dużą kartę z liczbą mieszkańców bez usług, liczbą obiektów wtórnych i liczbą
dotkniętych systemów IK; drzewo skutków zbudowane z `cascade_effect_tree` (poziomy = kolumna
`wave`, rodzic = `parent_node_id`); listę skutków w pierwszych sześciu godzinach posortowaną po
`fail_hour`. Suwak horyzontu 6–240 h. Przyciski: „Zapisz scenariusz ćwiczebny", „Eksportuj PDF",
„Wyślij do wojewody".

**2. Obraz bieżący.** Mapa obiektów w stanie `down` i `degraded` (kolor według `system_code`,
rozmiar według `population_served`). Pod mapą trzy listy: obiekty K1 niedziałające, kolejka
paliwowa z `FuelRunout(8.0)`, prognoza z `CascadeForecast(24.0)` z kolumną „godzin do skutku".
Automatyczne odświeżanie co 60 sekund.

**3. Meldunek operatora.** Formularz z polami: obiekt (lista ograniczona do obiektów
zalogowanego operatora), rodzaj zdarzenia (lista słownikowa), stan obiektu (operational /
degraded / down), zasilanie rezerwowe (tak/nie + godziny paliwa), przewidywany czas przywrócenia
w godzinach, potrzebne wsparcie (wielokrotny wybór: paliwo, pompy, transport, ochrona, łączność),
opis do 1000 znaków, załącznik. Walidacja: czas przywrócenia wymagany przy stanie `down`;
godziny paliwa wymagane przy zasilaniu rezerwowym. Zapis do tabeli
`ci_operator_report_writeback` oraz wysyłka zdarzenia do Eventstream. Formularz musi działać
offline i kolejkować meldunki do czasu odzyskania łączności.

**4. Rejestr IK.** Karta obiektu: dane techniczne, klasa krytyczności, indeks kaskadowy,
status współpracy SPO-10, historia meldunków. Czerwone znaczniki dla luk: brak umowy o wymianie
danych, brak punktu kontaktowego, obiekt poza rejestrem IK. Przyciski: „Zainicjuj test kontaktu",
„Zgłoś wniosek o wpis do rejestru", „Zaplanuj ćwiczenie".

**5. Plan wzmocnień.** Tabela obiektów z `whatif_marginal_value` z kolumnami: obiekt, operator,
obecna autonomia, liczba uratowanych obiektów, liczba uratowanych mieszkańców. Użytkownik
zaznacza obiekty do koszyka, aplikacja pokazuje łączny efekt. Przycisk „Zatwierdź plan"
zapisuje decyzję z uzasadnieniem i podpisem do `hardening_plan_writeback`.

## Role

- `Dyzurny_RCB` — ekrany 1, 2, 4, pełny zakres krajowy
- `CZK_Wojewodzkie` — ekrany 1, 2, 3, 4, filtr na własne województwo
- `Operator_IK` — ekrany 3 i 4, wyłącznie własne obiekty, bez dostępu do pełnego grafu zależności
- `Decydent` — ekrany 1 i 5
- `Audytor` — podgląd write-backów, tylko odczyt

## Wygląd i zachowanie

Motyw ciemny, wysoki kontrast — aplikacja jest używana na ścianie wizyjnej i na tabletach w terenie.
Typografia duża, kluczowe liczby wyróżnione. Każdy ekran ma widoczną stopkę:
„Dane syntetyczne — demo. Model wskazuje priorytety, decyzję podejmuje człowiek."
Wszystkie etykiety, komunikaty i walidacje po polsku. Nazwy tabel i kolumn pozostają angielskie.
