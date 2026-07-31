# Scenariusz demonstracji

**Czas:** 20–25 minut. **Odbiorca:** RCB, wojewódzkie i powiatowe centra zarządzania
kryzysowego, MSWiA, resorty odpowiedzialne za systemy IK, operatorzy infrastruktury krytycznej.

**Rola prowadzącego:** analityk wspierający wojewódzki zespół zarządzania kryzysowego.

**Sytuacja:** wrzesień 2026, dorzecze Odry i Nysy Kłodzkiej. Fala wezbraniowa przemieszcza się
przez województwa dolnośląskie i opolskie. D0 to moment przekroczenia stanów alarmowych.

Wszystkie dane są syntetyczne. **To trzeba powiedzieć na wstępie i na końcu.**

---

## Otwarcie (2 min) — postawienie problemu

> „Ustawa o zarządzaniu kryzysowym wymienia jedenaście systemów infrastruktury krytycznej.
> Każdy ma innego właściciela, innego regulatora, inny resort wiodący. Każdy z nich całkiem
> nieźle wie, co dzieje się u niego.
>
> Chciałbym zadać pytanie, na które dziś nie ma szybkiej odpowiedzi. Jeżeli **ta konkretna
> stacja energetyczna** przestanie dziś działać — kto straci wodę, który szpital przejdzie na
> agregat, ile godzin mamy do momentu, w którym zabraknie paliwa, i którzy wojewodowie muszą się
> o tym dowiedzieć?
>
> Dziś odpowiedź na to pytanie powstaje przez telefon i zajmuje godziny. Chcę pokazać, że może
> zajmować sekundy."

Nie pokazuj jeszcze ekranu. Postaw pytanie, dopiero potem otwórz narzędzie.

---

## Część 1 — Obraz sytuacji (4 min)

**Real-Time Dashboard `Infrastruktura krytyczna — obraz operacyjny`.**

Pokaż kolejno:

1. **Kafle stanu** — ile obiektów działa, ile w stanie degradacji, ile niedziałających. Fala
   powodziowa właśnie zaczyna dotykać pierwsze obiekty.
2. **Mapa** — obiekty IK na tle stref zalewowych i wodowskazów w stanie alarmowym.
3. **Kafel „na zasilaniu rezerwowym"** — z kolumną pozostałego paliwa.

> „Proszę zwrócić uwagę na ten kafel. To nie jest lista awarii. To lista obiektów, które
> **jeszcze działają** — ale mają licznik. Osiem szpitali pracuje na agregatach. Mediana
> pozostałej autonomii to około trzydziestu godzin. To jest informacja, której dziś nikt nie
> zbiera w jednym miejscu, bo każdy z tych szpitali raportuje gdzie indziej."

4. **Kafel meldunków operatorów** — wpływają zgłoszenia typu „zapotrzebowanie na pompy",
   „brak paliwa do agregatu". To realizacja procedury SPO-10 w postaci strumienia danych, nie
   telefonu.

---

## Część 2 — Wow moment: jedno kliknięcie (5 min)

**Raport Power BI, strona „Symulacja awarii".** Wybierz obiekt
**stacja NN 400/220 kV, województwo dolnośląskie** (`IK-01-00026`).

Zanim klikniesz — zapytaj salę:

> „To jest jedna stacja najwyższych napięć. Ile obiektów innych systemów przestanie działać,
> jeżeli ona zniknie? Proszę o liczbę."

Zwykle padają odpowiedzi rzędu kilku–kilkunastu. Kliknij.

> **538 453 mieszkańców bez zasilania**
> **104 obiekty wtórne w 6 falach**
> **9 szpitali — 8 przechodzi na agregaty, mediana autonomii 29,8 godziny, 1 nie ma rezerwy**
> **10 obiektów wodociągowych — woda przestaje płynąć po 0,9 godziny**
> **12 obiektów telekomunikacji, 10 obiektów ratownictwa**

Zatrzymaj się na jednej liczbie:

> „Zwrócę uwagę tylko na jedną pozycję. **Woda — pięćdziesiąt cztery minuty.** Nie sześć godzin,
> nie doba. Pięćdziesiąt cztery minuty od wyłączenia stacji energetycznej do momentu, w którym
> przepompownia przestaje tłoczyć. W tym czasie sztab kryzysowy zdąży się co najwyżej zebrać.
>
> To jest różnica między reagowaniem a wyprzedzaniem."

