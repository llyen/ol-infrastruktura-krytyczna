# Fabric App — „Symulator kaskad IK"

Aplikacja operatorska domykająca pętlę: od pytania „co jeśli", przez decyzję, po zapis
w rejestrze. Bez write-backu demo pozostaje prezentacją; z write-backiem staje się narzędziem
pracy sztabu i ćwiczeń.

**Odbiorcy:** dyżurny RCB, wojewódzkie CZK, komórka ds. infrastruktury krytycznej, operator IK
(w zakresie własnych obiektów).

---

## Ekran 1 — „Symulacja: wyłącz obiekt"

Ekran startowy. Użytkownik wskazuje obiekt i natychmiast widzi konsekwencje.

| Pole | Typ | Źródło / uwagi |
|---|---|---|
| Obiekt IK | wyszukiwarka z podpowiedziami | `DimNode` (nazwa, typ, operator, gmina) |
| Tryb symulacji | przełącznik | „awaria natychmiastowa" / „awaria zapowiedziana (planowany wyłącznik)" |
| Horyzont | suwak 6–240 h | domyślnie 48 h |
| Założenie o agregatach | przełącznik | „stan faktyczny" / „wszystkie agregaty sprawne" |

**Wynik (panel prawy, odświeżany na żywo):**
- nagłówek: liczba mieszkańców bez usług, liczba obiektów wtórnych, liczba systemów IK,
- drzewo skutków (fala → system → obiekt) z czasem wystąpienia,
- lista „pierwsze 6 godzin" — co się stanie, zanim sztab się zbierze,
- przycisk **Zapisz jako scenariusz ćwiczebny**.

**Akcje:** `Zapisz scenariusz`, `Eksportuj kartę skutków (PDF)`, `Wyślij do wojewody`.

---

## Ekran 2 — „Obraz bieżący"

| Element | Zawartość |
|---|---|
| Mapa | obiekty w stanie `down` / `degraded`, kolor wg systemu IK |
| Lista priorytetowa | obiekty K1 niedziałające, sortowane wg `population_served` |
| Kolejka paliwowa | wynik `FuelRunout(8.0)` z licznikiem godzin do wyczerpania |
| Prognoza | wynik `CascadeForecast(24.0)`: kto padnie następny i za ile godzin |

**Akcje:** `Utwórz zapotrzebowanie na paliwo`, `Oznacz jako obsłużone`, `Przekaż do CZK`.

---

## Ekran 3 — „Meldunek operatora IK" (write-back)

Ekran dla operatora infrastruktury krytycznej — realizacja dwustronnej wymiany informacji z SPO-10.

| Pole | Typ | Walidacja |
|---|---|---|
| Obiekt | lista (ograniczona rolą RLS do obiektów operatora) | wymagane |
| Rodzaj zdarzenia | lista słownikowa | wymagane |
| Stan obiektu | operational / degraded / down | wymagane |
| Zasilanie rezerwowe | tak / nie + godziny paliwa | wymagane, gdy stan ≠ operational |
| Przewidywany czas przywrócenia | liczba godzin | wymagane, gdy stan = down |
| Potrzebne wsparcie | wielokrotny wybór | paliwo, pompy, transport, ochrona, łączność |
| Opis | tekst (do 1000 znaków) | opcjonalne |
| Załącznik | zdjęcie / dokument | opcjonalne |

**Zapis:** tabela `ci_operator_report_writeback` w Lakehouse + zdarzenie do Eventstream, dzięki
czemu meldunek natychmiast zmienia obraz bieżący i prognozę kaskady.

**Tryb offline:** formularz działa bez łączności i kolejkuje meldunki. To nie jest ozdoba —
w scenariuszu, w którym pada łączność, operator z zalanego obiektu ma najgorsze warunki pracy
w całym systemie.

---

## Ekran 4 — „Rejestr IK i współpraca (SPO-10)"

| Element | Zawartość |
|---|---|
| Karta obiektu | dane techniczne, klasa krytyczności, indeks kaskadowy, ekspozycja na Z01–Z20 |
| Współpraca | status planu ochrony, umowa o wymianie danych, punkt kontaktowy, data ostatniego testu |
| Historia | meldunki, awarie, ćwiczenia |
| Luki | czerwone znaczniki: brak umowy, brak kontaktu, plan nieaktualny, obiekt poza rejestrem |

**Akcje:** `Zainicjuj test kontaktu`, `Zgłoś wniosek o wpis do rejestru IK`, `Zaplanuj ćwiczenie`.

---

## Ekran 5 — „Plan wzmocnień"

Ekran dla decydenta budżetowego, nie dla dyżurnego.

| Element | Zawartość |
|---|---|
| Warianty | porównanie BAZOWY / A / B / C z liczbą uratowanych obiektów i mieszkańców |
| Lista inwestycji | obiekty z `whatif_marginal_value.csv`, sortowane wg liczby uratowanych obiektów |
| Koszyk | użytkownik wybiera obiekty i widzi łączny efekt |
| Zatwierdzenie | podpis decydenta + uzasadnienie |

**Zapis:** `hardening_plan_writeback` — obiekt, decyzja, uzasadnienie, data, osoba.
To jest jednocześnie ślad audytowy: gdy zdarzenie wystąpi, wiadomo, kto co wiedział i kiedy.

---

## Role i uprawnienia

| Rola | Ekrany | Ograniczenia |
|---|---|---|
| Dyżurny RCB | 1, 2, 4 | pełny obraz krajowy |
| Wojewódzkie CZK | 1, 2, 3, 4 | własne województwo |
| Operator IK | 3, 4 (tylko własne obiekty) | brak dostępu do pełnego grafu zależności |
| Decydent | 1, 5 | bez danych operacyjnych obiektu |
| Audytor | podgląd wszystkich write-backów | tylko odczyt |

Ograniczenie roli operatora jest świadome i wynika z ryzyka: pełna mapa zależności krajowej
infrastruktury krytycznej jest informacją, której nie udostępnia się szeroko.

## Zasady projektowe

1. **Najpierw skutek, potem dane.** Pierwszy ekran nie pokazuje tabeli obiektów, tylko odpowiedź na pytanie „co się stanie".
2. **Każdy ekran kończy się akcją.** Ekran bez przycisku zapisu jest raportem, nie aplikacją.
3. **Model nie decyduje.** Każda rekomendacja ma widoczne uzasadnienie i możliwość odrzucenia z komentarzem.
4. **Offline jest wymogiem, nie opcją.** Scenariusz zakłada utratę łączności i zasilania.
