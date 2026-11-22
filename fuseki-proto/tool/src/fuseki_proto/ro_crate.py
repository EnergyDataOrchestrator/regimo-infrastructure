"""ro_crate.py — RO-Crate generation from the EDO internal format (card CF2-006).

Packages a linked DMP+SMS internal-format instance (the EDO pivot graph, the
CF2-005 deliverable ``linked-instance.example.json``) into a self-contained
RO-Crate 1.1 directory.

The generator uses the **`rocrate`** library (`rocrate` 0.16.0, the maintained
`ro-crate-py` implementation) to build and serialise the crate, so the produced
``ro-crate-metadata.json`` is spec-conformant by construction. Only the
internal-format field extraction is read from the compact JSON-LD directly
(via the stdlib ``json`` module) — no custom JSON-LD serializer is reimplemented.

The output directory is a valid RO-Crate 1.1:

  * ``ro-crate-metadata.json``      — the RO-Crate metadata file (root
    ``Dataset`` with name/description/datePublished/license plus the packaged
    graph as a ``File`` data entity and the sensor / measured properties /
    distribution / contact as contextual entities).
  * ``data/project-graph.jsonld``   — a copy of the internal-format instance as
    the packaged "data" entity.
  * ``README.md``                   — documentation of the crate.
  * ``validation-report.json``      — the generator's structural self-check,
    to be followed by a full spec validation with ``nova-crate`` (spec-v1.1).

Run ``fuseki-proto crate generate --help`` for options.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
import shutil
from typing import cast

import click
from rocrate.rocrate import ROCrate

# rocrate ships no type stubs — import its entity model so the checker can
# resolve `.id`, `__setitem__` and `append_to` on the objects we build.
from rocrate.model.entity import Entity
from rocrate.model.file import File

from . import docker as D

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
TOOL_DIR = D.TOOL_DIR                      # .../fuseki-proto/tool
PROTO_DIR = TOOL_DIR.parent                # .../fuseki-proto
SCRIPTS_DIR = PROTO_DIR.parent             # .../scripts
# the linked DMP+SMS internal-format instance (CF2-005) is the default input
LINKED_DEFAULT = SCRIPTS_DIR / "internal-format" / "linked-instance.example.json"

# the internal-format schema the packaged graph conforms to (reference)
SCHEMA_REL = (
    "https://w3id.org/edo/schemas/internal-format"
)

RO_CRATE_VERSION = "1.1"
RO_PROFILE = f"https://w3id.org/ro/crate/{RO_CRATE_VERSION}"

# namespace prefixes of the internal-format compact JSON-LD
NS = {
    "edo": "https://w3id.org/edo/terms/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "prov": "http://www.w3.org/ns/prov#",
    "time": "http://www.w3.org/2006/time#",
    "sosa": "http://www.w3.org/ns/sosa/",
    "smscv": "https://sms-cv.helmholtz.cloud/sms/cv/api/v1/",
}
SOSA = NS["sosa"]
SMSCV = NS["smscv"]


# ---------------------------------------------------------------------------
# internal-format extraction helpers (compacted JSON-LD over json)
# ---------------------------------------------------------------------------
def _as_dict(seg):
    return seg if isinstance(seg, dict) else {}


def _text(seg) -> str:
    """Human text of a scalar value; ignores IRIs/node objects."""
    if isinstance(seg, str):
        return seg
    if isinstance(seg, bool):
        return str(seg).lower()
    if isinstance(seg, (int, float)):
        return str(seg)
    return ""


def _expand_uri(v: str) -> str:
    """Expand a ``smscv:`` prefixed URI to the full SMS-CV base URI."""
    if isinstance(v, str) and v.startswith("smscv:"):
        return f"{SMSCV}{v.split(':', 1)[1]}"
    return v


# short, human names for a few known license URIs (used for the license
# contextual entity's ``name``; falls back to the last URI path segment)
_LICENSE_NAMES = {
    "https://creativecommons.org/licenses/by/4.0/": "CC BY 4.0",
    "https://spdx.org/licenses/MIT": "MIT",
    "https://creativecommons.org/licenses/by-nc-sa/3.0/au/":
        "CC BY-NC-SA 3.0 AU",
}


def _license_name(uri: str) -> str:
    return _LICENSE_NAMES.get(uri) or uri.rstrip("/").rsplit("/", 1)[-1]


def _first_text(items, *keys):
    for k in keys:
        v = _text(_val(items, k))
        if v:
            return v
    return ""


def _val(obj, key):
    return obj.get(key) if isinstance(obj, dict) else None


# ---------------------------------------------------------------------------
# crate construction
# ---------------------------------------------------------------------------
def _build(doc: dict, src: Path, out: Path) -> ROCrate:
    """Build the RO-Crate from the internal-format compact JSON-LD instance."""
    project = _as_dict(doc)
    project_title = _first_text(project, "dcterms:title")

    dataset = _as_dict(_val(project, "dcat:dataset"))
    ds_id = _first_text(dataset, "@id") or "edo:dataset:weatherstation-q3-2026"
    ds_title = _first_text(dataset, "dcterms:title") or "Dataset"
    ds_description = _first_text(dataset, "dcterms:description")
    keywords = _val(dataset, "dcat:keyword") or []

    # --- distribution / license --------------------------------------------
    license_uri = None
    for dist in (_val(dataset, "dcat:distribution") or []):
        lic = _as_dict(_val(dist, "edo:license"))
        lu = _val(lic, "dcterms:license")
        if lu:
            license_uri = _text(lu)

    # --- sensor + measured properties (the DMP-SMS link, CF2-005) ----------
    sensor = _as_dict(_val(dataset, "prov:wasGeneratedBy"))
    sensor_id = _first_text(sensor, "@id")
    sensor_title = _first_text(sensor, "dcterms:title")
    sensor_pid = _first_text(_as_dict(_val(sensor, "edo:identifier")),
                             "dcterms:identifier")
    props = [_as_dict(x) for x in (_val(sensor, "sosa:observes") or [])]

    # --- contact ------------------------------------------------------------
    contact = _as_dict(_val(project, "edo:hasContact"))
    contact_name = _first_text(contact, "foaf:name")

    # --- build the crate ----------------------------------------------------
    crate = ROCrate(version=RO_CRATE_VERSION)
    root = crate.root_dataset

    root["name"] = ds_title
    root["description"] = ds_description or (
        f"RO-Crate package of the EDO internal-format instance '{ds_title}' "
        f"(linked DMP + SMS) for the project '{project_title}'."
    )
    root["datePublished"] = _dt.date.today().isoformat()

    if keywords:
        root["keywords"] = list(keywords)

    # license -> contextual CreativeWork entity (RO-Crate 1.1 root requirement:
    # license SHOULD link to a contextual entity with name and description)
    if license_uri:
        lic = cast(Entity, crate.add_jsonld({
            "@id": license_uri,
            "@type": "CreativeWork",
            "name": _license_name(license_uri),
            "description": f"License of the packaged dataset ({license_uri}).",
        }))
        root["license"] = {"@id": lic.id}

    # the packaged internal-format graph as a File data entity
    data_id = "data/project-graph.jsonld"
    graph_file = cast(File, crate.add_file(
        src,
        data_id,
        properties={
            "name": "internal-format graph (linked DMP+SMS)",
            "encodingFormat": "application/ld+json",
            "conformsTo": {"@id": SCHEMA_REL},
            "description": (
                "EDO internal-format pivot graph: Project > Dataset "
                "prov:wasGeneratedBy Sensor, Sensor sosa:observes "
                "MeasuredProperty[]."
            ),
        },
    ))

    # provenance: CreateAction linking the source instance -> packaged file
    action = cast(Entity, crate.add_jsonld({
        "@id": "#generate-action",
        "@type": "CreateAction",
        "name": "internal-format -> RO-Crate generation (CF2-006)",
        "description": (
            "Generated by 'fuseki-proto crate generate' from the linked "
            "DMP+SMS internal-format instance."
        ),
        "endTime": _dt.datetime.now().isoformat(timespec="seconds"),
        "object": {"@id": ds_id},
        "result": {"@id": data_id},
        "instrument": {
            "@id": "https://github.com/researchobject/ro-crate-py",
        },
    }))
    graph_file["prov:wasGeneratedBy"] = {"@id": action.id}

    # contextual: the sensor (DMP-SMS link) + its measured properties
    if sensor_id or sensor_title:
        sensor_ent = cast(Entity, crate.add_jsonld({
            "@id": sensor_id or "https://sms.atmohub.kit.edu/devices/67",
            "@type": f"{SOSA}Sensor",
            "name": sensor_title or "Sensor",
            "identifier": sensor_pid or sensor_id,
        }))
        root["prov:wasGeneratedBy"] = {"@id": sensor_ent.id}  # CF2-005 link
        for i, p_ in enumerate(props, start=1):
            q = _expand_uri(_text(_val(p_, "smscv:measuredQuantity")))
            qname = _first_text(p_, "dcterms:title") or q
            prop_id = q or f"#measured-property-{i}"
            prop_ent = cast(Entity, crate.add_jsonld({
                "@id": prop_id,
                "@type": f"{SOSA}ObservableProperty",
                "name": qname,
            }))
            if q:
                prop_ent["identifier"] = q
            sensor_ent.append_to("observes", {"@id": prop_id})
            root.append_to("observes", {"@id": prop_id})

    # contextual: contact
    if contact_name:
        contact_ent = cast(Entity, crate.add_jsonld({
            "@id": "#contact",
            "@type": "Person",
            "name": contact_name,
        }))
        root["creator"] = {"@id": contact_ent.id}

    return crate


# ---------------------------------------------------------------------------
# structural self-check
# ---------------------------------------------------------------------------
def _validate(crate_dir: Path, name: str, input_file: Path) -> dict:
    """Run a structural RO-Crate 1.1 self-check and return a report dict."""
    meta_path = crate_dir / "ro-crate-metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    graph = meta["@graph"]

    def g(id_):
        return next((e for e in graph if e.get("@id") == id_), None)

    root = g("./")
    checks = []

    checks.append({
        "id": "root-dataset",
        "desc": "Root Data Entity is a Dataset (@id './')",
        "ok": bool(root and root.get("@type") == "Dataset"),
    })
    required = ("name", "description", "datePublished", "license")
    missing = [k for k in required if not (root or {}).get(k)]
    checks.append({
        "id": "root-required",
        "desc": f"Root has RO-Crate 1.1 required properties {list(required)}",
        "ok": not missing,
        "detail": f"missing: {missing}" if missing else "all present",
    })

    # every File data entity physically resides in the crate (nova-crate's
    # dataEntityFileError check, approximated)
    files_fail = []
    for e in graph:
        if e.get("@type") == "File" and e.get("@id") not in ("", "ro-crate-metadata.json"):
            target = crate_dir / e["@id"]
            if not target.is_file():
                files_fail.append(e["@id"])
    checks.append({
        "id": "files-resolve",
        "desc": "Every File data entity resolves inside the crate",
        "ok": not files_fail,
        "detail": f"unresolved: {files_fail}" if files_fail else "all resolve",
    })

    # the DMP-SMS link is reflected in the crate
    has_sensor = any(
        e.get("@type") == f"{SOSA}Sensor" for e in graph
    )
    checks.append({
        "id": "dmp-sms-link",
        "desc": "The DMP-SMS link is reflected (a Sensor entity is present)",
        "ok": bool(has_sensor),
    })

    # the packaged data file round-trips to the input
    data_path = crate_dir / "data" / "project-graph.jsonld"
    if data_path.is_file():
        input_doc = json.loads(input_file.read_text(encoding="utf-8"))
        data_doc = json.loads(data_path.read_text(encoding="utf-8"))
        checks.append({
            "id": "input-preserved",
            "desc": "Packaged graph equals the internal-format input",
            "ok": data_doc == input_doc,
        })

    passed = sum(1 for c in checks if c["ok"])
    return {
        "generator": "fuseki-proto crate generate (CF2-006)",
        "package": name,
        "input": str(input_file),
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "ro_crate_profile": RO_PROFILE,
        "checks": checks,
        "verdict": f"{passed}/{len(checks)} structural checks passed",
        "note": (
            "Structural self-check only. Validate the whole directory with an "
            "RO-Crate spec validator such as nova-crate (spec-v1.1)."
        ),
    }


def _readme(name: str, ds_title: str) -> str:
    return (
        f"# RO-Crate: `{name}`\n\n"
        f"This directory is an RO-Crate {RO_CRATE_VERSION} package generated "
        f"from the EDO internal format (card CF2-006) for the linked DMP+SMS "
        f"instance **{ds_title}**.\n\n"
        f"## Contents\n\n"
        f"- `ro-crate-metadata.json` — the RO-Crate metadata file (root "
        f"`Dataset` with name, description, datePublished and license, the "
        f"packaged graph as a `File` data entity, and the sensor / measured "
        f"properties as contextual entities).\n"
        f"- `data/project-graph.jsonld` — the packaged internal-format graph "
        f"(`Project > Dataset prov:wasGeneratedBy Sensor, Sensor sosa:observes "
        f"MeasuredProperty[]`).\n"
        f"- `validation-report.json` — the generator's structural self-check.\n"
        f"\n"
        f"## How it was produced\n\n"
        f"Run `fuseki-proto crate generate` (see "
        f"`../fuseki-proto/tool/src/fuseki_proto/ro_crate.py`), which uses the "
        f"`rocrate` (ro-crate-py) library on the linked internal-format instance "
        f"`../internal-format/linked-instance.example.json`.\n"
        f"\n"
        f"## Validate\n\n"
        f"Validate the **whole directory** (not just the metadata file) with an "
        f"RO-Crate validator such as `nova-crate` (spec-v1.1).\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
@click.group("crate")
@click.pass_context
def crate_group(ctx):
    """CF2-006: generate a self-contained RO-Crate from the internal format."""
    ctx.ensure_object(dict)


@crate_group.command("generate")
@click.option("--input", "input_file", type=click.Path(exists=True, dir_okay=False),
              default=str(LINKED_DEFAULT), show_default=True,
              help="Internal-format JSON-LD instance (linked DMP+SMS, CF2-005).")
@click.option("--out", "out_dir", type=click.Path(file_okay=False), default=None,
              help="Crate directory (default: data/crate/<timestamp>).")
@click.pass_context
def generate_cmd(ctx, input_file, out_dir):
    """Generate a self-contained RO-Crate directory from the internal format.

    Writes ro-crate-metadata.json, data/project-graph.jsonld, README.md and
    validation-report.json, prints the structural self-check, then zips the
    finished crate into <crate-dir>.zip. Validate the whole directory with
    nova-crate (spec-v1.1).
    """
    src = Path(input_file)
    doc = json.loads(src.read_text(encoding="utf-8"))
    ds_title = _first_text(_as_dict(_val(doc, "dcat:dataset")), "dcterms:title") \
        or "Dataset"

    out = (Path(out_dir) if out_dir else PROTO_DIR / "data" / "crate"
           / _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)

    crate = _build(doc, src, out)
    crate.write(out)

    report = _validate(out, out.name, src)
    (out / "validation-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "README.md").write_text(_readme(out.name, ds_title), encoding="utf-8")

    for c in report["checks"]:
        mark = "ok" if c["ok"] else "FAIL"
        click.echo(f"  [{mark}] {c['desc']}"
                   + (f"  ({c.get('detail')})" if c.get("detail") else ""))
    click.echo(f"Crate written to {out} — verdict: {report['verdict']}")
    click.echo("Validate the whole directory with nova-crate, e.g.:")
    click.echo(f"  nova-v1.1 validate {out}")

    # package the finished crate directory into a zip archive next to it
    zip_path = shutil.make_archive(str(out), "zip", root_dir=out.parent,
                                   base_dir=out.name)
    click.echo(f"Archive written to {zip_path}")
