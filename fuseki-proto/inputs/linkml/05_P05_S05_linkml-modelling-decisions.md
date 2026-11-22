# 05_P05_S05 — LinkML-Modellentscheidungen (CF1-007)

Status: ✅
Datum: 2026-11-19
Kontext: CF1-007 „LinkML-Schemas für DMP, SMS und internes Format" — grobes Prinzip, keine vollständige RDA-Spezifikation. Ziel ist, dass die späteren Transformationen (CF2-003) verständlich und prüfbar sind.

## 1. Drei eigenständige Schemas

| Datei | Klassen / Slots / Enums | Quelle |
|---|---|---|
| `05_P05_S05_madmp-schema.yaml` | 10 / 41 / 4 | maDMP-Export-Mapping (`scripts/dmp/03_P03_S03_madmp-export.mapping.yaml`) |
| `05_P05_S05_sms-schema.yaml` | 2 / 39 / 0 | SMS device 67 + device property 159 (`scripts/sms/`) |
| `05_P05_S05_internal-format-schema.yaml` | 14 / 57 / 4 | Internes-Format-Spec v0.2 (`scripts/internal-format/04_P04_S04_internal-format-spec.md`) |

Entscheidungen:

- **Kein `imports` zwischen den drei Schemas.** Jedes Schema steht allein und beschreibt seine eigene Quelle bzw. das Ziel. Die Abbildung DMP → internes Format und SMS → internes Format ist **keine Schema-Vererbung**, sondern passiert in den Transformationen (CF2-003). Damit bleiben die Schemas unabhängig austauschbar (z. B. wenn CF2-001 einen neuen RDMO-Katalog liefert).
- Die Schemas sind absichtlich **grob**: Pflichtfelder nur dort, wo die Quelle sie garantiert liefert; optionale Felder bleiben optional. Verfeinerung ist Teil von CF2.

## 2. IRI-Politik (lautet die offene Frage aus CF1-006 §6)

- `edo:` = `https://w3id.org/edo/terms/` — **Platzhalter**, echte IRI-Vergabe (w3id.org-Registrierung) ist Teil von CF2, nicht von CF1-007.
- Wiederverwendete Vokabulare stehen als Prefixes im Schema und werden pro Klasse/Slot über `class_uri` bzw. `mappings` fixiert: `dcterms`, `dcat`, `foaf`, `prov`, `time`, `sosa`, `linkml` (Typen), `xsd`.
- Eigene Klassen/Slots (`Project`-niveau, `Contribution`, `Cost`, `Identifier`, `Host`, `MeasurementSeries`, `SamplingPlan`, `edo:url`, `edo:dmpId` …) tragen `class_uri`/`mappings` auf `edo:`-IRIs.
- **Namenskonvention:** Die LinkML-Slot-Namen (`title`, `access_url`, `sampling_interval` …) sind die JSON-Feldnamen des internen Formats; die Vokabular-IRIs liegen in `mappings`. Ein generiertes JSON-Dokument benutzt Slot-Namen, keine IRIs — die Übersetzung Slot-Name ↔ IRI macht der JSON-LD-`@context` (CF2-003). Deshalb validiert das Beispiel aus Spec §4 (IRI-Schreibweise) **nicht** gegen das generierte JSON-Schema (Slot-Namen) — das ist beabsichtigt, kein Fehler.

## 3. Kontrollierte Vokabulare

