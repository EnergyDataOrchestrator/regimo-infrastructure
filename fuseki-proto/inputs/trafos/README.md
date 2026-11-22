# trafos — CF2-003 & CF2-004 Realisierung: Transformationen DMP & SMS → internes Format

This directory documents and drives the realisation of cards **CF2-003**
("Transformationen von DMP und SMS ins interne Format") and **CF2-004**
("LinkML Map für Transformation ins interne Format", fragment
`[[07_LinkML_Map]]`) — two ways of performing the same transformation:

* **CF2-003 — the hand-coded way:** every rule of the catalogue is realised in
  Python (`trip.py`). Sections 1–7 below.
* **CF2-004 — the map-driven way:** the transformation logic lives in two
  **LinkML Map** files (linkml-map TransformationSpecifications) compiled from
  the same catalogue; the executing tool (`agnostic_trip.py`) only wires the
  engine and serialises the result. Sections 8–13 below.

* `patterns.md` — the **transformation catalogue** (scenario 1 deliverable of
  CF2-003): every transformation from the sources into the internal format,
  tagged with a pattern identifier (P1–P42 for DMP, S1–S16 for SMS, N1–N6 for
  the new R4 classes).
* `dmp-to-internal.linkml-map.yaml` / `sms-to-internal.linkml-map.yaml` — the
  **LinkML Map files** (CF2-004 deliverable): the catalogue compiled into
  linkml-map TransformationSpecifications; the single container of the
  transformation logic in the second variant.
* `README.md` (this file) — the **realisation documentation**: how the three
  acceptance scenarios were executed end-to-end on a concrete instance (both
  variants), every concrete mapping decision, the verification results and the
  findings/open items that fell out of it.
* The executing code lives in `../fuseki-proto/tool/src/fuseki_proto/`
  (`trip.py` for CF2-003, `agnostic_trip.py` for CF2-004, run as
  `fuseki-proto trip …` / `fuseki-proto agnostic-trip …`), the storage backend
  is the Fuseki prototype `../fuseki-proto/` (README there).

Status:

* **CF2-003: all three scenarios executed 2026-11-19, run
  `../fuseki-proto/data/trip/20261119-173927/`** — 41/41 round-trip checks
  passed, triple-count equality store↔replay OK, one SHACL violation remains
  by design (see *Findings*, F1).
* **CF2-004: all three scenarios executed 2026-11-19, run
  `../fuseki-proto/data/agnostic-trip/20261119-182411/`** — 41/41 checks,
  82==82 triples, same SHACL verdict; the graph is **isomorphic** to the
  CF2-003 trip graph modulo 4 documented `rdf:type` triples (§11).

---

## 1. The three scenarios (card CF2-003) and how they map to the run

| # | Scenario (Given/When/Then, condensed) | Stage of `trip.py` |
|---|---|---|
| 1 | **Transformation rules documented** — mapping rules captured; field-level transformations, edge cases, missing-value handling documented | `transform` (applies the `patterns.md` catalogue and writes every rule application, translation decision and loss into the report) |
| 2 | **The transformed project is stored in the Fuseki triplestore** — transformed internal-format graph stored in `/projects`, retrievable via SPARQL, validated against `project-claim-shapes.ttl` | `store` (wipe + upload + SPARQL retrievability check + pyshacl) |
| 3 | **Round-trip via the Fuseki triplestore preserves the data** — dump the store back out, verify the dump carries the same data as the original DMP and SMS | `verify` (dump → replay graph → 41 field-level checks + triple-count equality) |

`fuseki-proto trip run` executes 1 → 2 → 3 in one command.

## 2. Instance under test

