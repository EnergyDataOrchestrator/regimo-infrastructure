"""Create an RDMO project from a DataCite DOI and export it as RDMO XML.

Stdlib only — this module runs inside the RDMO instance env (no click), both
as the child phase dispatched by ``edo_infra.child_dispatch`` and for its own
option parsing (argparse).

Fetches the DataCite metadata for a DOI (default: 10.5445/IR/1000162908,
"Semantico – Toolchain for literature classification"), maps it onto the
questions of the RDMO standard questionary ("RDMO" catalog) that is imported
into ``infrastructure/Servers/rdmo-app``, and:

1. **Project creation** — creates ``Project`` (title/description from the
   DOI), an owner ``Membership`` (default user ``admin``), and ``Value`` rows
   for every question that can be answered from the DOI metadata (single
   values and ``project/dataset`` set values, incl. the
   ``project/dataset/id`` set value). Options are stored as ``Value.option``
   FKs like the interview does; yesno questions store text ``1``/``0`` with
   value_type ``boolean``.
2. **XML export** — renders the project through RDMO's own ``RDMOXMLExport``
   (the same serializer/renderer as the web UI export) and writes it to
   ``infrastructure/fixtures/rdmo/``. The file can be re-imported into any
   RDMO instance (project create -> "Import from file").

The mapping only answers questions that actually exist in the questionary and
warns (and skips) whenever a question or option is missing. Values that would
require guessing (exact dates, ethics/legal details, …) are left out. The
funder (Helmholtz Metadata Collaboration, HMC) is added out-of-band via the
FUNDER_NAME / FUNDER_ID constants — the DOI record carries no funding info.
``project/funder/id`` has no question in the standard questionary, but the
domain attribute exists and the XML import stores it as a plain text value.

Network: DataCite API (api.datacite.org), unless ``--doi-json`` is given.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from .paths import DEFAULT_RDMO_APP, DEFAULT_XML_DIR

DEFAULT_DOI = "10.5445/IR/1000162908"
DATACITE_API = "https://api.datacite.org/dois/"
DEFAULT_OWNER = "admin"

DATASET_PREFIX = "project/dataset"

# Funder added out-of-band (not inferable from the DOI record): Helmholtz
# Metadata Collaboration (HMC).
FUNDER_NAME = "Helmholtz Metadata Collaboration"
FUNDER_ID = "https://helmholtz-metadaten.de/about-hmc"


# ---------------------------------------------------------------------------
# DOI fetch + metadata extraction + value plan
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
    top-level values and values inside the first dataset set both use
    set_prefix='' (RDMO's set_prefix is a chain of set indexes, not a path);
    the entry dict keeps DATASET_PREFIX as a marker for "inside the dataset
    set" and _values_for_project turns it into set_collection=True.
    """
    top = ""                      # set_prefix for top-level values
    ds = f"{DATASET_PREFIX}"      # marker for values inside the dataset set

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
    # toolchain); adjust via the web UI if needed.
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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="edo-infra create-project-from-doi",
        description="Create an RDMO project from a DataCite DOI and export it "
                    "as RDMO XML.")
    parser.add_argument("--doi", default=DEFAULT_DOI, help="DOI to fetch (default: %(default)s)")
    parser.add_argument("--doi-json", default=None,
                        help="Read cached DataCite JSON instead of the API (offline mode).")
    parser.add_argument("--rdmo-app", type=Path, default=DEFAULT_RDMO_APP,
                        help="RDMO instance directory (default: %(default)s)")
    parser.add_argument("--catalog", default=None,
                        help="Catalog URI (default: first available catalog).")
    parser.add_argument("--owner", default=DEFAULT_OWNER,
                        help="Username for the owner membership (default: %(default)s)")
    parser.add_argument("--xml-out", type=Path, default=None,
                        help="Where to write the RDMO XML export "
                             "(default: infrastructure/fixtures/rdmo/<doi-slug>.project.xml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch metadata and print the value plan; no DB writes, no XML.")
    parser.add_argument("--force", action="store_true",
                        help="Create the project even if one with the same title exists.")
    args = parser.parse_args(argv)

    # the child re-exec runs with cwd = rdmo-app; relative paths were typed
    # relative to the invocation directory, so resolve them against that
    from .instance import resolve_invocation_path
    args.rdmo_app = resolve_invocation_path(args.rdmo_app)
    if args.doi_json is not None:
        args.doi_json = str(resolve_invocation_path(Path(args.doi_json)))
    if args.xml_out is not None:
        args.xml_out = resolve_invocation_path(args.xml_out)

    if args.xml_out is None:
        slug = args.doi.lower().replace("/", "-")
        args.xml_out = DEFAULT_XML_DIR / f"doi-{slug}.project.xml"

    # we are already in the instance env child (dispatched by child_dispatch)
    from .instance import instance_child

    rdmo_app = args.rdmo_app.resolve()
    instance_child(rdmo_app)
    return child_main(rdmo_app, args.doi, args.doi_json, args.catalog,
                      args.owner, args.xml_out, args.dry_run, args.force)


