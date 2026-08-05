# Pulpit kaskad — Fabric App scenariusza „Infrastruktura krytyczna"

Aplikacja pokazuje, **co się stanie, gdy przestanie działać jeden obiekt**, i pozwala
sprawdzić, które wzmocnienia naprawdę zmniejszają skutki. Powstała dla scenariusza
demonstracyjnego `ol-infrastruktura-krytyczna`.

Dane są w całości syntetyczne. Obiekty, operatorzy i zależności to rekordy wygenerowane —
żaden nie odpowiada rzeczywistemu obiektowi infrastruktury.

## Ekrany

| Ścieżka | Ekran | Do czego służy |
|---|---|---|
| `/` | Symulacja awarii | Wskazujesz obiekt, ustawiasz horyzont i tryb — dostajesz zasięg skutków, drzewo propagacji i listę „pierwszych 6 godzin". Kończy się zapisem scenariusza ćwiczebnego. |
| `/obraz` | Obraz bieżący | Kaskada powodziowa odtwarzana godzina po godzinie: mapa, obiekty K1 poza pracą, kolejka paliwowa, prognoza na 12 h. Kończy się zgłoszeniem zapotrzebowania na paliwo. |
| `/meldunek` | Meldunek operatora | Formularz operatora IK z trybem terenowym. Kończy się złożeniem meldunku albo zapisem do kolejki synchronizacji. |
| `/rejestr` | Rejestr IK / SPO-10 | Karta obiektu, luki we współpracy wypisane słowami, ranking operatorów. Kończy się zainicjowaniem działania. |
| `/wzmocnienia` | Plan wzmocnień | Warianty BAZOWY/A/B/C, koszyk obiektów według wartości krańcowej, przeliczenie skutku. Kończy się zatwierdzeniem planu. |

## Role

| Rola | Widzi graf zależności | Może zapisywać | Zakres |
|---|---|---|---|
| RCB | tak | tak | kraj |
| wojewoda / WCZK | tak | tak | własne województwo |
| operator IK | **nie** | tak, tylko meldunki | własne obiekty |
| decydent | tak | tylko plan wzmocnień | kraj |
| audytor | tak | **nie** | kraj |

Operator IK jest świadomie wykluczony z pełnego grafu. Widzi skutki awarii własnych
obiektów, ale nie to, kto jeszcze zależy od tych samych dostawców — bo w rzeczywistości
też tego nie widzi.

## Jak liczone są skutki

Aplikacja **nie dostaje gotowych wyników**. Do przeglądarki trafia graf: 2106 węzłów
i 6552 krawędzie. Propagację liczy `src/data/cascade.ts` — wierny port
`../../cascade_engine.py`. Bez tego suwak horyzontu i przełącznik agregatów byłyby
atrapami, a wyliczenie 2106 kaskad na zapas dałoby plik nie do pobrania.

Reguły, których nie wolno zmienić bez zmiany silnika w Pythonie:

- węzeł pada, gdy suma `impactShare × edgeFactor` przekroczy próg 0,5;
- redundancja `full` tłumi wpływ do 0,40, `partial` do 0,90, `none` nie tłumi;
- **jeśli zapas autonomiczny jest dłuższy niż czas przywrócenia dostawcy, odbiorca nie
  pada wcale** — dzięki temu autonomia jest dźwignią inwestycyjną, a nie odroczeniem;
- ludność liczy się po gminach, nie przez sumowanie `population_served` — ten drugi
  sposób liczy tę samą osobę raz na każdy system i daje liczby większe niż ludność Polski.

Testy w `src/__tests__/model.test.ts` porównują wynik z metrykami z
`datasets/derived/cascade_summary.json`. Rozjazd portu i silnika psuje test, zanim
zdąży trafić na ekran.

## Uruchomienie

```powershell
npm install
python tools/build_scene.py     # public/data/scene.json, ok. 1,0 MB
npm run dev
```

Kontrola jakości:

```powershell
npm run test          # 46 testów
npm run lint
npm run build
python ..\..\..\_program\tools\audit_contrast.py    # ma dawać 0
```

## Budowa sceny

`tools/build_scene.py` składa `public/data/scene.json` ze zbiorów w `../../datasets`.
Scena jest zapisana kolumnowo — forma obiektowa dla 6552 krawędzi to kilkukrotnie
więcej bajtów na te same dane.

Skrypt **poprawia też współrzędne**: generator zbiorów rozrzuca obiekty losowym
odchyleniem wokół środka województwa i nie sprawdza, czy punkt został w regionie.
619 z 2106 węzłów wypadało poza własnym województwem, a 36 poza granicą kraju.
Korekta działa wyłącznie w warstwie prezentacji — wyniki symulacji nie zależą od
współrzędnych, więc żadna kotwica regresyjna się nie zmienia. Pilnuje tego
`src/__tests__/geography.test.ts`.

## Wygląd

Jasna paleta rządowa opisana w `_program/CONVENTIONS.md`, rozdział 7. Czerwień jest
sygnałem powagi, nie barwą marki. Skala powagi ma cztery rozróżnialne stopnie.
