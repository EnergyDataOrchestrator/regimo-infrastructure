# fuseki-proto — Apache Jena Fuseki prototype

Prototype for the **Jena / RDF / SHACL path** of the storage decision
(fragment `02_LinkML_Entscheidung` / card `CF2-002`): spin up a triplestore,
load an internal-format instance graph, and validate it against the **project
claim** SHACL shapes.

Choice rationale — this is the "semantically pure" alternative from CF2-002's
*How LinkML Influences the Decision*:
> **Jena (RDF/SPARQL) Path:** If you use Jena, you leverage LinkML's `gen-owl`
> or `gen-shacl` tools … the translation from your schema to RDF is direct,
> and your validation happens via SHACL.

It complements `../../projecting_spaces/EDO/Artefacts/07_Fragments/scripts/trafos/patterns.md` (the SHACL *transformation* patterns)
and the internal-format spec that is its source of truth:
`../../projecting_spaces/EDO/Artefacts/07_Fragments/scripts/internal-format/04_P04_S04_internal-format-spec.md` (§2 entities, §3.2
classes, §3.3 controlled vocabularies) and the LinkML schema from CF1-007
(`../../projecting_spaces/EDO/Artefacts/07_Fragments/scripts/linkml/05_P05_S05_internal-format-schema.yaml`).

## Layout

```
fuseki-proto/
├── docker-compose.yml            # Fuseki 5 Full (TDB2 + in-memory datasets); container port 3030, NO host publish
├── docker-compose.override.yml   # AUTO-MERGED: sole host publish, remaps to 3031 (avoids the ORKG Fuseki)
├── docker/
│   ├── Dockerfile                # builds Fuseki **Full** FROM SOURCE (Apache ships no registry image)
│   ├── download.sh               #   fetches apache-jena-fuseki-<ver>.zip from Maven Central (checksummed)
│   ├── entrypoint.sh             #   runs the distribution's `fuseki-server` launcher (web UI + /$/admin)
│   └── log4j2.properties         #   logging config baked into the image
├── config/
│   ├── projects-ds.ttl           # dataset assembler for /projects (TDB2) — auto-scanned by Full
│   └── shapes-ds.ttl             # dataset assembler for /shapes (in-memory) — auto-scanned by Full
├── shapes/
│   └── project-claim-shapes.ttl  # SHACL node shapes for a Project claim
├── data/
│   ├── sample-project.ttl        # spec §4 example translated to Turtle
│   └── backups/                  # created by `fuseki-proto backup` (git-ignored)
└── tool/                         # src-layout Python CLI (`pip install -e tool`);
    └── src/fuseki_proto/         #   lifecycle + backup/restore/load/wipe + CF2-003
                                  #   round trip (`trip.py`) and the CF2-004 map-driven
                                  #   round trip (`agnostic_trip.py`, see tool/README.md)
```

> **Port:** Docker Compose auto-loads `docker-compose.override.yml`, so the
> prototype serves on host port **3031** by default. Host `3030` stays free for
> the system-managed Jena Fuseki that serves the ORKG database
> (`/Library/LaunchDaemons/org.apache.jena.fuseki.plist`). `fuseki-proto`
> defaults to `--port 3031`.

## Run

Apache Jena does **not** publish a pre-built Fuseki image to any registry (the
`stainless/jena-fuseki` reference this prototype used initially no longer
exists on Docker Hub). The image is therefore **built locally from source** via
`docker/`. It installs the **Fuseki Full** distribution (the
`apache-jena-fuseki-<ver>.zip` webapp), pinned in the `Dockerfile`. Fuseki Full
provides the **web UI** and the **admin endpoints** (`/$/ping`, `/$/server`,
`/$/backup`, …) and **auto-scans `$FUSEKI_BASE/configuration/`** for dataset
assemblers, so `config/*.ttl` is picked up on boot without any `--config`.

The CLI builds automatically on start:

```bash
fuseki-proto start            # = docker compose build && docker compose up -d, then seed /shapes
```

or equivalently, manually:

```bash
docker compose build          # build once (only needed after JENA_VERSION changes)
docker compose up -d          # http://localhost:3031/  (web UI)
```

