# SHACL Transformation Patterns: Metadata Interoperability

This document outlines standardized patterns for mapping metadata schemas using SHACL-based transformation rules. These patterns address common challenges in achieving data interoperability between domain-specific vocabularies and broader standards like DCAT.

The full abstract taxonomy of transformation patterns — including class-level, conditional/guard-based, and structural reconstruction patterns — is maintained in `planning/Metadata Crosswalk - Patterns Map.md`. The catalogue below lists the pattern identifiers that the interactive creation CLI (see the last section) tags decisions with; the first two sections of this document then discuss the *Target Class Problem* and a concrete first pattern instance.

## Pattern Catalogue (Identifiers used by the interactive CLI)

| Identifier | Pattern | Category |
| --- | --- | --- |
| `direct-class-mapping` | Direct Class Mapping | Entity/Class-Level |
| `class-specialisation` | Class Specialisation / Splitting | Entity/Class-Level |
| `class-generalisation` | Class Generalisation / Merging | Entity/Class-Level |
| `direct-property-mapping` | Direct Property Mapping | Property-Level |
| `literal-transformation` | Literal Transformation / Casting | Property-Level |
| `inverse-property-mapping` | Inverse Property Mapping | Property-Level |
| `literal-to-node-promotion` | Literal-to-Node Promotion (Value-Driven Selection) | Property-Level |
| `type-conditional` | Type-Conditional Property Mapping | Conditional / Guard-Based |
| `value-conditional` | Value-Conditional Mapping | Conditional / Guard-Based |
| `existence-conditional` | Existence-Conditional Mapping | Conditional / Guard-Based |
| `flattening` | Flattening / Unnesting | Structural Reconstruction |
| `nesting` | Nesting / Aggregation | Structural Reconstruction |
| `reification` | Reification / Association Mapping | Structural Reconstruction |
| `default-injection` | Default Injection / Mandatory Attribute Completion | Structural Reconstruction |

Notes on the two value-driven patterns:

* **`literal-to-node-promotion`** — a literal in the input is used as a lookup key to *select* the target subject, predicate, or object (e.g. choosing the target class) instead of being carried over as a value. The interview collects the value→target lookup table.
* **`default-injection`** — when a target class is instantiated whose schema declares mandatory attributes (minCount ≥ 1) that the source lacks, schema-compliant defaults (fixed constants, minted/derived values via templates) are injected so the generated object stays valid. It is the target-driven counterpart of `existence-conditional`.

---

# EDO Transformation Catalogue: maDMP & SMS → Internes Format

This section is the CF2-003 deliverable (fragment `[[06_Transformationen]]`):
it tags **every** transformation from the EDO sources into the internal format
(the pivot, spec `scripts/internal-format/04_P04_S04_internal-format-spec.md`
v0.2; CF1-006) with a pattern identifier from the catalogue above. This is a
*different layer* than the existing RDMO→maDMP plugin mapping
(`scripts/dmp/03_P03_S03_madmp-export.mapping.yaml`, CF1-004): here the source is
the **maDMP document** (DMP) already produced by that plugin, plus the **SMS
device/property JSON** (`scripts/sms/`). The targets are the internal-format
classes.

Each table row answers the four questions of CF2-003 / fragment 06 in the two
right-most columns:

* **1:1?** — is the value carried over unchanged (`1:1`) or re-encoded
  (`cast` type change, `derive` computed value, `split` items list, `join`
  multi-value, `translate` CV/term lookup, `mint` generated identifier,
  `fixed` constant, `n/a` purely structural)?
* **Missing →** — what happens when the source value is absent (`omit` drop the
  slot, `default` fallback value, `null` optional nullable slot, `datasheet`
  authoritative override, `manual` provisioned on EDO level, `n/a` not
  applicable). **Lost information** appears as `omit` rows and is summarised
  after each DMP/SMS block. When the source value is a controlled-vocabulary
  term, the internal format keeps the CV term (option-map vocabulary passed
  through); only where the spec mandates a target-side dictionary (formats →
  IANA, contributor roles → RDA CV, accuracy override) is the value
  retranslated here.

