# Miary DAX

Nazwy miar po polsku (widoczne dla decydenta), nazwy kolumn i tabel po angielsku.

## 1. Obraz bieżący

```dax
Obiekty IK = COUNTROWS(DimNode)

Obiekty niedziałające =
CALCULATE(DISTINCTCOUNT(FactNodeStatus[node_id]), FactNodeStatus[status] = "down")

Dostępność IK % =
VAR Total = [Obiekty IK]
RETURN IF(Total = 0, BLANK(), DIVIDE(Total - [Obiekty niedziałające], Total) * 100)

Obiekty na zasilaniu rezerwowym =
CALCULATE(DISTINCTCOUNT(FactNodeStatus[node_id]), FactNodeStatus[on_backup_power] = TRUE())

Godziny paliwa — mediana =
MEDIANX(
    FILTER(FactNodeStatus, FactNodeStatus[on_backup_power] = TRUE()),
    FactNodeStatus[backup_fuel_hours_left]
)

Obiekty K1 niedziałające =
CALCULATE([Obiekty niedziałające], DimNode[criticality_class] = "K1")
```

## 2. Kaskada — skutki wtórne

```dax
Obiekty w kaskadzie = COUNTROWS(FactCascadeTimeline)

Skutki wtórne = CALCULATE(COUNTROWS(FactCascadeTimeline), FactCascadeTimeline[wave] > 0)

Zdarzenia inicjujące = CALCULATE(COUNTROWS(FactCascadeTimeline), FactCascadeTimeline[wave] = 0)

-- Ile razy zdarzenie się "rozmnożyło". Poniżej 1,5 to awaria; powyżej 2,5 to efekt domina.
-- Mianownikiem są obiekty fali 0, czyli te, które faktycznie weszły do kaskady.
Współczynnik wzmocnienia = DIVIDE([Obiekty w kaskadzie], [Zdarzenia inicjujące])

Najgłębsza fala = MAX(FactCascadeTimeline[wave])

Pierwszy skutek wtórny (h) =
CALCULATE(MIN(FactCascadeTimeline[fail_hour]), FactCascadeTimeline[wave] > 0)

-- Czas, jaki realnie ma sztab, zanim zdarzenie przestanie być lokalne.
Okno reakcji (h) =
VAR Pierwszy = [Pierwszy skutek wtórny (h)]
VAR TrzeciRzad = CALCULATE(MIN(FactCascadeTimeline[fail_hour]), FactCascadeTimeline[wave] >= 3)
RETURN TrzeciRzad - Pierwszy

-- Uwaga: filtr nałożony na tabelę faktów NIE propaguje na DimGmina (relacja biegnie
-- w drugą stronę: DimNode -> DimGmina). Dlatego zbiór gmin budujemy z kolumny
-- w tabeli faktów, a populację dociągamy przez LOOKUPVALUE.
Ludność dotknięta =
VAR Gminy =
    CALCULATETABLE(
        VALUES(FactCascadeTimeline[gmina_code]),
        FactCascadeTimeline[system_group] IN {"energy", "water", "health"}
    )
RETURN
SUMX(Gminy, LOOKUPVALUE(DimGmina[population], DimGmina[gmina_code], FactCascadeTimeline[gmina_code]))

-- Gmina liczy się jako dotknięta tylko wtedy, gdy padła w niej usługa dla ludności.
-- Awaria obiektu finansowego czy administracyjnego nie odcina mieszkańca od wody.
Gminy dotknięte =
CALCULATE(
    DISTINCTCOUNT(FactCascadeTimeline[gmina_code]),
    FactCascadeTimeline[system_group] IN {"energy", "water", "health"}
)

Systemy IK dotknięte = DISTINCTCOUNT(FactCascadeTimeline[system_code])
```

## 3. Krytyczność kaskadowa i SPOF

```dax
Indeks kaskadowy = AVERAGE(FactCascadeCentrality[cascade_index])

Indeks kaskadowy — maks. = MAX(FactCascadeCentrality[cascade_index])

Pojedyncze punkty awarii =
CALCULATE(
    DISTINCTCOUNT(FactCascadeCentrality[node_id]),
    FILTER(FactCascadeCentrality,
        FactCascadeCentrality[cascade_systems] >= 3
        || FactCascadeCentrality[cascade_population] >= 100000)
)

SPOF bez umowy SPO-10 =
CALCULATE([Pojedyncze punkty awarii], FactSpo10[data_sharing_agreement] = 0)

SPOF poza rejestrem IK =
CALCULATE([Pojedyncze punkty awarii], DimNode[on_ci_register] = 0)

-- Najmocniejsze zdanie w raporcie: ile osób traci usługi przez awarię JEDNEGO obiektu.
Najgorszy pojedynczy obiekt — ludność = MAX(FactCascadeCentrality[cascade_population])

Zasięg międzysystemowy = MAX(FactCascadeCentrality[cascade_systems])
```

## 4. Zależności i redundancja