| Source | File | Key content |
|---|---|---|
| DMP (maDMP export via RDMO) | `../dmp/measurement_02/Measurement_02-13.json` | `dmp_id` `urn:uuid:d9e575a1-7ae1-588a-be39-b44574958fa0` (type `urn`), project "Measurement_02" 2027-01-01…2027-07-31, 2 contributors ("A. Koubaa"), dataset `bnetza_vorhabenpunkte_bbplg_2` with 2 distributions, 3 quality-assurance items, personal+ sensitive data, no contact, no costs, no language |
| SMS device | `../sms/device-67.json` | "KIT-CN-IAI-Bau445-Weather-Station-Weatherstation", model FS6002, FuehlerSysteme eNET International GmbH, equipment type `smscv:equipmenttypes/54/`, PID `21.11157/9b6cdfb9-a4fb-4269-af04-1ef94588f5a8` |
| SMS device property | `../sms/device-67-property-159-air-temperature.json` | "Air temperature" (`smscv:measuredquantities/4/`), unit `…/units/51/` (°C), SMS range −80…60, accuracy/resolution `null`, sampling media Air, compartment Atmosphere, aggregation Average |

> Only device property 159 is available as a machine-readable file; the device
> references properties 157–161 (see finding F7).

## 3. Running it

```bash
cd ../fuseki-proto/tool
. .venv/bin/activate          # needs click + linkml-map (CF2-004); pyshacl optional (SHACL stage)
fuseki-proto start            # bring the prototype up (port 3031)
fuseki-proto trip run         # CF2-003: transform -> store -> verify
fuseki-proto agnostic-trip run  # CF2-004: the same scenarios, map-driven
# or the individual stages (both commands have the same shape):
fuseki-proto trip transform           # scenario 1: catalogue -> internal-format graph
fuseki-proto trip store               # scenario 2: load into /projects, SPARQL + SHACL
fuseki-proto trip verify              # scenario 3: dump, replay, field-level checks
fuseki-proto agnostic-trip transform  # scenario 1 via the LinkML Maps
fuseki-proto agnostic-trip store      # scenario 2 (default: latest agnostic-trip artifacts)
fuseki-proto agnostic-trip verify     # scenario 3 (replay graph urn:edo:agnostic-trip:replay)
```

Sources can be overridden (`--dmp`, `--sms-device`, `--sms-property`, repeatable
for several device properties); connection via `--port/--user/--password/--dataset`.

**Artifacts** per run in `../fuseki-proto/data/trip/<timestamp>/` (CF2-003) or
`../fuseki-proto/data/agnostic-trip/<timestamp>/` (CF2-004):

| File | Content |
|---|---|
| `project-graph.ttl` | the transformed internal-format instance graph (Turtle) |
| `roundtrip-dump.ttl` | the Turtle dump Fuseki served back from `/projects` |
| `trip-report.json` | inputs, applied rules, notes/losses, all 41 checks with per-graph results, store/verify summaries, SHACL report |
| `agnostic-trip-report.json` | (CF2-004) the same stages/checks plus the map files, linkml-map version, the compiled derivations and the transformed objects as JSON |

Exit code: `0` when all round-trip checks pass and the replay triple count
equals the store's; `1` otherwise. The SHACL verdict is recorded in the report
but does **not** fail the run (F1 is an open mapping/shape decision, not a
round-trip failure).

## 4. Concrete mapping decisions (scenario 1)

The catalogue in `patterns.md` names the *rule*; this section records the
*decision taken for this instance* — the exact content of
`data/trip/20261119-173652/trip-report.json` (`stages.transform.applied_rules`,
50 entries). Highlights:

### 4.1 Project (P1–P9)

