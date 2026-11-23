"""``write-columns-manifest`` — install the regimo-core columns manifest for
an **existing** RDMO project (UPL-004 Stage 2, decision A).

The data-file publisher owns the column structure: this command derives the
manifest from an OEMetadata datapackage (``schema.fields``, verbatim subset,
``type`` renamed to ``datatype``) and writes it to
``<out>/<project-id>/columns.json`` — the layout regimo-core reads via
``REGIMO_COLUMNS_EXTRAS`` on its next sync (a manifest change re-transforms
the project because it participates in the change digest).

Pure stdlib — no RDMO instance env needed, the project id is passed
explicitly (``-v`` output of ``regimo-core sync`` shows it; the artifacts
directory uses the same id, e.g. ``data/regimo-core/artifacts/20.ttl``).
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from .datapackage_project import (build_columns_manifest, extract_metadata,
                                  write_columns_manifest_file)
from .paths import EDO_ROOT

DEFAULT_COLUMNS_DIR = EDO_ROOT / "data" / "regimo-core" / "columns"


@click.command("write-columns-manifest")
@click.option("--datapackage", "dp_path", type=click.Path(exists=True,
              path_type=Path, dir_okay=False), required=True,
              help="Path to the OEMetadata datapackage.json.")
@click.option("--project-id", type=int, required=True,
              help="RDMO project id the manifest belongs to "
                   "(as shown by 'regimo-core sync -v' / the artifacts dir).")
@click.option("--out", "out_dir", type=click.Path(file_okay=False,
              path_type=Path),
              default=DEFAULT_COLUMNS_DIR, show_default=True,
              help="Columns extras directory of regimo-core.")
def write_columns_manifest(dp_path: Path, project_id: int, out_dir: Path):
    """Write the columns manifest of a datapackage for an existing project.

    regimo-core attaches the columns to the internal-format graph on the
    next sync (edo:hasColumn -> csvw:Column).
    """
    meta = extract_metadata(json.loads(dp_path.read_text(encoding="utf-8")))
    if not meta["resources"]:
        raise click.ClickException(f"no resources in {dp_path}")
    manifest = build_columns_manifest(meta)
    target = write_columns_manifest_file(out_dir, project_id, manifest)
    columns = sum(len(d["columns"]) for d in manifest["datasets"])
    click.echo(f"OK: wrote {target} ({columns} columns for "
               f"{len(manifest['datasets'])} dataset(s), project {project_id})")