```dax
Zależności = COUNTROWS(FactDependency)

Zależności bez redundancji =
CALCULATE(COUNTROWS(FactDependency), FactDependency[redundancy_level] = "none")

Udział zależności bez redundancji % =
DIVIDE([Zależności bez redundancji], [Zależności]) * 100

Zależności międzywojewódzkie =
CALCULATE(COUNTROWS(FactDependency), FactDependency[cross_voivodeship] = 1)

-- Ile zależności nigdy nie zostało sprawdzonych w ćwiczeniu.
Zależności niesprawdzone w ćwiczeniu % =
DIVIDE(
    CALCULATE(COUNTROWS(FactDependency), FactDependency[verified_in_exercise] = 0),
    [Zależności]
) * 100

-- Miara po stronie "ofiary" — wymaga relacji nieaktywnej.
Dostawcy obiektu =
CALCULATE(
    DISTINCTCOUNT(FactDependency[source_node_id]),
    USERELATIONSHIP(DimNode[node_id], FactDependency[target_node_id])
)

Obiekty z jednym źródłem zasilania =
CALCULATE(DISTINCTCOUNT(DimNode[node_id]), DimNode[single_source_power] = 1)
```

## 5. What-if — wartość inwestycji

```dax
Redukcja skutków wtórnych p.p. =
VAR Baza = CALCULATE(MAX(FactWhatIf[nodes_failed_secondary]), FactWhatIf[variant] = "BAZOWY")
VAR Wariant = SELECTEDVALUE(FactWhatIf[nodes_failed_secondary])
RETURN DIVIDE(Baza - Wariant, Baza) * 100

Ludność uratowana =
VAR Baza = CALCULATE(MAX(FactWhatIf[affected_population]), FactWhatIf[variant] = "BAZOWY")
VAR Wariant = SELECTEDVALUE(FactWhatIf[affected_population])
RETURN Baza - Wariant

-- Prosty wskaźnik efektywności: ile obiektów ratuje jedna inwestycja punktowa.
Efektywność wariantu =
VAR Interwencje = SELECTEDVALUE(FactWhatIf[hardened_nodes]) + SELECTEDVALUE(FactWhatIf[new_feeds])
VAR Baza = CALCULATE(MAX(FactWhatIf[nodes_failed_secondary]), FactWhatIf[variant] = "BAZOWY")
VAR Wariant = SELECTEDVALUE(FactWhatIf[nodes_failed_secondary])
RETURN DIVIDE(Baza - Wariant, Interwencje)

Najlepsza pojedyncza inwestycja =
CONCATENATEX(
    TOPN(1, FactMarginalValue, FactMarginalValue[nodes_saved], DESC),
    FactMarginalValue[node_name] & " (" & FactMarginalValue[nodes_saved] & " obiektów)",
    ", "
)
```

## 6. Gotowość i governance (SPO-10)

```dax
Obiekty w rejestrze IK % =
DIVIDE(CALCULATE(COUNTROWS(DimNode), DimNode[on_ci_register] = 1), [Obiekty IK]) * 100

Umowy o wymianie danych % =
DIVIDE(CALCULATE(COUNTROWS(DimNode), DimNode[spo10_agreement] = 1), [Obiekty IK]) * 100

Plany ochrony nieaktualne =
CALCULATE(
    COUNTROWS(FactSpo10),
    FactSpo10[protection_plan_status] IN {"brak", "w aktualizacji"}
)

Responsywność operatora = AVERAGE(FactSpo10[responsiveness_score])

Dni od ostatniego ćwiczenia = AVERAGEX(DimNode, DATEDIFF(DimNode[last_exercise_date], TODAY(), DAY))

-- Luka, którą widać dopiero po połączeniu grafu z rejestrem współpracy.
Krytyczne obiekty bez kontaktu operacyjnego =
CALCULATE(
    COUNTROWS(DimNode),
    DimNode[criticality_class] = "K1",
    FactSpo10[contact_point_registered] = 0
)
```

## 7. Miary narracyjne (karty i tytuły dynamiczne)

```dax
Nagłówek kaskady =
VAR Ludzie = FORMAT([Ludność dotknięta], "#,0")
VAR Systemy = [Systemy IK dotknięte]
VAR Okno = FORMAT([Pierwszy skutek wtórny (h)], "0.0")
RETURN
"Bez usług: " & Ludzie & " mieszkańców • systemy IK: " & Systemy &
" • pierwszy skutek wtórny po " & Okno & " h"

Poziom eskalacji =
SWITCH(TRUE(),
    [Systemy IK dotknięte] >= 6 && [Obiekty K1 niedziałające] >= 5, "Przesłanka do RZZK (SPO-1)",
    [Systemy IK dotknięte] >= 4, "Poziom wojewody",
    [Systemy IK dotknięte] >= 2, "Poziom powiatu",
    "Poziom gminy"
)

Kolor stanu =
SWITCH(TRUE(),
    [Dostępność IK %] < 90, "#B91C1C",
    [Dostępność IK %] < 97, "#D97706",
    "#15803D"
)
```
