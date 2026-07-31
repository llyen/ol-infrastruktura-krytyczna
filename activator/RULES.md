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
| Obiekt | `DetectCascade(6h, 3)` × `CascadeCentrality` |
| Warunek | w kaskadzie pojawia się obiekt fali ≥ 3 (`cascade_max_wave >= 3`) |
| Odbiorca | dyżurny RCB, sekretarz RZZK |
| Treść | „Kaskada od {node_name} sięga fali {cascade_max_wave} i obejmuje {cascade_systems} systemów IK ({cascade_population} osób). Rekomendacja: rozważyć SPO-1 (posiedzenie RZZK) i SPO-12 (obieg informacji)." |
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
| Obiekt | `CascadeForecast(12h)` ograniczone do `any_target_system = "IK06"` |
| Warunek | prognozowana utrata funkcji stacji uzdatniania lub przepompowni w ciągu 12 h |
| Odbiorca | wojewoda, gmina, służby OL, `ol-blackout-wrazliwi` (punkt styku ludność wrażliwa) |
| Treść | „Prognoza: {any_target_name} straci zasilanie za {hours_left} h. Ludność: {any_population}. Uruchomić dystrybucję wody butelkowanej (SPO-2)." |
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
| Warunek | wykryta anomalia (`series_decompose_anomalies`, próg 2.0) w liczbie **nowych** awarii w systemie IK, co najmniej 3 w oknie |
| Odbiorca | analityk dyżurny |
| Treść | „System {system_code}: {nodes_down} nowych awarii wobec spodziewanych {baseline} (wskaźnik {anomaly_score}). Sprawdzić, czy to zdarzenie naturalne, czy działanie celowe (Z04/Z16)." |
| Uzasadnienie | to jedyna reguła, która nie zakłada przyczyny naturalnej — łączy się ze scenariuszem zagrożeń hybrydowych |
| Tłumienie | 1 alert na system na 6 h |

> Reguła liczy **nowe** awarie na godzinę, a nie liczbę obiektów będących w awarii.
> `CiNodeStatus` powtarza status `down` co godzinę, dopóki obiekt jest wyłączony,
> więc liczba obiektów w awarii jest szeregiem monotonicznie rosnącym — `linefit`
> dopasowuje go idealnie i anomalia nigdy by nie powstała.

---

## Wdrożenie

Reguły są wdrażane skryptem, nie klikane w interfejsie:

```powershell
python deploy\14_activator.py            # kotwica: szczyt scenariusza
python deploy\15_verify_activator.py     # kontrola spójności 7 reguł
```

Każda reguła ma w bazie KQL własną funkcję `ActivatorR*` (plik `activator\queries.kql`),
która zwraca wiersz **wyłącznie wtedy, gdy alert ma się odpalić**. Activator uruchamia
ją co 5 minut i tworzy zdarzenie dla każdego wiersza. Dzięki temu cała logika progu
jest w KQL — wersjonowana, testowalna i czytelna — a warunek w samej regule sprawdza
tylko techniczną kolumnę `alert > 0`.

| Reguła | Funkcja KQL | Wierszy przy szczycie scenariusza |
|---|---|---|
| R1 | `ActivatorR1Cascade()` | 13 |
| R2 | `ActivatorR2ThirdOrder()` | 2 |
| R3 | `ActivatorR3Fuel(6.0, at)` | 123 |
| R4 | `ActivatorR4Water(12.0, at)` | 29 |
| R5 | `ActivatorR5NoSpo10(at)` | 11 |
| R6 | `ActivatorR6Footprint(4)` | 2 |
| R7 | `ActivatorR7Anomaly(2.0, at)` | 3 |

**Kotwica czasowa.** Dane demo są datowane na wrzesień 2026 i kończą się po odbudowie
sieci, więc przy kotwicy `ScenarioNow()` reguły R4, R5 i R7 milczą — sytuacja już wróciła
do normy. Domyślnie skrypt kotwiczy reguły na `ScenarioPeak()`, dzięki czemu demo na
danych statycznych pokazuje pełny obraz. Przy pracy z symulatorem na żywo należy użyć
`--anchor now`.

**Tłumienie** opisane w tabelach powyżej jest wymaganiem projektowym, którego Activator
nie egzekwuje po stronie reguły — realizuje je okno w zapytaniu KQL. Przy strojeniu
progów zmienia się funkcję, nie definicję reguły.

**Odbiorca.** Domyślnie alerty idą do zalogowanego użytkownika; adres docelowy podaje się
przez `--recipient`. Reguła bez przypisanej dyżurki jest regułą martwą — patrz punkt 1 poniżej.

---

## Progi i ich strojenie

| Parametr | Wartość domyślna | Kiedy zmienić |
|---|---|---|
| Minimalna liczba obiektów zależnych w R1 | 3 | podnieść do 5 przy zdarzeniach o dużej skali, żeby nie zalać dyżurnego |
| Próg paliwa R3 | 6 h | podnieść do 12 h zimą i przy złej przejezdności dróg |
| Horyzont prognozy R4 | 12 h | skrócić do 6 h, gdy logistyka działa w trybie zaostrzonym |
| Liczba systemów w R6 | 4 | to jest próg, przy którym zdarzenie z definicji przestaje należeć do jednego ministra |
| Minimalna liczba nowych awarii w R7 | 3 | obniżyć tylko razem z podniesieniem czułości — w systemie rzadko awaryjnym pojedyncza awaria daje wysoki wskaźnik wobec tła bliskiego zeru |

## Zasady, które trzeba uzgodnić przed uruchomieniem

1. **Kto odbiera alert w nocy** — reguła bez przypisanej dyżurki jest regułą martwą.
2. **Co się dzieje, gdy alert jest fałszywy** — musi istnieć droga zwrotna do korekty progu, inaczej po tygodniu wszyscy wyciszą kanał.
3. **Czy alert może iść bezpośrednio do operatora IK** — to decyzja prawna wynikająca z SPO-10, nie techniczna.
4. **Retencja alertów** — historia alertów jest materiałem do lessons learned i musi przeżyć zdarzenie.
