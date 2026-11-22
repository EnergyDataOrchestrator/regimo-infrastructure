"""Install the maDMP export plugin into the local RDMO instance.

Installs ``components/socket-rdmo/madmp-exporter`` (package
``rdmo-madmp-exporter``) into the RDMO virtualenv of
``infrastructure/Servers/rdmo-app`` and wires it up:

1. **Package install** — editable, via ``uv pip install -e …`` (the instance's
   env is uv-managed and has no ``pip``; edits in the repo take effect after a
   server reload).
2. **Export-plugin registration** — appends a marked
   ``PROJECT_EXPORTS += [('madmp', …)]`` block to ``config/settings/local.py``
   (RDMO's base settings already define the four standard exports; local.py is
   loaded last, so ``+=`` extends them). Idempotent via the marker comment.
3. **API wiring** — inserts ``path('api/v1/madmp/', include(
   'rdmo_madmp_exporter.urls'))`` into ``config/urls.py``, exposing
   ``GET /api/v1/madmp/projects/{pk}/`` (DRF, Token/Basic/Session auth,
   reusing RDMO's ``projects.export_project_object`` permission). Idempotent.
4. **Verification** — configures Django from the instance, lists the
   registered export plugins and reverse-maps the maDMP API route.

Optional machine-access token: ``--create-token <username>`` runs
``manage.py drf_create_token <username>`` in the instance env.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from .paths import DEFAULT_EXPORTER, DEFAULT_RDMO_APP

# Matches the marker written by the earlier standalone script, so a previously
# patched instance is still recognised as already registered.
MANAGED_MARKER_PREFIX = "# --- maDMP export plugin (managed by "
MANAGED_MARKER = (MANAGED_MARKER_PREFIX
                  + "edo-infra install-exporter) ---")
PLUGIN_ENTRY = ("PROJECT_EXPORTS += [('madmp', 'maDMP Export Plugin', "
                "'rdmo_madmp_exporter.rdmo.MaDMPExport')]")
URL_LINE = "    path('api/v1/madmp/', include('rdmo_madmp_exporter.urls')),"
URL_ANCHOR = "path('api/v1/', include('rdmo.core.urls.v1'))"


def _run(cmd: list, cwd: Path | None = None) -> subprocess.CompletedProcess:
    click.echo(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run([str(c) for c in cmd], cwd=cwd)


@click.command("install-exporter")
@click.option("--rdmo-app", type=click.Path(exists=True, file_okay=False,
                                            path_type=Path),
              default=DEFAULT_RDMO_APP, show_default=True,
              help="RDMO instance directory.")
@click.option("--exporter", type=click.Path(exists=True, file_okay=False,
                                            path_type=Path),
              default=DEFAULT_EXPORTER, show_default=True,
              help="madmp-exporter package directory.")
@click.option("--uv", "uv_exe", default="uv", show_default=True,
              help="uv executable used for the env install.")
@click.option("--create-token", metavar="USER",
              help="after installing, create/print a DRF token for USER.")
@click.option("--dry-run", is_flag=True,
              help="show what would be done without changing anything.")
def install_exporter(rdmo_app: Path, exporter: Path, uv_exe: str,
                     create_token: str | None, dry_run: bool):
    """Install the maDMP export plugin into the local RDMO instance."""
    rdmo_app = rdmo_app.resolve()
    exporter = exporter.resolve()
    env_python = rdmo_app / "env" / "bin" / "python"
    local_py = rdmo_app / "config" / "settings" / "local.py"
    urls_py = rdmo_app / "config" / "urls.py"

    click.echo(f"RDMO instance : {rdmo_app}")
    click.echo(f"Exporter      : {exporter}")

    # -- sanity checks -------------------------------------------------------
    for path, what in ((rdmo_app / "manage.py", "rdmo-app checkout"),
                       (env_python, "RDMO virtualenv (env/bin/python)"),
                       (exporter / "pyproject.toml", "madmp-exporter package")):
        if not path.exists():
            click.echo(f"ERROR: missing {what}: {path}", err=True)
            if what.startswith("RDMO virtualenv"):
                click.echo("       create it first, see infrastructure/README.md",
                           err=True)
            raise SystemExit(2)

    # -- 1. install the exporter package into the RDMO env -------------------
    probe = _run([env_python, "-c",
                  "import rdmo_madmp_exporter, yaml; "  # PyYAML's import name is 'yaml'
                  "print(rdmo_madmp_exporter.__file__)"],
                 cwd=rdmo_app)
    if probe.returncode == 0:
        click.echo(f"OK: rdmo-madmp-exporter already importable "
                   f"({(probe.stdout or b'').decode().strip()})")
    else:
        cmd = [uv_exe, "pip", "install", "--python", env_python, "-e", exporter]
        if dry_run:
            click.echo(f"(dry-run) would run: {' '.join(str(c) for c in cmd)}")
        elif _run(cmd, cwd=rdmo_app).returncode != 0:
            click.echo("ERROR: uv pip install failed", err=True)
            raise SystemExit(1)

    if dry_run:
        click.echo("(dry-run) settings/urls patching and verification skipped")
        return

    # -- 2. register the export plugin in config/settings/local.py -----------
    text = local_py.read_text(encoding="utf-8")
    if MANAGED_MARKER_PREFIX in text:
        click.echo(f"OK: plugin already registered in {local_py}")
    else:
        note = ""
        if "PROJECT_EXPORTS" in text:
            note = " (NOTE: local.py already defines PROJECT_EXPORTS; "
            "check the file afterwards.)"
        local_py.write_text(
            text.rstrip() + "\n\n\n" + MANAGED_MARKER + "\n" + PLUGIN_ENTRY + "\n",
            encoding="utf-8")
        click.echo(f"Wrote plugin registration -> {local_py}{note}")

    # -- 3. wire the API endpoint into config/urls.py ------------------------
    text = urls_py.read_text(encoding="utf-8")
    if "rdmo_madmp_exporter.urls" in text:
        click.echo(f"OK: maDMP API already wired in {urls_py}")
    else:
        lines = text.splitlines(keepends=True)
        anchor = next((i for i, line in enumerate(lines)
                       if URL_ANCHOR in line), None)
        if anchor is None:
            click.echo(f"ERROR: could not find the api/v1 include in {urls_py}; "
                       f"add this line manually:\n{URL_LINE}", err=True)
            raise SystemExit(1)
        lines.insert(anchor + 1, URL_LINE + "\n")
        urls_py.write_text("".join(lines), encoding="utf-8")
        click.echo(f"Wrote maDMP API route    -> {urls_py}")

    # -- 4. verify: plugin registration + API route --------------------------
    verify = (
        "import django, os; "
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
        "django.setup(); "
        "from rdmo.core.plugins import get_plugins; "
        "plugins = get_plugins('PROJECT_EXPORTS'); "
        "[print('  plugin:', k, '|', p.label, '|', p.class_name) "
        "for k, p in plugins.items()]; "
        "assert 'madmp' in plugins, 'madmp plugin not registered'; "
        "from django.urls import reverse; "
        "print('  api route:', "
        "reverse('rdmo_madmp_exporter:project-madmp', args=[1]))"
    )
    if _run([env_python, "-c", verify], cwd=rdmo_app).returncode != 0:
        click.echo("ERROR: verification failed", err=True)
        raise SystemExit(1)

    # -- 5. optional machine-access token ------------------------------------
    if create_token:
        if _run([env_python, "manage.py", "drf_create_token", create_token],
                cwd=rdmo_app).returncode != 0:
            click.echo(f"ERROR: could not create a token for {create_token}",
                       err=True)
            raise SystemExit(1)

    click.echo("\nDone. Restart/reload the RDMO server if it is running "
               "(the autoreloader picks up the settings/urls changes).")
    click.echo("Web UI export : project page -> 'maDMP Export Plugin'")
    click.echo("HTTP API      : GET /api/v1/madmp/projects/{pk}/  "
               "(Token/Basic/Session auth)")
