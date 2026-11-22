# Provenance crate: `05_P05_S05_internal-format.schema.json` (F11)

This directory is a RO-Crate 1.1 (`ro-crate-metadata.json`) that documents the
**provenance of one version** of the generated JSON Schema
`05_P05_S05_internal-format.schema.json` — the regeneration performed on
2026-11-19 to close finding **F11** ("the CF2-004 schema edits make the
generated JSON Schema stale; regenerate before the next JSON-Schema consumer",
see `../trafos/README.md`, section 13).

## What the crate contains

**Copies** (the files that *are* the version, plus everything needed to
repeat the generation — the crate is self-sufficient for the generation
process):

| File | Role |
|---|---|
| `05_P05_S05_internal-format.schema.json` | The generated JSON Schema (this version). Draft 2019-09, `metamodel_version 1.11.0`. |
| `05_P05_S05_internal-format-schema.yaml` | The LinkML schema — the direct source this version was generated from. |
| `reproduce.sh` | Shell script repeating the generation from the archived source; run from the crate root (`sh reproduce.sh`). Verified 2026-11-19: output byte-identical to the archived JSON Schema. |
| `environment/pip-freeze.txt` | Full `pip freeze` of the repository `.venv` used for the run (Python 3.12.12, Darwin arm64; `linkml==1.11.1`, `linkml-runtime==1.11.1`, pinned for `linkml-map==0.5.2` per F8), with the interpreter/platform in the header; installable via `pip install -r`. Copied because the generating library and its dependencies are not referenceable from the repository. |
| `environment/linkml-types.yaml` | The `linkml:types` module as resolved during the run — for the pinned versions it is the bundled `linkml_runtime/linkml_model/model/schema/types.yaml` of linkml-runtime 1.11.1, the resolution target of the source's `imports: linkml:types`. Copied because it lives inside the installed library. |

**Snapshot copies** (files copied from the repository into the crate so that
the crate is a self-contained, validatable package — every data entity typed
`File` must resolve inside the crate; each snapshot's `description` records
the git blob of the copied file):

| File (in `references/`) | Role |
|---|---|
| `05_P05_S05_madmp-schema.yaml` | LinkML maDMP schema — source-side sibling (CF1-007 family); its CV value sets are mirrored by the internal-format enums. |
| `05_P05_S05_sms-schema.yaml` | LinkML SMS schema — source-side sibling; the Sensor/MeasuredProperty part is fed by the SMS device record it models. |
| `patterns.md` | Transformation rules (P1–P42, S1–S16); compiled into the two LinkML Maps (commit `62f404b`). |
| `dmp-to-internal.linkml-map.yaml` | LinkML Map DMP → internal (CF2-004); input to the schema reconciliation. |
| `sms-to-internal.linkml-map.yaml` | LinkML Map SMS → internal (CF2-004); input to the schema reconciliation. |
| `trip.py` | Hand-coded realisation (CF2-003) — the behavioural reference of the reconciliation. |
| `agnostic_trip.py` | Map-driven realisation (CF2-004) consuming the schema together with the maps. |

**References** (documents left outside the crate as `CreativeWork` entities —
nova-crate flags only `File`-typed data entities against the crate contents,
and these markdown documents stay where they are maintained):

- `../../internal-format/04_P04_S04_internal-format-spec.md` — specification
  v0.2 (CF1-006) the format is derived from.
- `../trafos/README.md` — documentation of the reconciliation (§9) and the
  findings catalogue with F11 (§13).
- `../../../../05_Cards/CF1-006.md`, `CF1-007.md`, `CF2-003.md`,
  `CF2-004.md` — cards in which the format, the schemas, the realisations and
  the finding were decided and logged.

> Trade-off: the `references/` snapshots freeze the files at the crate date
> (their git blobs are recorded in the metadata for traceability). If a
> referenced file changes, either refresh the snapshot or treat this crate as
> the provenance record of that historical state — it documents the version,
> not the moving target.

## How the version came about (graph summary)

