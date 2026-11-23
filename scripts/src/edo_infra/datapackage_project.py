"""Create an RDMO project from an OEMetadata datapackage and export it as XML.

Stdlib only — this module runs inside the RDMO instance env (no click), both
as the child phase dispatched by :mod:`edo_infra.instance` and for its own
option parsing (argparse). It mirrors :mod:`edo_infra.doi_project`
(``create-project-from-doi``), but reads the metadata from a local
**datapackage.json** (OEMetadata v2, e.g.
``infrastructure/fixtures/rdmo/iai_active_power_pv_202302/datapackage.json``)
instead of the DataCite API.

What it does:

1. **Project creation** — creates ``Project`` (title/description from the
   package), an owner ``Membership`` (default user ``admin``) and ``Value``
   rows for every question answerable from the datapackage: top-level values
   (contact, description, keywords, funder) and **one ``project/dataset`` set
   per ``resource``** (set value ``project/dataset/id`` with the resource
   title as display name, plus description, format, creation method, sharing
   and preservation answers). Options are stored as ``Value.option`` FKs like
   the interview does; yesno questions store text ``1``/``0`` with value_type
   ``boolean``.
2. **XML export** — renders the project through RDMO's own
   ``RDMOXMLExport`` and writes it to
   ``infrastructure/fixtures/rdmo/datapackage-<name>.project.xml`` so it can
   be re-imported into any RDMO instance.

The mapping answers only questions that exist in the questionary and warns
(and skips) whenever a question or option is missing. Values that would
require guessing are left out — no personal-data or PID answers are invented
from a package that does not carry them (CF1-013: no fabricated data). When a
CSV companion file sits next to the datapackage
(``<resource.name>.csv`` or ``<directory-name>.csv``), its row/column count is
folded into the dataset's format description.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from .paths import DEFAULT_RDMO_APP, DEFAULT_XML_DIR
from .instance import resolve_invocation_path

DEFAULT_DATAPACKAGE = (DEFAULT_XML_DIR
                       / "iai_active_power_pv_202302" / "datapackage.json")
DEFAULT_OWNER = "admin"

DATASET_PREFIX = "project/dataset"

HOST_LABELS = {
    "openenergy-platform.org": "OpenEnergy Platform",
}


# ---------------------------------------------------------------------------
# Datapackage extraction + value plan
# ---------------------------------------------------------------------------
def extract_metadata(dp: dict) -> dict:
    """Normalize an OEMetadata v2 datapackage into the value-plan input."""
    resources = []
    for res in dp.get("resources") or []:
        if not isinstance(res, dict):
            continue
        schema = res.get("schema") or {}
        fields = [f for f in schema.get("fields") or []
                  if isinstance(f, dict) and (f.get("name") or "").strip()]
        context = res.get("context") or {}
        temporal = res.get("temporal") or {}
        timeseries = (temporal.get("timeseries") or [{}])[0] if isinstance(temporal, dict) else {}
        licenses = [l for l in res.get("licenses") or []
                    if isinstance(l, dict) and (l.get("name") or "").strip()]
        resources.append({
            "name": res.get("name") or "",
            "title": res.get("title") or "",
            "path": res.get("path") or "",
            "description": res.get("description") or "",
            "format": res.get("format") or "",
            "fields": fields,
            "keywords": [k for k in res.get("keywords") or [] if (k or "").strip()],
            "contact": context.get("contact") or "",
            "funding_agency": context.get("fundingAgency") or "",
            "grant_no": context.get("grantNo") or "",
            "license": licenses[0] if licenses else None,
            "timeseries": timeseries if isinstance(timeseries, dict) else {},
            "publication_date": res.get("publicationDate") or "",
        })

    first = resources[0] if resources else {}
    return {
        "title": (dp.get("title") or "").strip()
                 or first.get("title") or first.get("name") or "",
        "description": (dp.get("description") or "").strip()
                       or first.get("description") or "",
        "metadata_version": ((dp.get("metaMetadata") or {}).get("metadataVersion") or ""),
        "resources": resources,
    }


def companion_csv(dp_path: Path, resource: dict) -> Path | None:
    """The data file next to the datapackage (<resource.name>.csv or the
    directory-name.csv), None when neither exists."""
    directory = dp_path.parent
    for candidate in (f"{resource['name']}.csv", f"{directory.name}.csv"):
        path = directory / candidate
        if path.is_file():
            return path
    return None


def csv_shape(path: Path) -> tuple[int, int]:
    """(rows, columns) of a CSV file, header row excluded."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return 0, 0
    return max(len(rows) - 1, 0), max(len(row) for row in rows)


