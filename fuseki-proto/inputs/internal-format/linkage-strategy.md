# DMP–SMS-Linkage-Strategie (CF2-005)

> **Status:** Entscheidung getroffen 2026-11-19. Dieses Fragment ist die
> ausführlichere Ausarbeitung der Entscheidung in Karte `CF2-005`
> (``05_Cards/CF2-005.md``) und die Grundlage für das exemplifizierte
> Instanz-Beispiel `linked-instance.example.json` (gleiches Verzeichnis).
>
> Die Karte `CF2-005` verlinkt auf dieses Fragment als das vollständigere
> Deliverable zur Verknüpfungs-Strategie.

---

## 1. Ausgangslage

Das EDO-Pivot-Format verbindet zwei Quellen:

- den **DMP** (maDMP, via RDMO) auf Ebene `Project`/`Dataset`
  (`dcat:Dataset`), und
- die **SMS** (Sensordatenbank, JSON:API) auf Ebene `Sensor`
  (`sosa:Sensor` + `MeasuredProperty`).

Beide sind bereits in das interne Format transformiert (CF2-003/CF2-004,
`trip.py`/`agnostic_trip.py`), aber sie stehen als **getrennte Knoten** da:
der `Sensor` wird als Standalone-Knoten emittiert und ist **nicht** mit dem
`Dataset` verknüpft. Die verknüpfende Aussage „Dieses Dataset wurde von diesem
Sensor erzeugt" fehlt im Pivot-Graphen.

Die zugrundeliegende Lücke ist im Gap-Register (`05_P05_S05_madmp-catalog-gaps.md`
#18, `dataset↔sensor link`) sowie im Transformations-Katalog
(`trafos/patterns.md`, **P30**/*N6*) und als finden **F12** (`trafos/README.md`
§13) dokumentiert.

---

## 2. Entscheidung

### 2.1 Wo — im internen Format, als First-Class-Relation (nicht NovaCrate, nicht Quell-Merge)

Die Verknüpfung lebt **im EDO-Pivot-Graphen** (internes Format), nicht in
NovaCrate und nicht durch ein Zusammenführen der Quelldokumente:

- Die Quelldokumente (maDMP-JSON / SMS-JSON:API) werden **nicht geändert oder
  gemerged** — DMP- und SMS-Provenienz bleiben getrennt (R7: *separate
  provenance starters*).
- Das interne Format trägt die Verknüpfung als **eigene RDF-Relation**.
  Beide Slots existieren bereits im Schema
  (`linkml/05_P05_S05_internal-format-schema.yaml`) und im Spezifikations-ERD
  (`internal-format/04_P04_S04_internal-format-spec.md`, §2):
  - `Dataset.prov:wasGeneratedBy → Sensor` (`Dataset.was_generated_by`),
  - `Sensor.sosa:observes → MeasuredProperty` (`Sensor.observes`).

### 2.2 Wie — Referenz (IRI/Blank-Node), nicht Merge, nicht Annotation

Die Verknüpfung ist eine **reifizierte Graphkante** (eine *Referenz* auf den
`Sensor`-Knoten), kein Kopieren von Sensor-Feldern in das Dataset und kein
textuelles Annotation:

- `Dataset prov:wasGeneratedBy Sensor` referenziert den Sensor-Knoten.
- Durch `Sensor sosa:observes` sind darüber die vollen `MeasuredProperty[]`
  erreichbar.

**Join-Key = Sensor-PID (Handle).** Dieser PID erscheint heute an zwei Stellen:

(a) maschinenlesbar als SMS `Sensor.edo:identifier`
    (`persistent_identifier` = `21.11157/9b6cdfb9-a4fb-4269-af04-1ef94588f5a8`,
    ID-Typ `handle`, S5), und
(b) nur als Freitext `PIDINST: …` im DMP `dataset/description` (Gap #18, P30).

Für eine **maschinenlesbare, transformierbare** Verknüpfung müsste also auch
die DMP-Seite des PIDs maschinenlesbar werden (siehe §4 / F12). Bis dahin wird
die Verknüpfung auf der EDO-Ebene **provisioniert** (siehe Beispiel) bzw.
manuell gesetzt.

### 2.3 Welche Metadaten werden verknüpft

- die **Dataset → Sensor-Kante** (`prov:wasGeneratedBy`), und
- durch `Sensor.sosa:observes` deren volle `MeasuredProperty[]`:
  gemessene Größe (SMS-CV-URI), Einheit (SMS-CV-URI), Messbereich (min/max),
  Genauigkeit, Auflösung, Sampling-Medium, Compartment, Aggregation-Typ und die
  SMS-CV-Referenz-URIs.
- Optional `Dataset.realized_as → MeasurementSeries`, das selbst
  `prov:wasGeneratedBy` den Sensor referenziert.

### 2.4 Bidirektional?

Ja im Schema — beide Richtungen existieren:
- `Dataset prov:wasGeneratedBy Sensor` (Datensatz-Seite), und
- `Sensor sosa:observes MeasuredProperty` (Sensor-Seite).

Heute wird nur die Sensor-Seite jemals emittiert (Standalone-Sensor-Knoten);
die Dataset-Seite wird nie befüllt (P30 loggt eine Regel, fügt aber kein
`prov:wasGeneratedBy`-Triple hinzu — verifiziert 2026-11-19).

---

## 3. Konsequenz für F12 (Kartierbarkeit)

Sobald der DMP den Sensor-PID **maschinenlesbar** trägt
(strukturierte Instrument-PID-Frage — neue Katalogfrage, CF2-001/002 — oder ein
ELN/auflösbarer PID), wird `prov:wasGeneratedBy` ein normaler
Slot-Derivations-Fall und **P30 wandert in die Map** (`linkml-map`). Bis dahin
ist die Verknüpfung auf der EDO-Ebene provisioniert bzw. manuell gesetzt und
bleibt außerhalb der Map (F12: offen → Entscheidung getroffen; siehe
`trafos/README.md` §13).

LinkML-Map-fähig bedeutet konkret (Vergleich zu CF2-004):
- F12 → Status „Resolved (Entscheidung getroffen)": die Linkage-Entscheidung
  (Referenz statt Merge) und der Join-Key (Sensor-PID) sind festgelegt; die
  eigentliche *Populierung* in die Map ist an eine Spezifikations-Revision
  (maschinenlesbarer PID im Katalog) gekoppelt.
- `patterns.md` P30/N6: als „provisioniert auf EDO-Ebene / manuell" markiert;
  Muster-Kategorie `existence-conditional` (sobald Quell-PID existiert).

---

## 4. Beispiel-Instanz

Siehe `linked-instance.example.json` (gleiches Verzeichnis). Es exemplifiziert
das **Weatherstation-Szenario** (device 67, Handle-PID
`21.11157/9b6cdfb9-a4fb-4269-af04-1ef94588f5a8`) mit allen fünf verfügbaren
gemessenen Größen (157 Windgeschwindigkeit, 158 Windrichtung, 159 Lufttemperatur,
160 relative Feuchte, 161 Luftdruck) — konsistent zum Spezifikations-§4-Beispiel
Dieses konkrete DMP-`measurement_02-13`-Dataset ist das **Grid-Expansion**-
Szenario (bnetza_vorhabenpunkte_bbplg_2) ohne PIDINST/Sensor; das
Weatherstation-Szenario wird deshalb als referenziertes Beispiel verwendet, weil
sein Sensor-PID dem SMS-Datensatz (device 67) maschinenlesbar entspricht.
