#!/usr/bin/env python3
"""Admin script — install the maDMP export plugin into the local RDMO instance.

Installs `components/socket-rdmo/madmp-exporter` (package `rdmo-madmp-exporter`)
into the RDMO virtualenv of `infrastructure/Servers/rdmo-app` and wires it up:

1. **Package install** — editable, via `uv pip install -e …` (the instance's
   env is uv-managed and has no `pip`; edits in the repo take effect after a
   server reload).
2. **Export-plugin registration** — appends a marked
   `PROJECT_EXPORTS += [('madmp', …)]` block to `config/settings/local.py`
   (RDMO's base settings already define the four standard exports; local.py is
   loaded last, so `+=` extends them). Idempotent via the marker comment.
3. **API wiring** — inserts `path('api/v1/madmp/', include(
   'rdmo_madmp_exporter.urls'))` into `config/urls.py`, exposing
   `GET /api/v1/madmp/projects/{pk}/` (DRF, Token/Basic/Session auth, reusing
   RDMO's `projects.export_project_object` permission). Idempotent.
4. **Verification** — configures Django from the instance, lists the
   registered export plugins and reverse-maps the maDMP API route.

Stdlib only — safe to run with any Python 3 interpreter, e.g.:

    python3 infrastructure/scripts/install_madmp_exporter.py

Optional machine-access token: `--create-token <username>` runs
`manage.py drf_create_token <username>` in the instance env.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # infrastructure/scripts
INFRA_DIR = SCRIPT_DIR.parent                         # infrastructure/
DEFAULT_RDMO_APP = INFRA_DIR / "Servers" / "rdmo-app"
DEFAULT_EXPORTER = INFRA_DIR.parent / "components" / "socket-rdmo" / "madmp-exporter"

MANAGED_MARKER = "# --- maDMP export plugin (managed by infrastructure/scripts/install_madmp_exporter.py) ---"
PLUGIN_ENTRY = ("PROJECT_EXPORTS += [('madmp', 'maDMP Export Plugin', "
                "'rdmo_madmp_exporter.rdmo.MaDMPExport')]")
URL_LINE = "    path('api/v1/madmp/', include('rdmo_madmp_exporter.urls')),"
URL_ANCHOR = "path('api/v1/', include('rdmo.core.urls.v1'))"


def run(cmd: list, cwd: Path | None = None) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run([str(c) for c in cmd], cwd=cwd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rdmo-app", type=Path, default=DEFAULT_RDMO_APP,
                        help="RDMO instance directory (default: %(default)s)")
    parser.add_argument("--exporter", type=Path, default=DEFAULT_EXPORTER,
                        help="madmp-exporter package directory (default: %(default)s)")
    parser.add_argument("--uv", default="uv",
                        help="uv executable used for the env install (default: %(default)s)")
    parser.add_argument("--create-token", metavar="USER",
                        help="after installing, create/print a DRF token for USER")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be done without changing anything")
    args = parser.parse_args()

    rdmo_app = args.rdmo_app.resolve()
    exporter = args.exporter.resolve()
    env_python = rdmo_app / "env" / "bin" / "python"
    local_py = rdmo_app / "config" / "settings" / "local.py"
    urls_py = rdmo_app / "config" / "urls.py"

    print(f"RDMO instance : {rdmo_app}")
    print(f"Exporter      : {exporter}")

    # -- sanity checks -------------------------------------------------------
    for path, what in ((rdmo_app / "manage.py", "rdmo-app checkout"),
                       (env_python, "RDMO virtualenv (env/bin/python)"),
                       (exporter / "pyproject.toml", "madmp-exporter package")):
        if not path.exists():
            print(f"ERROR: missing {what}: {path}", file=sys.stderr)
            if what.startswith("RDMO virtualenv"):
                print("       create it first, see infrastructure/README.md",
                      file=sys.stderr)
            return 2

    # -- 1. install the exporter package into the RDMO env -------------------
    probe = run([env_python, "-c",
                 "import rdmo_madmp_exporter, yaml; "  # PyYAML's import name is 'yaml'
                 "print(rdmo_madmp_exporter.__file__)"],
                cwd=rdmo_app)
    if probe.returncode == 0:
        print(f"OK: rdmo-madmp-exporter already importable "
              f"({(probe.stdout or b'').decode().strip()})")
    else:
        cmd = [args.uv, "pip", "install", "--python", env_python, "-e", exporter]
        if args.dry_run:
            print(f"(dry-run) would run: {' '.join(str(c) for c in cmd)}")
        elif run(cmd, cwd=rdmo_app).returncode != 0:
            print("ERROR: uv pip install failed", file=sys.stderr)
            return 1

    if args.dry_run:
        print("(dry-run) settings/urls patching and verification skipped")
        return 0

    # -- 2. register the export plugin in config/settings/local.py -----------
    text = local_py.read_text(encoding="utf-8")
    if MANAGED_MARKER in text:
        print(f"OK: plugin already registered in {local_py}")
    else:
        note = ""
        if "PROJECT_EXPORTS" in text:
            note = " (NOTE: local.py already defines PROJECT_EXPORTS; "
            "check the file afterwards.)"
        local_py.write_text(
            text.rstrip() + "\n\n\n" + MANAGED_MARKER + "\n" + PLUGIN_ENTRY + "\n",
            encoding="utf-8")
        print(f"Wrote plugin registration -> {local_py}{note}")

    # -- 3. wire the API endpoint into config/urls.py ------------------------
    text = urls_py.read_text(encoding="utf-8")
    if "rdmo_madmp_exporter.urls" in text:
        print(f"OK: maDMP API already wired in {urls_py}")
    else:
        lines = text.splitlines(keepends=True)
        anchor = next((i for i, line in enumerate(lines)
                       if URL_ANCHOR in line), None)
        if anchor is None:
            print(f"ERROR: could not find the api/v1 include in {urls_py}; "
                  f"add this line manually:\n{URL_LINE}", file=sys.stderr)
            return 1
        lines.insert(anchor + 1, URL_LINE + "\n")
        urls_py.write_text("".join(lines), encoding="utf-8")
        print(f"Wrote maDMP API route    -> {urls_py}")

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
    if run([env_python, "-c", verify], cwd=rdmo_app).returncode != 0:
        print("ERROR: verification failed", file=sys.stderr)
        return 1

    # -- 5. optional machine-access token ------------------------------------
    if args.create_token:
        if run([env_python, "manage.py", "drf_create_token", args.create_token],
               cwd=rdmo_app).returncode != 0:
            print(f"ERROR: could not create a token for {args.create_token}",
                  file=sys.stderr)
            return 1

    print("\nDone. Restart/reload the RDMO server if it is running "
          "(the autoreloader picks up the settings/urls changes).")
    print("Web UI export : project page -> 'maDMP Export Plugin'")
    print("HTTP API      : GET /api/v1/madmp/projects/{pk}/  "
          "(Token/Basic/Session auth)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