Open **http://localhost:3031/** for the Fuseki web UI (both datasets listed), and
`http://localhost:3031/$/ping` for liveness.

Two ready-made datasets:
* **`/projects`** — TDB2 (persisted via `fuseki-data` volume); load the sample
  with the CLI or curl:
  ```bash
  fuseki-proto load data/sample-project.ttl     # -> /projects (default graph)
  # or:
  curl -s -X POST http://admin:edo-proto@localhost:3031/projects/data \
       -H 'Content-Type: text/turtle' \
       --data-binary @data/sample-project.ttl
  ```
* **`/shapes`** — in-memory read side. `fuseki-proto start` re-seeds it from
  `shapes/project-claim-shapes.ttl` on every start (like the assembler alone, the
  CLI keeps the read side in lock-step with file edits). Query it via the UI or
  `curl http://localhost:3031/shapes/query?query={...}`.

> **Web UI + admin endpoints available.** This prototype runs the Apache Jena
> *Fuseki **Full*** distribution — the web UI at `http://localhost:3031/` and the
> admin endpoints (`/$/ping`, `/$/server`, `/$/backup`) are enabled. The compose
> `healthcheck` probes `/$/ping`. `fuseki-proto` `start`/`status`/`ping` probe a
> data-service endpoint (`/<dataset>/query`) so the CLI also works unchanged;
> interact via the data-service endpoints (`/projects/query`, `/projects/data`,
> ...) the UI, or the CLI.

## Validate the claim

The shapes are self-contained (they do not import external vocabularies), so
SHACL validation is best done host-side with `pyshacl` against the same file
(Fuseki Full also exposes a `/projects/shacl` validation endpoint, but `pyshacl`
is the simplest route for the prototype):

```bash
pyshacl -s shapes/project-claim-shapes.ttl \
        -d data/sample-project.ttl \
        -e shapes/project-claim-shapes.ttl
```

`/shapes` is a convenience to browse the shape triples with SPARQL inside
Fuseki; the authoritative constraint file remains `shapes/project-claim-shapes.ttl`
and the authoritative validation is the `pyshacl` invocation above.

## What the claim shapes assert (spec §3.2)

| Shape | Enforces |
|---|---|
| `edo:ProjectShape` | title (req, 1), optional description, `language ∈ {eng,deu}`, one interval w/ dates, exactly-one `dmpId` (typed Identifier), ≥1 contact Person, contributions, costs |
| `time:IntervalShape` | begin (req) + end as `xsd:date` |
| `edo:IdentifierShape` | value (req), type ∈ {doi,handle,ark,urn,url,other} |
| `foaf:PersonShape` | name (req), optional mbox / identifier |
| `edo:ContributionShape` | agent Person (req), role ∈ RDA maDMP contributor-type CV |
| `edo:CostShape` | title (req), optional decimal value + currency |

## Notes / open items

* Shapes cover the **Project claim (top-down)**. Dataset / Distribution /
  Sensor claims remain future work (extend `shapes/` per class when the
  transformation CF2-003 feeds instance data).
* `data/sample-project.ttl` reflects the spec §4 example. The dataset↔sensor
  link is still only in free text (`PIDINST: …`, gap #18); once it becomes a
  typed edge the Dataset/Sensor shapes should assert `prov:wasGeneratedBy`.
* IRIs are placeholders (`urn:` / `edo:`), per spec open item 6 — concrete IRIs
  are fixed by CF1-007 / CF2-004.
* The CF2-003 transformation realisation lives in `../../projecting_spaces/EDO/Artefacts/07_Fragments/scripts/trafos/` (catalogue
  `patterns.md` + realisation `README.md`) and is executed by this tool's
  `trip` command (`fuseki-proto trip run`) — see `tool/README.md`. The CF2-004
  **second way** (same transformation, logic in LinkML Map files) is executed
  by `agnostic-trip` (`fuseki-proto agnostic-trip run`), writing to
  `data/agnostic-trip/<timestamp>/`. Both share the `/projects` dataset; each
  run wipes it first.
