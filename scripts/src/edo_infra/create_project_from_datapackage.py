"""Click wrapper for ``create-project-from-datapackage``.

The actual implementation (and option parsing/help) lives in the stdlib-only
:mod:`edo_infra.datapackage_project`, which runs in the RDMO instance env —
the wrapper only forwards the raw arguments to the re-executed child process.
"""

from __future__ import annotations

import click

from .instance import reexec_in_instance_env
from .paths import DEFAULT_RDMO_APP


@click.command("create-project-from-datapackage",
               context_settings={"ignore_unknown_options": True})
@click.argument("argv", nargs=-1, type=click.UNPROCESSED)
def create_project_from_datapackage(argv: tuple[str, ...]):
    """Create an RDMO project from an OEMetadata datapackage and export it as
    RDMO XML.

    Runs in two phases: this (outer) process re-executes itself with the RDMO
    instance env python; all options are documented in `--help` of the
    instance phase (--datapackage, --rdmo-app, --catalog, --owner, --xml-out,
    --dry-run, --force).
    """
    raise SystemExit(reexec_in_instance_env(DEFAULT_RDMO_APP))
