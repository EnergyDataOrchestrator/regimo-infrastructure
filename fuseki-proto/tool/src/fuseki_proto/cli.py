"""Click CLI for Fuseki prototype maintenance.

Lifecycle (via ``docker compose``) and data maintenance (via the Fuseki
HTTP admin/data endpoints). All options have sane defaults derived from the
prototype's ``docker-compose.yml`` that can be overridden.
"""

from __future__ import annotations

import datetime as _dt
import sys

from pathlib import Path

import click

from . import docker as D
from .docker import DEFAULT_BACKUPS_DIR, TOOL_DIR
from .trip import trip as trip_cmd
from .agnostic_trip import agnostic_trip as agnostic_trip_cmd
from .ro_crate import crate_group as crate_cmd

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


# ---------------------------------------------------------------------------
# shared, persistent CLI context
# ---------------------------------------------------------------------------
class FusekiContext:
    def __init__(self, compose_dir, service, dataset, port, user, password,
                 compose_file=None, backups_dir: str | Path | None = None):
        self.compose_dir = compose_dir
        self.service = service
        self.dataset = dataset
        self.port = port
        self.user = user
        self.password = password
        self.compose_file = compose_file or None
        self.backups_dir = Path(backups_dir) if backups_dir is not None else DEFAULT_BACKUPS_DIR

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def data_url(self) -> str:
        return f"{self.base_url}/{self.dataset}/data"

    @property
    def update_url(self) -> str:
        return f"{self.base_url}/{self.dataset}/update"

    def compose(self, *args):
        if self.compose_file:
            args = ("-f", self.compose_file) + args
        return D.compose(*args, cwd=self.compose_dir)


@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
@click.option("--compose-dir", type=click.Path(exists=True, file_okay=False),
              default=str(TOOL_DIR.parent), show_default=True,
              help="Directory containing docker-compose.yml.")
@click.option("--service", default="fuseki", show_default=True,
              help="docker compose service name.")
@click.option("--dataset", default="projects", show_default=True,
              help="Fuseki dataset for instance graphs.")
@click.option("--port", default=3031, type=int, show_default=True,
              help="Fuseki HTTP port (host side). Default 3031 because a host "
                   "Fuseki serving the ORKG database already occupies 3030 "
                   "(see docker-compose.yml).")
@click.option("--user", default="admin", show_default=True,
              help="Fuseki admin user (Basic auth).")
@click.option("--password", default="edo-proto", show_default=True,
              help="Fuseki admin password.")
@click.option("--backups-dir", type=click.Path(file_okay=False),
              default=str(DEFAULT_BACKUPS_DIR), show_default=True,
              help="Directory where backups are written/read.")
@click.pass_context
def cli(ctx, compose_dir, service, dataset, port, user, password, backups_dir):
    """Maintenance CLI for the EDO/Regimo Fuseki prototype."""
    ctx.obj = FusekiContext(compose_dir, service, dataset, port, user, password,
                            backups_dir=backups_dir)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
    pass


# CF2-003 round trip (transform -> store -> verify), see trip.py and
# scripts/trafos/README.md.
cli.add_command(trip_cmd)

# CF2-004 map-driven round trip (same scenarios, LinkML Map as the container
# of the transformation logic), see agnostic_trip.py and
# scripts/trafos/README.md.
cli.add_command(agnostic_trip_cmd)

# CF2-006 RO-Crate generation from the internal format (see ro_crate.py,
# scripts/ro_crate documentation).
cli.add_command(crate_cmd)


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------
@cli.command()
@click.pass_obj
def start(fc: FusekiContext):
    """Bring the Fuseki container up and wait until it responds.

    The image is built locally from ./docker/Dockerfile (Apache Jena ships no
    registry image), so `up --build` ensures it exists/rebuilt on every start.
    Then we seed /shapes from the local shapes file (idempotent).
    """
    _run_compose(fc, "up", "-d", "--build")
    if not D.wait_for_ping(fc.base_url, fc.dataset, fc.user, fc.password):
        raise click.ClickException("Fuseki did not answer /{}/query in time. "
                                   "Check `status` / `docker compose -f ... logs fuseki`.".format(
                                       fc.dataset))
    _seed_shapes(fc)
    click.echo(f"OK: Fuseki up at {fc.base_url}.")