- Enum-Werte bleiben **CV-Strings der RDA-maDMP-CVs** (`doi`, `handle`, `open`, `Contact Person`, `din31644` …), identisch zum maDMP-Export. Die URI-Form (DataCite-IRIs wie `http://purl.org/spar/datacite/…`) ist im Schema bewusst **noch nicht** an die Werte gebunden — Entscheidung vertagt auf CF2-003, damit der maDMP-Export unverändert bleibt.
- SMS-CV-Werte sind `uriorcurie`-Slots (`sensor_type`, `measured_quantity`, `unit`, `sampling_media`, `compartment`, `aggregation_type`) — die SMS-CV-URIs werden **wortwörtlich wiederverwendet** (CF1-006-Prinzip), keine Doppelmünzung.
- `format` (Distribution) bleibt freier String mit Hinweis auf IANA-Media-Types; Übersetzung des RDMO-Freitexts passiert in CF2-003.
- `sampling_media` taucht doppelt auf (`MeasuredProperty`, `SamplingPlan`) — bewusst, weil die Quelle zweigeteilt ist (SMS liefert die Messgröße, das Sampling-Intervall kommt aus RDMO/ELN, Lücke #16/#17).

## 4. Slot-spezifische Entscheidungen

- **`Person.name` / `Person.mbox`**: eigene Slots mit `foaf:name`/`foaf:mbox`-Mappings (`mbox` als `uriorcurie`, `mailto:`-URI). Lektion: LinkML **verwirft Slot-Referenzen still**, wenn sie nicht als Top-Level-Slots definiert sind — SchemaView läuft durch, erst `jsonschemagen` bricht mit `ValueError: No such slot …` ab. Gleiches traf `Host.url` (Mapping `edo:url`, Range `uriorcurie`, laut Spec §3.2) — nachgetragen.
- **`accuracy`**: bleibt Freitext (`"±0.3 K @ 25 °C"`). Die SMS-API liefert `null`; autoritativ ist das FS6002-Datenblatt (CF1-005). Strukturierte Form (Min/Max/Bedingung) erst mit CF2-003 entscheiden.
- **`resolution`**: `double` (0.1 K aus dem Datenblatt).
- **`sampling_interval`**: ISO-8601-Duration als String mit Regex-Pattern (`PT15M` für das Weatherstation-Szenario). Kein eigener Datentyp, damit CF2-003 frei bleibt.
- **`sampling_interval_source`**: Interim-Slot für Gap-Register #16 — dokumentiert, woher das Intervall stammt (manuell / ELN / künftige Katalogfrage), bis CF2-001/CF2-002 die Kataloglücke schließen.
- **`interval`** (`Project`, `MeasurementSeries`): inlined `time:Interval` mit `begin`/`end` als `date` (`time:hasBeginning`/`time:hasEnding`).
- **`dmp_id`**: deterministisch gemünzter `urn:uuid` (uuid5, Seed `rdmo:project:<pk>`) — gleiche Regel wie im maDMP-Export.
- **Beitragsrollen**: Enum `ContributorTypeEnum` = RDA-maDMP-contributor-type-CV (DataCite-Typen) — CF1-006-Entscheidung; die Freitext-`role_template`-Übersetzung ist CF2-003.

## 5. Generierung

- JSON-Schema-Artefakt: `05_P05_S05_internal-format.schema.json` (18 `$defs`), erzeugt mit `JsonSchemaGenerator` (`python -m linkml.generators.jsonschemagen -i <schema>.yaml > <out>.json`; CLI hat kein `-o`, Ausgabe per Redirect).
- Validierung: `SchemaView` über alle drei Schemas; Klassen-/Slot-/Enum-Zahlen oben sind die Regressions-Baseline.
- LinkML ist als Wegwerf-Installation unter `/tmp/linkmllib` (nicht in einem Projekt-Venv); falls weg: `.venv/bin/python3 -m pip install --quiet --target /tmp/linkmllib linkml`.
- YAML-Fallstrick (2× aufgetreten): Plain Scalars dürfen **kein `: `** enthalten (`mailto: URI`, `CF1-005: taken`) — Beschreibungen ggf. quoten oder umformulieren.
- Range-Fallstrick: `range: Any` ist ohne eigene `Any`-Klasse kein gültiger Range — `erdiagramgen`/`dotgen` brechen mit „unrecognized range (Any)“ ab, während `jsonschemagen` stillschweigend durchläuft. URI-artige Felder (`mbox`, `access_url`, `license_ref`, `url`, `website`) stehen deshalb auf `uriorcurie` (entspricht Spec §3.2, xsd:anyURI).

### 5.1 Grafische Repräsentation

- **Mermaid-ER-Diagramm** (rendert nativ in Obsidian, im Mermaid-Block einbetten):
  `PYTHONPATH=/tmp/linkmllib .venv/bin/python3 -m linkml.generators.erdiagramgen <schema>.yaml > <schema>-erd.mmd`
  → `05_P05_S05_{madmp,sms,internal-format}-erd.mmd` (je 1 Diagramm, Klassen + Kardinalitäten).
- Pro-Klassen-Mermaid-Dateien: `python -m linkml.generators.mermaidclassdiagramgen -d <outdir> <schema>.yaml`.
- Graphviz (veraltet, aber funktionsfähig; rendert **direkt** via `dot`, schreibt nichts auf stdout, hängt Format-Endung an): `python -m linkml.generators.dotgen <schema>.yaml -o <name> -f dot` → `<name>.dot` + `dot -Tsvg <name>.dot -o <name>.svg`.

## 6. Offene Punkte (bewusst nicht in CF1-007)

- Echte `edo:`-IRIs (w3id.org-Registrierung) — CF2.
- URI-Form der maDMP-CV-Enum-Werte (DataCite-IRIs) — CF2-003.
- Strukturierte `accuracy` — CF2-003.
- JSON-LD-`@context` (Slot-Name ↔ IRI) — CF2-003.
- Vollständige RDA-maDMP-Abdeckung (v1.0 aller Attribute) — CF2, hier nur grobes Prinzip.
