"""Click wrapper for ``reset-projects``.

The actual implementation (and option parsing/help) lives in the stdlib-only
:mod:`edo_infra.reset_projects_impl`, which runs in the RDMO instance env —
the wrapper only forwards the raw arguments to the re-executed child process.
"""

from __future__ import annotations

import click

from .instance import reexec_in_instance_env
from .paths import DEFAULT_RDMO_APP


@click.command("reset-projects",
               context_settings={"ignore_unknown_options": True})
@click.argument("argv", nargs=-1, type=click.UNPROCESSED)
def reset_projects(argv: tuple[str, ...]):
    """Reset the projects database of the local RDMO instance.

    Runs in two phases: this (outer) process re-executes itself with the RDMO
    instance env python; all options are documented in `--help` of the
    instance phase (--rdmo-app, --keep ID, --list, --yes).
    """
    raise SystemExit(reexec_in_instance_env(DEFAULT_RDMO_APP))