def dataset_description(resource: dict) -> str:
    """The dataset description: base description + everything the package
    knows about the table (path, coverage, license, columns)."""
    lines = [resource["description"] or resource["title"] or resource["name"]]
    if resource["path"]:
        lines.append(f"Published at: {resource['path']}")
    ts = resource["timeseries"]
    if ts.get("start") or ts.get("end"):
        coverage = f"Temporal coverage: {ts.get('start', '?')} … {ts.get('end', '?')}"
        resolution = " ".join(part for part in
                              (str(ts.get("resolutionValue", "")).strip(),
                               (ts.get("resolutionUnit") or "").strip()) if part)
        details = [part for part in (
            f"resolution {resolution}" if resolution else "",
            f"aggregation {ts['aggregationType']}" if ts.get("aggregationType") else "",
        ) if part]
        if details:
            coverage += f" ({', '.join(details)})"
        lines.append(coverage + ".")
    license_ = resource["license"]
    if license_:
        title = f" ({license_['title']})" if license_.get("title") else ""
        path = f" — {license_['path']}" if license_.get("path") else ""
        lines.append(f"License: {license_['name']}{title}{path}.")
    fields = resource["fields"]
    if fields:
        lines.append(f"Columns ({len(fields)}):")
        for field in fields:
            unit = f", unit {field['unit']}" if (field.get("unit") or "").strip() else ""
            description = f" — {field['description']}" if (field.get("description") or "").strip() else ""
            lines.append(f"- {field['name']} ({field.get('type', '')}{unit}){description}")
    return "\n".join(lines)


def dataset_format(resource: dict, csv_path: Path | None) -> str:
    fields = resource["fields"]
    columns = ", ".join(f["name"] for f in fields) if fields else ""
    if csv_path is not None:
        rows, cols = csv_shape(csv_path)
        shape = f"{rows} rows x {cols} columns"
        detail = f"; columns: {columns}" if columns else ""
        return f"CSV ({shape}{detail})"
    if resource["format"]:
        detail = f"; columns: {columns}" if columns else ""
        return f"{resource['format']} ({len(fields)} fields{detail})"
    detail = f"; columns: {columns}" if columns else ""
    return f"Table ({len(fields)} columns{detail})"


def dataset_creation(resource: dict, metadata_version: str) -> str:
    parts = []
    if resource["publication_date"]:
        parts.append(f"published {resource['publication_date']}")
    if metadata_version:
        parts.append(f"provided as an OEMetadata datapackage ({metadata_version})")
    if not parts:
        return "Data provided as an OEMetadata datapackage."
    return "Data " + ", ".join(parts) + "."


def repository_for(resource: dict) -> str:
    host = urlparse(resource["path"]).hostname or "" if resource["path"] else ""
    for known, label in HOST_LABELS.items():
        if host == known or host.endswith("." + known):
            return label
    return ""


def build_value_plan(meta: dict, dp_path: Path) -> list[dict]:
    """Map the datapackage metadata onto RDMO standard-questionary attributes.

    Entry schema as in :mod:`edo_infra.doi_project` (attribute path, kind,
    payload, collection_index), extended by ``set_index`` — the
    ``project/dataset`` set the entry belongs to (one set per resource).
    kind: "text" | "boolean" ("1"/"0") | "option" (option_text) |
    "option+text" (option_text, additional input for Value.text).
    """
    top = ""
    ds = DATASET_PREFIX

    plan: list[dict] = []

    def add(path, set_prefix, kind, payload, coll_idx=0, set_index=0):
        plan.append({"path": path, "set_prefix": set_prefix, "kind": kind,
                     "payload": payload, "collection_index": coll_idx,
                     "set_index": set_index})

    # ---- project level -----------------------------------------------------
    contact = next((r["contact"] for r in meta["resources"] if r["contact"]), "")
    if contact:
        add("project/coordination/name", top, "text", [contact])
    if meta["description"]:
        add("project/research_question/title", top, "text", [meta["description"]])

    keywords: list[str] = []
    for resource in meta["resources"]:
        for keyword in resource["keywords"]:
            if keyword not in keywords:
                keywords.append(keyword)
    for i, keyword in enumerate(keywords):
        add("project/research_question/keywords", top, "text", [keyword], i)

    funder = next((r["funding_agency"] for r in meta["resources"]
                   if r["funding_agency"]), "")
    if funder:
        add("project/funder/name", top, "text", [funder])

    # ---- one dataset set per resource ---------------------------------------
    for i, resource in enumerate(meta["resources"]):
        name = resource["title"] or resource["name"]
        add(f"{DATASET_PREFIX}/description", ds, "text",
            [dataset_description(resource)], 0, i)
        add(f"{DATASET_PREFIX}/format", ds, "text",
            [dataset_format(resource, companion_csv(dp_path, resource))], 0, i)
        add(f"{DATASET_PREFIX}/creation_methods", ds, "text",
            [dataset_creation(resource, meta["metadata_version"])], 0, i)
        add(f"{DATASET_PREFIX}/origin", ds, "option", ["Created"], 0, i)

        repository = repository_for(resource) or resource["path"]
        license_ = resource["license"]
        if license_ or repository:
            add(f"{DATASET_PREFIX}/sharing/yesno", ds, "option",
                ["Yes, externally for everyone"], 0, i)
        if repository:
            add(f"{DATASET_PREFIX}/sharing/repository", ds, "text", [repository], 0, i)
        if license_:
            title = f" ({license_['title']})" if license_.get("title") else ""
            path = f" — {license_['path']}" if license_.get("path") else ""
            add(f"{DATASET_PREFIX}/sharing/conditions", ds, "option+text",
                ["Other, or exact designation", f"{license_['name']}{title}{path}"], 0, i)
        # no personal-data or PID answers: the package carries no such
        # information, and none is invented (CF1-013)

    return [entry for entry in plan if entry["payload"] not in (None, [None])]


