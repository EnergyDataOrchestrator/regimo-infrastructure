#!/usr/bin/env python3
"""Admin script — create an RDMO project from a DataCite DOI and export it as RDMO XML.

Fetches the DataCite metadata for a DOI (default: 10.5445/IR/1000162908,
"Semantico – Toolchain for literature classification"), maps it onto the
questions of the RDMO standard questionary ("RDMO" catalog) that is imported
into `infrastructure/Servers/rdmo-app`, and:

1. **Project creation** — creates `Project` (title/description from the DOI),
   an owner `Membership` (default user `admin`), and `Value` rows for every
   question that can be answered from the DOI metadata (single values and
   `project/dataset` set values, incl. the `project/dataset/id` set value).
   Options are stored as `Value.option` FKs like the interview does; yesno
   questions store text `1`/`0` with value_type `boolean`.
2. **XML export** — renders the project through RDMO's own
   `RDMOXMLExport` (the same serializer/renderer as the web UI export) and
   writes it to `infrastructure/fixtures/rdmo/`. The file can be re-imported
   into any RDMO instance (project create -> "Import from file").

The mapping only answers questions that actually exist in the questionary and
warns (and skips) whenever a question or option is missing. Values that would
require guessing (exact dates, ethics/legal details, …) are left out. The
funder (Helmholtz Metadata Collaboration, HMC) is added out-of-band via the
FUNDER_NAME / FUNDER_ID constants — the DOI record carries no funding info.
`project/funder/id` has no question in the standard questionary, but the
domain attribute exists and the XML import stores it as a plain text value.

Run with any Python 3 interpreter — the script re-executes itself with the
RDMO instance env (`env/bin/python`) for the Django ORM work:

    python3 infrastructure/scripts/create_project_from_doi.py [--dry-run]

Network: DataCite API (api.datacite.org), unless `--doi-json` is given.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # infrastructure/scripts
INFRA_DIR = SCRIPT_DIR.parent                         # infrastructure/
DEFAULT_RDMO_APP = INFRA_DIR / "Servers" / "rdmo-app"
DEFAULT_XML_DIR = INFRA_DIR / "fixtures" / "rdmo"

DEFAULT_DOI = "10.5445/IR/1000162908"
DATACITE_API = "https://api.datacite.org/dois/"
DEFAULT_OWNER = "admin"
CHILD_ENV_VAR = "RDMO_PROJECT_FROM_DOI_CHILD"

DATASET_PREFIX = "project/dataset"

# Funder added out-of-band (not inferable from the DOI record): Helmholtz
# Metadata Collaboration (HMC).
FUNDER_NAME = "Helmholtz Metadata Collaboration"
FUNDER_ID = "https://helmholtz-metadaten.de/about-hmc"


# ---------------------------------------------------------------------------
# phase 1 (outer, stdlib only): DOI fetch + metadata extraction + value plan
# ---------------------------------------------------------------------------
def fetch_doi_metadata(doi: str, doi_json: str | None) -> dict:
    if doi_json:
        print(f"Reading DOI metadata from {doi_json}")
        return json.loads(Path(doi_json).read_text(encoding="utf-8"))
    url = DATACITE_API + urllib.parse.quote(doi, safe="")
    print(f"Fetching DOI metadata from {url}")
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_metadata(payload: dict) -> dict:
    attrs = payload.get("data", {}).get("attributes", {})

    creators = [
        f"{c.get('givenName', '')} {c.get('familyName', '')}".strip()
        for c in attrs.get("creators", [])
    ]
    keywords = [s.get("subject") for s in attrs.get("subjects", []) if s.get("subject")]
    rights = (attrs.get("rightsList") or [{}])[0]
    descriptions = attrs.get("descriptions") or []
    abstract = next((d.get("description") for d in descriptions
                     if d.get("descriptionType") == "Abstract"),
                    descriptions[0].get("description") if descriptions else "")

    return {
        "doi": attrs.get("doi"),
        "title": (attrs.get("titles") or [{}])[0].get("title", ""),
        "abstract": abstract or "",
        "creators": creators,
        "keywords": keywords,
        "publication_year": attrs.get("publicationYear"),
        "publisher": attrs.get("publisher") if isinstance(attrs.get("publisher"), str) else "",
        "language": attrs.get("language") or "",
        "url": attrs.get("url") or "",
        "rights": rights.get("rights") or "",
        "rights_uri": rights.get("rightsUri") or "",
        "resource_type": (attrs.get("types") or {}).get("resourceTypeGeneral") or "",
    }


def build_value_plan(meta: dict) -> list[dict]:
    """Map DOI metadata onto RDMO standard-questionary attributes.

    Each entry: attribute path, plus the value payload (text and/or option
    text to resolve against the question's options). Set membership is fixed:
    top-level values use set_prefix='', dataset values use the
    'project/dataset' set (set_index 0).
    """
    top = ""                      # set_prefix for top-level values
    ds = f"{DATASET_PREFIX}"      # set_prefix for values inside the dataset set

    # (path, set_prefix, kind, payload, collection_index)
    # kind: "text" | "boolean" ("1"/"0") | "option" (option_text) |
    #       "option+text" (option_text, additional input stored in Value.text)
    plan: list[dict] = []

    def add(path, set_prefix, kind, payload, coll_idx=0):
        plan.append({"path": path, "set_prefix": set_prefix, "kind": kind,
                     "payload": payload, "collection_index": coll_idx})

    # ---- project level -----------------------------------------------------
    if meta["creators"]:
        add("project/coordination/name", top, "text", [meta["creators"][0]], 0)

    if meta["abstract"]:
        add("project/research_question/title", top, "text", [meta["abstract"]])
    for i, kw in enumerate(meta["keywords"]):
        add("project/research_question/keywords", top, "text", [kw], i)
    # research field is an inference from the topic (literature classification
    # toolchain); adjust via --research-field if needed.
    add("project/research_field/title", top, "option", ["Engineering Sciences / Computer Science"], 0)

    # ---- funder (out-of-band, see FUNDER_NAME / FUNDER_ID) ------------------
    add("project/funder/name", top, "text", [FUNDER_NAME])
    add("project/funder/id", top, "text", [FUNDER_ID])

    # ---- dataset set --------------------------------------------------------
    if meta["abstract"]:
        add(f"{DATASET_PREFIX}/description", ds, "text",
            [f"{meta['abstract']} ({meta['resource_type']}, published via "
             f"{meta['publisher']}, {meta['publication_year']})."])

    add(f"{DATASET_PREFIX}/origin", ds, "option", ["Created"])
    if meta["doi"]:
        add(f"{DATASET_PREFIX}/data_publication_pid", ds, "text", [f"https://doi.org/{meta['doi']}"])
    add(f"{DATASET_PREFIX}/pids/yesno", ds, "boolean", ["1"])
    add(f"{DATASET_PREFIX}/pids/system", ds, "option", ["Handle / DOI"])
    add(f"{DATASET_PREFIX}/sharing/yesno", ds, "option", ["Yes, externally for everyone"])
    add(f"{DATASET_PREFIX}/sharing/repository", ds, "text", [meta["publisher"] or "Zenodo"])
    if meta["rights"]:
        add(f"{DATASET_PREFIX}/sharing/conditions", ds, "option+text",
            ["Other, or exact designation", f"{meta['rights']} ({meta['rights_uri']})"], 0)
    add(f"{DATASET_PREFIX}/preservation/yesno", ds, "boolean", ["1"])
    add(f"{DATASET_PREFIX}/preservation/repository", ds, "option", ["Generic data centre"], 0)
    add(f"{DATASET_PREFIX}/ipr/owner/name", ds, "option", ["Yes"])
    # safe inference: the record is a published report about a software
    # toolchain and contains no personal data.
    add(f"{DATASET_PREFIX}/sensitive_data/personal_data_yesno/yesno", ds, "boolean", ["0"])

    return [entry for entry in plan if entry["payload"] not in (None, [None])]


def describe_plan(meta: dict, plan: list[dict]) -> str:
    lines = [
        f"title       : {meta['title']}",
        f"doi         : {meta['doi']}",
        f"abstract    : {meta['abstract']}",
        f"creators    : {'; '.join(meta['creators'])}",
        f"keywords    : {', '.join(meta['keywords'])}",
        f"publisher   : {meta['publisher']} ({meta['publication_year']}, {meta['resource_type']})",
        f"rights      : {meta['rights']} ({meta['rights_uri']})",
        f"url         : {meta['url']}",
        "",
        f"Planned values ({len(plan)}):",
    ]
    for entry in plan:
        payload = entry["payload"]
        detail = payload if entry["kind"] in ("text", "boolean") else payload[0]
        set_info = entry["set_prefix"] or "(top level)"
        lines.append(f"  [{set_info}] {entry['path']} -> {entry['kind']}: {detail}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# phase 2 (re-exec): hand over to the instance env python
# ---------------------------------------------------------------------------
def reexec_in_instance_env(rdmo_app: Path) -> int:
    env_python = rdmo_app / "env" / "bin" / "python"
    if not env_python.is_file():
        print(f"ERROR: instance env python not found at {env_python}", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env[CHILD_ENV_VAR] = "1"
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    print(f"Running ORM phase with {env_python}")
    return subprocess.run(
        [str(env_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(rdmo_app), env=env,
    ).returncode


# ---------------------------------------------------------------------------
# phase 3 (child, instance env): Django ORM work + XML export
# ---------------------------------------------------------------------------
def child_main(rdmo_app: Path, args: argparse.Namespace) -> int:
    sys.path.insert(0, str(rdmo_app))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django
    django.setup()

    from django.contrib.auth import get_user_model
    from django.db import transaction

    from rdmo.domain.models import Attribute
    from rdmo.options.models import Option
    from rdmo.projects.exports import RDMOXMLExport
    from rdmo.projects.models import Membership, Project, Value
    from rdmo.questions.models import Catalog, Question

    # -- 1. DOI metadata ------------------------------------------------------
    payload = fetch_doi_metadata(args.doi, args.doi_json)
    meta = extract_metadata(payload)
    plan = build_value_plan(meta)

    if args.dry_run:
        print(describe_plan(meta, plan))
        print("\n(dry-run) no project created, no XML written")
        return 0

    print(describe_plan(meta, plan))

    # -- 2. resolve catalog, questions, options -------------------------------
    catalog = Catalog.objects.get(uri=args.catalog) if args.catalog else Catalog.objects.first()
    if catalog is None:
        print("ERROR: no catalog found (import a questionary first, see infrastructure/README.md)",
              file=sys.stderr)
        return 1
    print(f"Using catalog: {catalog.uri} ({catalog.title})")

    attributes = {a.path: a for a in Attribute.objects.filter(
        path__in={e["path"] for e in plan} | {f"{DATASET_PREFIX}/id"})}

    # options of each question (via its optionsets), matched by exact or
    # prefix text match, like the interview would resolve them
    def question_for(path: str):
        return (Question.objects.filter(attribute__path=path).first())

    def option_for(question, option_text: str):
        options = [o for os_ in question.optionsets.all() for o in os_.options.all()]
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
            # attribute exists in the domain but has no question in the catalog
            # (e.g. project/funder/id) — only plain text values can be stored
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
                print(f"WARN: option '{option_text}' not found for '{entry['path']}' — skipped",
                      file=sys.stderr)
                continue
            if entry["kind"] == "option+text":
                text = entry["payload"][1]
        resolved.append({**entry, "attribute": attribute, "value_type": value_type,
                         "text": text, "option": option})

    # -- 3. create the project ------------------------------------------------
    if Project.objects.filter(title=meta["title"]).exists() and not args.force:
        print(f"ERROR: a project titled '{meta['title']}' already exists "
              f"(use --force to create a duplicate)", file=sys.stderr)
        return 1

    owner = get_user_model().objects.filter(username=args.owner).first()
    if owner is None:
        print(f"ERROR: user '{args.owner}' not found", file=sys.stderr)
        return 1

    with transaction.atomic():
        project = Project.objects.create(
            title=meta["title"], description=meta["abstract"], catalog=catalog,
        )
        Membership.objects.create(project=project, user=owner, role="owner")

        created = []
        # set value for the dataset set (collection page attribute project/dataset/id)
        set_attribute = attributes.get(f"{DATASET_PREFIX}/id")
        if set_attribute and any(e["set_prefix"] == DATASET_PREFIX for e in resolved):
            created.append(Value(
                project=project, attribute=set_attribute, set_prefix="", set_index=0,
                set_collection=True, collection_index=0, text="", value_type="text",
            ))
        for entry in resolved:
            created.append(Value(
                project=project, attribute=entry["attribute"],
                set_prefix=entry["set_prefix"], set_index=0,
                set_collection=bool(entry["set_prefix"]),
                collection_index=entry["collection_index"],
                text=entry["text"], option=entry["option"],
                value_type=entry["value_type"], unit="",
            ))
        # per-row save(): rdmo.core.models.Model sets created/updated in save()
        for value in created:
            value.save()

    print(f"OK: created project #{project.pk} '{project.title}' "
          f"with {len(created)} values (owner: {args.owner})")

    # -- 4. export XML via RDMO's own export plugin ---------------------------
    exporter = RDMOXMLExport("xml", "RDMO XML", "rdmo.projects.exports.RDMOXMLExport")
    exporter.project = project
    xml_bytes = exporter.render().content
    args.xml_out.parent.mkdir(parents=True, exist_ok=True)
    args.xml_out.write_bytes(xml_bytes)
    print(f"OK: wrote {args.xml_out} ({args.xml_out.stat().st_size} bytes)")

    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an RDMO project from a DataCite DOI and export it as RDMO XML.")
    parser.add_argument("--doi", default=DEFAULT_DOI, help=f"DOI to fetch (default: %(default)s)")
    parser.add_argument("--doi-json", default=None,
                        help="Read cached DataCite JSON instead of the API (offline mode).")
    parser.add_argument("--rdmo-app", type=Path, default=DEFAULT_RDMO_APP,
                        help="RDMO instance directory (default: %(default)s)")
    parser.add_argument("--catalog", default=None,
                        help="Catalog URI (default: first available catalog).")
    parser.add_argument("--owner", default=DEFAULT_OWNER,
                        help=f"Username for the owner membership (default: %(default)s)")
    parser.add_argument("--xml-out", type=Path, default=None,
                        help="Where to write the RDMO XML export "
                             "(default: infrastructure/fixtures/rdmo/<doi-slug>.project.xml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch metadata and print the value plan; no DB writes, no XML.")
    parser.add_argument("--force", action="store_true",
                        help="Create the project even if one with the same title exists.")
    args = parser.parse_args()

    if args.xml_out is None:
        slug = args.doi.lower().replace("/", "-")
        args.xml_out = DEFAULT_XML_DIR / f"doi-{slug}.project.xml"

    if os.environ.get(CHILD_ENV_VAR) != "1":
        return reexec_in_instance_env(args.rdmo_app)
    return child_main(args.rdmo_app, args)


if __name__ == "__main__":
    raise SystemExit(main())
