"""Bridge between the outer CLI environment and the RDMO instance environment.

The RDMO instance env (``Servers/rdmo-app/env``) has Django + rdmo installed
but not this package; ORM-touching commands therefore re-execute this
package's CLI with the instance python (``python -m edo_infra``, cwd = the
instance dir, ``PYTHONPATH`` pointed at ``infrastructure/scripts/src``,
``EDO_INFRA_INSTANCE_CHILD=1``). The re-executed process calls
:func:`instance_child` to put the instance checkout on ``sys.path`` and run
``django.setup()`` before the command body executes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .paths import PACKAGE_SRC

CHILD_ENV_VAR = "EDO_INFRA_INSTANCE_CHILD"


def in_instance_child() -> bool:
    return os.environ.get(CHILD_ENV_VAR) == "1"


def reexec_in_instance_env(rdmo_app: Path) -> int:
    """Run this CLI again with the instance env python (from the app dir)."""
    env_python = rdmo_app / "env" / "bin" / "python"
    if not env_python.is_file():
        print(f"ERROR: RDMO instance env python not found: {env_python}\n"
              "       create it first, see infrastructure/README.md",
              file=sys.stderr)
        return 2
    env = os.environ.copy()
    env[CHILD_ENV_VAR] = "1"
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (str(PACKAGE_SRC)
                         + (os.pathsep + existing if existing else ""))
    print(f"Running ORM phase with {env_python}")
    return subprocess.run(
        [str(env_python), "-m", "edo_infra", *sys.argv[1:]],
        cwd=str(rdmo_app), env=env,
    ).returncode


def instance_child(rdmo_app: Path) -> None:
    """Prepare the re-executed process for Django ORM work."""
    sys.path.insert(0, str(rdmo_app))  # config.settings lives in rdmo-app
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()