| Rule | Decision on this instance |
|---|---|
| P1 | `project/title` `"Measurement_02"` → `dcterms:title`. **Note:** spec §4's example carries the *DMP-document* title ("maDMP for Measurement_02") — see finding F3. |
| P2 | `project/description` "Example Measurement, as a child-project of IAI." → `dcterms:description` (1:1). |
| P3 | No `language` in export → **default `eng`** (omit → default). |
| P4 | `start`/`end` 2027-01-01…2027-07-31 → `time:hasInterval` blank node, dates cast to `xsd:date`. (NB: the spec §4 example shows the older 2026-07-01…09-11 window.) |
| P5/P16/P17 | `dmp_id` `urn:uuid:d9e575a1-…` (type `urn`) → `edo:dmpId` Identifier node. |
| P6 | **No `contact` in export → omitted** (faithful mapping). This trips `edo:ProjectShape` (`sh:minCount 1` on `edo:hasContact`) — finding **F1**. |
| P7/P8 | 2 contributors → 2 `edo:Contribution` nodes. Role translation (see 4.4): both "Responsible for preservation" and "Responsible for metadata …" → `Data Curator`; unmapped templates would default to `Other`. The free-text role itself is lost in the CV translation (documented). |
| P10/P11 | Agent name 1:1; mbox cast to `mailto:…` **typed as `xsd:anyURI` literal** — required by `foaf:PersonShape` (`sh:datatype xsd:anyURI`); an IRI has no datatype and violates the shape — finding **F2**. |
| P9 | No `cost[]` → omitted. |

### 4.2 Dataset & distributions (P18–P42)

| Rule | Decision on this instance |
|---|---|
| P18 | `dataset_id` `bnetza_vorhabenpunkte_bbplg_2` (type `other`) → `edo:identifier` Identifier node. Dataset IRI minted as `<dmp_id>/dataset:<id>`. |
| P19/P20 | Title, German description 1:1. |
| P21 | `issued` 2027-01-29 → `xsd:date`. |
| P22 | No dataset `type` in this export → omitted (the RDMO-template default was not materialised). |
| P23–P27 | Keywords ×2, `personal_data: yes → true`, `sensitive_data: yes → true` (maDMP yes/no-CV → boolean), quality assurance split into 3 items, preservation statement 1:1. |
| P28 | `security_and_privacy` ("Access authentication" / "Data is public under GeoNutzV.") → **LOST** — no v0.2 target property. Negative check C19 asserts its absence. |
| P29–P34 | Distribution "Storage during the project": `access_url` → `dcat:accessURL`, `data_access open` → `edo:dataAccess`, format **"CSV and JSON" → `text/csv` + `application/json`** (free text → IANA media types, emitted as `http://purl.org/NET/mediatypes/…` IRIs following `data/sample-project.ttl`). |
| P31–P42 | Distribution "Preservation after the project": `data_access open` (given, not derived), `pid_system "doi"` (NB: maDMP JSON carries a **string**, not a list — normalised, F6), `host.title "Own institution"` → `edo:hostedBy edo:Host`, license CC-BY-4.0 with `start_date` 2027-01-29 → `dcterms:license` + `time:hasBeginning`. |
| P30 | No `PIDINST:` fragment in this dataset's description → **no `prov:wasGeneratedBy` link**; the SMS sensor is emitted as a standalone node. Negative check C25 asserts the absence (gap #18). |

### 4.3 SMS (S1–S16)

| Rule | Decision on this instance |
|---|---|
| S6 | Sensor IRI `https://sms.atmohub.kit.edu/devices/67` (SMS API path + EDO base URL). |
| S1–S4 | `short_name` → `dcterms:title`, model FS6002, manufacturer (trailing whitespace normalised), equipment-type URI passthrough (`device_type_name` "Weather station" label dropped — documented loss). |
| S5 | PID → Identifier node, type `handle`. |
| S7–S9 | `smscv:measuredQuantity` (measuredquantities/4/), title "Air temperature", unit units/51/ — URI passthrough, CV *names* dropped (documented loss). |
| S10 | **Datasheet override**: SMS says −80…60 → graph carries **−40.0…80.0** (datasheet is authoritative per CF1-005 / spec open item 7). Negative check C35 asserts the raw SMS value is *not* in the graph. |
| S11/S12 | accuracy/resolution `null` in SMS → datasheet values "±0.3 K @ 25 °C; ±1.0 K over -40…+80 °C" and 0.1. |
| S13–S15 | sampling media / compartment / aggregation-type URI passthrough (`smscv:samplingMedia`, `smscv:compartment`, `edo:aggregationType`). |
| S16 | Property → `sosa:observes` node (type `sosa:ObservableProperty`). |

### 4.4 Translation tables (implemented in `trip.py`)

