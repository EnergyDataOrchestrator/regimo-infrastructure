# edo-infra

Maintenance CLI for the EDO **infrastructure** parts that live outside Docker:
the local RDMO dev instance (`Servers/rdmo-app`), its plugins and the RDMO
project XML fixtures (`fixtures/rdmo/`).

The commands that touch the RDMO database (Django ORM) re-execute themselves
with the instance environment (`Servers/rdmo-app/env/bin/python`); the outer
CLI itself only needs Python ≥ 3.10 and `click` and is meant to be run via
`uv` from the repository root:

```bash
# from the edo root
uv run --project infrastructure/scripts edo-infra --help
```

## Commands

| command | what it does |
|---|---|
| `install-exporter` | Install the maDMP export plugin (`components/socket-rdmo/madmp-exporter`) into the RDMO instance: editable `uv pip install`, plugin registration in `config/settings/local.py`, `GET /api/v1/madmp/projects/{pk}/` route in `config/urls.py`, verification. Idempotent. `--create-token USER` adds a DRF token, `--dry-run` shows the plan. |
| `create-project-from-doi` | Fetch DataCite metadata for a DOI (default: `10.5445/IR/1000162908`, "Semantico"), map it onto the RDMO standard questionary, create the project (owner membership for `admin`) and export it via RDMO's own XML exporter to `fixtures/rdmo/`. `--dry-run` prints the value plan only. |
| `reset-projects` | Delete all (or all-but-`--keep ID`) RDMO projects so fixture projects can be re-imported cleanly. `--list` shows what would happen. Cascades values/snapshots/memberships; catalogs, questionnaires and users stay. |
| `add-dataset` | Add a `project/dataset` block (id/name/description/format/creation date) to a fixture project XML, optionally with paper rows from a CSV (`--papers`, columns Author, Publication Date, Title). Idempotent: aborts when a dataset with the same name already exists. |

## Examples

```bash
edo-infra install-exporter                     # + --create-token admin for machine access
edo-infra create-project-from-doi --dry-run    # value plan only
edo-infra reset-projects --list                # show projects
edo-infra add-dataset --help                   # add a dataset to a fixture XML
```

All commands default to `infrastructure/Servers/rdmo-app` (`--rdmo-app`) and
`infrastructure/fixtures/rdmo` (`--xml`/`--xml-out`); everything is overridable.