@cli.command()
@click.pass_obj
def stop(fc: FusekiContext):
    """Stop the container gracefully (TDB2 holds a lock; do NOT kill -9)."""
    _run_compose(fc, "stop", fc.service)
    click.echo("Stopped.")


@cli.command()
@click.pass_obj
def restart(fc: FusekiContext):
    """Restart the container."""
    _run_compose(fc, "restart", fc.service)
    click.echo("Restarted.")


@cli.command()
@click.pass_obj
def status(fc: FusekiContext):
    """Show container state and whether the prototype datasets respond.

    The (server-only) jena-fuseki-server build exposes NO `/$/ping` / `/$/datasets`
    admin endpoints, so liveness/dataset checks probe each data-service `/query`
    endpoint directly.
    """
    state = D.container_status(fc.service, cwd=fc.compose_dir)
    click.echo(f"container {fc.service}: {state}")
    if state != "running":
        click.echo("(compose container not running; start it with `fuseki-proto start`)")
    # Probing proceeds regardless of compose state: a Fuseki may already be
    # listening on the port (e.g. a host install), in which case the prototype
    # datasets may be absent.
    try:
        D.http_get(D.dataset_query_url(fc.base_url, fc.dataset), fc.user, fc.password)
    except Exception:
        click.echo(f"no Fuseki responding on {fc.base_url} (probed /{fc.dataset}/query)")
        return
    click.echo(f"live Fuseki on {fc.base_url}; served datasets:")
    present = []
    for name in (fc.dataset, "shapes"):
        try:
            D.http_get(D.dataset_query_url(fc.base_url, name), fc.user, fc.password)
            present.append(name)
        except Exception:
            pass
    for name in present:
        marker = "  <-- prototype" if name == fc.dataset else ""
        click.echo(f"  /{name}{marker}")
    missing = [n for n in (fc.dataset, "shapes") if n not in present]
    if missing:
        click.echo(f"note: expected dataset(s) not responding: {', '.join('/'+m for m in missing)}.")
        if state == "running":
            click.echo("      They should appear once `config/projects-ds.ttl` is loaded by the compose container.")
        else:
            click.echo("      This is likely an unrelated host Fuseki; start the compose one on another port.")


@cli.command()
@click.pass_obj
def ping(fc: FusekiContext):
    """Run a trivial query on a dataset — exit 0 if the server answers it."""
    try:
        D.http_get(D.dataset_query_url(fc.base_url, fc.dataset), fc.user, fc.password)
        click.echo("pong")
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(f"no response: {exc}")


# ---------------------------------------------------------------------------
# data maintenance
# ---------------------------------------------------------------------------
def _ts() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


@cli.command()
@click.option("--dataset", default=None, help="Dataset to back up (defaults to context).")
@click.pass_obj
def backup(fc: FusekiContext, dataset):
    """Dump a dataset as RDF (Turtle) under backups/.

    The (server-only) jena-fuseki-server build has no `/$/backup` admin
    endpoint, so this runs a CONSTRUCT dump from the dataset `/query` endpoint
    instead of the Fuseki-Full `/$/backup` download.
    """
    ds = dataset or fc.dataset
    fc.backups_dir.mkdir(parents=True, exist_ok=True)
    target = fc.backups_dir / f"{ds}-{_ts()}.ttl"
    try:
        body = D.dump_graph(fc.base_url, ds, fc.user, fc.password)
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(f"backup failed: {exc}")
    target.write_bytes(body)
    click.echo(f"Wrote {target} ({target.stat().st_size} bytes).")


