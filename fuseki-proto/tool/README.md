# fuseki-proto-tool

Maintenance CLI for the EDO/Regimo Fuseki prototype (see the parent
`../README.md`). Wraps `docker compose` for lifecycle and the Fuseki HTTP
admin/data endpoints for backup/restore/load, with a small stdlib-only
`urllib` HTTP client (the only third-party dependency is `click`).

## Install

```bash
cd tool
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

## Usage

> **Port:** the CLI defaults to `--port 3031`, matching the host binding in
> `docker-compose.yml` (the prototype's non-conflicting host port).
> Host `3030` is left for the system-managed Jena Fuseki that serves the ORKG
> database. Point `fuseki-proto` at that other instance explicitly with
> `--port 3030` / `--dataset orkg` if you ever need to.

```bash
# Lifecycle (via docker compose)
fuseki-proto start          # build the image if needed, bring the container up, wait for ping
fuseki-proto stop           # stop the container gracefully (TDB2 lock!)
fuseki-proto status         # container + live-server/dataset overview

# Data maintenance (Fuseki HTTP)
fuseki-proto ping           # run a trivial query on a dataset (liveness)
fuseki-proto backup         # dump a dataset -> backups/ (now that Fuseki is Full,
                           #   this could use /$/backup instead, but the CONSTRUCT
                           #   dump round-trips fine and needs no code change)
fuseki-proto list-backups   # files in backups/
fuseki-proto restore <file> # empty the dataset then re-upload a backup/ttl dump
fuseki-proto load <file.ttl> [--graph <name>]   # POST a graph into /projects
fuseki-proto wipe [--yes]   # CLEAR ALL over /projects (destructive!)

# CF2-003 round trip (see ../../../projecting_spaces/EDO/Artefacts/07_Fragments/scripts/trafos/README.md)
fuseki-proto trip transform   # DMP + SMS -> internal-format graph (scenario 1)
fuseki-proto trip store       # store it in /projects + SPARQL/SHACL check (scenario 2)
fuseki-proto trip verify      # dump /projects, replay, field-level checks (scenario 3)
fuseki-proto trip run         # all three stages, artifacts in ../data/trip/<ts>/

# CF2-004 round trip, map-driven (see ../../../projecting_spaces/EDO/Artefacts/07_Fragments/scripts/trafos/README.md §8–§13)
fuseki-proto agnostic-trip transform   # same scenarios, logic from the LinkML Maps
fuseki-proto agnostic-trip store       # (default: latest agnostic-trip artifacts)
fuseki-proto agnostic-trip verify      # replay graph urn:edo:agnostic-trip:replay
fuseki-proto agnostic-trip run         # artifacts in ../data/agnostic-trip/<ts>/

# CF2-006 RO-Crate generation from the internal format (see ../ro_crate.py docs)
fuseki-proto crate generate            # linked internal format -> RO-Crate directory
```

The prototype runs **Fuseki Full**, so the web UI is on `http://localhost:3031/`
and the admin endpoints `/$/ping`, `/$/server`, `/$/backup` are available. The
CLI's `start`/`status`/`ping` probe a data-service `/query` endpoint (which
works under both server-only and Full), and `backup` uses a CONSTRUCT dump — so
the tool works unchanged; the Full admin endpoints are just extra conveniences.

Sensible options are derived from `docker-compose.yml`
defaults and can be overridden (e.g. `--port`, `--user`, `--password`,
`--service`, `--dataset`, `--compose-dir`, `--backups-dir`). Run
`fuseki-proto --help` / `fuseki-proto <cmd> --help` for details.

## The `trip` command (CF2-003)

`trip.py` (module `fuseki_proto.trip`) realises the three acceptance scenarios
of card CF2-003 end-to-end against the maDMP export
`projecting_spaces/EDO/Artefacts/07_Fragments/scripts/dmp/measurement_02/Measurement_02-13.json` and the SMS device 67
records: transform (applies the `trafos/patterns.md` catalogue), store (into
`/projects`, with pyshacl validation when available — install it into the venv
with `uv pip install pyshacl`, it is optional), verify (dump → replay graph →
41 field-level checks against the original sources + triple-count equality).
Sources are overridable (`--dmp`, `--sms-device`, repeatable `--sms-property`).
Artifacts (`project-graph.ttl`, `roundtrip-dump.ttl`, `trip-report.json`) land
in `../data/trip/<timestamp>/`; the exit code is 0 only if every round-trip
check passes (the SHACL verdict is recorded in the report but does not fail the
run). Full documentation: `../../../projecting_spaces/EDO/Artefacts/07_Fragments/scripts/trafos/README.md`.

## The `agnostic-trip` command (CF2-004)

`agnostic_trip.py` (module `fuseki_proto.agnostic_trip`) performs the **same
round trip as `trip`**, but the transformation logic is **not** in the code: it
lives in the two LinkML Map files
`projecting_spaces/EDO/Artefacts/07_Fragments/scripts/trafos/dmp-to-internal.linkml-map.yaml` (rules P1–P42) and
`projecting_spaces/EDO/Artefacts/07_Fragments/scripts/trafos/sms-to-internal.linkml-map.yaml` (rules S1–S16), which compile
the `trafos/patterns.md` catalogue. The tool only wires the linkml-map
`ObjectTransformer` (`--dmp-map` / `--sms-map` override the map files) and
serialises the transformed objects into Turtle, driven entirely by the
internal-format schema (`projecting_spaces/EDO/Artefacts/07_Fragments/scripts/linkml/05_P05_S05_internal-format-schema.yaml`:
slot `mappings` → predicates, ranges → datatyping, `class_uri` → node types).

Stage and CLI shape are identical to `trip` (`transform` / `store` / `verify` /
`run`, same connection options, same source overrides plus `--dmp-map/--sms-map`),
with two differences:

* artifacts land in `../data/agnostic-trip/<timestamp>/` and the report is
  `agnostic-trip-report.json` (adds map files, linkml-map version, compiled
  derivations, transformed objects);
* the replay graph is `<urn:edo:agnostic-trip:replay>`.

Dependencies: `linkml-map` (pinned 0.5.x — the specification language is the
0.5 datamodel) and `linkml-runtime` in addition to `click`; `pyshacl` optional.
The agnostic graph is isomorphic to the `trip` graph modulo 4 documented
`rdf:type` triples (the serialiser types every class node; CF2-004 §11 of
`trafos/README.md`).

## The `crate` command (CF2-006)

`ro_crate.py` (module `fuseki_proto.ro_crate`) generates a self-contained
RO-Crate 1.1 from the **internal format** — the linked DMP+SMS pivot graph. The
generator uses the **`rocrate`** library (`ro-crate-py`, pinned 0.16.0) to build
and serialise the crate, so the metadata is spec-conformant by construction; only
the internal-format field extraction reads the compact JSON-LD directly.

```bash
fuseki-proto crate generate            # default input: the CF2-005 linked instance
fuseki-proto crate generate --input <internal-format.jsonld>
fuseki-proto crate generate --out <crate-dir>
```

The output directory contains `ro-crate-metadata.json`, the packaged graph as a
`File` data entity (`data/project-graph.jsonld`), `README.md`, and
`validation-report.json` (the generator's structural self-check). The generator
then **zips the finished crate directory** into `<crate-dir>.zip`. Dependency:
`rocrate>=0.16.0`. To fully validate a crate against the RO-Crate 1.1 spec, load
the whole directory into an RO-Crate validator (e.g. the nova-crate editor).