1. **Specification** (CF1-006) → **LinkML schema** (CF1-007, commit
   `397a789`/`09a25eb`), first generated as JSON Schema with linkml 1.12.0.
2. **CF2-004 schema reconciliation** (`e8b6ee8`): slot mappings/descriptions
   of the LinkML schema were aligned with the CF2-003 realisation
   (`time:hasEnd`, `license_start_date = time:hasBeginning`, IANA media-type
   IRIs per P34, SMS CV mappings S7/S8/S13/S14). This made the previously
   generated JSON Schema stale → F11.
3. **This version**: `.venv/bin/gen-json-schema …internal-format-schema.yaml`
   (linkml **1.11.1**, pinned for linkml-map 0.5.2 per F8) run 2026-11-19
   18:34 +01:00, recorded as `CreateAction` `#gen-json-schema-run-20261119T1834`
   with `instrument`, `object`, `result`, `startTime`/`endTime`.

## Repeating the generation from the crate alone

The provenance graph is closed for the generation step — from the crate
contents it is possible to repeat the process end to end:

1. create an environment matching `environment/pip-freeze.txt`
   (`pip install -r environment/pip-freeze.txt`; the run used Python 3.12.12);
2. run `sh reproduce.sh` in the crate root — it invokes
   `gen-json-schema 05_P05_S05_internal-format-schema.yaml >
   05_P05_S05_internal-format.schema.json`;
3. the output is byte-identical to the archived
   `05_P05_S05_internal-format.schema.json` (verified 2026-11-19).

The relationship chain in `ro-crate-metadata.json` encodes this:
`#gen-json-schema-run-20261119T1834` (`CreateAction`) has `instrument` →
`#linkml-gen-json-schema` (SoftwareApplication, version 1.11.1) and
`reproduce.sh`, `object` → the LinkML source copy, `result` → the JSON Schema
copy; `reproduce.sh` and the software `dcterms:requires` the environment
snapshot, and the LinkML source `dcterms:requires`
`environment/linkml-types.yaml` (its import resolution).

Note on completeness: the linkml library itself is not copied into the crate
(its version is recorded on the SoftwareApplication and its dependency
closure is pinned in the freeze). If bit-level replication of the
environment is required, create the environment from the freeze on the same
platform (Python 3.12.12, Darwin arm64) as recorded in the header.

Version identity for reproducibility:

- predecessor blob: `14c33a8b9064c8d81d413f45c3dbc3baea7f5917`
  (generated with linkml 1.12.0, `metamodel_version 1.12.0`, commit `09a25eb`)
- this version's blob: `d768c94a65ca824260495f6f67c48ae8fd31d2cc`
- differences: the reconciliation descriptions, one generator-behaviour change
  (`data_access`: `anyOf` with `null` → direct `$ref`), and the
  `metamodel_version` downgrade caused by the pinning.

## Conventions and caveats

- Provenance vocabulary: schema.org (`CreateAction`, `object`/`result`/
  `instrument`/`startTime`/`endTime`) plus PROV terms (`wasGeneratedBy`,
  `wasDerivedFrom`) and `dcterms:requires` via the additional `prov` and
  `dcterms` context entries.
- License: the Root Data Entity links via `license` to the contextual entity
  `https://spdx.org/licenses/MIT` (RO-Crate 1.1 root requirements: license
  SHOULD link to a contextual entity with name and description). The crate is
  under the same MIT License as the EDO repository (repository-root `LICENSE`,
  Copyright (c) 2026 Mohamed Anis Koubaa).
- External documents (spec, trafos README, cards) are referenced with
  repository-relative `@id`s as `CreativeWork` entities (not data entities);
  every `File`-typed data entity, by contrast, physically resides in the
  crate so that RO-Crate validators (e.g. nova-crate,
  `spec-v1.1/dataEntityFileError`) pass when the whole crate directory is
  validated. Note: validating `ro-crate-metadata.json` in isolation (e.g.
  pasting it into a web form) cannot resolve any in-crate file — always
  validate the directory.
- The copies are snapshots; if the schema changes again, either refresh this
  crate or create a new one per version (one crate per version keeps the
  provenance history explicit).