@cli.command(name="list-backups")
@click.pass_obj
def list_backups(fc: FusekiContext):
    """List backup files in backups/."""
    if not fc.backups_dir.exists():
        click.echo("(no backups yet)")
        return
    for p in sorted(fc.backups_dir.glob("*")):
        if p.is_file():
            click.echo(f"{p.name}  ({p.stat().st_size} bytes)")


@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dataset", default=None, help="Dataset to restore into (defaults to context).")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt (destructive).")
@click.pass_obj
def restore(fc: FusekiContext, file, dataset, yes):
    """Restore a backup (or any RDF dump) into a dataset.

    Warns and clears the target dataset first. Best used with a TDB2 dataset
    that is not mid-write.
    """
    dataset = dataset or fc.dataset
    path = Path(file)
    _confirm_wipe(fc, yes)
    _clear(fc, dataset=dataset)
    _upload_to(fc, path, dataset=dataset)
    click.echo(f"Restored {path.name} into /{dataset}.")


@cli.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--graph", default=None, help="Named graph to load into (default: default graph).")
@click.option("--dataset", default=None, help="Dataset (defaults to context).")
@click.pass_obj
def load(fc: FusekiContext, file, graph, dataset):
    """Load a local RDF file (Turtle/JSON-LD/N-Triples/...) into a dataset."""
    dataset = dataset or fc.dataset
    path = Path(file)
    _upload_to(fc, path, dataset=dataset, graph=graph)
    click.echo(f"Loaded {path.name} into /{dataset}.")


@cli.command()
@click.option("--dataset", default=None, help="Dataset to wipe (defaults to context).")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt (destructive).")
@click.pass_obj
def wipe(fc: FusekiContext, dataset, yes):
    """Delete ALL data in a dataset (CLEAR ALL). Irreversible."""
    dataset = dataset or fc.dataset
    _confirm_wipe(fc, yes)
    _clear(fc, dataset=dataset)
    click.echo(f"Wiped /{dataset}.")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _run_compose(fc: FusekiContext, *args: str):
    try:
        fc.compose(*args)
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(f"docker compose failed: {exc}")


def _clear(fc: FusekiContext, dataset: str | None = None):
    dataset = dataset or fc.dataset
    D.http_update("CLEAR ALL",
                  fc.update_url if dataset == fc.dataset else
                  f"{fc.base_url}/{dataset}/update", fc.user, fc.password)


def _upload_to(fc: FusekiContext, path, dataset: str | None = None, graph: str | None = None):
    dataset = dataset or fc.dataset
    content_type = None if path.suffix == ".gz" else D.guess_content_type(path)
    url = f"{fc.base_url}/{dataset}/data"
    if graph:
        url += f"?graph={graph}"
    body = D.http_upload(url, fc.user, fc.password, path, content_type=content_type)
    sys.stdout.write(body.decode(errors="replace"))


def _seed_shapes(fc: FusekiContext) -> None:
    """(Re)load the project-claim SHACL shapes into the /shapes dataset.

    The /shapes assembler cannot reliably self-load the file, so on every start
    we clear and re-upload it. Re-seeding keeps /shapes in lock-step with edits
    to shapes/project-claim-shapes.ttl.
    """
    dataset = "shapes"
    shapes_file = Path(fc.compose_dir) / "shapes" / "project-claim-shapes.ttl"
    if not shapes_file.is_file():
        click.echo(f"(no shapes file at {shapes_file}; skipping /shapes seed)")
        return
    try:
        _clear(fc, dataset=dataset)
        _upload_to(fc, shapes_file, dataset=dataset)
        click.echo(f"Seeded /{dataset} from {shapes_file.name}.")
    except Exception as exc:  # noqa: BLE001
        click.echo(f"(warning: could not seed /{dataset}: {exc})")


def _confirm_wipe(fc: FusekiContext, yes: bool):
    if not yes:
        click.confirm(
            f"This will clear the dataset /{fc.dataset}. Continue?",
            abort=True,
        )


if __name__ == "__main__":
    cli()