| Free text (role_template) | RDA maDMP CV (P8) |
|---|---|
| "Responsible for preservation" | `Data Curator` |
| "Responsible for metadata …" | `Data Curator` |
| anything else | `Other` (documented default) |

| Free text (format) | IANA media type (P34) |
|---|---|
| "CSV" | `text/csv` |
| "JSON" | `application/json` |
| "CSV and JSON" | `text/csv`, `application/json` |
| XLS/Excel, NetCDF, PDF, XML | respective media types |

Datasheet overrides (S10–S12) are keyed by measured-quantity URI and currently
cover `smscv:measuredquantities/4/` (air temperature).

## 5. Verification (scenario 3)

After storing, `/projects` is dumped (CONSTRUCT, Turtle), the dump is
**re-uploaded into the named replay graph `<urn:edo:trip:replay>`**, and every
check is evaluated **twice**: against the replay graph (i.e. the dump — what
scenario 3 asks) and against the default graph (the store). Values are compared
at the SPARQL level against values extracted directly from the original JSON
sources, which sidesteps blank-node relabelling during round-trips.

Result of run `20261119-173927`:

* **41/41 checks passed** on both graphs (C01–C40, one count check per repeatable
  field): project title/description/language-default/interval/dmpId, both
  contributions incl. translated roles and mbox, dataset id/title/description/
  issued/keywords×2/personal/sensitive/quality-assurance×3/preservation
  statement, both distributions incl. formats×2/host/license, sensor
  title/model/manufacturer/type/PID, measured property incl. datasheet override
  (and the rejection of the raw SMS range).
