"""Dispatch of the re-executed instance-env child (stdlib only, no click).

The child process runs ``python -m edo_infra <command> <args...>`` inside the
RDMO instance env, where ``click`` is not installed; this module therefore
maps the command name to a stdlib-only implementation module and lets it
parse its own options (argparse).
"""

from __future__ import annotations

import sys


def dispatch() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    argv = sys.argv[2:]

    if command == "reset-projects":
        from .reset_projects_impl import main
        raise SystemExit(main(argv))
    if command == "create-project-from-doi":
        from .doi_project import main
        raise SystemExit(main(argv))

    print(f"ERROR: unknown command for instance child: {command!r}",
          file=sys.stderr)
    raise SystemExit(2)