## DMP → Internes Format

### Project class (from `dmp/project`, `dmp`, `dmp/contact`, `dmp/contributor`, `dmp/cost`, `dmp/dmp_id`)

| # | Source (maDMP) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| P1 | `project/title` | Project `dcterms:title` | `direct-property-mapping` (Property-Level) | 1:1 | default (maDMP title template) |
| P2 | `project/description` | Project `dcterms:description` | `direct-property-mapping` (Property-Level) | 1:1 | null (optional) |
| P3 | `language` | Project `dcterms:language` | `direct-property-mapping` (Property-Level) | 1:1 (CV) | omit → fall back to `eng` |
| P4 | `project/start`, `project/end` | Project `time:hasInterval` → **Interval** node (`begin`/`end`) | `nesting` (Structural) + `direct-property-mapping` per date | cast (→date) | null (interval optional) |
| P5 | `dmp_id` (minted `urn:uuid`, uuid5 `rdmo:project:{pk}`) | Project `edo:dmpId` → **Identifier** node | `default-injection` (minted value, Structural) + `nesting` | mint | always present (minted) |
| P6 | `contact` | Project `edo:hasContact` → **Person** node | `nesting` (Structural) | 1:1 | omit (contact optional) |
| P7 | `contributor` | Project `edo:hasContribution` → **Contribution** node | `nesting` + `class-specialisation` (Entity/Class-Level) | n/a (agent split) | omit |
| P8 | `contributor.role_template` (free text) | Contribution `dcterms:type` (RDA maDMP contributor-type CV) | `literal-transformation` (free text → CV lookup, Property-Level) | translate | default `Other` (unmapped template) |
| P9 | `cost[]` | Project `edo:hasCost` → **Cost** nodes | `nesting` (Structural) | n/a | omit |

> **Lost (Project):** funder (`dmp/project/funder`), grant id, and the RDMO
> `role_template` free text itself are not carried into the v0.2 Project class.

### Person class (contact / contributor agent)

| # | Source (maDMP) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| P10 | `contact.name` / `contributor.name` | Person `foaf:name` | `direct-property-mapping` (Property-Level) | 1:1 | omit (person without name) |
| P11 | `contact.mbox` / `contributor.mbox` | Person `foaf:mbox` | `direct-property-mapping` (Property-Level) | 1:1 | null (optional) |
| P12 | `contact.identifier` / `contributor.identifier` (e.g. ORCID) | Person `edo:identifier` → **Identifier** node | `nesting` (Structural) | 1:1 (CV type) | omit |

### Cost class

