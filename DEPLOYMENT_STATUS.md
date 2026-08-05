# Stan wdrożenia — Scenariusz 7: Infrastruktura krytyczna i kaskady

Dane w całości syntetyczne. Środowisko demonstracyjne, nie produkcyjne.

## 1. Środowisko

| Element | Wartość |
|---|---|
| Obszar roboczy | `OL-ZK-Demo-IK` — `8eed174a-6298-4867-929c-bc12e129cff7` |
| Pojemność | `fcdemo` (F8, West Europe, `rg-fabric-cap-demo`) |
| Lakehouse | `f4822651-4e59-4973-b5cb-0ecd389d473a` |
| Eventhouse | `68f4bbd0-1297-425a-a49b-756051314f04` |
| Baza KQL | `609cd47b-33f1-4b12-9c56-57c801ef40df` |
| Model semantyczny | `7666aa21-0659-499b-ab05-d600080b218a` |
| Raport | `ff7a222f-8bac-446d-ac00-18e8d0499df8` |
| Pulpit czasu rzeczywistego | `aa5e0ad3-3962-4aa1-9fbf-b6165994cae2` |

Kolejność wdrażania warstwy danych opisuje `SETUP_FABRIC.md`.

## 2. Fabric App „Symulator kaskad IK" — wdrożona

| Element | Wartość |
|---|---|
| Adres | https://grand-coast-b2b8efb506-westeurope.webapp.fabricapps.net |
| Rayfin Item ID | `df073ae4-0d1f-4727-92e8-14913c13bdc1` |
| Wdrożenie | `deploy-20260805125120-b29a0f18` |
| Kod | `fabric-app\pulpit-kaskad` |

Pięć ekranów: symulacja „co jeśli", obraz bieżący powodzi, meldunek operatora IK,
rejestr obiektów i luk SPO-10, plan wzmocnień z wartością krańcową. Encje zapisu
zaaplikowane (`rayfin up db apply --force`), adres dopisany do `allowedRedirectUris`.
Szczegóły i sposób uruchomienia — `fabric-app\pulpit-kaskad\README.md`.

Sprawdzone automatycznie: budowanie, 46 testów (w tym kotwice regresyjne wobec
`cascade_summary.json`), audyt kontrastu WCAG, odpowiedź serwisu (HTTP 200),
serwowanie sceny (1,04 MB) i jasnej palety rządowej w CSS.

**Do przeklikania przez człowieka w portalu:** logowanie brokerem Fabric i zapis
wiersza przez formularz. Ścieżka zapisu nie została wykonana ręcznie od końca do końca.

## 3. Zgodność symulatora w aplikacji z silnikiem w Pythonie

`fabric-app\pulpit-kaskad\src\data\cascade.ts` jest portem `cascade_engine.py`.
Testy kotwiczące porównują wynik portu z `datasets\derived\cascade_summary.json`:
liczba obiektów wtórnych, największa fala, 538 453 osoby bez zasilania, godzina
pierwszego skutku wtórnego oraz najgorszy pojedynczy obiekt. Horyzont symulacji
to 240 h — tak samo jak w notatnikach 02, 03 i 04.

## 4. Napotkane problemy i rozwiązania

| Problem | Rozwiązanie |
|---|---|
| 619 z 2106 obiektów miało współrzędne w cudzym województwie, 36 poza granicą kraju | `tools\build_scene.py` przyciąga punkt do wnętrza własnego województwa (`snap_into`); korekta wyłącznie prezentacyjna, nie wchodzi do propagacji, więc żadna liczba w scenariuszu się nie zmieniła. Pilnuje tego `src\__tests__\geography.test.ts` |
| `rayfin up` bez kontekstu obszaru roboczego | Podawać `--workspace-id 8eed174a-6298-4867-929c-bc12e129cff7` |
| Pojemność `fcdemo` usypia się sama | Przed wdrożeniem `deploy\ensure_capacity.ps1` |
| `tsc -b --noEmit` kończy się TS6310 | Używać samego `tsc -b` |

## 5. Kroki pozostające do wykonania

- [ ] Przeklikanie logowania i zapisu wiersza w portalu przez człowieka
- [ ] Porównanie linii bazowej liczonej na ekranie planu wzmocnień z wierszem
      BAZOWY tabeli wariantów (777 obiektów) — klatki mają rozdzielczość godzinową,
      możliwa rozbieżność o kilka obiektów