* **Negative checks** confirmed the documented losses: no security predicate
  (P28), no `prov:wasGeneratedBy` (P30/gap #18), no contact (P6), no raw SMS
  range values (S10).
* **Triple-count equality**: default graph 78 triples == replay graph 78 triples.

## 6. Findings & open items

| # | Finding | Status |
|---|---|---|
| F1 | `edo:ProjectShape` demands ≥1 `edo:hasContact` (`sh:minCount 1`), but the maDMP export carries no `contact`; faithful P6 behaviour (omit) → SHACL violation. **Decision needed:** relax the shape (contact optional) vs. guarantee a contact in the RDMO export vs. derive contact from a contributor. | Open — tracked in card **[[CF2-007]]** (decision 2027-04-30) |
| F2 | `foaf:PersonShape` types `foaf:mbox` as `xsd:anyURI`; an IRI has no datatype, a plain literal has `xsd:string` — both violate. Correct encoding: `mailto:…` as an `xsd:anyURI` **typed literal** (now in `trip.py`). `data/sample-project.ttl` had the same defect and was corrected on 2026-11-19 (now conforms). | Resolved (sample + trip.py) |
| F3 | Title rule: catalogue P1 maps `project/title`; spec §4's example carries the DMP-document title instead. `trip.py` follows the catalogue; harmonise spec §4 / catalogue wording. | Resolved 2026-11-19: spec §4 example + `sample-project.ttl` now use the project title "Measurement_02" and note the `dmp/title` distinction; P1 annotated in the catalogue. |
| F4 | Namespace inconsistency: `data/sample-project.ttl` uses `sosa:` = `http://www.w3.org/ns/sosa#`, spec §3.1 and the shapes use `…/sosa/`. `trip.py` follows spec/shapes. | Resolved 2026-11-19: `sample-project.ttl` `sosa:` → `http://www.w3.org/ns/sosa/` (matches spec §3.1, shapes, trip.py). |
| F5 | `dcat:format` encoding: spec §4 shows plain strings ("text/csv"), `sample-project.ttl` and `trip.py` emit `http://purl.org/NET/mediatypes/…` IRIs. | Resolved 2026-11-19: spec §4 Example + §3.3 document the Media-Type-IRI representation (`http://purl.org/NET/mediatypes/<type>`); catalogue P34 harmonised. |
| F6 | maDMP JSON types `pid_system` as a plain string ("doi"), not a list — `trip.py` normalises both. Also `project/title` ("Measurement_02") vs `dmp/title` ("maDMP for Measurement_02") differ in this export. | Handled in code |
| F7 | Only device property 159 is available as a file; device 67 references properties 157–161. Export the remaining property files to cover the full sensor. | Resolved 2026-11-19 (CF1-010): all five `device-67-property-{157..161}-*.json` exported (wind speed/direction, air temperature, rel. humidity, atm. pressure) under `scripts/sms/`; coverage of `device-67.json` ids verified. |

## 7. Related artefacts

* Card: `../../05_Cards/CF2-003.md` (activity log documents the runs)
* Catalogue: `patterns.md` in this directory
* Internal-format spec: `../internal-format/04_P04_S04_internal-format-spec.md`
* Fuseki prototype: `../fuseki-proto/` (+ `tool/README.md` for the CLI,
  incl. the `trip` command)
* Run artifacts: `../fuseki-proto/data/trip/<timestamp>/`

---

# CF2-004 — zweite Variante: LinkML-Map-getriebene Transformation (`agnostic-trip`)

Card **CF2-004** (“LinkML Map für Transformation ins interne Format”) requires
the **same transformation** as CF2-003 — same sources, same internal format,
same store, same acceptance scenarios — but with the logic **not hand-coded**:
two **LinkML Map** files (linkml-map TransformationSpecifications) compile the
catalogue `patterns.md` and are the **container of the whole transformation
logic**. The executing tool is *agnostic* with respect to the rules: it only
wires the engine (linkml-map ObjectTransformer) and serialises the transformed
objects into the internal-format graph, driven by the internal-format schema.

Deliverables (all in place):

| Deliverable | File |
|---|---|
| LinkML Map, DMP half (rules P1–P42) | `dmp-to-internal.linkml-map.yaml` (this directory) |
| LinkML Map, SMS half (rules S1–S16) | `sms-to-internal.linkml-map.yaml` (this directory) |
| Executing tool | `../fuseki-proto/tool/src/fuseki_proto/agnostic_trip.py` (`fuseki-proto agnostic-trip …`) |
| Test results + validation report | run `../fuseki-proto/data/agnostic-trip/20261119-182411/` (+ §12) |

Status: **realised and executed 2026-11-19** — 41/41 round-trip checks passed,
triple-count equality 82==82, SHACL verdict identical to CF2-003 (one F1
violation by design), and the emitted graph is **isomorphic to the CF2-003
trip graph** modulo 4 documented `rdf:type` triples (§11).

## 8. How the catalogue is compiled into the maps

linkml-map 0.5.2 (pinned; the version used defines the specification language)
executes a TransformationSpecification with the `ObjectTransformer`: each
**class derivation** (`populated_from` = source class, keyed by target class)
maps a source object into a target dict via **slot derivations** — either
`populated_from` (direct field, recursing into nested class derivations by the
source slot's range) or `expr` (a LinkML expression evaluated by the restricted
evaluator: null-propagating operators, `case()`, schema-bound attribute access
— `.strip()`, `.join()`, `.lower()` work on resolved slot values). Enum-typed
source slots require one matching **enum derivation** per source enum (the
two maps use pass-through `mirror_source` derivations). Reconciliation of
export-JSON deviations against the source schema happens inside the map via
`source_schema_patches` (F4, F5 — see below), so each map file is fully
self-contained.

Rule → derivation index (the map files document every slot derivation with its
rule reference in the `description`):

| patterns.md rule | Derivation / mechanism in the map |
|---|---|
| P1/P2 | `Project.title` / `.description`, `expr: project[0].title|description` (project title, NOT the DMP-document title — F3; needs the F4 patch) |
| P3 | `Project.language`, `expr: language or "eng"` (omit → default) |
| P4 | `Project.interval`, `expr` dict literal `{interval_begin, interval_end}` → Interval node |
| P5/P16/P17 | `Project.dmp_id` → shared `Identifier` derivation (`identifier_value`/`identifier_type`) |
| P6/P10/P11 | `Project.has_contact`, `populated_from: contact` (absent → omitted → F1) |
| P7/P8 | `Project.has_contribution` → `Contribution.role`, `expr` case over the joined roles (`responsible for preservation|metadata` → `Data Curator`, else `Other`) — compiles the ROLE_TRANSLATION table |
| P10/P11 | `Contribution.agent`, `expr` dict `{name, 'mailto:' + mbox}` (null-propagating; absent mbox → key dropped) |
| P9 | `Project.has_cost`, `populated_from: cost` (absent → omitted) |
| P18 | `Dataset.identifier` ← `dataset_id` (Identifier derivation); the Dataset IRI is minted by the serialiser |
| P19–P22 | `Dataset.title/description/issued/dataset_type`, `populated_from` |
| P23 | `Dataset.keyword`, `populated_from` (array passthrough) |
| P24/P25 | `Dataset.personal_data/sensitive_data`, `expr` `case((… == "yes", True), (… == "no", False), (True, False))` |
| P26/P27 | `Dataset.quality_assurance` ← `data_quality_assurance` (split), `.preservation_statement` |
| P28 | **deliberately NOT derived** — no v0.2 target class (documented loss) |
| P29–P33 | `Dataset.has_distribution` → `Distribution.title/access_url/data_access` (data_access via DataAccessEnum mirror) |
| P34 | `Distribution.format`, `expr`: list of six `case` entries compiling the FORMAT_TRANSLATION table (case-insensitive substring over the joined labels; no match → `None`, dropped by the serialiser; "CSV and JSON" → both media types) |
| P35/P36 | `Distribution.certified_with/pid_system`, `populated_from` (CertificationEnum / IdentifierTypeEnum mirror; the string "doi" is coerced to a list by the engine) |
| P37/P40 | `Distribution.hosted_by` → `Host.title/url` |
| P38/P39/P41/P42 | `Distribution.license` → `License.license_uri/license_start_date` (needs the F5 patch introducing `LicenseRef`) |
| P30 | **not derivable as a slot derivation** — dataset↔sensor link via PIDINST free text remains a code-level concern (gap #18) |
| S1 | `Sensor.title`, `expr: short_name or long_name or device_type_name` |
| S2/S4 | `Sensor.model` / `.sensor_type`, `populated_from` |
| S3 | `Sensor.manufacturer`, `expr: manufacturer_name.strip() if manufacturer_name else None` (whitespace normalisation) |
| S5 | `Sensor.identifier`, `expr` dict `{identifier_value: persistent_identifier, identifier_type: 'handle'}` |
| S6 | **not in the map** — the serialiser mints the device IRI from the JSON:API `data/id` |
| S7–S9 | `MeasuredProperty.measured_quantity/measured_quantity_name/unit`, `populated_from` |
| S10–S12 | `MeasuredProperty.measuring_range_min/max`, `.accuracy`, `.resolution`, `expr` `case` over `property_uri` — compiles the DATASHEET_OVERRIDES table (`…measuredquantities/4/` → −40.0 / 80.0 / "±0.3 K …" / 0.1) |
| S13–S15 | `MeasuredProperty.sampling_media/compartment/aggregation_type`, `populated_from` |
| S16 | `Sensor.observes`, `populated_from: device_properties` (assembled by the tool, see §10) |

Both maps carry the four maDMP CVs (`IdentifierTypeEnum`, `DataAccessEnum`,
`CertificationEnum`, `LanguageEnum`) as `mirror_source` pass-through enum
derivations — linkml-map requires exactly one derivation per reachable source
enum.

## 9. Schema reconciliation (internal-format schema edits)

Writing the maps against `05_P05_S05_internal-format-schema.yaml` surfaced
places where the CF1-007 schema and the CF2-003 realisation diverged; the
schema was reconciled to the realisation (each an explicit finding):

| Edit | Rationale |
|---|---|
| prefix `smscv:` added | the schema references SMS-CV URIs but lacked the prefix |
| `measured_quantity` → `smscv:measuredQuantity`, `sampling_media` → `smscv:samplingMedia`, `compartment` → `smscv:compartment` | align the mappings with trip.py (S7/S13/S14) |
| `measured_quantity_name` → `dcterms:title` | S8 |
| `license_start_date` → `time:hasBeginning` | P39/P42 |
| `interval_end`: `time:hasEnding` → **`time:hasEnd`** | trip.py + SHACL `IntervalShape` use `time:hasEnd` |
| `format`: `string` → **`uriorcurie`** | F5 resolved in favour of media-type IRIs (`http://purl.org/NET/mediatypes/…`) |
| `measuring_range_min/max`, `resolution`: `double` → **`decimal`** | trip.py emits `xsd:decimal` literals |

> NB (F11, closed 2026-11-19): the JSON Schema was regenerated after these
> edits with `.venv/bin/gen-json-schema` (linkml **1.11.1**, pinned for
> linkml-map 0.5.2 per F8). Deltas to the superseded linkml-1.12.0 version of
> commit `09a25eb`: the reconciliation descriptions above, one generator
> behaviour change (`data_access`: `anyOf`+`null` → direct `$ref`), and
> `metamodel_version` 1.12.0 → 1.11.0. The provenance of this version (copies
> of the two files, references to everything that shaped it, the generation
> run as `CreateAction`) is documented in the RO-Crate
> `../linkml/05_P05_S05_internal-format-json-schema-crate/` (see its
> README.md). The crate is self-sufficient for the generation step: it
> contains `reproduce.sh`, the pinned environment (`environment/pip-freeze.txt`,
> linkml 1.11.1 / linkml-runtime 1.11.1) and the `linkml:types` module resolved
> during the run (`environment/linkml-types.yaml`); re-running the generation
> from the crate contents reproduced the archived JSON Schema byte-identically
> (verified 2026-11-19).

The same reconciliation applies **inside the DMP map** as
`source_schema_patches` (so the map stays self-contained): F4 (`dmp/project`
as a single-element list → `multivalued`) and F5 (`license` as an array of
`{license_ref, start_date}` objects → multivalued `LicenseRef` reference + new
`LicenseRef` class).

## 10. Engine-level adaptations (agnostic_trip.py)

Three things cannot be expressed in a map and live in the tool (documented in
its docstring):

1. **JSON:API unwrapping** — SMS records are enveloped (`data/attributes`);
   attributes are filtered to the slots the SMS schema knows and the separately
   fetched device-property records are assembled under `device_properties`
   before `map_object` runs (the map then addresses them via normal slot
   derivations).
2. **IRI minting from context** — the Sensor IRI
   `https://sms.atmohub.kit.edu/devices/<data.id>` (S6) comes from the
   JSON:API envelope, not from the attributes the map sees; the Dataset IRI
   `<dmp_id>/dataset:<urlquoted identifier_value>` (P18) is minted from the
   transformed Identifier during serialisation.
3. **Schema-driven serialiser** — walks each transformed object against the
   internal-format SchemaView: predicate = first slot `mappings` entry (else
   `<default_prefix>:<lowerCamel(slot)>`), datatyping = slot range (`date` →
   `xsd:date`, `decimal` → `xsd:decimal`, `boolean` → plain `true/false`,
   `uriorcurie` → IRI, `foaf:mbox` → `"…"^^xsd:anyURI` per F2), node types =
   class `class_uri`; `None` values, `None` list items (P34's non-matches) and
   content-free nodes are skipped. Subject strategy: Project ←
   `dmp_id.identifier_value`, Dataset ← minted IRI, Sensor ← context IRI,
   everything else blank nodes.

The transformer runs with `unrestricted_eval=True`, so the asteval fallback is
available for future rules; all current rules evaluate in the restricted
LinkML evaluator.

## 11. Equivalence with the CF2-003 way (the second way proves the first)

The two variants must produce the same data. Verified with rdflib against the
CF2-003 run artifact `data/trip/20261119-173927/project-graph.ttl`:

* All IRI/literal (blank-node-free) triples are **identical** between the two
  graphs.
* After removing the 4 nested `rdf:type` triples (see below), the graphs are
  **isomorphic** (rdflib `isomorphic`, blank-node structure included).
* The difference: the agnostic serialiser emits `rdf:type` for **every** class
  node, while trip.py omitted it for the Interval and the three Identifier
  blank nodes. The agnostic graph therefore holds **82 vs. 78 triples**, all
  four extra triples are `a time:Interval` / `a edo:Identifier` on blank
  nodes. Both encodings are faithful; the SHACL shapes don't target these
  classes directly, so the verdict is unaffected.

## 12. Executing the three scenarios (CF2-004 run)

```text
fuseki-proto agnostic-trip run
  # transform: map-driven, project urn:uuid:d9e575a1-…, sensor …/devices/67
  # store:     82 triples loaded into /projects, retrievable via SPARQL
  #            SHACL: does NOT conform — exactly 1 violation (F1, hasContact)
  # verify:    dump 6307 bytes -> replay <urn:edo:agnostic-trip:replay>
  #            Round-trip checks: 41/41 passed
  #            Triple-count equality default vs. replay: OK (82 vs. 82)
```

Run `20261119-182411`, artifacts `data/agnostic-trip/20261119-182411/`:
`project-graph.ttl`, `roundtrip-dump.ttl`, `agnostic-trip-report.json` (map
files, linkml-map 0.5.2, compiled derivations, transformed objects, stages,
41 checks, SHACL report). Exit code 0; the SHACL verdict is recorded but does
not fail the run (same policy as CF2-003).

## 13. CF2-004 findings & open items

| # | Finding | Status |
|---|---|---|
| F8 | linkml-map 0.5.2's specification language is the *old* datamodel (class/slot/enum derivations with `populated_from`/`expr`); preconditions/class rules are not yet usable. Version-pinned: the maps are only guaranteed against 0.5.x. | Documented |
| F9 | `str()` in a restricted `expr` distributes over lists (linkml-map `_distributing`), so substring tests over list-valued slots must join first — the maps use `(' '.join(format or [])).lower()` / `(' / '.join(role or [''])).lower()` instead of `str(format)`. | Compiled into the maps |
| F10 | P34 as a substring test over the joined labels refines trip.py's regex word boundaries (`\bcsv\b`) — equivalent on this data, to be kept in mind for free-text formats like "scsv". Same for P8. | Documented in the maps |
| F11 | The internal-format schema edits (§9) make the generated JSON Schema stale; regenerate before the next JSON-Schema consumer. | Closed 2026-11-19: regenerated with linkml 1.11.1; provenance in the RO-Crate `../linkml/05_P05_S05_internal-format-json-schema-crate/`. |
| F12 | P30 (dataset↔sensor link, gap #18) and S6/P18 subject minting stay outside the maps — a future spec revision with machine-readable links should move them into the map (target schema slots) as well. | **P30 linkage decision made (CF2-005, 2026-11-19):** link lives in the internal format as reference (`Dataset prov:wasGeneratedBy Sensor`, `Sensor sosa:observes MeasuredProperty`), join key = sensor PID; strategy + exemplified instance in `../internal-format/linkage-strategy.md` / `linked-instance.example.json`. Becomes map-able once the DMP carries the PID machine-readably (CF2-001/002). **S6/P18 subject minting:** still Open (spec). |

## 14. Related artefacts (CF2-004)

* Card: `../../05_Cards/CF2-004.md` (activity log documents the runs)
* LinkML Maps: `dmp-to-internal.linkml-map.yaml`, `sms-to-internal.linkml-map.yaml` (this directory)
* Executing tool: `../fuseki-proto/tool/src/fuseki_proto/agnostic_trip.py` + `tool/README.md` (`agnostic-trip` command)
* Internal-format schema: `../linkml/05_P05_S05_internal-format-schema.yaml` (reconciled, §9)
* Run artifacts: `../fuseki-proto/data/agnostic-trip/<timestamp>/`
* CF2-003 counterpart: sections 1–7 above (same catalogue, hand-coded)
