#!/usr/bin/env python3
"""Admin script — reset the projects database of the local RDMO instance.

Deletes all (or all-but-keep) RDMO projects from `infrastructure/Servers/
rdmo-app` so that fixture projects can be re-imported cleanly. Related rows
cascade via Django's FK CASCADE: values, snapshots, memberships and the
project's integrations go with the project; catalogs, questionnaires, users
and views are untouched.

Before deleting, the projects are listed (id, title, owner) and a
confirmation prompt requires an explicit answer unless `--yes` is given.

Because the CF1 sync engine detects removals via digest comparison against
RDMO, the next `regimo-core sync` run after a reset will emit one
`project.removed` event per vanished project on `edo.projects.v1` and clear
the corresponding artifacts/graph — that is expected behaviour, not an error.

Stdlib only — run with any Python 3 interpreter; the script re-executes
itself with the RDMO instance env (`env/bin/python`) for the Django ORM work:

    python3 infrastructure/scripts/reset_projects.py            # confirm, wipe
    python3 infrastructure/scripts/reset_projects.py --list     # just show
    python3 infrastructure/scripts/reset_projects.py --keep 5   # keep project 5
    python3 infrastructure/scripts/reset_projects.py --yes      # no prompt
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # infrastructure/scripts
INFRA_DIR = SCRIPT_DIR.parent                         # infrastructure/
DEFAULT_RDMO_APP = INFRA_DIR / "Servers" / "rdmo-app"

CHILD_ENV_VAR = "RDMO_RESET_PROJECTS_CHILD"


# ---------------------------------------------------------------------------
# phase 1 (outer, stdlib only): sanity checks + re-exec decision
# ---------------------------------------------------------------------------
def sanity_checks(rdmo_app: Path) -> None:
    problems = []
    if not (rdmo_app / "manage.py").is_file():
        problems.append(f"rdmo-app checkout missing: {rdmo_app/'manage.py'}")
    if not (rdmo_app / "env" / "bin" / "python").is_file():
        problems.append(
            f"RDMO virtualenv missing: {rdmo_app/'env'/'bin'/'python'} "
            "(create it first, see infrastructure/README.md)")
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        sys.exit(2)


def reexec_in_instance_env(rdmo_app: Path) -> int:
    """Run the ORM phase with the instance env python (from the app dir)."""
    env_python = rdmo_app / "env" / "bin" / "python"
    env = os.environ.copy()
    env[CHILD_ENV_VAR] = "1"
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    print(f"Running ORM phase with {env_python}")
    return subprocess.run(
        [str(env_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(rdmo_app), env=env,
    ).returncode


# ---------------------------------------------------------------------------
# phase 2 (re-exec, Django env): list / delete
# ---------------------------------------------------------------------------
def child_main(rdmo_app: Path, keep: list[int], assume_yes: bool,
               list_only: bool) -> int:
    sys.path.insert(0, str(rdmo_app))  # config.settings lives in rdmo-app
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from django.contrib.auth import get_user_model
    from rdmo.projects.models import Project

    User = get_user_model()

    def describe(project: Project) -> str:
        owners = ", ".join(
            m.user.username for m in project.memberships.all()
            if m.role == "owner") or "(no owner)"
        return f"  {project.id:>4}  {project.title!r:<60}  owner: {owners}"

    projects = list(Project.objects.order_by("id"))
    if not projects:
        print("No projects in the database — nothing to do.")
        return 0

    print(f"Projects in {rdmo_app}:")
    for project in projects:
        print(describe(project))

    doomed = [p for p in projects if p.id not in keep]
    if not doomed:
        print("Nothing to delete (all selected projects are kept).")
        return 0

    if list_only:
        print(f"List only — {len(doomed)} project(s) would be deleted, "
              f"{len(projects) - len(doomed)} kept.")
        return 0

    print(f"\nAbout to delete {len(doomed)} project(s): "
          + ", ".join(f"{p.id} ({p.title!r})" for p in doomed))
    if keep:
        print(f"Keeping project id(s): {', '.join(str(k) for k in keep)}")
    print("Values, snapshots and memberships cascade; catalogs, "
          "questionnaires and users stay.")
    if not assume_yes:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted — nothing changed.")
            return 1

    counts = {}
    before = {
        "Value": 0, "Snapshot": 0, "Membership": 0,
    }
    from django.apps import apps
    for label in before:
        before[label] = apps.get_model("projects", label).objects.count()

    for project in doomed:
        title = project.title
        project.delete()
        print(f"Deleted project {project.id} ({title!r}).")

    print("\nDone. Row counts before/after:")
    for label in before:
        model = apps.get_model("projects", label)
        print(f"  {label:<12} {before[label]:>6} -> {model.objects.count():>6}")
    remaining = Project.objects.count()
    print(f"  Project      {len(projects):>6} -> {remaining:>6}")

    print("\nNote: the next `regimo-core sync` run will report the removals "
          "(project.removed events on edo.projects.v1, artifacts cleared).")
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset the projects database of the local RDMO instance.")
    parser.add_argument("--rdmo-app", type=Path, default=DEFAULT_RDMO_APP,
                        help="RDMO instance directory (default: %(default)s)")
    parser.add_argument("--keep", type=int, action="append", default=[],
                        metavar="ID",
                        help="project id to keep (repeatable)")
    parser.add_argument("--list", action="store_true",
                        help="only list the projects, delete nothing")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    args = parser.parse_args()

    rdmo_app = args.rdmo_app.resolve()
    sanity_checks(rdmo_app)
    if os.environ.get(CHILD_ENV_VAR) != "1":
        return reexec_in_instance_env(rdmo_app)
    return child_main(rdmo_app, args.keep, args.yes, args.list)


if __name__ == "__main__":
    sys.exit(main())
