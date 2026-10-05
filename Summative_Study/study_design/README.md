# Counterbalancing – SonoAdapt Summative Study (Interview / Mathe)

## 1. Design in Kürze

| Faktor | Stufen | Art |
|---|---|---|
| Scenario | I = Interview, M = Mathe/Rechen | within |
| System | Baseline-Earcon (E), Baseline-Speech (S), SonoAdapt (A) | within |
| Urgency | LOW (L), HIGH (H) | within |
| Message | L1–L6 / H1–H6 | Nuisance-Faktor, counterbalanced |

**12 Trials pro Person** = 2 Szenarien × 6 Bedingungen (LE, HE, LS, HS, LA, HA).

**Wichtige Eigenschaft:** 12 Trials = 6 LOW + 6 HIGH, und es gibt genau 6 LOW- und
6 HIGH-Messages → **jede Person sieht jede Message genau einmal**. Message ist damit
komplett innerhalb der Person balanciert.

## 2. Blockstruktur (6×6)

Pro Person wird **erst ein Szenario komplett durchgeführt** (6 Trials), dann das andere:

| Proband | Block 1 (Trials 1–6) | Block 2 (Trials 7–12) |
|---|---|---|
| Ungerade (1, 3, 5 …) | Interview | Mathe |
| Gerade (2, 4, 6 …) | Mathe | Interview |

Begründung: Kognitive Task-Switching-Kosten vermeiden, Immersion sicherstellen,
Carry-over zwischen Szenarien minimieren.

## 3. Wie counterbalanced wird (3 Ebenen)

1. **Szenario-Reihenfolge** – 2 Permutationen (Interview-first / Mathe-first),
   alternierend nach gerader/ungerader Teilnehmernummer.

2. **Bedingungs-Reihenfolge innerhalb eines Szenario-Blocks** – Williams-Square der
   Ordnung 6 (balanciert für Position *und* First-Order-Carry-over):

   Die 6 Bedingungen (LE, HE, LS, HS, LA, HA entspricht Index 1–6):

   | Zeile | T1 | T2 | T3 | T4 | T5 | T6 |
   |---|---|---|---|---|---|---|
   | W1 | LE | HE | HA | LS | HS | LA |
   | W2 | HE | LS | LE | HA | LA | HS |
   | W3 | LS | HA | HE | LA | LE | HS |  ← *korr., alle 30 Paare eindeutig*
   | W4 | HA | LA | LS | HS | HE | LE |
   | W5 | LA | HS | HA | LE | LS | HE |
   | W6 | HS | LE | LA | HE | HA | LS |

   Jede Person bekommt **zwei verschiedene Zeilen** (Block 1 und Block 2 haben
   immer einen Offset von +3, also Paare 0↔3, 1↔4, 2↔5).

3. **Message-Zuweisung** – die 6 LOW-Slots einer Person entsprechen den 6 Zellen
   (Scenario I/M) × (System E/S/X). Ein zweiter Williams-Square der Ordnung 6
   mappt Messages auf diese Zellen, entkoppelt vom Bedingungs-Index.

## 4. Stichprobengröße

Volle Balance bei **Vielfachen von 6** (kgV von 2 und 6).
→ Empfehlung: **N = 12** anpeilen, sonst 24.
Die Tabelle enthält 24 Zeilen; nimm Teilnehmer 1..N der Reihe nach.

Erreichte Balance (geprüft für N = 6, 12, 24):

- Scenario × Blockposition: exakt gleichverteilt
- Bedingung × Position im Block: exakt gleichverteilt
- Bedingung × globaler Trial (1–12): exakt gleichverteilt
- Message × System: exakt gleichverteilt
- Message × Scenario: exakt gleichverteilt
- Alle 30 geordneten Bedingungspaare (Carry-over) gleich häufig
- Keine Person hat zweimal dieselbe Bedingungs-Sequenz

## 5. Der Key / Code (das, was du in Qualtrics eintippst)

4 Zeichen, **selbst-erklärend**:

```
<Scenario I|M><System E|S|X><Urgency L|H><Message 1..6>
```

| Zeichen | Bedeutung |
|---|---|
| `I` / `M` | Interview / Mathe |
| `E` | Baseline-Earcon |
| `S` | Baseline-Speech |
| `X` | SonoAdapt |
| `L` / `H` | LOW / HIGH urgency |
| `1`–`6` | Message-Nummer |

Beispiele:

- `IEL3` = Interview, Baseline-Earcon, LOW, Message L3 (Anna – Doku)
- `MSH4` = Mathe, Baseline-Speech, HIGH, Message H4 (Paul – Schlüssel)
- `IXH1` = Interview, SonoAdapt, HIGH, Message H1 (Sarah – Fahrradunfall)

### Qualtrics-Setup

1. **Einmal am Anfang:** Text-Entry-Frage `ParticipantID` (1–24) → als Embedded Data speichern.
2. **12 identische Blöcke** in fixer Reihenfolge (Block 1 … Block 12), Randomizer aus.
   Jeder Block = 1 Text-Entry-Frage `CODE` + deine Likert-Items.
