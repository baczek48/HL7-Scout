# HL7 Scout

> © 2026 Sebastian Bąk. Wszelkie prawa zastrzeżone.

Desktopowe narzędzie do analizy wiadomości **HL7 v2.x** — wklej ramkę, a aplikacja natychmiast rozbija ją na kolorowe kafelki segmentów z pełnym widokiem drzewa, tabeli i legendy opisującej każde pole.

---

## Instalacja (użytkownik końcowy)

1. Pobierz plik `HL7Scout.exe` z sekcji **Releases**.
2. Uruchom — brak instalatora, brak dodatkowych zależności.
3. System Windows może pokazać ostrzeżenie SmartScreen → kliknij **„Więcej informacji" → „Uruchom mimo to"**.

> Wymagany system: **Windows 10 / 11 (64-bit)**

---

## Funkcje

### Widok kafelkowy
- Po wklejeniu wiadomości HL7 każdy segment pojawia się jako osobny, kolorowy kafelek.
- Każdy typ segmentu ma unikalny kolor; wielokrotne wystąpienia tego samego segmentu (np. OBX) alternują między dwoma odcieniami dla łatwego odróżnienia.
- Zawartość każdego kafelka jest **edytowalna** bezpośrednio w miejscu.
- Przycisk **⎘** na kafelku kopiuje dany segment do schowka.
- Przycisk **Kopiuj ramkę** składa wszystkie segmenty z powrotem w poprawną ramkę HL7 (separator `\r`) i kopiuje do schowka.

### Drzewo
Hierarchiczna struktura: segment → pole → komponenty → powtórzenia.

### Tabela
Widok tabelaryczny: **Segment | Pole | Nazwa pola | Wartość** — wyświetlane tylko niepuste pola.

### Legenda
Kliknięcie segmentu lub pola wyświetla jego pełną nazwę i opis w języku polskim, oparty na dokumentacji **InfoMedica/AMMS HL7 v2.3**.

---

## Obsługiwane segmenty

`MSH` `EVN` `PID` `PD1` `NK1` `PV1` `PV2` `ORC` `OBR` `OBX` `NTE` `AL1` `DG1` `PR1`
`MSA` `ERR` `IN1` `IN2` `GT1` `SCH` `RXO` `RXE` `RXD` `RXA` `RXR` `BPO` `MRG`
oraz segmenty Z (niestandardowe, np. `ZAL`, `ZPI`).

---

## Skróty klawiszowe

| Skrót | Akcja |
|---|---|
| `Ctrl+V` | Wklej i sparsuj wiadomość HL7 |
| `Ctrl+Enter` | Parsuj ręcznie |

---

## Uruchamianie ze źródeł

```bash
pip install PyQt6
python main.py
```

---

## Budowanie .exe

```bash
build_exe.bat
```

Wynik: `dist\HL7Scout.exe`
"# HL7-Scout" 