| # | Source (maDMP) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| P13 | `cost.title` | Cost `dcterms:title` | `direct-property-mapping` (Property-Level) | 1:1 | n/a (title always set) |
| P14 | `cost.value` | Cost `edo:value` | `direct-property-mapping` (Property-Level) | cast (→decimal) | null (value optional, gap #13) |
| P15 | `cost.currency` | Cost `edo:currency` (ISO 4217) | `existence-conditional` (guard: only when present; yesterday not produced — gap #13) | translate (CV) | omit (gap #13) |

### Identifier class (dmp_id, dataset_id, person_id, sensor PID)

| # | Source | Target | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| P16 | id value | Identifier `dcterms:identifier` | `direct-property-mapping` (Property-Level) | 1:1 | mint fallback |
| P17 | id type CV (+ fallback `other`) | Identifier `dcterms:type` | `direct-property-mapping` (CV) or `default-injection` (fallback `other`) | translate (CV) | default `other` |

### Dataset class (from `dmp/dataset`) — one dataset per `set` element

| # | Source (maDMP) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| P18 | `dataset_id` (+ fallback to dataset set value) | Dataset `edo:identifier` → **Identifier** node | `nesting` + `default-injection` (fallback id, type `other`) | translate (CV) | default (fallback to set value, type `other`) |
| P19 | `title` (+ `title_fallback` "Dataset #n") | Dataset `dcterms:title` | `direct-property-mapping` + `default-injection` (fallback) | 1:1 | default `Dataset #n` |
| P20 | `description` | Dataset `dcterms:description` | `direct-property-mapping` (Property-Level) | 1:1 | null (optional) |
| P21 | `issued` (`data_publication_date`) | Dataset `dcterms:issued` | `literal-transformation` (ISO date cast, Property-Level) | cast (→date) | omit (not yet published) |
| P22 | `type` | Dataset `dcterms:type` | `direct-property-mapping` (Property-Level) | 1:1 (CV) | default (RDMO dataset type template) |
| P23 | `keyword[]` | Dataset `dcat:keyword[]` | `direct-property-mapping` (multivalued, Property-Level) | 1:1 (array) | omit (no keywords) |
| P24 | `personal_data` (bool) | Dataset `edo:personalData` | `direct-property-mapping` (Property-Level) | 1:1 | default (`false`) |
| P25 | `sensitive_data` (bool) | Dataset `edo:sensitiveData` | `direct-property-mapping` (Property-Level) | 1:1 | default (`false`) |
| P26 | `data_quality_assurance` (items list, "- "-prefixed lines) | Dataset `edo:qualityAssurance[]` | `direct-property-mapping` + `literal-transformation` (items-list split, Property-Level) | split (items list → array) | omit (empty list) |
| P27 | `preservation_statement` (joined `value_list`) | Dataset `edo:preservationStatement` | `direct-property-mapping` (join, Property-Level) | join (multi-value → string) | omit |
| P28 | `security_and_privacy` | (*no target in v0.2 — carried as free text / later*) | — | n/a (lost) | n/a |
| P29 | `distribution` (during + after) | Dataset `dcat:distribution` → **Distribution** nodes × 2 | `nesting` (Structural) | n/a (structural) | default (two distributions always emitted) |
| P30 | dataset↔sensor (today only `PIDINST:` free text in `description`) | Dataset `prov:wasGeneratedBy` → **Sensor** | `existence-conditional` (guard on present PID) / future — gap #18 | derive (extract PID) | omit (today lost; gap #18) |

> **Lost (Dataset):** `security_and_privacy` has no v0.2 target (P28, carried as
> free text / future spec revision); the machine-readable dataset↔sensor link is
> not yet captured — today only a `PIDINST:` free-text fragment in `description`
> survives (P30, gap #18).

### Distribution class

| # | Source (maDMP) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| P31 | during/after `title` (fixed constants) | Distribution `dcterms:title` | `default-injection` (fixed value, Structural) | fixed | always present |
| P32 | during `access_url` | Distribution `dcat:accessURL` | `direct-property-mapping` (Property-Level) | 1:1 (URI) | null (optional) |
| P33 | `data_access` (during: option CV; after: **derived** open⇔during-open else closed) | Distribution `edo:dataAccess` | `direct-property-mapping` (during) + `literal-transformation` (after: value derivation, Property-Level) | 1:1 (during) / derive (after) | default (`closed` when derivation ambiguous) |
| P34 | `format[]` | Distribution `dcat:format[]` | `direct-property-mapping` (CV/IANA translation of free text later — CF2-003) | translate (CV → IANA, later) | omit |
| P35 | after `certified_with` | Distribution `edo:certifiedWith[]` | `direct-property-mapping` (CV, Property-Level) | 1:1 (CV) | omit (none certified) |
| P36 | after `pid_system` | Distribution `edo:pidSystem[]` | `direct-property-mapping` (CV, Property-Level) | 1:1 (CV) | omit |
| P37 | after `host` (repository title) | Distribution `edo:hostedBy` → **Host** node | `nesting` + `direct-property-mapping` (title) | 1:1 | omit (host optional) |
| P38 | after `license_ref` (option CV) | Distribution `edo:license` → **License** node | `nesting` + `direct-property-mapping` (value-conditional via license options) | translate (option CV) | omit (not licensed) |
| P39 | after `license_start_date` | License `time:hasBeginning` | `literal-transformation` (date, Property-Level) | cast (→date) | omit |

> **Lost (Distribution):** exact `format` free-text labels are dropped where the
> IANA media-type translation is not yet implemented (P34); the internally-vs-
> externally-accessible distinction carried by the during/after `data_access`
> derivation (P33) is a simplification of the RDMO source options.

### Host class

| # | Source (maDMP) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| P40 | `host` (repository) / `access_url` | Host `dcterms:title`, Host `edo:url` | `direct-property-mapping` (`edo:url` nullable → `existence-conditional`) | 1:1 | null (url optional) |

### License class

| # | Source (maDMP) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| P41 | `license_ref` | License `dcterms:license` | `direct-property-mapping` (value-conditional via `license_ref_options`) | translate (option CV) | omit (not licensed) |
| P42 | `license_start_date` | License `time:hasBeginning` | `literal-transformation` (date, Property-Level) | cast (→date) | omit |

## SMS → Internes Format

### Sensor class (from SMS device JSON:API `attributes`)

| # | Source (SMS) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| S1 | device `short_name` | Sensor `dcterms:title` | `direct-property-mapping` (Property-Level) | 1:1 | manual (fall back to `long_name`, then device URI) |
| S2 | device `model` | Sensor `edo:model` | `direct-property-mapping` (Property-Level) | 1:1 | omit (not modelled) |
| S3 | device `manufacturer_name` | Sensor `edo:manufacturer` | `direct-property-mapping` (Property-Level) | 1:1 | null (optional) |
| S4 | device `device_type_uri` | Sensor `dcterms:type` (SMS-CV equipment-type URI) | `direct-property-mapping` (URI passthrough) | 1:1 (URI) | manual (SMS-CV equipment type not linked to RDA CV, CF1-009-G2) |
| S5 | device `persistent_identifier` (handle) | Sensor `edo:identifier` → **Identifier** node | `nesting` + `default-injection` (type `handle`) | 1:1 (URI) | mint (handle fallback when absent) |
| S6 | device URL (`…/devices/67`) | Sensor `@id` (instance IRI) | `direct-property-mapping` (URI reuse, identifier strategy) | 1:1 (URI) | always present |

> **Lost (Sensor):** SMS carries additional device attributes not surfaced in the
> v0.2 Sensor class — e.g. `status_uri`, `inventory_number`, `created_at`/
> `updated_at`, `archived`, and the owner/group — together with the SMS-CV
> *names* for equipment types (the URI survives, the human label is dropped).

### MeasuredProperty class (from SMS device-property JSON) — one per `device_properties[]`

| # | Source (SMS) | Target (internal) | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| S7 | `property_uri` | MeasuredProperty `smscv:` property URI | `direct-property-mapping` (URI passthrough) | 1:1 (URI) | always present |
| S8 | `property_name` | MeasuredProperty `dcterms:title` | `direct-property-mapping` (Property-Level) | 1:1 | manual (fall back to property URI) |
| S9 | `unit_uri` | MeasuredProperty `edo:unit` (SMS-CV unit URI) | `direct-property-mapping` (URI passthrough) | 1:1 (URI) | omit (dimensionless) |
| S10 | `measuring_range_min` / `max` → **datasheet −40…+80** (⚠️ SMS says −80…60) | MeasuredProperty `edo:measuringRangeMin/Max` | `literal-transformation` + **override via `default-injection`** (datasheet is authority, CF1-005) | cast (→decimal) + override | datasheet (authoritative override) |
| S11 | `accuracy` = **null** → datasheet "±0.3 K @ 25 °C" | MeasuredProperty `edo:accuracy` | `default-injection` (datasheet fixed value; SMS missing, Structural) | derive (datasheet text) | datasheet (authoritative override) |
| S12 | `resolution` = **null** → datasheet 0.1 K | MeasuredProperty `edo:resolution` | `default-injection` (datasheet fixed value; SMS missing, Structural) | derive (datasheet value) | datasheet (authoritative override) |
| S13 | `sampling_media_uri` | MeasuredProperty `smscv:` sampling media URI | `direct-property-mapping` (URI passthrough) | 1:1 (URI) | manual (no sampling medium — gap) |
| S14 | `compartment_uri` | MeasuredProperty `smscv:` compartment URI | `direct-property-mapping` (URI passthrough) | 1:1 (URI) | omit |
| S15 | `aggregation_type_uri` | MeasuredProperty `edo:aggregationType` | `direct-property-mapping` (URI passthrough) | 1:1 (URI) | manual (aggregation type not in SMS-CV — gap) |
| S16 | device `device_properties[]` (many) | Sensor `sosa:observes` → **MeasuredProperty[]** | `nesting` (Structural) | n/a (structural) | omit (empty property list) |

> **Lost (MeasuredProperty):** the SMS-CV *names* for property / unit /
> sampling-media / compartment / aggregation type are dropped, leaving only the
> URIs (S7–S15); SMS `label` and any `status` are not carried. The datasheet
> overrides for range / accuracy / resolution (S10–S12) supercede the (sometimes
> contradictory, sometimes null) SMS values per CF1-005.

## R4 / neue Klassen (MeasurementSeries, SamplingPlan) — keine maschinenlesbare Quelle

These target classes have **no machine-readable source** today (gap register
#16 sampling interval, #17 measurement-series timeframe, #18 dataset↔sensor
link — `scripts/dmp/05_P05_S05_madmp-catalog-gaps.md`). Until CF2-001/CF2-002
add the needed catalog questions (or an ELN feeds it), the values are provisioned
on the EDO level:

| # | Value | Target | Pattern (Category) | 1:1? | Missing → |
|---|---|---|---|---|---|
| N1 | series title (e.g. "Weatherstation Q3-2026") | MeasurementSeries `dcterms:title` | `default-injection` (manual, EDO level) | n/a (human) | manual (EDO-level provision) |
| N2 | measurement-series timeframe `2026-07-01…2026-09-30` | MeasurementSeries `time:hasInterval` | `default-injection` (manual) — `existence-conditional` once an ELN/question source exists (gap #17) | n/a (human) | manual — `existence-conditional` later (gap #17) |
| N3 | sampling interval "PT15M" | SamplingPlan `edo:samplingInterval` | `default-injection` (manual) — `existence-conditional` once routed via RDMO/ELN (gap #16) | n/a (human) | manual — `existence-conditional` later (gap #16) |
| N4 | `sampling_interval_source` (manual / ELN / catalog) | SamplingPlan `edo:samplingIntervalSource` | `default-injection` (provenance marker, interim) | fixed | `manual` (default marker) |
| N5 | sampling media (SMS-CV URI reuse) | SamplingPlan `edo:samplingMedia` | `direct-property-mapping` (reuse SMS-CV, derived alongside #16) | 1:1 (URI) | manual |
| N6 | dataset↔sensor link | Dataset `prov:wasGeneratedBy` → Sensor / MeasurementSeries | future `reification` or direct link — gap #18 (today free text) | n/a | `existence-conditional` later (gap #18) |

> **Lost / manual (R4):** these target classes have no machine-readable source, so
> the values are provisioned **manually on the EDO level** (`default-injection`)
> rather than transformed. The dataset↔sensor link (N6) is not representable
> today (gap #18) and would move from a manual link to a concrete pattern once a
> catalog/ELN source exists.

## Notes

* The pattern identifiers above are exactly those of the **Pattern Catalogue**; downstream SHACL-rule generation can select the `CONSTRUCT` block per identifier as described for the interactive CLI.
* CV passthrough (DMP/SMS → internal keeps the CV term/URI) is uniformly `direct-property-mapping`; target-side re-encodings (free text → RDA contributor CV, items list → array, datasheet overrides) are `literal-transformation` / `default-injection`.
* `security_and_privacy` (internal-format gap) and a machine-readable dataset↔sensor link are not yet represented in the v0.2 target classes; they are listed here for completeness and would switch from `—`/`existence-conditional` to concrete patterns in a later spec revision.

## The 'Target Class' Problem

In RDF-based metadata mapping, a fundamental challenge arises when the source schema and the target schema define entity boundaries differently. 

The **'Target Class' Problem** refers to the requirement of defining the scope of a transformation rule. When using SHACL for inference or transformation (e.g., using `sh:nodeShape` to define rules), we must determine:
1.  **Which entities** are subject to the transformation (the `sh:targetClass`).
2.  **How to handle** entities that might exist in the source dataset but do not have an explicit class definition matching the expected source `sh:targetClass`.

If the source graph is loosely typed or relies on implicit property-based typing, using `sh:targetClass` might fail to capture all intended instances. Conversely, over-broad targets lead to computational overhead and potential "collisions" where properties are incorrectly mapped to entities that share the same class but exist in different contexts.

---

## Pattern 1: Property-to-Property Mapping (Simple)

This pattern represents the simplest form of transformation: a direct mapping of a literal value from a source property in `oemetadata` to a target property in `dcat`.

### Description
We want to map the title field of a dataset entry defined in the `oemetadata` schema to the `dcterms:title` field within the `dcat:Record` (or `dcat:Dataset`) structure. This does not involve structural changes, only the projection of a value from a specific property path to a new predicate.

### SHACL Transformation Rule

```turtle
@prefix sh: [http://www.w3.org/ns/shacl#](http://www.w3.org/ns/shacl#) .
@prefix dcterms: [http://purl.org/dc/terms/](http://purl.org/dc/terms/) .
@prefix oemetadata: [https://github.com/OpenEnergyPlatform/oemetadata/blob/develop/oemetadata/v2/v20/context.json] .
@prefix dcat: [http://www.w3.org/ns/dcat#](http://www.w3.org/ns/dcat#) .

# Pattern: Direct Property Mapping
# This shape assumes the subject is an instance of an Oemetadata Dataset
ex:TopElementToDatasetRule
    a sh:NodeShape ;
    sh:targetSubjectsOf owl:versionInfo ;
    sh:rule [
        a sh:SPARQLRule ;
        sh:construct """
            PREFIX dac4: <http://datacite.org/schema/kernel-4#>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            CONSTRUCT {
                $this a dcat:Dataset ;
                $this dct:title ?title .
            }
            WHERE {
                $this owl:versionInfo ?_ ;
                $this  dct:title ?title .
            }
        "" ;
    ] .

---

## Interactive Creation of Transformation Specifications

The script `src/omi/crosswalks/interactive_creation.py` implements the CLI-guided workflow from `planning/Metadata Crosswalk - Interactive Creation.md`. It interviews the user about their data and the target schema — in data terms, never in pattern jargon — and derives the applicable patterns from the answers.

### Usage

```bash
python -m omi.crosswalks.interactive_creation new \
    --name oemetadata_to_dcat --source oemetadata-2.0.4 --target dcat-3 \
    --direction uplift

python -m omi.crosswalks.interactive_creation resume oemetadata_to_dcat
```

The interview is resumable: every answer is written to `<name>.cw-session.json`. At every question `b` goes back one step (inside a key's question group it restarts that group; at the group's first question it returns to the previous key, whose decisions are discarded for a clean redo), `s` skips (recorded as TODO), `?` prints an explanation, and `q` saves and quits.

### Understandability Features

* **Explicit questions.** The routing question spells out what property / container / class means in data terms with source examples; every pattern choice prints a one-line hint underneath each option, so the distinction is visible without pressing `?`. Guard, identifier, and constraint questions list their options with hints the same way.
* **Hierarchical target proposals.** Target properties and classes are shown **grouped by where they live in the target schema** (e.g. DataCite properties under *Resource — core attributes* vs. *GeoLocation — geographic attributes*), not as a flat list. The group label acts as the taxonomical place of each proposal.
* **Recommendation with neighbourhood.** When the project crosswalk (`OEMeta_mappings.md`, Patterns Map) recommends a target term for a source key, the header names the recommendation, its group, and its **neighbours** (the sibling terms of the same group), and the entry is marked inline; plain Enter accepts it.
* **Mandatory-attribute hints.** At the constraint check, well-known mandatory attributes of the created target class (per DCAT-AP / DataCite 4.x, e.g. DataCite `Resource` requires identifier, creator, title, publisher, publicationYear, resourceType) are listed, marked as already mapped or still needed, with an explicit *please verify against the target profile* note.

### Question → Pattern Mapping

| Stage | CLI Question | Answer leads to |
| --- | --- | --- |
| Setup | source / target / direction / scope | session metadata |
| Per key | What kind of information is it (property / container / class)? | routes to Q1/Q4/Q6 question sets |
| Q1 (class) | How does this key correspond to target classes? | `direct-class-mapping`, `class-specialisation` (with value→class lookup), `class-generalisation`, `literal-to-node-promotion` |
| Q4 (property) | Which target situation applies? | `direct-property-mapping`, `literal-transformation` (with cast note), `inverse-property-mapping`, `literal-to-node-promotion` (with value→predicate lookup) |
| Q5 (guard) | Should the mapping always apply? | `type-conditional`, `value-conditional`, `existence-conditional`, or no guard |
| Q6 (container) | How is the container represented? | `nesting`, `flattening`, `reification` (with child properties) |
| Q7 (identifier) | How is the target node identified? | URI minting template / blank node / source IRI |
| Constraint check | Which mandatory attributes are missing? | `default-injection` (fixed value or `{parent}` template) — the counterpart of `existence-conditional` |
| Review | Accept and emit? | writes `<name>.cw.yaml` |

### Emitted Artifacts

* **`<name>.cw-session.json`** — the full interview state (resumable, diffable).
* **`<name>.cw.yaml`** — the transformation specification, grouped into `classes`, `properties`, `containers`, `defaults`, and `todo` sections; each entry carries its pattern identifier from the catalogue above so downstream SHACL-rule generation (see below and the TTL files in this directory) can select the right `CONSTRUCT` block template per pattern.

### From Specification to SHACL Rules

`src/omi/crosswalks/generate_shacl.py` turns a finished specification into a SHACL SPARQL-rule skeleton:

```bash
uv run generate_shacl.py experiment_01        # reads experiment_01.cw.yaml -> experiment_01.ttl
uv run generate_shacl.py experiment_01 --out my_rules.ttl
```

One `sh:NodeShape` with one `sh:SPARQLRule` is emitted per specification entry, following the structure of the hand-written crosswalks in this directory (e.g. `oemetadata_2-0-4_to_dcat_3.ttl`). The `CONSTRUCT`/`WHERE` body is selected by the pattern identifier:

| Pattern | Generated rule body |
| --- | --- |
| `direct-property-mapping` | `$this <target> ?value` from `$this oem:<key> ?value` |
| `literal-transformation` | adds `BIND(<cast>(?value) AS ?cast)` parsed from the cast note (e.g. `string -> xsd:date`) |
| `inverse-property-mapping` | direction reversed: `?value <target> $this` |
| `literal-to-node-promotion` | `VALUES` lookup table from the spec's `lookup` |
| `nesting` | creates a child node (`?node a <class>` with the child properties), linked via a parent link property; node URI minted from the identifier strategy |
| `flattening` | child properties attached directly to `$this` |
| `reification` | child node as association (`?assoc`), blank-node identifier |
| `default-injection` | `FILTER NOT EXISTS` guard plus a fixed value or `{parent}` URI template |

The output is a **skeleton**: rule structure and pattern bodies are generated mechanically, but two modelling decisions remain open and are flagged with `# TODO` comments at the top of the file:

1. **Source representation** — which IRIs represent the source keys (the generated rules assume `oem:<key>` predicates under `https://openenergyplatform.org/oemetadata/2.0.4/#`; adjust the namespace to whatever your JSON -> RDF step produces).
2. **Target vocabulary binding** — DataCite terms are mapped to common RDF equivalents (`title` -> `dcterms:title`, `pointLatitude` -> `geo:lat`, ...) where one exists; anything else becomes a `target:` placeholder to replace.

Hand-finish those bindings, then validate and execute the rules with pySHACL's advanced features (`pyshacl --advanced` supports SHACL Rules), and integrate the file like the other crosswalks in this directory.
