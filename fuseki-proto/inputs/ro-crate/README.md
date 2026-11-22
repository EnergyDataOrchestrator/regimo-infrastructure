# RO-Crate generation from the EDO internal format (CF2-006)

Card: `../../../05_Cards/CF2-006.md` — **"Generierung RO Crate aus internem
Format"**.

This directory documents how an **RO-Crate 1.1** is generated from the EDO
internal format (the linked DMP+SMS pivot graph, card CF2-005) and holds the
committed **example crate**.

## The generator

`../fuseki-proto/tool/src/fuseki_proto/ro_crate.py` implements the
`fuseki-proto crate generate` command. It uses the **`rocrate`** library
(`ro-crate-py`, pinned `0.16.0` in `../fuseki-proto/tool/pyproject.toml`) to
build and serialise the crate, so `ro-crate-metadata.json` is spec-conformant
by construction.

```bash
.venv/bin/fuseki-proto crate generate            # default input below
.venv/bin/fuseki-proto crate generate --input <instance.jsonld> --out <dir>
```

**Input** (default): `../internal-format/linked-instance.example.json` — the
linked DMP+SMS internal-format instance (weatherstation device 67, five
measured properties) produced as the CF2-005 deliverable. This satisfies the
CF2-006 precondition "the internal format contains linked DMP and SMS data".

**Output** (a self-contained crate directory):

| File | Role |
|---|---|
| `ro-crate-metadata.json` | RO-Crate 1.1 metadata file — root `Dataset` (`@id ./`) with `name`, `description`, `datePublished`, `license` (→ a contextual `CreativeWork`), plus the packaged graph as a `File` data entity and the Sensor / MeasuredProperties / contact as contextual entities. |
| `data/project-graph.jsonld` | The packaged internal-format graph (a `File` data entity, `encodingFormat` JSON-LD, `conformsTo` the EDO internal-format schema). |
| `README.md` | Per-crate documentation. |
| `validation-report.json` | The generator's structural self-check (5 checks: root dataset, root required properties, every `File` resolves in-crate, DMP-SMS link reflected, input preserved). |

The generator **zips** the finished crate directory into `<crate-dir>.zip` (the
zip's root is the crate directory, so it can be uploaded/extracted and
validated as-is by nova-crate).

```bash
.venv/bin/fuseki-proto crate generate --out /tmp/my-crate
# -> /tmp/my-crate/   (crate directory)
# -> /tmp/my-crate.zip (programmatically packaged archive)
```

## The example crate

`cf2-006-weatherstation.crate/` is the committed example — a crate for the
linked weatherstation instance. It round-trips through `rocrate`
(`ROCrate(crate_dir)`) and passes the generator's structural self-check
`5/5`.

## Validation

The generator's `validation-report.json` is only a **structural** self-check.
For full RO-Crate 1.1 spec conformance, load the **whole crate directory** into
an RO-Crate validator — the project uses the nova-crate editor:

- <https://novacrate.datamanager.kit.edu/editor>

(The editor must be pointed at the whole directory, not a single
`ro-crate-metadata.json` pasted into a form — RDF-file data entities are only
resolvable when the directory is validated as a crate.)

## Related

- Card CF2-006 (AC + activity log).
- Linkage strategy / linked instance: `../internal-format/linkage-strategy.md`,
  `../internal-format/linked-instance.example.json` (CF2-005).
- The internal-format schema the packaged graph conforms to:
  `../linkml/05_P05_S05_internal-format-schema.yaml`.
- The provenance crate for the generated JSON Schema (F11), a separate RO-Crate
  concern: `../linkml/05_P05_S05_internal-format-json-schema-crate/`.
