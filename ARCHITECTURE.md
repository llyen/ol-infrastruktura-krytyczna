# Architektura rozwiązania

## Założenie operacyjne

Scenariusz łączy dwie zupełnie różne potrzeby czasowe. Pierwsza to obraz bieżący: który obiekt
infrastruktury krytycznej właśnie przestał działać i ile paliwa zostało w jego agregacie — to
pytanie sekundowe. Druga to przewidywanie: kto padnie za sześć godzin i czy zdarzenie wyjdzie
poza jeden resort — to pytanie wymagające przeliczenia grafu 2106 obiektów i 6552 zależności.
Architektura rozdziela te dwie warstwy celowo, bo próba obsłużenia obu jednym narzędziem
kończy się albo wolnym dashboardem, albo płytką analizą.

## Warstwa danych wsadowych — Lakehouse

Lakehouse przechowuje rejestr obiektów IK, graf zależności, ekspozycję na zagrożenia Z01–Z20 oraz
rejestr współpracy z operatorami w trybie SPO-10. To dane referencyjne: zmieniają się rzadko, ale
wymagają wersjonowania, lineage i jakości. Zmiana w grafie zależności jest zdarzeniem
organizacyjnym — ktoś zgłosił nową zależność albo ćwiczenie wykazało zależność, o której nie
wiedziano. Delta pozwala pokazać ten graf sprzed pół roku i porównać, co się zmieniło. Dla
rejestru IK ma to znaczenie nie techniczne, lecz dowodowe.

## Warstwa real-time — Eventstream i Eventhouse

Eventstream przyjmuje trzy strumienie: telemetrię stanu obiektów, meldunki operatorów IK oraz
odczyty wodowskazów. Eventhouse jest właściwy dla tej warstwy, bo wszystkie pytania dyżurnego są
pytaniami o okno czasowe: „ostatni status obiektu", „przyrost awarii w ostatnich dwóch
godzinach", „które agregaty zejdą poniżej sześciu godzin paliwa", „czy awarie w systemie
wodociągowym pojawiły się po awariach energetycznych i w jakim odstępie". Widok materializowany
`CiNodeCurrent` sprowadza 659 tysięcy zdarzeń do jednego wiersza na obiekt, dzięki czemu kafle
dashboardu odpowiadają w sekundach niezależnie od długości historii.

Funkcja `CascadeForecast` jest tu świadomym kompromisem: to uproszczona propagacja jednego kroku
wykonana w KQL, żeby dyżurny dostał odpowiedź „kto padnie następny" bez czekania na notatnik.
Pełna propagacja wielofalowa pozostaje w warstwie analitycznej.

## Warstwa analityczna — notebooki

Notatniki wykonują obliczenia, których nie da się i nie należy robić przy każdym odświeżeniu
raportu. Notatnik 03 uruchamia pełną symulację kaskady osobno dla każdego z 2106 obiektów, żeby
zbudować ranking krytyczności kaskadowej. To jest kosztowne, ale wykonywane raz na dobę albo po
zmianie w grafie — a nie przy każdym kliknięciu.

Silnik (`cascade_engine.py`) jest wydzielony do osobnego modułu z trzech powodów. Po pierwsze,
używają go trzy notatniki i duplikacja logiki w tak wrażliwym obszarze byłaby błędem. Po drugie,
model musi być audytowalny — decydent ma prawo zapytać, dlaczego system twierdzi, że woda
przestanie płynąć za sześć godzin, a odpowiedź musi mieścić się na jednej stronie kodu. Po
trzecie, silnik jest testowalny w oderwaniu od Fabric.

Propagacja jest realizowana kolejką priorytetową po czasie, a nie przeszukiwaniem wszerz. Ma to
znaczenie merytoryczne: skutki nie występują w kolejności „odległości w grafie", tylko w
kolejności czasu. Obiekt oddalony o trzy kroki, ale bez zasilania rezerwowego, przestanie działać
wcześniej niż sąsiad z agregatem na czterdzieści osiem godzin. Kolejność zdarzeń w symulacji musi
odpowiadać kolejności, w jakiej zdarzenia dotrą do sztabu.

## Warstwa decyzyjna — Power BI i Real-Time Dashboard

Podział jest ten sam co w pozostałych repozytoriach programu i wynika z różnych cykli decyzyjnych.
Real-Time Dashboard służy dyżurnemu: jedenaście kafli, obraz bieżący, prognoza dwudziestoczterogodzinna,
brak narracji. Raport Power BI służy odprawie i decyzji budżetowej: sześć stron, z których każda
kończy się wnioskiem, oraz drzewo skutków, które pozwala pokazać kaskadę osobie widzącej temat
pierwszy raz.

Kluczowym elementem modelu semantycznego jest podwójna rola tabeli obiektów wobec tabeli
zależności — ten sam obiekt jest raz dostawcą, raz odbiorcą. Bez relacji nieaktywnej i
`USERELATIONSHIP` nie da się w jednym raporcie zadać pytania „na kogo ten obiekt wpływa" i „od
kogo ten obiekt zależy".

## Warstwa działania — Fabric App, Activator, Data Agent