Pokaż **drzewo skutków** (`cascade_effect_tree`) — rozwiń dwa poziomy, żeby było widać, że
łańcuch prowadzi przez systemy należące do różnych resortów.

> „Proszę zauważyć, że ten łańcuch przechodzi przez cztery różne systemy IK, z czterema różnymi
> właścicielami. Żaden z nich nie widzi całości. Widzi ją dopiero ten model."

---

## Część 3 — Skala zdarzenia (3 min)

Przełącz na stronę **„Kaskada powodziowa"**.

> „To był jeden obiekt. A teraz zdarzenie rzeczywiste — powódź, która wyłącza 232 obiekty
> jednocześnie."

- **232 obiekty wyłączone przez wodę → 777 niedziałających. 545 z nich nie zostało zalanych.**
- Współczynnik wzmocnienia **3,35**.
- Pierwszy skutek wtórny po **33 minutach**, kaskada sięga **siódmej fali**.
- **200 gmin, ok. 2,63 mln mieszkańców** bez co najmniej jednej usługi.

> „To jest liczba, którą chciałbym, żeby państwo zapamiętali: **na każdy obiekt, który zalała
> woda, przypadają ponad dwa, które przestały działać z innego powodu.** Te dwa nie pojawią się
> w żadnym meldunku o powodzi. Pojawią się jako osobne awarie, w osobnych resortach, bez
> informacji, że mają wspólną przyczynę."

Pokaż wykres fal — 232, 169, 131, 105, 76, 48, 13, 3. Kaskada nie wygasa w drugiej fali.

Wskaż **132 zależności międzywojewódzkie**:

> „I jeszcze jedno. Sto trzydzieści dwie zależności w tym grafie przekraczają granicę
> województwa. Kompetencja wojewody kończy się na granicy. Awaria nie."

---

## Część 4 — Gdzie jest najsłabszy punkt (4 min)

Strona **„Punkty krytyczne"**. Pokaż ranking SPOF.

- 217 obiektów spełnia kryterium pojedynczego punktu awarii, 29 w kategorii „krytyczny".
- Najgroźniejszy: **642 162 mieszkańców, wszystkie 11 systemów IK**.

Przewiń do drugiej pozycji i zatrzymaj się:

> „Chcę pokazać coś, co jest dla mnie najważniejszym wynikiem tej analizy. Na drugim miejscu
> listy najgroźniejszych obiektów w kraju **nie stoi elektrownia ani stacja energetyczna. Stoi
> magazyn paliw.** Pół miliona mieszkańców, 130 obiektów wtórnych, wszystkie jedenaście systemów.
>
> Dlaczego? Bo kiedy zabraknie prądu, wszystko przechodzi na agregaty. A agregaty trzeba
> zatankować. Magazyn paliw nie jest infrastrukturą energetyczną w potocznym rozumieniu — jest
> infrastrukturą **wszystkiego pozostałego**.
>
> Tego wniosku nie da się uzyskać, analizując każdy system osobno. On powstaje wyłącznie wtedy,
> gdy się je połączy."

Pokaż luki governance: **67 obiektów SPOF bez umowy o wymianie danych, 46 poza rejestrem IK,
46 w strefie zalewowej**.

> „To jest lista zadań do wykonania jutro rano, bez żadnej inwestycji. Sześćdziesiąt siedem
> telefonów do wykonania i czterdzieści sześć wniosków o wpis do rejestru."

---

## Część 5 — Co warto zrobić (4 min)

Strona **„Warianty wzmocnienia"**.

> „Ostatnie pytanie — najtrudniejsze. Mamy ograniczony budżet. Co realnie zmniejszy skutki?
> Porównałem dwie interwencje na tym samym zdarzeniu powodziowym."

| Wariant | Interwencja | Skutki wtórne | Redukcja |
|---|---|---|---|
| BAZOWY | stan obecny | 545 | — |
| **A — autonomia** | agregat i paliwo na 72 h w 120 obiektach usługowych | **414** | **24,0%** |
| B — redundancja | drugie zasilanie dla 241 obiektów K1 | 521 | 4,4% |
| C — razem | A + B | 396 | 27,3% |

Zrób pauzę przed puentą:

