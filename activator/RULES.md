# Reguły alertowe — Data Activator (Reflex)

Zasada nadrzędna: **Activator ma budzić człowieka wtedy, gdy zdarzenie przestaje być awarią,
a zaczyna być kaskadą.** Alert o pojedynczej awarii obiektu jest szumem — operator wie o niej
pierwszy. Wartością jest sygnał o skutku drugiego rzędu, którego nie widzi nikt, kto patrzy
tylko na swój system.

Źródło zdarzeń: Eventhouse `CriticalInfrastructure` (`CiNodeStatus`, `CiOperatorReport`) oraz
tabela `CascadeCentrality` z wynikami notebooków.

---

## R1 — Kaskada wykryta (alert główny)

| Pole | Wartość |
|---|---|
| Obiekt | wynik funkcji `DetectCascade(6h, 3)` |
| Warunek | awaria obiektu pociągnęła ≥ 3 obiekty zależne w ≥ 2 systemach IK |
| Okno | 6 h kroczące |
| Odbiorca | dyżurny RCB (Teams: *Dyżur RCB*), wojewódzkie CZK właściwego województwa |
| Treść | „Efekt domina: awaria {node_name} ({node_type}) pociągnęła {children} obiektów w {systems_hit} systemach IK. Średnie opóźnienie skutku: {avg_delay_h} h." |
| Akcja | otwarcie strony „Wyłącz ten węzeł" z preselekcją obiektu |
| Tłumienie | 1 alert na obiekt źródłowy na 6 h |

## R2 — Skutek trzeciego rzędu

| Pole | Wartość |
|---|---|
| Warunek | w kaskadzie pojawia się obiekt fali ≥ 3 |
| Odbiorca | dyżurny RCB, sekretarz RZZK |
| Treść | „Zdarzenie przekroczyło trzeci rząd skutków. Rekomendacja: rozważyć SPO-1 (posiedzenie RZZK) i SPO-12 (obieg informacji)." |
| Uzasadnienie | trzeci rząd skutków oznacza, że zdarzenie na pewno wyszło poza jeden resort |
| Tłumienie | 1 alert na zdarzenie (identyfikowane po obiekcie źródłowym fali 0) |

## R3 — Paliwo w agregacie na wyczerpaniu

| Pole | Wartość |
|---|---|
| Obiekt | `FuelRunout(6.0)` |
| Warunek | obiekt K1 lub K2 na zasilaniu rezerwowym, `backup_fuel_hours_left ≤ 6` |
| Odbiorca | wojewódzkie CZK, operator obiektu, logistyka (powiązanie z `ol-zasoby-logistyka`) |
| Treść | „{node_name}: paliwo w agregacie na {backup_fuel_hours_left} h. Obsługuje {population_served} odbiorców. Operator: {operator_name}." |
| Akcja | utworzenie zapotrzebowania transportowego w aplikacji |
| Tłumienie | 1 alert na obiekt na 4 h; alert powtarzany przy progu 2 h |

## R4 — Woda przestanie płynąć

| Pole | Wartość |
|---|---|
| Obiekt | `CascadeForecast(12h)` ograniczone do `target_system = "IK06"` |
| Warunek | prognozowana utrata funkcji stacji uzdatniania lub przepompowni w ciągu 12 h |
| Odbiorca | wojewoda, gmina, służby OL, `ol-blackout-wrazliwi` (punkt styku ludność wrażliwa) |
| Treść | „Prognoza: {any_target_name} straci zasilanie za {hours_left} h. Ludność w gminie: {any_population}. Uruchomić dystrybucję wody butelkowanej (SPO-2)." |
| Uzasadnienie | to jedyny alert, który wyprzedza zdarzenie o czas potrzebny na reakcję logistyczną |
| Tłumienie | 1 alert na obiekt na 12 h |

## R5 — Obiekt krytyczny bez kontaktu operacyjnego

| Pole | Wartość |
|---|---|
| Warunek | obiekt K1 w stanie `down`, dla którego `spo10_agreement = false` |
| Odbiorca | RCB — komórka ds. infrastruktury krytycznej |
| Treść | „Awaria obiektu K1 {node_name}, operator {operator_name}, brak umowy o wymianie danych (SPO-10). Kontakt wymaga trybu awaryjnego." |
| Uzasadnienie | alert nie dotyczy techniki, tylko procesu — pokazuje lukę, którą trzeba zamknąć poza kryzysem |
| Tłumienie | 1 alert na obiekt na 24 h |

## R6 — Wiele systemów IK naraz w jednym województwie

| Pole | Wartość |
|---|---|
| Obiekt | `CascadeFootprint()` |
| Warunek | ≥ 4 systemy IK ze statusem `down`/`degraded` w jednym województwie |
| Odbiorca | wojewoda, RCB |
| Treść | „{voivodeship_code}: dotknięte {systems_affected} z 11 systemów IK, {k1_affected} obiektów K1. Sugerowany poziom: {escalation_hint}." |
| Akcja | powiadomienie do `ol-cop24` (wspólny obraz sytuacji) i `ol-siatka-bezpieczenstwa` (aktywacja modułów zadaniowych) |
| Tłumienie | 1 alert na województwo na 3 h |

## R7 — Anomalia liczby awarii

| Pole | Wartość |
|---|---|
| Obiekt | `OutageAnomaly(1h)` |
| Warunek | wykryta anomalia (`series_decompose_anomalies`, próg 2.0) w liczbie awarii w systemie IK |
| Odbiorca | analityk dyżurny |
| Treść | „System {system_code}: {nodes_down} awarii wobec spodziewanych {baseline}. Sprawdzić, czy to zdarzenie naturalne, czy działanie celowe (Z04/Z16)." |
| Uzasadnienie | to jedyna reguła, która nie zakłada przyczyny naturalnej — łączy się ze scenariuszem zagrożeń hybrydowych |
| Tłumienie | 1 alert na system na 6 h |

---

## Progi i ich strojenie

| Parametr | Wartość domyślna | Kiedy zmienić |
|---|---|---|
| Minimalna liczba obiektów zależnych w R1 | 3 | podnieść do 5 przy zdarzeniach o dużej skali, żeby nie zalać dyżurnego |
| Próg paliwa R3 | 6 h | podnieść do 12 h zimą i przy złej przejezdności dróg |
| Horyzont prognozy R4 | 12 h | skrócić do 6 h, gdy logistyka działa w trybie zaostrzonym |
| Liczba systemów w R6 | 4 | to jest próg, przy którym zdarzenie z definicji przestaje należeć do jednego ministra |

## Zasady, które trzeba uzgodnić przed uruchomieniem

1. **Kto odbiera alert w nocy** — reguła bez przypisanej dyżurki jest regułą martwą.
2. **Co się dzieje, gdy alert jest fałszywy** — musi istnieć droga zwrotna do korekty progu, inaczej po tygodniu wszyscy wyciszą kanał.
3. **Czy alert może iść bezpośrednio do operatora IK** — to decyzja prawna wynikająca z SPO-10, nie techniczna.
4. **Retencja alertów** — historia alertów jest materiałem do lessons learned i musi przeżyć zdarzenie.
