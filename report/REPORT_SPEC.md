# Specyfikacja raportu Power BI — „Efekt domina"

Sześć stron. Każda odpowiada na jedno pytanie decydenta i kończy się konkretną decyzją.
Raport jest przeznaczony na odprawę, nie na dyżur — dyżurny pracuje na Real-Time Dashboard.

---

## Strona 1 — „Mapa zależności" (wejście)

**Pytanie:** czym w ogóle jest krajowa infrastruktura krytyczna i jak bardzo jest ze sobą splątana.

| Element | Wizual | Miara / pole |
|---|---|---|
| Karty górne | 4 × karta | `Obiekty IK`, `Zależności`, `Udział zależności bez redundancji %`, `Zależności niesprawdzone w ćwiczeniu %` |
| Mapa Polski | mapa punktowa | `DimNode[lat/lon]`, rozmiar = `population_served`, kolor = `system_code` |
| Macierz zależności | macierz 11 × 11 | wiersze = system dostawcy, kolumny = system odbiorcy, wartość = `Zależności` |
| Rozkład typów zależności | wykres słupkowy | `FactDependency[dependency_type]` |
| Filtry | segmentatory | województwo, system IK, klasa krytyczności |

**Punkt narracyjny:** macierz 11 × 11 pokazuje, że system energetyczny jest dostawcą dla wszystkich
pozostałych dziesięciu. To nie jest opinia — to policzalna właściwość grafu.

---

## Strona 2 — „Wyłącz ten węzeł" (wow moment)

**Pytanie:** co się stanie, jeśli ten jeden obiekt przestanie działać.

| Element | Wizual | Uwagi |
|---|---|---|
| Wybór obiektu | segmentator jednokrotny na `DimNode[node_name]` | domyślnie stacja NN 400/220 kV z osi scenariusza |
| Nagłówek | karta z tekstem | miara `Nagłówek kaskady` |
| Drzewo skutków | dekompozycja (decomposition tree) | `FactEffectTree`: fala → system → typ obiektu → obiekt |
| Oś czasu skutków | wykres punktowy | oś X = `fail_hour`, oś Y = system IK, rozmiar = `population_served` |
| Cztery karty skutków | karty | szpitale, węzły wodociągowe, węzły telekomunikacyjne, obiekty ratownictwa |
| „Woda przestanie płynąć za" | karta z dużą liczbą | `MIN(fail_hour)` dla `system_group = "water"` |

**Punkt narracyjny:** kliknięcie w jeden obiekt, a po sekundzie pełna lista skutków drugiego i
trzeciego rzędu z czasem ich wystąpienia. Dekompozycja pokazuje, że skutki wychodzą poza
system, w którym doszło do awarii — i poza resort, który za ten system odpowiada.

---

## Strona 3 — „Pojedyncze punkty awarii"

**Pytanie:** gdzie jedna awaria kosztuje najwięcej i czy w ogóle o tych obiektach wiemy.

| Element | Wizual | Miara / pole |
|---|---|---|
| Ranking obiektów | tabela | `FactCascadeCentrality`: `cascade_index`, `cascade_nodes`, `cascade_systems`, `cascade_population` |
| Rozrzut | wykres punktowy | X = `cascade_nodes`, Y = `cascade_population`, kolor = `system_code` |
| Karty governance | 3 × karta | `SPOF poza rejestrem IK`, `SPOF bez umowy SPO-10`, `Krytyczne obiekty bez kontaktu operacyjnego` |
| Powód klasyfikacji | tabela | kolumna `spof_reason` z `single_points_of_failure.csv` |
| Mapa cieplna | mapa | koncentracja obiektów o wysokim `cascade_index` |

**Punkt narracyjny:** najwyżej w rankingu nie stoi elektrownia, tylko **magazyn paliw** —
bo zasila generatory, które zasilają wszystko inne. Tego wniosku nie da się uzyskać, patrząc na
każdy system osobno; wymaga on jednego grafu dla wszystkich jedenastu systemów.

---

## Strona 4 — „Powódź wrzesień — kaskada w czasie"

**Pytanie:** jak wygląda pełna kaskada realnego zdarzenia i kiedy przestaje być lokalna.

