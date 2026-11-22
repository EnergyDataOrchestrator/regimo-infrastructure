# inputs/ — pipeline input corpus for the fuseki-proto tool

Copied from the research testbed
`projecting_spaces/EDO/Artefacts/07_Fragments/scripts/` (2026-11-22) so that the
agnostic trip (`fuseki-proto agnostic-trip run`) and the CF2-003 `trip` are
self-contained inside `regimo-infrastructure`. The testbed remains the working
area of the research cards; **this copy is what the tool consumes**.

| Directory | Contents | Used by |
| :--- | :--- | :--- |
| `dmp/` | maDMP exports (RDMO projects, e.g. `measurement_02/Measurement_02-13.json`), RDMO answers, mapping spec, validator | `trip`, `agnostic-trip` (`--dmp` default) |
| `sms/` | SMS device 67 record + device-property records (JSON:API) | `trip`, `agnostic-trip` (`--sms-device` / `--sms-property` defaults) |
| `trafos/` | LinkML Map files (`dmp-to-internal`, `sms-to-internal`, rules P1–P47 / S1–S16) + the `patterns.md` catalogue | `agnostic-trip` (`--dmp-map` / `--sms-map` defaults) |
| `linkml/` | Internal-format / maDMP / SMS LinkML schemas (single source of the internal format) + json-schema crate | `agnostic-trip` (schema-driven serialisation), `trip` |
| `internal-format/` | Internal-format spec, linkage strategy, linked-instance example | documentation / frontend artifact copies |
| `ro-crate/` | CF2-006 weather-station RO-Crate example | `crate` command reference |

The tool's defaults point here (`inputs/…`); everything is overridable via CLI
options — see `tool/README.md`.