def child_main(rdmo_app: Path, doi: str, doi_json: str | None,
               catalog_uri: str | None, owner_name: str, xml_out: Path,
               dry_run: bool, force: bool) -> int:
    from django.contrib.auth import get_user_model
    from django.db import transaction

    from rdmo.domain.models import Attribute
    from rdmo.options.models import Option
    from rdmo.projects.exports import RDMOXMLExport
    from rdmo.projects.models import Membership, Project, Value
    from rdmo.questions.models import Catalog, Question

    # -- 1. DOI metadata ------------------------------------------------------
    payload = fetch_doi_metadata(doi, doi_json)
    meta = extract_metadata(payload)
    plan = build_value_plan(meta)

    if dry_run:
        print(describe_plan(meta, plan))
        print("\n(dry-run) no project created, no XML written")
        return 0

    print(describe_plan(meta, plan))

    # -- 2. resolve catalog, questions, options -------------------------------
    catalog = Catalog.objects.get(uri=catalog_uri) if catalog_uri else Catalog.objects.first()
    if catalog is None:
        print("ERROR: no catalog found (import a questionary first, see "
              "infrastructure/README.md)", file=sys.stderr)
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
                print(f"WARN: option '{option_text}' not found for "
                      f"'{entry['path']}' — skipped", file=sys.stderr)
                continue
            if entry["kind"] == "option+text":
                text = entry["payload"][1]
        resolved.append({**entry, "attribute": attribute, "value_type": value_type,
                         "text": text, "option": option})

    # -- 3. create the project ------------------------------------------------
    if Project.objects.filter(title=meta["title"]).exists() and not force:
        print(f"ERROR: a project titled '{meta['title']}' already exists "
              f"(use --force to create a duplicate)", file=sys.stderr)
        return 1

    owner = get_user_model().objects.filter(username=owner_name).first()
    if owner is None:
        print(f"ERROR: user '{owner_name}' not found", file=sys.stderr)
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
            in_dataset_set = entry["set_prefix"] == DATASET_PREFIX
            created.append(Value(
                project=project, attribute=entry["attribute"],
                set_prefix="", set_index=0,
                set_collection=in_dataset_set,
                collection_index=entry["collection_index"],
                text=entry["text"], option=entry["option"],
                value_type=entry["value_type"], unit="",
            ))
        # per-row save(): rdmo.core.models.Model sets created/updated in save()
        for value in created:
            value.save()

    print(f"OK: created project #{project.pk} '{project.title}' "
          f"with {len(created)} values (owner: {owner_name})")

    # -- 4. export XML via RDMO's own export plugin ---------------------------
    exporter = RDMOXMLExport("xml", "RDMO XML", "rdmo.projects.exports.RDMOXMLExport")
    exporter.project = project
    xml_bytes = exporter.render().content
    xml_out.parent.mkdir(parents=True, exist_ok=True)
    xml_out.write_bytes(xml_bytes)
    print(f"OK: wrote {xml_out} ({xml_out.stat().st_size} bytes)")

    return 0