| Element | Wizual | Uwagi |
|---|---|---|
| Oś czasu fal | wykres warstwowy skumulowany | oś X = godzina od D0, seria = fala 0–7 |
| Profil systemowy | wykres liniowy | `cascade_hourly_profile.csv`, seria = system IK |
| Karty | 4 × karta | `Zdarzenia inicjujące`, `Skutki wtórne`, `Współczynnik wzmocnienia`, `Okno reakcji (h)` |
| Poziom eskalacji | karta | miara `Poziom eskalacji` |
| Czas do skutku per gmina | tabela | `cascade_gmina_time_to_effect.csv` z kolumnami: energia, woda, zdrowie, łączność |
| Animacja | „odtwórz oś czasu" | pole `hour_bucket` jako oś odtwarzania |

**Punkt narracyjny:** 232 obiekty podtopione bezpośrednio, 545 wtórnie. Zdarzenie mnoży się
prawie trzykrotnie, a pierwszy skutek wtórny pojawia się po 33 minutach — czyli zanim sztab
zdąży się zebrać.

---

## Strona 5 — „Co warto wzmocnić" (what-if)

**Pytanie:** gdzie wydać pieniądze, żeby to samo zdarzenie zabolało mniej.

| Element | Wizual | Miara / pole |
|---|---|---|
| Porównanie wariantów | wykres słupkowy | `FactWhatIf`: skutki wtórne w wariantach BAZOWY / A / B / C |
| Redukcja | karty | `Redukcja skutków wtórnych p.p.`, `Ludność uratowana`, `Efektywność wariantu` |
| Ranking inwestycji | tabela | `FactMarginalValue`: `nodes_saved`, `population_saved`, `current_autonomy_h` |
| Lista obiektów do wzmocnienia | tabela z eksportem | obiekt, operator, obecna autonomia, umowa SPO-10 |

**Punkt narracyjny:** wariant tańszy (agregaty w obiektach usługowych) daje kilkukrotnie większą
redukcję niż wariant droższy (nowe linie zasilające). To jest dokładnie ten rodzaj wniosku,
którego nie da się obronić na spotkaniu bez modelu.

---

## Strona 6 — „Gotowość i współpraca (SPO-10)"

**Pytanie:** czy mamy z kim rozmawiać, zanim coś się stanie.

| Element | Wizual | Miara / pole |
|---|---|---|
| Scorecard | karty | `Obiekty w rejestrze IK %`, `Umowy o wymianie danych %`, `Plany ochrony nieaktualne` |
| Operatorzy | tabela | operator, liczba obiektów K1, `Responsywność operatora`, data ostatniego testu kontaktu |
| Luka rejestrowa | wykres | obiekty o wysokim `cascade_index` poza rejestrem IK |
| Ćwiczenia | histogram | `Dni od ostatniego ćwiczenia` |

**Punkt narracyjny:** część obiektów o najwyższym indeksie kaskadowym jest poza rejestrem IK
i bez umowy o wymianie danych. Model odporności jest tyle wart, ile jakość rejestru, na którym
się opiera — i to też widać w liczbach.

---

## Nawigacja i drill-through

- Drill-through z każdej tabeli obiektów → strona szczegółu obiektu (poza sześcioma stronami głównymi):
  dane obiektu, dostawcy, odbiorcy, ekspozycja na Z01–Z20, historia statusu z Eventhouse, dane kontaktowe SPO-10.
- Przycisk „Pokaż w obrazie sytuacji" → zakładka Real-Time Dashboard.
- Przycisk „Zgłoś do operatora" → aplikacja Fabric App (ekran meldunku).

## Zasady prezentacji

- Liczby ludności zawsze z adnotacją, że to szacunek na podstawie gmin obsługiwanych, nie suma `population_served`
  (ta ostatnia zawiera nakładanie się usług między systemami i nie może być pokazywana jako liczba mieszkańców).
- Każda strona ma stopkę: *„Dane syntetyczne. Model wskazuje priorytety — decyzję podejmuje człowiek."*
- Motyw: ciemny, wysokokontrastowy (raport jest pokazywany na ścianie w centrum zarządzania kryzysowego).
