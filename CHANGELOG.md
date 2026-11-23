# Changelog

All notable changes to the EDO infrastructure repository are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/); versioning: SemVer.

## [0.2.0] - 2026-11-23

### Fixed
- `trip` / `agnostic-trip` verify stages now `DROP SILENT` their replay named graphs, so no leftover Weatherstation data stays in the Fuseki `/projects` dataset between runs (CF1-013).

## [0.1.0] - 2026-11-23

First release — graph database prototype, transformation tooling and local RDMO instance.

### Added
- `fuseki-proto` stack: Apache Jena Fuseki (TDB2) compose setup with the `/projects` and `/shapes` datasets, SHACL prototype and `project-claim-shapes.ttl`.
- `fuseki-proto` maintenance CLI (`tool/`): lifecycle (start/stop/status/backup/restore/wipe), CF2-003 round trip (`trip`), map-driven agnostic trip (`agnostic-trip run/transform`), linked-instance serialiser (`agnostic-trip instance`) and RO-Crate generation (`crate generate`).
- LinkML Maps DMP→internal and SMS→internal (catalogue rules compiled into `case()` expressions), internal-format schema (v0.2) with funder/funding and Person/contact derivations.
- `edo-infra` maintenance CLI (`scripts/`, src layout, Click): `install-exporter`, `create-project-from-doi`, `reset-projects`, `add-dataset` (papers CSV) — Django commands re-execute under the RDMO instance environment.
- Local RDMO dev instance config (`Servers/rdmo-app` submodule): maDMP exporter plugin route, settings, fixtures.
- Kafka broker configuration (single-node, `edo.projects.v1` topic consumers downstream).