3. **Validation** auf der CODE-Frage: Content Type → *Custom Validation* /
   RegEx: `^[IM][ESX][LH][1-6]$` → verhindert Vertipper.

Beim Auswerten splittest du `CODE` in 4 Spalten (in R: `substr`) und hast sofort
Scenario, System, Urgency, Message. Die `ParticipantID` + Blocknummer dienen als
Gegenprobe gegen `design_long.csv`.

> **Tipp:** Der Code ist redundant zu ParticipantID + Blocknummer. Wenn beides nicht
> zusammenpasst, weißt du, dass im Ablauf etwas verrutscht ist.

## 6. Dateien

| Datei | Inhalt |
|---|---|
| `generate_design.py` | Generator inkl. Balance-Checks (`python generate_design.py`) |
| `make_excel.py` | Excel-Builder (`pip install openpyxl` → `python make_excel.py`) |
| `design_wide.csv` | **Schnelle Nachschlagetabelle**: 1 Zeile pro Person, Spalten B01–B12 |
| `design_long.csv` | 1 Zeile pro Trial, alle Spalten (für Analyse / Merge mit Qualtrics) |
| `runsheets.md` | Pro Person eine Tabelle mit Block, Code, Szenario, System, Urgency und vollem Message-Text |
| `study_design.xlsx` | Formatiertes Excel-Workbook (Lookup / Trials / Run Cards / Legend) |

CSVs sind mit `;` getrennt und UTF-8-BOM → öffnen direkt korrekt in deutschem Excel.

## 7. Nachschlagetabelle (Teilnehmer 1–12)

> 🟠 = Interview-Block (B01–B06 bei ungeraden, B07–B12 bei geraden), 🔵 = Mathe-Block.
> Vollständige Tabelle (P 1–24) in `design_wide.csv` und `study_design.xlsx` → Sheet "Lookup".

| P | B01 | B02 | B03 | B04 | B05 | B06 | B07 | B08 | B09 | B10 | B11 | B12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | IEL1 | IEH4 | IXH3 | ISL2 | IXL6 | ISH5 | MSH2 | MXL4 | MSL5 | MXH1 | MEH6 | MEL3 |
| 2 | MEH1 | MSL6 | MEL4 | MSH3 | MXH2 | MXL5 | IXL1 | IXH4 | ISH6 | IEL2 | ISL3 | IEH5 |
| 3 | ISL4 | ISH1 | IEH6 | IXL2 | IEL3 | IXH5 | MXH3 | MEL5 | MXL6 | MEH2 | MSH4 | MSL1 |
| 4 | MSH5 | MXL1 | MSL2 | MXH4 | MEH3 | MEL6 | IEL4 | IEH1 | IXH6 | ISL5 | IXL3 | ISH2 |
| 5 | IXL4 | IXH1 | ISH3 | IEL5 | ISL6 | IEH2 | MEH4 | MSL3 | MEL1 | MSH6 | MXH5 | MXL2 |
| 6 | MXH6 | MEL2 | MXL3 | MEH5 | MSH1 | MSL4 | ISL1 | ISH4 | IEH3 | IXL5 | IEL6 | IXH2 |
| 7 | IEL2 | IEH5 | IXH4 | ISL3 | IXL1 | ISH6 | MSH3 | MXL5 | MSL6 | MXH2 | MEH1 | MEL4 |
| 8 | MEH2 | MSL1 | MEL5 | MSH4 | MXH3 | MXL6 | IXL2 | IXH5 | ISH1 | IEL3 | ISL4 | IEH6 |
| 9 | ISL5 | ISH2 | IEH1 | IXL3 | IEL4 | IXH6 | MXH4 | MEL6 | MXL1 | MEH3 | MSH5 | MSL2 |
| 10 | MSH6 | MXL2 | MSL3 | MXH5 | MEH4 | MEL1 | IEL5 | IEH2 | IXH1 | ISL6 | IXL4 | ISH3 |
| 11 | IXL5 | IXH2 | ISH4 | IEL6 | ISL1 | IEH3 | MEH5 | MSL4 | MEL2 | MSH1 | MXH6 | MXL3 |
| 12 | MXH1 | MEL3 | MXL4 | MEH6 | MSH2 | MSL5 | ISL2 | ISH5 | IEH4 | IXL6 | IEL1 | IXH3 |

Teilnehmer 13–24 stehen in `design_wide.csv`.

## 8. Message-Legende

| ID | LOW | ID | HIGH |
|---|---|---|---|
| L1 | Lilly – short walk after work | H1 | Sarah – bike accident, call me |
| L2 | Max – pasta for dinner | H2 | Leo – fire alarm in your apartment |
| L3 | Anna – watched a documentary | H3 | Laura – forgot to turn the stove off |
| L4 | Ben – took the bus to work | H4 | Paul – forgot my keys, open the door |
| L5 | Emma – stopped by a bakery | H5 | Sophie – outside your building |
| L6 | Tom – finished a book | H6 | David – left wallet on the train |