def describe_plan(meta: dict, plan: list[dict]) -> str:
    lines = [
        f"title       : {meta['title']}",
        f"description : {meta['description']}",
        f"resources   : {len(meta['resources'])}",
        "",
        f"Planned values ({len(plan)}):",
    ]
    for entry in plan:
        payload = entry["payload"]
        detail = payload if entry["kind"] in ("text", "boolean") else payload[0]
        set_info = ("(top level)" if entry["set_prefix"] == ""
                    else f"dataset {entry['set_index']}")
        lines.append(f"  [{set_info}] {entry['path']} -> {entry['kind']}: {detail}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Instance phase: resolve the plan against the questionary, create, export
# ---------------------------------------------------------------------------
def child_main(rdmo_app: Path, dp_path: Path, catalog_uri: str | None,
               owner_name: str, xml_out: Path, dry_run: bool, force: bool) -> int:
    from django.contrib.auth import get_user_model
    from django.db import transaction

    from rdmo.domain.models import Attribute
    from rdmo.options.models import Option
    from rdmo.projects.exports import RDMOXMLExport
    from rdmo.projects.models import Membership, Project, Value
    from rdmo.questions.models import Catalog, Question

    meta = extract_metadata(json.loads(dp_path.read_text(encoding="utf-8")))
    plan = build_value_plan(meta, dp_path)

    if dry_run:
        print(describe_plan(meta, plan))
        print("\n(dry-run) no project created, no XML written")
        return 0

    print(describe_plan(meta, plan))

    # -- 1. resolve catalog, questions, options -------------------------------
    catalog = Catalog.objects.get(uri=catalog_uri) if catalog_uri else Catalog.objects.first()
    if catalog is None:
        print("ERROR: no catalog found (import a questionary first, see "
              "infrastructure/README.md)", file=sys.stderr)
        return 1
    print(f"Using catalog: {catalog.uri} ({catalog.title})")

    attributes = {a.path: a for a in Attribute.objects.filter(
        path__in={entry["path"] for entry in plan} | {f"{DATASET_PREFIX}/id"})}

    def question_for(path: str):
        return Question.objects.filter(attribute__path=path).first()

    def option_for(question, option_text: str):
        options = [o for optionset in question.optionsets.all()
                   for o in optionset.options.all()]
        for option in options:
            if option.text == option_text:
                return option
        for option in options:
            if option.text.startswith(option_text):
                return option
        return None

    resolved = []
    for entry in plan:
        attribute = attributes.get(entry["path"])
        question = question_for(entry["path"]) if attribute else None
        if attribute is None:
            print(f"WARN: no attribute '{entry['path']}' — skipped", file=sys.stderr)
            continue
        if question is None:
            # attribute exists in the domain but has no question in the
            # catalog — only plain text values can be stored
            if entry["kind"] != "text":
                print(f"WARN: no question for attribute '{entry['path']}' — skipped",
                      file=sys.stderr)
                continue
            value_type = "text"
        else:
            value_type = question.value_type
        text = ""
        option = None
        if entry["kind"] in ("text", "boolean"):
            text = entry["payload"][0]
        elif entry["kind"] in ("option", "option+text"):
            option_text = entry["payload"][0]
            option = option_for(question, option_text)
            if option is None:
                print(f"WARN: option '{option_text}' not found for "
                      f"'{entry['path']}' — skipped", file=sys.stderr)
                continue
            if entry["kind"] == "option+text":
                text = entry["payload"][1]
        resolved.append({**entry, "attribute": attribute, "value_type": value_type,
                         "text": text, "option": option})

    # -- 2. create the project ------------------------------------------------
    if Project.objects.filter(title=meta["title"]).exists() and not force:
        print(f"ERROR: a project titled '{meta['title']}' already exists "
              f"(use --force to create a duplicate)", file=sys.stderr)
        return 1

    owner = get_user_model().objects.filter(username=owner_name).first()
    if owner is None:
        print(f"ERROR: user '{owner_name}' not found", file=sys.stderr)
        return 1

    resource_names = [r["title"] or r["name"] for r in meta["resources"]]

    with transaction.atomic():
        project = Project.objects.create(
            title=meta["title"], description=meta["description"], catalog=catalog,
        )
        Membership.objects.create(project=project, user=owner, role="owner")

        created = []
        # the set value of each dataset set (project/dataset/id) carries the
        # resource title as display name — RDMO/maDMP show the set row's text
        # as the dataset name (see add_dataset.py)
        set_attribute = attributes.get(f"{DATASET_PREFIX}/id")
        dataset_sets = sorted({entry["set_index"] for entry in resolved
                               if entry["set_prefix"] == DATASET_PREFIX})
        if set_attribute is None:
            print("WARN: no attribute 'project/dataset/id' — no dataset set "
                  "value created; the dataset(s) will not be visible in RDMO",
                  file=sys.stderr)
        for set_index in dataset_sets:
            created.append(Value(
                    project=project, attribute=set_attribute,
                    set_prefix="", set_index=set_index, set_collection=True,
                    collection_index=0,
                    text=resource_names[set_index] if set_index < len(resource_names) else "",
                    value_type="text",
                ))
        for entry in resolved:
            in_dataset_set = entry["set_prefix"] == DATASET_PREFIX
            created.append(Value(
                project=project, attribute=entry["attribute"],
                set_prefix="", set_index=entry["set_index"],
                set_collection=in_dataset_set,
                collection_index=entry["collection_index"],
                text=entry["text"], option=entry["option"],
                value_type=entry["value_type"], unit="",
            ))
        # per-row save(): rdmo.core.models.Model sets created/updated in save()
        for value in created:
            value.save()

    print(f"OK: created project #{project.pk} '{project.title}' "
          f"with {len(created)} values in {len(dataset_sets)} dataset set(s) "
          f"(owner: {owner_name})")

    # -- 3. export XML via RDMO's own export plugin ---------------------------
    exporter = RDMOXMLExport("xml", "RDMO XML", "rdmo.projects.exports.RDMOXMLExport")
    exporter.project = project
    xml_bytes = exporter.render().content
    xml_out.parent.mkdir(parents=True, exist_ok=True)
    xml_out.write_bytes(xml_bytes)
    print(f"OK: wrote {xml_out} ({xml_out.stat().st_size} bytes)")

    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="edo-infra create-project-from-datapackage",
        description="Create an RDMO project from an OEMetadata datapackage "
                    "(datapackage.json) and export it as RDMO XML.")
    parser.add_argument("--datapackage", type=Path, default=DEFAULT_DATAPACKAGE,
                        help="Path to the datapackage.json "
                             "(default: %(default)s)")
    parser.add_argument("--rdmo-app", type=Path, default=DEFAULT_RDMO_APP,
                        help="RDMO instance directory (default: %(default)s)")
    parser.add_argument("--catalog", default=None,
                        help="Catalog URI (default: first available catalog).")
    parser.add_argument("--owner", default=DEFAULT_OWNER,
                        help="Username for the owner membership (default: %(default)s)")
    parser.add_argument("--xml-out", type=Path, default=None,
                        help="Where to write the RDMO XML export "
                             "(default: infrastructure/fixtures/rdmo/"
                             "datapackage-<name>.project.xml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the value plan; no DB writes, no XML.")
    parser.add_argument("--force", action="store_true",
                        help="Create the project even if one with the same title exists.")
    args = parser.parse_args(argv)

    # the child re-exec runs with cwd = rdmo-app; relative paths were typed
    # relative to the invocation directory, so resolve them against that
    args.datapackage = resolve_invocation_path(args.datapackage)
    args.rdmo_app = resolve_invocation_path(args.rdmo_app)
    if args.xml_out is not None:
        args.xml_out = resolve_invocation_path(args.xml_out)

    if not args.datapackage.is_file():
        print(f"ERROR: datapackage not found: {args.datapackage}", file=sys.stderr)
        return 2

    if args.xml_out is None:
        name = (extract_metadata(json.loads(
            args.datapackage.read_text(encoding="utf-8")))["title"]
            or args.datapackage.parent.name)
        slug = "".join(c if c.isalnum() or c in "-_" else "-"
                       for c in name.lower().replace(" ", "-"))
        args.xml_out = DEFAULT_XML_DIR / f"datapackage-{slug}.project.xml"

    # we are already in the instance env child (dispatched by child_dispatch)
    from .instance import instance_child

    rdmo_app = args.rdmo_app.resolve()  # absolute by now
    instance_child(rdmo_app)
    return child_main(rdmo_app, args.datapackage, args.catalog,
                      args.owner, args.xml_out, args.dry_run, args.force)
