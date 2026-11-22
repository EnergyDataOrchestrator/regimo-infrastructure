# RO-Crate: `cf2-006-weatherstation.crate`

This directory is an RO-Crate 1.1 package generated from the EDO internal format (card CF2-006) for the linked DMP+SMS instance **Weatherstation Q3-2026**.

## Contents

- `ro-crate-metadata.json` — the RO-Crate metadata file (root `Dataset` with name, description, datePublished and license, the packaged graph as a `File` data entity, and the sensor / measured properties as contextual entities).
- `data/project-graph.jsonld` — the packaged internal-format graph (`Project > Dataset prov:wasGeneratedBy Sensor, Sensor sosa:observes MeasuredProperty[]`).
- `validation-report.json` — the generator's structural self-check.

## How it was produced

Run `fuseki-proto crate generate` (see `../fuseki-proto/tool/src/fuseki_proto/ro_crate.py`), which uses the `rocrate` (ro-crate-py) library on the linked internal-format instance `../internal-format/linked-instance.example.json`.

## Validate

Validate the **whole directory** (not just the metadata file) with an RO-Crate validator such as `nova-crate` (spec-v1.1).