> „Wariant B to inwestycja w linie zasilające — kosztowna, wieloletnia, wymagająca decyzji
> lokalizacyjnych. Wariant A to agregaty i paliwo — tańszy o rząd wielkości, do wdrożenia
> w jeden sezon.
>
> **Tańszy wariant daje pięć razy większy efekt.**
>
> Nie twierdzę, że to jest odpowiedź na każde pytanie. Twierdzę, że to jest pierwszy raz, kiedy
> na to pytanie w ogóle da się odpowiedzieć liczbą, a nie przekonaniem."

Pokaż tabelę wartości krańcowej:

> „A jeśli budżet wystarczy na dwadzieścia obiektów zamiast stu dwudziestu — to jest lista tych
> dwudziestu, uporządkowana według liczby uratowanych obiektów i mieszkańców. Z nazwiskiem
> operatora i informacją, czy mamy z nim podpisaną umowę."

---

## Część 6 — Domknięcie pętli (3 min)

**Fabric App — symulator kaskad.**

1. Operator IK melduje awarię obiektu przez formularz w aplikacji.
2. Obraz bieżący i prognoza aktualizują się natychmiast.
3. **Data Activator** wyzwala regułę — pokaż powiadomienie w Teams: alert dotyczy **kaskady**,
   nie pojedynczej awarii.
4. Decydent zatwierdza pozycję planu wzmocnień; zapis trafia do Lakehouse wraz z uzasadnieniem
   i datą.

**Data Agent** — zadaj na żywo pytanie głosem lub tekstem:

> „Które szpitale w województwie dolnośląskim stracą zasilanie w ciągu najbliższych sześciu
> godzin i ile mają paliwa?"

Zadaj też pytanie, na które agent **odmówi** odpowiedzi (dokładna lokalizacja obiektu K1):

> „To jest celowe. Model, który pokazuje, gdzie uderzyć, żeby wyrządzić największą szkodę, musi
> mieć granice. One są częścią projektu, nie dodatkiem do niego."

---

## Zamknięcie (1 min)

> „Podsumuję trzema zdaniami.
>
> Po pierwsze — kaskada jest realna i mierzalna: na każdy zalany obiekt przypadają dwa, które
> padły z innego powodu.
>
> Po drugie — najgroźniejszy punkt w systemie nie jest tam, gdzie się go spodziewamy. Magazyn
> paliw okazał się ważniejszy od elektrowni.
>
> Po trzecie — tańsza interwencja okazała się pięć razy skuteczniejsza od droższej. To jest
> argument budżetowy, którego dziś nie da się postawić.
>
> Wszystkie dane, które państwo widzieli, są syntetyczne. Mechanizm jest prawdziwy. Żeby go
> uruchomić, nie trzeba nowej platformy — trzeba grafu zależności. A ten powstaje w ćwiczeniach."

---

## Plan B

| Ryzyko | Reakcja |
|---|---|
| Brak dostępu do Fabric | prowadź demo na raporcie PBIX offline i wynikach z `datasets/derived/` |
| Strumień real-time nie płynie | `python simulate_realtime.py --dry-run` i pokaz na danych historycznych; dashboard operacyjny zastąp stroną „Kaskada powodziowa" |
| Pytanie o realne dane IK | „To repozytorium demonstracyjne. Wdrożenie produkcyjne wymaga klasyfikacji informacji, umów SPO-10 i podstawy prawnej — opisane w `ARCHITECTURE.md`" |
| Pytanie o wiarygodność modelu | pokaż `cascade_engine.py` — reguła mieści się na jednej stronie; podkreśl, że próg 0,5 i opóźnienia są parametrami planistycznymi do kalibracji z ekspertami |
| Pytanie „skąd weźmiemy graf" | to najważniejsze pytanie i należy je pochwalić: graf buduje się w ćwiczeniach, pole `verified_in_exercise` jest w modelu właśnie po to |
| Mało czasu (10 min) | części 2, 4 i 5 — jedno kliknięcie, magazyn paliw, agregaty vs linie |

## Czego nie robić

- Nie podawaj liczb ludności jako „ofiar" ani „poszkodowanych" — to liczba mieszkańców gmin,
  w których przestała działać co najmniej jedna usługa.
- Nie sugeruj, że model przewiduje sabotaż lub wskazuje sprawcę.
- Nie obiecuj, że wdrożenie sprowadza się do wgrania danych — najtrudniejszy jest graf zależności
  i porozumienia z operatorami.
