"""agnostic_trip.py — map-driven round trip, realisation of card CF2-004.

This is the **second, agnostic way** of performing the CF2-003 transformation:
instead of hand-coding every rule of `scripts/trafos/patterns.md` in Python
(``trip.py``, card CF2-003), the transformation logic lives in two **LinkML
Map** files (linkml-map TransformationSpecifications) that compile the
catalogue:

  * ``scripts/trafos/dmp-to-internal.linkml-map.yaml``  — rules P1–P42
  * ``scripts/trafos/sms-to-internal.linkml-map.yaml``  — rules S1–S16

The executing tool (`fuseki-proto agnostic-trip`) is *agnostic* with respect
to the rules: it only wires the engine and serialises the result.

Pipeline (the three CF2-003 scenarios, re-used as acceptance criteria):

  1. **transform** — the linkml-map ObjectTransformer applies the two map
     files to the maDMP export and the SMS device/property records; a
     schema-driven serialiser walks the transformed objects and emits the
     internal-format Turtle graph. Every predicate, datatyping and class IRI
     is derived from `05_P05_S05_internal-format-schema.yaml` (slot
     `mappings`, ranges, `class_uri`) — no rule is hard-coded here.
  2. **store** — the graph is loaded into the `/projects` TDB2 dataset,
     checked for retrievability via SPARQL and (when `pyshacl` is available)
     validated against `shapes/project-claim-shapes.ttl`.
  3. **verify** — `/projects` is dumped, the dump is replayed into the named
     graph `<urn:edo:agnostic-trip:replay>` and the same 41 field-level
     checks as in CF2-003 (imported from `trip.py`: catalogue-level,
     implementation-independent) run against the replay graph AND the store.

`run` executes all three stages. Artifacts land in
`data/agnostic-trip/<timestamp>/` next to the prototype's `data/` directory:

  * `project-graph.ttl`         — the transformed internal-format instance graph
  * `roundtrip-dump.ttl`        — the Turtle dump served back by Fuseki
  * `agnostic-trip-report.json` — map files, derivations, transformed objects,
                                  stages, checks and verdicts

Differences to the CF2-003 `trip.py` output (documented, both faithful):

  * The serialiser emits `rdf:type` for EVERY nested class node — trip.py
    omitted the type for Interval and the three Identifier blank nodes. The
    agnostic graph therefore holds 4 more triples (82 vs. 78) with identical
    content otherwise; the verification compares store vs. replay *within*
    this run, so the count check is unaffected.

Engine-level adaptations (JSON:API envelope, not expressible in a map):

  * SMS `data/attributes` are filtered to schema-known Device slots and the
    `device_properties` list (the per-property JSON:API records) is assembled
    under the `device_properties` key before `map_object` runs.
  * The device IRI is minted from the JSON:API `data/id` (S6) and handed to
    the serialiser as context; the Project IRI comes from the transformed
    `dmp_id.identifier_value` (P5).

Run it either standalone (``python -m fuseki_proto.agnostic_trip run``) or
through the maintenance CLI (``fuseki-proto agnostic-trip run``).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import urllib.parse
from importlib.metadata import version as _package_version
from pathlib import Path

import click
from linkml_runtime import SchemaView
from linkml_map.transformer.object_transformer import ObjectTransformer

from . import docker as D
from .trip import (DMP_DEFAULT, DEVICE_DEFAULT, SHAPES_FILE, SPARQL_PREFIXES,
                   Builder, TurtleGraph, _build_checks,
                   _default_property_files, _load_json, ask, count, date_lit,
                   dec_lit, iri, shacl_validate, sparql, sparql_update,
                   ttl_escape)

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
TOOL_DIR = D.TOOL_DIR                      # .../fuseki-proto/tool
PROTO_DIR = TOOL_DIR.parent                # .../fuseki-proto
SCRIPTS_DIR = PROTO_DIR.parent             # .../scripts
TRAFO_DIR = SCRIPTS_DIR / "trafos"
LINKML_DIR = SCRIPTS_DIR / "linkml"
DMP_MAP_DEFAULT = TRAFO_DIR / "dmp-to-internal.linkml-map.yaml"
SMS_MAP_DEFAULT = TRAFO_DIR / "sms-to-internal.linkml-map.yaml"
MADMP_SCHEMA = LINKML_DIR / "05_P05_S05_madmp-schema.yaml"
SMS_SCHEMA = LINKML_DIR / "05_P05_S05_sms-schema.yaml"
INTERNAL_SCHEMA = LINKML_DIR / "05_P05_S05_internal-format-schema.yaml"
SMS_DIR = SCRIPTS_DIR / "sms"
AGNOSTIC_DIR = PROTO_DIR / "data" / "agnostic-trip"

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
SMS_DEVICE_BASE = "https://sms.atmohub.kit.edu/devices/"
REPLAY_GRAPH = "urn:edo:agnostic-trip:replay"

# linkml-map logs one warning per class-range coercion ("Unknown target range
# Dataset" etc.) — harmless but noisy; keep the run output readable.
logging.getLogger("linkml_map.transformer.transformer").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# map execution (scenario 1, stage 1)
# ---------------------------------------------------------------------------
def run_map(map_file: Path, source_schema: Path, source_obj: dict,
            source_type: str) -> dict:
    """Apply one LinkML Map to one source object via linkml-map.

    The map file carries the whole transformation logic (slot derivations,
    expressions, value tables, reconciliation patches); this function only
    wires source/target schema views and the ObjectTransformer.
    """
    tr = ObjectTransformer(unrestricted_eval=True)
    tr.source_schemaview = SchemaView(str(source_schema))
    tr.load_transformer_specification(str(map_file))
    tr.target_schemaview = SchemaView(str(INTERNAL_SCHEMA))
    return tr.map_object(source_obj, source_type=source_type)


def _prepare_sms_attributes(device: dict, properties: list[dict],
                            sv: SchemaView) -> dict:
    """Unwrap the JSON:API envelope into a Device-shaped dict for the map.

    Filters both the device attributes and each device-property record to the
    slots the SMS schema knows (the export carries extra JSON:API fields the
    schema deliberately ignores) and assembles `device_properties` from the
    separately fetched property records — the map then addresses everything
    through normal slot derivations.
    """
    device_slots = {s.name for s in sv.class_induced_slots("Device")}
    prop_slots = {s.name for s in sv.class_induced_slots("DeviceProperty")}
    attrs = {k: v for k, v in device["data"]["attributes"].items()
             if k in device_slots}
    attrs["device_properties"] = [
        {k: v for k, v in p["data"]["attributes"].items() if k in prop_slots}
        for p in properties
    ]
    return attrs


# ---------------------------------------------------------------------------
# schema-driven serialiser (scenario 1, stage 2)
# ---------------------------------------------------------------------------
def _lower_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class GraphSerializer:
    """Serialises transformed objects into Turtle, driven by the internal schema.

    Everything is derived from `05_P05_S05_internal-format-schema.yaml`:
    predicate = first slot `mappings` entry (else `<default_prefix>:<lowerCamel>`),
    datatyping = slot range (date/decimal/boolean/uriorcurie), node types =
    class `class_uri`. Only the subject-IRI strategy is fixed in code
    (documented CF2-004 decision): Project <- dmp_id.identifier_value,
    Dataset <- <project>/dataset:<urlquoted identifier_value>, Sensor <-
    SMS device base + id (context), everything else blank nodes.
    """

    def __init__(self, sv: SchemaView):
        self.sv = sv
        self.g = TurtleGraph()
        self._classes = sv.all_classes()
        self._bnode_n = 0

    def bnode(self) -> str:
        self._bnode_n += 1
        return f"_:b{self._bnode_n}"

    def class_uri(self, class_name: str) -> str:
        cd = self.sv.get_class(class_name)
        if cd is None:
            return class_name
        return cd.class_uri or (cd.mappings[0] if cd.mappings else class_name)

    def predicate(self, slot) -> str:
        if slot.mappings:
            return slot.mappings[0]
        schema = self.sv.schema
        prefix = (schema.default_prefix if schema is not None else None) or "edo"
        return f"{prefix}:{_lower_camel(slot.name)}"

    def literal(self, slot, predicate: str, value) -> str:
        rng = slot.range
        if rng == "boolean":
            return "true" if value else "false"
        if rng == "date":
            return date_lit(value)
        if rng == "decimal":
            return dec_lit(value)
        if rng == "uriorcurie":
            # foaf:mbox is typed xsd:anyURI per the internal-format spec §3.2
            # and foaf:PersonShape — an IRI would violate the shape (CF2-003).
            if predicate == "foaf:mbox":
                return f'"{ttl_escape(value)}"^^xsd:anyURI'
            return iri(str(value))
        return f'"{ttl_escape(value)}"'

    @staticmethod
    def _has_content(obj: dict) -> bool:
        return any(v is not None for v in obj.values())

    def serialize(self, class_name: str, obj: dict, subject: str | None = None,
                  project_iri: str | None = None) -> None:
        """Emit one node (and recursively its inlined children) as triples."""
        if subject is None:
            subject = self.bnode()
        self.g.add(subject, "a", self.class_uri(class_name))
        for slot in self.sv.class_induced_slots(class_name):
            value = obj.get(slot.name)
            if value is None:
                continue
            predicate = self.predicate(slot)
            if slot.range in self._classes:
                items = value if slot.multivalued and isinstance(value, list) \
                    else [value]
                for item in items:
                    if not isinstance(item, dict) or not self._has_content(item):
                        continue
                    child = self.bnode()
                    if class_name == "Project" and slot.name == "has_dataset":
                        # Dataset IRI minted from its Identifier (P18/P19):
                        # <dmp_id>/dataset:<urlquoted identifier_value>
                        ident = (item.get("identifier") or {}).get("identifier_value")
                        child = iri(f"{project_iri}/dataset:"
                                    f"{urllib.parse.quote(str(ident), safe='')}")
                    self.g.add(subject, predicate, child)
                    self.serialize(str(slot.range), item, child, project_iri)
            else:
                values = value if slot.multivalued and isinstance(value, list) \
                    else [value]
                values = [v for v in values if v is not None]
                for v in values:
                    self.g.add(subject, predicate, self.literal(slot, predicate, v))


# ---------------------------------------------------------------------------
# transformation (scenario 1)
# ---------------------------------------------------------------------------
def transform(dmp: dict, device: dict | None, properties: list[dict],
              dmp_map: Path = DMP_MAP_DEFAULT,
              sms_map: Path = SMS_MAP_DEFAULT):
    """Run both maps and serialize the transformed objects into one graph.

    Returns ``(turtle, checks, meta)`` where ``checks`` are the CF2-003
    catalogue checks (imported from trip.py) and ``meta`` documents the maps,
    the applied derivations and the transformed objects.
    """
    # --- DMP half ------------------------------------------------------------
    project_obj = run_map(dmp_map, MADMP_SCHEMA, dmp["dmp"], "DMP")

    # --- SMS half ------------------------------------------------------------
    sensor_obj = None
    device_id = None
    if device:
        sms_sv = SchemaView(str(SMS_SCHEMA))
        attrs = _prepare_sms_attributes(device, properties, sms_sv)
        device_id = device["data"]["id"]
        sensor_obj = run_map(sms_map, SMS_SCHEMA, attrs, "Device")

    # --- serialise both halves into one graph --------------------------------
    ser = GraphSerializer(SchemaView(str(INTERNAL_SCHEMA)))
    project_iri = project_obj["dmp_id"]["identifier_value"]
    ser.serialize("Project", project_obj, iri(project_iri), project_iri)
    sensor_iri = None
    if sensor_obj is not None:
        sensor_iri = f"{SMS_DEVICE_BASE}{device_id}"
        ser.serialize("Sensor", sensor_obj, iri(sensor_iri), project_iri)

    # --- verification checks (catalogue-level, from trip.py) -----------------
    b = Builder()
    _build_checks(b, dmp, device, properties)

    meta = {
        "project_iri": project_iri,
        "sensor_iri": sensor_iri,
        "map_files": {"dmp": str(dmp_map), "sms": str(sms_map)},
        "linkml_map_version": _package_version("linkml-map"),
        "derivations": [_derivation_summary(dmp_map), _derivation_summary(sms_map)],
        "transformed_project": project_obj,
        "transformed_sensor": sensor_obj,
        "notes": [
            "The serialiser emits rdf:type for every nested class node; "
            "trip.py (CF2-003) omitted it for Interval and Identifier blank "
            "nodes — the agnostic graph therefore holds 4 more triples "
            "(82 vs. 78) with otherwise identical content.",
            "SHACL: the faithful P6 omission of edo:hasContact (absent in the "
            "export) still trips the project-claim-shapes.ttl sh:minCount 1 "
            "(documented conflict, CF2-003 finding F1).",
        ],
    }
    return ser.g.turtle(), b.checks, meta


def _derivation_summary(map_file: Path) -> dict:
    """Summarise a map file's class derivations for the report."""
    import yaml

    with open(map_file, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    derivs = []
    for cd in spec.get("class_derivations", {}).values():
        derivs.append({
            "derivation": cd.get("name") if isinstance(cd, dict) else None,
            "populated_from": cd.get("populated_from"),
            "slot_derivations": {
                slot: ({"populated_from": sd.get("populated_from")}
                       if sd.get("populated_from") else {"expr": sd.get("expr")})
                for slot, sd in (cd.get("slot_derivations") or {}).items()
            },
        })
    return {"file": str(map_file), "class_derivations": derivs}


# ---------------------------------------------------------------------------
# artifact/report helpers
# ---------------------------------------------------------------------------
def _latest_artifacts_dir() -> Path | None:
    if not AGNOSTIC_DIR.exists():
        return None
    dirs = sorted(p for p in AGNOSTIC_DIR.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


def _patch_latest_report(patch: dict) -> None:
    latest = _latest_artifacts_dir()
    path = latest / "agnostic-trip-report.json" if latest else None
    if not path or not path.exists():
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    for key, value in patch.items():
        if isinstance(value, dict):
            report.setdefault(key, {}).update(value)
        else:
            report[key] = value
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                    encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
@click.group("agnostic-trip")
@click.option("--port", default=3031, type=int, show_default=True,
              help="Fuseki HTTP port (host side).")
@click.option("--user", default="admin", show_default=True, help="Fuseki admin user.")
@click.option("--password", default="edo-proto", show_default=True,
              help="Fuseki admin password.")
@click.option("--dataset", default="projects", show_default=True,
              help="Fuseki dataset for the instance graph.")
@click.pass_context
def agnostic_trip(ctx, port, user, password, dataset):
    """CF2-004 round trip: map-driven transform -> store -> dump -> verify.

    Realises the CF2-003 scenarios with the transformation logic taken from
    the LinkML Map files in scripts/trafos/ (dmp-to-internal and
    sms-to-internal); see scripts/trafos/README.md for the full documentation.
    """
    ctx.obj = {
        "base_url": f"http://127.0.0.1:{port}",
        "user": user, "password": password, "dataset": dataset,
    }


@agnostic_trip.command("transform")
@click.option("--dmp", "dmp_path", type=click.Path(exists=True, dir_okay=False),
              default=str(DMP_DEFAULT), show_default=True,
              help="maDMP export (JSON) to transform.")
@click.option("--sms-device", "device_path", type=click.Path(exists=True, dir_okay=False),
              default=str(DEVICE_DEFAULT), show_default=True,
              help="SMS device JSON:API record.")
@click.option("--sms-property", "property_paths", multiple=True,
              type=click.Path(exists=True, dir_okay=False),
              default=[str(p) for p in _default_property_files()],
              show_default="(all device-*-property-*.json under scripts/sms/)",
              help="SMS device-property JSON:API records (repeatable).")
@click.option("--dmp-map", "dmp_map", type=click.Path(exists=True, dir_okay=False),
              default=str(DMP_MAP_DEFAULT), show_default=True,
              help="LinkML Map for the DMP half (rules P1–P42).")
@click.option("--sms-map", "sms_map", type=click.Path(exists=True, dir_okay=False),
              default=str(SMS_MAP_DEFAULT), show_default=True,
              help="LinkML Map for the SMS half (rules S1–S16).")
@click.option("--out", "out_dir", type=click.Path(file_okay=False), default=None,
              help="Artifacts directory (default: data/agnostic-trip/<timestamp>).")
@click.pass_obj
def transform_cmd(obj, dmp_path, device_path, property_paths, dmp_map, sms_map,
                  out_dir):
    """Scenario 1: apply the LinkML Maps and emit the internal-format graph."""
    out = Path(out_dir) if out_dir else AGNOSTIC_DIR / _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    dmp = _load_json(Path(dmp_path))
    device = _load_json(Path(device_path)) if device_path else None
    properties = [_load_json(Path(p)) for p in property_paths]
    turtle, checks, meta = transform(dmp, device, properties,
                                     dmp_map=Path(dmp_map), sms_map=Path(sms_map))
    (out / "project-graph.ttl").write_text(turtle, encoding="utf-8")
    report = {
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
        "tool": "agnostic-trip (CF2-004)",
        "inputs": {"dmp": str(dmp_path), "sms_device": str(device_path),
                   "sms_properties": list(property_paths)},
        "maps": meta["map_files"],
        "linkml_map_version": meta["linkml_map_version"],
        "stages": {"transform": {
            "project_iri": meta["project_iri"],
            "sensor_iri": meta["sensor_iri"],
            "derivations": meta["derivations"],
            "transformed_project": meta["transformed_project"],
            "transformed_sensor": meta["transformed_sensor"],
            "notes": meta["notes"]}},
        "checks": [{"id": c["id"], "rule": c["rule"],
                    "description": c["description"], "kind": c["kind"]}
                   for c in checks],
    }
    (out / "agnostic-trip-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(f"Transformed {Path(dmp_path).name} + SMS via LinkML Maps "
               f"(project {meta['project_iri']}, sensor {meta['sensor_iri']}); "
               f"linkml-map {meta['linkml_map_version']}.")
    for note in meta["notes"]:
        click.echo(f"  NOTE: {note}")
    click.echo(f"Graph written to {out / 'project-graph.ttl'}")


@agnostic_trip.command("store")
@click.option("--graph", "graph_path", type=click.Path(exists=True, dir_okay=False),
              default=None, help="Graph to store (default: latest agnostic-trip artifacts).")
@click.option("--wipe/--no-wipe", default=True, show_default=True,
              help="CLEAR the dataset default graph before loading (destructive).")
@click.option("--validate/--no-validate", default=True, show_default=True,
              help="Validate the stored graph with pyshacl (if available).")
@click.pass_obj
def store_cmd(obj, graph_path, wipe, validate):
    """Scenario 2: store the transformed project in the /projects dataset."""
    base, ds, user, password = (obj["base_url"], obj["dataset"],
                                obj["user"], obj["password"])
    graph = Path(graph_path) if graph_path else None
    if graph is None:
        latest = _latest_artifacts_dir()
        if not latest:
            raise click.ClickException("No agnostic-trip artifacts found — run "
                                       "`fuseki-proto agnostic-trip transform` first.")
        graph = latest / "project-graph.ttl"

    if wipe:
        sparql_update(base, ds, user, password, "CLEAR DEFAULT")
        click.echo(f"Cleared default graph of /{ds}.")
    D.http_upload(f"{base}/{ds}/data", user, password, graph,
                  content_type="text/turtle")
    click.echo(f"Loaded {graph.name} into /{ds} (default graph).")

    result = sparql(base, ds, user, password, SPARQL_PREFIXES +
                    "SELECT ?title ?dmpId WHERE { ?p a edo:Project ; "
                    "dcterms:title ?title ; edo:dmpId ?id . "
                    "?id dcterms:identifier ?dmpId }")
    rows = result.get("results", {}).get("bindings", [])
    if not rows:
        raise click.ClickException("Stored graph is NOT retrievable — no "
                                   "edo:Project found via /query.")
    title = rows[0]["title"]["value"]
    dmp_id = rows[0]["dmpId"]["value"]
    click.echo(f"Retrievable via /{ds}/query: project {title!r} "
               f"(dmp_id {dmp_id!r}).")
    triples = count(base, ds, user, password, "?s ?p ?o", None)
    click.echo(f"Default graph now holds {triples} triples.")

    shacl = {"ran": False}
    if validate:
        shacl = shacl_validate(graph, SHAPES_FILE)
        if shacl.get("ran"):
            if shacl["conforms"]:
                click.echo("SHACL: graph CONFORMS to project-claim-shapes.ttl.")
            else:
                click.echo("SHACL: graph does NOT conform — violations reported below.")
                click.echo(shacl.get("output", ""))
        else:
            click.echo(f"SHACL: skipped ({shacl.get('note')})")

    _patch_latest_report({"stages": {"store": {
        "graph": str(graph), "triples": triples,
        "retrievable": {"title": title, "dmp_id": dmp_id},
        "shacl": {k: v for k, v in shacl.items() if k != "output"} | (
            {"output_tail": shacl.get("output", "")} if shacl.get("ran") else {})}}})


@agnostic_trip.command("verify")
@click.option("--dmp", "dmp_path", type=click.Path(exists=True, dir_okay=False),
              default=str(DMP_DEFAULT), show_default=True)
@click.option("--sms-device", "device_path", type=click.Path(exists=True, dir_okay=False),
              default=str(DEVICE_DEFAULT), show_default=True)
@click.option("--sms-property", "property_paths", multiple=True,
              type=click.Path(exists=True, dir_okay=False),
              default=[str(p) for p in _default_property_files()],
              show_default="(all device-*-property-*.json under scripts/sms/)")
@click.pass_obj
def verify_cmd(obj, dmp_path, device_path, property_paths):
    """Scenario 3: dump /projects and verify field-level equality with the sources."""
    base, ds, user, password = (obj["base_url"], obj["dataset"],
                                obj["user"], obj["password"])
    latest = _latest_artifacts_dir()
    if not latest:
        raise click.ClickException("No agnostic-trip artifacts found — run "
                                   "`fuseki-proto agnostic-trip transform` first.")

    dmp = _load_json(Path(dmp_path))
    device = _load_json(Path(device_path)) if device_path else None
    properties = [_load_json(Path(p)) for p in property_paths]
    _, checks, _ = transform(dmp, device, properties)

    # 1. dump the stored graph back out
    dump = D.dump_graph(base, ds, user, password)
    dump_path = latest / "roundtrip-dump.ttl"
    dump_path.write_bytes(dump)
    click.echo(f"Dumped /{ds} -> {dump_path} ({len(dump)} bytes).")

    # 2. replay the dump into a named graph (the dump is the round-trip
    #    artifact under test: what Fuseki served must parse and re-load)
    sparql_update(base, ds, user, password,
                  f"DROP SILENT GRAPH <{REPLAY_GRAPH}>")
    D._req("POST", f"{base}/{ds}/data?graph={urllib.parse.quote(REPLAY_GRAPH, safe='')}",
           user, password, data=dump, content_type="text/turtle", timeout=120.0)
    replay_triples = count(base, ds, user, password, "?s ?p ?o", REPLAY_GRAPH)
    default_triples = count(base, ds, user, password, "?s ?p ?o", None)
    click.echo(f"Re-uploaded dump into <{REPLAY_GRAPH}> "
               f"({replay_triples} triples; default graph: {default_triples}).")

    # 3. field-level checks: against the replay graph (the dump) AND the
    #    default graph (the store)
    results = []
    for check in checks:
        pattern = check["pattern"]
        replay = ask(base, ds, user, password, pattern, REPLAY_GRAPH)
        default = ask(base, ds, user, password, pattern, None)
        passed = (replay == (check["kind"] != "absent")) and \
                 (default == (check["kind"] != "absent"))
        results.append({**{k: v for k, v in check.items() if k != "pattern"},
                        "result": {"replay": replay, "default": default},
                        "pass": passed})

    counts_equal = replay_triples == default_triples
    passed_n = sum(1 for r in results if r["pass"])
    failed = [r for r in results if not r["pass"]]

    click.echo("")
    click.echo(f"Round-trip checks: {passed_n}/{len(results)} passed "
               f"(replay graph vs. original DMP/SMS sources).")
    for r in failed:
        click.echo(f"  FAIL [{r['id']}] ({r['rule']}) {r['description']}: "
                   f"replay={r['result']['replay']} default={r['result']['default']}")
    click.echo(f"Triple-count equality default vs. replay: "
               f"{'OK' if counts_equal else 'MISMATCH'} "
               f"({default_triples} vs. {replay_triples}).")

    report_path = latest / "agnostic-trip-report.json"
    report = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    report.setdefault("stages", {})["verify"] = {
        "dump": str(dump_path), "replay_graph": REPLAY_GRAPH,
        "triple_counts": {"default": default_triples, "replay": replay_triples,
                          "equal": counts_equal},
        "summary": {"total": len(results), "passed": passed_n, "failed": len(failed)},
    }
    report["checks"] = results
    report["summary"] = {"total": len(results), "passed": passed_n,
                         "failed": len(failed), "triple_counts_equal": counts_equal}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    click.echo(f"Report updated: {report_path}")

    if failed or not counts_equal:
        raise SystemExit(1)


@agnostic_trip.command("run")
@click.pass_context
def run_cmd(ctx):
    """All three scenarios: transform -> store -> verify."""
    ctx.invoke(transform_cmd)
    ctx.invoke(store_cmd)
    ctx.invoke(verify_cmd)
