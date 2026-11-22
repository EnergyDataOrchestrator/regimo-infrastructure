"""edo-infra CLI — the click command group."""

from __future__ import annotations

import click

from . import __version__
from .add_dataset import add_dataset
from .create_project_from_doi import create_project_from_doi
from .install_exporter import install_exporter
from .reset_projects import reset_projects

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__, prog_name="edo-infra")
def cli():
    """Maintenance CLI for the EDO infrastructure
    (local RDMO instance, fixture XMLs, plugins)."""


cli.add_command(install_exporter)
cli.add_command(create_project_from_doi)
cli.add_command(add_dataset)
cli.add_command(reset_projects)