Aplikacja zamyka pętlę write-backu w dwóch miejscach. Operator IK raportuje stan obiektu, co
natychmiast zmienia obraz bieżący i prognozę. Decydent zatwierdza plan wzmocnień, co zostaje
zapisane wraz z uzasadnieniem i datą — i staje się śladem audytowym na wypadek, gdyby zdarzenie
rzeczywiście wystąpiło.

Activator jest skonfigurowany wokół jednej zasady: alarmuje o kaskadzie, nie o awarii. Alert
o pojedynczej awarii obiektu jest szumem, bo operator wie o niej pierwszy. Wartością jest sygnał
o skutku drugiego i trzeciego rzędu, którego nie widzi nikt patrzący wyłącznie na swój system.

Data Agent ma jawnie zdefiniowane granice — nie ujawnia współrzędnych obiektów K1, nie przypisuje
intencji sprawcy i nie podejmuje decyzji. Dla scenariusza dotyczącego infrastruktury krytycznej
te ograniczenia są częścią projektu, nie dodatkiem.

## Latencje i wolumeny

- Strumienie wejściowe: 659 178 zdarzeń telemetrii, 889 meldunków operatorów, 37 560 odczytów wodowskazów.
- Eventhouse: sekundy dla stanu bieżącego i prognozy jednokrokowej.
- Notatnik 02 (pełna kaskada powodziowa + scenariusz jednowęzłowy): kilkadziesiąt sekund.
- Notatnik 03 (2106 niezależnych symulacji): kilka minut — cykl dobowy lub po zmianie grafu.
- Power BI: import dla wyników symulacji, DirectQuery na KQL dla kafli stanu bieżącego.

## Co byłoby inaczej w prawdziwym wdrożeniu

**Integracje.** Dane o stanie obiektów pochodziłyby od operatorów IK na podstawie umów zawartych
w trybie SPO-10, dane hydrologiczne z IMGW, dane energetyczne od OSD i operatora przesyłowego.
Kluczową trudnością nie jest technika, lecz to, że część operatorów to podmioty prywatne, dla
których udostępnienie danych o własnej infrastrukturze jest ryzykiem biznesowym i wymaga podstawy
prawnej oraz gwarancji ochrony.

**Kompletność grafu.** Największym problemem realnego wdrożenia byłoby zbudowanie samego grafu.
Zależności nie są nigdzie spisane w jednym miejscu, a te zadeklarowane bywają nieaktualne.
Realistyczna droga prowadzi przez ćwiczenia: każde ćwiczenie ujawnia zależności, o których nie
wiedziano, i powinno kończyć się aktualizacją grafu. W danych demonstracyjnych odzwierciedla to
pole `verified_in_exercise`.

**Bezpieczeństwo i klasyfikacja.** Kompletna mapa zależności infrastruktury krytycznej państwa
jest informacją o wysokiej wartości dla przeciwnika. Wymagane byłyby: klasyfikacja informacji,
Private Link, Managed Identity, Key Vault, etykiety Purview, RLS ograniczające operatorów do
własnych obiektów, pełny audyt dostępu i procedura dostępu awaryjnego. Model, który pokazuje,
gdzie uderzyć, żeby wyrządzić największą szkodę, wymaga ochrony proporcjonalnej do tej wiedzy.

**Ciągłość działania.** System analizujący awarie infrastruktury musi działać, gdy ta
infrastruktura zawodzi. Oznacza to redundancję regionów, łącza awaryjne, offline cache dla
wojewódzkich CZK, eksport paczek PDF/CSV przed utratą łączności, zasilanie zapasowe stanowisk
dyżurnych i regularne ćwiczenia przełączenia w tryb ręczny.

**Governance.** Potrzebne byłyby: właściciel grafu, procedura zgłaszania i weryfikacji
zależności, cykl przeglądu parametrów modelu, walidacja rekomendacji przez ekspertów dziedzinowych
oraz jasna zasada, że wynik symulacji jest przesłanką, a nie decyzją.

## Granice odpowiedzialności komponentów

Eventstream dostarcza zdarzenia i nie interpretuje ich. Eventhouse odpowiada na pytania o stan
i wykrywa korelacje krótkookresowe. Notatniki tworzą model przewidywany i rankingi. Power BI
tłumaczy sytuację decydentowi. Aplikacja zapisuje meldunki i decyzje. Activator budzi człowieka,
gdy zdarzenie przestaje być awarią. Data Agent odpowiada na pytania w granicach swojej instrukcji.
Decyzję o eskalacji, ewakuacji czy uruchomieniu rezerw podejmuje wyłącznie organ do tego
uprawniony.

## Odporność organizacyjna

Architektura wymaga odpowiednika proceduralnego. Trzeba ustalić, kto aktualizuje graf zależności
i w jakim trybie, kto ma prawo uruchomić symulację ćwiczebną na danych produkcyjnych, kto odbiera
alert o kaskadzie w nocy, kto potwierdza ostatni poprawny snapshot przy utracie łączności i kto
rozstrzyga, gdy model wskazuje priorytet sprzeczny z oceną doświadczonego dyżurnego. Bez tych
ustaleń nawet poprawnie działający system pozostaje ciekawostką analityczną.
