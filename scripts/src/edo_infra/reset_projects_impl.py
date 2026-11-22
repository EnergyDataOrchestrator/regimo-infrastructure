"""Reset the projects database of the local RDMO instance (ORM phase).

Stdlib only — this module runs inside the RDMO instance env (no click), both
as the child phase dispatched by ``edo_infra.child_dispatch`` and for its own
option parsing (argparse).

Deletes all (or all-but-keep) RDMO projects from ``infrastructure/Servers/
rdmo-app`` so that fixture projects can be re-imported cleanly. Related rows
cascade via Django's FK CASCADE: values, snapshots, memberships and the
project's integrations go with the project; catalogs, questionnaires, users
and views are untouched.

Before deleting, the projects are listed (id, title, owner) and a
confirmation prompt requires an explicit answer unless ``--yes`` is given.

Because the CF1 sync engine detects removals via digest comparison against
RDMO, the next ``regimo-core sync`` run after a reset will emit one
``project.removed`` event per vanished project on ``edo.projects.v1`` and
clear the corresponding artifacts/graph — that is expected behaviour, not an
error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .paths import DEFAULT_RDMO_APP


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
        raise SystemExit(2)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="edo-infra reset-projects",
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
    args = parser.parse_args(argv)

    rdmo_app = args.rdmo_app.resolve()
    sanity_checks(rdmo_app)

    # we are already in the instance env child (dispatched by child_dispatch)
    from .instance import instance_child

    instance_child(rdmo_app)
    return child_main(rdmo_app, args.keep, args.yes, args.list)


def child_main(rdmo_app: Path, keep: list[int], assume_yes: bool,
               list_only: bool) -> int:
    from django.apps import apps
    from rdmo.projects.models import Project

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

    before = {
        "Value": 0, "Snapshot": 0, "Membership": 0,
    }
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
